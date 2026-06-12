"""Regression tests for F1 race control card message filters."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
CARD_PATH = (
    ROOT
    / "custom_components"
    / "f1_sensor"
    / "www"
    / "f1-sensor-live-data-card"
    / "f1-sensor-live-data-card.js"
)
NODE_PROBE_SCRIPT = r"""
const fs = require("node:fs");

const payload = JSON.parse(process.env.RACE_CONTROL_FILTER_PAYLOAD || "{}");
const source = fs.readFileSync(process.env.RACE_CONTROL_CARD_PATH, "utf8");

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

function extractMethod(classSource, signature) {
  const start = classSource.indexOf(signature);
  if (start === -1) {
    throw new Error(`Method signature not found: ${signature}`);
  }
  const braceStart = classSource.indexOf("{", start);
  const end = findMatchingBrace(classSource, braceStart);
  return classSource.slice(start, end + 1);
}

const classSource = extractClass("class F1RaceControlCard extends LitElement {");
const methodSources = [
  extractMethod(classSource, "_formatMessage(message) {"),
  extractMethod(classSource, "_shouldHideMessage(item) {"),
  extractMethod(classSource, "_isBlueFlagMessage(item) {"),
  extractMethod(classSource, "_isTrackLimitsMessage(item) {"),
  extractMethod(classSource, "_stripEmbeddedTime(message) {"),
];

const Harness = new Function(
  `
  return class Harness {
    constructor(config) {
      this.config = config;
    }

    ${methodSources.join("\n\n")}
  };
  `,
)();

const harness = new Harness(payload.config || {});
const result = payload.items.map((item) => harness._shouldHideMessage(item));
process.stdout.write(JSON.stringify(result));
"""


def _run_probe(config: dict, items: list[dict]) -> list[bool]:
    if not CARD_PATH.exists():
        pytest.skip(f"card JS not found at {CARD_PATH}")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for race control card filter tests")

    completed = subprocess.run(
        [node, "-e", NODE_PROBE_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
        env={
            "RACE_CONTROL_CARD_PATH": str(CARD_PATH),
            "RACE_CONTROL_FILTER_PAYLOAD": json.dumps(
                {"config": config, "items": items}
            ),
        },
    )
    return json.loads(completed.stdout)


def test_track_limits_messages_can_be_hidden() -> None:
    result = _run_probe(
        {"hide_track_limits": True},
        [
            {
                "message": (
                    "CAR 44 (HAM) TIME 1:30.229 DELETED - TRACK LIMITS AT TURN 1 LAP 5"
                )
            },
            {
                "message": ("BLACK AND WHITE FLAG FOR CAR 44 (HAM) - TRACK LIMITS"),
                "flag": "BLACK AND WHITE",
            },
            {"message": "DRS ENABLED"},
        ],
    )

    assert result == [True, True, False]


def test_race_control_filters_are_independent() -> None:
    items = [
        {"message": "WAVED BLUE FLAG FOR CAR 43", "flag": "BLUE"},
        {"message": "CAR 10 TIME DELETED - TRACK LIMITS AT TURN 4 LAP 12"},
    ]

    assert _run_probe({"hide_blue_flags": True}, items) == [True, False]
    assert _run_probe({"hide_track_limits": True}, items) == [False, True]
    assert _run_probe({}, items) == [False, False]


def test_track_limits_filter_is_available_in_card_editor() -> None:
    source = CARD_PATH.read_text()

    assert "hide_track_limits: false" in source
    assert "'hide_track_limits'," in source
    assert "'Hide track limits messages'," in source
