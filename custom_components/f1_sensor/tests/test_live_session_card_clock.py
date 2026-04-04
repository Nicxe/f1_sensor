"""Regression tests for the live session card clock display logic."""

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

const payload = JSON.parse(process.env.CARD_CLOCK_PAYLOAD || "{}");
const source = fs.readFileSync(process.env.CARD_CLOCK_PATH, "utf8");

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

function extractMethod(signature) {
  const start = source.indexOf(signature);
  if (start === -1) {
    throw new Error(`Method signature not found: ${signature}`);
  }
  const braceStart = source.indexOf("{", start);
  const end = findMatchingBrace(source, braceStart);
  return source.slice(start, end + 1);
}

const helperSources = [
  extractConst("const resolveEntityIdWithFallback = (hass, entityId) =>"),
  extractConst("const getEntityStateWithFallback = (hass, entityId) =>"),
];

const methodSource = extractMethod("_getSessionClockData() {");

const Harness = new Function(
  `
  const LEGACY_ENTITY_ID_FALLBACKS = {};

  ${helperSources.join("\n\n")}

  class Harness {
    constructor(payload) {
      this.hass = { states: payload.hassStates || {} };
      this.config = payload.config || {};
      this._clockSnapshot = null;
      this._clockSnapshotKey = null;
    }

    _configuredEntityId(key, legacyEntityId = null) {
      return this.config[key] || legacyEntityId || null;
    }

    _legacyEntityId() {
      return null;
    }

    ${methodSource}
  }

  return Harness;
`,
)();

const harness = new Harness(payload);
const results = {};

for (const step of payload.steps || []) {
  harness.hass.states = step.hassStates || {};
  Date.now = () => step.nowMs;
  results[step.name] = harness._getSessionClockData();
}

process.stdout.write(JSON.stringify(results));
"""


def _clock_entities(
    *,
    remaining: str,
    elapsed: str,
    clock_running: bool,
    clock_phase: str,
) -> dict[str, dict]:
    attrs = {
        "clock_running": clock_running,
        "clock_phase": clock_phase,
    }
    return {
        "sensor.f1_session_time_remaining": {
            "state": remaining,
            "attributes": attrs,
        },
        "sensor.f1_session_time_elapsed": {
            "state": elapsed,
            "attributes": attrs,
        },
    }


def _run_clock_probe(steps: list[dict]) -> dict:
    """Execute the live session clock logic directly from the JS source."""
    if not CARD_PATH.exists():
        pytest.skip(f"card JS not found at {CARD_PATH}")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for live session card clock tests")

    env = os.environ.copy()
    env["CARD_CLOCK_PATH"] = str(CARD_PATH)
    env["CARD_CLOCK_PAYLOAD"] = json.dumps(
        {
            "config": {
                "session_time_remaining_entity": "sensor.f1_session_time_remaining",
                "session_time_elapsed_entity": "sensor.f1_session_time_elapsed",
            },
            "steps": steps,
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


def test_live_session_clock_waits_for_full_second_before_advancing() -> None:
    """The local display must not round up before a whole second has passed."""
    result = _run_clock_probe(
        [
            {
                "name": "initial",
                "nowMs": 0,
                "hassStates": _clock_entities(
                    remaining="1:00:00",
                    elapsed="0:00:00",
                    clock_running=True,
                    clock_phase="running",
                ),
            },
            {
                "name": "before_full_second",
                "nowMs": 600,
                "hassStates": _clock_entities(
                    remaining="1:00:00",
                    elapsed="0:00:00",
                    clock_running=True,
                    clock_phase="running",
                ),
            },
            {
                "name": "after_full_second",
                "nowMs": 1100,
                "hassStates": _clock_entities(
                    remaining="1:00:00",
                    elapsed="0:00:00",
                    clock_running=True,
                    clock_phase="running",
                ),
            },
        ]
    )

    assert result["initial"] == {"remaining": "1:00:00", "elapsed": "0:00:00"}
    assert result["before_full_second"] == result["initial"]
    assert result["after_full_second"] == {
        "remaining": "0:59:59",
        "elapsed": "0:00:01",
    }


def test_live_session_clock_stays_frozen_while_paused() -> None:
    """Paused clocks should keep the raw HA value without local ticking."""
    result = _run_clock_probe(
        [
            {
                "name": "running",
                "nowMs": 0,
                "hassStates": _clock_entities(
                    remaining="1:00:00",
                    elapsed="0:00:00",
                    clock_running=True,
                    clock_phase="running",
                ),
            },
            {
                "name": "paused",
                "nowMs": 600,
                "hassStates": _clock_entities(
                    remaining="1:00:00",
                    elapsed="0:00:00",
                    clock_running=False,
                    clock_phase="paused",
                ),
            },
            {
                "name": "frozen",
                "nowMs": 30_600,
                "hassStates": _clock_entities(
                    remaining="1:00:00",
                    elapsed="0:00:00",
                    clock_running=False,
                    clock_phase="paused",
                ),
            },
        ]
    )

    assert result["paused"] == {"remaining": "1:00:00", "elapsed": "0:00:00"}
    assert result["frozen"] == result["paused"]
