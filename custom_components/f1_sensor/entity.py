from contextlib import suppress
import asyncio

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import Entity

from .const import (
    CONF_OPERATION_MODE,
    DEFAULT_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
)


def _safe_write_ha_state(entity: Entity) -> None:
    """Thread-safe request to write entity state."""
    hass = getattr(entity, "hass", None)
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
        with suppress(Exception):
            entity.async_schedule_update_ha_state(False)
        return

    with suppress(Exception):
        loop.call_soon_threadsafe(entity.async_schedule_update_ha_state, False)


class F1BaseEntity(CoordinatorEntity):
    """Common base entity for F1 sensors."""

    def __init__(self, coordinator, name, unique_id, entry_id, device_name):
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._entry_id = entry_id
        self._device_name = device_name
        self._stream_last_active: bool | None = None

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
        with suppress(Exception):
            coord = getattr(self, "coordinator", None)
            if coord is not None and hasattr(coord, "available"):
                coord_available = bool(getattr(coord, "available"))

                # Additional guard: for live timing coordinators, only consider them
                # available when the integration's live_state says we are in a live
                # window (or when running in replay mode).
                #
                # This prevents sensors from staying available with restored/stale
                # values when the supervisor is idle or the upstream is quiet.
                with suppress(Exception):
                    reg = (self.hass.data.get(DOMAIN, {}) if self.hass else {}).get(
                        self._entry_id, {}
                    ) or {}
                    operation_mode = reg.get(
                        CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE
                    )
                    live_state = reg.get("live_state")
                    is_live_window = (
                        bool(getattr(live_state, "is_live", False))
                        if live_state is not None
                        else None
                    )
                    if (
                        operation_mode != OPERATION_MODE_DEVELOPMENT
                        and is_live_window is False
                    ):
                        return False

                    # Check if replay mode is active - skip activity check during replay
                    # since activity timestamps are cleared during transport swap
                    replay_controller = reg.get("replay_controller")
                    replay_active = False
                    if replay_controller is not None:
                        with suppress(Exception):
                            from .replay_mode import ReplayState

                            replay_active = replay_controller.state in (
                                ReplayState.PLAYING,
                                ReplayState.PAUSED,
                            )

                    # If we're in a live window, require actual stream activity.
                    # If we have seen no activity at all, treat as offline.
                    # Skip this check during replay mode since activity timestamps
                    # are reset when swapping transports.
                    if (
                        operation_mode != OPERATION_MODE_DEVELOPMENT
                        and is_live_window is True
                        and not replay_active
                    ):
                        bus = reg.get("live_bus")
                        activity_age = None
                        with suppress(Exception):
                            if bus is not None:
                                activity_age = bus.last_stream_activity_age()
                        if activity_age is None:
                            return False
                        # Treat prolonged inactivity as offline/unavailable.
                        # Heartbeat frames should keep this low during real sessions.
                        if activity_age > 90.0:
                            return False

                return coord_available
        return super().available

    def _safe_write_ha_state(self, *_args) -> None:
        """Thread-safe request to write entity state.

        Some upstream libraries (e.g. SignalR clients) invoke callbacks from worker
        threads. Calling `async_write_ha_state` directly from those threads is not
        safe. This helper always schedules the write on Home Assistant's event loop.
        """
        _safe_write_ha_state(self)

    def _is_stream_active(self) -> bool:
        reg = (self.hass.data.get(DOMAIN, {}) if self.hass else {}).get(
            self._entry_id, {}
        ) or {}
        live_state = reg.get("live_state")
        if live_state is not None and bool(getattr(live_state, "is_live", False)):
            return True
        replay_controller = reg.get("replay_controller")
        if replay_controller is not None:
            try:
                from .replay_mode import ReplayState

                return replay_controller.state in (
                    ReplayState.PLAYING,
                    ReplayState.PAUSED,
                )
            except Exception:
                return False
        return False

    def _clear_state_if_possible(self) -> None:
        clear = getattr(self, "_clear_state", None)
        if callable(clear):
            with suppress(Exception):
                clear()

    def _handle_stream_state(self, updated: bool) -> bool:
        """Handle live/replay stream inactivity and transitions.

        Returns True when state should be written (updated or cleared).
        """
        stream_active = self._is_stream_active()
        if not updated:
            if not stream_active:
                self._clear_state_if_possible()
                self._stream_last_active = stream_active
                return True
            return False

        if self._stream_last_active is None:
            self._stream_last_active = stream_active
        elif self._stream_last_active is True and stream_active is False:
            self._clear_state_if_possible()
            self._stream_last_active = stream_active
            return True

        self._stream_last_active = stream_active
        if not stream_active:
            self._clear_state_if_possible()
            return True
        return True


class F1AuxEntity(Entity):
    """Helper base for entities that do not use a coordinator but share device info."""

    def __init__(self, name: str, unique_id: str, entry_id: str, device_name: str):
        super().__init__()
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._entry_id = entry_id
        self._device_name = device_name
        self._stream_last_active: bool | None = None

    def _safe_write_ha_state(self, *_args) -> None:
        """Thread-safe request to write entity state (see F1BaseEntity)."""
        _safe_write_ha_state(self)

    def _is_stream_active(self) -> bool:
        reg = (self.hass.data.get(DOMAIN, {}) if self.hass else {}).get(
            self._entry_id, {}
        ) or {}
        live_state = reg.get("live_state")
        if live_state is not None and bool(getattr(live_state, "is_live", False)):
            return True
        replay_controller = reg.get("replay_controller")
        if replay_controller is not None:
            try:
                from .replay_mode import ReplayState

                return replay_controller.state in (
                    ReplayState.PLAYING,
                    ReplayState.PAUSED,
                )
            except Exception:
                return False
        return False

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": self._device_name,
            "manufacturer": "Nicxe",
            "model": "F1 Sensor",
        }
