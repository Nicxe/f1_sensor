from __future__ import annotations
from contextlib import suppress

from typing import Any, Callable

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.entity import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .entity import F1AuxEntity
from .calibration import LiveDelayCalibrationManager
from .live_delay import LiveDelayController


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    registry = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not registry:
        return
    controller: LiveDelayController | None = registry.get("live_delay_controller")
    calibration: LiveDelayCalibrationManager | None = registry.get(
        "calibration_manager"
    )
    if controller is None:
        return
    entity = F1LiveDelayNumber(
        controller=controller,
        calibration=calibration,
        sensor_name=f"{entry.data.get('sensor_name', 'F1')} live delay",
        unique_id=f"{entry.entry_id}_live_delay_number",
        entry_id=entry.entry_id,
        device_name=entry.data.get("sensor_name", "F1"),
    )
    async_add_entities([entity])


class F1LiveDelayNumber(F1AuxEntity, NumberEntity):
    """Configurable number entity that mirrors the calibrated live delay."""

    _attr_native_min_value = 0
    _attr_native_max_value = 300
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        controller: LiveDelayController,
        calibration: LiveDelayCalibrationManager | None,
        sensor_name: str,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, sensor_name, unique_id, entry_id, device_name)
        NumberEntity.__init__(self)
        self._controller = controller
        self._attr_native_value = controller.current
        self._attr_extra_state_attributes: dict[str, Any] = {}
        self._controller_unsub: Callable[[], None] | None = controller.add_listener(
            self._handle_delay_update
        )
        self._calibration_unsub: Callable[[], None] | None = None
        if calibration:
            self._calibration_unsub = calibration.add_listener(
                self._handle_calibration_update
            )

    async def async_will_remove_from_hass(self) -> None:
        if self._controller_unsub:
            with suppress(Exception):
                self._controller_unsub()
            self._controller_unsub = None
        if self._calibration_unsub:
            with suppress(Exception):
                self._calibration_unsub()
            self._calibration_unsub = None

    async def async_set_native_value(self, value: float) -> None:
        await self._controller.async_set_delay(
            int(round(value)), source="number_entity"
        )

    def _handle_delay_update(self, new_value: int) -> None:
        if self._attr_native_value == new_value:
            return
        self._attr_native_value = new_value
        if self.hass:
            self.async_write_ha_state()

    def _handle_calibration_update(self, snapshot: dict[str, Any]) -> None:
        self._attr_extra_state_attributes = {
            "calibration_mode": snapshot.get("mode"),
            "calibration_reference": snapshot.get("reference"),
            "calibration_waiting_since": snapshot.get("waiting_since"),
            "calibration_started_at": snapshot.get("started_at"),
            "calibration_elapsed": round(snapshot.get("elapsed", 0.0), 1),
            "calibration_timeout_at": snapshot.get("timeout_at"),
            "calibration_last_result": snapshot.get("last_result"),
            "calibration_message": snapshot.get("message"),
        }
        if self.hass:
            self.async_write_ha_state()
