"""Race Control history no longer requires a sensor to address the entry."""

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import RaceControlLogStore, _ws_get_race_control_log
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager


async def test_entry_address_reads_history_without_sensor_and_honors_spoilers(hass):
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    store = RaceControlLogStore(hass, entry.entry_id)
    await store.async_initialize()
    store.append({"Message": "YELLOW FLAG", "Utc": "2026-10-20T12:00:00Z"})
    manager = NoSpoilerModeManager(hass)
    hass.data[DOMAIN] = {
        "no_spoiler_manager": manager,
        entry.entry_id: {"race_control_log_store": store},
    }
    connection = MagicMock()
    message = {"id": 1, "entry_id": entry.entry_id}
    _ws_get_race_control_log(hass, connection, message)
    await hass.async_block_till_done()
    assert (
        connection.send_result.call_args.args[1]["items"][0]["message"] == "YELLOW FLAG"
    )
    await manager.async_set_active(True)
    _ws_get_race_control_log(hass, connection, message)
    await hass.async_block_till_done()
    assert connection.send_result.call_args.args[1]["items"] == []
    assert connection.send_result.call_args.args[1]["status"] == "blocked"
    await store.async_close()
