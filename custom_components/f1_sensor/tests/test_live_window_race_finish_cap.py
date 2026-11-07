"""Late start metadata cannot impose a lifetime on an active race."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.f1_sensor import live_window
from custom_components.f1_sensor.live_window import LiveSessionSupervisor, SessionWindow
from custom_components.f1_sensor.signalr import LiveBus


@pytest.mark.parametrize("start_data_at", [40, 1880], ids=["before-flag", "after-flag"])
async def test_late_actual_race_start_cannot_cut_off_final_laps(
    hass, monkeypatch, start_data_at
):
    """Receiving actual start history must not close a healthy delayed race."""
    origin = datetime(2026, 10, 30, 19, 0, tzinfo=UTC)
    actual_start = origin - timedelta(hours=2, minutes=15)
    old_race_limit = actual_start + timedelta(hours=3, minutes=15)
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
    window = SessionWindow(
        meeting_name="United States Grand Prix",
        session_name="Race",
        path="",
        start_utc=actual_start,
        end_utc=origin - timedelta(minutes=15),
        connect_at=actual_start - timedelta(hours=1),
        disconnect_at=origin,
        meeting_key=1297,
        session_key=11396,
    )
    delivered = []
    unsubscribe = bus.subscribe("TimingData", delivered.append)
    final_lap = {"Lines": {"27": {"NumberOfLaps": 56}}}

    async def advance(seconds):
        nonlocal now
        now += timedelta(seconds=seconds)
        elapsed = (now - origin).total_seconds()
        assert elapsed <= 4500, "The ended race did not finish its drain"
        if elapsed == start_data_at:
            bus.inject_message(
                "SessionData",
                {
                    "StatusSeries": {
                        "1": {
                            "SessionStatus": "Started",
                            "Utc": actual_start.isoformat(),
                        }
                    }
                },
            )
        if elapsed == 1840:
            # The flag arrives after the scheduled end + 45-minute bound.
            bus.inject_message(
                "SessionStatus", {"Status": "Finished", "Started": "Finished"}
            )
        if elapsed == 4200:
            assert now > old_race_limit
            bus.inject_message("TimingData", final_lap)
        if elapsed == 4380:
            bus.inject_message("SessionStatus", {"Status": "Finalised"})
        if elapsed == 4400:
            bus.inject_message("SessionStatus", {"Status": "Ends"})

    monkeypatch.setattr(supervisor, "_interruptible_sleep", advance)
    monkeypatch.setattr(live_window, "dt_util", SimpleNamespace(utcnow=lambda: now))
    monkeypatch.setattr(bus, "last_heartbeat_age", lambda: 0.0)
    monkeypatch.setattr(bus, "last_stream_activity_age", lambda *_args: 0.0)
    try:
        reason = await supervisor._monitor_window(window, source="index")
    finally:
        unsubscribe()
        await bus.async_close()

    assert delivered == [final_lap]
    assert reason == "session-finished"
    assert now == origin + timedelta(seconds=4460)
