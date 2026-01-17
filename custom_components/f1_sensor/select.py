"""Select platform for F1 Sensor."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.components.select import SelectEntity

from .const import (
    DOMAIN,
    LIVE_DELAY_REFERENCE_FORMATION,
    LIVE_DELAY_REFERENCE_SESSION,
)
from .entity import F1AuxEntity
from .live_delay import LiveDelayReferenceController
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

    reference_controller: LiveDelayReferenceController | None = registry.get(
        "delay_reference_controller"
    )
    if reference_controller is not None:
        entities.append(
            F1LiveDelayReferenceSelect(
                reference_controller,
                f"{name} live delay reference",
                f"{entry.entry_id}_live_delay_reference",
                entry.entry_id,
                name,
            )
        )

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


class F1LiveDelayReferenceSelect(F1AuxEntity, SelectEntity):
    """Select entity to choose the live delay calibration reference."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-sync"

    def __init__(
        self,
        controller: LiveDelayReferenceController,
        sensor_name: str,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, sensor_name, unique_id, entry_id, device_name)
        SelectEntity.__init__(self)
        self._controller = controller
        self._unsub = controller.add_listener(self._handle_reference_update)
        self._option_to_value = {
            "Session live": LIVE_DELAY_REFERENCE_SESSION,
            "Formation start (race/sprint)": LIVE_DELAY_REFERENCE_FORMATION,
        }
        self._value_to_option = {v: k for k, v in self._option_to_value.items()}
        self._current_option = self._value_to_option.get(
            controller.current, "Session live"
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            try:
                self._unsub()
            except Exception:  # noqa: BLE001
                pass
            self._unsub = None

    @property
    def options(self) -> list[str]:
        return list(self._option_to_value.keys())

    @property
    def current_option(self) -> str | None:
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        value = self._option_to_value.get(option, LIVE_DELAY_REFERENCE_SESSION)
        await self._controller.async_set_reference(value, source="select_entity")

    def _handle_reference_update(self, value: str) -> None:
        self._current_option = self._value_to_option.get(value, "Session live")
        if self.hass:
            self.async_write_ha_state()
