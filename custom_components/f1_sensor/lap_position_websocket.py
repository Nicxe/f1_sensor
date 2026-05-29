"""WebSocket API for F1 lap position progression session payloads."""

from __future__ import annotations

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_registry as er
import voluptuous as vol

from .const import DOMAIN

LAP_POSITION_WS_MARKER = "__lap_position_ws_registered__"
LAP_POSITION_WS_SESSION_TYPE = f"{DOMAIN}/lap_position/session"


def async_register_lap_position_websocket(hass: HomeAssistant) -> None:
    """Register lap position WebSocket commands once per Home Assistant runtime."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get(LAP_POSITION_WS_MARKER):
        return
    websocket_api.async_register_command(hass, _ws_get_lap_position_session)
    root[LAP_POSITION_WS_MARKER] = True


@websocket_api.websocket_command(
    {
        vol.Required("type"): LAP_POSITION_WS_SESSION_TYPE,
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("session_key"): vol.All(str, vol.Length(min=1)),
    }
)
@websocket_api.async_response
async def _ws_get_lap_position_session(
    hass: HomeAssistant,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    """Return chart-ready lap position data for one selected session."""
    entity_id = msg["entity_id"]
    coordinator = _resolve_lap_position_coordinator(hass, entity_id)
    if coordinator is None:
        connection.send_error(
            msg["id"],
            "not_found",
            "Lap position progression data is not available for this entity",
        )
        return

    result = await coordinator.async_get_session(msg["session_key"])
    connection.send_result(msg["id"], result)


def _resolve_lap_position_coordinator(
    hass: HomeAssistant,
    entity_id: str,
) -> Any | None:
    root = hass.data.get(DOMAIN)
    if not isinstance(root, dict):
        return None

    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry is not None and entry.config_entry_id:
        data = root.get(entry.config_entry_id)
        if isinstance(data, dict):
            return data.get("lap_position_progression_coordinator")

    candidates = [
        data.get("lap_position_progression_coordinator")
        for data in root.values()
        if isinstance(data, dict) and data.get("lap_position_progression_coordinator")
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None
