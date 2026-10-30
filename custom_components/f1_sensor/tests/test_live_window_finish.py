"""Final laps must outlive Finished without defeating bounded live windows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.f1_sensor import live_window
from custom_components.f1_sensor.live_window import LiveSessionSupervisor, SessionWindow
from custom_components.f1_sensor.signalr import LiveBus

_RACE = json.loads(
    (Path(__file__).parent / "fixtures" / "issue_958_session_finish.json").read_text()
)["sources"][0]
_LAST_LAP = next(
    event["payload"]
    for event in _RACE["events"]
    if event["stream"] == "TimingData"
    and event["payload"].get("Lines", {}).get("27", {}).get("NumberOfLaps") == 56
)


async def _run_window(
    hass,
    monkeypatch,
    events,
    *,
    session_name="Practice 1",
    source="index",
    heartbeat_age=0.0,
    activity_age=0.0,
    disconnect_seconds=1800,
):
    """Drive the real supervisor and bus using only a controlled clock."""
    origin = datetime(2026, 10, 30, 19, 30, tzinfo=UTC)
    now = origin
    bus = LiveBus(hass, AsyncMock())
    bus.inject_message("SessionInfo", {"Key": 11396, "SessionStatus": "Started"})
    bus.inject_message("SessionStatus", {"Status": "Started", "Started": "Started"})
    supervisor = LiveSessionSupervisor(
        hass,
        SimpleNamespace(async_request_refresh=AsyncMock()),
        bus,
        http_session=AsyncMock(),
    )
    supervisor._resolve_primary_window = AsyncMock(return_value=None)
    window = SessionWindow(
        "United States Grand Prix",
        session_name,
        "",
        origin - timedelta(hours=2),
        origin + timedelta(seconds=disconnect_seconds) - timedelta(minutes=15),
        origin - timedelta(hours=3),
        origin + timedelta(seconds=disconnect_seconds),
        meeting_key=1297,
        session_key=11396,
    )
    pending = iter(events)
    following = next(pending, None)
    received = []
    unsubscribe = bus.subscribe("TimingData", received.append)

    async def advance(seconds):
        nonlocal now, following
        now += timedelta(seconds=seconds)
        elapsed = (now - origin).total_seconds()
        assert elapsed <= 4000, "Live window failed to stop within its bounded lifetime"
        while following is not None and following[0] <= elapsed:
            _, stream, payload = following
            bus.inject_message(stream, payload)
            following = next(pending, None)

    monkeypatch.setattr(supervisor, "_interruptible_sleep", advance)
    monkeypatch.setattr(live_window.dt_util, "utcnow", lambda: now)
    monkeypatch.setattr(bus, "last_heartbeat_age", lambda: heartbeat_age)
    monkeypatch.setattr(bus, "last_stream_activity_age", lambda *_args: activity_age)
    try:
        reason = await supervisor._monitor_window(window, source=source)
        eligible = await supervisor._select_window([window], source=source)
        return reason, (now - origin).total_seconds(), received, eligible
    finally:
        unsubscribe()
        await bus.async_close()


@pytest.mark.parametrize("source", ["index", "event_tracker"])
@pytest.mark.parametrize(
    "session_name",
    [
        "Practice 1",
        "Practice 2",
        "Practice 3",
        "Race",
        "Sprint",
        "Qualifying",
        "Sprint Qualifying",
        "Sprint Shootout",
        "Day 1",
    ],
)
async def test_all_session_types_wait_for_late_lap_and_finalisation(
    hass, monkeypatch, session_name, source
):
    events = [
        (20, "SessionStatus", {"Status": "Finished", "Started": "Finished"}),
        # A fixed 180-second replacement would still lose this valid lap.
        (220, "TimingData", _LAST_LAP),
        (240, "SessionStatus", {"Status": "Finalised", "Started": "Finished"}),
        (260, "SessionStatus", {"Status": "Ends", "Started": "Finished"}),
    ]
    reason, elapsed, received, eligible = await _run_window(
        hass, monkeypatch, events, session_name=session_name, source=source
    )
    assert received == [_LAST_LAP]
    assert reason == "session-finished"
    assert elapsed == 300
    assert eligible is None


async def test_stale_heartbeat_does_not_cut_fresh_timing(hass, monkeypatch):
    events = [
        (20, "SessionStatus", {"Status": "Finished", "Started": "Finished"}),
        (100, "TimingData", _LAST_LAP),
        (120, "SessionStatus", {"Status": "Finalised", "Started": "Finished"}),
    ]
    reason, _, received, _ = await _run_window(
        hass, monkeypatch, events, heartbeat_age=80.0
    )
    assert received == [_LAST_LAP]
    assert reason == "session-finished"


async def test_delayed_race_retains_extended_window_through_last_laps(
    hass, monkeypatch
):
    origin = datetime(2026, 10, 30, 19, 30, tzinfo=UTC)
    events = [
        (
            0,
            "SessionData",
            {
                "StatusSeries": {
                    "1": {
                        "SessionStatus": "Started",
                        "Utc": (origin - timedelta(hours=1)).isoformat(),
                    }
                }
            },
        ),
        # Finish at the old scheduled end + 45-minute extension limit.
        (1840, "SessionStatus", {"Status": "Finished", "Started": "Finished"}),
        (1940, "TimingData", _LAST_LAP),
        (1960, "SessionStatus", {"Status": "Finalised", "Started": "Finished"}),
    ]
    reason, elapsed, received, eligible = await _run_window(
        hass, monkeypatch, events, session_name="Race", disconnect_seconds=40
    )
    assert received == [_LAST_LAP]
    assert reason == "session-finished"
    assert elapsed == 2020
    assert eligible is None


@pytest.mark.parametrize("active_feed", [False, True])
async def test_missing_finalisation_still_stops_on_idle_or_window_cap(
    hass, monkeypatch, active_feed
):
    reason, elapsed, _, _ = await _run_window(
        hass,
        monkeypatch,
        [(20, "SessionStatus", {"Status": "Finished", "Started": "Finished"})],
        heartbeat_age=0.0 if active_feed else 80.0,
        activity_age=0.0 if active_feed else 80.0,
        disconnect_seconds=40,
    )
    if active_feed:
        assert reason == "disconnect-window-expired"
        assert elapsed == 1840
    else:
        assert reason == "heartbeat-timeout-80s"
        assert elapsed == 20
