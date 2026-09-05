"""Real replay transport regressions for full queues and lifecycle transitions."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.f1_sensor import async_unload_entry, replay_mode
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.replay_mode import (
    ReplayController,
    ReplayIndex,
    ReplaySession,
    ReplayState,
    ReplayTransport,
)
from custom_components.f1_sensor.signalr import LiveBus


@pytest.fixture
def playback_probe(hass, monkeypatch):
    """Observe the production bounded queue and executor completion without sleeps."""
    queue_created = asyncio.Event()
    queue_full = asyncio.Event()
    queues = []
    readers = []
    queue_class = asyncio.Queue
    executor_job = hass.async_add_executor_job

    class ObservedQueue(queue_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.pending_puts = set()
            queues.append(self)
            queue_created.set()

        async def put(self, item):
            task = asyncio.current_task()
            self.pending_puts.add(task)
            try:
                if self.full() and item is not None:
                    queue_full.set()
                await super().put(item)
            finally:
                self.pending_puts.discard(task)

    def run_executor(func, *args):
        future = executor_job(func, *args)
        if getattr(func, "__name__", None) == "_read_frames_stream":
            readers.append(future)
        return future

    monkeypatch.setattr(replay_mode.asyncio, "Queue", ObservedQueue)
    monkeypatch.setattr(hass, "async_add_executor_job", run_executor)
    return queue_created, queue_full, queues, readers


def _index(tmp_path: Path, name: str, *, large: bool) -> ReplayIndex:
    path = tmp_path / f"{name}.jsonl"
    frames = [
        {"t": 60_000 + index if large else 0, "s": "TimingData", "p": {"session": name}}
        for index in range(1500 if large else 1)
    ]
    path.write_text("".join(json.dumps(frame) + "\n" for frame in frames))
    return ReplayIndex(
        session_id=name,
        total_frames=len(frames),
        duration_ms=61_500 if large else 1,
        session_started_at_ms=0,
        frames_file=path,
        index_file=tmp_path / f"{name}.json",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("paused", [False, True], ids=["playing", "paused"])
@pytest.mark.parametrize(
    "action", ["bus_close", "load", "stop", "seek", "entry_unload", "repeated_cancel"]
)
async def test_full_replay_queue_can_close_or_load_next_session(
    hass, tmp_path, monkeypatch, playback_probe, paused, action
):
    queue_created, queue_full, queues, readers = playback_probe
    first_index = _index(tmp_path, "first", large=True)
    next_index = _index(tmp_path, "next", large=False)
    transport = ReplayTransport(hass, first_index, start_from_session_start=False)
    if paused:
        transport.pause()
    bus = LiveBus(
        hass,
        AsyncMock(),
        transport_factory=lambda: transport,
        requested_streams={"TimingData"},
    )
    controller = ReplayController(hass, "entry", AsyncMock(), bus)
    controller._transport = transport
    controller._replay_active = True
    controller.session_manager._loaded_index = first_index
    controller.session_manager._state = (
        ReplayState.PAUSED if paused else ReplayState.PLAYING
    )
    controller._playback_task = hass.async_create_task(controller._run_playback())
    received = []
    next_received = asyncio.Event()

    def receive(payload):
        received.append(payload)
        if payload.get("session") == "next":
            next_received.set()

    unsubscribe = bus.subscribe("TimingData", receive)
    operation = None
    try:
        await bus.start()
        await asyncio.wait_for(queue_created.wait(), 3)
        await asyncio.wait_for(queue_full.wait(), 3)
        assert queues[0].qsize() == 500
        if action == "load":
            session = ReplaySession(
                year=2026,
                meeting_key=1,
                meeting_name="Next GP",
                session_key=2,
                session_name="Race",
                session_type="Race",
                path="2026/next/race/",
                start_utc=datetime(2026, 9, 1, tzinfo=UTC),
                end_utc=datetime(2026, 9, 1, 2, tzinfo=UTC),
            )
            controller.session_manager._available_sessions = [session]
            await controller.session_manager.async_select_session(session.unique_id)
            download = AsyncMock(return_value=next_index)
            monkeypatch.setattr(
                controller.session_manager, "_download_and_index_session", download
            )
            operation = asyncio.create_task(controller.async_prepare_and_load_session())
        elif action == "stop":
            operation = asyncio.create_task(controller.async_stop())
        elif action == "seek":
            operation = asyncio.create_task(controller.async_seek_to_ms(100))
        elif action == "entry_unload":
            entry = SimpleNamespace(entry_id="entry", runtime_data=None)
            hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
                "live_bus": bus,
                "replay_controller": controller,
            }
            monkeypatch.setattr(
                hass.config_entries,
                "async_unload_platforms",
                AsyncMock(return_value=True),
            )
            operation = asyncio.create_task(async_unload_entry(hass, entry))
        elif action == "repeated_cancel":
            joining = asyncio.Event()
            wait_for_reader = transport._async_wait_for_reader

            async def observe_join():
                joining.set()
                await wait_for_reader()

            monkeypatch.setattr(transport, "_async_wait_for_reader", observe_join)
            operation = asyncio.create_task(bus.async_close())
            await asyncio.wait_for(joining.wait(), 3)
            bus._task.cancel()
        else:
            operation = asyncio.create_task(bus.async_close())
        # Shield keeps the failed baseline alive for explicit safe cleanup below.
        await asyncio.wait_for(asyncio.shield(operation), 3)
        assert readers[0].done() and not readers[0].cancelled()
        assert not queues[0].pending_puts
        if action != "seek":
            assert bus._task is None
        else:
            assert controller.transport is not transport
            assert controller.state is (
                ReplayState.PAUSED if paused else ReplayState.PLAYING
            )
        assert received == []
        if action == "load":
            download.assert_awaited_once_with(session)
            assert controller.state is ReplayState.READY
            assert controller.transport is None
            await controller.async_play()
            await asyncio.wait_for(next_received.wait(), 3)
            assert all(payload["session"] == "next" for payload in received)
        if action == "entry_unload":
            assert "entry" not in hass.data[DOMAIN]
    finally:
        await transport.close()
        if operation is not None:
            await asyncio.wait_for(operation, 3)
        await controller.async_close()
        await bus.async_close()
        unsubscribe()
        await hass.async_block_till_done()
