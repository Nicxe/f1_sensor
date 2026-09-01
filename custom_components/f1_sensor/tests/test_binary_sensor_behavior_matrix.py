"""Behavior matrix for binary sensor state and availability models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.core import State

from custom_components.f1_sensor import binary_sensor
from custom_components.f1_sensor.binary_sensor import (
    F1FormationStartBinarySensor,
    F1LiveTimingOnlineBinarySensor,
    F1OnTrackIncidentBinarySensor,
    F1OvertakeModeBinarySensor,
    F1PossibleOnTrackIncidentBinarySensor,
    F1RaceWeekSensor,
    F1SafetyCarBinarySensor,
)
from custom_components.f1_sensor.const import (
    CONF_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
    RACE_WEEK_START_SATURDAY,
    RACE_WEEK_START_SUNDAY,
)


def _coordinator(data=None, *, available=True):
    return SimpleNamespace(
        data=data,
        available=available,
        async_add_listener=lambda _callback, *_args: Mock(),
    )


def test_race_week_boundaries_and_attributes(monkeypatch) -> None:
    now = datetime(2026, 9, 1, 12, tzinfo=UTC)
    monkeypatch.setattr(binary_sensor.dt_util, "utcnow", lambda: now)
    monkeypatch.setattr(binary_sensor.dt_util, "as_local", lambda value: value)
    race = {"raceName": "Test GP"}
    sensor = F1RaceWeekSensor(
        _coordinator({}), "week", "entry", "F1", race_week_start=RACE_WEEK_START_SUNDAY
    )
    sensor._get_next_race = lambda: (now + timedelta(days=4), race)
    assert sensor.is_on is True
    assert sensor.extra_state_attributes == {
        "days_until_next_race": 4,
        "next_race_name": "Test GP",
    }
    sensor._race_week_start = RACE_WEEK_START_SATURDAY
    sensor._get_next_race = lambda: (None, None)
    assert sensor.is_on is False
    assert sensor.extra_state_attributes["days_until_next_race"] is None
    sensor._race_week_start = "monday"
    sensor._get_next_race = lambda: (now + timedelta(days=1), race)
    assert sensor.is_on is True
    sensor._race_week_start = RACE_WEEK_START_SATURDAY
    assert isinstance(sensor.is_on, bool)


def test_safety_car_timestamp_ordering_and_terminal_context(hass) -> None:
    sensor = F1SafetyCarBinarySensor(
        _coordinator(
            {
                "data": {
                    "Status": "4",
                    "Utc": "2026-09-01T12:00:00Z",
                }
            }
        ),
        "safety",
        "entry",
        "F1",
    )
    sensor.hass = hass
    payload, timestamp = sensor._extract_payload()
    assert payload["Status"] == "4"
    assert timestamp == datetime(2026, 9, 1, 12, tzinfo=UTC)
    sensor._update_from_track_status()
    assert sensor.is_on is True
    sensor.coordinator.data = {
        "Status": "1",
        "Utc": "2026-09-01T11:59:00Z",
    }
    sensor._update_from_track_status()
    assert sensor.is_on is True
    sensor.coordinator.data = {"Status": "1", "Utc": "bad"}
    assert sensor._extract_payload()[1] is None
    sensor._session_status_coordinator = SimpleNamespace(
        data={"Status": "Finished"},
        is_qualifying_like_session=True,
        qualifying_part=1,
    )
    assert sensor._session_is_terminal() is False
    sensor._session_status_coordinator.qualifying_part = 3
    assert sensor._session_is_terminal() is True
    sensor._clear_state()
    assert sensor._forced_unavailable is True
    sensor.coordinator.available = False
    assert sensor.available is False
    sensor.coordinator.data = {"Status": "4", "Utc": "2026-09-01T12:00:00"}
    assert sensor._extract_payload()[1].tzinfo is UTC


def test_incident_binary_sensors_filter_phase_and_confidence() -> None:
    coordinator = _coordinator(
        {
            "active_count": 99,
            "active_incidents": [
                {"phase": "candidate", "confidence": "low"},
                {"phase": "confirmed", "confidence": "high"},
                {"phase": "resolved", "confidence": "medium"},
                "bad",
            ],
        }
    )
    confirmed = F1OnTrackIncidentBinarySensor(coordinator, "confirmed", "entry", "F1")
    possible = F1PossibleOnTrackIncidentBinarySensor(
        coordinator, "possible", "entry", "F1"
    )
    assert confirmed.is_on is True
    assert confirmed.extra_state_attributes["active_count"] == 1
    assert confirmed.extra_state_attributes["highest_confidence"] == "high"
    assert possible.extra_state_attributes["active_count"] == 2
    assert confirmed._highest_confidence([]) is None
    assert F1OnTrackIncidentBinarySensor(None, "none", "entry", "F1").available is False


def test_formation_start_update_and_clear_without_hass() -> None:
    tracker = SimpleNamespace(add_listener=lambda callback: lambda: None)
    sensor = F1FormationStartBinarySensor(tracker, "formation", "entry", "F1")
    sensor._is_stream_active = lambda: True
    sensor._safe_write_ha_state = lambda: None
    sensor._handle_update(
        {
            "status": "ready",
            "scheduled_start": "scheduled",
            "formation_start": "actual",
            "delta_seconds": 1,
            "source": "live",
            "session_type": "Race",
            "session_name": "Race",
            "error": None,
        }
    )
    assert sensor._is_on is True
    assert sensor.extra_state_attributes["source"] == "live"
    sensor._is_stream_active = lambda: False
    sensor._handle_live_state(False, "window-ended")
    assert sensor._is_on is False
    sensor._handle_live_state(False, "no-spoiler")


def test_live_timing_connectivity_modes_and_overtake_state(hass) -> None:
    bus = SimpleNamespace(
        last_heartbeat_age=lambda: 10.04,
        last_stream_activity_age=lambda: 12.06,
    )
    live_state = SimpleNamespace(is_live=True, reason="window-active")
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": live_state,
        "live_bus": bus,
    }
    online = F1LiveTimingOnlineBinarySensor(hass, "entry", "F1")
    assert online.is_on is True
    assert online.extra_state_attributes["heartbeat_age_s"] == 10.0
    bus.last_heartbeat_age = lambda: 100
    assert online.is_on is False
    live_state.is_live = False
    assert online.is_on is False
    hass.data[DOMAIN]["entry"][CONF_OPERATION_MODE] = OPERATION_MODE_DEVELOPMENT
    assert online.is_on is True

    overtake = F1OvertakeModeBinarySensor(
        _coordinator({"overtake_enabled": True, "straight_mode": "low_drag"}),
        "overtake",
        "entry",
        "F1",
    )
    assert overtake._extract_data()["overtake_enabled"] is True
    assert overtake._has_overtake_state(overtake.coordinator.data) is True
    overtake._apply_data(overtake.coordinator.data)
    assert overtake.is_on is True
    assert overtake.extra_state_attributes["straight_mode"] == "low_drag"
    overtake.coordinator.data = "bad"
    assert overtake._extract_data() is None
    overtake._clear_state()
    assert overtake.is_on is None


def test_race_week_start_legacy_normalization_and_schedule() -> None:
    assert binary_sensor._normalize_race_week_start({})
    assert (
        binary_sensor._normalize_race_week_start({"race_week_sunday_start": True})
        == "sunday"
    )
    assert (
        binary_sensor._normalize_race_week_start({"race_week_sunday_start": False})
        == "monday"
    )
    assert (
        binary_sensor._normalize_race_week_start({"race_week_sunday_start": "saturday"})
        == "saturday"
    )
    sensor = F1RaceWeekSensor(_coordinator(None), "week", "entry", "F1")
    assert sensor._get_next_race() == (None, None)
    sensor.coordinator.data = {
        "MRData": {
            "RaceTable": {
                "Races": [
                    {
                        "raceName": "Test GP",
                        "date": "2099-01-01",
                        "time": "12:00:00Z",
                    }
                ]
            }
        }
    }
    assert sensor._get_next_race()[1]["raceName"] == "Test GP"


def test_safety_car_update_guards_and_availability(hass) -> None:
    sensor = F1SafetyCarBinarySensor(
        _coordinator({"Status": "4"}), "safety", "entry", "F1"
    )
    sensor.hass = hass
    sensor.async_write_ha_state = Mock()
    sensor._session_is_terminal = Mock(return_value=False)
    sensor._handle_stream_state = Mock(return_value=False)
    sensor._handle_coordinator_update()
    sensor._handle_stream_state = Mock(return_value=True)
    sensor._is_stream_active = Mock(return_value=False)
    sensor._handle_coordinator_update()
    sensor._is_stream_active = Mock(return_value=True)
    sensor.coordinator.data = None
    sensor._handle_coordinator_update()
    sensor.coordinator.data = {"Status": "4"}
    sensor._handle_coordinator_update()
    assert sensor.is_on is True

    sensor._session_is_terminal = Mock(return_value=True)
    sensor._forced_unavailable = False
    sensor._handle_session_status_update()
    assert sensor._forced_unavailable is True
    sensor.async_write_ha_state.reset_mock()
    sensor._handle_session_status_update()
    sensor.async_write_ha_state.assert_not_called()
    sensor._session_is_terminal = Mock(return_value=False)
    sensor._handle_session_status_update()
    assert sensor.available is False


async def test_incident_and_formation_entity_lifecycle(hass) -> None:
    missing = F1OnTrackIncidentBinarySensor(None, "missing", "entry", "F1")
    await missing.async_added_to_hass()

    removal = Mock()
    coordinator = _coordinator({"active_incidents": []})
    coordinator.async_add_listener = Mock(return_value=removal)
    incident = F1OnTrackIncidentBinarySensor(coordinator, "incident", "entry", "F1")
    incident.hass = hass
    await incident.async_added_to_hass()
    coordinator.async_add_listener.assert_called_once()

    tracker_remove = Mock()
    tracker = SimpleNamespace(add_listener=Mock(return_value=tracker_remove))
    live_remove = Mock()
    live_state = SimpleNamespace(
        is_live=True,
        reason="replay",
        add_listener=Mock(return_value=live_remove),
    )
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": live_state,
    }
    formation = F1FormationStartBinarySensor(tracker, "formation", "entry", "F1")
    formation.hass = hass
    formation._safe_write_ha_state = Mock()
    await formation.async_added_to_hass()
    formation._handle_update({"status": "ready"})
    assert formation.is_on is True
    await formation.async_will_remove_from_hass()
    tracker_remove.assert_called_once()
    live_remove.assert_called_once()


async def test_live_timing_registration_and_overtake_update_paths(
    hass, monkeypatch
) -> None:
    live_remove = Mock()
    live_state = SimpleNamespace(
        is_live=True,
        reason="live",
        add_listener=Mock(return_value=live_remove),
    )
    bus = SimpleNamespace(
        last_heartbeat_age=Mock(side_effect=RuntimeError("offline")),
        last_stream_activity_age=lambda: 1,
    )
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": live_state,
        "live_bus": bus,
    }
    interval_remove = Mock()
    monkeypatch.setattr(
        binary_sensor,
        "async_track_time_interval",
        Mock(return_value=interval_remove),
    )
    online = F1LiveTimingOnlineBinarySensor(hass, "entry", "F1")
    await online.async_added_to_hass()
    assert online._compute_mode_and_ages()[1:4] == (None, None, None)
    assert online.is_on is True

    coordinator = _coordinator({})
    overtake = F1OvertakeModeBinarySensor(coordinator, "overtake", "entry", "F1")
    overtake.hass = hass
    overtake.async_write_ha_state = Mock()
    overtake._session_is_terminal = Mock(return_value=True)
    overtake._handle_coordinator_update()
    assert overtake.is_on is None
    overtake._session_is_terminal = Mock(return_value=False)
    overtake._handle_stream_state = Mock(return_value=False)
    overtake._handle_coordinator_update()
    overtake._handle_stream_state = Mock(return_value=True)
    overtake._is_stream_active = Mock(return_value=False)
    overtake._handle_coordinator_update()
    overtake._is_stream_active = Mock(return_value=True)
    coordinator.data = {"overtake_enabled": True, "straight_mode": "normal_grip"}
    overtake._handle_coordinator_update()
    assert overtake.is_on is True


async def test_binary_setup_and_restore_exact_paths(hass) -> None:
    entry = SimpleNamespace(
        entry_id="entry",
        data={
            "sensor_name": "F1",
            "disabled_sensors": [
                "live_timing_diagnostics",
                "race_week",
                "safety_car",
                "on_track_incident",
                "possible_on_track_incident",
                "formation_start",
            ],
        },
        options={},
    )
    live_mode = _coordinator({"overtake_enabled": False, "straight_mode": "disabled"})
    hass.data.setdefault(DOMAIN, {})["entry"] = {"live_mode_coordinator": live_mode}
    added = []
    await binary_sensor.async_setup_entry(
        hass, entry, lambda entities, _update: added.extend(entities)
    )
    assert len(added) == 1
    assert isinstance(added[0], F1OvertakeModeBinarySensor)

    safety_coord = _coordinator(None)
    safety = F1SafetyCarBinarySensor(safety_coord, "safety", "entry", "F1")
    safety.hass = hass
    safety.entity_id = "binary_sensor.safety"
    safety._is_stream_active = Mock(return_value=True)
    safety.async_get_last_state = AsyncMock(
        return_value=State("binary_sensor.safety", "on")
    )
    safety.async_write_ha_state = Mock()
    await safety.async_added_to_hass()
    assert safety.is_on is True
    assert safety.extra_state_attributes["restored"] is True

    overtake = F1OvertakeModeBinarySensor(
        _coordinator({}), "overtake_restore", "entry", "F1"
    )
    overtake.hass = hass
    overtake.entity_id = "binary_sensor.overtake_restore"
    overtake._is_stream_active = Mock(return_value=True)
    overtake.async_get_last_state = AsyncMock(
        return_value=State(
            "binary_sensor.overtake_restore",
            "on",
            {"straight_mode": "low_drag"},
        )
    )
    overtake.async_write_ha_state = Mock()
    await overtake.async_added_to_hass()
    assert overtake.is_on is True
    assert overtake.extra_state_attributes == {
        "straight_mode": "low_drag",
        "restored": True,
    }


async def test_binary_listener_failures_and_inactive_formation(hass) -> None:
    tracker = SimpleNamespace(add_listener=Mock(return_value=Mock()))
    live_state = SimpleNamespace(
        add_listener=Mock(side_effect=RuntimeError("listener"))
    )
    hass.data.setdefault(DOMAIN, {})["entry"] = {"live_state": live_state}
    formation = F1FormationStartBinarySensor(tracker, "formation_error", "entry", "F1")
    formation.hass = hass
    formation._is_stream_active = Mock(return_value=False)
    formation._is_on = True
    formation._safe_write_ha_state = Mock()
    await formation.async_added_to_hass()
    assert formation.is_on is False
    assert formation.available is False
    formation._handle_update({"status": "ready"})
    assert formation._is_on is False

    online_state = SimpleNamespace(
        is_live=True,
        reason="live",
        add_listener=Mock(side_effect=RuntimeError("listener")),
    )
    hass.data[DOMAIN]["entry"] = {"live_state": online_state}
    online = F1LiveTimingOnlineBinarySensor(hass, "entry", "F1")
    await online.async_added_to_hass()
    assert online._unsub_live_state is None

    incident = F1OnTrackIncidentBinarySensor(
        _coordinator("bad"), "incident_bad", "entry", "F1"
    )
    assert incident.is_on is False
    incident.coordinator.data = {"active_incidents": "bad"}
    assert incident.extra_state_attributes["active_count"] == 0
