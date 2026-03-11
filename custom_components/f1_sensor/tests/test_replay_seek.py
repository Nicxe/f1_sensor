from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant import config_entries
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import (
    LiveModeCoordinator,
    RaceControlCoordinator,
    SessionClockCoordinator,
    SessionInfoCoordinator,
    SessionStatusCoordinator,
    TrackStatusCoordinator,
    _build_replay_reset_callbacks,
)
from custom_components.f1_sensor.const import (
    DOMAIN,
    RCM_OVERTAKE_ENABLED,
    REPLAY_START_REFERENCE_SESSION,
)
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.replay_mode import (
    ReplayController,
    ReplayIndex,
    ReplayState,
)

ENTRY_ID = "entry-test"


def _make_config_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, entry_id=ENTRY_ID)
    entry.add_to_hass(hass)
    object.__setattr__(
        entry, "state", config_entries.ConfigEntryState.SETUP_IN_PROGRESS
    )
    return entry


class FakeLiveBus:
    def __init__(self) -> None:
        self._subs: dict[str, list] = {}
        self._transport_factory = None
        self._running = False
        self.injected: list[tuple[str, dict]] = []

    def subscribe(self, stream: str, callback):
        self._subs.setdefault(stream, []).append(callback)

        def _unsub() -> None:
            callbacks = self._subs.get(stream, [])
            if callback in callbacks:
                callbacks.remove(callback)

        return _unsub

    async def swap_transport(self, transport_factory) -> None:
        self._transport_factory = transport_factory
        self._running = transport_factory is not None

    async def async_close(self) -> None:
        self._running = False

    def inject_message(self, stream: str, payload: dict) -> None:
        self.injected.append((stream, payload))
        for callback in list(self._subs.get(stream, [])):
            callback(payload)


class CloseOrderLiveBus(FakeLiveBus):
    def __init__(self) -> None:
        super().__init__()
        self.controller: ReplayController | None = None
        self.transport_closed_on_async_close: list[bool] = []

    async def async_close(self) -> None:
        transport = self.controller.transport if self.controller else None
        self.transport_closed_on_async_close.append(
            transport is None or transport._closed
        )
        await super().async_close()


def _write_frames(tmp_path: Path, frames: list[tuple[int, str, dict]]) -> Path:
    frames_file = tmp_path / "frames.jsonl"
    lines = [
        json.dumps({"t": ts_ms, "s": stream, "p": payload}, separators=(",", ":"))
        for ts_ms, stream, payload in frames
    ]
    frames_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return frames_file


def _build_index(
    tmp_path: Path,
    *,
    initial_state: dict[str, dict],
    frames: list[tuple[int, str, dict]],
) -> ReplayIndex:
    frames_file = _write_frames(tmp_path, frames)
    duration_ms = max(ts_ms for ts_ms, _stream, _payload in frames)
    return ReplayIndex(
        session_id="test_session",
        total_frames=len(frames),
        duration_ms=duration_ms,
        session_started_at_ms=0,
        frames_file=frames_file,
        index_file=tmp_path / "index.json",
        formation_started_at_ms=None,
        initial_state=initial_state,
        formation_initial_state=None,
    )


async def _setup_controller(
    hass,
    tmp_path: Path,
    *,
    initial_state: dict[str, dict],
    frames: list[tuple[int, str, dict]],
    coordinators: tuple,
) -> tuple[ReplayController, ReplayIndex, FakeLiveBus, LiveAvailabilityTracker]:
    bus = FakeLiveBus()
    live_state = LiveAvailabilityTracker()
    controller = ReplayController(
        hass,
        ENTRY_ID,
        AsyncMock(),
        bus,
        live_state=live_state,
        start_reference_controller=SimpleNamespace(
            current=REPLAY_START_REFERENCE_SESSION
        ),
    )
    index = _build_index(tmp_path, initial_state=initial_state, frames=frames)
    controller.session_manager._loaded_index = index
    controller.session_manager._state = ReplayState.READY
    hass.data.setdefault(DOMAIN, {})[ENTRY_ID] = {
        "replay_controller": controller,
        "replay_reset_callbacks": _build_replay_reset_callbacks(*coordinators),
    }
    return controller, index, bus, live_state


async def _setup_stateful_replay_harness(hass, tmp_path: Path):
    initial_state = {
        "SessionInfo": {"Type": "Race", "Name": "Race"},
        "SessionStatus": {"Status": "Started", "Started": True},
        "TrackStatus": {"Status": "1", "Message": "All clear"},
    }
    frames = [
        (0, "SessionInfo", initial_state["SessionInfo"]),
        (0, "SessionStatus", initial_state["SessionStatus"]),
        (0, "TrackStatus", initial_state["TrackStatus"]),
        (
            15_000,
            "RaceControlMessages",
            {
                "Messages": {
                    "1": {
                        "Utc": "2025-12-07T13:00:15Z",
                        "Category": "Other",
                        "Message": RCM_OVERTAKE_ENABLED,
                    }
                }
            },
        ),
        (
            20_000,
            "TrackStatus",
            {"Status": "5", "Message": "Red flag"},
        ),
    ]

    bus = FakeLiveBus()
    live_state = LiveAvailabilityTracker()
    entry = _make_config_entry(hass)
    track = TrackStatusCoordinator(
        hass,
        session_coord=object(),
        bus=bus,
        config_entry=entry,
        live_state=live_state,
    )
    session_status = SessionStatusCoordinator(
        hass,
        session_coord=object(),
        bus=bus,
        config_entry=entry,
        live_state=live_state,
    )
    session_info = SessionInfoCoordinator(
        hass,
        session_coord=object(),
        bus=bus,
        config_entry=entry,
        live_state=live_state,
    )
    race_control = RaceControlCoordinator(
        hass,
        session_coord=object(),
        bus=bus,
        config_entry=entry,
        live_state=live_state,
    )
    live_mode = LiveModeCoordinator(
        hass,
        race_control,
        session_status_coordinator=session_status,
        config_entry=entry,
        live_state=live_state,
    )

    for coordinator in (track, session_status, session_info, race_control, live_mode):
        await coordinator.async_config_entry_first_refresh()

    controller = ReplayController(
        hass,
        ENTRY_ID,
        AsyncMock(),
        bus,
        live_state=live_state,
        start_reference_controller=SimpleNamespace(
            current=REPLAY_START_REFERENCE_SESSION
        ),
    )
    index = _build_index(tmp_path, initial_state=initial_state, frames=frames)
    controller.session_manager._loaded_index = index
    controller.session_manager._state = ReplayState.READY
    hass.data.setdefault(DOMAIN, {})[ENTRY_ID] = {
        "replay_controller": controller,
        "replay_reset_callbacks": _build_replay_reset_callbacks(
            track,
            session_status,
            session_info,
            race_control,
            live_mode,
        ),
    }
    return controller, track, race_control, live_mode


async def _setup_session_clock_harness(
    hass,
    tmp_path: Path,
    *,
    initial_state: dict[str, dict],
    frames: list[tuple[int, str, dict]],
) -> tuple[ReplayController, SessionClockCoordinator]:
    bus = FakeLiveBus()
    live_state = LiveAvailabilityTracker()
    entry = _make_config_entry(hass)
    session_clock = SessionClockCoordinator(
        hass,
        session_coord=object(),
        bus=bus,
        config_entry=entry,
        live_state=live_state,
    )
    await session_clock.async_config_entry_first_refresh()
    controller = ReplayController(
        hass,
        ENTRY_ID,
        AsyncMock(),
        bus,
        live_state=live_state,
        start_reference_controller=SimpleNamespace(
            current=REPLAY_START_REFERENCE_SESSION
        ),
    )
    index = _build_index(tmp_path, initial_state=initial_state, frames=frames)
    controller.session_manager._loaded_index = index
    controller.session_manager._state = ReplayState.READY
    hass.data.setdefault(DOMAIN, {})[ENTRY_ID] = {
        "replay_controller": controller,
        "replay_reset_callbacks": _build_replay_reset_callbacks(session_clock),
    }
    return controller, session_clock


async def _setup_close_order_harness(
    hass, tmp_path: Path
) -> tuple[ReplayController, CloseOrderLiveBus]:
    bus = CloseOrderLiveBus()
    live_state = LiveAvailabilityTracker()
    controller = ReplayController(
        hass,
        ENTRY_ID,
        AsyncMock(),
        bus,
        live_state=live_state,
        start_reference_controller=SimpleNamespace(
            current=REPLAY_START_REFERENCE_SESSION
        ),
    )
    bus.controller = controller
    index = _build_index(
        tmp_path,
        initial_state={"SessionInfo": {"Type": "Race", "Name": "Race"}},
        frames=[
            (0, "SessionInfo", {"Type": "Race", "Name": "Race"}),
            (0, "TrackStatus", {"Status": "1", "Message": "All clear"}),
            (30_000, "TrackStatus", {"Status": "1", "Message": "All clear"}),
        ],
    )
    controller.session_manager._loaded_index = index
    controller.session_manager._state = ReplayState.READY
    hass.data.setdefault(DOMAIN, {})[ENTRY_ID] = {
        "replay_controller": controller,
        "replay_reset_callbacks": [],
    }
    return controller, bus


@pytest.mark.asyncio
async def test_replay_seek_ready_updates_planned_position(hass, tmp_path: Path) -> None:
    controller, index, _bus, _live_state = await _setup_controller(
        hass,
        tmp_path,
        initial_state={"SessionInfo": {"Type": "Race", "Name": "Race"}},
        frames=[
            (0, "SessionInfo", {"Type": "Race", "Name": "Race"}),
            (45_000, "TrackStatus", {"Status": "1"}),
        ],
        coordinators=(),
    )

    await controller.async_seek_by(30)
    status = controller.get_playback_status()
    assert status["position_ms"] == 30_000

    await controller.async_seek_by(-60)
    status = controller.get_playback_status()
    assert status["position_ms"] == 0

    await controller.async_seek_to_ms(index.duration_ms + 120_000)
    status = controller.get_playback_status()
    assert status["position_ms"] == index.duration_ms


@pytest.mark.asyncio
async def test_replay_seek_forward_replays_intermediate_state_changes(
    hass, tmp_path: Path
) -> None:
    controller, track, race_control, live_mode = await _setup_stateful_replay_harness(
        hass, tmp_path
    )

    await controller.async_play()
    await asyncio.sleep(0)
    assert track.data["Status"] == "1"

    await controller.async_seek_by(30)
    await asyncio.sleep(0)

    assert controller.state == ReplayState.PLAYING
    assert track.data["Status"] == "5"
    assert race_control.data["Message"] == RCM_OVERTAKE_ENABLED
    assert live_mode.data["overtake_enabled"] is True

    await controller.async_stop()


@pytest.mark.asyncio
async def test_replay_seek_backward_replays_same_race_control_message_again(
    hass, tmp_path: Path
) -> None:
    controller, track, race_control, _live_mode = await _setup_stateful_replay_harness(
        hass, tmp_path
    )
    deliveries: list[dict | None] = []
    unsub = race_control.async_add_listener(
        lambda: deliveries.append(race_control.data)
    )

    try:
        await controller.async_play()
        await controller.async_seek_by(30)
        await asyncio.sleep(0)
        assert track.data["Status"] == "5"
        first_delivery_count = len(
            [item for item in deliveries if isinstance(item, dict)]
        )

        await controller.async_seek_by(-30)
        await asyncio.sleep(0)
        assert track.data["Status"] == "1"
        assert race_control.data is None

        await controller.async_seek_by(30)
        await asyncio.sleep(0)
        second_delivery_count = len(
            [item for item in deliveries if isinstance(item, dict)]
        )

        assert race_control.data["Message"] == RCM_OVERTAKE_ENABLED
        assert track.data["Status"] == "5"
        assert second_delivery_count == first_delivery_count + 1
    finally:
        unsub()
        await controller.async_stop()


@pytest.mark.asyncio
async def test_replay_seek_preserves_paused_state(hass, tmp_path: Path) -> None:
    (
        controller,
        _track,
        _race_control,
        _live_mode,
    ) = await _setup_stateful_replay_harness(hass, tmp_path)

    await controller.async_play()
    await controller.async_pause()
    await controller.async_seek_by(30)
    await asyncio.sleep(0)

    status = controller.get_playback_status()
    assert controller.state == ReplayState.PAUSED
    assert controller.transport is not None
    assert controller.transport.is_paused() is True
    assert status["position_ms"] == 20_000
    assert status["playback_start_ms"] == 0

    await controller.async_stop()


@pytest.mark.asyncio
async def test_replay_seek_closes_transport_before_live_bus_shutdown(
    hass, tmp_path: Path
) -> None:
    controller, bus = await _setup_close_order_harness(hass, tmp_path)

    await controller.async_play()
    await controller.async_pause()
    await controller.async_seek_by(30)
    await asyncio.sleep(0)

    assert bus.transport_closed_on_async_close
    assert bus.transport_closed_on_async_close[-1] is True

    await controller.async_stop()


@pytest.mark.asyncio
async def test_replay_seek_race_session_clock_updates_after_seek(
    hass, tmp_path: Path
) -> None:
    initial_state = {
        "SessionInfo": {"Type": "Race", "Name": "Race"},
        "SessionStatus": {"Status": "Started", "Started": True},
        "SessionData": {
            "StatusSeries": {
                "0": {"Utc": "2025-12-07T13:00:00Z", "SessionStatus": "Started"}
            }
        },
        "ExtrapolatedClock": {
            "Utc": "2025-12-07T13:00:00Z",
            "Remaining": "02:00:00",
            "Extrapolating": True,
        },
        "Heartbeat": {"Utc": "2025-12-07T13:00:00Z"},
    }
    frames = [
        (0, "SessionInfo", initial_state["SessionInfo"]),
        (0, "SessionStatus", initial_state["SessionStatus"]),
        (0, "SessionData", initial_state["SessionData"]),
        (0, "ExtrapolatedClock", initial_state["ExtrapolatedClock"]),
        (0, "Heartbeat", initial_state["Heartbeat"]),
        (
            30_000,
            "ExtrapolatedClock",
            {
                "Utc": "2025-12-07T13:00:30Z",
                "Remaining": "01:59:30",
                "Extrapolating": True,
            },
        ),
        (30_000, "Heartbeat", {"Utc": "2025-12-07T13:00:30Z"}),
    ]
    controller, session_clock = await _setup_session_clock_harness(
        hass,
        tmp_path,
        initial_state=initial_state,
        frames=frames,
    )

    await controller.async_play()
    await controller.async_seek_by(30)
    await asyncio.sleep(0)

    state = session_clock.data
    assert state["clock_elapsed_s"] == 30
    assert state["clock_remaining_s"] == 7170
    assert state["session_status"] == "Started"
    assert state["race_three_hour_remaining_s"] in {10_769, 10_770}

    await controller.async_stop()


@pytest.mark.asyncio
async def test_replay_seek_qualifying_session_clock_keeps_restart_state(
    hass, tmp_path: Path
) -> None:
    initial_state = {
        "SessionInfo": {"Type": "Qualifying", "Name": "Qualifying"},
        "SessionStatus": {"Status": "Started", "Started": True},
        "SessionData": {
            "Series": {"0": {"Utc": "2025-12-06T14:00:00Z", "QualifyingPart": 1}},
            "StatusSeries": {
                "0": {"Utc": "2025-12-06T14:00:00Z", "SessionStatus": "Started"}
            },
        },
        "ExtrapolatedClock": {
            "Utc": "2025-12-06T14:00:00Z",
            "Remaining": "00:18:00",
            "Extrapolating": True,
        },
        "Heartbeat": {"Utc": "2025-12-06T14:00:00Z"},
    }
    frames = [
        (0, "SessionInfo", initial_state["SessionInfo"]),
        (0, "SessionStatus", initial_state["SessionStatus"]),
        (0, "SessionData", initial_state["SessionData"]),
        (0, "ExtrapolatedClock", initial_state["ExtrapolatedClock"]),
        (0, "Heartbeat", initial_state["Heartbeat"]),
        (
            15_000,
            "SessionData",
            {
                "StatusSeries": {
                    "0": {
                        "Utc": "2025-12-06T14:00:15Z",
                        "SessionStatus": "Aborted",
                    }
                }
            },
        ),
        (
            15_000,
            "SessionStatus",
            {"Status": "Aborted", "Started": False},
        ),
        (
            15_000,
            "ExtrapolatedClock",
            {
                "Utc": "2025-12-06T14:00:15Z",
                "Remaining": "00:17:45",
                "Extrapolating": False,
            },
        ),
        (
            25_000,
            "SessionData",
            {
                "StatusSeries": {
                    "0": {
                        "Utc": "2025-12-06T14:00:25Z",
                        "SessionStatus": "Resumed",
                    }
                }
            },
        ),
        (
            25_000,
            "SessionStatus",
            {"Status": "Resumed", "Started": True},
        ),
        (
            30_000,
            "ExtrapolatedClock",
            {
                "Utc": "2025-12-06T14:00:30Z",
                "Remaining": "00:17:40",
                "Extrapolating": True,
            },
        ),
        (30_000, "Heartbeat", {"Utc": "2025-12-06T14:00:30Z"}),
    ]
    controller, session_clock = await _setup_session_clock_harness(
        hass,
        tmp_path,
        initial_state=initial_state,
        frames=frames,
    )

    await controller.async_play()
    await controller.async_seek_by(30)
    await asyncio.sleep(0)

    state = session_clock.data
    assert state["session_part"] == 1
    assert state["clock_total_s"] == 1080
    assert state["clock_elapsed_s"] == 20
    assert state["clock_remaining_s"] == 1060
    assert state["session_status"] == "Resumed"
    assert state["clock_phase"] == "running"

    await controller.async_stop()


@pytest.mark.asyncio
async def test_replay_seek_practice_session_clock_updates_after_seek(
    hass, tmp_path: Path
) -> None:
    initial_state = {
        "SessionInfo": {
            "Type": "Practice",
            "Name": "Practice 1",
            "StartDate": "2025-12-06T10:00:00Z",
            "EndDate": "2025-12-06T11:00:00Z",
        },
        "SessionStatus": {"Status": "Started", "Started": True},
        "SessionData": {
            "StatusSeries": {
                "0": {"Utc": "2025-12-06T10:00:00Z", "SessionStatus": "Started"}
            }
        },
        "ExtrapolatedClock": {
            "Utc": "2025-12-06T10:00:00Z",
            "Remaining": "01:00:00",
            "Extrapolating": True,
        },
        "Heartbeat": {"Utc": "2025-12-06T10:00:00Z"},
    }
    frames = [
        (0, "SessionInfo", initial_state["SessionInfo"]),
        (0, "SessionStatus", initial_state["SessionStatus"]),
        (0, "SessionData", initial_state["SessionData"]),
        (0, "ExtrapolatedClock", initial_state["ExtrapolatedClock"]),
        (0, "Heartbeat", initial_state["Heartbeat"]),
        (
            30_000,
            "ExtrapolatedClock",
            {
                "Utc": "2025-12-06T10:00:30Z",
                "Remaining": "00:59:30",
                "Extrapolating": True,
            },
        ),
        (30_000, "Heartbeat", {"Utc": "2025-12-06T10:00:30Z"}),
    ]
    controller, session_clock = await _setup_session_clock_harness(
        hass,
        tmp_path,
        initial_state=initial_state,
        frames=frames,
    )

    await controller.async_play()
    await controller.async_seek_by(30)
    await asyncio.sleep(0)

    state = session_clock.data
    assert state["session_type"] == "Practice"
    assert state["clock_total_s"] == 3600
    assert state["clock_elapsed_s"] == 30
    assert state["clock_remaining_s"] == 3570

    await controller.async_stop()


@pytest.mark.asyncio
async def test_replay_pause_freezes_session_clock(hass, tmp_path: Path) -> None:
    initial_state = {
        "SessionInfo": {"Type": "Race", "Name": "Race"},
        "SessionStatus": {"Status": "Started", "Started": True},
        "SessionData": {
            "StatusSeries": {
                "0": {"Utc": "2025-12-07T13:00:00Z", "SessionStatus": "Started"}
            }
        },
        "ExtrapolatedClock": {
            "Utc": "2025-12-07T13:00:00Z",
            "Remaining": "02:00:00",
            "Extrapolating": True,
        },
        "Heartbeat": {"Utc": "2025-12-07T13:00:00Z"},
    }
    frames = [
        (0, "SessionInfo", initial_state["SessionInfo"]),
        (0, "SessionStatus", initial_state["SessionStatus"]),
        (0, "SessionData", initial_state["SessionData"]),
        (0, "ExtrapolatedClock", initial_state["ExtrapolatedClock"]),
        (0, "Heartbeat", initial_state["Heartbeat"]),
        (
            10_000,
            "ExtrapolatedClock",
            {
                "Utc": "2025-12-07T13:00:10Z",
                "Remaining": "01:59:50",
                "Extrapolating": True,
            },
        ),
        (10_000, "Heartbeat", {"Utc": "2025-12-07T13:00:10Z"}),
    ]
    controller, session_clock = await _setup_session_clock_harness(
        hass,
        tmp_path,
        initial_state=initial_state,
        frames=frames,
    )

    await controller.async_play()
    await controller.async_seek_by(10)
    await controller.async_pause()
    paused_remaining = session_clock.data["clock_remaining_s"]

    await asyncio.sleep(1.2)

    assert controller.state == ReplayState.PAUSED
    assert session_clock.data["clock_remaining_s"] == paused_remaining

    await controller.async_stop()
