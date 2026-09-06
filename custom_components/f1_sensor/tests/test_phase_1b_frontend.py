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
const actionSource = fs.readFileSync(process.env.F1_ACTION_PATH, "utf8");

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

const helperStart = actionSource.indexOf("export const handleF1CardActionKeydown =");
const helperBrace = actionSource.indexOf("{", helperStart);
const helperEnd = actionSource.indexOf(";", findMatchingBrace(actionSource, helperBrace));
const helper = actionSource.slice(helperStart, helperEnd + 1).replace("export ", "");
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

NODE_RACE_CONTROL_SAFETY_PROBE = r"""
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

function extractMethod(signature) {
  const classStart = source.indexOf("class F1RaceControlCard extends LitElement");
  const methodStart = source.indexOf(signature, classStart);
  const braceStart = source.indexOf("{", methodStart);
  return source.slice(methodStart, findMatchingBrace(source, braceStart) + 1);
}

const formatMethod = extractMethod("_formatListTime(value) {");
const resetMethod = extractMethod("_resetClearConfirmation() {");
const requestMethod = extractMethod("_requestClearConfirmation() {");
const clearMethod = extractMethod("async _handleClearList(ev) {");

const formatHassDateTime = (hass, date, options, fallback) => {
  try {
    return new Intl.DateTimeFormat(hass.locale.language, {
      ...options,
      timeZone: hass.config.time_zone,
      hour12: false,
    }).format(date);
  } catch (_err) {
    return fallback;
  }
};
const resolveEntityIdWithFallback = (_hass, entity) => entity;

const Harness = new Function(
  "formatHassDateTime",
  "resolveEntityIdWithFallback",
  `return class Harness {
    constructor() {
      this.hass = {
        locale: { language: "en", time_format: "24" },
        config: { time_zone: "Europe/Stockholm" },
        calls: [],
        async callService(domain, service, data) {
          this.calls.push({ domain, service, data });
        },
      };
      this.config = { entity: "sensor.f1_race_control" };
      this._listMessages = [{ sequence: 1 }];
      this._listError = "old";
      this._isClearing = false;
      this._clearConfirmationPending = false;
      this._clearConfirmationTimer = null;
    }
    ${formatMethod}
    ${resetMethod}
    ${requestMethod}
    ${clearMethod}
  }`,
)(formatHassDateTime, resolveEntityIdWithFallback);

(async () => {
  const host = new Harness();
  const firstEvent = { stopped: false, stopPropagation() { this.stopped = true; } };
  await host._handleClearList(firstEvent);
  const afterFirst = {
    stopped: firstEvent.stopped,
    pending: host._clearConfirmationPending,
    calls: host.hass.calls.length,
  };
  await host._handleClearList({ stopPropagation() {} });
  process.stdout.write(JSON.stringify({
    formatted: host._formatListTime("2026-01-01T00:00:00Z"),
    afterFirst,
    afterSecond: {
      pending: host._clearConfirmationPending,
      calls: host.hass.calls,
      messages: host._listMessages,
      error: host._listError,
    },
  }));
})().catch((err) => {
  process.stderr.write(String(err));
  process.exit(1);
});
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
    env["F1_ACTION_PATH"] = str(bundled_card_path.parent / "platform" / "actions.js")
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


def test_race_control_uses_ha_timezone_and_confirms_before_clear(
    bundled_card_path: Path,
) -> None:
    """Race Control follows HA time and requires a deliberate second clear click."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for frontend interaction tests")
    env = os.environ.copy()
    env["F1_CARD_PATH"] = str(bundled_card_path)
    completed = subprocess.run(
        [node, "-e", NODE_RACE_CONTROL_SAFETY_PROBE],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    payload = json.loads(completed.stdout)
    assert payload["formatted"] == "01:00:00"
    assert payload["afterFirst"] == {"stopped": True, "pending": True, "calls": 0}
    assert payload["afterSecond"] == {
        "pending": False,
        "calls": [
            {
                "domain": "f1_sensor",
                "service": "clear_race_control_log",
                "data": {"entity_id": "sensor.f1_race_control"},
            }
        ],
        "messages": [],
        "error": None,
    }


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
    accessibility_source = _source(
        bundled_card_path.parent / "platform" / "accessibility.js"
    )

    assert "installF1CardActionAccessibility" in source
    assert "installF1EditorTabAccessibility" in source
    assert (
        "const installF1CardActionAccessibility = (CardClass) =>"
        in accessibility_source
    )
    assert (
        "const installF1EditorTabAccessibility = (EditorClass) =>"
        in accessibility_source
    )
    assert (
        "const installF1GridTableAccessibility = (CardClass, prefix, label) =>"
        in accessibility_source
    )
    assert "tabList.setAttribute('role', 'tablist');" in accessibility_source
    assert (
        "tab.setAttribute('aria-selected', selected ? 'true' : 'false');"
        in accessibility_source
    )
    assert "['ArrowLeft', 'ArrowRight', 'Home', 'End']" in accessibility_source
    assert "aria-live=${criticalClass ? 'assertive' : 'polite'}" in source
    assert 'role="table" aria-label="Pit stops and tyres"' in source
