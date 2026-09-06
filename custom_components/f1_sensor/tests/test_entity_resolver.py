from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
RESOLVER_PATH = (
    ROOT
    / "custom_components"
    / "f1_sensor"
    / "www"
    / "f1-sensor-live-data-card"
    / "platform"
    / "entity-resolver.js"
)

NODE_SCRIPT = r"""
import { pathToFileURL } from 'node:url';

const payload = JSON.parse(process.env.F1_RESOLVER_PAYLOAD || '{}');
const { resolveF1CardEntities } = await import(pathToFileURL(process.env.F1_RESOLVER_PATH));
let calls = 0;
const hass = {
  connection: {},
  callWS: async (message) => {
    calls += 1;
    if (message.type !== 'f1_sensor/entities') throw new Error('Unexpected command');
    return payload.entries;
  },
};
const first = await resolveF1CardEntities(hass, payload.config, payload.bindings);
const second = await resolveF1CardEntities(hass, first, payload.bindings);
process.stdout.write(JSON.stringify({ first, second, calls }));
"""


def _resolve(payload: dict) -> dict:
    env = {
        **os.environ,
        "F1_RESOLVER_PATH": str(RESOLVER_PATH),
        "F1_RESOLVER_PAYLOAD": json.dumps(payload),
    }
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", NODE_SCRIPT],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return json.loads(result.stdout)


def test_single_entry_resolves_empty_and_default_entities() -> None:
    result = _resolve(
        {
            "entries": [
                {
                    "entry_id": "entry-two",
                    "title": "F1",
                    "entities": {
                        "driver_list": "sensor.f1_driver_list_2",
                        "current_tyres": "sensor.f1_current_tyres_2",
                    },
                }
            ],
            "config": {
                "entry_id": "auto",
                "drivers_entity": "",
                "tyres_entity": "sensor.f1_current_tyres",
            },
            "bindings": {
                "drivers_entity": "driver_list",
                "tyres_entity": "current_tyres",
            },
        }
    )

    assert result["first"] == {
        "f1_entry_id": "entry-two",
        "entry_id": "entry-two",
        "drivers_entity": "sensor.f1_driver_list_2",
        "tyres_entity": "sensor.f1_current_tyres_2",
    }
    assert result["second"] == result["first"]
    assert result["calls"] == 1


def test_weekend_hub_resolves_automatic_config_entry() -> None:
    result = _resolve(
        {
            "entries": [
                {
                    "entry_id": "weekend-entry",
                    "title": "Weekend Hub",
                    "entities": {},
                }
            ],
            "config": {"entry_id": "auto", "default_view": "overview"},
            "bindings": {},
        }
    )

    assert result["first"] == {
        "f1_entry_id": "weekend-entry",
        "entry_id": "weekend-entry",
        "default_view": "overview",
    }
    assert result["second"] == result["first"]


def test_multiple_entries_infer_from_an_explicit_entity_and_preserve_overrides() -> (
    None
):
    result = _resolve(
        {
            "entries": [
                {
                    "entry_id": "first",
                    "entities": {
                        "driver_list": "sensor.f1_driver_list",
                        "current_tyres": "sensor.f1_current_tyres",
                    },
                },
                {
                    "entry_id": "second",
                    "entities": {
                        "driver_list": "sensor.office_drivers",
                        "current_tyres": "sensor.f1_current_tyres_2",
                    },
                },
            ],
            "config": {
                "drivers_entity": "sensor.office_drivers",
                "tyres_entity": "sensor.f1_current_tyres",
            },
            "bindings": {
                "drivers_entity": "driver_list",
                "tyres_entity": "current_tyres",
            },
        }
    )

    assert result["first"]["f1_entry_id"] == "second"
    assert result["first"]["drivers_entity"] == "sensor.office_drivers"
    assert result["first"]["tyres_entity"] == "sensor.f1_current_tyres_2"


def test_multiple_entries_remain_unchanged_when_selection_is_ambiguous() -> None:
    config = {"drivers_entity": "", "tyres_entity": ""}
    result = _resolve(
        {
            "entries": [
                {"entry_id": "first", "entities": {"driver_list": "sensor.one"}},
                {"entry_id": "second", "entities": {"driver_list": "sensor.two"}},
            ],
            "config": config,
            "bindings": {
                "drivers_entity": "driver_list",
                "tyres_entity": "current_tyres",
            },
        }
    )

    assert result["first"] == config
