"""Real HA setup, data propagation and unload from the installable artifact."""

import os
from pathlib import Path
import re

from homeassistant.config_entries import ConfigEntryState
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.asyncio
async def test_installed_integration_lifecycle(
    hass, enable_custom_integrations, aioclient_mock, hass_ws_client
):
    from custom_components import f1_sensor
    from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS

    assert (
        Path(f1_sensor.__file__).parent.resolve()
        == Path(os.environ["F1_INSTALLED_ROOT"]).resolve()
    )
    aioclient_mock.get(
        re.compile(r"https://.*"),
        json={"Meetings": [], "MRData": {"RaceTable": {"Races": []}}},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        data={
            "sensor_name": "F1",
            "enable_race_control": True,
            "operation_mode": "live",
            "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS - {"track_status"}),
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.LOADED
    registry = hass.data[DOMAIN][entry.entry_id]
    bus = registry["live_bus"]
    registry["live_state"].set_state(True, "smoke-feed")
    bus._dispatch("TrackStatus", {"Status": "2", "Message": "Yellow"})
    await hass.async_block_till_done()
    states = hass.states.async_all("sensor")
    state = next(s for s in states if "track_status" in s.entity_id)
    assert state.state == "YELLOW"
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "f1_sensor/entities"})
    result = await client.receive_json()
    assert result["success"]
    assert result["result"][0]["entities"]["track_status"] == state.entity_id
    await client.close()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
