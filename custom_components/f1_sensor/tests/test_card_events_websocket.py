"""Dashboard event subscriptions honor normal user read permissions."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.auth.permissions.events import SUBSCRIBE_ALLOWLIST
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context, callback
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import card_events_websocket as ws
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager

CONFIGURATION_EVENT = "f1_sensor_data_configuration"
RACE_CONTROL_EVENTS = (
    "f1_sensor_race_control_data",
    "f1_sensor_race_control_event",
    "f1_sensor_race_control_log_reset_event",
)


def _loaded_entry(hass, entry_id="first", *, domain=DOMAIN):
    entry = MockConfigEntry(
        domain=domain, entry_id=entry_id, state=ConfigEntryState.LOADED
    )
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace()
    return entry


def _message(event_type=CONFIGURATION_EVENT, **address):
    return {
        "id": 1,
        "type": "f1_sensor/events/subscribe",
        "protocol_version": 1,
        "event_type": event_type,
        **address,
    }


async def _events_before_pong(client, message_id=2):
    """Use a WS round trip to bound assertions without timing sleeps."""
    await client.send_json({"id": message_id, "type": "ping"})
    events = []
    while True:
        message = await client.receive_json()
        if message == {"id": message_id, "type": "pong"}:
            return events
        events.append(message)


@pytest.mark.parametrize("event_type", [CONFIGURATION_EVENT, *RACE_CONTROL_EVENTS])
async def test_read_only_user_can_receive_only_selected_f1_events(
    hass,
    hass_ws_client,
    hass_read_only_access_token,
    hass_read_only_user,
    event_type,
):
    """Authenticated viewers do not need the admin-only HA event endpoint."""
    assert not hass_read_only_user.is_admin
    allowlist_before = set(SUBSCRIBE_ALLOWLIST)
    entry = _loaded_entry(hass)
    hass.data[DOMAIN] = {"no_spoiler_manager": NoSpoilerModeManager(hass)}
    ws.async_register_card_events_websocket(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await client.send_json(_message(event_type, entry_id=entry.entry_id))
    assert (await client.receive_json())["success"] is True

    payload = {"entry_id": entry.entry_id, "message": {"Message": "YELLOW FLAG"}}
    hass.bus.async_fire("unrelated_event", payload)
    hass.bus.async_fire(event_type, {**payload, "entry_id": "another-entry"})
    hass.bus.async_fire(event_type, payload, context=Context(user_id="private-context"))
    await hass.async_block_till_done()
    events = await _events_before_pong(client)
    expected_data = (
        {"entry_id": entry.entry_id} if event_type == CONFIGURATION_EVENT else payload
    )
    assert events == [
        {
            "id": 1,
            "type": "event",
            "event": {"event_type": event_type, "data": expected_data},
        }
    ]
    assert SUBSCRIBE_ALLOWLIST == allowlist_before


async def test_global_configuration_subscription_returns_only_entry_identity(
    hass, hass_ws_client, hass_read_only_access_token
):
    _loaded_entry(hass)
    _loaded_entry(hass, "second")
    manager = NoSpoilerModeManager(hass)
    await manager.async_set_active(True)
    hass.data[DOMAIN] = {"no_spoiler_manager": manager}
    ws.async_register_card_events_websocket(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await client.send_json(_message())
    assert (await client.receive_json())["success"] is True
    for entry_id in ("first", "second"):
        hass.bus.async_fire(
            CONFIGURATION_EVENT,
            {"entry_id": entry_id, "unrelated_setting": "must-not-leak"},
        )
    await hass.async_block_till_done()
    events = await _events_before_pong(client)
    assert [event["event"] for event in events] == [
        {"event_type": CONFIGURATION_EVENT, "data": {"entry_id": entry_id}}
        for entry_id in ("first", "second")
    ]


@pytest.mark.parametrize(
    "message",
    [
        _message("*"),
        _message("state_changed"),
        _message("unrelated_event"),
        _message(protocol_version=2),
        _message(RACE_CONTROL_EVENTS[0]),
        _message(RACE_CONTROL_EVENTS[0], entry_id="first", entity_id="sensor.rc"),
    ],
)
async def test_subscription_rejects_broad_or_invalid_requests(
    hass, hass_ws_client, hass_read_only_access_token, message
):
    ws.async_register_card_events_websocket(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await client.send_json(message)
    response = await client.receive_json()
    assert response["success"] is False
    assert response["error"]["code"] in {
        "invalid_format",
        "invalid_request",
        "invalid_address",
    }


@pytest.mark.parametrize("entry_kind", ["missing", "foreign", "not_loaded"])
async def test_subscription_rejects_entries_without_loaded_f1_runtime(
    hass, hass_ws_client, hass_read_only_access_token, entry_kind
):
    if entry_kind != "missing":
        entry = _loaded_entry(
            hass, domain="another_integration" if entry_kind == "foreign" else DOMAIN
        )
        if entry_kind == "not_loaded":
            entry.runtime_data = None
    ws.async_register_card_events_websocket(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await client.send_json(_message(RACE_CONTROL_EVENTS[0], entry_id="first"))
    response = await client.receive_json()
    assert response["success"] is False
    assert response["error"]["code"] in {"not_found", "not_loaded"}


@pytest.mark.parametrize("entity_addressed", [False, True])
async def test_race_control_filters_entities_and_rechecks_read_permission(
    hass,
    hass_ws_client,
    hass_read_only_access_token,
    hass_read_only_user,
    entity_addressed,
):
    entry = _loaded_entry(hass)
    other = _loaded_entry(hass, "second")
    registry = er.async_get(hass)
    entity = registry.async_get_or_create(
        "sensor", DOMAIN, "first_race_control", config_entry=entry
    )
    other_entity = registry.async_get_or_create(
        "sensor", DOMAIN, "second_race_control", config_entry=other
    )
    hass.data[DOMAIN] = {"no_spoiler_manager": NoSpoilerModeManager(hass)}
    ws.async_register_card_events_websocket(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    address = (
        {"entity_id": entity.entity_id}
        if entity_addressed
        else {"entry_id": entry.entry_id}
    )
    await client.send_json(_message(RACE_CONTROL_EVENTS[0], **address))
    assert (await client.receive_json())["success"] is True

    payload = {
        "entry_id": entry.entry_id,
        "entity_id": entity.entity_id,
        "message": {"Message": "GREEN LIGHT"},
    }
    hass.bus.async_fire(RACE_CONTROL_EVENTS[0], payload)
    hass.bus.async_fire(
        RACE_CONTROL_EVENTS[0],
        {**payload, "entry_id": other.entry_id, "entity_id": other_entity.entity_id},
    )
    hass.bus.async_fire(
        RACE_CONTROL_EVENTS[0], {**payload, "entity_id": other_entity.entity_id}
    )
    await hass.async_block_till_done()
    assert len(await _events_before_pong(client)) == 1

    hass_read_only_user.mock_policy(
        {"entities": {"entity_ids": {entity.entity_id: {"read": False}}}}
    )
    hass.bus.async_fire(RACE_CONTROL_EVENTS[0], payload)
    await hass.async_block_till_done()
    assert await _events_before_pong(client, 3) == []

    # A sensor-free event cannot bypass an entity-restricted user's policy.
    hass.bus.async_fire(
        RACE_CONTROL_EVENTS[0], {"entry_id": entry.entry_id, "message": "RESULT"}
    )
    await hass.async_block_till_done()
    assert await _events_before_pong(client, 4) == []


async def test_entity_subscription_is_denied_without_read_permission(
    hass, hass_ws_client, hass_read_only_access_token, hass_read_only_user
):
    entry = _loaded_entry(hass)
    entity = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, "first_race_control", config_entry=entry
    )
    hass_read_only_user.mock_policy(
        {"entities": {"entity_ids": {entity.entity_id: {"read": False}}}}
    )
    ws.async_register_card_events_websocket(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await client.send_json(_message(RACE_CONTROL_EVENTS[0], entity_id=entity.entity_id))
    response = await client.receive_json()
    assert response["success"] is False
    assert response["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("protection", ["missing", "active"])
async def test_race_control_is_blocked_when_spoiler_safety_cannot_be_confirmed(
    hass, hass_ws_client, hass_read_only_access_token, protection
):
    entry = _loaded_entry(hass)
    if protection == "active":
        manager = NoSpoilerModeManager(hass)
        await manager.async_set_active(True)
        hass.data[DOMAIN] = {"no_spoiler_manager": manager}
    ws.async_register_card_events_websocket(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await client.send_json(_message(RACE_CONTROL_EVENTS[0], entry_id=entry.entry_id))
    assert (await client.receive_json())["success"] is True
    hass.bus.async_fire(
        RACE_CONTROL_EVENTS[0], {"entry_id": entry.entry_id, "message": "RESULT"}
    )
    await hass.async_block_till_done()
    assert await _events_before_pong(client) == []


async def test_unsubscribe_and_entry_unload_remove_event_listeners(
    hass, hass_ws_client, hass_read_only_access_token
):
    entry = _loaded_entry(hass)
    hass.data[DOMAIN] = {"no_spoiler_manager": NoSpoilerModeManager(hass)}
    ws.async_register_card_events_websocket(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    baseline = hass.bus.async_listeners().get(RACE_CONTROL_EVENTS[0], 0)
    await client.send_json(_message(RACE_CONTROL_EVENTS[0], entry_id=entry.entry_id))
    assert (await client.receive_json())["success"] is True
    assert hass.bus.async_listeners()[RACE_CONTROL_EVENTS[0]] == baseline + 1
    await client.send_json({"id": 2, "type": "unsubscribe_events", "subscription": 1})
    assert (await client.receive_json())["success"] is True
    assert hass.bus.async_listeners().get(RACE_CONTROL_EVENTS[0], 0) == baseline

    await client.send_json(
        {**_message(RACE_CONTROL_EVENTS[0], entry_id=entry.entry_id), "id": 3}
    )
    assert (await client.receive_json())["success"] is True
    reset_baseline = hass.bus.async_listeners().get(RACE_CONTROL_EVENTS[2], 0)
    await client.send_json(
        {**_message(RACE_CONTROL_EVENTS[2], entry_id=entry.entry_id), "id": 4}
    )
    assert (await client.receive_json())["success"] is True
    assert len(entry._on_state_change) == 2
    entry._async_set_state(hass, ConfigEntryState.UNLOAD_IN_PROGRESS, None)
    # These callbacks run before deferred close callbacks. They must not leak
    # data from an entry that has already started unloading.
    for event_type in (RACE_CONTROL_EVENTS[0], RACE_CONTROL_EVENTS[2]):
        hass.bus.async_fire(event_type, {"entry_id": entry.entry_id})
    await hass.async_block_till_done()
    assert await _events_before_pong(client, 5) == [
        {
            "id": subscription_id,
            "type": "event",
            "event": {
                "status": "closed",
                "event_type": event_type,
                "data": {},
            },
        }
        for subscription_id, event_type in (
            (3, RACE_CONTROL_EVENTS[0]),
            (4, RACE_CONTROL_EVENTS[2]),
        )
    ]
    assert hass.bus.async_listeners().get(RACE_CONTROL_EVENTS[0], 0) == baseline
    assert hass.bus.async_listeners().get(RACE_CONTROL_EVENTS[2], 0) == reset_baseline
    assert not entry._on_state_change


async def test_unsubscribe_during_event_dispatch_drops_already_selected_callback(
    hass, hass_read_only_user
):
    """HA can already have selected a callback when another listener removes it."""
    entry = _loaded_entry(hass)
    hass.data[DOMAIN] = {"no_spoiler_manager": NoSpoilerModeManager(hass)}
    connection = MagicMock(user=hass_read_only_user, subscriptions={})

    @callback
    def stop_before_forward(_event):
        connection.subscriptions.pop(1)()

    stop = hass.bus.async_listen(RACE_CONTROL_EVENTS[0], stop_before_forward)
    ws._ws_subscribe_card_events(
        hass, connection, _message(RACE_CONTROL_EVENTS[0], entry_id=entry.entry_id)
    )
    connection.send_result.assert_called_once_with(1)
    hass.bus.async_fire(RACE_CONTROL_EVENTS[0], {"entry_id": entry.entry_id})
    await hass.async_block_till_done()
    connection.send_message.assert_not_called()
    assert not connection.subscriptions
    assert not entry._on_state_change
    stop()


def test_card_event_command_registration_is_idempotent(hass, monkeypatch):
    registered = []
    monkeypatch.setattr(
        ws.websocket_api, "async_register_command", lambda _, fn: registered.append(fn)
    )
    ws.async_register_card_events_websocket(hass)
    ws.async_register_card_events_websocket(hass)
    assert registered == [ws._ws_subscribe_card_events]
    assert hass.data[DOMAIN][ws.CARD_EVENTS_WS_MARKER] is True
