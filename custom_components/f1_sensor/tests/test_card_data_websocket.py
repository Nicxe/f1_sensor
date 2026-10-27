"""Direct subscriptions work with no registered data sensor."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor.card_data import CardDataStore
from custom_components.f1_sensor.card_data_websocket import (
    _ws_subscribe_card_data,
    async_register_card_data_websocket,
)
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager


async def test_subscription_has_own_initial_snapshot_and_unloads(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, options={"card_data_features": ["driver_standings"]}
    )
    entry.add_to_hass(hass)
    hass.data[DOMAIN] = {"no_spoiler_manager": NoSpoilerModeManager(hass)}
    coordinator = SimpleNamespace(
        data={},
        last_update_success=True,
        async_add_listener=MagicMock(return_value=lambda: None),
    )
    store = CardDataStore(hass, entry, {"driver_coordinator": coordinator})
    entry.runtime_data = SimpleNamespace(card_data=store)
    connection = MagicMock(subscriptions={})
    _ws_subscribe_card_data(
        hass,
        connection,
        {
            "id": 1,
            "entry_id": entry.entry_id,
            "protocol_version": 1,
            "type": "f1_sensor/data/subscribe",
            "data_keys": ["driver_standings"],
        },
    )
    connection.send_result.assert_called_once_with(1)
    assert connection.send_message.call_args.args[0]["event"]["status"] == "ready"
    await store.async_close()
    assert connection.send_message.call_args.args[0]["event"]["status"] == "closed"
    assert not connection.subscriptions


async def test_unknown_and_unloaded_entry_returns_actionable_errors(hass):
    connection = MagicMock(subscriptions={})
    message = {
        "id": 1,
        "entry_id": "missing",
        "protocol_version": 1,
        "data_keys": ["driver_standings"],
    }
    _ws_subscribe_card_data(hass, connection, message)
    assert connection.send_error.call_args.args[1] == "not_found"
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    _ws_subscribe_card_data(hass, connection, {**message, "entry_id": entry.entry_id})
    assert connection.send_error.call_args.args[1] == "not_loaded"


def test_commands_register_once(hass, monkeypatch):
    registered = MagicMock()
    monkeypatch.setattr(
        "custom_components.f1_sensor.card_data_websocket.websocket_api.async_register_command",
        registered,
    )
    async_register_card_data_websocket(hass)
    async_register_card_data_websocket(hass)
    registered.assert_called_once()


async def test_connection_close_keeps_subscription_mapping_owned_by_home_assistant(
    hass,
):
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    store = CardDataStore(hass, entry, {})
    entry.runtime_data = SimpleNamespace(card_data=store)
    connection = MagicMock(subscriptions={})
    _ws_subscribe_card_data(
        hass,
        connection,
        {
            "id": 1,
            "entry_id": entry.entry_id,
            "protocol_version": 1,
            "type": "f1_sensor/data/subscribe",
            "data_keys": ["driver_standings"],
        },
    )
    for unsubscribe in connection.subscriptions.values():
        unsubscribe()
    assert set(connection.subscriptions) == {1}
    connection.subscriptions.clear()
    assert not store._listeners
    await store.async_close()
