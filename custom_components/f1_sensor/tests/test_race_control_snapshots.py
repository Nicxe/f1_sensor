"""Race Control snapshots contain events, not container placeholder messages."""

from __future__ import annotations

import json
from pathlib import Path
import re

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import _RC_LOG_EVENT, RaceControlCoordinator
from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"Messages": {}},
        {"Messages": []},
        {"Messages": None},
        {"Messages": "invalid"},
        {"Messages": {"0": {}}},
        {"Messages": [{}]},
        [{}],
    ],
)
def test_empty_race_control_snapshots_contain_no_events(payload):
    assert RaceControlCoordinator._extract_items(payload) == []


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"Flag": "YELLOW"}, [{"Flag": "YELLOW"}]),
        ({"Scope": "Sector", "Sector": 3}, [{"Scope": "Sector", "Sector": 3}]),
        ({"CategoryType": "SafetyCar"}, [{"CategoryType": "SafetyCar"}]),
        ({"Messages": [{"Flag": "GREEN"}]}, [{"Flag": "GREEN"}]),
        (
            {
                "Messages": {
                    "2": {"Flag": "GREEN"},
                    "1": {"Flag": "YELLOW"},
                    "metadata": {},
                }
            },
            [{"Flag": "YELLOW", "id": 1}, {"Flag": "GREEN", "id": 2}],
        ),
        (
            {"Messages": {"source-id": {"Flag": "YELLOW", "id": "official-id"}}},
            [{"Flag": "YELLOW", "id": "official-id"}],
        ),
    ],
)
def test_race_control_snapshot_preserves_valid_partial_events(payload, expected):
    assert RaceControlCoordinator._extract_items(payload) == expected


@pytest.mark.parametrize("snapshot_name", ["empty", "initial_state", "checkpoint"])
async def test_real_entry_delivers_checkpoint_events_without_placeholders(
    hass, enable_custom_integrations, aioclient_mock, snapshot_name
):
    """Exercise real bus, entity, saved log and event delivery from cached P2 data."""
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/race_control_p2_checkpoint.json").read_text()
    )
    payload = {"Messages": {}} if snapshot_name == "empty" else fixture[snapshot_name]
    expected = list(payload["Messages"].values())
    aioclient_mock.get(
        re.compile(r"https://.*"),
        json={"Meetings": [], "MRData": {"RaceTable": {"Races": []}}},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        data={"sensor_name": "F1"},
        options={
            "operation_mode": "live",
            "enable_race_control": True,
            "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS - {"race_control"}),
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    events = []

    @callback
    def record_event(event):
        events.append(event.data)

    unsub = hass.bus.async_listen(_RC_LOG_EVENT, record_event)
    try:
        registry = hass.data[DOMAIN][entry.entry_id]
        registry["live_state"].set_state(True, "replay")
        bus = registry["live_bus"]
        store = registry["race_control_log_store"]
        coordinator = registry["race_control_coordinator"]
        entity_id = er.async_get(hass).async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_race_control"
        )
        bus._dispatch("RaceControlMessages", payload)
        await hass.async_block_till_done()
        assert [item["message"] for item in store.get_items()] == [
            item["Message"] for item in reversed(expected)
        ]
        assert [event["message"]["Message"] for event in events] == [
            item["Message"] for item in expected
        ]
        if expected:
            assert hass.states.get(entity_id).state == expected[-1]["Message"]
            assert coordinator.data["Utc"] == expected[-1]["Utc"]
        else:
            assert coordinator.data is None
            assert hass.states.get(entity_id).state in ("unknown", "unavailable")

        # Replayed snapshots and empty updates must not append or replace events.
        bus._dispatch("RaceControlMessages", payload)
        bus._dispatch("RaceControlMessages", {"Messages": {}})
        await hass.async_block_till_done()
        assert len(events) == len(expected)
        assert len(store.get_items()) == len(expected)
        if expected:
            assert hass.states.get(entity_id).state == expected[-1]["Message"]
    finally:
        unsub()
        if entry.state is ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)
