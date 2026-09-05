"""Regression tests for Home Assistant locale-aware card time formatting."""

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
} else if (payload.action === "race_control_time") {
  const classSource = extractClass("class F1RaceControlCard extends LitElement {");
  const Harness = buildHarness([
    extractMethod(classSource, "_formatListTime(value) {"),
  ]);
  const harness = new Harness(payload);
  result = harness._formatListTime(payload.value);
} else if (payload.action === "explicit_time_zone") {
  result = new Function("hass", "value", `${helperSource}
    return formatHassDateTime(hass, new Date(value), {
      hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Asia/Tokyo'
    }, '--:--:--');`)(payload.hass, payload.value);
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
        pytest.fail(f"Bundled card JS not found at {CARD_PATH}")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for card time formatting tests")

    completed = subprocess.run(
        [node, "-e", NODE_PROBE_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
        env={
            "TZ": "America/New_York",
            "LANG": payload.get("browser_language", "en_US.UTF-8"),
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


@pytest.mark.parametrize(
    ("time_zone", "expected"),
    [
        ("server", "12:33:14"),
        ("local", "06:33:14"),
        ("UTC", "10:33:14"),
        (None, "12:33:14"),
    ],
)
@pytest.mark.parametrize(
    "value",
    ["2026-09-04T10:33:14+00:00", "2026-09-04T10:33:14Z", "2026-09-04T10:33:14"],
)
def test_race_control_time_resolves_ha_time_zone_preference(
    time_zone: str | None, expected: str, value: str
) -> None:
    hass = _hass("24", "en-GB")
    hass["locale"]["time_zone"] = time_zone
    hass["config"]["time_zone"] = "Europe/Stockholm"

    assert (
        _run_probe({"action": "race_control_time", "hass": hass, "value": value})
        == expected
    )


def test_race_control_time_keeps_12_hour_preference() -> None:
    hass = _hass("12")
    hass["locale"]["time_zone"] = "server"
    hass["config"]["time_zone"] = "Europe/Stockholm"

    assert (
        _normalize_space(
            _run_probe(
                {
                    "action": "race_control_time",
                    "hass": hass,
                    "value": "2026-09-04T10:33:14+00:00",
                }
            )
        )
        == "12:33:14 PM"
    )


@pytest.mark.parametrize("value", [None, "", "invalid"])
def test_race_control_time_keeps_placeholder_for_missing_or_invalid_time(value) -> None:
    assert _run_probe({"action": "race_control_time", "value": value}) == "--:--:--"


@pytest.mark.parametrize("time_zone", ["server", "local"])
def test_explicit_track_time_zone_overrides_profile_preference(time_zone: str) -> None:
    hass = _hass("24", "en-GB")
    hass["locale"]["time_zone"] = time_zone
    hass["config"]["time_zone"] = "Europe/Stockholm"

    assert (
        _run_probe(
            {
                "action": "explicit_time_zone",
                "hass": hass,
                "value": "2026-09-04T10:33:14+00:00",
            }
        )
        == "19:33:14"
    )


@pytest.mark.parametrize(
    ("time_format", "language", "browser_language", "expected"),
    [
        ("12", "en-GB", "sv_SE.UTF-8", "06:30:00 pm"),
        ("24", "en-US", "en_US.UTF-8", "18:30:00"),
        ("language", "en-US", "sv_SE.UTF-8", "06:30:00 PM"),
        ("language", "en-GB", "en_US.UTF-8", "18:30:00"),
        ("system", "en-US", "sv_SE.UTF-8", "18:30:00"),
        ("system", "en-GB", "en_US.UTF-8", "06:30:00 pm"),
    ],
)
def test_race_control_follows_all_ha_time_format_preferences(
    time_format: str, language: str, browser_language: str, expected: str
) -> None:
    result = _run_probe(
        {
            "action": "race_control_time",
            "hass": _hass(time_format, language),
            "browser_language": browser_language,
            "value": "2026-09-04T18:30:00Z",
        }
    )
    assert _normalize_space(result) == expected


def test_race_control_24_hour_midnight_starts_at_zero() -> None:
    assert (
        _run_probe(
            {
                "action": "race_control_time",
                "hass": _hass("24", "en-US"),
                "value": "2026-09-04T00:05:00Z",
            }
        )
        == "00:05:00"
    )
