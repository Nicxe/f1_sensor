"""Regression tests for F1 next race card layout helpers."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
CARD_PATH = ROOT / "www" / "f1-sensor-live-data-card.js"

NODE_PROBE_SCRIPT = r"""
const fs = require("node:fs");

const payload = JSON.parse(process.env.NEXT_RACE_LAYOUT_PAYLOAD || "{}");
const source = fs.readFileSync(process.env.NEXT_RACE_LAYOUT_PATH, "utf8");

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

function extractClass(signature) {
  const start = source.indexOf(signature);
  if (start === -1) {
    throw new Error(`Class signature not found: ${signature}`);
  }
  const braceStart = source.indexOf("{", start);
  const end = findMatchingBrace(source, braceStart);
  return source.slice(start, end + 1);
}

const classSource = extractClass("class F1NextRaceCard extends LitElement {");

function extractMethod(signature) {
  const start = classSource.indexOf(signature);
  if (start === -1) {
    throw new Error(`Method signature not found: ${signature}`);
  }
  const braceStart = classSource.indexOf("{", start);
  const end = findMatchingBrace(classSource, braceStart);
  return classSource.slice(start, end + 1);
}

const methodSources = [
  extractMethod("_responsiveLayoutBreakpoints() {"),
  extractMethod("_resolveVisibleSections() {"),
  extractMethod("_normalizeOffset(offset) {"),
  extractMethod("_parseDateWithOffset(value, offset = null) {"),
  extractMethod("_getTimeZone() {"),
  extractMethod("_formatDate(date, timeZone = this._getTimeZone()) {"),
  extractMethod("_formatTime(date, timeZone = this._getTimeZone()) {"),
  extractMethod("_formatDateTimeParts(date, timeZone = this._getTimeZone()) {"),
  extractMethod("_mapSessionLabel(value) {"),
  extractMethod("_buildSessionItems(nextRace) {"),
  extractMethod("_resolveTimelineState(items, currentSession, sessionStatus) {"),
  extractMethod("_formatCountdownCompact(countdown) {"),
  extractMethod("_getRoundSummary(nextRace) {"),
  extractMethod("_getSummaryCells(nextRace, currentSession, sessionStatus, countdown) {"),
  extractMethod("_resolveSecondaryPanelState(sections, weather) {"),
  extractMethod("_historyHasContent(nextRace) {"),
  extractMethod("_getHistoryRibbonItems(nextRace) {"),
  extractMethod("_resolveWeekendSummary(items, timeline) {"),
  extractMethod("_renderWeekendPanel(nextRace, currentSession, sessionStatus, layoutMode = 'wide') {"),
];

const Harness = new Function(
  `
  function serializeValue(value) {
    if (Array.isArray(value)) {
      return value.map((item) => serializeValue(item)).join("");
    }
    if (value === null || value === undefined || value === false) {
      return "";
    }
    if (typeof value === "object" && Object.prototype.hasOwnProperty.call(value, "__html")) {
      return value.__html;
    }
    return String(value);
  }

  function html(strings, ...values) {
    let output = "";
    for (let index = 0; index < strings.length; index += 1) {
      output += strings[index];
      if (index < values.length) {
        output += serializeValue(values[index]);
      }
    }
    return { __html: output };
  }

  class Harness {
    constructor(payload) {
      this.config = payload.config || {};
      this.hass = payload.hass || {
        locale: { time_format: "24", language: "en-GB", time_zone: "UTC" },
        config: { time_zone: "UTC" },
      };
    }

    ${methodSources.join("\n\n")}
  }

  return Harness;
`,
)();

const harness = new Harness(payload);

let result;
if (payload.action === "breakpoints") {
  result = harness._responsiveLayoutBreakpoints();
} else if (payload.action === "sections") {
  result = harness._resolveVisibleSections();
} else if (payload.action === "summary") {
  const items = harness._buildSessionItems(payload.nextRace || {});
  const timeline = harness._resolveTimelineState(
    items,
    payload.currentSession || null,
    payload.sessionStatus || null,
  );
  result = harness._resolveWeekendSummary(items, timeline);
} else if (payload.action === "round") {
  result = harness._getRoundSummary(payload.nextRace || {});
} else if (payload.action === "summary_cells") {
  result = harness._getSummaryCells(
    payload.nextRace || {},
    payload.currentSession || null,
    payload.sessionStatus || null,
    payload.countdown || null,
  );
} else if (payload.action === "secondary") {
  result = harness._resolveSecondaryPanelState(
    payload.sections || {},
    payload.weather || null,
  );
} else if (payload.action === "history_ribbon") {
  result = harness._getHistoryRibbonItems(payload.nextRace || {});
} else if (payload.action === "weekend_panel") {
  result = harness._renderWeekendPanel(
    payload.nextRace || {},
    payload.currentSession || null,
    payload.sessionStatus || null,
    payload.layoutMode || "wide",
  );
  result = result && typeof result === "object" && "__html" in result ? result.__html : result;
} else {
  throw new Error(`Unknown action: ${payload.action}`);
}

process.stdout.write(JSON.stringify(result));
"""


def _run_probe(payload: dict) -> dict:
    if not CARD_PATH.exists():
        pytest.skip(f"card JS not found at {CARD_PATH}")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for next race layout regression tests")

    proc = subprocess.run(
        [node, "-e", NODE_PROBE_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
        env={
            "NEXT_RACE_LAYOUT_PAYLOAD": json.dumps(payload),
            "NEXT_RACE_LAYOUT_PATH": str(CARD_PATH),
        },
    )
    return json.loads(proc.stdout)


def test_next_race_card_uses_compact_layout_breakpoints() -> None:
    result = _run_probe({"action": "breakpoints"})

    assert result == {"narrow": 560, "medium": 920}


def test_next_race_card_visibility_defaults_enable_all_sections() -> None:
    result = _run_probe({"action": "sections", "config": {}})

    assert result == {
        "header": True,
        "countdown": True,
        "overview": True,
        "schedule": True,
        "map": True,
        "weather": True,
        "history": True,
    }


def test_next_race_card_visibility_respects_disabled_sections() -> None:
    result = _run_probe(
        {
            "action": "sections",
            "config": {
                "show_header": False,
                "show_overview": False,
                "show_schedule": False,
                "show_history": False,
            },
        }
    )

    assert result == {
        "header": False,
        "countdown": True,
        "overview": False,
        "schedule": False,
        "map": True,
        "weather": True,
        "history": False,
    }


def test_next_race_card_weekend_summary_prefers_live_session() -> None:
    result = _run_probe(
        {
            "action": "summary",
            "nextRace": {
                "qualifying_start_utc": "2026-03-20T14:00:00Z",
                "race_start_utc": "2026-03-22T14:00:00Z",
            },
            "currentSession": {"state": "Qualifying"},
            "sessionStatus": {"state": "live"},
        }
    )

    assert result["label"] == "Live session"
    assert result["value"] == "Qualifying"
    assert result["chip"] == "Live"


def test_next_race_card_weekend_summary_uses_next_upcoming_session() -> None:
    result = _run_probe(
        {
            "action": "summary",
            "nextRace": {
                "first_practice_start_utc": "2099-03-20T10:00:00Z",
                "qualifying_start_utc": "2099-03-21T14:00:00Z",
                "race_start_utc": "2099-03-22T14:00:00Z",
            },
            "currentSession": None,
            "sessionStatus": {"state": "pre"},
        }
    )

    assert result["label"] == "Next session"
    assert result["value"] == "FP1"
    assert result["chip"] == "Next"


def test_next_race_card_round_summary_prioritizes_round_and_season() -> None:
    result = _run_probe(
        {
            "action": "round",
            "nextRace": {"round": 7, "season": 2026},
        }
    )

    assert result == {"value": "Round 7", "detail": "Season 2026"}


def test_next_race_card_summary_cells_use_compact_four_cell_matrix() -> None:
    result = _run_probe(
        {
            "action": "summary_cells",
            "config": {"show_overview": True, "show_countdown": True},
            "nextRace": {
                "round": 7,
                "season": 2026,
                "qualifying_start_utc": "2099-03-21T14:00:00Z",
                "race_start_utc": "2099-03-22T14:00:00Z",
            },
            "sessionStatus": {"state": "pre"},
            "countdown": {
                "totalSeconds": 90061,
                "days": 1,
                "hours": 1,
                "minutes": 1,
                "seconds": 1,
                "start": "2099-03-22T14:00:00.000Z",
            },
        }
    )

    assert [item["key"] for item in result] == [
        "weekend",
        "race_start",
        "countdown",
        "round",
    ]
    assert result[0]["label"] == "Next session"
    assert result[0]["chip"] is None
    assert result[1]["detail"] is None


def test_next_race_card_secondary_panel_hides_when_both_parts_are_absent() -> None:
    result = _run_probe(
        {
            "action": "secondary",
            "sections": {"map": False, "weather": True},
            "weather": {"show": False},
        }
    )

    assert result == {"showMap": False, "showWeather": False, "showPanel": False}


def test_next_race_card_secondary_panel_keeps_map_when_weather_is_missing() -> None:
    result = _run_probe(
        {
            "action": "secondary",
            "sections": {"map": True, "weather": True},
            "weather": {"show": False},
        }
    )

    assert result == {"showMap": True, "showWeather": False, "showPanel": True}


def test_next_race_card_history_ribbon_omits_empty_state() -> None:
    result = _run_probe(
        {
            "action": "history_ribbon",
            "nextRace": {},
        }
    )

    assert result == []


def test_next_race_card_schedule_places_next_chip_in_right_status_column() -> None:
    result = _run_probe(
        {
            "action": "weekend_panel",
            "config": {"show_schedule": True, "show_track_time": False},
            "layoutMode": "wide",
            "nextRace": {
                "circuit_timezone": "Asia/Tokyo",
                "first_practice_start_utc": "2099-03-20T10:00:00Z",
                "qualifying_start_utc": "2099-03-21T14:00:00Z",
                "race_start_utc": "2099-03-22T14:00:00Z",
            },
            "sessionStatus": {"state": "pre"},
        }
    )

    assert "nr-schedule-cell status" in result
    assert result.index('nr-schedule-session-name">FP1</span>') < result.index(
        'nr-schedule-cell time">'
    )
    assert result.index('nr-schedule-cell date compact">') < result.index(
        ">Next</span>"
    )


def test_next_race_card_schedule_hides_track_column_when_disabled() -> None:
    result = _run_probe(
        {
            "action": "weekend_panel",
            "config": {"show_schedule": True, "show_track_time": False},
            "layoutMode": "wide",
            "nextRace": {
                "circuit_timezone": "Asia/Tokyo",
                "first_practice_start_utc": "2099-03-20T10:00:00Z",
                "qualifying_start_utc": "2099-03-21T14:00:00Z",
                "race_start_utc": "2099-03-22T14:00:00Z",
            },
            "sessionStatus": {"state": "pre"},
        }
    )

    assert "nr-schedule-head track-hidden" in result
    assert ">Track</span>" not in result
