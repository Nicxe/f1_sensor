"""Authenticated, narrowly scoped event subscriptions for dashboard readers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_registry as er
import voluptuous as vol

from .const import DOMAIN

CARD_EVENTS_WS_MARKER = "__card_events_ws_registered__"
CARD_EVENTS_WS_TYPE = f"{DOMAIN}/events/subscribe"
CARD_CONFIGURATION_EVENT = f"{DOMAIN}_data_configuration"
CARD_EVENT_TYPES = frozenset(
    {
        CARD_CONFIGURATION_EVENT,
        f"{DOMAIN}_race_control_data",
        f"{DOMAIN}_race_control_event",
        f"{DOMAIN}_race_control_log_reset_event",
    }
)


@callback
def async_register_card_events_websocket(hass: HomeAssistant) -> None:
    """Register once; Home Assistant authenticates each WebSocket connection."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get(CARD_EVENTS_WS_MARKER):
        return
    websocket_api.async_register_command(hass, _ws_subscribe_card_events)
    root[CARD_EVENTS_WS_MARKER] = True


@websocket_api.websocket_command(
    {
        vol.Required("type"): CARD_EVENTS_WS_TYPE,
        vol.Required("protocol_version"): vol.In((1,)),
        vol.Required("event_type"): vol.In(CARD_EVENT_TYPES),
        vol.Exclusive("entry_id", "address"): str,
        vol.Exclusive("entity_id", "address"): cv.entity_id,
    }
)
@callback
def _ws_subscribe_card_events(
    hass: HomeAssistant, connection: Any, msg: dict[str, Any]
) -> None:
    """Forward only card events, preserving their existing delivery chronology."""
    event_type = msg["event_type"]
    entity_id = msg.get("entity_id")
    entry_id = msg.get("entry_id")
    if entity_id:
        entity = er.async_get(hass).async_get(entity_id)
        if entity is None or entity.platform != DOMAIN:
            connection.send_error(msg["id"], "not_found", "F1 Sensor entity not found")
            return
        entry_id = entity.config_entry_id
        if not connection.user.permissions.check_entity(entity_id, POLICY_READ):
            connection.send_error(msg["id"], "unauthorized", "Unauthorized")
            return
    entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
    if entry_id and (entry is None or entry.domain != DOMAIN):
        connection.send_error(msg["id"], "not_found", "F1 Sensor entry not found")
        return
    if event_type != CARD_CONFIGURATION_EVENT and entry is None:
        connection.send_error(
            msg["id"], "invalid_address", "Race Control requires an entry or entity"
        )
        return
    if entry is not None and getattr(entry, "runtime_data", None) is None:
        connection.send_error(msg["id"], "not_loaded", "F1 Sensor data is not loaded")
        return
    cleanups: list[Callable[[], None]] = []

    @callback
    def unsubscribe() -> None:
        # HA owns removal from connection.subscriptions on client disconnect.
        while cleanups:
            cleanups.pop()()

    @callback
    def forward(event: Event) -> None:
        if not cleanups or (
            entry is not None and entry.state is not ConfigEntryState.LOADED
        ):
            return
        data = event.data
        if entry_id and data.get("entry_id") != entry_id:
            return
        if entity_id and data.get("entity_id") != entity_id:
            return
        if event_type == CARD_CONFIGURATION_EVENT:
            payload = {"entry_id": data.get("entry_id")}
        else:
            manager = hass.data.get(DOMAIN, {}).get("no_spoiler_manager")
            if manager is None or manager.is_active:
                return
            event_entity_id = data.get("entity_id")
            permissions = connection.user.permissions
            if event_entity_id:
                entity = er.async_get(hass).async_get(event_entity_id)
                if (
                    entity is None
                    or entity.platform != DOMAIN
                    or entity.config_entry_id != entry_id
                ):
                    return
                if not permissions.check_entity(event_entity_id, POLICY_READ):
                    return
            elif not permissions.access_all_entities(POLICY_READ):
                return
            payload = dict(data)
        connection.send_message(
            websocket_api.event_message(
                msg["id"], {"event_type": event_type, "data": payload}
            )
        )

    @callback
    def close() -> None:
        if not cleanups:
            return
        connection.send_message(
            websocket_api.event_message(
                msg["id"], {"status": "closed", "event_type": event_type, "data": {}}
            )
        )
        connection.subscriptions.pop(msg["id"], None)
        unsubscribe()

    @callback
    def entry_state_changed() -> None:
        if entry.state is not ConfigEntryState.LOADED:
            # Defer removal: HA may be iterating the entry's listener list.
            hass.loop.call_soon(close)

    cleanups.append(hass.bus.async_listen(event_type, forward))
    if entry is not None:
        cleanups.append(entry.async_on_state_change(entry_state_changed))
    connection.subscriptions[msg["id"]] = unsubscribe
    connection.send_result(msg["id"])
