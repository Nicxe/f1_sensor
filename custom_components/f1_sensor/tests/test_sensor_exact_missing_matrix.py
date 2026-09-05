"""Exact defensive and restore branches reported by the CI coverage profile."""

from __future__ import annotations

from datetime import UTC
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.f1_sensor import sensor as sensor_platform
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.sensor import (
    F1ConstructorPointsProgressionSensor,
    F1CurrentSessionSensor,
    F1CurrentTyresSensor,
    F1DriverListSensor,
    F1DriverPointsProgressionSensor,
    F1DriverPositionsSensor,
    F1FavoriteDriverSensor,
    F1FiaDocumentsSensor,
    F1InvestigationsSensor,
    F1LiveTimingModeSensor,
    F1RaceControlSensor,
    F1RaceLapCountSensor,
    F1RaceTimeToThreeHourLimitSensor,
    F1SessionTimeElapsedSensor,
    F1StartingGridSensor,
    F1TopThreePositionSensor,
    F1TrackStatusSensor,
    F1TrackWeatherSensor,
    F1TyreStatisticsSensor,
    _async_setup_points_progression,
    _combine_date_time,
    _extract_driver_position,
    _map_session_status_payload,
    _to_float_value,
    _to_home,
    _to_local,
)


class _RaiseOnceDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._raised = False

    def get(self, key, default=None):
        if key == "team_color" and not self._raised:
            self._raised = True
            raise RuntimeError("color")
        return super().get(key, default)


class _RaiseSecondDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._calls = 0

    def get(self, key, default=None):
        if key == "team_color":
            self._calls += 1
            if self._calls == 2:
                raise RuntimeError("color")
        return super().get(key, default)


class _BadName:
    def __bool__(self):
        raise RuntimeError("name")


class _BadStateText:
    def isdigit(self):
        raise RuntimeError("state")


def _coordinator(hass, data=None):
    coordinator = DataUpdateCoordinator(
        hass, logging.getLogger(__name__), name="exact-sensor"
    )
    coordinator.data = data
    coordinator.data_list = []
    return coordinator


class _BadString:
    def __str__(self):
        raise RuntimeError("string conversion")


class _BadWindow:
    @property
    def label(self):
        raise RuntimeError("window")


class _BadSupervisor:
    @property
    def current_window(self):
        return _BadWindow()


class _BadBus:
    def last_heartbeat_age(self):
        raise RuntimeError("heartbeat")

    def last_stream_activity_age(self):
        raise RuntimeError("activity")

    def stream_diagnostics(self, _streams):
        raise RuntimeError("diagnostics")


class _BadGetDict(dict):
    def get(self, _key, _default=None):
        raise RuntimeError("get")


class _BadDataCoordinator:
    @property
    def data(self):
        raise RuntimeError("data")


class _BadStateController:
    @property
    def state(self):
        raise RuntimeError("state")


def test_scalar_helpers_and_live_mode_exact_defensive_paths(hass) -> None:
    assert _extract_driver_position(None) is None
    assert _extract_driver_position({"timing": {"position": _BadString()}}) is None
    assert _combine_date_time("bad", "bad") is None
    assert _to_local("bad", "Europe/Stockholm") is None
    assert _to_home(hass, "bad") is None
    old_tz = hass.config.time_zone
    hass.config.time_zone = None
    assert _to_home(hass, "2026-09-01T12:00:00+00:00").startswith("2026")
    hass.config.time_zone = "Invalid/Timezone"
    assert _to_home(hass, "2026-09-01T12:00:00+00:00").startswith("2026")
    hass.config.time_zone = old_tz
    assert _to_float_value(None) == 0.0
    assert _to_float_value(_BadString()) == 0.0

    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": SimpleNamespace(is_live=True, reason="live"),
        "live_supervisor": _BadSupervisor(),
        "live_bus": _BadBus(),
        "signalr_stream_capabilities": {"active_live_streams": [None, " "]},
    }
    sensor = F1LiveTimingModeSensor(hass, "entry", "F1")
    mode, attrs = sensor._compute()
    assert mode == "live"
    assert attrs["window"] is None
    assert attrs["heartbeat_age_s"] is None
    assert attrs["streams"]


async def test_favorite_and_points_restore_exact_lifecycle(hass) -> None:
    remove = Mock()
    controller = SimpleNamespace(
        available=True,
        snapshot={"position": 2, "tla": "NOR"},
        selected_tla="NOR",
        add_listener=Mock(return_value=remove),
    )
    favorite = F1FavoriteDriverSensor(controller, "favorite", "entry", "F1")
    favorite.hass = hass
    favorite.async_write_ha_state = Mock()
    await favorite.async_added_to_hass()
    assert favorite.native_value == 2
    assert favorite.extra_state_attributes["selected"] == "NOR"
    favorite._handle_update()
    favorite.async_write_ha_state.assert_called_once()
    await favorite.async_will_remove_from_hass()
    remove.assert_called_once()

    points = F1DriverPointsProgressionSensor(
        _coordinator(hass, {}), "points", "entry", "F1"
    )
    points.hass = hass
    points.entity_id = "sensor.points"
    points._recompute = Mock()
    points.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(state="bad", attributes={"series": {}})
    )
    points.async_write_ha_state = Mock()
    await _async_setup_points_progression(points)
    assert points._attr_native_value is None
    points.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(state="3", attributes={"series": {}})
    )
    await _async_setup_points_progression(points)
    assert points._attr_native_value == 3


async def test_top_three_race_control_and_current_session_restore_paths(hass) -> None:
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": SimpleNamespace(is_live=True, reason="live")
    }
    top = F1TopThreePositionSensor(
        _coordinator(hass, None), "top_exact", "entry", "F1", 0
    )
    top.hass = hass
    top.entity_id = "sensor.top_exact"
    top.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(state="NOR", attributes={"team": "McLaren"})
    )
    top.async_write_ha_state = Mock()
    await top.async_added_to_hass()
    assert top.native_value == "NOR"
    assert top.extra_state_attributes["team"] == "McLaren"

    race = F1RaceControlSensor(_coordinator(hass, None), "race_exact", "entry", "F1")
    race.hass = hass
    race.entity_id = "sensor.race_exact"
    race.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="Yellow",
            attributes={"event_id": "one", "history": [{"message": "Yellow"}, "bad"]},
        )
    )
    race.async_write_ha_state = Mock()
    await race.async_added_to_hass()
    assert race.state == "Yellow"
    assert race._history == [{"message": "Yellow"}]
    assert race._resolve_icon(None, "SafetyCar") == "mdi:car-emergency"
    assert race._resolve_icon(None, "VSC") == "mdi:car-brake-alert"

    current = F1CurrentSessionSensor(
        _coordinator(hass, None), "current_exact", "entry", "F1"
    )
    current.hass = hass
    current.entity_id = "sensor.current_exact"
    current.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="Practice 1",
            attributes={"end": "bad", "meeting_name": "Test GP"},
        )
    )
    current.async_write_ha_state = Mock()
    await current.async_added_to_hass()
    assert current.state == "Practice 1"


def test_weather_progression_and_session_clock_exact_branches(hass) -> None:
    weather = F1TrackWeatherSensor(
        _coordinator(hass, {"AirTemp": "20", "Utc": "2026-09-01T12:00:00"}),
        "weather_exact",
        "entry",
        "F1",
    )
    weather.hass = hass
    weather.entity_id = "sensor.weather_exact"
    weather.async_write_ha_state = Mock()
    weather.schedule_update_ha_state = Mock()
    weather._apply_payload(weather.coordinator.data)
    assert weather._last_timestamped_dt.tzinfo is UTC
    weather._handle_stream_state = Mock(return_value=True)
    weather._is_stream_active = Mock(return_value=False)
    weather._handle_coordinator_update()
    weather._is_stream_active = Mock(return_value=True)
    weather.coordinator.data = None
    weather._handle_coordinator_update()

    hass.data.setdefault(DOMAIN, {}).setdefault("entry", {}).update(
        {
            "race_coordinator": SimpleNamespace(
                data={"MRData": {"RaceTable": {"Races": [{"round": "1"}]}}}
            ),
            "driver_coordinator": SimpleNamespace(data="bad"),
            "constructor_coordinator": SimpleNamespace(data="bad"),
        }
    )
    drivers = F1DriverPointsProgressionSensor(
        _coordinator(hass, {}), "drivers_exact", "entry", "F1"
    )
    constructors = F1ConstructorPointsProgressionSensor(
        _coordinator(hass, {}), "teams_exact", "entry", "F1"
    )
    drivers.hass = hass
    constructors.hass = hass
    assert drivers._get_full_schedule() == [{"round": "1"}]
    assert drivers._get_driver_standings() == ({}, None)
    assert constructors._get_constructor_standings() == ({}, None)

    clock_data = {
        "clock_elapsed_s": "bad",
        "clock_total_s": 100,
        "clock_remaining_s": 50,
        "source_quality": "official",
        "session_type": "Race",
        "session_name": "Race",
    }
    elapsed = F1SessionTimeElapsedSensor(
        _coordinator(hass, clock_data), "elapsed_exact", "entry", "F1"
    )
    assert elapsed._extract_value(clock_data) is None
    attrs = elapsed._build_attrs(clock_data, 50)
    assert attrs["clock_remaining_s"] == 50
    elapsed._clear_state()
    assert elapsed.native_value is None
    cap = F1RaceTimeToThreeHourLimitSensor(
        _coordinator(hass, clock_data), "cap_exact", "entry", "F1"
    )
    assert cap._is_value_available(clock_data, 10) is True


def test_investigations_exact_message_transitions(hass) -> None:
    sensor = F1InvestigationsSensor(
        _coordinator(hass, {}), "investigations_exact", "entry", "F1"
    )
    assert sensor._expire_nfi_items() is False
    assert (
        sensor._process_message(
            {"Utc": "1", "Message": "TRACK LIMITS WARNING - INVESTIGATION"}
        )
        is False
    )
    assert (
        sensor._process_message(
            {"Utc": "2", "Message": "TRACK LIMITS LAP DELETED - INVESTIGATION"}
        )
        is False
    )
    assert (
        sensor._process_message(
            {
                "Utc": "2026-09-01T12:00:00Z",
                "Message": "INCIDENT INVOLVING CAR 4 (NOR) NOTED - CAUSING A COLLISION",
            }
        )
        is True
    )
    assert (
        sensor._process_message(
            {
                "Utc": "2026-09-01T12:01:00Z",
                "Message": "FIA STEWARDS: CAR 4 (NOR) NO FURTHER INVESTIGATION",
            }
        )
        is True
    )
    assert sensor._nfi
    assert (
        sensor._process_message(
            {
                "Utc": "2026-09-01T12:02:00Z",
                "Message": "FIA STEWARDS: CAR 81 (PIA) UNDER INVESTIGATION - UNSAFE RELEASE",
            }
        )
        is True
    )
    assert (
        sensor._process_message(
            {
                "Utc": "2026-09-01T12:03:00Z",
                "Message": "FIA STEWARDS: CAR 81 (PIA) UNDER INVESTIGATION - UNSAFE RELEASE",
            }
        )
        is False
    )
    assert (
        sensor._process_message(
            {
                "Utc": "2026-09-01T12:04:00Z",
                "Message": "INCIDENT INVOLVING CAR 16 (LEC) NOTED - IMPEDING",
            }
        )
        is True
    )
    assert (
        sensor._process_message(
            {
                "Utc": "2026-09-01T12:05:00Z",
                "Message": "CAR 16 (LEC) WILL BE INVESTIGATED AFTER THE RACE - IMPEDING",
            }
        )
        is True
    )
    assert any(item.get("after_race") for item in sensor._under_investigation.values())
    assert (
        sensor._process_message(
            {
                "Utc": "2026-09-01T12:06:00Z",
                "Message": "INCIDENT INVOLVING CAR 44 (HAM) NOTED",
            }
        )
        is True
    )
    assert (
        sensor._process_message(
            {
                "Utc": "2026-09-01T12:07:00Z",
                "Message": "INCIDENT INVOLVING CAR 44 (HAM) NOTED",
            }
        )
        is False
    )
    assert (
        sensor._process_message({"Utc": "8", "Message": "INVESTIGATION STATUS UNKNOWN"})
        is False
    )
    sensor.coordinator.data_list = "bad"
    sensor._process_all_messages()
    sensor._handle_live_state(True, "init")
    sensor._handle_live_state(True, "no-spoiler")


async def test_investigations_inactive_and_listener_failure(hass) -> None:
    coordinator = _coordinator(hass, {})
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": SimpleNamespace(
            add_listener=Mock(side_effect=RuntimeError("listener"))
        )
    }
    sensor = F1InvestigationsSensor(
        coordinator, "investigations_inactive", "entry", "F1"
    )
    sensor.hass = hass
    sensor.entity_id = "sensor.investigations_inactive"
    sensor._is_stream_active = Mock(return_value=False)
    sensor.async_write_ha_state = Mock()
    await sensor.async_added_to_hass()
    assert sensor.native_value == 0
    sensor.async_get_last_state = AsyncMock(return_value=None)
    await sensor._restore_from_last()


def test_driver_and_tyre_exact_defensive_matrices(hass) -> None:
    driver_list = F1DriverListSensor(
        _coordinator(hass, "bad"), "drivers_exact", "entry", "F1"
    )
    assert driver_list._update_from_coordinator() is False
    driver_list.coordinator.data = {
        "drivers": {
            "4": {"identity": _RaiseOnceDict({"team_color": "FF00FF"})},
            "bad": "ignored",
        }
    }
    assert driver_list._update_from_coordinator() is True
    assert driver_list.native_value == 2
    assert driver_list._bootstrap_from_ergast() is False
    driver_list.hass = hass
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "driver_coordinator": SimpleNamespace(
            data={
                "MRData": {
                    "StandingsTable": {
                        "StandingsLists": [
                            {
                                "DriverStandings": [
                                    "bad",
                                    {"Driver": "bad"},
                                    {"Driver": {"permanentNumber": ""}},
                                    {
                                        "Driver": {
                                            "permanentNumber": "4",
                                            "givenName": _BadName(),
                                        }
                                    },
                                ]
                            }
                        ]
                    }
                }
            }
        )
    }
    assert driver_list._bootstrap_from_ergast() is True

    current = F1CurrentTyresSensor(
        _coordinator(hass, "bad"), "current_tyres_exact", "entry", "F1"
    )
    assert current._update_from_coordinator() is False
    current.coordinator.data = {
        "drivers": {
            "skip": "bad",
            "4": {
                "identity": _RaiseSecondDict(
                    {"racing_number": "4", "team_color": "FF00FF"}
                ),
                "tyres": {"compound": "prototype"},
            },
        }
    }
    assert current._update_from_coordinator() is True
    assert current.extra_state_attributes["drivers"][0]["compound_short"] == "?"
    current._clear_state()

    stats = F1TyreStatisticsSensor(
        _coordinator(hass, "bad"), "tyre_stats_exact", "entry", "F1"
    )
    assert stats._compound_from_tyre_history({}) is None
    assert stats._compound_from_tyre_history({"tyre_history": {}}) is None
    assert (
        stats._compound_from_tyre_history(
            {
                "tyre_history": {
                    "stints": [
                        "bad",
                        {"compound": " unknown "},
                        {"compound": " soft "},
                    ]
                }
            }
        )
        == "SOFT"
    )
    assert stats._update_from_coordinator() is False
    stats.coordinator.data = {
        "drivers": {
            "bad": "bad",
            "4": {
                "tyre_history": {"stints": [{"compound": "SOFT"}]},
                "tyres": {"stint_laps": 2},
            },
        }
    }
    assert stats._update_waiting_for_compound_data(stats.coordinator.data) is False
    stats.coordinator.data["drivers"]["4"]["tyre_history"]["stints"] = [{}]
    assert stats._update_waiting_for_compound_data(stats.coordinator.data) is True
    stats.coordinator.data["tyre_statistics"] = {"compounds": "bad"}
    assert stats._update_from_coordinator() is True
    stats._clear_state()


async def test_positions_exact_context_fallback_and_clear_paths(hass) -> None:
    coordinator = _coordinator(hass, {})
    sensor = F1DriverPositionsSensor(coordinator, "positions_exact", "entry", "F1")
    sensor.hass = hass
    sensor.entity_id = "sensor.positions_exact"
    sensor._is_stream_active = Mock(return_value=False)
    sensor.async_write_ha_state = Mock()
    hass.data.setdefault(DOMAIN, {})["entry"] = {}
    await sensor.async_added_to_hass()
    assert sensor.native_value is None
    sensor.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(state=_BadStateText(), attributes={})
    )
    await sensor._restore_state()
    assert sensor.native_value is None
    sensor._handle_stream_state = Mock(return_value=False)
    sensor._handle_coordinator_update()
    sensor._handle_context_update()
    sensor._session_info_coordinator = SimpleNamespace(data="bad")
    sensor._get_session_from_replay = Mock(return_value=("Race", "Replay Race"))
    assert sensor._get_session_type_and_name() == ("Race", "Replay Race")
    sensor._session_info_coordinator = SimpleNamespace(data={})
    assert sensor._get_session_type_and_name() == ("Race", "Replay Race")
    sensor._get_session_from_replay = Mock(return_value=(None, None))
    sensor._get_session_name_from_window = Mock(return_value=(None, "Window Race"))
    assert sensor._get_session_type_and_name() == (None, "Window Race")
    assert sensor._is_race_or_sprint("Sprint", None) is True
    hass.data[DOMAIN]["entry"] = {
        "replay_controller": SimpleNamespace(session_manager=None),
        "live_supervisor": SimpleNamespace(current_window=None),
    }
    del sensor._get_session_name_from_window
    assert sensor._get_session_from_replay() == (None, None)
    assert sensor._get_session_name_from_window() == (None, None)
    assert sensor._update_from_coordinator() is False


def test_race_lap_count_exact_timestamp_and_write_paths(hass, monkeypatch) -> None:
    sensor = F1RaceLapCountSensor(_coordinator(hass, {}), "laps_exact", "entry", "F1")
    sensor.hass = hass
    sensor.entity_id = "sensor.laps_exact"
    sensor.coordinator.data = {
        "CurrentLap": "2",
        "Utc": "2026-09-01T12:00:00",
    }
    sensor._apply_payload(sensor.coordinator.data)
    assert sensor._last_timestamped_dt.tzinfo is UTC
    sensor._attr_extra_state_attributes = SimpleNamespace()
    sensor._apply_payload({"CurrentLap": 3})
    sensor.schedule_update_ha_state = Mock()
    with monkeypatch.context() as context:
        context.setattr("asyncio.get_running_loop", Mock(side_effect=RuntimeError))
        sensor._safe_write_ha_state()
    sensor.schedule_update_ha_state.assert_called_once()
    sensor._handle_stream_state = Mock(return_value=False)
    sensor._handle_coordinator_update()


def test_silver_document_progression_and_status_defensive_paths(
    hass, monkeypatch
) -> None:
    documents = F1FiaDocumentsSensor(
        _coordinator(hass, {}), "fia_silver", "entry", "F1"
    )
    documents._update_from_coordinator = Mock(return_value=True)
    documents._safe_write_ha_state = Mock()
    documents._handle_coordinator_update()
    documents._safe_write_ha_state.assert_called_once()

    latest = documents._select_latest_document(
        [
            "ignored",
            {
                "name": "Document 2 - Old",
                "published": "2026-09-01T10:00:00Z",
            },
            {
                "name": "Document 2 - New",
                "published": "2026-09-01T11:00:00Z",
            },
        ]
    )
    assert latest["name"] == "Document 2 - New"

    drivers = F1DriverPointsProgressionSensor(
        _coordinator(hass, {}), "drivers_silver", "entry", "F1"
    )
    constructors = F1ConstructorPointsProgressionSensor(
        _coordinator(hass, {}), "constructors_silver", "entry", "F1"
    )
    drivers.hass = hass
    constructors.hass = hass
    monkeypatch.setattr(
        sensor_platform,
        "entry_runtime_registry",
        Mock(side_effect=RuntimeError("registry")),
    )
    assert drivers._get_full_schedule() == []
    assert drivers._get_driver_standings() == ({}, None)
    assert constructors._get_constructor_standings() == ({}, None)

    bad_standings = {
        "MRData": {
            "StandingsTable": {
                "StandingsLists": [
                    {
                        "round": _BadString(),
                        "DriverStandings": [
                            {
                                "Driver": {"code": "NOR"},
                                "points": _BadString(),
                            }
                        ],
                        "ConstructorStandings": [
                            {
                                "Constructor": {"constructorId": "mclaren"},
                                "points": _BadString(),
                            }
                        ],
                    }
                ]
            }
        }
    }
    monkeypatch.setattr(
        sensor_platform,
        "entry_runtime_registry",
        Mock(
            return_value={
                "driver_coordinator": SimpleNamespace(data=bad_standings),
                "constructor_coordinator": SimpleNamespace(data=bad_standings),
            }
        ),
    )
    assert drivers._get_driver_standings() == ({"NOR": 0.0}, None)
    assert constructors._get_constructor_standings() == ({"mclaren": 0.0}, None)

    bad_hass = SimpleNamespace(data=_BadGetDict())
    assert (
        _map_session_status_payload(
            {"Message": "Inactive", "Started": "Started"}, bad_hass
        )
        == "suspended"
    )
    assert (
        _map_session_status_payload(
            {"Message": "Aborted", "Started": "Started"}, bad_hass
        )
        == "suspended"
    )
    assert _map_session_status_payload({"Message": "Aborted"}, bad_hass) == "pre"


def test_silver_stream_update_and_context_fallback_paths(hass, monkeypatch) -> None:
    top = F1TopThreePositionSensor(
        _coordinator(hass, {"lines": []}), "top_silver", "entry", "F1", 0
    )
    top.hass = hass
    top.entity_id = "sensor.top_silver"
    top._attr_native_value = "OLD"
    top._safe_write_ha_state = Mock()
    top._last_write_ts = 1
    monkeypatch.setattr(
        sensor_platform,
        "async_call_later",
        Mock(side_effect=RuntimeError("schedule")),
    )
    top._update_from_coordinator()
    assert top.native_value is None
    top._safe_write_ha_state.assert_called_once()

    current = F1CurrentSessionSensor(
        _coordinator(hass, None), "current_silver", "entry", "F1"
    )
    current.hass = hass
    current.entity_id = "sensor.current_silver"
    current._handle_stream_state = Mock(return_value=True)
    current._is_stream_active = Mock(return_value=True)
    current.async_write_ha_state = Mock()
    current._handle_coordinator_update()
    current.coordinator.data = {"Name": "Race", "Type": "Race"}
    current._handle_coordinator_update()
    current.async_write_ha_state.assert_called_once()

    grid = F1StartingGridSensor(_coordinator(hass, {}), "grid_silver", "entry", "F1")
    grid._safe_write_ha_state = Mock()

    def _change_grid() -> bool:
        grid._attr_native_value = "available"
        return True

    grid._update_from_coordinator = _change_grid
    grid._handle_coordinator_update()
    grid._safe_write_ha_state.assert_called_once()
    grid._handle_coordinator_update()

    positions = F1DriverPositionsSensor(
        _coordinator(hass, {}), "positions_silver", "entry", "F1"
    )
    positions.hass = hass
    positions._session_info_coordinator = _BadDataCoordinator()
    monkeypatch.setattr(
        sensor_platform,
        "entry_runtime_registry",
        Mock(side_effect=RuntimeError("registry")),
    )
    assert positions._get_session_type_and_name() == (None, None)
    assert positions._get_session_from_replay() == (None, None)
    assert positions._get_session_name_from_window() == (None, None)
    sensor_platform.entry_runtime_registry = Mock(
        return_value={"replay_controller": _BadStateController()}
    )
    assert positions._is_replay_active() is False

    track = F1TrackStatusSensor(_coordinator(hass, None), "track_silver", "entry", "F1")
    track.hass = hass
    track.coordinator.data_list = ["bad", {"Status": "2"}]
    assert track._extract_current() == {"Status": "2"}

    weather = F1TrackWeatherSensor(
        _coordinator(hass, {}), "weather_silver", "entry", "F1"
    )
    weather.hass = hass
    weather.schedule_update_ha_state = Mock(side_effect=[RuntimeError("first"), None])
    weather._safe_write_ha_state()
    assert weather.schedule_update_ha_state.call_count == 2


async def test_silver_driver_list_invalid_restore_bootstraps(hass) -> None:
    driver_list = F1DriverListSensor(
        _coordinator(hass, {}), "drivers_silver_restore", "entry", "F1"
    )
    driver_list.hass = hass
    driver_list.entity_id = "sensor.drivers_silver_restore"
    driver_list.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(state="not-a-number", attributes={})
    )
    driver_list._bootstrap_from_ergast = Mock(return_value=True)
    driver_list.async_write_ha_state = Mock()
    await driver_list.async_added_to_hass()
    assert driver_list._attr_native_value is None
    driver_list._bootstrap_from_ergast.assert_called_once()
