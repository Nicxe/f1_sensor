from __future__ import annotations
from contextlib import suppress

from typing import Any, Callable

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .entity import F1AuxEntity
from .calibration import LiveDelayCalibrationManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    registry = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not registry:
        return
    manager: LiveDelayCalibrationManager | None = registry.get("calibration_manager")
    if manager is None:
        return
    name = entry.data.get("sensor_name", "F1")
    entity = F1DelayCalibrationSwitch(
        manager,
        f"{entry.entry_id}_delay_calibration_switch",
        entry.entry_id,
        name,
    )
    async_add_entities([entity])


class F1DelayCalibrationSwitch(F1AuxEntity, SwitchEntity):
    """Toggle to arm/cancel the live delay calibration workflow."""

    _device_category = "system"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "delay_calibration"

    def __init__(
        self,
        manager: LiveDelayCalibrationManager,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
        SwitchEntity.__init__(self)
        self._manager = manager
        self._is_on = False
        self._attrs: dict[str, Any] = {}
        self._unsub: Callable[[], None] | None = manager.add_listener(
            self._handle_snapshot
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            with suppress(Exception):
                self._unsub()
            self._unsub = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._manager.async_prepare(source="switch")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._manager.async_cancel(source="switch")

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._attrs

    def _handle_snapshot(self, snapshot: dict[str, Any]) -> None:
        mode = snapshot.get("mode")
        next_state = mode in {"waiting", "running"}
        attrs = {
            "mode": mode,
            "reference": snapshot.get("reference"),
            "message": snapshot.get("message"),
            "waiting_since": snapshot.get("waiting_since"),
            "started_at": snapshot.get("started_at"),
            "elapsed": snapshot.get("elapsed"),
            "timeout_at": snapshot.get("timeout_at"),
            "recorded_lap": snapshot.get("recorded_lap"),
        }
        self._attrs = attrs
        changed = next_state != self._is_on
        self._is_on = next_state
        if self.hass and (changed or self._attrs):
            self.async_write_ha_state()
