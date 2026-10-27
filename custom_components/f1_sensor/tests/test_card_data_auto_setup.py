"""Real setup and card clients operate without sensors or manual data selection."""

import re

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS
from custom_components.f1_sensor.data_choice import notification_id


@pytest.mark.parametrize("old_card_selection", [None, [], ["weather"]])
async def test_automatic_card_data_lazy_shared_and_reload_preserves_sensors(
    hass, enable_custom_integrations, aioclient_mock, hass_ws_client, old_card_selection
):
    aioclient_mock.get(
        re.compile(r"https://.*"),
        json={
            "MRData": {
                "total": "1",
                "limit": "100",
                "offset": "0",
                "StandingsTable": {
                    "StandingsLists": [
                        {
                            "season": "2026",
                            "round": "18",
                            "DriverStandings": [
                                {
                                    "position": "1",
                                    "points": "331",
                                    "Driver": {"driverId": "russell", "code": "RUS"},
                                    "Constructors": [{"constructorId": "mercedes"}],
                                }
                            ],
                        }
                    ]
                },
            }
        },
    )
    options = {
        "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS),
        "enable_race_control": False,
        "install_dashboard_cards": False,
    }
    if old_card_selection is not None:
        options["card_data_features"] = old_card_selection
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        minor_version=2,
        data={"sensor_name": "F1", "operation_mode": "live"},
        options=options,
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    record = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_driver_standings",
        config_entry=entry,
        suggested_object_id="my_standings",
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    before = (record.entity_id, record.name, record.disabled_by)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.LOADED
    assert "data_choice_version" not in entry.data
    assert dict(entry.options) == options
    assert aioclient_mock.call_count == 0
    owner = entry.runtime_data.card_data
    assert owner._timer is None
    first, second = await hass_ws_client(hass), await hass_ws_client(hass)
    request = {
        "id": 1,
        "type": "f1_sensor/data/subscribe",
        "entry_id": entry.entry_id,
        "protocol_version": 1,
        "data_keys": ["driver_standings"],
    }
    for client in (first, second):
        await client.send_json(request)
        assert (await client.receive_json())["success"]
        while True:
            message = await client.receive_json()
            if message["event"]["status"] == "ready":
                break
        assert (
            message["event"]["payload"]["attributes"]["driver_standings"][0]["points"]
            == "331"
        )
    assert aioclient_mock.call_count == 1
    await first.close()
    await hass.async_block_till_done()
    assert "driver_coordinator" in owner._unsubs
    await second.close()
    await hass.async_block_till_done()
    assert not owner._unsubs
    persistent_notification.async_dismiss(hass, notification_id(entry.entry_id))
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.LOADED
    assert owner.closed
    assert dict(entry.options) == options
    record = registry.async_get(record.entity_id)
    assert (record.entity_id, record.name, record.disabled_by) == before
    assert aioclient_mock.call_count == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
