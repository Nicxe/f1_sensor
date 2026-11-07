"""Recorded live sessions retain ownership beyond stale schedule boundaries."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.f1_sensor import live_window
from custom_components.f1_sensor.live_window import (
    LiveSessionSupervisor,
    ScheduleFetchResult,
    SessionWindow,
)
from custom_components.f1_sensor.signalr import LiveBus

_RECORDING = json.loads(
    (Path(__file__).parent / "fixtures/issue_1005_session_lifecycle.json").read_text()
)
_EVENTS = [
    (datetime.fromisoformat(frame["utc"]), frame["stream"], frame["payload"])
    for frame in _RECORDING["events"]
]


def _window(*, name="Qualifying", key=11408, path="", start=None, end=None):
    start = start or datetime(2026, 11, 7, 18, tzinfo=UTC)
    end = end or datetime(2026, 11, 7, 19, tzinfo=UTC)
    return SessionWindow(
        "São Paulo Grand Prix",
        name,
        path,
        start,
        end,
        start - timedelta(hours=1),
        end + timedelta(minutes=15),
        meeting_key=1299,
        session_key=key,
    )


async def _recorded_monitor(hass, monkeypatch, *, origin, source="index"):
    """Use the actual bus and supervisor, substituting only I/O and time."""
    now = origin
    bus = LiveBus(hass, AsyncMock())
    monkeypatch.setattr(bus, "_monotonic", lambda: now.timestamp())
    supervisor = LiveSessionSupervisor(
        hass,
        SimpleNamespace(async_request_refresh=AsyncMock()),
        bus,
        http_session=AsyncMock(),
    )
    supervisor._resolve_primary_window = AsyncMock(return_value=None)
    monkeypatch.setattr(live_window.dt_util, "utcnow", lambda: now)
    pending = iter(deepcopy(_EVENTS))
    following = next(pending, None)
    while following is not None and following[0] <= origin:
        now, stream, payload = following
        bus.inject_message(stream, payload)
        following = next(pending, None)
    now = origin
    window = _window()
    received = []
    unsubscribe = bus.subscribe("TimingData", received.append)

    async def advance(seconds):
        nonlocal now, following
        target = now + timedelta(seconds=seconds)
        assert target <= datetime(2026, 11, 7, 20, 35, tzinfo=UTC)
        while following is not None and following[0] <= target:
            now, stream, payload = following
            bus.inject_message(stream, payload)
            following = next(pending, None)
        now = target

    monkeypatch.setattr(supervisor, "_interruptible_sleep", advance)
    try:
        reason = await supervisor._monitor_window(window, source=source)
        return reason, now, received
    finally:
        unsubscribe()
        await bus.async_close()


@pytest.mark.parametrize(
    "origin",
    [
        datetime(2026, 11, 7, 18, 1, tzinfo=UTC),
        datetime(2026, 11, 7, 19, 44, tzinfo=UTC),
    ],
    ids=["before-long-red-flag", "q1-break-before-old-cutoff"],
)
@pytest.mark.parametrize("source", ["index", "event_tracker"])
async def test_recorded_qualifying_survives_long_interruption_and_q1_break(
    hass, monkeypatch, origin, source
):
    reason, closed_at, received = await _recorded_monitor(
        hass, monkeypatch, origin=origin, source=source
    )
    assert reason == "session-finished"
    assert closed_at >= datetime(2026, 11, 7, 20, 33, 43, 555000, tzinfo=UTC)
    assert closed_at <= datetime(2026, 11, 7, 20, 34, 4, tzinfo=UTC)
    boundary_update = next(
        frame["payload"]
        for frame in _RECORDING["events"]
        if frame["stream"] == "TimingData" and frame["source_line"] == 6543
    )
    assert boundary_update in received


async def _activated_monitor(
    hass,
    monkeypatch,
    *,
    window,
    origin,
    phase="Started",
    source="index",
    source_update=None,
    recover_after=None,
):
    """Run activation, real message dispatch and final shutdown without transport I/O."""
    now = origin
    bus = LiveBus(hass, AsyncMock())
    monkeypatch.setattr(bus, "_monotonic", lambda: now.timestamp())
    supervisor = LiveSessionSupervisor(
        hass,
        SimpleNamespace(async_request_refresh=AsyncMock()),
        bus,
        http_session=AsyncMock(),
    )
    supervisor._resolve_primary_window = AsyncMock(return_value=source_update)
    monkeypatch.setattr(live_window.dt_util, "utcnow", lambda: now)
    bus.inject_message(
        "SessionInfo",
        {
            "Key": window.session_key,
            "Type": "Qualifying"
            if "Qualifying" in window.session_name
            else window.session_name,
            "SessionStatus": "Started",
        },
    )
    bus.inject_message("SessionStatus", {"Status": "Started", "Started": "Started"})
    if phase != "Started":
        bus.inject_message(
            "SessionStatus",
            {
                "Status": phase,
                "Started": "Started" if phase == "Aborted" else "Finished",
            },
        )
    bus.inject_message("Heartbeat", {"Utc": now.isoformat()})
    # These cases begin with an already connected live owner. Cold starts use
    # the real queued transport in the outer-runner tests below.
    bus._mark_connection_live()
    if recover_after is not None:
        now += timedelta(seconds=80)
        origin = now
    bus.start = AsyncMock()
    close_bus = bus.async_close
    bus.async_close = AsyncMock(wraps=close_bus)
    changes = []
    supervisor.availability.add_listener(lambda active, _reason: changes.append(active))
    received = []
    unsubscribe = bus.subscribe("TimingData", received.append)
    received_lap = {"Lines": {"43": {"NumberOfLaps": 12}}}
    ends_after = 160 if recover_after is not None else 80
    observed_sources = []

    async def advance(seconds):
        nonlocal now
        now += timedelta(seconds=seconds)
        elapsed = (now - origin).total_seconds()
        assert elapsed <= ends_after + 100, "Confirmed session did not stop after Ends"
        if recover_after is None or elapsed >= recover_after:
            bus.inject_message("Heartbeat", {"Utc": now.isoformat()})
        if elapsed == ends_after - 40:
            bus.inject_message("TimingData", received_lap)
        if elapsed == ends_after:
            bus.inject_message(
                "SessionStatus", {"Status": "Ends", "Started": "Finished"}
            )
        observed_sources.append(supervisor.current_window_source)

    monkeypatch.setattr(supervisor, "_interruptible_sleep", advance)
    try:
        await supervisor._activate_window(window, source=source)
        return SimpleNamespace(
            supervisor=supervisor,
            bus=bus,
            changes=changes,
            received=received,
            expected_lap=received_lap,
            closed_at=now,
            ends_at=origin + timedelta(seconds=ends_after),
            observed_sources=observed_sources,
        )
    finally:
        unsubscribe()
        await close_bus()


@pytest.mark.parametrize(
    ("name", "phase"),
    [
        ("Practice 1", "Started"),
        ("Practice 2", "Started"),
        ("Practice 3", "Started"),
        ("Race", "Started"),
        ("Sprint", "Started"),
        ("Qualifying", "Started"),
        ("Sprint Qualifying", "Started"),
        ("Sprint Shootout", "Started"),
        ("Day 1", "Started"),
        ("Qualifying", "Aborted"),
        ("Qualifying", "Finished"),
        ("Qualifying", "Inactive"),
    ],
)
async def test_confirmed_sessions_outlive_all_old_schedule_caps(
    hass, monkeypatch, name, phase
):
    origin = datetime(2026, 11, 7, 23, tzinfo=UTC)
    result = await _activated_monitor(
        hass, monkeypatch, window=_window(name=name), origin=origin, phase=phase
    )
    assert result.received == [result.expected_lap]
    assert result.changes == [False, True, False]
    assert result.closed_at == result.ends_at + timedelta(seconds=60)
    assert result.supervisor.availability.reason == f"finished-{name}"
    result.bus.start.assert_awaited_once()
    result.bus.async_close.assert_awaited_once()


async def test_same_session_source_update_does_not_close_or_pulse_availability(
    hass, monkeypatch
):
    origin = datetime(2026, 11, 7, 18, 10, tzinfo=UTC)
    window = _window()
    primary = replace(
        window,
        path="2026/2026-11-08_São_Paulo_Grand_Prix/2026-11-07_Qualifying/",
        end_utc=window.end_utc + timedelta(minutes=20),
        disconnect_at=window.disconnect_at + timedelta(minutes=20),
    )
    result = await _activated_monitor(
        hass,
        monkeypatch,
        window=window,
        origin=origin,
        source="event_tracker",
        source_update=primary,
    )
    assert result.received == [result.expected_lap]
    assert result.changes == [False, True, False]
    assert "index" in result.observed_sources
    assert result.closed_at == result.ends_at + timedelta(seconds=60)
    result.bus.start.assert_awaited_once()
    result.bus.async_close.assert_awaited_once()


async def test_transport_silence_does_not_retire_confirmed_session_before_recovery(
    hass, monkeypatch
):
    result = await _activated_monitor(
        hass,
        monkeypatch,
        window=_window(name="Practice 1"),
        origin=datetime(2026, 11, 7, 19, 2, tzinfo=UTC),
        recover_after=100,
    )
    assert result.received == [result.expected_lap]
    assert result.changes == [False, True, False]
    assert result.closed_at == result.ends_at + timedelta(seconds=60)
    assert result.supervisor.availability.reason == "finished-Practice 1"


class _SnapshotTransport:
    """Expose an upstream snapshot and queued live frames to the real bus."""

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.frames = asyncio.Queue()
        self.connection_count = 0
        self.close_count = 0
        self.closed = False

    async def ensure_connection(self):
        self.closed = False
        self.connection_count += 1

    async def messages(self):
        yield {"R": self.snapshot}
        while True:
            yield await self.frames.get()

    async def close(self):
        if not self.closed:
            self.closed = True
            self.close_count += 1


def _feed(stream, payload, now):
    return {"M": [{"M": "feed", "A": [stream, payload, now.isoformat()]}]}


@pytest.mark.parametrize(
    ("schedule_case", "bootstrap_phase"),
    [
        (schedule, phase)
        for schedule in ["future-only", "expired-and-future", "empty"]
        for phase in ["Started", "Finalised"]
    ]
    + [("empty", "Inactive-to-Finalised")],
)
async def test_outer_runner_discovers_live_session_before_waiting_for_future_race(
    hass, monkeypatch, schedule_case, bootstrap_phase
):
    """Cold/reload discovery uses upstream identity, without a historical path."""
    now = datetime(2026, 11, 7, 19, 55, tzinfo=UTC)
    info = deepcopy(
        next(payload for _at, stream, payload in _EVENTS if stream == "SessionInfo")
    )
    initial_phase = (
        "Inactive" if bootstrap_phase == "Inactive-to-Finalised" else bootstrap_phase
    )
    info["SessionStatus"] = initial_phase
    info.pop("Path", None)
    transport = _SnapshotTransport(
        {
            "SessionInfo": info,
            "SessionStatus": {
                "Status": initial_phase,
                "Started": "Started" if initial_phase == "Started" else initial_phase,
            },
        }
    )
    bus = LiveBus(
        hass,
        AsyncMock(),
        transport_factory=lambda: transport,
        monotonic=lambda: now.timestamp(),
    )
    tomorrow = _window(
        name="Race",
        key=11412,
        start=datetime(2026, 11, 8, 17, tzinfo=UTC),
        end=datetime(2026, 11, 8, 19, tzinfo=UTC),
    )
    windows = {
        "future-only": [tomorrow],
        "expired-and-future": [_window(), tomorrow],
        "empty": [],
    }[schedule_case]
    source = SimpleNamespace(
        async_fetch_windows=AsyncMock(
            return_value=ScheduleFetchResult(
                source="index", windows=windows, index_http_status=200
            )
        )
    )
    coordinator = SimpleNamespace(async_request_refresh=AsyncMock())
    supervisor = LiveSessionSupervisor(
        hass, coordinator, bus, http_session=AsyncMock(), index_source=source
    )
    monkeypatch.setattr(live_window.dt_util, "utcnow", lambda: now)
    activated_at = None
    selected_keys = []
    changes = []
    received = []
    finalised_sent = False
    supervisor.availability.add_listener(lambda active, _reason: changes.append(active))
    unsubscribe = bus.subscribe("TimingData", received.append)

    async def finish_runner():
        if supervisor.availability.reason == "finished-Qualifying":
            supervisor._stopped = True

    coordinator.async_request_refresh.side_effect = finish_runner

    async def advance(seconds):
        nonlocal now, activated_at, finalised_sent
        now += timedelta(seconds=seconds)
        assert now <= datetime(2026, 11, 7, 20, 1, tzinfo=UTC), (
            "Live discovery waited for tomorrow's race"
        )
        await asyncio.sleep(0)
        if bootstrap_phase == "Inactive-to-Finalised" and not finalised_sent:
            finalised_sent = True
            await transport.frames.put(
                _feed("SessionInfo", {"Key": 11408, "SessionStatus": "Finalised"}, now)
            )
            await asyncio.sleep(0)
        if supervisor.current_window is not None:
            selected_keys.append(supervisor.current_window.session_key)
            if activated_at is None:
                activated_at = now
            elapsed = (now - activated_at).total_seconds()
            await transport.frames.put(
                _feed("Heartbeat", {"Utc": now.isoformat()}, now)
            )
            if elapsed == 20:
                await transport.frames.put(
                    _feed("TimingData", {"Lines": {"43": {"NumberOfLaps": 8}}}, now)
                )
            if elapsed == 40:
                await transport.frames.put(
                    _feed(
                        "SessionStatus", {"Status": "Ends", "Started": "Finished"}, now
                    )
                )
            await asyncio.sleep(0)

    monkeypatch.setattr(supervisor, "_interruptible_sleep", advance)
    try:
        await supervisor._runner()
        assert activated_at is not None
        assert set(selected_keys) == {11408}
        assert any(
            payload.get("Lines", {}).get("43", {}).get("NumberOfLaps") == 8
            for payload in received
        )
        assert changes == [False, True, False]
        assert transport.connection_count == 1
        assert transport.close_count == 1
        assert supervisor.availability.reason == "finished-Qualifying"
    finally:
        unsubscribe()
        await supervisor.async_close()
        await bus.async_close()


@pytest.mark.parametrize(
    ("partial_identity", "successor_phase"),
    [(False, "Started"), (True, "Started"), (False, "Ends")],
    ids=["coherent", "phase-arrives-later", "reconnect-to-ended-successor"],
)
async def test_new_session_handoff_rejects_late_prior_identity_and_ends(
    hass, monkeypatch, partial_identity, successor_phase
):
    """New timing without heartbeat keeps its owner despite reordered old frames."""
    now = datetime(2026, 11, 7, 19, 55, tzinfo=UTC)
    original = deepcopy(
        next(payload for _at, stream, payload in _EVENTS if stream == "SessionInfo")
    )
    original["SessionStatus"] = "Started"
    successor = {
        "Key": 11409,
        "Name": "Practice 1",
        "Type": "Practice",
        "SessionStatus": successor_phase,
        "Meeting": {"Key": 1299, "Name": "São Paulo Grand Prix"},
        "StartDate": "2026-11-07T20:00:00",
        "EndDate": "2026-11-07T21:00:00",
        "GmtOffset": "00:00:00",
    }
    transport = _SnapshotTransport(
        {"SessionInfo": original, "SessionStatus": {"Status": "Started"}}
    )
    bus = LiveBus(
        hass,
        AsyncMock(),
        transport_factory=lambda: transport,
        monotonic=lambda: now.timestamp(),
    )
    source = SimpleNamespace(
        async_fetch_windows=AsyncMock(
            return_value=ScheduleFetchResult(
                source="index", windows=[], index_http_status=200
            )
        )
    )
    coordinator = SimpleNamespace(async_request_refresh=AsyncMock())
    supervisor = LiveSessionSupervisor(
        hass, coordinator, bus, http_session=AsyncMock(), index_source=source
    )
    monkeypatch.setattr(live_window.dt_util, "utcnow", lambda: now)
    active_origin = None
    keys = []
    changes = []
    supervisor.availability.add_listener(lambda active, _reason: changes.append(active))

    async def finish_runner():
        if supervisor.availability.reason == "finished-Practice 1":
            supervisor._stopped = True

    coordinator.async_request_refresh.side_effect = finish_runner

    async def advance(seconds):
        nonlocal now, active_origin
        now += timedelta(seconds=seconds)
        assert now < datetime(2026, 11, 7, 20, 1, tzinfo=UTC)
        await asyncio.sleep(0)
        if supervisor.current_window is None:
            return
        if active_origin is None:
            active_origin = now
        elapsed = (now - active_origin).total_seconds()
        await transport.frames.put(
            _feed("TimingData", {"Lines": {"43": {"NumberOfLaps": 9}}}, now)
        )
        if elapsed == 20:
            info = deepcopy(successor)
            if partial_identity:
                info.pop("SessionStatus")
            await transport.frames.put(_feed("SessionInfo", info, now))
        if elapsed == 40:
            old_time = active_origin - timedelta(hours=1)
            await transport.frames.put(_feed("SessionInfo", original, old_time))
            await transport.frames.put(
                _feed("SessionStatus", {"Status": "Ends"}, old_time)
            )
        if partial_identity and elapsed == 60:
            await transport.frames.put(
                _feed("SessionStatus", {"Status": "Started", "Started": "Started"}, now)
            )
        if elapsed == 100:
            await transport.frames.put(
                _feed("SessionStatus", {"Status": "Ends", "Started": "Finished"}, now)
            )
        await asyncio.sleep(0)
        keys.append(supervisor.current_window.session_key)

    monkeypatch.setattr(supervisor, "_interruptible_sleep", advance)
    try:
        await supervisor._runner()
        assert keys[0] == 11408
        assert keys[-1] == 11409
        first_successor = keys.index(11409)
        assert set(keys[first_successor:]) == {11409}
        assert changes[0] is False
        assert changes[-1] is False
        assert all(changes[1:-1])
        assert supervisor.availability.reason == "finished-Practice 1"
        assert transport.connection_count == 1
        assert transport.close_count == 1
    finally:
        await supervisor.async_close()
        await bus.async_close()


@pytest.mark.parametrize(
    ("info_status", "stream_status", "cached_only", "terminal_history"),
    [
        ("Unknown", "Unknown", False, False),
        ("Ends", "Started", False, False),
        ("Started", "Started", True, False),
        ("Started", "Started", False, True),
    ],
    ids=[
        "unrecognised-phase",
        "stale-started-snapshot-after-ends",
        "previous-generation-info-with-new-heartbeat-only",
        "newer-history-ends-overrides-started-snapshot",
    ],
)
async def test_outer_runner_does_not_acquire_unknown_or_ended_snapshot(
    hass, monkeypatch, info_status, stream_status, cached_only, terminal_history
):
    now = datetime(2026, 11, 7, 19, 55, tzinfo=UTC)
    info = deepcopy(
        next(payload for _at, stream, payload in _EVENTS if stream == "SessionInfo")
    )
    info["SessionStatus"] = info_status
    snapshot = (
        {"Heartbeat": {"Utc": now.isoformat()}}
        if cached_only
        else {"SessionInfo": info, "SessionStatus": {"Status": stream_status}}
    )
    if terminal_history:
        snapshot["SessionData"] = {
            "StatusSeries": [
                {
                    "Utc": (now - timedelta(seconds=10)).isoformat(),
                    "SessionStatus": "Ends",
                }
            ]
        }
    transport = _SnapshotTransport(snapshot)
    bus = LiveBus(hass, AsyncMock(), transport_factory=lambda: transport)
    if cached_only:
        bus.inject_message("SessionInfo", info)
        bus.inject_message("SessionStatus", {"Status": "Started", "Started": "Started"})
    tomorrow = _window(
        name="Race",
        key=11412,
        start=now + timedelta(days=1),
        end=now + timedelta(days=1, hours=2),
    )
    source = SimpleNamespace(
        async_fetch_windows=AsyncMock(
            return_value=ScheduleFetchResult(
                source="index", windows=[tomorrow], index_http_status=200
            )
        )
    )
    supervisor = LiveSessionSupervisor(
        hass,
        SimpleNamespace(async_request_refresh=AsyncMock()),
        bus,
        http_session=AsyncMock(),
        index_source=source,
    )
    monkeypatch.setattr(live_window.dt_util, "utcnow", lambda: now)
    changes = []
    supervisor.availability.add_listener(lambda active, _reason: changes.append(active))

    async def advance(seconds):
        nonlocal now
        assert supervisor.current_window is None, (
            "Unconfirmed snapshot acquired a live session"
        )
        now += timedelta(seconds=min(seconds, 1))
        if seconds > live_window.ACTIVE_REFRESH.total_seconds():
            supervisor._stopped = True
        await asyncio.sleep(0)

    monkeypatch.setattr(supervisor, "_interruptible_sleep", advance)
    try:
        await supervisor._runner()
        assert not any(changes)
        assert supervisor.current_window is None
        assert transport.close_count == 1
    finally:
        await supervisor.async_close()
        await bus.async_close()


@pytest.mark.parametrize(
    "newer_start", [False, True], ids=["old-start-snapshot", "dated-restart"]
)
async def test_closed_session_reopens_only_for_a_demonstrably_newer_start(
    hass, monkeypatch, newer_start
):
    """A real close cannot make old Started snapshots eligible for a new owner."""
    now = datetime(2026, 11, 7, 19, 55, tzinfo=UTC)
    initial_time = now
    info = deepcopy(
        next(payload for _at, stream, payload in _EVENTS if stream == "SessionInfo")
    )
    info["SessionStatus"] = "Started"
    transport = _SnapshotTransport(
        {"SessionInfo": info, "SessionStatus": {"Status": "Started"}}
    )
    bus = LiveBus(
        hass,
        AsyncMock(),
        transport_factory=lambda: transport,
        monotonic=lambda: now.timestamp(),
    )
    source = SimpleNamespace(
        async_fetch_windows=AsyncMock(
            return_value=ScheduleFetchResult(
                source="index", windows=[], index_http_status=200
            )
        )
    )
    coordinator = SimpleNamespace(async_request_refresh=AsyncMock())
    supervisor = LiveSessionSupervisor(
        hass, coordinator, bus, http_session=AsyncMock(), index_source=source
    )
    monkeypatch.setattr(live_window.dt_util, "utcnow", lambda: now)
    monkeypatch.setattr(
        live_window, "time", SimpleNamespace(monotonic=lambda: now.timestamp())
    )
    changes = []
    supervisor.availability.add_listener(lambda active, _reason: changes.append(active))
    active_origin = None
    completed = 0

    async def after_close():
        nonlocal completed, now, active_origin
        if supervisor.availability.reason != "finished-Qualifying":
            return
        completed += 1
        if completed == 2:
            supervisor._stopped = True
            return
        now += timedelta(minutes=20)
        active_origin = None
        start_time = now if newer_start else initial_time
        transport.snapshot = {
            "SessionInfo": info,
            "SessionStatus": {"Status": "Started", "Started": "Started"},
            "SessionData": {
                "StatusSeries": [
                    {"Utc": start_time.isoformat(), "SessionStatus": "Started"}
                ]
            },
        }

    coordinator.async_request_refresh.side_effect = after_close

    async def advance(seconds):
        nonlocal now, active_origin
        if completed == 1 and supervisor.current_window is None and seconds > 20:
            supervisor._stopped = True
            return
        now += timedelta(seconds=seconds)
        assert now < initial_time + timedelta(minutes=25)
        await asyncio.sleep(0)
        if supervisor.current_window is not None:
            if active_origin is None:
                active_origin = now
            elapsed = (now - active_origin).total_seconds()
            await transport.frames.put(
                _feed("Heartbeat", {"Utc": now.isoformat()}, now)
            )
            if elapsed == 40:
                await transport.frames.put(
                    _feed("SessionStatus", {"Status": "Ends"}, now)
                )
            await asyncio.sleep(0)

    monkeypatch.setattr(supervisor, "_interruptible_sleep", advance)
    try:
        await supervisor._runner()
        assert completed == (2 if newer_start else 1)
        assert changes.count(True) == (2 if newer_start else 1)
        assert changes[-1] is False
        assert transport.connection_count == 2
        assert transport.close_count == 2
    finally:
        await supervisor.async_close()
        await bus.async_close()


@pytest.mark.parametrize("armed_name", ["Race", "Practice 1"])
async def test_discovered_session_does_not_retire_an_unstarted_schedule_candidate(
    hass, monkeypatch, armed_name
):
    """Discovering ongoing qualifying must leave the next session selectable."""
    now = datetime(2026, 11, 7, 19, 55, tzinfo=UTC)
    origin = now
    info = deepcopy(
        next(payload for _at, stream, payload in _EVENTS if stream == "SessionInfo")
    )
    info["SessionStatus"] = "Started"
    transport = _SnapshotTransport(
        {"SessionInfo": info, "SessionStatus": {"Status": "Started"}}
    )
    bus = LiveBus(
        hass,
        AsyncMock(),
        transport_factory=lambda: transport,
        monotonic=lambda: now.timestamp(),
    )
    supervisor = LiveSessionSupervisor(
        hass,
        SimpleNamespace(async_request_refresh=AsyncMock()),
        bus,
        http_session=AsyncMock(),
    )
    candidate = _window(
        name=armed_name,
        key=11412,
        start=now + timedelta(minutes=30),
        end=now + timedelta(hours=2),
    )
    observed_keys = []
    monkeypatch.setattr(live_window.dt_util, "utcnow", lambda: now)

    async def advance(seconds):
        nonlocal now
        now += timedelta(seconds=seconds)
        assert now <= origin + timedelta(minutes=3)
        await asyncio.sleep(0)
        observed_keys.append(supervisor.current_window.session_key)
        await transport.frames.put(_feed("Heartbeat", {"Utc": now.isoformat()}, now))
        if now >= origin + timedelta(seconds=40):
            await transport.frames.put(_feed("SessionStatus", {"Status": "Ends"}, now))
        await asyncio.sleep(0)

    monkeypatch.setattr(supervisor, "_interruptible_sleep", advance)
    try:
        await supervisor._activate_window(replace(candidate), source="index")
        assert 11408 in observed_keys
        selected = await supervisor._select_window([candidate], source="index")
        assert selected is not None, "The unstarted schedule candidate was retired"
        assert selected.session_key == 11412
        assert supervisor.availability.reason == "finished-Qualifying"
    finally:
        await supervisor.async_close()
        await bus.async_close()
