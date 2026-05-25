"""Regression tests for No Spoiler Mode card overlay behavior."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
BUNDLED_CARD_PATH = (
    ROOT
    / "custom_components"
    / "f1_sensor"
    / "www"
    / "f1-sensor-live-data-card"
    / "f1-sensor-live-data-card.js"
)
RUNTIME_CARD_PATH = ROOT / "www" / "f1-sensor-live-data-card.js"

SPOILER_CARD_CLASSES = (
    "F1TyreStatisticsCard",
    "F1PitStopOverviewCard",
    "F1DriverLapTimesCard",
    "F1ChampionshipPredictionDriversCard",
    "F1ChampionshipPredictionTeamsCard",
    "F1LastRaceResultsCard",
    "F1InvestigationsCard",
    "F1TrackLimitsCard",
    "F1LiveSessionCard",
    "F1RaceControlCard",
    "F1FiaDocumentsCard",
    "F1QualifyingTimingCard",
    "F1PracticeTimingCard",
    "F1RaceLapCard",
    "F1StartingGridCard",
)
NON_SPOILER_CARD_CLASSES = (
    "F1ReplayControlCard",
    "F1NextRaceCard",
    "F1SeasonCalendarCard",
)

NODE_OVERLAY_PROBE = r"""
const fs = require("node:fs");

const source = fs.readFileSync(process.env.NO_SPOILER_CARD_PATH, "utf8");
const start = source.indexOf("const DEFAULT_NO_SPOILER_ENTITY =");
const end = source.indexOf("const measureRenderedCardHeight =", start);
if (start === -1 || end === -1) {
  throw new Error("No Spoiler overlay helper block not found");
}

const helperSource = source.slice(start, end);
const html = (strings, ...values) => strings.reduce(
  (result, part, index) => result + part + (index < values.length ? String(values[index]) : ""),
  "",
);
const getEntityStateWithFallback = (hass, entityId) => hass?.states?.[entityId] || null;
const isNoSpoilerModeActive = (entityState) => String(entityState?.state || "").trim().toLowerCase() === "on";

const harnessFactory = new Function(
  "html",
  "getEntityStateWithFallback",
  "isNoSpoilerModeActive",
  `
  ${helperSource}

  class SpoilerCard {
    setConfig(config = {}) {
      this.config = { type: "custom:spoiler-card", ...config };
    }

    render() {
      return "<ha-card>body</ha-card>";
    }
  }

  installNoSpoilerOverlay(SpoilerCard);

  return { SpoilerCard, DEFAULT_NO_SPOILER_ENTITY };
  `,
);

const { SpoilerCard, DEFAULT_NO_SPOILER_ENTITY } = harnessFactory(
  html,
  getEntityStateWithFallback,
  isNoSpoilerModeActive,
);

const defaultCard = new SpoilerCard();
defaultCard.setConfig({});
const defaultEntity = defaultCard.config.no_spoiler_entity;

defaultCard.hass = { states: { [DEFAULT_NO_SPOILER_ENTITY]: { state: "on" } } };
const onRender = defaultCard.render();

defaultCard.hass = { states: { [DEFAULT_NO_SPOILER_ENTITY]: { state: "off" } } };
const offRender = defaultCard.render();

const customCard = new SpoilerCard();
customCard.setConfig({ no_spoiler_entity: "switch.custom_no_spoiler" });
customCard.hass = {
  states: {
    [DEFAULT_NO_SPOILER_ENTITY]: { state: "on" },
    "switch.custom_no_spoiler": { state: "off" },
  },
};
const customOffRender = customCard.render();

process.stdout.write(JSON.stringify({
  defaultEntity,
  onHasOverlay: onRender.includes("f1-no-spoiler-overlay")
    && onRender.includes("No Spoiler Mode is active"),
  offHasOverlay: offRender.includes("f1-no-spoiler-overlay"),
  customEntity: customCard.config.no_spoiler_entity,
  customOffHasOverlay: customOffRender.includes("f1-no-spoiler-overlay"),
}));
"""


def _read_card(path: Path) -> str:
    if not path.exists():
        pytest.skip(f"card JS not found at {path}")
    return path.read_text(encoding="utf-8")


def _overlay_install_block(source: str) -> str:
    start = source.index("const F1_NO_SPOILER_CARD_CLASSES = [")
    end = source.index("F1_NO_SPOILER_CARD_CLASSES.forEach", start)
    return source[start:end]


def _run_overlay_probe(path: Path) -> dict:
    if not path.exists():
        pytest.skip(f"card JS not found at {path}")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for card overlay regression tests")

    env = os.environ.copy()
    env["NO_SPOILER_CARD_PATH"] = str(path)
    completed = subprocess.run(
        [node, "-e", NODE_OVERLAY_PROBE],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(completed.stdout)


@pytest.mark.parametrize("card_path", (BUNDLED_CARD_PATH, RUNTIME_CARD_PATH))
def test_no_spoiler_overlay_renders_only_when_switch_is_on(card_path: Path) -> None:
    result = _run_overlay_probe(card_path)

    assert result == {
        "defaultEntity": "switch.f1_no_spoiler_mode",
        "onHasOverlay": True,
        "offHasOverlay": False,
        "customEntity": "switch.custom_no_spoiler",
        "customOffHasOverlay": False,
    }


@pytest.mark.parametrize("card_path", (BUNDLED_CARD_PATH, RUNTIME_CARD_PATH))
def test_no_spoiler_overlay_installs_only_on_spoiler_cards(card_path: Path) -> None:
    source = _read_card(card_path)
    block = _overlay_install_block(source)

    assert "const DEFAULT_NO_SPOILER_ENTITY = 'switch.f1_no_spoiler_mode';" in source
    assert "const installNoSpoilerOverlay = (CardClass) =>" in source
    assert "No Spoiler Mode is active" in source

    for class_name in SPOILER_CARD_CLASSES:
        assert class_name in block

    for class_name in NON_SPOILER_CARD_CLASSES:
        assert class_name not in block

    if "class F1TrackMapCard extends" in source:
        assert "F1TrackMapCard" in block
