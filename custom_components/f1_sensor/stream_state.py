"""Entity-free shared availability and incremental stream transitions."""

from contextlib import suppress

from .const import (
    CONF_OPERATION_MODE,
    DEFAULT_OPERATION_MODE,
    OPERATION_MODE_DEVELOPMENT,
)


class StreamStateMixin:
    """Use the same stream guards in runtime models and visible entities."""

    @property
    def available(self) -> bool:
        """Expose coordinator availability as entity availability.

        Many live-feed coordinators toggle `coordinator.available` via
        LiveAvailabilityTracker. When not available, entities should be
        `unavailable` instead of keeping stale values for days/weeks.
        """
        from .entity import entry_runtime_registry, is_no_spoiler_live_state

        with suppress(Exception):
            coord = getattr(self, "coordinator", None)
            if coord is not None and hasattr(coord, "available"):
                coord_available = bool(coord.available)

                # Additional guard: for live timing coordinators, only consider them
                # available when the integration's live_state says we are in a live
                # window (or when running in replay mode).
                #
                # This prevents sensors from staying available with restored/stale
                # values when the supervisor is idle or the upstream is quiet.
                with suppress(Exception):
                    reg = entry_runtime_registry(self.hass, self._entry_id)
                    operation_mode = reg.get(
                        CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE
                    )
                    live_state = reg.get("live_state")
                    is_live_window = (
                        bool(getattr(live_state, "is_live", False))
                        if live_state is not None
                        else None
                    )
                    live_reason = (
                        getattr(live_state, "reason", None)
                        if live_state is not None
                        else None
                    )
                    if (
                        operation_mode != OPERATION_MODE_DEVELOPMENT
                        and is_live_window is False
                        and not is_no_spoiler_live_state(live_reason)
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
        return bool(getattr(self.coordinator, "last_update_success", True))

    def _is_stream_active(self) -> bool:
        from .entity import entry_runtime_registry

        reg = entry_runtime_registry(self.hass, self._entry_id)
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
