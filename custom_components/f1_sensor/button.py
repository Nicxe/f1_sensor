from __future__ import annotations

import logging

from homeassistant.components import persistent_notification
from inspect import isawaitable
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .entity import F1AuxEntity
from .calibration import LiveDelayCalibrationManager

_LOGGER = logging.getLogger(__name__)


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
    entity = F1MatchDelayButton(
        manager,
        f"{name} match live delay",
        f"{entry.entry_id}_delay_calibration_match",
        entry.entry_id,
        name,
    )
    async_add_entities([entity])


class F1MatchDelayButton(F1AuxEntity, ButtonEntity):
    """Button that captures the elapsed calibration time and applies it."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        manager: LiveDelayCalibrationManager,
        sensor_name: str,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, sensor_name, unique_id, entry_id, device_name)
        ButtonEntity.__init__(self)
        self._manager = manager
        self._attr_icon = "mdi:check"

    async def async_press(self) -> None:
        try:
            await self._manager.async_complete(source="button")
        except RuntimeError as err:  # noqa: BLE001
            _LOGGER.debug("Calibration button press ignored: %s", err)
            if self.hass:
                snapshot = {}
                try:
                    snapshot = self._manager.snapshot() or {}
                except Exception:  # noqa: BLE001
                    snapshot = {}
                mode = str(snapshot.get("mode") or "idle")
                if mode == "waiting":
                    message = (
                        "Calibration is enabled, but the timer hasn't started yet.\n\n"
                        "This usually means no session has gone live yet. Wait until the "
                        "session is running, then press `Match live delay` when your TV feed "
                        "has caught up."
                    )
                elif mode == "idle":
                    message = (
                        "Calibration is not enabled.\n\n"
                        "Turn on the calibration switch before pressing `Match live delay`, "
                        "otherwise no value will be saved."
                    )
                else:
                    detail = snapshot.get("message")
                    detail_line = f"\n\nDetail: {detail}" if detail else ""
                    message = (
                        "Can't match live delay right now.\n\n"
                        "The calibration timer must be running to save a value."
                        f"{detail_line}"
                    )
                result = persistent_notification.async_create(
                    self.hass,
                    message,
                    title="F1 live delay",
                    notification_id=f"{DOMAIN}_delay_calibration_warning",
                )
                if isawaitable(result):
                    await result
