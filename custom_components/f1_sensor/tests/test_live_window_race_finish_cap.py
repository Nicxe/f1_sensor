"""Late race start data must refine provisional limits through the final laps."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.f1_sensor import live_window
from custom_components.f1_sensor.live_window import LiveSessionSupervisor, SessionWindow
from custom_components.f1_sensor.signalr import LiveBus


@pytest.mark.parametrize("start_data_at", [40, 1880], ids=["before-flag", "after-flag"])
async def test_actual_race_start_refines_provisional_cap_through_finished(
    hass, monkeypatch, start_data_at
):
    """Retain final-lap coverage without freezing a longer provisional cap."""
    origin = datetime(2026, 10, 30, 19, 0, tzinfo=UTC)
    actual_start = origin - timedelta(hours=2, minutes=15)
    expected_disconnect = actual_start + timedelta(hours=3, minutes=15)
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
    observed_caps = []

    async def advance(seconds):
        nonlocal now
        now += timedelta(seconds=seconds)
        elapsed = (now - origin).total_seconds()
        assert elapsed <= 6500, "The bounded race window did not close"
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
        if elapsed in {20, start_data_at}:
            observed_caps.append(supervisor._race_extension_cap(window))

    monkeypatch.setattr(supervisor, "_interruptible_sleep", advance)
    monkeypatch.setattr(live_window, "dt_util", SimpleNamespace(utcnow=lambda: now))
    monkeypatch.setattr(bus, "last_heartbeat_age", lambda: 0.0)
    monkeypatch.setattr(bus, "last_stream_activity_age", lambda *_args: 0.0)
    try:
        reason = await supervisor._monitor_window(window, source="index")
    finally:
        await bus.async_close()

    assert observed_caps == [
        window.end_utc + timedelta(hours=2),
        expected_disconnect,
    ]
    assert reason == "disconnect-window-expired"
    assert window.disconnect_at == expected_disconnect
    assert now == expected_disconnect
