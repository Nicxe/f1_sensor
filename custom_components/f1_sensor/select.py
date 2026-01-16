"""Select platform for F1 Sensor."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .replay_entities import F1ReplaySessionSelect

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up F1 Sensor select entities."""
    registry = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not registry:
        return

    name = entry.data.get("sensor_name", "F1")
    entities = []

    # Replay session selector
    replay_controller = registry.get("replay_controller")
    if replay_controller is not None:
        entities.append(
            F1ReplaySessionSelect(
                replay_controller,
                f"{name} Replay Session",
                f"{entry.entry_id}_replay_session_select",
                entry.entry_id,
                name,
            )
        )

    if entities:
        async_add_entities(entities)
        _LOGGER.debug("Added %d select entities for F1 Sensor", len(entities))
