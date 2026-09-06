"""Behavior tests for live-delay calibration workflows."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.f1_sensor import calibration
from custom_components.f1_sensor.calibration import LiveDelayCalibrationManager
from custom_components.f1_sensor.const import (
    LIVE_DELAY_REFERENCE_FORMATION,
    LIVE_DELAY_REFERENCE_LAP_SYNC,
    LIVE_DELAY_REFERENCE_SESSION,
)
from custom_components.f1_sensor.replay_mode import ReplayState


class _Bus:
    def __init__(self, *, fail_stream: str | None = None) -> None:
        self.fail_stream = fail_stream
        self.callbacks = {}
        self.removed = []

    def subscribe(self, stream, callback):
        if stream == self.fail_stream:
            raise RuntimeError("subscription failed")
        self.callbacks[stream] = callback

        def remove():
            self.removed.append(stream)

        return remove


class _ReferenceController:
    def __init__(self) -> None:
        self.callback = None
        self.removed = False

    def add_listener(self, callback):
        self.callback = callback

        def remove():
            self.removed = True

        return remove


class _FormationTracker:
    def __init__(self) -> None:
        self.callback = None
        self.formation_start_utc = None
        self._session_type = "Race"
        self._session_name = "Race"

    def add_listener(self, callback):
        self.callback = callback
        return Mock()


def _manager(hass, **kwargs):
    controller = SimpleNamespace(async_set_delay=AsyncMock())
    manager = LiveDelayCalibrationManager(hass, controller, **kwargs)
    manager._notify_user = Mock()
    return manager, controller


async def test_session_reference_prepare_complete_and_listener_lifecycle(
    hass, monkeypatch
) -> None:
    fixed = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(calibration.dt_util, "utcnow", lambda: fixed)
    bus = _Bus()
    reference = _ReferenceController()
    reload_callback = Mock(side_effect=RuntimeError("reload failed"))
    manager, controller = _manager(
        hass,
        bus=bus,
        reference_controller=reference,
        reload_callback=reload_callback,
        timeout_seconds=1,
    )
    manager._schedule_tick = Mock()
    manager._schedule_timeout = Mock()
    snapshots = []
    remove_listener = manager.add_listener(snapshots.append)
    manager.add_listener(Mock(side_effect=RuntimeError("listener failed")))

    waiting = await manager.async_prepare(source="test")
    assert waiting["mode"] == "waiting"
    assert manager._timeout_seconds == 5
    assert waiting["message"] == "Waiting for SessionStatus to report 'Started'."

    bus.callbacks["SessionStatus"]({"Started": "true"})
    assert manager.snapshot()["mode"] == "running"
    manager._state["started_at"] = fixed - timedelta(seconds=8.6)
    manager._on_tick()
    assert manager.snapshot()["elapsed"] == 8.6

    completed = await manager.async_complete(source="button")
    controller.async_set_delay.assert_awaited_once_with(9, source="calibration")
    assert completed["last_result"]["seconds"] == 9
    assert completed["last_result"]["completed_at"] == "2026-09-01T12:00:00+00:00"
    reload_callback.assert_called_once()
    assert manager._notify_user.call_args.args[0] == "F1 live delay calibrated"

    remove_listener()
    await manager.async_close()
    assert "SessionStatus" in bus.removed
    assert reference.removed is True
    assert snapshots


async def test_prepare_uses_already_available_session_and_formation_markers(
    hass, monkeypatch
) -> None:
    fixed = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(calibration.dt_util, "utcnow", lambda: fixed)
    formation = _FormationTracker()
    manager, _ = _manager(hass, formation_tracker=formation)
    manager._schedule_tick = Mock()
    manager._schedule_timeout = Mock()

    manager._last_session_payload = {"Message": "GreenFlag"}
    assert (await manager.async_prepare())["mode"] == "running"
    await manager.async_cancel()

    manager._handle_reference_update(LIVE_DELAY_REFERENCE_FORMATION)
    marker = fixed - timedelta(seconds=12)
    manager._formation_start_utc = marker
    state = await manager.async_prepare()
    assert state["mode"] == "running"
    assert state["started_at"] == marker.isoformat(timespec="seconds")
    assert state["message"].startswith("Calibration running from formation marker")

    await manager.async_cancel()
    manager._formation_start_utc = None
    await manager.async_prepare()
    formation.formation_start_utc = fixed
    assert formation.callback is not None
    formation.callback({"ready": True})
    assert manager.snapshot()["mode"] == "running"


async def test_lap_sync_validation_tick_and_timeout_notifications(hass) -> None:
    bus = _Bus()
    formation = _FormationTracker()
    manager, _ = _manager(hass, bus=bus, formation_tracker=formation)
    manager._schedule_tick = Mock()
    manager._schedule_timeout = Mock()
    manager._handle_reference_update(LIVE_DELAY_REFERENCE_LAP_SYNC)

    formation._session_type = "Practice"
    formation._session_name = "Practice 1"
    blocked = await manager.async_prepare()
    assert blocked["mode"] == "idle"
    assert "only available" in blocked["message"]

    formation._session_type = "Sprint"
    formation._session_name = "Sprint"
    waiting = await manager.async_prepare()
    assert waiting["mode"] == "waiting"
    assert waiting["message"] == "Waiting for next lap to complete..."
    assert manager._effective_timeout() == 300

    for payload in (None, {}, {"CurrentLap": None}, {"LapCount": "bad"}):
        manager._handle_lapcount_message(payload)  # type: ignore[arg-type]
        assert manager.snapshot()["mode"] == "waiting"
    manager._handle_lapcount_message({"LapCount": "1"})
    running = manager.snapshot()
    assert running["mode"] == "running"
    assert running["recorded_lap"] == 0
    assert running["message"].startswith("Lap 0 completed")

    await manager.async_cancel(source="timeout")
    assert "Lap 0 was recorded" in manager._notify_user.call_args.args[1]
    manager._recorded_lap = None
    manager._reference = LIVE_DELAY_REFERENCE_FORMATION
    manager._state["mode"] = "running"
    await manager.async_cancel(source="timeout")
    assert manager._notify_user.call_args.args[1] == (
        "Calibration timed out without changing the delay."
    )


async def test_replay_blocks_calibration_and_invalid_completion(hass) -> None:
    replay_controller = SimpleNamespace(state=ReplayState.PLAYING)
    manager, controller = _manager(hass, replay_controller=replay_controller)
    state = await manager.async_prepare(source="switch")
    assert state["mode"] == "idle"
    assert "not available in replay mode" in state["message"]
    assert not controller.async_set_delay.await_count

    state = await manager.async_complete(source="button")
    assert state["mode"] == "idle"
    state = await manager.async_cancel(source="button")
    assert state["mode"] == "idle"

    replay_controller.state = ReplayState.IDLE
    with pytest.raises(RuntimeError, match="not running"):
        await manager.async_complete()


async def test_internal_session_timer_and_cleanup_branches(hass, monkeypatch) -> None:
    bus = _Bus(fail_stream="SessionStatus")
    manager, _ = _manager(hass, bus=bus)
    assert manager._session_unsub is None
    assert manager._is_session_live(None) is False
    assert manager._is_session_live({"Started": "started"}) is True
    assert manager._is_session_live({"Status": "Started"}) is True
    assert manager._is_session_live({"Status": "Stopped"}) is False
    assert manager._is_session_finished(None) is False
    assert manager._is_session_finished({"Message": "Finalised"}) is True

    manager._reference = LIVE_DELAY_REFERENCE_FORMATION
    manager._state["mode"] = "running"
    manager._handle_session_status({"Status": "Finished"})
    assert manager.snapshot()["mode"] == "idle"
    manager._on_tick()
    manager._on_timeout()

    manager._state["mode"] = "running"
    manager._on_timeout()
    await hass.async_block_till_done()
    assert manager.snapshot()["mode"] == "idle"

    bad = object()
    manager._state["started_at"] = bad
    assert manager._serialize_state()["started_at"] is bad
    manager._state["started_at"] = None
    assert manager._compute_elapsed() == 0.0

    tick = Mock()
    timeout = Mock()
    manager._tick_handle = SimpleNamespace(cancel=tick)
    manager._timeout_handle = SimpleNamespace(cancel=timeout)
    manager._cancel_handles()
    tick.assert_called_once()
    timeout.assert_called_once()

    manager._schedule_tick()
    manager._schedule_timeout()
    manager._cancel_handles()

    manager._schedule_tick = Mock()
    manager._schedule_timeout = Mock()
    manager._start_timer(reason="invalid_marker", started_at=object())
    assert manager.snapshot()["mode"] == "running"

    manager._bus = _Bus(fail_stream="LapCount")
    manager._reference = LIVE_DELAY_REFERENCE_LAP_SYNC
    manager._ensure_lapcount_listener()
    assert manager._lapcount_unsub is None

    manager._reference = LIVE_DELAY_REFERENCE_SESSION
    manager._handle_lapcount_message({"CurrentLap": 2})
    manager._reference = LIVE_DELAY_REFERENCE_LAP_SYNC
    manager._state["mode"] = "idle"
    manager._handle_lapcount_message({"CurrentLap": 2})

    manager._formation_tracker = None
    manager._ensure_formation_listener()
    manager._remove_formation_listener()
    manager._remove_lapcount_listener()

    manager._bus = None
    manager._lapcount_unsub = None
    manager._ensure_lapcount_listener()

    async def notification_result():
        await asyncio.sleep(0)

    monkeypatch.setattr(
        calibration.persistent_notification,
        "async_create",
        Mock(return_value=notification_result()),
    )
    manager._notify_user = LiveDelayCalibrationManager._notify_user.__get__(manager)
    manager._notify_user("Title", "Message")
    await hass.async_block_till_done()


async def test_reference_switches_start_waiting_workflows_and_close_safely(
    hass,
) -> None:
    fixed = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    bus = _Bus()
    formation = _FormationTracker()
    manager, _ = _manager(hass, bus=bus, formation_tracker=formation)
    manager._schedule_tick = Mock()
    manager._schedule_timeout = Mock()
    manager._state["mode"] = "waiting"
    manager._formation_start_utc = fixed

    manager._handle_reference_update(LIVE_DELAY_REFERENCE_FORMATION)
    assert manager.snapshot()["mode"] == "running"
    manager._transition_to_idle(None)

    manager._state["mode"] = "waiting"
    manager._handle_reference_update(LIVE_DELAY_REFERENCE_LAP_SYNC)
    assert "LapCount" in bus.callbacks

    manager._state["mode"] = "waiting"
    manager._last_session_payload = {"Status": "Green"}
    manager._handle_reference_update(LIVE_DELAY_REFERENCE_SESSION)
    assert manager.snapshot()["mode"] == "running"

    def fail_remove():
        raise RuntimeError("remove failed")

    manager._formation_unsub = fail_remove
    manager._lapcount_unsub = fail_remove
    await manager.async_close()


def test_replay_state_exception_and_reference_message_helpers(hass) -> None:
    manager, _ = _manager(hass, replay_controller=SimpleNamespace())
    assert manager._is_replay_active() is False

    manager._reference = LIVE_DELAY_REFERENCE_LAP_SYNC
    assert manager._waiting_message().startswith("Waiting for next lap")
    assert manager._running_message().startswith("Calibration running")
    manager._recorded_lap = 3
    assert manager._running_message().startswith("Lap 3 completed")

    manager._reference = LIVE_DELAY_REFERENCE_FORMATION
    assert manager._waiting_message().startswith("Waiting for formation")
    assert manager._running_message().startswith("Calibration running from formation")

    manager._reference = LIVE_DELAY_REFERENCE_SESSION
    assert manager._effective_timeout() == 120
    assert manager._is_current_session_race_or_sprint() is True
