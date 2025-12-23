import asyncio

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import Entity

from .const import (
    CONF_OPERATION_MODE,
    DEFAULT_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
)


class F1BaseEntity(CoordinatorEntity):
    """Common base entity for F1 sensors."""

    def __init__(self, coordinator, name, unique_id, entry_id, device_name):
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._entry_id = entry_id
        self._device_name = device_name

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": self._device_name,
            "manufacturer": "Nicxe",
            "model": "F1 Sensor",
        }

    @property
    def available(self) -> bool:
        """Expose coordinator availability as entity availability.

        Many live-feed coordinators toggle `coordinator.available` via
        LiveAvailabilityTracker. When not available, entities should be
        `unavailable` instead of keeping stale values for days/weeks.
        """
        try:
            coord = getattr(self, "coordinator", None)
            if coord is not None and hasattr(coord, "available"):
                coord_available = bool(getattr(coord, "available"))

                # Additional guard: for live timing coordinators, only consider them
                # available when the integration's live_state says we are in a live
                # window (or when running in replay mode).
                #
                # This prevents sensors from staying available with restored/stale
                # values when the supervisor is idle or the upstream is quiet.
                try:
                    reg = (
                        (self.hass.data.get(DOMAIN, {}) if self.hass else {})
                        .get(self._entry_id, {})
                        or {}
                    )
                    operation_mode = reg.get(CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE)
                    live_state = reg.get("live_state")
                    is_live_window = (
                        bool(getattr(live_state, "is_live", False))
                        if live_state is not None
                        else None
                    )
                    if operation_mode != OPERATION_MODE_DEVELOPMENT and is_live_window is False:
                        return False

                    # If we're in a live window, require actual stream activity.
                    # If we have seen no activity at all, treat as offline.
                    if operation_mode != OPERATION_MODE_DEVELOPMENT and is_live_window is True:
                        bus = reg.get("live_bus")
                        activity_age = None
                        try:
                            if bus is not None:
                                activity_age = bus.last_stream_activity_age()
                        except Exception:
                            activity_age = None
                        if activity_age is None:
                            return False
                        # Treat prolonged inactivity as offline/unavailable.
                        # Heartbeat frames should keep this low during real sessions.
                        if activity_age > 90.0:
                            return False

                except Exception:
                    pass

                return coord_available
        except Exception:
            pass
        return super().available

    def _safe_write_ha_state(self, *_args) -> None:
        """Thread-safe request to write entity state.

        Some upstream libraries (e.g. SignalR clients) invoke callbacks from worker
        threads. Calling `async_write_ha_state` directly from those threads is not
        safe. This helper always schedules the write on Home Assistant's event loop.
        """
        hass = getattr(self, "hass", None)
        if hass is None:
            return

        try:
            loop = hass.loop
        except Exception:
            return

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        # `async_schedule_update_ha_state` is a @callback (not a coroutine) and will
        # perform the write on the loop safely.
        if running is loop:
            try:
                self.async_schedule_update_ha_state(False)
            except Exception:
                pass
            return

        try:
            loop.call_soon_threadsafe(self.async_schedule_update_ha_state, False)
        except Exception:
            pass


class F1AuxEntity(Entity):
    """Helper base for entities that do not use a coordinator but share device info."""

    def __init__(self, name: str, unique_id: str, entry_id: str, device_name: str):
        super().__init__()
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._entry_id = entry_id
        self._device_name = device_name

    def _safe_write_ha_state(self, *_args) -> None:
        """Thread-safe request to write entity state (see F1BaseEntity)."""
        hass = getattr(self, "hass", None)
        if hass is None:
            return

        try:
            loop = hass.loop
        except Exception:
            return

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if running is loop:
            try:
                self.async_schedule_update_ha_state(False)
            except Exception:
                pass
            return

        try:
            loop.call_soon_threadsafe(self.async_schedule_update_ha_state, False)
        except Exception:
            pass

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": self._device_name,
            "manufacturer": "Nicxe",
            "model": "F1 Sensor",
        }
