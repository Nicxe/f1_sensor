"""Regression gates for the Phase 1B realtime frontend work."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

NODE_PIT_ACTION_PROBE = r"""
const fs = require("node:fs");
const source = fs.readFileSync(process.env.F1_CARD_PATH, "utf8");

function findMatchingBrace(text, openIndex) {
  let depth = 0;
  for (let index = openIndex; index < text.length; index += 1) {
    if (text[index] === "{") depth += 1;
    if (text[index] === "}") depth -= 1;
    if (depth === 0) return index;
  }
  throw new Error("Unbalanced source block");
}

function extractMethod(className, signature) {
  const classStart = source.indexOf(`class ${className} extends LitElement`);
  const methodStart = source.indexOf(signature, classStart);
  const braceStart = source.indexOf("{", methodStart);
  return source.slice(methodStart, findMatchingBrace(source, braceStart) + 1);
}

const helperStart = source.indexOf("const handleF1CardActionKeydown =");
const helperBrace = source.indexOf("{", helperStart);
const helperEnd = source.indexOf(";", findMatchingBrace(source, helperBrace));
const helper = source.slice(helperStart, helperEnd + 1);
const pitAction = extractMethod("F1PitStopOverviewCard", "_handleCardAction() {");

const Harness = new Function("CustomEvent", `
  ${helper}
  class PitHarness {
    constructor() {
      this.config = { drivers_entity: "sensor.f1_driver_list" };
      this.events = [];
    }
    dispatchEvent(event) { this.events.push(event); }
    ${pitAction}
  }
  return { PitHarness, handleF1CardActionKeydown };
`)(class CustomEvent {
  constructor(type, options) {
    this.type = type;
    Object.assign(this, options);
  }
});

const host = new Harness.PitHarness();
host._handleCardAction();
for (const key of ["Enter", " ", "Escape"]) {
  const event = {
    key,
    target: host,
    currentTarget: host,
    prevented: false,
    preventDefault() { this.prevented = true; },
  };
  Harness.handleF1CardActionKeydown(host, event);
}

process.stdout.write(JSON.stringify({
  eventCount: host.events.length,
  eventTypes: host.events.map((event) => event.type),
  entityIds: host.events.map((event) => event.detail.entityId),
}));
"""


def _source(card_path: Path) -> str:
    return card_path.read_text(encoding="utf-8")


def _class_block(source: str, class_name: str, next_class_name: str) -> str:
    start = source.index(f"class {class_name} extends LitElement")
    end = source.index(f"class {next_class_name} extends LitElement", start)
    return source[start:end]


def test_bundled_card_is_valid_javascript(bundled_card_path: Path) -> None:
    """The shipped card must parse in the same Node runtime used by CI."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for frontend syntax validation")
    subprocess.run(
        [node, "--check", str(bundled_card_path)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_pit_stop_default_action_supports_click_and_keyboard(
    bundled_card_path: Path,
) -> None:
    """The default Pit Stops config opens its drivers entity from all inputs."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for frontend interaction tests")
    env = os.environ.copy()
    env["F1_CARD_PATH"] = str(bundled_card_path)
    completed = subprocess.run(
        [node, "-e", NODE_PIT_ACTION_PROBE],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert json.loads(completed.stdout) == {
        "eventCount": 3,
        "eventTypes": ["hass-more-info"] * 3,
        "entityIds": ["sensor.f1_driver_list"] * 3,
    }


def test_race_control_teardown_rejects_late_callbacks(
    bundled_card_path: Path,
) -> None:
    """Race Control subscriptions are generation-bound and visibly retry errors."""
    source = _source(bundled_card_path)
    block = _class_block(source, "F1RaceControlCard", "F1RaceControlCardEditor")

    assert "this._listGeneration += 1;" in block
    assert "this._listLoadToken += 1;" in block
    assert "this._isListContextActive(contextKey, generation)" in block
    assert "this._callUnsubscribe(eventUnsub);" in block
    assert "this._scheduleListSubscriptionRetry(contextKey, generation);" in block
    assert "Live feed unavailable; showing saved messages" in block


def test_track_map_subscription_retries_and_survives_remount(
    bundled_card_path: Path,
) -> None:
    """Track Map owns its callbacks, retry timer and resize observer lifecycle."""
    source = _source(bundled_card_path)
    block = _class_block(source, "F1TrackMapCard", "F1TrackMapCardEditor")

    assert (
        "if (!this.isConnected || token !== this._subscriptionToken) return;" in block
    )
    assert "this._scheduleSubscriptionRetry(key, token);" in block
    assert "this._clearSubscriptionRetry();" in block
    assert "if (this.isConnected) this._ensureResizeObserver();" in block
    assert "this._resizeObserver.disconnect();" in block
    assert '<canvas role="img" aria-label=${textAlternative}></canvas>' in block
    assert '<div class="f1-visually-hidden">${textAlternative}</div>' in block


def test_phase_1b_accessibility_contract_is_installed(
    bundled_card_path: Path,
) -> None:
    """Interactive cards, editors and timing grids expose keyboard semantics."""
    source = _source(bundled_card_path)

    assert "const installF1CardActionAccessibility = (CardClass) =>" in source
    assert "const installF1EditorTabAccessibility = (EditorClass) =>" in source
    assert (
        "const installF1GridTableAccessibility = (CardClass, prefix, label) =>"
        in source
    )
    assert "tabList.setAttribute('role', 'tablist');" in source
    assert "tab.setAttribute('aria-selected', selected ? 'true' : 'false');" in source
    assert "['ArrowLeft', 'ArrowRight', 'Home', 'End']" in source
    assert "aria-live=${criticalClass ? 'assertive' : 'polite'}" in source
    assert 'role="table" aria-label="Pit stops and tyres"' in source
