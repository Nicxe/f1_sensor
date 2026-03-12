"""Regression tests for the practice timing card session gating and lap logic."""

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

const payload = JSON.parse(process.env.CARD_PROBE_PAYLOAD || "{}");
const source = fs.readFileSync(process.env.CARD_PROBE_PATH, "utf8");

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

function extractMethod(text, signature) {
  const start = text.indexOf(signature);
  if (start === -1) {
    throw new Error(`Method signature not found: ${signature}`);
  }
  const braceStart = text.indexOf("{", start);
  const end = findMatchingBrace(text, braceStart);
  return text.slice(start, end + 1);
}

const classStart = source.indexOf("class F1PracticeTimingCard extends LitElement");
const classEnd = source.indexOf("class F1PracticeTimingCardEditor extends LitElement");
if (classStart === -1 || classEnd === -1 || classEnd <= classStart) {
  throw new Error("Unable to locate practice timing card class boundaries");
}
const classSource = source.slice(classStart, classEnd);

const methodSources = [
  extractMethod(classSource, "_buildRows(positionDrivers, tyresDrivers, driverList) {"),
  extractMethod(classSource, "_buildTitle(sessionState) {"),
  extractMethod(classSource, "_practiceSessionNumber(sessionState) {"),
  extractMethod(classSource, "_isPracticeSession(sessionState, sessionStatusState) {"),
  extractMethod(classSource, "_isPracticeLikeLabel(label) {"),
  extractMethod(classSource, "_asDriversList(value) {"),
  extractMethod(classSource, "_buildLapSnapshot(positionInfo) {"),
  extractMethod(classSource, "_normalizeLapEntries(laps) {"),
  extractMethod(classSource, "_resolveLastLapEntry(entries, completedLaps) {"),
  extractMethod(classSource, "_resolveBestLapEntry(entries) {"),
  extractMethod(classSource, "_parseLapTimeSeconds(value) {"),
  extractMethod(classSource, "_isLapTimeMatch(left, right) {"),
  extractMethod(classSource, "_statusInfo(info) {"),
  extractMethod(classSource, "_parsePosition(value) {"),
  extractMethod(classSource, "_parsePositiveInt(value) {"),
  extractMethod(classSource, "_compareRacingNumber(a, b) {"),
  extractMethod(classSource, "_formatLaps(value) {"),
  extractMethod(classSource, "_normalizeCompoundKey(value) {"),
  extractMethod(classSource, "_compoundDisplayName(value) {"),
  extractMethod(classSource, "_normalizeColor(value) {"),
];

const Harness = new Function(
  `
  const COMPOUND_FALLBACK = {
    SOFT: "#ff3b30",
    MEDIUM: "#ffd60a",
    HARD: "#e5e5e5",
    INTERMEDIATE: "#34c759",
    WET: "#0a84ff",
  };
  const getTeamLogoMeta = () => null;

  class Harness {
    constructor() {
      this.config = {
        title: "Free Practice",
        show_team_logo: false,
        team_logo_style: "color",
      };
    }

    ${methodSources.join("\n\n")}
  }

  return Harness;
`,
)();

const harness = new Harness();
const rows = harness._buildRows(
  payload.positionDrivers || [],
  payload.tyresDrivers || [],
  payload.driverList || [],
);

process.stdout.write(
  JSON.stringify({
    sessionVisible: harness._isPracticeSession(
      payload.sessionState || {},
      payload.sessionStatusState || {},
    ),
    title: harness._buildTitle(payload.sessionState || {}),
    rows,
    usesPracticeRowsCall: classSource.includes(
      "const rows = this._buildRows(positionDrivers, tyresDrivers, driverList);",
    ),
    readsPositionsFastestLap: classSource.includes(
      "positionsState?.attributes?.fastest_lap",
    ),
  }),
);
"""


def _run_card_probe(
    *,
    session_state: dict,
    session_status_state: dict,
    position_drivers: list[dict] | None = None,
    tyres_drivers: list[dict] | None = None,
    driver_list: list[dict] | None = None,
) -> dict:
    """Execute the practice-card logic from the actual JS source."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for practice card regression tests")

    env = os.environ.copy()
    env["CARD_PROBE_PATH"] = str(CARD_PATH)
    env["CARD_PROBE_PAYLOAD"] = json.dumps(
        {
            "sessionState": session_state,
            "sessionStatusState": session_status_state,
            "positionDrivers": position_drivers or [],
            "tyresDrivers": tyres_drivers or [],
            "driverList": driver_list or [],
        }
    )

    completed = subprocess.run(
        [node, "-e", NODE_PROBE_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    return json.loads(completed.stdout)


def test_practice_card_stays_visible_for_suspended_practice_last_label() -> None:
    """Suspended practice sessions should stay visible via last_label fallback."""
    result = _run_card_probe(
        session_state={"state": "", "attributes": {"last_label": "Practice 2"}},
        session_status_state={"state": "suspended"},
    )

    assert result["sessionVisible"] is True
    assert result["title"] == "Free Practice 2"


def test_practice_card_prefers_session_number_for_title() -> None:
    """Header should use the session number from current_session when available."""
    result = _run_card_probe(
        session_state={"state": "Practice 3", "attributes": {"number": 3}},
        session_status_state={"state": "live"},
    )

    assert result["title"] == "Free Practice 3"


def test_practice_card_derives_laps_and_status_from_driver_history() -> None:
    """Rows should sort by position and derive practice fastest laps locally."""
    result = _run_card_probe(
        session_state={"state": "Practice 1", "attributes": {"number": 1}},
        session_status_state={"state": "live"},
        position_drivers=[
            {
                "racing_number": "63",
                "tla": "RUS",
                "team": "Mercedes",
                "team_color": "#00D2BE",
                "current_position": "2",
                "completed_laps": 2,
                "in_pit": True,
                "laps": {
                    "1": "1:21.000",
                    "2": "1:20.750",
                },
            },
            {
                "racing_number": "55",
                "tla": "SAI",
                "team": "Ferrari",
                "team_color": "#DC0000",
                "current_position": "1",
                "completed_laps": 1,
                "laps": {
                    "1": "1:20.900",
                },
            },
            {
                "racing_number": "43",
                "tla": "COL",
                "team": "Williams",
                "team_color": "#005AFF",
                "current_position": "22",
                "completed_laps": 0,
                "laps": {},
            },
        ],
        tyres_drivers=[
            {
                "racing_number": "63",
                "compound": "MEDIUM",
                "compound_short": "M",
                "stint_laps": 13,
            },
            {
                "racing_number": "55",
                "compound": "SOFT",
                "compound_short": "S",
                "stint_laps": 5,
            },
            {
                "racing_number": "43",
                "compound": "HARD",
                "compound_short": "H",
                "stint_laps": 1,
            },
        ],
        driver_list=[
            {"racing_number": "63", "tla": "RUS", "team": "Mercedes"},
            {"racing_number": "55", "tla": "SAI", "team": "Ferrari"},
            {"racing_number": "43", "tla": "COL", "team": "Williams"},
        ],
    )

    rows = result["rows"]

    assert result["usesPracticeRowsCall"] is True
    assert result["readsPositionsFastestLap"] is False

    assert [row["tla"] for row in rows] == ["SAI", "RUS", "COL"]

    leader = rows[0]
    assert leader["position"] == 1
    assert leader["last_lap"] == "1:20.900"
    assert leader["best_lap"] == "1:20.900"
    assert leader["is_fastest"] is False

    russell = rows[1]
    assert russell["position"] == 2
    assert russell["status_label"] == "PIT"
    assert russell["status_key"] == "pit-in"
    assert russell["last_lap"] == "1:20.750"
    assert russell["best_lap"] == "1:20.750"
    assert russell["is_fastest"] is True
    assert russell["compound_short"] == "M"
    assert russell["tyre_age"] == 13

    colapinto = rows[2]
    assert colapinto["position"] == 22
    assert colapinto["last_lap"] is None
    assert colapinto["best_lap"] is None
    assert colapinto["is_fastest"] is False
