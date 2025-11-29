from __future__ import annotations

import asyncio

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class F1BaseEntity(CoordinatorEntity):
    """
    Base entity shared by all F1 Sensor integration entities.

    Provides:
    - Stable device registry information
    - Safe HA state updates (avoids cross-thread/loop errors)
    """

    def __init__(
        self,
        coordinator: CoordinatorEntity,
        name: str,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        """
        Initialize the base entity.

        Parameters
        ----------
        coordinator : CoordinatorEntity
            The data update coordinator used by this entity.
        name : str
            Display name of the entity.
        unique_id : str
            Unique identifier for this entity instance.
        entry_id : str
            Config entry ID associated with this entity.
        device_name : str
            Label used for grouping entities under a shared device.
        """
        super().__init__(coordinator)

        self._attr_name = name
        self._attr_unique_id = unique_id

        self._entry_id = entry_id
        self._device_name = device_name

    @property
    def device_info(self) -> dict[str, object]:
        """
        Provide device registry information.

        Returns
        -------
        dict[str, object]
            Device metadata for Home Assistant.
        """
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": self._device_name,
            "manufacturer": "Nicxe",
            "model": "F1 Sensor",
        }

    def _safe_write_ha_state(self) -> None:
        """
        Safely write the entity state to Home Assistant.

        Automatically detects whether it's running inside the Home Assistant
        event loop and chooses the appropriate update method.

        Ensures:
        - No cross-thread event-loop errors
        - Always attempts a fallback update
        """
        try:
            running_loop = None
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

            if running_loop is self.hass.loop:
                self.async_write_ha_state()
            else:
                self.schedule_update_ha_state()

        except Exception as exc:
            # Fallback for unexpected failures — still try to schedule update
            try:
                self.schedule_update_ha_state()
            except Exception:
                # Final fail-safe: swallow the error, avoid recursion
                self.hass.logger.warning(
                    "State update failed in F1BaseEntity: %s", exc
                )
