"""Preserve legacy Race Control event automations independently of sensor selection."""

from __future__ import annotations

import asyncio
import re

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import async_migrate_entry
from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS


def _entry(
    version: int, live_enabled: bool = True, minor_version: int = 1
) -> MockConfigEntry:
    selected = {"session_status", "track_status"}
    settings = {"enable_race_control": live_enabled, "operation_mode": "live"}
    if version == 1:
        settings["enabled_sensors"] = sorted(selected)
    else:
        settings["disabled_sensors"] = sorted(SUPPORTED_SENSOR_KEYS - selected)
    return MockConfigEntry(
        domain=DOMAIN,
        version=version,
        minor_version=minor_version,
        data={"sensor_name": "F1", **(settings if version < 3 else {})},
        options=settings if version >= 3 else {},
    )


@pytest.mark.parametrize("version", [1, 2, 3, 4])
async def test_legacy_event_automation_survives_upgrade_and_reload(
    hass, enable_custom_integrations, aioclient_mock, version
):
    """An existing event trigger must work without enabling the Race Control sensor."""
    aioclient_mock.get(
        re.compile(r"https://.*"),
        json={"Meetings": [], "MRData": {"RaceTable": {"Races": []}}},
    )
    entry = _entry(version)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.version == 4
    assert entry.minor_version == 2
    assert entry.data["legacy_race_control_events"] is True
    events = []
    received = asyncio.Event()

    @callback
    def record_event(event):
        events.append(event.data)
        received.set()

    unsub = hass.bus.async_listen("test_legacy_race_control", record_event)
    try:
        assert await async_setup_component(
            hass,
            "automation",
            {
                "automation": [
                    {
                        "id": "legacy_race_control",
                        "alias": "Legacy Race Control",
                        "triggers": [
                            {
                                "trigger": "event",
                                "event_type": "f1_sensor_race_control_event",
                            }
                        ],
                        "actions": [
                            {
                                "event": "test_legacy_race_control",
                                "event_data": {
                                    "message": "{{ trigger.event.data.message.Message }}"
                                },
                            }
                        ],
                    }
                ]
            },
        )
        await hass.async_block_till_done()
        for index in range(2):
            received.clear()
            registry = hass.data[DOMAIN][entry.entry_id]
            assert registry["race_control_coordinator"] is not None
            assert (
                "RaceControlMessages"
                in entry.runtime_data.capabilities.requested_streams
            )
            assert (
                "race_control" not in entry.runtime_data.capabilities.requested_features
            )
            assert (
                er.async_get(hass).async_get_entity_id(
                    "sensor", DOMAIN, f"{entry.entry_id}_race_control"
                )
                is None
            )
            registry["live_bus"]._dispatch(
                "RaceControlMessages",
                {
                    "Messages": {
                        str(index): {
                            "Utc": dt_util.utcnow().isoformat(),
                            "Category": "Flag",
                            "Flag": "YELLOW",
                            "Message": f"YELLOW IN SECTOR {index + 1}",
                        }
                    }
                },
            )
            await asyncio.wait_for(received.wait(), timeout=2)
            await hass.async_block_till_done()
            assert len(events) == index + 1
            assert events[-1]["message"] == f"YELLOW IN SECTOR {index + 1}"
            if index == 0:
                saved_data = dict(entry.data)
                saved_options = dict(entry.options)
                assert await hass.config_entries.async_reload(entry.entry_id)
                await hass.async_block_till_done()
                assert dict(entry.data) == saved_data
                assert dict(entry.options) == saved_options
        # The compatibility flag must never override an explicit live-API off.
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, "enable_race_control": False}
        )
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert (
            "RaceControlMessages"
            not in entry.runtime_data.capabilities.requested_streams
        )
        assert hass.data[DOMAIN][entry.entry_id].get("race_control_coordinator") is None
    finally:
        unsub()
        if entry.state is ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    ("minor_version", "live_enabled"), [(1, False), (2, True), (2, False)]
)
async def test_migration_does_not_enable_unrequested_event_delivery(
    hass, enable_custom_integrations, aioclient_mock, minor_version, live_enabled
):
    """Keep live disabled and preserve feature-based demand for new installations."""
    aioclient_mock.get(
        re.compile(r"https://.*"),
        json={"Meetings": [], "MRData": {"RaceTable": {"Races": []}}},
    )
    entry = _entry(4, live_enabled, minor_version)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    try:
        assert (
            "RaceControlMessages"
            not in entry.runtime_data.capabilities.requested_streams
        )
        assert hass.data[DOMAIN][entry.entry_id].get("race_control_coordinator") is None
    finally:
        if entry.state is ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("minor_version", [2, 3])
async def test_migration_preserves_existing_compatibility_metadata(hass, minor_version):
    """Revisiting migration must not reset event compatibility or newer metadata."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        minor_version=minor_version,
        data={"sensor_name": "F1", "legacy_race_control_events": True},
        options={"enable_race_control": False},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.version == 4
    assert entry.minor_version == minor_version
    assert entry.data["legacy_race_control_events"] is True
    assert entry.options["enable_race_control"] is False
