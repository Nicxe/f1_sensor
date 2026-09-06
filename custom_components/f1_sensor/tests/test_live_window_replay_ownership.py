"""A live supervisor must not close a transport handed over to replay."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from custom_components.f1_sensor import signalr
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.live_delay import LiveDelayController
from custom_components.f1_sensor.live_window import LiveSessionSupervisor, SessionWindow
from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager
from custom_components.f1_sensor.replay_mode import (
    ReplayController,
    ReplayIndex,
    ReplaySession,
    ReplayState,
)
from custom_components.f1_sensor.signalr import LiveBus


class _UpstreamTransport:
    """Replace only the external network transport, retaining the real bus."""

    async def ensure_connection(self):
        return None

    async def messages(self):
        await asyncio.Event().wait()
        yield {}

    async def close(self):
        return None


@pytest_asyncio.fixture
async def active_window(hass, tmp_path, monkeypatch):
    bus = LiveBus(
        hass,
        AsyncMock(),
        transport_factory=_UpstreamTransport,
        requested_streams={"TimingData"},
    )
    coordinator = SimpleNamespace(async_request_refresh=AsyncMock())
    supervisor = LiveSessionSupervisor(hass, coordinator, bus, http_session=AsyncMock())
    now = datetime.now(UTC)
    window = SessionWindow(
        "Italian Grand Prix",
        "Practice 3",
        "2026/practice3/",
        now - timedelta(minutes=10),
        now + timedelta(minutes=30),
        now - timedelta(hours=1),
        now + timedelta(minutes=45),
    )
    asleep = asyncio.Event()
    sleep = supervisor._interruptible_sleep

    async def observe_sleep(seconds):
        asleep.set()
        await sleep(seconds)

    monkeypatch.setattr(supervisor, "_interruptible_sleep", observe_sleep)
    controller = ReplayController(
        hass,
        "entry",
        AsyncMock(),
        bus,
        live_state=supervisor.availability,
        on_replay_ended=supervisor.wake,
    )
    session = ReplaySession(
        year=2026,
        meeting_key=1,
        meeting_name="Italian Grand Prix",
        session_key=2,
        session_name="Practice 2",
        session_type="Practice",
        path="2026/practice2/",
        start_utc=now - timedelta(days=1),
        end_utc=now - timedelta(days=1) + timedelta(hours=1),
    )
    frames = tmp_path / "replay.jsonl"
    frames.write_text(
        "".join(
            json.dumps({"t": time, "s": "TimingData", "p": {"session": "replay"}})
            + "\n"
            for time in [0, 600_000]
        )
    )
    index = ReplayIndex(
        session_id=session.unique_id,
        total_frames=2,
        duration_ms=600_000,
        session_started_at_ms=0,
        frames_file=frames,
        index_file=tmp_path / "index.json",
    )
    controller.session_manager._available_sessions = [session]
    monkeypatch.setattr(
        controller.session_manager,
        "_download_and_index_session",
        AsyncMock(return_value=index),
    )
    received = asyncio.Event()
    unsubscribe = bus.subscribe("TimingData", lambda _payload: received.set())
    manager = NoSpoilerModeManager(hass)
    monkeypatch.setattr(manager._store, "async_save", AsyncMock())
    hass.data.setdefault(DOMAIN, {})["no_spoiler_manager"] = manager
    remove_listener = manager.add_listener(lambda _active: supervisor.wake())
    delay = LiveDelayController(hass, "entry")
    activation = None

    async def activate(source="index"):
        nonlocal activation
        activation = asyncio.create_task(
            supervisor._activate_window(window, source=source)
        )
        await asyncio.wait_for(asleep.wait(), 3)
        assert supervisor.availability.reason == "live-Practice 3"
        return activation

    async def replay(paused=False):
        await controller.session_manager.async_select_session(session.unique_id)
        await controller.async_prepare_and_load_session()
        await controller.async_play()
        await asyncio.wait_for(received.wait(), 3)
        if paused:
            await controller.async_pause()
        return controller.transport

    try:
        yield SimpleNamespace(
            bus=bus,
            supervisor=supervisor,
            controller=controller,
            window=window,
            activate=activate,
            replay=replay,
            no_spoiler=manager,
            delay=delay,
            coordinator=coordinator,
        )
    finally:
        if activation is not None:
            activation.cancel()
            with suppress(asyncio.CancelledError):
                await activation
        remove_listener()
        unsubscribe()
        await controller.async_close()
        await bus.async_close()
        await delay.async_close()
        await hass.async_block_till_done()


@pytest.mark.asyncio
@pytest.mark.parametrize("paused", [False, True], ids=["playing", "paused"])
@pytest.mark.parametrize("trigger", ["no_spoiler", "window_expired", "cancel"])
async def test_old_live_window_does_not_close_replay(active_window, paused, trigger):
    probe = active_window
    activation = await probe.activate()
    transport = await probe.replay(paused)
    if trigger == "no_spoiler":
        await probe.delay.async_set_delay(30)
        await probe.no_spoiler.async_set_active(True)
    elif trigger == "window_expired":
        probe.window.disconnect_at = datetime.now(UTC) - timedelta(hours=1)
        probe.supervisor.wake()
    else:
        activation.cancel()
    with suppress(asyncio.CancelledError):
        await asyncio.wait_for(asyncio.shield(activation), 3)

    assert not transport._closed
    assert probe.bus._running
    assert probe.controller.state is (
        ReplayState.PAUSED if paused else ReplayState.PLAYING
    )
    assert probe.supervisor.availability.reason == "replay"
    assert probe.supervisor._current_window is None
    probe.coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stop_replay", [False, True], ids=["replay_active", "returned_to_live"]
)
async def test_late_primary_recovery_cannot_close_a_new_owner(
    active_window, monkeypatch, stop_replay
):
    probe = active_window
    resolving, release = asyncio.Event(), asyncio.Event()

    async def resolve_primary(**_kwargs):
        resolving.set()
        await release.wait()
        return probe.window

    monkeypatch.setattr(probe.supervisor, "_resolve_primary_window", resolve_primary)
    activation = await probe.activate("event_tracker")
    probe.supervisor.wake()
    await asyncio.wait_for(resolving.wait(), 3)
    transport = await probe.replay()
    if stop_replay:
        await probe.controller.async_stop()
        probe.bus._transport_factory = _UpstreamTransport
        await probe.bus.start()
        probe.supervisor.availability.set_state(True, "live-new-owner")
    current_task = probe.bus._task
    release.set()
    await asyncio.wait_for(asyncio.shield(activation), 3)

    assert probe.bus._running
    assert probe.bus._task is current_task
    assert not current_task.done()
    if not stop_replay:
        assert not transport._closed
        assert probe.controller.state is ReplayState.PLAYING
    assert probe.supervisor.availability.reason == (
        "live-new-owner" if stop_replay else "replay"
    )
    assert probe.supervisor._current_window is None
    probe.coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_replay_takeover_during_bus_start_preserves_heartbeat_policy(
    active_window, monkeypatch
):
    probe = active_window
    starting, release = asyncio.Event(), asyncio.Event()
    start = probe.bus.start

    async def held_first_start():
        await start()
        if not starting.is_set():
            starting.set()
            await release.wait()

    monkeypatch.setattr(probe.bus, "start", held_first_start)
    activation = asyncio.create_task(
        probe.supervisor._activate_window(probe.window, source="index")
    )
    try:
        await asyncio.wait_for(starting.wait(), 3)
        transport = await probe.replay()
        release.set()
        await asyncio.wait_for(asyncio.shield(activation), 3)
        assert not transport._closed
        assert probe.bus._running
        assert not probe.bus._expect_heartbeat
        assert probe.controller.state is ReplayState.PLAYING
        assert probe.supervisor.availability.reason == "replay"
        assert probe.supervisor._current_window is None
    finally:
        release.set()
        activation.cancel()
        with suppress(asyncio.CancelledError):
            await activation


@pytest.mark.asyncio
async def test_paused_replay_ignores_live_heartbeat_inactivity(
    active_window, monkeypatch
):
    probe = active_window
    await probe.activate()
    transport = await probe.replay(paused=True)
    guard = probe.bus._heartbeat_guard
    guard.cancel()
    await guard
    probe.bus._heartbeat_guard = None
    probe.bus._heartbeat_timeout = 0
    checked, hold = asyncio.Event(), asyncio.Event()
    sleeps = 0

    async def one_guard_cycle(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps > 1:
            checked.set()
            await hold.wait()

    monkeypatch.setattr(
        signalr,
        "asyncio",
        SimpleNamespace(sleep=one_guard_cycle, CancelledError=asyncio.CancelledError),
    )
    guard = asyncio.create_task(probe.bus._monitor_heartbeat())
    try:
        await asyncio.wait_for(checked.wait(), 3)
        assert not transport._closed
        assert probe.controller.state is ReplayState.PAUSED
        assert not probe.bus._expect_heartbeat
    finally:
        guard.cancel()
        await guard
        monkeypatch.setattr(signalr, "asyncio", asyncio)


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_replay", [False, True])
async def test_live_close_revalidates_ownership_after_await(
    active_window, monkeypatch, stop_replay
):
    probe = active_window
    activation = await probe.activate()
    close = probe.bus.async_close
    closing, release = asyncio.Event(), asyncio.Event()

    async def held_first_close():
        await close()
        if not closing.is_set():
            closing.set()
            await release.wait()

    monkeypatch.setattr(probe.bus, "async_close", held_first_close)
    probe.bus.set_heartbeat_expectation(False)
    probe.window.disconnect_at = datetime.now(UTC) - timedelta(hours=1)
    probe.supervisor.wake()
    await asyncio.wait_for(closing.wait(), 3)
    await probe.replay()
    if stop_replay:
        await probe.controller.async_stop()
        probe.bus._transport_factory = _UpstreamTransport
        await probe.bus.start()
        probe.supervisor.availability.set_state(True, "live-new-owner")
    release.set()
    await asyncio.wait_for(asyncio.shield(activation), 3)
    assert probe.supervisor.availability.reason == (
        "live-new-owner" if stop_replay else "replay"
    )
    probe.coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_idle_replay_stop_does_not_clear_retained_live_data(hass, active_window):
    probe = active_window
    hass.data[DOMAIN]["entry"] = {
        "replay_reset_callbacks": [probe.bus.reset_for_replay],
    }
    live_data = {"session": "live"}
    probe.bus.inject_message("TimingData", live_data)
    await probe.controller.async_stop()
    assert probe.bus.get_last_payload("TimingData") == live_data


@pytest.mark.asyncio
@pytest.mark.parametrize("paused", [False, True], ids=["playing", "paused"])
async def test_explicit_stop_cleans_once_and_preserves_restarted_live_data(
    hass, active_window, monkeypatch, paused
):
    probe = active_window
    await probe.activate()
    await probe.replay(paused)
    reset_calls, unload_calls, wake_calls = [], [], []
    cache_entered, release_cache, live_started = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    new_live_tasks = []
    unload = probe.controller.session_manager.async_unload

    def reset():
        reset_calls.append(True)
        probe.bus.reset_for_replay()

    async def held_cache_cleanup():
        cache_entered.set()
        await release_cache.wait()

    async def counted_unload():
        unload_calls.append(True)
        await unload()

    async def start_live():
        probe.bus._transport_factory = _UpstreamTransport
        await probe.bus.start()
        probe.supervisor.availability.set_state(True, "live-new-owner")
        probe.bus.inject_message("TimingData", {"session": "live-new-owner"})
        live_started.set()

    def wake():
        wake_calls.append(True)
        new_live_tasks.append(asyncio.create_task(start_live()))

    hass.data[DOMAIN]["entry"] = {"replay_reset_callbacks": [reset]}
    monkeypatch.setattr(
        probe.controller.session_manager, "_prune_cache", held_cache_cleanup
    )
    monkeypatch.setattr(
        probe.controller.session_manager, "async_unload", counted_unload
    )
    probe.controller._on_replay_ended = wake
    stopping = asyncio.create_task(probe.controller.async_stop())
    try:
        await asyncio.wait_for(cache_entered.wait(), 3)
        await asyncio.wait_for(live_started.wait(), 3)
        release_cache.set()
        await asyncio.wait_for(asyncio.shield(stopping), 3)
        assert len(reset_calls) == 1
        assert len(unload_calls) == 1
        assert len(wake_calls) == 1
        assert probe.controller.state is ReplayState.IDLE
        assert probe.supervisor.availability.reason == "live-new-owner"
        assert probe.bus.get_last_payload("TimingData") == {"session": "live-new-owner"}
        assert probe.bus._running
    finally:
        release_cache.set()
        await stopping
        await asyncio.gather(*new_live_tasks)
