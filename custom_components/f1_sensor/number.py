from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .calibration import LiveDelayCalibrationManager
from .entity import (
    F1AuxEntity,
    default_object_id,
    entry_runtime_registry,
    set_default_entity_id,
)
from .live_delay import LiveDelayController
from .replay_mode import ReplayController
from .runtime import F1ConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: F1ConfigEntry, async_add_entities
) -> None:
    registry = entry_runtime_registry(hass, entry.entry_id)
    if not registry:
        return
    controller: LiveDelayController | None = registry.get("live_delay_controller")
    calibration: LiveDelayCalibrationManager | None = registry.get(
        "calibration_manager"
    )
    name = entry.data.get("sensor_name", "F1")
    entities: list[NumberEntity] = []
    if controller is not None:
        entity = F1LiveDelayNumber(
            controller=controller,
            calibration=calibration,
            unique_id=f"{entry.entry_id}_live_delay_number",
            entry_id=entry.entry_id,
            device_name=name,
        )
        set_default_entity_id(entity, Platform.NUMBER, default_object_id("live_delay"))
        entities.append(entity)

    replay_controller: ReplayController | None = registry.get("replay_controller")
    if replay_controller is not None:
        entity = F1ReplayLapNumber(
            controller=replay_controller,
            unique_id=f"{entry.entry_id}_replay_lap_number",
            entry_id=entry.entry_id,
            device_name=name,
        )
        set_default_entity_id(entity, Platform.NUMBER, default_object_id("replay_lap"))
        entities.append(entity)

    if entities:
        async_add_entities(entities)


class F1LiveDelayNumber(F1AuxEntity, NumberEntity):
    """Configurable number entity that mirrors the calibrated live delay."""

    _device_category = "system"
    _attr_native_min_value = 0
    _attr_native_max_value = 300
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "live_delay"

    def __init__(
        self,
        controller: LiveDelayController,
        calibration: LiveDelayCalibrationManager | None,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
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
            "calibration_idle_reason": snapshot.get("idle_reason"),
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


class F1ReplayLapNumber(F1AuxEntity, NumberEntity):
    """Number entity used to choose a replay lap to seek to."""

    _device_category = "system"
    _attr_native_min_value = 1
    _attr_native_max_value = 200
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "replay_lap"
    _attr_icon = "mdi:counter"

    def __init__(
        self,
        controller: ReplayController,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
        NumberEntity.__init__(self)
        self._controller = controller
        self._attr_native_value = controller.lap_target

    async def async_set_native_value(self, value: float) -> None:
        target = max(int(self._attr_native_min_value), int(round(value)))
        self._controller.set_lap_target(target)
        self._attr_native_value = target
        self.async_write_ha_state()
