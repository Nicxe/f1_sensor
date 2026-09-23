"""WebSocket discovery API for bundled dashboard cards."""

from __future__ import annotations

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import voluptuous as vol

from .const import DOMAIN

ENTITY_MAP_WS_MARKER = "__entity_map_ws_registered__"
ENTITY_MAP_WS_TYPE = f"{DOMAIN}/entities"


def async_register_entity_map_websocket(hass: HomeAssistant) -> None:
    """Register the card entity-discovery command exactly once."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get(ENTITY_MAP_WS_MARKER):
        return
    websocket_api.async_register_command(hass, _ws_get_entity_map)
    root[ENTITY_MAP_WS_MARKER] = True


@websocket_api.websocket_command({vol.Required("type"): ENTITY_MAP_WS_TYPE})
@websocket_api.async_response
async def _ws_get_entity_map(
    hass: HomeAssistant,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    """Return entity IDs grouped by their F1 Sensor config entry."""
    registry = er.async_get(hass)
    # This switch belongs to one entry in the registry but protects all entries.
    # Discover by stable identity so renamed entities remain safe for cards.
    spoiler_entity_id = registry.async_get_entity_id(
        "switch", DOMAIN, "f1_sensor_no_spoiler_mode"
    )
    global_entities = (
        {"no_spoiler_mode": spoiler_entity_id} if spoiler_entity_id else {}
    )
    result: list[dict[str, Any]] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        prefix = f"{entry.entry_id}_"
        entities: dict[str, str] = {}
        disabled_entities: list[str] = []
        for registry_entry in er.async_entries_for_config_entry(
            registry, entry.entry_id
        ):
            unique_id = registry_entry.unique_id
            if not unique_id.startswith(prefix):
                continue
            suffix = unique_id.removeprefix(prefix)
            entities[suffix] = registry_entry.entity_id
            if registry_entry.disabled_by is not None:
                disabled_entities.append(suffix)
        result.append(
            {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "entities": dict(sorted(entities.items())),
                "global_entities": global_entities,
                "disabled_entities": sorted(disabled_entities),
            }
        )
    connection.send_result(msg["id"], result)
