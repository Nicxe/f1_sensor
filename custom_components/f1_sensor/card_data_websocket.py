"""Versioned subscriptions for entity-independent card data."""

from __future__ import annotations

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
import voluptuous as vol

from .card_data import DATA_PRODUCTS, DATA_PROTOCOL_VERSION, CardDataStore
from .const import DOMAIN

CARD_DATA_WS_MARKER = "__card_data_ws_registered__"
CARD_DATA_WS_TYPE = f"{DOMAIN}/data/subscribe"
CARD_RACE_CONTROL_EVENT = f"{DOMAIN}_race_control_data"


@callback
def async_register_card_data_websocket(hass: HomeAssistant) -> None:
    """Register read commands once; HA authenticates WebSocket connections."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get(CARD_DATA_WS_MARKER):
        return
    websocket_api.async_register_command(hass, _ws_subscribe_card_data)
    root[CARD_DATA_WS_MARKER] = True


@websocket_api.websocket_command(
    {
        vol.Required("type"): CARD_DATA_WS_TYPE,
        vol.Required("entry_id"): str,
        vol.Required("protocol_version"): vol.In((DATA_PROTOCOL_VERSION,)),
        vol.Required("data_keys"): vol.All([str], vol.Length(min=1, max=64)),
    }
)
@callback
def _ws_subscribe_card_data(
    hass: HomeAssistant, connection: Any, msg: dict[str, Any]
) -> None:
    """Send the subscription's own initial snapshot before later updates."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "F1 Sensor entry not found")
        return
    if any(key not in DATA_PRODUCTS for key in msg["data_keys"]):
        connection.send_error(msg["id"], "unsupported_dataset", "Unsupported card data")
        return
    store = getattr(getattr(entry, "runtime_data", None), "card_data", None)
    if not isinstance(store, CardDataStore) or store.closed:
        connection.send_error(msg["id"], "not_loaded", "F1 Sensor data is not loaded")
        return
    stop = None

    @callback
    def unsubscribe() -> None:
        nonlocal stop
        if stop is not None:
            stop()
            stop = None

    @callback
    def send(payload: dict) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], payload))
        if payload["status"] == "closed":
            connection.subscriptions.pop(msg["id"], None)
            unsubscribe()

    connection.subscriptions[msg["id"]] = unsubscribe
    connection.send_result(msg["id"])
    stop = store.subscribe(msg["data_keys"], send)
