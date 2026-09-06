"""Behavior coverage for sensor fallback and update branches."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import sensor as sensor_platform
from custom_components.f1_sensor.auth import evaluate_f1tv_auth_header
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.favorite_driver import FavoriteDriverController
from custom_components.f1_sensor.sensor import (
    F1ChampionshipPredictionDriversSensor,
    F1ChampionshipPredictionTeamsSensor,
    F1ConstructorPointsProgressionSensor,
    F1CurrentSessionSensor,
    F1CurrentTyresSensor,
    F1DriverListSensor,
    F1DriverPointsProgressionSensor,
    F1DriverPositionsSensor,
    F1FiaDocumentsSensor,
    F1PitStopsSensor,
    F1SessionStatusSensor,
    F1StraightModeSensor,
    F1TeamRadioSensor,
    F1TopThreePositionSensor,
    F1TrackStatusSensor,
)


def _coordinator(data=None, data_list=None):
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


async def test_sensor_setup_expands_special_entities_and_auth_health(
    hass, monkeypatch
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    entry.add_to_hass(hass)
    coordinator = _coordinator({})
    favorite = object.__new__(FavoriteDriverController)
    registry = {
        "race_coordinator": coordinator,
        "driver_coordinator": coordinator,
        "constructor_coordinator": coordinator,
        "last_race_coordinator": coordinator,
        "season_results_coordinator": coordinator,
        "sprint_results_coordinator": coordinator,
        "top_three_coordinator": coordinator,
        "championship_prediction_coordinator": coordinator,
        "favorite_driver_controller": favorite,
        "replay_controller": Mock(),
        sensor_platform.AUTH_RUNTIME_STATUS: evaluate_f1tv_auth_header("Bearer x"),
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = registry
    monkeypatch.setattr(sensor_platform.const, "ENABLE_DEVELOPMENT_MODE_UI", True)
    monkeypatch.setattr(sensor_platform, "is_auth_health_visible", lambda _status: True)
    added = []

    def _add_entities(entities, update_before_add=False) -> None:
        assert update_before_add is False
        added.extend(entities)

    await sensor_platform.async_setup_entry(hass, entry, _add_entities)

    types = {type(entity).__name__ for entity in added}
    assert {
        "F1TopThreePositionSensor",
        "F1ChampionshipPredictionDriversSensor",
        "F1ChampionshipPredictionTeamsSensor",
        "F1FavoriteDriverSensor",
        "F1LiveTimingModeSensor",
        "F1TvTokenStatusSensor",
        "F1TvTokenExpiresAtSensor",
        "F1ReplayStatusSensor",
    } <= types


def test_points_standings_registry_parsing_and_failure_paths(hass) -> None:
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "driver_coordinator": SimpleNamespace(
            data={
                "MRData": {
                    "StandingsTable": {
                        "StandingsLists": [
                            {
                                "round": "3",
                                "DriverStandings": [
                                    {
                                        "points": "62.5",
                                        "Driver": {"code": "NOR"},
                                    },
                                    {
                                        "points": "bad",
                                        "Driver": {"driverId": "piastri"},
                                    },
                                    {"points": "1", "Driver": {}},
                                ],
                            }
                        ]
                    }
                }
            }
        ),
        "constructor_coordinator": SimpleNamespace(
            data={
                "MRData": {
                    "StandingsTable": {
                        "StandingsLists": [
                            {
                                "round": "bad",
                                "ConstructorStandings": [
                                    {
                                        "points": "100",
                                        "Constructor": {"constructorId": "mclaren"},
                                    },
                                    {
                                        "points": None,
                                        "Constructor": {"name": "Ferrari"},
                                    },
                                    {"points": "1", "Constructor": {}},
                                ],
                            }
                        ]
                    }
                }
            }
        ),
    }
    drivers = F1DriverPointsProgressionSensor(
        _coordinator({}), "drivers", "entry", "F1"
    )
    constructors = F1ConstructorPointsProgressionSensor(
        _coordinator({}), "constructors", "entry", "F1"
    )
    drivers.hass = hass
    constructors.hass = hass

    assert drivers._get_driver_standings() == (
        {"NOR": 62.5, "piastri": 0.0},
        3,
    )
    assert constructors._get_constructor_standings() == (
        {"mclaren": 100.0, "Ferrari": 0.0},
        None,
    )

    hass.data[DOMAIN]["entry"] = None
    assert drivers._get_driver_standings() == ({}, None)
    assert constructors._get_constructor_standings() == ({}, None)


def test_driver_list_update_guards_and_rate_limiting(hass, monkeypatch) -> None:
    sensor = F1DriverListSensor(_coordinator({}), "drivers", "entry", "F1")
    sensor.hass = hass
    sensor._update_from_coordinator = Mock(return_value=False)
    sensor._safe_write_ha_state = Mock()
    sensor._handle_coordinator_update()
    sensor._safe_write_ha_state.assert_not_called()

    sensor._update_from_coordinator = Mock(return_value=True)
    sensor._attr_native_value = 1
    sensor._attr_extra_state_attributes = {"drivers": []}
    sensor._handle_coordinator_update()
    sensor._safe_write_ha_state.assert_not_called()

    sensor._update_from_coordinator = Mock(
        side_effect=lambda: setattr(sensor, "_attr_native_value", 2) or True
    )
    monkeypatch.setattr("time.time", lambda: 100.0)
    sensor._handle_coordinator_update()
    sensor._safe_write_ha_state.assert_called_once()

    callback = None

    def _later(_hass, delay, scheduled):
        nonlocal callback
        assert delay == 50.0
        callback = scheduled
        return Mock()

    sensor._last_write_ts = 90.0
    sensor._pending_write = False
    sensor._update_from_coordinator = Mock(
        side_effect=lambda: setattr(sensor, "_attr_native_value", 3) or True
    )
    monkeypatch.setattr(
        "homeassistant.helpers.event.async_call_later",
        _later,
    )
    sensor._handle_coordinator_update()
    assert sensor._pending_write is True
    assert callback is not None
    callback(None)
    assert sensor._pending_write is False
    assert sensor._safe_write_ha_state.call_count == 2


def test_track_status_update_terminal_inactive_and_change_paths() -> None:
    sensor = F1TrackStatusSensor(_coordinator({"Status": "1"}), "track", "entry", "F1")
    sensor.async_write_ha_state = Mock()
    sensor._session_is_terminal = Mock(return_value=True)
    sensor._handle_coordinator_update()
    assert sensor.state is None
    assert sensor._forced_unavailable is True

    sensor.async_write_ha_state.reset_mock()
    sensor._handle_session_status_update()
    sensor.async_write_ha_state.assert_not_called()
    sensor._forced_unavailable = False
    sensor._handle_session_status_update()
    sensor.async_write_ha_state.assert_called_once()

    sensor._session_is_terminal = Mock(return_value=False)
    sensor._handle_stream_state = Mock(return_value=False)
    sensor._handle_coordinator_update()

    sensor._handle_stream_state = Mock(return_value=True)
    sensor._is_stream_active = Mock(return_value=False)
    sensor._handle_coordinator_update()

    sensor._is_stream_active = Mock(return_value=True)
    sensor.coordinator.data = None
    sensor.coordinator.data_list = []
    sensor._handle_coordinator_update()

    sensor.coordinator.data = {"Status": "2"}
    sensor._attr_native_value = "YELLOW"
    sensor._handle_coordinator_update()
    sensor.coordinator.data = {"Status": "1"}
    sensor._handle_coordinator_update()
    assert sensor.state == "CLEAR"
    assert sensor._forced_unavailable is False


def test_driver_positions_session_fallbacks_and_rate_limiter(hass, monkeypatch) -> None:
    sensor = F1DriverPositionsSensor(_coordinator({}), "positions", "entry", "F1")
    sensor.hass = hass
    hass.data.setdefault(DOMAIN, {})["entry"] = {}

    assert sensor._get_session_from_replay() == (None, None)
    hass.data[DOMAIN]["entry"]["replay_controller"] = SimpleNamespace(
        session_manager=SimpleNamespace(
            selected_session=SimpleNamespace(
                session_type="Race", session_name="Grand Prix"
            )
        )
    )
    assert sensor._get_session_from_replay() == ("Race", "Grand Prix")
    sensor._session_info_coordinator = SimpleNamespace(data={})
    assert sensor._get_session_type_and_name() == ("Race", "Grand Prix")

    hass.data[DOMAIN]["entry"].pop("replay_controller")
    hass.data[DOMAIN]["entry"]["live_supervisor"] = SimpleNamespace(
        current_window=SimpleNamespace(session_name="Sprint")
    )
    sensor._session_info_coordinator = None
    assert sensor._get_session_type_and_name() == (None, "Sprint")

    sensor._safe_write_ha_state = Mock()
    monkeypatch.setattr("time.time", lambda: 10.0)
    sensor._rate_limited_write()
    sensor._safe_write_ha_state.assert_called_once()

    scheduled = None

    def _later(_hass, delay, callback):
        nonlocal scheduled
        assert delay == 0.5
        scheduled = callback
        return Mock()

    monkeypatch.setattr("time.time", lambda: 10.5)
    monkeypatch.setattr("custom_components.f1_sensor.sensor.async_call_later", _later)
    sensor._rate_limited_write()
    sensor._rate_limited_write()
    assert sensor._pending_write is True
    assert scheduled is not None
    scheduled(None)
    assert sensor._pending_write is False
    assert sensor._safe_write_ha_state.call_count == 2


async def test_fia_documents_restores_list_and_flat_legacy_states() -> None:
    sensor = F1FiaDocumentsSensor(_coordinator({}), "fia", "entry", "F1")
    sensor.async_get_last_state = AsyncMock(return_value=None)
    await sensor._restore_last_state()

    sensor.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="2",
            attributes={
                "documents": [
                    {
                        "name": "Document 2 - Decision",
                        "url": " https://fia.test/2 ",
                        "published": "2026-09-01T12:00:00Z",
                    },
                    "bad",
                ],
                "race": {"race_name": "Test GP"},
            },
        )
    )
    await sensor._restore_last_state()
    assert sensor._attr_native_value == 2
    assert sensor._seen_urls == {"https://fia.test/2"}
    assert sensor.extra_state_attributes["race"]["race_name"] == "Test GP"

    sensor.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="1",
            attributes={
                "name": "Document 1 - Decision",
                "url": "https://fia.test/1",
                "published": "2026-09-01T11:00:00Z",
                "race": "bad",
            },
        )
    )
    await sensor._restore_last_state()
    assert sensor._attr_native_value == 1
    assert sensor.extra_state_attributes["race"] is None


def test_pit_stops_and_championship_payload_update_paths() -> None:
    pit = F1PitStopsSensor(_coordinator({}), "pit", "entry", "F1")
    pit._apply_payload(
        {
            "total_stops": "2.0",
            "cars": {"4": {"stops": 1}},
            "last_update": "now",
            "last_reset": "2026-09-01T12:00:00Z",
        }
    )
    assert pit._attr_native_value == 2
    assert pit.last_reset is not None
    pit._apply_payload({"total_stops": "bad", "cars": []})
    assert pit._attr_native_value == 0
    assert pit.extra_state_attributes["cars"] == {}
    assert pit._parse_last_reset("bad") is None
    assert pit._parse_last_reset(1) is None

    pit._handle_stream_state = Mock(return_value=True)
    pit._is_stream_active = Mock(return_value=False)
    pit._safe_write_ha_state = Mock()
    pit._handle_coordinator_update()
    pit._is_stream_active = Mock(return_value=True)
    pit.coordinator.data = None
    pit._handle_coordinator_update()
    pit.coordinator.data = {"total_stops": 3}
    pit._handle_coordinator_update()
    assert pit._attr_native_value == 3

    drivers = F1ChampionshipPredictionDriversSensor(
        _coordinator({}), "driver_prediction", "entry", "F1"
    )
    teams = F1ChampionshipPredictionTeamsSensor(
        _coordinator({}), "team_prediction", "entry", "F1"
    )
    drivers._apply_payload(
        {
            "predicted_driver_p1": {"tla": " NOR "},
            "drivers": {"NOR": {"points": 100}},
            "last_update": "now",
        }
    )
    teams._apply_payload(
        {
            "predicted_team_p1": {"team_name": " McLaren "},
            "teams": {"McLaren": {"points": 200}},
            "last_update": "now",
        }
    )
    assert drivers._attr_native_value == "NOR"
    assert teams._attr_native_value == "McLaren"
    drivers._apply_payload({"predicted_driver_p1": "bad", "drivers": []})
    teams._apply_payload({"predicted_team_p1": "bad", "teams": []})
    assert drivers.extra_state_attributes["drivers"] == {}
    assert teams.extra_state_attributes["teams"] == {}

    for prediction in (drivers, teams):
        prediction._handle_stream_state = Mock(return_value=True)
        prediction._is_stream_active = Mock(return_value=False)
        prediction._safe_write_ha_state = Mock()
        prediction._handle_coordinator_update()
        prediction._is_stream_active = Mock(return_value=True)
        prediction.coordinator.data = None
        prediction._handle_coordinator_update()


def test_straight_mode_update_terminal_and_stream_paths() -> None:
    sensor = F1StraightModeSensor(
        _coordinator({"straight_mode": "normal_grip", "overtake_enabled": True}),
        "straight",
        "entry",
        "F1",
    )
    sensor.async_write_ha_state = Mock()
    assert sensor._has_straight_mode_state(sensor.coordinator.data) is True
    sensor._apply_data(sensor.coordinator.data)
    assert sensor.native_value == "normal_grip"
    assert sensor.available is True

    sensor.coordinator.session_is_terminal = True
    sensor._handle_coordinator_update()
    assert sensor.native_value is None
    assert sensor.available is False

    sensor.coordinator.session_is_terminal = False
    sensor._handle_stream_state = Mock(return_value=False)
    sensor._handle_coordinator_update()
    sensor._handle_stream_state = Mock(return_value=True)
    sensor._is_stream_active = Mock(return_value=False)
    sensor._handle_coordinator_update()
    sensor._is_stream_active = Mock(return_value=True)
    sensor.coordinator.data = {}
    sensor._handle_coordinator_update()
    sensor.coordinator.data = {
        "straight_mode": "disabled",
        "overtake_enabled": False,
    }
    sensor._handle_coordinator_update()
    assert sensor.native_value == "disabled"


def test_current_session_labels_status_and_end_detection(hass) -> None:
    coordinator = _coordinator({"Type": "Race", "Name": "Grand Prix"})
    sensor = F1CurrentSessionSensor(coordinator, "session", "entry", "F1")
    sensor.hass = hass
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "drivers_coordinator": _coordinator({"session": {"part": 2}})
    }

    assert sensor._resolve_label({"Type": "Practice", "Number": "2"})[0] == (
        "Practice 2"
    )
    assert sensor._resolve_label({"Type": "Practice", "Number": "bad"})[0] == (
        "Practice"
    )
    assert (
        sensor._resolve_label({"Type": "Qualifying", "Name": "Sprint Shootout"})[0]
        == "Sprint Qualifying"
    )
    assert (
        sensor._resolve_label({"Type": "Race", "Name": "Sprint Qualifying"})[0]
        == "Sprint Qualifying"
    )
    assert sensor._resolve_label({"Type": "Race", "Name": "Sprint"})[0] == "Sprint"
    assert sensor._resolve_label({"Type": "Other", "Name": "Warm-up"})[0] == ("Warm-up")

    sensor._status_coordinator = _coordinator({"Status": "Started"})
    sensor._apply_payload(
        {
            "Type": "Race",
            "Name": "Grand Prix",
            "Meeting": {
                "Key": 1,
                "Name": "Test GP",
                "Country": {"Name": "Sweden"},
                "Circuit": {"ShortName": "Test"},
            },
        }
    )
    assert sensor.state == "Grand Prix"
    assert sensor._attr_extra_state_attributes["active"] is True

    sensor._status_coordinator.data = {"Status": "Finished"}
    sensor._apply_payload({"Type": "Race", "Name": "Grand Prix"})
    assert sensor.state is None
    assert sensor._attr_extra_state_attributes["last_label"] == "Grand Prix"

    sensor._status_coordinator.data = {"Status": "Started"}
    sensor._apply_payload({"Type": "Qualifying", "Name": "Qualifying"})
    assert sensor.state == "Qualifying"
    sensor._status_coordinator.data = {"Status": "Finished"}
    sensor._apply_payload({"Type": "Qualifying", "Name": "Qualifying"})
    assert sensor.state is None

    sensor._status_coordinator = SimpleNamespace(data="bad")
    assert sensor._live_status_payload() is None
    assert sensor._live_status() is None
    sensor._status_coordinator = SimpleNamespace(
        data={"Status": "Inactive"},
        is_qualifying_like_session=False,
        qualifying_part=None,
    )
    sensor._attr_native_value = "Race"
    sensor._apply_payload(
        {
            "Type": "Race",
            "Name": "Race",
            "EndDate": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        },
        allow_clear=False,
    )
    assert sensor.state == "Race"

    sensor.async_write_ha_state = Mock()
    sensor._handle_stream_state = Mock(return_value=False)
    sensor._handle_coordinator_update()
    sensor._handle_status_update()
    sensor._handle_stream_state = Mock(return_value=True)
    sensor._is_stream_active = Mock(return_value=False)
    sensor._handle_coordinator_update()
    sensor._handle_status_update()
    sensor._clear_state()
    assert sensor.state is None


def test_session_status_metadata_grip_and_update_guards() -> None:
    coordinator = _coordinator({"data": {"Status": "Started"}})
    sensor = F1SessionStatusSensor(coordinator, "status", "entry", "F1")
    assert sensor._extract_current() == {"Status": "Started"}
    coordinator.data = {"Message": "Finished"}
    assert sensor._extract_current() == {"Message": "Finished"}
    coordinator.data = "bad"
    assert sensor._extract_current() is None

    sensor._session_info_coordinator = _coordinator(
        {
            "Meeting": {
                "Name": "Test GP",
                "Location": "Gothenburg",
                "Country": {"Name": "Sweden"},
                "Circuit": {"ShortName": "Test"},
            },
            "GmtOffset": "+02:00",
            "StartDate": "start",
            "EndDate": "end",
        }
    )
    attrs = sensor._extract_session_info()
    assert attrs["meeting_country"] == "Sweden"
    sensor._session_info_coordinator.data = "bad"
    assert sensor._extract_session_info() == {}

    sensor._race_control_coordinator = _coordinator(
        data_list=[
            {"Message": "NORMAL GRIP CONDITIONS"},
            {"Message": "LOW GRIP CONDITIONS"},
        ]
    )
    assert sensor._detect_track_grip() == "low"
    sensor._race_control_coordinator.data_list = [{"Text": "NORMAL GRIP CONDITIONS"}]
    assert sensor._detect_track_grip() == "normal"
    sensor._race_control_coordinator.data_list = [{"Message": "Other"}]
    sensor._track_grip_state = None
    assert sensor._detect_track_grip() == "normal"
    sensor._race_control_coordinator = None
    assert sensor._detect_track_grip() == "normal"

    sensor.async_write_ha_state = Mock()
    sensor._is_stream_active = Mock(return_value=False)
    sensor._handle_session_info_update()
    sensor._handle_race_control_update()
    sensor._is_stream_active = Mock(return_value=True)
    sensor._session_info_coordinator = _coordinator({"Meeting": {"Name": "New"}})
    sensor._handle_session_info_update()
    sensor._race_control_coordinator = _coordinator(
        data_list=[{"Message": "LOW GRIP CONDITIONS"}]
    )
    sensor._handle_race_control_update()
    assert sensor._attr_extra_state_attributes["track_grip"] == "low"

    coordinator.data = None
    sensor._handle_stream_state = Mock(return_value=False)
    sensor._handle_coordinator_update()
    sensor._handle_stream_state = Mock(return_value=True)
    sensor._is_stream_active = Mock(return_value=False)
    sensor._handle_coordinator_update()
    sensor._is_stream_active = Mock(return_value=True)
    coordinator.data = {"Status": "Started"}
    sensor._handle_coordinator_update()
    sensor._handle_coordinator_update()
    sensor._clear_state()
    assert sensor.native_value is None


def test_team_radio_urls_history_and_update_guards(hass) -> None:
    coordinator = _coordinator({"latest": {"Utc": "2026-09-01T12:00:00Z"}})
    sensor = F1TeamRadioSensor(coordinator, "radio", "entry", "F1")
    sensor.hass = hass
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_supervisor": SimpleNamespace(
            current_window=SimpleNamespace(path="2026/test/session")
        ),
        "session_coordinator": SimpleNamespace(year=2026),
    }
    assert sensor._normalize_utc(None) is None
    assert sensor._normalize_utc("bad") == "bad"
    assert sensor._build_clip_url({}, None) is None
    assert (
        sensor._build_clip_url(
            {"_static_root": "https://static.test/root/"}, "/clip.mp3"
        )
        == "https://static.test/root/clip.mp3"
    )
    assert sensor._build_clip_url({}, "clip.mp3").endswith(
        "/2026/test/session/clip.mp3"
    )

    payload = {
        "Utc": "2026-09-01T12:00:00Z",
        "RacingNumber": 4,
        "Path": "clip.mp3",
    }
    sensor._apply_payload(payload)
    first_sequence = sensor._sequence
    sensor._apply_payload(payload)
    assert sensor._sequence == first_sequence
    sensor._apply_payload(payload, force=True)
    assert sensor._sequence == first_sequence + 1
    assert sensor.extra_state_attributes["racing_number"] == "4"

    sensor._safe_write_ha_state = Mock()
    sensor._handle_stream_state = Mock(return_value=False)
    sensor._handle_coordinator_update()
    sensor._handle_stream_state = Mock(return_value=True)
    sensor._is_stream_active = Mock(return_value=False)
    sensor._handle_coordinator_update()
    sensor._is_stream_active = Mock(return_value=True)
    coordinator.data = {}
    sensor._handle_coordinator_update()
    sensor._clear_state()
    assert sensor.state is None


async def test_stream_base_lifecycle_and_driver_positions_restore(hass) -> None:
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": SimpleNamespace(is_live=True, reason="live"),
        "session_info_coordinator": _ha_coordinator(
            hass, {"Type": "Qualifying", "Name": "Qualifying"}
        ),
        "session_status_coordinator": _ha_coordinator(hass, {"Status": "Started"}),
    }
    tyres_coord = _ha_coordinator(
        hass,
        {
            "drivers": {
                "4": {
                    "identity": {"tla": "NOR"},
                    "tyres": {"compound": "SOFT"},
                }
            }
        },
    )
    tyres = F1CurrentTyresSensor(tyres_coord, "tyres", "entry", "F1")
    tyres.hass = hass
    tyres.entity_id = "sensor.tyres"
    tyres.async_write_ha_state = Mock()
    tyres._safe_write_ha_state = Mock()
    await tyres.async_added_to_hass()
    assert tyres.state == 1
    tyres_coord.data = {}
    tyres._handle_coordinator_update()

    positions_coord = _ha_coordinator(hass, {})
    positions = F1DriverPositionsSensor(
        positions_coord, "positions_restore", "entry", "F1"
    )
    positions.hass = hass
    positions.entity_id = "sensor.positions_restore"
    positions.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="12",
            attributes={"drivers": [{"racing_number": "4"}]},
        )
    )
    positions.async_write_ha_state = Mock()
    await positions.async_added_to_hass()
    assert positions.state == 12

    positions.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(state="bad", attributes={})
    )
    await positions._restore_state()
    assert positions.state is None


def test_driver_positions_qualifying_segments_and_top_three_payload(hass) -> None:
    coordinator = _coordinator(
        {
            "lap_current": 3,
            "lap_total": 70,
            "session": {"part": 2},
            "drivers": {
                "4": {
                    "identity": {
                        "tla": "NOR",
                        "team_color": "ff8700",
                    },
                    "lap_history": {"grid_position": "2"},
                    "timing": {"position": "1", "pit_out": True},
                    "sectors": {
                        "current": {0: {"time": "30.0", "lap": 3}},
                        "best": {0: "29.0"},
                        "personal_best": {
                            0: {"time": "29.0", "lap": 2, "session_part": 1}
                        },
                    },
                    "qualifying": {
                        "knocked_out": True,
                        "segments": {
                            1: {"best_time": "1:20.000", "participated": True},
                            2: {"best_time": "bad", "participated": True},
                            3: {"best_time": None, "participated": False},
                        },
                    },
                },
                "81": {
                    "identity": {"tla": "PIA"},
                    "lap_history": {"grid_position": None},
                    "timing": {},
                    "sectors": {},
                    "qualifying": {"segments": {1: {"best_time": "1:19.000"}}},
                },
            },
        }
    )
    positions = F1DriverPositionsSensor(coordinator, "positions", "entry", "F1")
    positions.hass = hass
    hass.data.setdefault(DOMAIN, {})["entry"] = {}
    positions._session_info_coordinator = _coordinator(
        {"Type": "Qualifying", "Name": "Qualifying"}
    )
    assert positions._update_from_coordinator() is True
    drivers = positions.extra_state_attributes["drivers"]
    assert drivers[0]["team_color_rgb"] == [255, 135, 0]
    assert drivers[0]["q2_knocked_out"] is True
    assert drivers[1]["q1_position"] == 1
    assert positions.extra_state_attributes["current_qualifying_part"] == 2

    top = F1TopThreePositionSensor(
        _coordinator(
            {
                "lines": [
                    {
                        "RacingNumber": "4",
                        "Tla": "NOR",
                        "Position": "1",
                        "DiffToLeader": "+0.000",
                    }
                ],
                "withheld": False,
            }
        ),
        "top",
        "entry",
        "F1",
        0,
    )
    top._update_from_coordinator(initial=True)
    assert top.native_value == "NOR"
    top.coordinator.data = {"lines": [], "withheld": True}
    top._update_from_coordinator(initial=True)
    assert top.native_value is None
