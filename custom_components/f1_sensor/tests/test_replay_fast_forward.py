"""Replay catch-up must use snapshots and keep Home Assistant responsive."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.f1_sensor import LiveDriversCoordinator
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.replay_mode import (
    ReplayController,
    ReplayIndex,
    ReplayState,
)


class _LiveBus:
    """Record real controller injection and transport handoff without network I/O."""

    def __init__(self) -> None:
        self._transport_factory = object()
        self._running = False
        self.injected: list[tuple[str, dict]] = []
        self.swaps: list[Callable] = []
        self.on_frame: Callable[[dict], None] | None = None

    def set_heartbeat_expectation(self, _enabled: bool) -> None:
        pass

    def inject_message(self, stream: str, payload: dict) -> None:
        self.injected.append((stream, payload))
        if self.on_frame is not None:
            self.on_frame(payload)

    async def swap_transport(self, factory) -> None:
        self.swaps.append(factory)
        self._transport_factory = factory
        self._running = True

    async def async_close(self) -> None:
        self._running = False


def _timing(lap: int) -> dict:
    return {"Lines": {"16": {"NumberOfLaps": lap}}}


def _lap(payload: dict) -> int:
    return payload["Lines"]["16"]["NumberOfLaps"]


def _ready_controller(hass, tmp_path, frames, *, checkpoints=None):
    path = tmp_path / "frames.jsonl"
    path.write_text(
        "".join(
            json.dumps({"t": timestamp, "s": "TimingData", "p": _timing(lap)}) + "\n"
            for timestamp, lap in frames
        ),
        encoding="utf-8",
    )
    index = ReplayIndex(
        session_id="catch-up-session",
        total_frames=len(frames),
        duration_ms=frames[-1][0],
        session_started_at_ms=0,
        frames_file=path,
        index_file=tmp_path / "index.json",
        initial_state={"TimingData": _timing(0)},
        seek_checkpoints=checkpoints,
    )
    bus = _LiveBus()
    controller = ReplayController(
        hass,
        "fast-forward-entry",
        AsyncMock(),
        bus,
        start_reference_controller=SimpleNamespace(current="session"),
    )
    controller.session_manager._loaded_index = index
    controller.session_manager._state = ReplayState.READY
    hass.data.setdefault(DOMAIN, {})["fast-forward-entry"] = {
        "replay_controller": controller,
    }
    return controller, bus


@pytest.mark.parametrize(("target_s", "completed_laps"), [(90, 3), (120, 5)])
async def test_ready_jump_preserves_history_absent_from_cached_snapshot(
    hass, tmp_path, target_s, completed_laps
) -> None:
    """Timing snapshots cannot replace earlier laps needed by user-facing history."""
    checkpoints = [
        {"t": timestamp, "state": {"TimingData": _timing(lap)}}
        for timestamp, lap in ((60_000, 2), (90_000, 3), (130_000, 6))
    ]
    frames = [(10_000, 1), (60_000, 2), (90_000, 3), (95_000, 4), (120_000, 5)]
    controller, bus = _ready_controller(hass, tmp_path, frames, checkpoints=checkpoints)
    lap_times = ["1:32.000", "1:30.000", "1:31.000", "1:33.000", "1:34.000"]
    lines = []
    for timestamp, lap in frames:
        payload = _timing(lap)
        payload["Lines"]["16"]["LastLapTime"] = {"Value": lap_times[lap - 1]}
        lines.append(json.dumps({"t": timestamp, "s": "TimingData", "p": payload}))
    index = controller.session_manager.get_loaded_index()
    index.frames_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    drivers = LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    bus.on_frame = drivers._on_timingdata
    try:
        await controller.async_seek_to_position(target_s)
        await controller.async_play()

        current = drivers.data["drivers"]["16"]
        history = current["lap_history"]["laps"]
        assert history == {
            str(lap): lap_times[lap - 1] for lap in range(1, completed_laps + 1)
        }
        assert drivers.data["fastest_lap"]["time"] == "1:30.000"
        assert [_lap(payload) for _, payload in bus.injected] == list(
            range(completed_laps + 1)
        )
        assert controller.transport.get_playback_position_ms() == target_s * 1000
        assert controller.transport._include_start_frame is False
    finally:
        await controller.async_stop()
        await drivers.async_close()


async def test_fallback_fast_forward_yields_before_injection_finishes(
    hass, tmp_path
) -> None:
    """Other HA tasks must run during catch-up even when there are no snapshots."""
    total = 5_000
    controller, bus = _ready_controller(
        hass, tmp_path, [(lap, lap) for lap in range(1, total + 1)]
    )
    first_frame = asyncio.Event()
    bus.on_frame = lambda payload: first_frame.set() if _lap(payload) else None

    async def heartbeat() -> int:
        await first_frame.wait()
        return len(bus.injected) - 1  # Exclude the baseline snapshot.

    observer = asyncio.create_task(heartbeat())
    try:
        await controller.async_seek_to_position(total / 1000)
        await controller.async_play()
        observed = await observer

        assert 0 < observed < total
        assert [_lap(payload) for _, payload in bus.injected] == list(range(total + 1))
    finally:
        observer.cancel()
        await asyncio.gather(observer, return_exceptions=True)
        await controller.async_stop()


@pytest.mark.parametrize("action", ["async_stop", "async_close"])
async def test_stop_or_unload_during_catch_up_cannot_restore_old_replay(
    hass, tmp_path, action
) -> None:
    """A stop at a cooperative yield must prevent later old frames and handoff."""
    total = 5_000
    controller, bus = _ready_controller(
        hass, tmp_path, [(lap, lap) for lap in range(1, total + 1)]
    )
    original_factory = bus._transport_factory
    first_frame = asyncio.Event()
    bus.on_frame = lambda payload: first_frame.set() if _lap(payload) else None

    async def stop_after_first_data() -> tuple[int, int]:
        await first_frame.wait()
        before = len(bus.injected)
        await getattr(controller, action)()
        return before, len(bus.injected)

    stopper = asyncio.create_task(stop_after_first_data())
    try:
        await controller.async_seek_to_position(total / 1000)
        play = asyncio.create_task(controller.async_play())
        result = await asyncio.gather(play, stopper, return_exceptions=True)
        assert result[0] is None or isinstance(result[0], asyncio.CancelledError)
        assert not isinstance(result[1], BaseException)
        before_stop, after_stop = result[1]
        await asyncio.sleep(0)

        assert 1 < before_stop < total + 1
        assert len(bus.injected) == after_stop
        assert bus.swaps == []
        assert bus._transport_factory is original_factory
        assert controller.state is ReplayState.IDLE
        assert controller.transport is None
        assert controller.session_manager.get_loaded_index() is None
        assert controller._replay_active is False
    finally:
        stopper.cancel()
        await asyncio.gather(stopper, return_exceptions=True)
        await controller.async_close()


async def test_stop_while_executor_reads_cannot_inject_stale_range(
    hass, tmp_path, monkeypatch
) -> None:
    """Finishing an already-running disk job after stop must not revive replay."""
    controller, bus = _ready_controller(hass, tmp_path, [(1_000, 1)])
    original_factory = bus._transport_factory
    original_read = controller._read_frames_range_sync
    started = asyncio.Event()
    finished = asyncio.Event()
    release = threading.Event()

    def blocked_read(*args, **kwargs):
        hass.loop.call_soon_threadsafe(started.set)
        try:
            release.wait()
            return original_read(*args, **kwargs)
        finally:
            hass.loop.call_soon_threadsafe(finished.set)

    monkeypatch.setattr(controller, "_read_frames_range_sync", blocked_read)
    await controller.async_seek_to_position(1)
    play = asyncio.create_task(controller.async_play())
    try:
        await started.wait()
        await controller.async_stop()
        release.set()
        await finished.wait()
        await play

        assert [_lap(payload) for _, payload in bus.injected] == [0]
        assert bus.swaps == []
        assert bus._transport_factory is original_factory
        assert controller.state is ReplayState.IDLE
        assert controller.transport is None
    finally:
        release.set()
        await asyncio.gather(play, return_exceptions=True)
        await controller.async_close()


async def test_stop_during_awaited_transport_handoff_restores_live_factory(
    hass, tmp_path, monkeypatch
) -> None:
    """Stop must cancel a partially completed bus swap before playback attaches."""
    controller, bus = _ready_controller(hass, tmp_path, [(1_000, 1)])
    original_factory = bus._transport_factory
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_swap(factory):
        bus._transport_factory = factory
        bus._running = True
        started.set()
        await release.wait()
        bus.swaps.append(factory)

    monkeypatch.setattr(bus, "swap_transport", blocked_swap)
    play = asyncio.create_task(controller.async_play())
    try:
        await started.wait()
        await controller.async_stop()
        release.set()
        await play

        assert bus.swaps == []
        assert bus._transport_factory is original_factory
        assert bus._running is False
        assert controller.state is ReplayState.IDLE
        assert controller.transport is None
        assert controller._playback_task is None
        assert controller._replay_active is False
    finally:
        release.set()
        await asyncio.gather(play, return_exceptions=True)
        await controller.async_close()


async def test_loading_another_session_supersedes_partial_catch_up(
    hass, tmp_path, monkeypatch
) -> None:
    """An old Play request cannot overwrite the newly loaded session's state."""
    controller, bus = _ready_controller(
        hass, tmp_path, [(lap, lap) for lap in range(1, 5_001)]
    )
    original_factory = bus._transport_factory
    manager = controller.session_manager
    replacement = replace(manager.get_loaded_index(), session_id="replacement-session")
    manager._available_sessions = [
        SimpleNamespace(
            unique_id=replacement.session_id,
            label="Another meeting - Race",
            year=2026,
            meeting_key=2,
            session_key=3,
        )
    ]
    first_frame = asyncio.Event()
    bus.on_frame = lambda payload: first_frame.set() if _lap(payload) else None

    async def load_replacement() -> None:
        manager._loaded_index = replacement
        manager._state = ReplayState.READY

    load = AsyncMock(side_effect=load_replacement)
    monkeypatch.setattr(manager, "async_load_session", load)

    async def select_and_load() -> int:
        await first_frame.wait()
        await manager.async_select_session(replacement.session_id)
        await controller.async_prepare_and_load_session()
        return len(bus.injected)

    loader = asyncio.create_task(select_and_load())
    try:
        await controller.async_seek_to_position(5)
        play = asyncio.create_task(controller.async_play())
        _, count_after_load = await asyncio.gather(play, loader)
        await asyncio.sleep(0)

        load.assert_awaited_once()
        assert len(bus.injected) == count_after_load < 5_001
        assert bus.swaps == []
        assert bus._transport_factory is original_factory
        assert manager.get_loaded_index() is replacement
        assert controller.state is ReplayState.READY
        assert controller.transport is None
        assert controller._replay_active is False
    finally:
        loader.cancel()
        await asyncio.gather(loader, return_exceptions=True)
        await controller.async_close()


async def test_cancelling_play_caller_releases_replay_ownership(hass, tmp_path) -> None:
    """A cancelled service caller must not leave HA locked in a partial replay."""
    controller, bus = _ready_controller(
        hass, tmp_path, [(lap, lap) for lap in range(1, 5_001)]
    )
    original_factory = bus._transport_factory
    first_frame = asyncio.Event()
    bus.on_frame = lambda payload: first_frame.set() if _lap(payload) else None
    await controller.async_seek_to_position(5)
    play = asyncio.create_task(controller.async_play())
    try:
        await first_frame.wait()
        play.cancel()
        with pytest.raises(asyncio.CancelledError):
            await play
        count_after_cancel = len(bus.injected)
        await asyncio.sleep(0)

        assert 1 < count_after_cancel < 5_001
        assert len(bus.injected) == count_after_cancel
        assert bus.swaps == []
        assert bus._transport_factory is original_factory
        assert controller.state is ReplayState.IDLE
        assert controller.transport is None
        assert controller.session_manager.get_loaded_index() is None
        assert controller._replay_active is False
    finally:
        await asyncio.gather(play, return_exceptions=True)
        await controller.async_close()


async def test_older_stop_cannot_unload_session_loaded_while_it_joins_cancelled_play(
    hass, tmp_path, monkeypatch
) -> None:
    """A newer Load owns the state even if an older Stop is still joining work."""
    controller, bus = _ready_controller(hass, tmp_path, [(1_000, 1)])
    manager = controller.session_manager
    replacement = replace(manager.get_loaded_index(), session_id="replacement-session")
    manager._available_sessions = [
        SimpleNamespace(
            unique_id=replacement.session_id,
            label="Another meeting - Race",
            year=2026,
            meeting_key=2,
            session_key=3,
        )
    ]
    entered = asyncio.Event()
    cancellation_started = asyncio.Event()
    release = asyncio.Event()

    async def slow_prepare(_index):
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancellation_started.set()
            await release.wait()

    async def load_replacement():
        manager._loaded_index = replacement
        manager._state = ReplayState.READY

    monkeypatch.setattr(controller, "_prepare_track_map_replay_index", slow_prepare)
    monkeypatch.setattr(manager, "async_load_session", load_replacement)
    play = asyncio.create_task(controller.async_play())
    stop = None
    try:
        await entered.wait()
        stop = asyncio.create_task(controller.async_stop())
        await cancellation_started.wait()

        await manager.async_select_session(replacement.session_id)
        await controller.async_prepare_and_load_session()
        assert controller.state is ReplayState.READY
        release.set()
        await asyncio.gather(play, stop)

        assert manager.get_loaded_index() is replacement
        assert controller.state is ReplayState.READY
        assert controller.transport is None
        assert bus.swaps == []
    finally:
        release.set()
        await asyncio.gather(
            *(task for task in (play, stop) if task is not None),
            return_exceptions=True,
        )
        await controller.async_close()


async def _select_download_session(manager, index) -> None:
    manager._available_sessions = [
        SimpleNamespace(
            unique_id=index.session_id,
            label="Test meeting - Race",
            year=2026,
            meeting_key=2,
            session_key=3,
        )
    ]
    await manager.async_select_session(index.session_id)


@pytest.mark.parametrize("download_error", [False, True])
async def test_stopped_download_cannot_restore_ready_or_error(
    hass, tmp_path, monkeypatch, download_error
) -> None:
    """Late download success and failure must leave an explicitly stopped replay idle."""
    controller, _bus = _ready_controller(hass, tmp_path, [(1_000, 1)])
    manager = controller.session_manager
    index = manager.get_loaded_index()
    await _select_download_session(manager, index)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def pending_download(_session):
        entered.set()
        await release.wait()
        if download_error:
            raise RuntimeError("Archive download failed")
        return index

    monkeypatch.setattr(manager, "_download_and_index_session", pending_download)
    load = asyncio.create_task(controller.async_prepare_and_load_session())
    try:
        await entered.wait()
        await controller.async_stop()
        release.set()
        await load

        assert manager.state is ReplayState.IDLE
        assert manager.get_loaded_index() is None
        assert manager.selected_session is None
        assert manager._get_snapshot()["download_error"] is None
    finally:
        release.set()
        await asyncio.gather(load, return_exceptions=True)
        await controller.async_close()


async def test_new_load_of_same_session_rejects_older_download_result(
    hass, tmp_path, monkeypatch
) -> None:
    """The selected object and LOADING state can match while a newer load owns them."""
    controller, _bus = _ready_controller(hass, tmp_path, [(1_000, 1)])
    manager = controller.session_manager
    stale_index = manager.get_loaded_index()
    fresh_index = replace(stale_index, total_frames=2)
    await _select_download_session(manager, stale_index)
    entered = [asyncio.Event(), asyncio.Event()]
    release = [asyncio.Event(), asyncio.Event()]
    calls = 0

    async def pending_download(_session):
        nonlocal calls
        call = calls
        calls += 1
        entered[call].set()
        await release[call].wait()
        return (stale_index, fresh_index)[call]

    monkeypatch.setattr(manager, "_download_and_index_session", pending_download)
    old_load = asyncio.create_task(controller.async_prepare_and_load_session())
    new_load = None
    try:
        await entered[0].wait()
        await manager.async_select_session(stale_index.session_id)
        new_load = asyncio.create_task(controller.async_prepare_and_load_session())
        await entered[1].wait()
        release[0].set()
        await old_load

        assert manager.state is ReplayState.LOADING
        assert manager.get_loaded_index() is None
        release[1].set()
        await new_load
        assert manager.state is ReplayState.READY
        assert manager.get_loaded_index() is fresh_index
    finally:
        for event in release:
            event.set()
        await asyncio.gather(
            *(task for task in (old_load, new_load) if task is not None),
            return_exceptions=True,
        )
        await controller.async_close()
