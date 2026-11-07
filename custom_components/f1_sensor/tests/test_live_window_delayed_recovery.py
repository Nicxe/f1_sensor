"""Delayed sessions recover from feed evidence, not a longer scheduled window."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.f1_sensor import live_window
from custom_components.f1_sensor.live_window import (
    LiveSessionSupervisor,
    _window_identity,
    build_session_windows,
)
from custom_components.f1_sensor.signalr import LiveBus

_EVIDENCE = json.loads(
    (Path(__file__).parent / "fixtures/delayed_qualifying_2026.json").read_text()
)


def _utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.fixture
def delayed_session(hass, monkeypatch):
    """Use the real bus and supervisor with controlled transport and wall time."""
    clock = SimpleNamespace(now=_utc("2026-11-07T19:52:00Z"))
    bus = LiveBus(hass, AsyncMock())
    supervisor = LiveSessionSupervisor(
        hass,
        SimpleNamespace(async_request_refresh=AsyncMock()),
        bus,
        http_session=AsyncMock(),
    )
    case = SimpleNamespace(
        clock=clock,
        bus=bus,
        supervisor=supervisor,
        windows=build_session_windows(_EVIDENCE["index"]),
        snapshot=deepcopy(_EVIDENCE["snapshot"]),
        heartbeat_offset=timedelta(),
        ticks=0,
        updates=[],
        publication=[],
    )

    def seed():
        for stream, payload in case.snapshot.items():
            payload = deepcopy(payload)
            if stream == "SessionData":
                for series in ("Series", "StatusSeries"):
                    payload[series] = [
                        item
                        for item in payload.get(series, [])
                        if _utc(item["Utc"]) <= clock.now
                    ]
            bus.inject_message(stream, payload)

    async def advance(seconds):
        case.ticks += 1
        assert case.ticks < 800, "A recovery window failed to stop"
        clock.now += timedelta(seconds=seconds)
        bus.inject_message(
            "Heartbeat", {"Utc": (clock.now + case.heartbeat_offset).isoformat()}
        )
        while case.updates and _utc(case.updates[0]["Utc"]) <= clock.now:
            item = case.updates.pop(0)
            bus.inject_message("SessionData", {"StatusSeries": {"50": item}})
            bus.inject_message("SessionStatus", {"Status": item["SessionStatus"]})
            bus.inject_message("TimingData", {"state": item["SessionStatus"]})

    monkeypatch.setattr(live_window.dt_util, "utcnow", lambda: clock.now)
    monkeypatch.setattr(bus, "start", AsyncMock(side_effect=seed))
    monkeypatch.setattr(supervisor, "_interruptible_sleep", advance)
    supervisor.availability.add_listener(
        lambda active, reason: case.publication.append((clock.now, active, reason))
    )
    case.seed = seed
    case.advance = advance
    return case


@pytest.mark.parametrize("start", ["19:10:00", "19:52:00", "20:10:00"])
async def test_delayed_qualifying_survives_window_and_reload_through_final_laps(
    delayed_session, start
):
    """Recorded Q1/Q2 timing and synthetic Q3 completion survive the old cutoff."""
    case = delayed_session
    case.clock.now = _utc(f"2026-11-07T{start}Z")
    case.updates = [
        deepcopy(item)
        for item in _EVIDENCE["snapshot"]["SessionData"]["StatusSeries"]
        if _utc(item["Utc"]) > case.clock.now
    ] + [
        {"Utc": "2026-11-07T20:15:00Z", "SessionStatus": "Inactive"},
        {"Utc": "2026-11-07T20:18:00Z", "SessionStatus": "Started"},
        {"Utc": "2026-11-07T20:30:00Z", "SessionStatus": "Finished"},
        {"Utc": "2026-11-07T20:33:00Z", "SessionStatus": "Finalised"},
        {"Utc": "2026-11-07T20:34:00Z", "SessionStatus": "Ends"},
    ]
    received = []
    unsubscribe = case.bus.subscribe("TimingData", received.append)
    window = await case.supervisor._select_window(case.windows, source="index")
    assert window.session_key == case.windows[0].session_key
    assert getattr(window, "recovery", False) is (start != "19:10:00")
    try:
        await case.supervisor._activate_window(window, source="index")
    finally:
        unsubscribe()
        await case.bus.async_close()
    assert received[-1] == {"state": "Ends"}
    assert case.clock.now == _utc("2026-11-07T20:35:00Z")
    assert _window_identity(window) in case.supervisor._terminal_sessions
    assert not case.supervisor.availability.is_live
    assert (
        await case.supervisor._select_window(case.windows, source="index")
        is case.windows[1]
    )
    if window.recovery:
        first_live = next(at for at, active, _ in case.publication if active)
        assert first_live > _utc(f"2026-11-07T{start}Z")


@pytest.mark.parametrize(
    "fault",
    ["session", "meeting", "missing", "stale-start", "future", "heartbeat"],
)
async def test_unconfirmed_recovery_stays_hidden_and_retries_only_within_bounds(
    delayed_session, fault
):
    """A Started hint, wrong identity or old/future snapshot is not live proof."""
    case = delayed_session
    if fault == "session":
        case.snapshot["SessionInfo"]["Key"] += 1
    elif fault == "meeting":
        case.snapshot["SessionInfo"]["Meeting"]["Key"] += 1
    elif fault == "missing":
        case.snapshot["SessionData"] = {}
    elif fault == "heartbeat":
        case.heartbeat_offset = timedelta(days=-1)
    else:
        offset = timedelta(days=1 if fault == "future" else -1)
        case.snapshot["SessionData"]["StatusSeries"] = [
            {"Utc": (case.clock.now + offset).isoformat(), "SessionStatus": "Started"},
            {"Utc": case.clock.now.isoformat(), "SessionStatus": "Inactive"},
        ]
    window = await case.supervisor._select_window(case.windows, source="index")
    await case.supervisor._activate_window(window, source="index")
    assert case.ticks == 6
    assert not any(active for _, active, _ in case.publication)
    assert not case.bus._running
    assert (
        await case.supervisor._select_window(case.windows, source="index")
        is case.windows[1]
    )
    case.clock.now += live_window.IDLE_REFRESH
    assert (await case.supervisor._select_window(case.windows, source="index")).recovery
    case.clock.now = window.end_utc + live_window.SESSION_RECOVERY_HORIZON
    assert (
        await case.supervisor._select_window(case.windows, source="index")
        is case.windows[1]
    )


@pytest.mark.parametrize("terminal", ["Finalised", "Ends"])
@pytest.mark.parametrize("resume", [False, True])
async def test_terminal_history_requires_explicit_dated_resumption(
    delayed_session, terminal, resume
):
    """Inactive after completion cannot revive it; a real subsequent start can."""
    case = delayed_session
    history = case.snapshot["SessionData"]["StatusSeries"]
    case.snapshot["SessionInfo"]["SessionStatus"] = terminal
    history[:] = [
        {"Utc": "2026-11-07T19:00:00Z", "SessionStatus": "Started"},
        {"Utc": "2026-11-07T19:30:00Z", "SessionStatus": terminal},
        {"Utc": "2026-11-07T19:40:00Z", "SessionStatus": "Inactive"},
    ]
    if resume:
        history.append({"Utc": "2026-11-07T19:45:00Z", "SessionStatus": "Started"})
        case.updates = [{"Utc": "2026-11-07T19:54:00Z", "SessionStatus": "Ends"}]
    window = await case.supervisor._select_window(case.windows, source="index")
    await case.supervisor._activate_window(window, source="index")
    assert any(active for _, active, _ in case.publication) is resume
    assert _window_identity(window) in case.supervisor._terminal_sessions
    if resume:
        assert case.clock.now == _utc("2026-11-07T19:55:00Z")
        assert not case.updates


async def test_fresh_ends_during_recovery_is_not_cleared_by_resumption_history(
    delayed_session, monkeypatch
):
    case = delayed_session
    case.snapshot["SessionInfo"]["SessionStatus"] = "Ends"
    case.snapshot["SessionData"]["StatusSeries"] = [
        {"Utc": "2026-11-07T19:00:00Z", "SessionStatus": "Started"},
        {"Utc": "2026-11-07T19:30:00Z", "SessionStatus": "Ends"},
        {"Utc": "2026-11-07T19:45:00Z", "SessionStatus": "Started"},
    ]

    async def finish(seconds):
        await case.advance(seconds)
        if case.ticks == 1:
            case.bus.inject_message("SessionStatus", {"Status": "Ends"})

    monkeypatch.setattr(case.supervisor, "_interruptible_sleep", finish)
    window = await case.supervisor._select_window(case.windows, source="index")
    await case.supervisor._activate_window(window, source="index")
    assert case.clock.now == _utc("2026-11-07T19:53:20Z")
    assert _window_identity(window) in case.supervisor._terminal_sessions


async def test_recovery_horizon_preserves_final_configured_delay_drain(delayed_session):
    case = delayed_session
    case.clock.now = _utc("2026-11-07T20:58:00Z")
    case.snapshot["SessionData"]["StatusSeries"] = [
        {"Utc": "2026-11-07T20:50:00Z", "SessionStatus": "Started"}
    ]
    case.supervisor._delay_controller = SimpleNamespace(current=300)
    case.updates = [{"Utc": "2026-11-08T00:04:40Z", "SessionStatus": "Ends"}]
    window = await case.supervisor._select_window(case.windows, source="index")
    await case.supervisor._activate_window(window, source="index")
    assert case.clock.now == _utc("2026-11-08T00:10:40Z")
    assert _window_identity(window) in case.supervisor._terminal_sessions


@pytest.mark.parametrize("repeat_starts", [False, True])
async def test_late_actual_start_has_a_frozen_feed_based_continuation_budget(
    delayed_session, repeat_starts
):
    case = delayed_session
    case.clock.now = _utc("2026-11-07T20:58:00Z")
    case.snapshot["SessionData"]["StatusSeries"] = [
        {"Utc": "2026-11-07T20:50:00Z", "SessionStatus": "Started"}
    ]
    if repeat_starts:
        case.updates = [
            {"Utc": "2026-11-07T22:30:00Z", "SessionStatus": "Started"},
            {"Utc": "2026-11-07T23:30:00Z", "SessionStatus": "Started"},
        ]
    window = await case.supervisor._select_window(case.windows, source="index")
    await case.supervisor._activate_window(window, source="index")
    assert any(active for _, active, _ in case.publication)
    assert case.clock.now == _utc("2026-11-08T00:05:00Z")
    assert not case.supervisor._terminal_sessions
    assert (
        await case.supervisor._select_window(case.windows, source="index")
        is case.windows[1]
    )


async def test_future_snapshot_does_not_poison_valid_later_deltas(delayed_session):
    case = delayed_session
    case.seed()
    status = live_window._LiveSessionStatus()
    status.update_info(case.snapshot["SessionInfo"])
    status.update_data(
        {"StatusSeries": [{"Utc": "2026-11-08T19:00:00Z", "SessionStatus": "Started"}]}
    )
    status.update_data(case.bus.get_last_payload("SessionData"))
    case.bus.inject_message("Heartbeat", {"Utc": case.clock.now.isoformat()})
    assert (
        case.supervisor._recovery_status(case.windows[0], status, case.clock.now)
        == "Started"
    )


async def test_recovered_identity_change_returns_to_later_session(
    delayed_session, monkeypatch
):
    case = delayed_session
    window = await case.supervisor._select_window(case.windows, source="index")

    async def change_session(seconds):
        await case.advance(seconds)
        if case.ticks == 2:
            case.windows[1].connect_at = case.clock.now - timedelta(minutes=1)
            case.bus.inject_message(
                "SessionInfo",
                {"Key": case.windows[1].session_key, "Meeting": {"Key": 1299}},
            )

    monkeypatch.setattr(case.supervisor, "_interruptible_sleep", change_session)
    await case.supervisor._activate_window(window, source="index")
    assert case.ticks == 2
    assert not case.supervisor.availability.is_live
    assert (
        await case.supervisor._select_window(case.windows, source="index")
        is case.windows[1]
    )


async def test_normal_windows_and_fresh_feed_take_priority_without_start_veto(
    delayed_session,
):
    case = delayed_session
    qualifying, race = case.windows
    case.clock.now = qualifying.start_utc - timedelta(minutes=30)
    assert (
        await case.supervisor._select_window(case.windows, source="index") is qualifying
    )
    case.clock.now = _utc("2026-11-07T19:52:00Z")
    race.connect_at = case.clock.now - timedelta(minutes=10)
    assert await case.supervisor._select_window(case.windows, source="index") is race
    case.seed()
    case.bus.inject_message("Heartbeat", {"Utc": case.clock.now.isoformat()})
    selected = await case.supervisor._select_window(case.windows, source="index")
    assert selected.session_key == qualifying.session_key
    assert selected.recovery
