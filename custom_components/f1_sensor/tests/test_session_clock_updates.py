"""Regressions for clocks remaining visible to Home Assistant (issue 641)."""

from datetime import UTC, datetime, timedelta
import logging
from unittest.mock import Mock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.entity_component import EntityComponent
import pytest

from custom_components.f1_sensor.__init__ import (
    SessionClockCoordinator,
    _reset_replay_sensitive_coordinator_state,
)
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.replay_mode import ReplayState
from custom_components.f1_sensor.sensor import (
    F1RaceTimeToThreeHourLimitSensor,
    F1SessionTimeElapsedSensor,
    F1SessionTimeRemainingSensor,
)

START = datetime(2026, 9, 4, 14, tzinfo=UTC)


@pytest.fixture
async def running_clock(hass, monkeypatch, mock_config_entry):
    """Set up a real coordinator with a controllable local timer and clock."""
    callbacks = []
    cancels = []

    def subscribe(_hass, action, interval):
        assert interval == timedelta(seconds=1)
        cancel = Mock()
        callbacks.append(action)
        cancels.append(cancel)
        return cancel

    monkeypatch.setattr(
        "custom_components.f1_sensor.__init__.async_track_time_interval", subscribe
    )
    now = [START]
    live = LiveAvailabilityTracker()
    mock_config_entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    coordinator = SessionClockCoordinator(
        hass, object(), live_state=live, config_entry=mock_config_entry
    )
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now[0])
    await coordinator.async_config_entry_first_refresh()
    live.set_state(True, "live-Race")
    coordinator._on_session_info({"Type": "Race", "Name": "Race"})
    coordinator._on_session_data(
        {"StatusSeries": {"0": {"Utc": START.isoformat(), "SessionStatus": "Started"}}}
    )
    coordinator._on_session_status({"Status": "Started"})
    coordinator._on_extrapolated_clock(
        {"Utc": START.isoformat(), "Remaining": "02:00:00", "Extrapolating": True}
    )
    coordinator._on_heartbeat({"Utc": START.isoformat()})
    yield coordinator, now, live, callbacks, cancels
    await coordinator.async_close()


async def test_clock_sensors_update_after_successive_heartbeats(
    hass, running_clock, cleanup_test_entity_components
):
    """All three HA entities must advance, not just the private clock state."""
    coordinator, now, live, _, _ = running_clock
    entry_id = "clock_updates"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        "live_state": live,
        "live_bus": Mock(last_stream_activity_age=Mock(return_value=0)),
    }
    sensors = [
        cls(coordinator, f"{entry_id}_{index}", entry_id, "F1")
        for index, cls in enumerate(
            (
                F1SessionTimeRemainingSensor,
                F1SessionTimeElapsedSensor,
                F1RaceTimeToThreeHourLimitSensor,
            )
        )
    ]
    component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
    hass.data.setdefault("_f1_sensor_test_entity_components", []).append(component)
    await component.async_add_entities(sensors)
    for seconds in (5, 20, 35, 50):
        now[0] = START + timedelta(seconds=seconds)
        coordinator._on_heartbeat({"Utc": now[0].isoformat()})
        await hass.async_block_till_done()
        values = [
            hass.states.get(sensor.entity_id).attributes["value_seconds"]
            for sensor in sensors
        ]
        assert values == [7200 - seconds, seconds, 10800 - seconds]


@pytest.mark.parametrize("timestamped", [True, False])
async def test_clock_timer_advances_between_messages_and_preserves_race_cap(
    running_clock,
    timestamped,
):
    """Sparse streams still tick; red flags pause only the official clock."""
    coordinator, now, _, callbacks, cancels = running_clock
    assert len(callbacks) == 1
    tick = callbacks[0]
    now[0] += timedelta(seconds=10)
    tick(now[0])
    assert coordinator.data["clock_remaining_s"] == 7190
    assert coordinator.data["clock_elapsed_s"] == 10
    assert coordinator.data["race_three_hour_remaining_s"] == 10790

    pause = {"Extrapolating": False}
    if timestamped:
        pause["Utc"] = now[0].isoformat()
    coordinator._on_extrapolated_clock(pause)
    coordinator._on_session_status({"Status": "Aborted"})
    now[0] += timedelta(seconds=30)
    tick(now[0])
    assert coordinator.data["clock_remaining_s"] == 7190
    assert coordinator.data["clock_elapsed_s"] == 10
    assert coordinator.data["race_three_hour_remaining_s"] == 10760
    assert not cancels[0].called

    coordinator._on_extrapolated_clock(
        {"Utc": now[0].isoformat(), "Extrapolating": True}
    )
    coordinator._on_session_status({"Status": "Resumed"})
    now[0] += timedelta(seconds=5)
    tick(now[0])
    assert coordinator.data["clock_remaining_s"] == 7185
    assert coordinator.data["race_three_hour_remaining_s"] == 10755


@pytest.mark.parametrize(
    "transition",
    ["idle", "no-spoiler", "replay-reset", "close", "finished", "replay-pause"],
)
async def test_clock_timer_stops_on_lifecycle_transition(
    running_clock, monkeypatch, transition
):
    coordinator, now, live, callbacks, cancels = running_clock
    assert len(callbacks) == 1
    if transition == "idle":
        live.set_state(False, "finished-Race")
    elif transition == "no-spoiler":
        live.set_state(False, "no-spoiler")
    elif transition == "replay-reset":
        _reset_replay_sensitive_coordinator_state(coordinator)
    elif transition == "close":
        await coordinator.async_close()
    elif transition == "finished":
        coordinator._on_session_status({"Status": "Finalised"})
    else:
        monkeypatch.setattr(
            coordinator, "_replay_controller_state", lambda: ReplayState.PAUSED
        )
        coordinator._on_replay_state_change({"state": "paused"})
    cancels[0].assert_called_once()

    if transition == "replay-pause":
        monkeypatch.setattr(
            coordinator, "_replay_controller_state", lambda: ReplayState.PLAYING
        )
        coordinator._on_replay_state_change({"state": "playing"})
        assert len(callbacks) == 2
        now[0] += timedelta(seconds=1)
        callbacks[1](now[0])
        assert coordinator.data["clock_elapsed_s"] == 1


async def test_inferred_session_start_stays_fixed_between_heartbeats(hass, monkeypatch):
    """A missing SessionData start must not make the inferred start drift."""
    coordinator = SessionClockCoordinator(hass, object())
    now = [START]
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now[0])
    coordinator._on_session_info({"Type": "Practice", "Name": "Practice 2"})
    coordinator._on_extrapolated_clock(
        {"Utc": START.isoformat(), "Remaining": "00:50:00", "Extrapolating": True}
    )
    inferred = coordinator.data["session_start_utc"]
    now[0] += timedelta(seconds=30)
    coordinator._on_heartbeat({"Utc": now[0].isoformat()})
    assert coordinator.data["session_start_utc"] == inferred
    assert coordinator.data["clock_elapsed_s"] == 630
    await coordinator.async_close()


async def test_finished_status_freezes_all_clocks_before_sessiondata_arrives(
    running_clock,
):
    """Heartbeats after Finished cannot keep moving the final sensor values."""
    coordinator, now, _, _, _ = running_clock
    now[0] += timedelta(seconds=100)
    coordinator._on_session_status({"Status": "Finished"})
    final_values = [
        coordinator.data[key]
        for key in (
            "clock_remaining_s",
            "clock_elapsed_s",
            "race_three_hour_remaining_s",
        )
    ]
    now[0] += timedelta(seconds=30)
    coordinator._on_heartbeat({"Utc": now[0].isoformat()})
    assert [
        coordinator.data[key]
        for key in (
            "clock_remaining_s",
            "clock_elapsed_s",
            "race_three_hour_remaining_s",
        )
    ] == final_values

    coordinator._on_session_data(
        {
            "StatusSeries": {
                "1": {
                    "Utc": (START + timedelta(seconds=98)).isoformat(),
                    "SessionStatus": "Finished",
                }
            }
        }
    )
    assert coordinator.data["clock_elapsed_s"] == 98
