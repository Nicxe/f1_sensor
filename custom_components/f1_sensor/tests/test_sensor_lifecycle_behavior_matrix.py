"""Behavior coverage for stateful live sensor lifecycle helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.sensor import (
    F1DriverListSensor,
    F1DriverPositionsSensor,
    F1InvestigationsSensor,
    F1RaceControlSensor,
    F1RaceLapCountSensor,
    F1TrackLimitsSensor,
)


def _coordinator(*, data=None, data_list=None):
    return SimpleNamespace(
        data=data,
        data_list=data_list,
        available=True,
        async_add_listener=lambda _callback: Mock(),
    )


def _ha_coordinator(hass, data=None):
    coordinator = DataUpdateCoordinator(hass, logging.getLogger(__name__), name="test")
    coordinator.data = data
    coordinator.data_list = []
    return coordinator


def test_race_control_payload_normalization_history_and_icons(monkeypatch) -> None:
    sensor = F1RaceControlSensor(_coordinator(data={}), "race", "entry", "F1")
    monkeypatch.setattr(
        "custom_components.f1_sensor.sensor.dt_util.utcnow",
        lambda: datetime(2026, 9, 1, 12, tzinfo=UTC),
    )
    assert sensor._extract_current() is None
    sensor.coordinator.data_list = [{"Message": "Fallback"}]
    assert sensor._extract_current() == {"Message": "Fallback"}
    assert sensor._cleanup_string("  ") is None
    assert sensor._cleanup_string(12) == "12"
    assert sensor._build_event_id({}) is None

    payloads = [
        {"Utc": "2026-09-01T12:00:00Z", "Flag": "RED", "Message": "Stop"},
        {"utc": "bad", "Flag": "YELLOW", "Text": "Caution"},
        {"timestamp": "2026-09-01T12:02:00", "Flag": "GREEN", "Scope": "Track"},
        {"Category": "SafetyCar", "Flag": "BLUE", "Sector": 2},
        {"CategoryType": "VSC", "Flag": "CLEAR", "Car": 4},
        {"Flag": "WHITE", "Number": 5},
        {"Category": "Other", "TrackSegment": 3, "Driver": 6},
    ]
    for payload in payloads:
        sensor._apply_payload(payload)
    assert sensor.state == "Other"
    assert len(sensor.extra_state_attributes["history"]) == sensor._history_limit
    assert sensor.extra_state_attributes["car_number"] == "6"
    sequence = sensor.extra_state_attributes["sequence"]
    sensor._apply_payload(payloads[-1])
    assert sensor.extra_state_attributes["sequence"] == sequence
    sensor._apply_payload(payloads[-1], force=True)
    assert sensor.extra_state_attributes["sequence"] == sequence + 1
    assert sensor._resolve_icon(None, None) == "mdi:flag-outline"
    sensor._clear_state()
    assert sensor.state is None


def test_track_limits_processes_all_violation_types_and_duplicates() -> None:
    messages = [
        {"Utc": "t1", "Lap": 4, "Message": "No relevant message"},
        {
            "Utc": "t2",
            "Message": "CAR 4 (NOR) LAP DELETED - TRACK LIMITS AT TURN 2 LAP 3",
        },
        {
            "Utc": "t3",
            "Lap": 5,
            "Message": "BLACK AND WHITE FLAG FOR CAR 4 (NOR) - TRACK LIMITS",
        },
        {
            "Utc": "t4",
            "Lap": 6,
            "Message": "5 SECOND TIME PENALTY FOR CAR 4 (NOR) - TRACK LIMITS",
        },
        {"Utc": "t5", "Message": "TRACK LIMITS but unparsable"},
    ]
    sensor = F1TrackLimitsSensor(
        _coordinator(data_list=messages), "limits", "entry", "F1"
    )
    assert sensor._process_message(messages[0]) is False
    assert sensor._process_message(messages[1]) is True
    assert sensor._process_message(messages[1]) is False
    assert sensor._process_message(messages[2]) is True
    assert sensor._process_message(messages[3]) is True
    assert sensor._process_message(messages[4]) is False
    sensor._process_all_messages()
    assert sensor.state == 2
    assert sensor.extra_state_attributes["total_deletions"] == 1
    assert sensor.extra_state_attributes["total_warnings"] == 1
    assert sensor.extra_state_attributes["total_penalties"] == 1
    assert sensor._build_message_id({}) == "|"
    sensor._clear_state()
    assert sensor.state == 0


def test_investigations_full_lifecycle_and_expiry() -> None:
    sensor = F1InvestigationsSensor(
        _coordinator(data_list=[]), "investigations", "entry", "F1"
    )
    messages = [
        {"Utc": "2026-09-01T12:00:00+00:00", "Message": "Unrelated"},
        {
            "Utc": "2026-09-01T12:00:01+00:00",
            "Lap": 1,
            "Message": "INCIDENT INVOLVING CARS 4 (NOR) AND 81 (PIA) NOTED - COLLISION",
        },
        {
            "Utc": "2026-09-01T12:00:02+00:00",
            "Lap": 1,
            "Message": "UPDATE: INCIDENT INVOLVING CARS 4 (NOR) AND 81 (PIA) NOTED - CAUSING A COLLISION",
        },
        {
            "Utc": "2026-09-01T12:00:03+00:00",
            "Lap": 1,
            "Message": "FIA STEWARDS: CARS 81 (PIA) AND 4 (NOR) UNDER INVESTIGATION - CAUSING A COLLISION",
        },
        {
            "Utc": "2026-09-01T12:00:04+00:00",
            "Lap": 2,
            "Message": "FIA STEWARDS: CARS 4 (NOR) AND 81 (PIA) NO FURTHER ACTION - CAUSING A COLLISION",
        },
    ]
    assert sensor._process_message(messages[0]) is False
    for message in messages[1:]:
        assert sensor._process_message(message) is True
    assert sensor._process_message(messages[-1]) is False
    sensor._update_attributes()
    assert sensor.state == 0
    assert len(sensor.extra_state_attributes["no_further_action"]) == 1
    assert sensor._extract_location("INCIDENT AT PIT EXIT") == "PIT EXIT"
    assert sensor._extract_reason("NOTED - unsafe release") == "UNSAFE RELEASE"
    assert sensor._find_incident_by_drivers(["XXX"], sensor._noted) is None
    assert sensor._find_incident_containing_driver("XXX", sensor._noted) is None

    sensor._session_time = datetime(2026, 9, 1, 12, 10, tzinfo=UTC)
    assert sensor._expire_nfi_items() is True
    assert sensor._expire_nfi_items() is False
    sensor._clear_state()
    assert sensor._session_time is None


def test_investigations_after_race_direct_and_penalty_served() -> None:
    sensor = F1InvestigationsSensor(
        _coordinator(data_list=[]), "investigations", "entry", "F1"
    )
    after_race = {
        "Utc": "2026-09-01T12:00:00+00:00",
        "Message": "CAR 44 (HAM) WILL BE INVESTIGATED AFTER THE RACE - PIT LANE",
    }
    assert sensor._process_message(after_race) is True
    assert next(iter(sensor._under_investigation.values()))["after_race"] is True
    penalty = {
        "Utc": "2026-09-01T12:01:00+00:00",
        "Message": "FIA STEWARDS: REPRIMAND (DRIVING) FOR CAR 44 (HAM)",
    }
    assert sensor._process_message(penalty) is True
    assert sensor._penalties[0]["penalty"] == "REPRIMAND (DRIVING)"
    served = {
        "Utc": "2026-09-01T12:02:00+00:00",
        "Message": "FIA STEWARDS: PENALTY SERVED FOR CAR 44 (HAM)",
    }
    assert sensor._process_message(served) is True
    assert sensor._penalties == []


def test_lap_count_extract_apply_stale_and_clear(monkeypatch) -> None:
    now = datetime(2026, 9, 1, 12, tzinfo=UTC)
    sensor = F1RaceLapCountSensor(
        _coordinator(data={"data": {"LapCount": "4", "TotalLaps": "70"}}),
        "laps",
        "entry",
        "F1",
    )
    assert sensor._to_int("4.9") == 4
    assert sensor._to_int("bad") is None
    assert sensor._extract_current() == {"LapCount": "4", "TotalLaps": "70"}
    monkeypatch.setattr(
        "custom_components.f1_sensor.sensor.dt_util.utcnow", lambda: now
    )
    sensor._apply_payload(
        {"CurrentLap": "4", "TotalLaps": 70, "Utc": "2026-09-01T11:59:00Z"}
    )
    assert sensor._attr_native_value == 4
    sensor._apply_payload({"LapCount": 5})
    assert sensor.extra_state_attributes["total_laps"] == 70
    sensor._last_timestamped_dt = now - timedelta(minutes=6)
    sensor._safe_write_ha_state = Mock()
    sensor._handle_stale_timeout()
    assert sensor._attr_native_value is None
    assert sensor.extra_state_attributes["stale"] is True
    sensor._stale_timer = Mock()
    sensor._clear_state()
    assert sensor._stale_timer is None


def test_driver_list_normalizes_and_bootstraps_from_standings() -> None:
    coordinator = _coordinator(
        data={
            "drivers": {
                "A": {"identity": {"racing_number": "X", "team_color": 42}},
                "4": {
                    "identity": {
                        "racing_number": "4",
                        "tla": "NOR",
                        "team_color": "ff8700",
                        "headshot": "fallback",
                    }
                },
            }
        }
    )
    sensor = F1DriverListSensor(coordinator, "drivers", "entry", "F1")
    assert sensor._update_from_coordinator() is True
    assert sensor.state == 2
    assert sensor.extra_state_attributes["drivers"][0]["team_color"] == "#ff8700"
    coordinator.data = "bad"
    assert sensor._update_from_coordinator() is False
    assert sensor.available is True


def test_driver_positions_status_restore_and_session_helpers() -> None:
    sensor = F1DriverPositionsSensor(_coordinator(data={}), "positions", "entry", "F1")
    assert sensor._normalize_qualifying_part(None) is None
    assert sensor._normalize_qualifying_part("bad") is None
    assert sensor._normalize_qualifying_part(0) == 1
    assert sensor._normalize_qualifying_part(4) is None
    assert sensor._is_race_or_sprint("Race", None) is True
    assert sensor._is_race_or_sprint(None, "Sprint Qualifying") is False

    status, attrs = sensor._derive_driver_status("4", None)
    assert status is None and attrs["in_pit"] is None
    assert sensor._derive_driver_status("4", {"in_pit": True}, now=1)[0] == "pit_in"
    assert sensor._derive_driver_status("4", {"pit_out": True}, now=2)[0] == "pit_out"
    assert sensor._derive_driver_status("4", {"retired": True}, now=3)[0] == "out"
    assert sensor._derive_driver_status("4", {}, default_on_track=True)[0] == (
        "on_track"
    )
    restored = sensor._normalize_restored_attributes(
        {"drivers": [{"racing_number": "4"}, "bad"]}
    )
    assert restored["drivers"][0]["q3_position"] is None
    sensor._clear_state()
    assert sensor.state is None


async def test_lap_count_and_driver_list_restore_lifecycle(hass) -> None:
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": SimpleNamespace(is_live=True, reason="live")
    }
    lap_coordinator = _ha_coordinator(hass)
    lap_sensor = F1RaceLapCountSensor(lap_coordinator, "laps_restore", "entry", "F1")
    lap_sensor.hass = hass
    lap_sensor.entity_id = "sensor.laps_restore"
    lap_sensor.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="7",
            attributes={
                "total_laps": 70,
                "measurement_time": "2026-09-01T11:00:00Z",
                "measurement_age_seconds": 5,
                "received_at": "2026-09-01T11:00:01Z",
            },
        )
    )
    lap_sensor._safe_write_ha_state = Mock()
    await lap_sensor.async_added_to_hass()
    assert lap_sensor._attr_native_value == 7
    assert lap_sensor.extra_state_attributes == {"total_laps": 70}
    assert lap_sensor._safe_write_ha_state.called
    lap_sensor._stale_timer = Mock()
    await lap_sensor.async_will_remove_from_hass()
    assert lap_sensor._stale_timer is None

    driver_coordinator = _ha_coordinator(hass, {})
    driver_sensor = F1DriverListSensor(
        driver_coordinator, "drivers_restore", "entry", "F1"
    )
    driver_sensor.hass = hass
    driver_sensor.entity_id = "sensor.drivers_restore"
    driver_sensor.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="1",
            attributes={
                "headshot": "old",
                "drivers": [{"racing_number": "4", "headshot": "old"}],
            },
        )
    )
    driver_sensor._bootstrap_from_ergast = Mock(return_value=False)
    driver_sensor.async_write_ha_state = Mock()
    await driver_sensor.async_added_to_hass()
    assert driver_sensor._attr_native_value == 1
    assert "headshot" not in driver_sensor.extra_state_attributes
    assert "headshot" not in driver_sensor.extra_state_attributes["drivers"][0]


async def test_lap_count_restore_guards_history_and_safe_write_paths(
    hass, monkeypatch
) -> None:
    """Cover inactive startup, history fallback, timers, and write scheduling."""
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": SimpleNamespace(is_live=True, reason="live")
    }
    coordinator = _ha_coordinator(hass)
    coordinator.data_list = ["bad", {"CurrentLap": "9", "TotalLaps": "70"}]
    sensor = F1RaceLapCountSensor(coordinator, "laps_matrix", "entry", "F1")
    sensor.hass = hass
    sensor.entity_id = "sensor.laps_matrix"
    sensor.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(state="unknown", attributes={})
    )
    sensor._safe_write_ha_state = Mock()
    await sensor.async_added_to_hass()
    assert sensor._attr_native_value == 9

    coordinator.data_list = ["bad"]
    assert sensor._extract_current() is None
    sensor._attr_extra_state_attributes = {
        "measurement_time": "bad",
        "total_laps": 70,
    }
    now = datetime(2026, 9, 1, 12, tzinfo=UTC)
    sensor._last_timestamped_dt = now - timedelta(seconds=10)
    old_timer = Mock()
    new_timer = Mock()
    sensor._stale_timer = old_timer
    monkeypatch.setattr(
        "custom_components.f1_sensor.sensor.async_call_later",
        lambda *_args: new_timer,
    )
    sensor._schedule_stale_check(now_utc=now)
    old_timer.assert_called_once()
    assert sensor._stale_timer is new_timer

    sensor._attr_extra_state_attributes = {}
    sensor._last_timestamped_dt = None
    sensor._last_received_utc = None
    sensor._schedule_stale_check(now_utc=now)
    sensor._handle_stale_timeout()

    inactive = F1RaceLapCountSensor(
        _ha_coordinator(hass), "laps_inactive", "entry", "F1"
    )
    inactive.hass = hass
    inactive.entity_id = "sensor.laps_inactive"
    inactive._is_stream_active = Mock(return_value=False)
    inactive._safe_write_ha_state = Mock()
    await inactive.async_added_to_hass()
    assert inactive._attr_native_value is None

    direct = F1RaceLapCountSensor(
        _ha_coordinator(hass, {"LapCount": 1}), "laps_write", "entry", "F1"
    )
    direct.hass = hass
    direct.entity_id = "sensor.laps_write"
    direct.async_write_ha_state = Mock()
    direct.schedule_update_ha_state = Mock()
    direct._safe_write_ha_state()
    direct.async_write_ha_state.assert_called_once()
    direct.async_write_ha_state = Mock(side_effect=RuntimeError("write"))
    direct._safe_write_ha_state()
    assert direct.schedule_update_ha_state.called


async def test_driver_positions_context_restore_and_metadata_fallbacks(
    hass, monkeypatch
) -> None:
    """Cover live context listeners and replay/window session fallbacks."""
    info = _ha_coordinator(hass, {"Type": "Race", "Name": "Grand Prix"})
    status = _ha_coordinator(hass, {"Status": "Started"})
    selected = SimpleNamespace(session_type="Sprint", session_name="Sprint")
    replay_controller = SimpleNamespace(
        state=__import__(
            "custom_components.f1_sensor.replay_mode",
            fromlist=["ReplayState"],
        ).ReplayState.PLAYING,
        session_manager=SimpleNamespace(selected_session=selected),
    )
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": SimpleNamespace(is_live=True, reason="live"),
        "session_info_coordinator": info,
        "session_status_coordinator": status,
        "replay_controller": replay_controller,
        "live_supervisor": SimpleNamespace(
            current_window=SimpleNamespace(session_name="Practice 1")
        ),
    }
    coordinator = _ha_coordinator(hass, {})
    sensor = F1DriverPositionsSensor(coordinator, "positions_matrix", "entry", "F1")
    sensor.hass = hass
    sensor.entity_id = "sensor.positions_matrix"
    sensor.async_write_ha_state = Mock()
    sensor.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="12",
            attributes={"drivers": [{"racing_number": "4"}]},
        )
    )
    await sensor.async_added_to_hass()
    assert sensor._attr_native_value == 12
    assert sensor._session_info_coordinator is info
    assert sensor._is_replay_active() is True

    sensor._session_info_coordinator = None
    assert sensor._get_session_type_and_name() == ("Sprint", "Sprint")
    replay_controller.session_manager.selected_session = None
    assert sensor._get_session_type_and_name() == (None, "Practice 1")
    del hass.data[DOMAIN]["entry"]["live_supervisor"]
    assert sensor._get_session_name_from_window() == (None, None)

    sensor.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(state="bad", attributes={})
    )
    await sensor._restore_state()
    assert sensor._attr_native_value is None
    sensor.async_get_last_state = AsyncMock(return_value=None)
    await sensor._restore_state()

    sensor._update_from_coordinator = Mock(return_value=True)
    sensor._handle_stream_state = Mock(return_value=True)
    sensor._attr_native_value = 1
    sensor._attr_extra_state_attributes = {"drivers": []}
    sensor._update_from_coordinator.side_effect = lambda **_kwargs: (
        setattr(sensor, "_attr_native_value", 2) or True
    )
    sensor._rate_limited_write = Mock()
    sensor._handle_session_info_update()
    sensor._rate_limited_write.assert_called_once()

    monkeypatch.setitem(hass.data[DOMAIN]["entry"], "replay_controller", None)
    assert sensor._is_replay_active() is False


async def test_track_limits_and_investigations_restore_payloads() -> None:
    track = F1TrackLimitsSensor(
        _coordinator(data_list=[]), "limits_restore", "entry", "F1"
    )
    track.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="bad",
            attributes={"by_driver": {"NOR": {"deletions": 2}}},
        )
    )
    await track._restore_from_last()
    assert track._attr_native_value == 0
    assert "NOR" in track._by_driver
    track.async_get_last_state = AsyncMock(return_value=None)
    await track._restore_from_last()

    investigations = F1InvestigationsSensor(
        _coordinator(data_list=[]), "investigations_restore", "entry", "F1"
    )
    investigations.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="bad",
            attributes={
                "noted": [
                    {"drivers": ["NOR"], "location": "TURN 1", "reason": "unsafe"},
                    "bad",
                ],
                "under_investigation": [
                    {"drivers": ["PIA"], "location": None, "reason": None},
                    "bad",
                ],
                "no_further_action": [
                    {"drivers": ["HAM"], "location": None, "reason": None},
                    "bad",
                ],
                "penalties": [{"driver": "LEC"}, "bad"],
                "last_update": "2026-09-01T12:00:00Z",
            },
        )
    )
    await investigations._restore_from_last()
    assert investigations._attr_native_value == 0
    assert len(investigations._noted) == 1
    assert len(investigations._under_investigation) == 1
    assert len(investigations._nfi) == 1
    assert investigations._penalties == [{"driver": "LEC"}]
    assert investigations._session_time is not None


def test_driver_list_bootstraps_from_standings_registry(hass) -> None:
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "driver_coordinator": SimpleNamespace(
            data={
                "MRData": {
                    "StandingsTable": {
                        "StandingsLists": [
                            {
                                "DriverStandings": [
                                    {
                                        "Driver": {
                                            "permanentNumber": "4",
                                            "code": "NOR",
                                            "givenName": "Lando",
                                            "familyName": "Norris",
                                            "url": "https://example.test/norris",
                                        },
                                        "Constructors": [{"name": "McLaren"}],
                                    },
                                    {
                                        "Driver": {
                                            "permanentNumber": "",
                                            "driverId": "missing-number",
                                        }
                                    },
                                    "bad",
                                ]
                            }
                        ]
                    }
                }
            }
        )
    }
    sensor = F1DriverListSensor(_coordinator(data={}), "drivers", "entry", "F1")
    sensor.hass = hass
    assert sensor._bootstrap_from_ergast() is True
    assert sensor._attr_native_value == 1
    driver = sensor.extra_state_attributes["drivers"][0]
    assert driver["name"] == "Lando Norris"
    assert driver["team"] == "McLaren"
    hass.data[DOMAIN]["entry"]["driver_coordinator"].data = {}
    assert sensor._bootstrap_from_ergast() is False


def test_lap_count_stale_schedule_and_update_paths(hass, monkeypatch) -> None:
    sensor = F1RaceLapCountSensor(
        _coordinator(data={"CurrentLap": 2, "TotalLaps": 70}),
        "laps",
        "entry",
        "F1",
    )
    sensor.hass = hass
    timer = Mock()
    monkeypatch.setattr(
        "custom_components.f1_sensor.sensor.async_call_later",
        lambda _hass, _delay, _callback: timer,
    )
    now = datetime(2026, 9, 1, 12, tzinfo=UTC)
    sensor._schedule_stale_check(now - timedelta(seconds=100), now)
    assert sensor._stale_timer is timer
    sensor._attr_extra_state_attributes = {"measurement_time": "bad"}
    sensor._last_timestamped_dt = now - timedelta(seconds=400)
    sensor._schedule_stale_check(now_utc=now)
    sensor._safe_write_ha_state = Mock()
    sensor._handle_stream_state = Mock(return_value=True)
    sensor._is_stream_active = Mock(return_value=True)
    sensor._handle_coordinator_update()
    assert sensor._attr_native_value == 2
    sensor.coordinator.data = None
    sensor._handle_coordinator_update()
    sensor._is_stream_active = Mock(return_value=False)
    sensor._handle_coordinator_update()


def test_race_control_track_limits_and_investigations_update_guards() -> None:
    race = F1RaceControlSensor(
        _coordinator(data={"Utc": "t", "Message": "Message"}),
        "race",
        "entry",
        "F1",
    )
    race._handle_stream_state = Mock(return_value=True)
    race._is_stream_active = Mock(return_value=True)
    race._safe_write_ha_state = Mock()
    race._handle_coordinator_update()
    assert race._attr_native_value == "Message"
    race._handle_coordinator_update()
    race.coordinator.data = None
    race.coordinator.data_list = []
    race._handle_coordinator_update()
    race._is_stream_active = Mock(return_value=False)
    race._handle_coordinator_update()

    track = F1TrackLimitsSensor(
        _coordinator(
            data_list=[
                {
                    "Utc": "t",
                    "Message": "BLACK AND WHITE FLAG FOR CAR 4 (NOR) - TRACK LIMITS",
                }
            ]
        ),
        "limits",
        "entry",
        "F1",
    )
    track._handle_stream_state = Mock(return_value=True)
    track._is_stream_active = Mock(return_value=True)
    track._safe_write_ha_state = Mock()
    track._handle_coordinator_update()
    assert track._attr_native_value == 1
    track._handle_coordinator_update()
    track._is_stream_active = Mock(return_value=False)
    track._handle_coordinator_update()
    track._handle_live_state(False, "init")
    track._handle_live_state(False, "no-spoiler")
    track._handle_live_state(False, "window-ended")

    investigations = F1InvestigationsSensor(
        _coordinator(
            data_list=[
                {
                    "Utc": "2026-09-01T12:00:00Z",
                    "Message": "INCIDENT INVOLVING CAR 4 (NOR) NOTED - TURN 1",
                }
            ]
        ),
        "investigations",
        "entry",
        "F1",
    )
    investigations._handle_stream_state = Mock(return_value=True)
    investigations._is_stream_active = Mock(return_value=True)
    investigations._safe_write_ha_state = Mock()
    investigations._handle_coordinator_update()
    assert investigations._attr_native_value == 1
    investigations._handle_coordinator_update()
    investigations._is_stream_active = Mock(return_value=False)
    investigations._handle_coordinator_update()
    investigations._handle_live_state(False, "window-ended")
