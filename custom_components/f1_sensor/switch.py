from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .calibration import LiveDelayCalibrationManager
from .const import DOMAIN
from .entity import F1AuxEntity
from .no_spoiler import NoSpoilerModeManager

_NO_SPOILER_SWITCH_ENTRY_KEY = "no_spoiler_switch_entry_id"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    registry = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not registry:
        return

    entities: list[SwitchEntity] = []

    # Calibration switch (per-entry)
    manager: LiveDelayCalibrationManager | None = registry.get("calibration_manager")
    if manager is not None:
        name = entry.data.get("sensor_name", "F1")
        entities.append(
            F1DelayCalibrationSwitch(
                manager,
                f"{entry.entry_id}_delay_calibration_switch",
                entry.entry_id,
                name,
            )
        )

    # No Spoiler Mode switch — global, registered only by the first entry that loads.
    domain_root = hass.data.setdefault(DOMAIN, {})
    no_spoiler_mgr: NoSpoilerModeManager | None = domain_root.get("no_spoiler_manager")
    if no_spoiler_mgr is not None and not domain_root.get(_NO_SPOILER_SWITCH_ENTRY_KEY):
        domain_root[_NO_SPOILER_SWITCH_ENTRY_KEY] = entry.entry_id
        name = entry.data.get("sensor_name", "F1")
        entities.append(
            F1NoSpoilerSwitch(
                no_spoiler_mgr,
                "f1_sensor_no_spoiler_mode",
                entry.entry_id,
                name,
            )
        )

    if entities:
        async_add_entities(entities)


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


class F1NoSpoilerSwitch(F1AuxEntity, SwitchEntity):
    """Global switch that activates No Spoiler Mode across all f1_sensor entries.

    When on, all spoiler-sensitive coordinators stop delivering new data to
    entities.  Turning it off triggers an immediate catch-up refresh.
    """

    _device_category = "system"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "no_spoiler_mode"

    def __init__(
        self,
        manager: NoSpoilerModeManager,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
        SwitchEntity.__init__(self)
        self._manager = manager
        self._is_on = manager.is_active
        self._unsub: Callable[[], None] | None = manager.add_listener(
            self._handle_state_change
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            with suppress(Exception):
                self._unsub()
            self._unsub = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._manager.async_set_active(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._manager.async_set_active(False)

    @property
    def is_on(self) -> bool:
        return self._is_on

    def _handle_state_change(self, active: bool) -> None:
        self._is_on = active
        if self.hass:
            self.async_write_ha_state()
