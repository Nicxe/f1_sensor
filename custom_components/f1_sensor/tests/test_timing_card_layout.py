"""Regression tests for timing-card layout and replay-only pit UX."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
CARD_PATH = ROOT / "www" / "f1-sensor-live-data-card.js"

NODE_PROBE_SCRIPT = r"""
const fs = require("node:fs");

const payload = JSON.parse(process.env.TIMING_LAYOUT_PAYLOAD || "{}");
const source = fs.readFileSync(process.env.TIMING_LAYOUT_PATH, "utf8");

function findMatchingBrace(text, openIndex) {
  let depth = 0;
  for (let idx = openIndex; idx < text.length; idx += 1) {
    const ch = text[idx];
    if (ch === "{") {
      depth += 1;
    } else if (ch === "}") {
      depth -= 1;
      if (depth === 0) {
        return idx;
      }
    }
  }
  throw new Error(`Unmatched brace starting at ${openIndex}`);
}

function extractConst(signature) {
  const start = source.indexOf(signature);
  if (start === -1) {
    throw new Error(`Const signature not found: ${signature}`);
  }
  const braceStart = source.indexOf("{", start);
  const end = findMatchingBrace(source, braceStart);
  const semicolon = source.indexOf(";", end);
  return source.slice(start, semicolon + 1);
}

function extractClass(signature) {
  const start = source.indexOf(signature);
  if (start === -1) {
    throw new Error(`Class signature not found: ${signature}`);
  }
  const braceStart = source.indexOf("{", start);
  const end = findMatchingBrace(source, braceStart);
  return source.slice(start, end + 1);
}

function extractMethod(text, signature) {
  const start = text.indexOf(signature);
  if (start === -1) {
    throw new Error(`Method signature not found: ${signature}`);
  }
  const braceStart = text.indexOf("{", start);
  const end = findMatchingBrace(text, braceStart);
  return text.slice(start, end + 1);
}

function extractInstallOptions(className) {
  const signature = `installSectionsAutoHeight(${className}, {`;
  const start = source.indexOf(signature);
  if (start === -1) {
    throw new Error(`installSectionsAutoHeight call not found for ${className}`);
  }
  const braceStart = source.indexOf("{", start);
  const end = findMatchingBrace(source, braceStart);
  const objectLiteral = source.slice(braceStart, end + 1);
  return new Function(`return (${objectLiteral});`)();
}

function buildHost(data = {}) {
  const hostWidth = data.hostWidth ?? 0;
  const cardWidth = data.cardWidth ?? 0;
  const contentWidth = data.contentWidth ?? 0;
  const breakpoints = data.breakpoints || null;

  return {
    getBoundingClientRect() {
      return { width: hostWidth };
    },
    renderRoot: {
      querySelector() {
        return {
          clientWidth: cardWidth,
          getBoundingClientRect() {
            return { width: cardWidth };
          },
          firstElementChild: {
            getBoundingClientRect() {
              return { width: contentWidth };
            },
          },
        };
      },
    },
    _responsiveLayoutBreakpoints: breakpoints ? () => breakpoints : undefined,
  };
}

const helperSources = [
  extractConst("const measureRenderedCardWidth = (host) =>"),
  extractConst("const DEFAULT_RESPONSIVE_BREAKPOINTS ="),
  extractConst("const getResponsiveBreakpoints = (host) =>"),
  extractConst("const resolveResponsiveLayoutMode = (width, breakpoints) =>"),
  extractConst("const getResponsiveLayoutMode = (host) =>"),
];

const liveSessionClass = extractClass("class F1LiveSessionCard extends LitElement {");
const qualifyingClass = extractClass("class F1QualifyingTimingCard extends LitElement {");
const practiceClass = extractClass("class F1PracticeTimingCard extends LitElement {");
const raceLapClass = extractClass("class F1RaceLapCard extends LitElement {");
const driversClass = extractClass("class F1ChampionshipPredictionDriversCard extends LitElement {");
const driversEditorClass = extractClass("class F1ChampionshipPredictionDriversCardEditor extends LitElement {");
const teamsClass = extractClass("class F1ChampionshipPredictionTeamsCard extends LitElement {");
const teamsEditorClass = extractClass("class F1ChampionshipPredictionTeamsCardEditor extends LitElement {");

const Harnesses = new Function(
  `
  ${helperSources.join("\n\n")}

  class LiveSessionHarness {
    ${extractMethod(liveSessionClass, "getGridOptions() {")}
  }

  class QualifyingHarness {
    ${extractMethod(qualifyingClass, "getGridOptions() {")}
  }

  class PracticeHarness {
    ${extractMethod(practiceClass, "getGridOptions() {")}
  }

  class RaceLapHarness {
    constructor(config = {}) {
      this.config = {
        show_position: true,
        show_team_logo: true,
        show_full_name: false,
        show_tyre: true,
        show_tyre_age: true,
        show_pit_count: true,
        show_last_lap: true,
        show_fastest_lap: true,
        ...config,
      };
    }

    ${extractMethod(raceLapClass, "getGridOptions() {")}
    ${extractMethod(raceLapClass, "_columns(layoutMode = 'wide', suppressPit = false) {")}
  }

  return {
    measureRenderedCardWidth,
    getResponsiveLayoutMode,
    LiveSessionHarness,
    QualifyingHarness,
    PracticeHarness,
    RaceLapHarness,
  };
`,
)();

let result;
if (payload.action === "measure_width") {
  result = Harnesses.measureRenderedCardWidth(buildHost(payload.host || {}));
} else if (payload.action === "layout_mode") {
  result = Harnesses.getResponsiveLayoutMode(buildHost(payload.host || {}));
} else if (payload.action === "grid_options") {
  const className = payload.className;
  const mapping = {
    F1LiveSessionCard: Harnesses.LiveSessionHarness,
    F1QualifyingTimingCard: Harnesses.QualifyingHarness,
    F1PracticeTimingCard: Harnesses.PracticeHarness,
    F1RaceLapCard: Harnesses.RaceLapHarness,
  };
  const Klass = mapping[className];
  if (!Klass) {
    throw new Error(`Unknown className: ${className}`);
  }
  result = new Klass(payload.config || {}).getGridOptions();
} else if (payload.action === "install_options") {
  result = extractInstallOptions(payload.className);
} else if (payload.action === "race_lap_columns") {
  result = new Harnesses.RaceLapHarness(payload.config || {})._columns(
    payload.layoutMode || "wide",
    Boolean(payload.suppressPit),
  );
} else if (payload.action === "source_checks") {
  result = {
    driversCardUsesShortTitle: driversClass.includes("Driver Championship"),
    driversCardAvoidsLongTitle: !driversClass.includes("Championship Standings Drivers"),
    driversEditorUsesShortTitle: driversEditorClass.includes("Driver Championship"),
    driversEditorAvoidsLongTitle: !driversEditorClass.includes("Championship Standings Drivers"),
    teamsCardUsesShortTitle: teamsClass.includes("Constructor Championship"),
    teamsCardAvoidsLongTitle: !teamsClass.includes("Championship Standings Teams"),
    teamsEditorUsesShortTitle: teamsEditorClass.includes("Constructor Championship"),
    teamsEditorAvoidsLongTitle: !teamsEditorClass.includes("Championship Standings Teams"),
    raceLapReplayNotePresent: raceLapClass.includes("Pit stop data is available in Replay Mode only"),
    raceLapPitSuppressionCallPresent: raceLapClass.includes(
      "Boolean(this.config.pitstops_entity) && !pitDataAvailable",
    ),
    qualifyingRowHeightPresent: qualifyingClass.includes(".qt-row:not(.header)")
      && qualifyingClass.includes("height: var(--f1-live-table-row-height, 34px);"),
    practiceRowHeightPresent: practiceClass.includes(".pt-row:not(.header)")
      && practiceClass.includes("height: var(--f1-live-table-row-height, 34px);"),
    raceLapRowHeightPresent: raceLapClass.includes(".rl-row:not(.header)")
      && raceLapClass.includes("height: var(--f1-live-table-row-height, 34px);"),
  };
} else {
  throw new Error(`Unknown action: ${payload.action}`);
}

process.stdout.write(JSON.stringify(result));
"""


def _run_probe(payload: dict) -> dict | list | str | int:
    """Execute a small Node probe against the actual card source."""
    if not CARD_PATH.exists():
        pytest.skip(f"card JS not found at {CARD_PATH}")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for timing card layout regression tests")

    env = os.environ.copy()
    env["TIMING_LAYOUT_PATH"] = str(CARD_PATH)
    env["TIMING_LAYOUT_PAYLOAD"] = json.dumps(payload)

    completed = subprocess.run(
        [node, "-e", NODE_PROBE_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(completed.stdout)


def test_measure_rendered_card_width_prefers_container_over_overflow_content() -> None:
    """Overflowing content must not force the layout engine into wide mode."""
    result = _run_probe(
        {
            "action": "measure_width",
            "host": {
                "hostWidth": 320,
                "cardWidth": 320,
                "contentWidth": 760,
            },
        }
    )

    assert result == 320


def test_overflowing_content_still_uses_narrow_layout_breakpoints() -> None:
    """Layout mode should follow actual card width, not scroll width."""
    result = _run_probe(
        {
            "action": "layout_mode",
            "host": {
                "hostWidth": 320,
                "cardWidth": 320,
                "contentWidth": 760,
                "breakpoints": {"narrow": 560, "medium": 920},
            },
        }
    )

    assert result == "narrow"


@pytest.mark.parametrize(
    "class_name",
    [
        "F1LiveSessionCard",
        "F1QualifyingTimingCard",
        "F1PracticeTimingCard",
        "F1RaceLapCard",
    ],
)
def test_timing_cards_use_four_min_columns_for_sections_layout(class_name: str) -> None:
    """Target cards should stay usable in narrower Home Assistant sections."""
    grid_options = _run_probe({"action": "grid_options", "className": class_name})
    install_options = _run_probe({"action": "install_options", "className": class_name})

    assert grid_options["min_columns"] == 4
    assert install_options["min_columns"] == 4


def test_race_lap_columns_hide_pit_count_when_pit_sensor_is_unavailable() -> None:
    """Pit count should be suppressed in live no-auth when pit stop sensor is unavailable."""
    visible_columns = _run_probe(
        {
            "action": "race_lap_columns",
            "layoutMode": "wide",
            "suppressPit": False,
        }
    )
    suppressed_columns = _run_probe(
        {
            "action": "race_lap_columns",
            "layoutMode": "wide",
            "suppressPit": True,
        }
    )

    assert any(column["key"] == "pit_count" for column in visible_columns)
    assert all(column["key"] != "pit_count" for column in suppressed_columns)


def test_timing_card_source_keeps_replay_only_pit_behavior_and_short_titles() -> None:
    """Lock the user-facing replay-only pit UX and shorter default headers."""
    result = _run_probe({"action": "source_checks"})

    assert result == {
        "driversCardUsesShortTitle": True,
        "driversCardAvoidsLongTitle": True,
        "driversEditorUsesShortTitle": True,
        "driversEditorAvoidsLongTitle": True,
        "teamsCardUsesShortTitle": True,
        "teamsCardAvoidsLongTitle": True,
        "teamsEditorUsesShortTitle": True,
        "teamsEditorAvoidsLongTitle": True,
        "raceLapReplayNotePresent": True,
        "raceLapPitSuppressionCallPresent": True,
        "qualifyingRowHeightPresent": True,
        "practiceRowHeightPresent": True,
        "raceLapRowHeightPresent": True,
    }
