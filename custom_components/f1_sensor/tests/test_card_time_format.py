"""Regression tests for Home Assistant locale-aware card time formatting."""

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

const payload = JSON.parse(process.env.CARD_TIME_FORMAT_PAYLOAD || "{}");
const source = fs.readFileSync(process.env.CARD_TIME_FORMAT_PATH, "utf8");

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
  const arrow = source.indexOf("=>", start);
  const braceStart = source.indexOf("{", arrow);
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

function extractMethod(classSource, signature) {
  const start = classSource.indexOf(signature);
  if (start === -1) {
    throw new Error(`Method signature not found: ${signature}`);
  }
  const braceStart = classSource.indexOf("{", start);
  const end = findMatchingBrace(classSource, braceStart);
  return classSource.slice(start, end + 1);
}

const helperSource = extractConst("const formatHassDateTime = (hass, date, options = {}, fallback = '') =>");

function buildHarness(methodSources) {
  return new Function(
    `
    ${helperSource}

    class Harness {
      constructor(payload) {
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
}

let result;
if (payload.action === "live_status_label") {
  const classSource = extractClass("class F1LiveSessionCard extends LitElement {");
  const Harness = buildHarness([
    extractMethod(classSource, "_normalizeOffset(offset) {"),
    extractMethod(classSource, "_parseDateWithOffset(value, offset) {"),
    extractMethod(classSource, "_formatLocalTime(value, offset) {"),
    extractMethod(classSource, "_getTimeZone() {"),
    extractMethod(classSource, "_getSessionStartValue(sessionStatus) {"),
    extractMethod(classSource, "_sessionStatusLabel(sessionStatus) {"),
  ]);
  const harness = new Harness(payload);
  result = harness._sessionStatusLabel(payload.sessionStatus || null);
} else if (payload.action === "fia_published") {
  const classSource = extractClass("class F1FiaDocumentsCard extends LitElement {");
  const Harness = buildHarness([
    extractMethod(classSource, "_parseDateTs(value) {"),
    extractMethod(classSource, "_formatPublished(value) {"),
  ]);
  const harness = new Harness(payload);
  result = harness._formatPublished(payload.value);
} else if (payload.action === "starting_grid_updated") {
  const classSource = extractClass("class F1StartingGridCard extends LitElement {");
  const Harness = buildHarness([
    extractMethod(classSource, "_formatDateTime(value) {"),
  ]);
  const harness = new Harness(payload);
  result = harness._formatDateTime(payload.value);
} else {
  throw new Error(`Unknown action: ${payload.action}`);
}

process.stdout.write(JSON.stringify(result));
"""


def _normalize_space(value: str) -> str:
    return value.replace("\u202f", " ").replace("\xa0", " ")


def _hass(time_format: str, language: str = "en-US") -> dict:
    return {
        "locale": {
            "time_format": time_format,
            "language": language,
            "time_zone": "UTC",
        },
        "config": {"time_zone": "UTC"},
    }


def _run_probe(payload: dict) -> str:
    if not CARD_PATH.exists():
        pytest.skip(f"card JS not found at {CARD_PATH}")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for card time formatting tests")

    completed = subprocess.run(
        [node, "-e", NODE_PROBE_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
        env={
            "CARD_TIME_FORMAT_PATH": str(CARD_PATH),
            "CARD_TIME_FORMAT_PAYLOAD": json.dumps(payload),
        },
    )
    return json.loads(completed.stdout)


def test_live_session_start_label_uses_ha_12_hour_time() -> None:
    result = _run_probe(
        {
            "action": "live_status_label",
            "hass": _hass("12"),
            "sessionStatus": {
                "state": "pre",
                "start_time": "2026-05-21T18:30:00",
                "gmt_offset": "+00:00",
            },
        }
    )

    assert _normalize_space(result) == "Starts 06:30 PM"


def test_fia_document_published_time_uses_ha_12_hour_time() -> None:
    result = _run_probe(
        {
            "action": "fia_published",
            "hass": _hass("12"),
            "value": "2026-05-21T18:30:00+00:00",
        }
    )

    assert "06:30 PM" in _normalize_space(result)


def test_starting_grid_updated_time_uses_ha_24_hour_time() -> None:
    result = _run_probe(
        {
            "action": "starting_grid_updated",
            "hass": _hass("24", "en-US"),
            "value": "2026-05-21T18:30:00+00:00",
        }
    )

    assert "18:30" in _normalize_space(result)
