"""Regression tests for Home Assistant unit handling in weather cards."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

CARD_PATH = (
    Path(__file__).resolve().parents[1]
    / "www"
    / "f1-sensor-live-data-card"
    / "f1-sensor-live-data-card.js"
)

NODE_PROBE_SCRIPT = r"""
const fs = require("node:fs");

const payload = JSON.parse(process.env.WEATHER_UNIT_PAYLOAD || "{}");
const source = fs.readFileSync(process.env.WEATHER_UNIT_CARD_PATH, "utf8");

function findMatchingBrace(text, openIndex) {
  let depth = 0;
  for (let index = openIndex; index < text.length; index += 1) {
    if (text[index] === "{") {
      depth += 1;
    } else if (text[index] === "}") {
      depth -= 1;
      if (depth === 0) {
        return index;
      }
    }
  }
  throw new Error(`Unmatched brace starting at ${openIndex}`);
}

function extractFunction(signature) {
  const start = source.indexOf(signature);
  if (start === -1) {
    throw new Error(`Function signature not found: ${signature}`);
  }
  const braceStart = source.indexOf("{", start);
  const end = findMatchingBrace(source, braceStart);
  return source.slice(start, end + 1);
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

const helpers = [
  extractFunction("function getF1UnitSystemUnit(hass, key, fallback) {"),
  extractFunction("function getF1TemperatureUnit(hass, entity) {"),
  extractFunction("function convertF1Temperature(value, fromUnit, toUnit) {"),
  extractFunction("function convertF1Speed(value, fromUnit, toUnit) {"),
];

const liveClass = extractClass("class F1LiveSessionCard extends LitElement {");
const nextRaceClass = extractClass("class F1NextRaceCard extends LitElement {");

const Harness = new Function(
  `
  ${helpers.join("\n\n")}

  function getEntityStateWithFallback(hass, entityId) {
    return hass.states[entityId] || null;
  }

  class Harness {
    constructor(payload) {
      this.hass = payload.hass;
      this.config = payload.config || {};
    }

    _configuredEntityId(key) {
      return this.config[key] || null;
    }

    _legacyEntityId() {
      return null;
    }

    _hasTrackWeather() {
      return true;
    }

    ${extractMethod(liveClass, "_getWeatherData() {")}
    ${extractMethod(nextRaceClass, "_weatherBlockHasData(block) {")}
    ${extractMethod(
      nextRaceClass,
      "_resolveWeatherComparison(weatherState, trackWeatherState, sessionStatus) {",
    )}
    ${extractMethod(nextRaceClass, "_formatTemperature(value, unit) {")}
    ${extractMethod(nextRaceClass, "_formatWind(speed, directionDegrees, unit) {")}
    ${extractMethod(nextRaceClass, "_windDirectionToCardinal(degrees) {")}
  }

  return Harness;
`,
)();

const harness = new Harness(payload);
let result;

if (payload.action === "live") {
  result = harness._getWeatherData();
} else if (payload.action === "next_race") {
  result = harness._resolveWeatherComparison(
    payload.weatherState,
    payload.trackWeatherState,
    payload.sessionStatus,
  );
} else if (payload.action === "format") {
  result = {
    temperature: harness._formatTemperature(payload.temperature, payload.temperatureUnit),
    wind: harness._formatWind(payload.wind, payload.windDirection, payload.windUnit),
  };
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
        pytest.skip("node is required for weather card unit tests")

    env = os.environ.copy()
    env["WEATHER_UNIT_CARD_PATH"] = str(CARD_PATH)
    env["WEATHER_UNIT_PAYLOAD"] = json.dumps(payload)
    completed = subprocess.run(
        [node, "-e", NODE_PROBE_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(completed.stdout)


def _hass(*, temperature: str = "°F", wind_speed: str = "mph") -> dict:
    return {
        "config": {
            "unit_system": {
                "temperature": temperature,
                "wind_speed": wind_speed,
            }
        },
        "states": {},
    }


def test_live_weather_uses_entity_temperature_unit_and_ha_wind_unit() -> None:
    hass = _hass()
    hass["states"]["sensor.f1_track_weather"] = {
        "state": "68",
        "attributes": {
            "unit_of_measurement": "°F",
            "air_temperature": 20,
            "track_temperature": 30,
            "wind_speed": 10,
        },
    }

    result = _run_probe(
        {
            "action": "live",
            "hass": hass,
            "config": {"weather_entity": "sensor.f1_track_weather"},
        }
    )

    assert result["air_temperature"] == 68
    assert result["track_temperature"] == 86
    assert result["temperature_unit"] == "°F"
    assert result["wind_speed"] == pytest.approx(22.3693629205)
    assert result["wind_speed_unit"] == "mph"


def test_next_race_weather_converts_raw_attributes_to_selected_units() -> None:
    result = _run_probe(
        {
            "action": "next_race",
            "hass": _hass(),
            "weatherState": {
                "state": "68",
                "attributes": {
                    "unit_of_measurement": "°F",
                    "current_temperature": 20,
                    "current_wind_speed": 5,
                    "race_temperature": 25,
                    "race_wind_speed": 10,
                },
            },
            "trackWeatherState": {
                "state": "69.8",
                "attributes": {
                    "unit_of_measurement": "°F",
                    "air_temperature": 21,
                    "track_temperature": 40,
                    "wind_speed": 10,
                },
            },
            "sessionStatus": {"state": "live"},
        }
    )

    assert result["now"]["temperature"] == 69.8
    assert result["now"]["trackTemperature"] == 104
    assert result["now"]["temperatureUnit"] == "°F"
    assert result["now"]["windSpeed"] == pytest.approx(22.3693629205)
    assert result["now"]["windSpeedUnit"] == "mph"
    assert result["race"]["temperature"] == 77
    assert result["race"]["temperatureUnit"] == "°F"
    assert result["race"]["windSpeed"] == pytest.approx(22.3693629205)


def test_weather_formatters_render_selected_units() -> None:
    result = _run_probe(
        {
            "action": "format",
            "hass": _hass(),
            "temperature": 77,
            "temperatureUnit": "°F",
            "wind": 22.3693629205,
            "windDirection": 90,
            "windUnit": "mph",
        }
    )

    assert result == {
        "temperature": "77.0 °F",
        "wind": "22.4 mph E",
    }
