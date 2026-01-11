from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta
from inspect import isawaitable
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .live_delay import LiveDelayController
from .signalr import LiveBus

_LOGGER = logging.getLogger(__name__)


class LiveDelayCalibrationManager:
    """Coordinates the timer-based calibration workflow."""

    def __init__(
        self,
        hass: HomeAssistant,
        controller: LiveDelayController,
        *,
        bus: LiveBus | None = None,
        timeout_seconds: int = 120,
        reload_callback: Callable[[], None] | None = None,
    ) -> None:
        self._hass = hass
        self._controller = controller
        self._bus = bus
        self._timeout_seconds = max(5, int(timeout_seconds))
        self._reload_cb = reload_callback
        self._state = self._initial_state()
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._tick_handle: asyncio.Handle | None = None
        self._timeout_handle: asyncio.Handle | None = None
        self._session_unsub: Callable[[], None] | None = None
        self._last_session_payload: dict | None = None
        if self._bus is not None:
            try:
                self._session_unsub = self._bus.subscribe(
                    "SessionStatus", self._handle_session_status
                )
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Calibration manager failed to subscribe to SessionStatus")

    def snapshot(self) -> dict[str, Any]:
        return self._serialize_state()

    async def async_close(self) -> None:
        self._cancel_handles()
        if self._session_unsub:
            try:
                self._session_unsub()
            except Exception:  # noqa: BLE001
                pass
            self._session_unsub = None

    async def async_prepare(self, *, source: str = "button") -> dict[str, Any]:
        """Arm calibration and wait for session start."""
        _LOGGER.debug("Calibration prepare triggered by %s", source)
        self._cancel_handles()
        now = dt_util.utcnow()
        self._state.update(
            {
                "mode": "waiting",
                "waiting_since": now,
                "started_at": None,
                "elapsed": 0.0,
                "timeout_at": None,
                "message": "Waiting for SessionStatus to report 'Started'.",
            }
        )
        self._notify_listeners()
        if self._is_session_live(self._last_session_payload):
            self._start_timer(reason="session_already_live")
        return self.snapshot()

    async def async_complete(self, *, source: str = "button") -> dict[str, Any]:
        """Commit the measured delay."""
        if self._state["mode"] != "running":
            raise RuntimeError("Calibration timer is not running")
        elapsed = self._compute_elapsed()
        seconds = int(round(elapsed))
        seconds = max(0, min(300, seconds))
        await self._controller.async_set_delay(seconds, source="calibration")
        self._state["last_result"] = {
            "seconds": seconds,
            "completed_at": dt_util.utcnow(),
            "source": source,
        }
        message = f"Live delay updated to {seconds} seconds."
        self._transition_to_idle(message)
        self._notify_user("F1 live delay calibrated", message)
        self._notify_listeners()
        if self._reload_cb:
            try:
                self._reload_cb()
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Failed to schedule reload after calibration", exc_info=True)
        return self.snapshot()

    async def async_cancel(self, *, source: str = "button") -> dict[str, Any]:
        """Abort the calibration flow."""
        self._transition_to_idle("Calibration cancelled.")
        self._notify_listeners()
        if source == "timeout":
            self._notify_user(
                "F1 live delay",
                "Calibration timed out after 2 minutes without changing the delay.",
            )
        return self.snapshot()

    def add_listener(self, listener: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        try:
            listener(self.snapshot())
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Calibration listener raised during sync", exc_info=True)

        @callback
        def _remove() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return _remove

    # Internal helpers -----------------------------------------------------

    def _handle_session_status(self, payload: dict) -> None:
        self._last_session_payload = payload
        if self._state["mode"] == "waiting" and self._is_session_live(payload):
            self._start_timer(reason="session_status_live")
        elif self._state["mode"] == "running" and self._is_session_finished(payload):
            self._transition_to_idle("Sessionen avslutades – kalibreringen stoppades.")
            self._notify_listeners()

    def _start_timer(self, *, reason: str) -> None:
        start = dt_util.utcnow()
        self._state.update(
            {
                "mode": "running",
                "waiting_since": None,
                "started_at": start,
                "elapsed": 0.0,
                "timeout_at": start + timedelta(seconds=self._timeout_seconds),
                "message": "Calibration running – press 'Match live delay' when TV catches up.",
            }
        )
        _LOGGER.debug("Calibration timer started (%s)", reason)
        self._schedule_tick()
        self._schedule_timeout()
        self._notify_listeners()

    def _compute_elapsed(self) -> float:
        started_at = self._state.get("started_at")
        if not started_at:
            return 0.0
        now = dt_util.utcnow()
        return max(0.0, (now - started_at).total_seconds())

    def _schedule_tick(self) -> None:
        self._cancel_tick()
        loop = self._hass.loop
        self._tick_handle = loop.call_later(1, self._on_tick)

    def _cancel_tick(self) -> None:
        if self._tick_handle:
            try:
                self._tick_handle.cancel()
            except Exception:  # noqa: BLE001
                pass
            self._tick_handle = None

    def _on_tick(self) -> None:
        if self._state["mode"] != "running":
            return
        self._state["elapsed"] = self._compute_elapsed()
        self._notify_listeners()
        self._schedule_tick()

    def _schedule_timeout(self) -> None:
        self._cancel_timeout()
        loop = self._hass.loop
        self._timeout_handle = loop.call_later(self._timeout_seconds, self._on_timeout)

    def _cancel_timeout(self) -> None:
        if self._timeout_handle:
            try:
                self._timeout_handle.cancel()
            except Exception:  # noqa: BLE001
                pass
            self._timeout_handle = None

    def _on_timeout(self) -> None:
        self._timeout_handle = None
        if self._state["mode"] != "running":
            return
        _LOGGER.debug("Calibration timed out")
        self._hass.async_create_task(self.async_cancel(source="timeout"))

    def _transition_to_idle(self, message: str | None) -> None:
        self._cancel_handles()
        self._state.update(
            {
                "mode": "idle",
                "waiting_since": None,
                "started_at": None,
                "elapsed": 0.0,
                "timeout_at": None,
                "message": message,
            }
        )

    def _cancel_handles(self) -> None:
        self._cancel_tick()
        self._cancel_timeout()

    def _is_session_live(self, payload: dict | None) -> bool:
        if not isinstance(payload, dict):
            return False
        message = str(payload.get("Status") or payload.get("Message") or "").strip()
        started = payload.get("Started")
        if str(started).lower() in ("started", "true"):
            return True
        return message in {"Started", "Green", "GreenFlag"}

    def _is_session_finished(self, payload: dict | None) -> bool:
        if not isinstance(payload, dict):
            return False
        message = str(payload.get("Status") or payload.get("Message") or "").strip()
        return message in {"Finished", "Finalised", "Ends"}

    def _initial_state(self) -> dict[str, Any]:
        return {
            "mode": "idle",
            "waiting_since": None,
            "started_at": None,
            "elapsed": 0.0,
            "timeout_at": None,
            "message": None,
            "last_result": None,
        }

    def _serialize_state(self) -> dict[str, Any]:
        def _fmt(value):
            if value is None:
                return None
            try:
                return value.isoformat(timespec="seconds")
            except AttributeError:
                return value

        state = dict(self._state)
        state["waiting_since"] = _fmt(state.get("waiting_since"))
        state["started_at"] = _fmt(state.get("started_at"))
        state["timeout_at"] = _fmt(state.get("timeout_at"))
        last = state.get("last_result")
        if isinstance(last, dict):
            last_copy = dict(last)
            last_copy["completed_at"] = _fmt(last_copy.get("completed_at"))
            state["last_result"] = last_copy
        return state

    def _notify_listeners(self) -> None:
        snapshot = self._serialize_state()
        for listener in list(self._listeners):
            try:
                listener(snapshot)
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Calibration listener raised", exc_info=True)

    def _notify_user(self, title: str, message: str) -> None:
        # Home Assistant's persistent_notification helper has changed over time:
        # in some versions async_create() returns a coroutine, in others it returns None.
        # Never pass None into hass.async_create_task().
        result = persistent_notification.async_create(
            self._hass,
            message,
            title=title,
            notification_id=f"{DOMAIN}_delay_calibration",
        )
        if isawaitable(result):
            self._hass.async_create_task(result)
