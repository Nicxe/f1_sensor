"""Regression tests for the qualifying timing card Q-part handling."""

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

function extractMethod(signature) {
  const start = source.indexOf(signature);
  if (start === -1) {
    throw new Error(`Method signature not found: ${signature}`);
  }
  const braceStart = source.indexOf("{", start);
  const end = findMatchingBrace(source, braceStart);
  return source.slice(start, end + 1);
}

const methodSources = [
  extractMethod(
    "_buildRows(positionDrivers, tyresDrivers, driverList, currentQPart)",
  ),
  extractMethod("_resolveDisplayQualifyingPart(sessionState, ...parts)"),
  extractMethod("_normalizeQualifyingPart(value)"),
  extractMethod("_inferQualifyingPartFromDrivers(drivers)"),
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
        show_team_logo: false,
        team_logo_style: "color",
      };
    }

    _normalizeColor(value) {
      return value ?? null;
    }

    _resolveLastLapTime(pos) {
      return pos.last_lap ?? null;
    }

    _statusInfo() {
      return {
        label: null,
        key: null,
      };
    }

    _parsePosition(value) {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : null;
    }

    ${methodSources.join("\n\n")}
  }

  return Harness;
`,
)();

const harness = new Harness();
const sessionPart = harness._resolveDisplayQualifyingPart(
  { state: payload.sessionState },
  payload.currentQPart,
  payload.positionDrivers,
);
const rows = harness._buildRows(
  payload.positionDrivers,
  [],
  [],
  payload.currentQPart,
);

process.stdout.write(
  JSON.stringify({
    callUsesSessionPart: source.includes(
      "const rows = this._buildRows(positionDrivers, tyresDrivers, driverList, sessionPart);",
    ),
    sessionPart,
    rows,
  }),
);
"""


def _run_card_probe(
    *,
    current_q_part: str | int | None,
    position_drivers: list[dict],
    session_state: str = "Qualifying",
) -> dict:
    """Execute the qualifying-card row logic from the actual JS source."""
    if not CARD_PATH.exists():
        pytest.skip(f"card JS not found at {CARD_PATH}")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for qualifying card regression tests")

    env = os.environ.copy()
    env["CARD_PROBE_PATH"] = str(CARD_PATH)
    env["CARD_PROBE_PAYLOAD"] = json.dumps(
        {
            "currentQPart": current_q_part,
            "positionDrivers": position_drivers,
            "sessionState": session_state,
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


def test_qualifying_card_reuses_inferred_qpart_for_rows() -> None:
    """Missing current_qualifying_part must still render Q2 row data."""
    result = _run_card_probe(
        current_q_part=None,
        position_drivers=[
            {
                "racing_number": "81",
                "tla": "PIA",
                "team": "McLaren",
                "q1_time": "1:19.664",
                "q1_position": 11,
                "q2_time": "1:19.525",
                "q2_position": 3,
                "q3_time": None,
                "q3_position": None,
                "current_position": "11",
            }
        ],
    )

    assert result["callUsesSessionPart"] is True
    assert result["sessionPart"] == 2
    assert result["rows"][0]["position"] == 3
    assert result["rows"][0]["current_segment_best_lap"] == "1:19.525"


def test_qualifying_card_normalizes_string_qpart_for_rows() -> None:
    """String-valued current_qualifying_part must still drive Q3 row data."""
    result = _run_card_probe(
        current_q_part="3",
        position_drivers=[
            {
                "racing_number": "63",
                "tla": "RUS",
                "team": "Mercedes",
                "q1_time": "1:19.507",
                "q1_position": 7,
                "q2_time": "1:18.934",
                "q2_position": 5,
                "q3_time": "1:18.518",
                "q3_position": 1,
                "current_position": "7",
            }
        ],
    )

    assert result["sessionPart"] == 3
    assert result["rows"][0]["position"] == 1
    assert result["rows"][0]["current_segment_best_lap"] == "1:18.518"


def test_qualifying_card_does_not_reuse_previous_segment_rank_in_q3() -> None:
    """Untimed Q3 drivers must not inherit their Q2 position."""
    result = _run_card_probe(
        current_q_part=3,
        position_drivers=[
            {
                "racing_number": "16",
                "tla": "LEC",
                "team": "Ferrari",
                "q1_time": "1:31.100",
                "q1_position": 7,
                "q2_time": "1:30.800",
                "q2_position": 4,
                "q3_time": "1:30.400",
                "q3_position": 4,
                "current_position": "4",
            },
            {
                "racing_number": "81",
                "tla": "PIA",
                "team": "McLaren",
                "q1_time": "1:31.000",
                "q1_position": 3,
                "q2_time": "1:30.700",
                "q2_position": 4,
                "q3_time": None,
                "q3_position": None,
                "current_position": "5",
            },
        ],
    )

    assert result["sessionPart"] == 3
    assert [row["tla"] for row in result["rows"]] == ["LEC", "PIA"]
    assert result["rows"][0]["position"] == 4
    assert result["rows"][1]["position"] == 5
    assert result["rows"][1]["current_segment_best_lap"] is None
