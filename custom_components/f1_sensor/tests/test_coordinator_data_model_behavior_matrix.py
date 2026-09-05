"""Behavior matrix for coordinator payload models and normalizers."""

from __future__ import annotations

from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock

from custom_components.f1_sensor import (
    ChampionshipPredictionCoordinator,
    F1DataCoordinator,
    F1NextRaceHistoryCoordinator,
    LapCountCoordinator,
    PitStopCoordinator,
    RaceControlCoordinator,
    TeamRadioCoordinator,
    WeatherDataCoordinator,
)
from custom_components.f1_sensor.const import API_URL


def test_weather_and_lap_count_signalr_payload_parsers() -> None:
    assert WeatherDataCoordinator._parse_message(None) is None
    assert WeatherDataCoordinator._parse_message(
        {"M": [{"A": ["WeatherData", {"AirTemp": "20"}]}]}
    ) == {"AirTemp": "20"}
    assert WeatherDataCoordinator._parse_message(
        {"R": {"WeatherData": {"TrackTemp": "30"}}}
    ) == {"TrackTemp": "30"}
    assert WeatherDataCoordinator._parse_message({"M": [{"A": []}]}) is None
    assert WeatherDataCoordinator._has_timestamp({"Utc": "t"}) is True
    assert WeatherDataCoordinator._has_timestamp({}) is False

    coordinator = object.__new__(WeatherDataCoordinator)
    coordinator._last_message = {"AirTemp": "20", "Humidity": "50"}
    assert coordinator._should_skip_duplicate("bad") is False
    assert coordinator._should_skip_duplicate({"Utc": "t", "AirTemp": "20"}) is False
    assert coordinator._should_skip_duplicate({"AirTemp": "21"}) is False
    assert (
        coordinator._should_skip_duplicate({"AirTemp": "20", "Humidity": "50"}) is True
    )

    assert LapCountCoordinator._parse_message(None) is None
    assert LapCountCoordinator._parse_message(
        {"M": [{"A": ["LapCount", {"CurrentLap": 2}]}]}
    ) == {"CurrentLap": 2}
    assert LapCountCoordinator._parse_message(
        {"R": {"LapCount": {"CurrentLap": 3}}}
    ) == {"CurrentLap": 3}
    assert LapCountCoordinator._parse_message({"M": [{"A": []}]}) is None


def test_race_control_parser_and_normalized_message_shapes() -> None:
    assert RaceControlCoordinator._parse_message(None) is None
    assert RaceControlCoordinator._parse_message(
        {"M": [{"A": ["RaceControlMessages", {"Messages": []}]}]}
    ) == {"Messages": []}
    assert RaceControlCoordinator._parse_message(
        {"R": {"RaceControlMessages": {"Messages": []}}}
    ) == {"Messages": []}
    assert RaceControlCoordinator._parse_message({"M": [{"A": []}]}) is None
    assert RaceControlCoordinator._extract_items(None) == []
    assert RaceControlCoordinator._extract_items([{}, "bad"]) == [{}]
    assert RaceControlCoordinator._extract_items(
        {"Messages": [{"Message": "A"}, "bad"]}
    ) == [{"Message": "A"}]
    assert RaceControlCoordinator._extract_items(
        {"Messages": {"2": {"Message": "B"}, "1": {"Message": "A"}, "bad": {}}}
    ) == [
        {"Message": "A", "id": 1},
        {"Message": "B", "id": 2},
    ]
    assert RaceControlCoordinator._extract_items({"Message": "single"}) == [
        {"Message": "single"}
    ]

    coordinator = object.__new__(RaceControlCoordinator)
    coordinator._startup_cutoff = None
    coordinator._seen_ids_set = set()
    coordinator._seen_ids_order = deque(maxlen=2)
    coordinator._schedule_deliver = Mock()
    coordinator._on_bus_message(
        [
            {"Utc": "2026-09-01T12:00:00Z", "Message": "A"},
            {"Utc": "2026-09-01T12:00:01Z", "Message": "B"},
            {"Utc": "2026-09-01T12:00:02Z", "Message": "C"},
        ]
    )
    assert coordinator._schedule_deliver.call_count == 3
    coordinator._on_bus_message({"Utc": "2026-09-01T12:00:02Z", "Message": "C"})
    assert coordinator._schedule_deliver.call_count == 3


def test_pitstop_parsing_bounding_and_dedup_rebuild() -> None:
    assert PitStopCoordinator._parse_int(None) is None
    assert PitStopCoordinator._parse_int(2) == 2
    assert PitStopCoordinator._parse_int(" ") is None
    assert PitStopCoordinator._parse_int("3") == 3
    assert PitStopCoordinator._parse_int("4.9") == 4
    assert PitStopCoordinator._parse_int("bad") is None
    assert PitStopCoordinator._parse_float(None) is None
    assert PitStopCoordinator._parse_float(2) == 2.0
    assert PitStopCoordinator._parse_float(" ") is None
    assert PitStopCoordinator._parse_float("3.5") == 3.5
    assert PitStopCoordinator._parse_float("bad") is None
    assert PitStopCoordinator._normalize_racing_number(None) is None
    assert PitStopCoordinator._normalize_racing_number("0") is None
    assert PitStopCoordinator._normalize_racing_number("004") == "4"
    assert PitStopCoordinator._normalize_racing_number("bad") is None
    assert PitStopCoordinator._bounded_text(None) is None
    assert PitStopCoordinator._bounded_text(" ") is None
    assert PitStopCoordinator._bounded_text(" x ") == "x"

    coordinator = object.__new__(PitStopCoordinator)
    coordinator._by_car = {
        "4": [
            {
                "lap": "2",
                "timestamp": "t",
                "pit_lane_time": "20.1",
                "pit_stop_time": "2.2",
            },
            "bad",
        ],
        "bad": "ignored",
    }
    coordinator._dedup = set()
    coordinator._rebuild_pitstop_dedup()
    assert len(coordinator._dedup) == 1

    coordinator._history_limit = 2
    coordinator._by_car = {}
    coordinator._dedup = set()
    coordinator._maybe_update_pit_delta = lambda _rn, _entry: None
    coordinator._ingest_pitstopseries(
        {
            "PitTimes": {
                "4": [
                    {
                        "Timestamp": "t1",
                        "PitStop": {
                            "RacingNumber": "4",
                            "Lap": "2",
                            "PitStopTime": "2.2",
                            "PitLaneTime": "20.1",
                        },
                    },
                    {"Timestamp": "bad", "PitStop": "bad"},
                    "bad",
                ],
                "81": {
                    "0": {
                        "Timestamp": "t2",
                        "PitStop": {"Lap": 3, "PitStopTime": 2.3},
                    }
                },
                "bad": "ignored",
            }
        }
    )
    assert len(coordinator._by_car["4"]) == 1
    assert len(coordinator._by_car["81"]) == 1
    coordinator._add_stop("bad", {})
    coordinator._add_stop("4", {"timestamp": "t1", "lap": 2})


def test_team_radio_capture_normalization_shapes() -> None:
    assert TeamRadioCoordinator._normalize_captures("bad") == []
    assert TeamRadioCoordinator._normalize_captures(
        {"Captures": [{"Path": "a"}, "bad"], "_static_root": "root"}
    ) == [{"Path": "a", "_static_root": "root"}]
    assert TeamRadioCoordinator._normalize_captures(
        {"Captures": {"2": {"Path": "b"}, "1": {"Path": "a"}}}
    ) == [{"Path": "a"}, {"Path": "b"}]
    assert TeamRadioCoordinator._normalize_captures(
        {"Captures": {"Utc": "t", "Path": "a"}}
    ) == [{"Utc": "t", "Path": "a"}]
    assert TeamRadioCoordinator._normalize_captures(
        {"Utc": "t", "RacingNumber": "4"}
    ) == [{"Utc": "t", "RacingNumber": "4"}]


def test_championship_prediction_merge_selection_and_number_parsing() -> None:
    assert ChampionshipPredictionCoordinator._to_int(None) is None
    assert ChampionshipPredictionCoordinator._to_int("2.9") == 2
    assert ChampionshipPredictionCoordinator._to_int("bad") is None
    assert ChampionshipPredictionCoordinator._to_float(None) is None
    assert ChampionshipPredictionCoordinator._to_float("2.5") == 2.5
    assert ChampionshipPredictionCoordinator._to_float("bad") is None
    assert ChampionshipPredictionCoordinator._deep_merge(
        {"a": {"x": 1}}, {"a": {"y": 2}, "b": 3}
    ) == {"a": {"x": 1, "y": 2}, "b": 3}

    coordinator = object.__new__(ChampionshipPredictionCoordinator)
    coordinator._drivers = {}
    coordinator._teams = {}
    coordinator._driver_map = {}
    coordinator._schedule_deliver = lambda: None
    coordinator._ingest_prediction(
        {
            "Drivers": {
                "4": {"PredictedPosition": "2", "Nested": {"a": 1}},
                "1": {"RacingNumber": "1", "PredictedPosition": "1"},
                "bad": "ignored",
            },
            "Teams": {
                "mclaren": {"PredictedPosition": "2"},
                "ferrari": {"TeamKey": "FER", "PredictedPosition": "1"},
                "bad": "ignored",
            },
        }
    )
    assert coordinator._pick_predicted_driver_p1()[0] == "1"
    assert coordinator._pick_predicted_team_p1()[0] == "FER"
    coordinator._on_driverlist(
        {
            "4": {"Tla": "NOR", "FullName": "Lando", "TeamName": "McLaren"},
            "bad": "ignored",
        }
    )
    assert coordinator._driver_map["4"]["tla"] == "NOR"


def test_data_and_history_static_normalizers() -> None:
    coordinator = object.__new__(F1DataCoordinator)
    assert coordinator._extract_season(None) is None
    assert (
        coordinator._extract_season({"MRData": {"RaceTable": {"season": " 2026 "}}})
        == "2026"
    )
    assert (
        coordinator._extract_season(
            {"MRData": {"RaceTable": {"Races": [{"season": 2025}]}}}
        )
        == "2025"
    )
    assert (
        coordinator._extract_season({"MRData": {"RaceTable": {"season": " "}}}) is None
    )
    coordinator._url = "other"
    coordinator._last_seen_season = "2025"
    coordinator._handle_season_rollover_if_needed(
        {"MRData": {"RaceTable": {"season": "2026"}}}
    )
    assert coordinator._last_seen_season == "2025"
    saved = Mock()
    coordinator._url = API_URL
    coordinator._cache = {f"{API_URL}/drivers": 1, "other": 2}
    coordinator._persist = {f"{API_URL}/constructors": 1, "other": 2}
    coordinator._persist_save = saved
    coordinator.config_entry = None
    coordinator.hass = SimpleNamespace(data={})
    coordinator._handle_season_rollover_if_needed(
        {"MRData": {"RaceTable": {"season": "2026"}}}
    )
    assert coordinator._last_seen_season == "2026"
    assert all("/current" not in key for key in coordinator._cache)
    assert all("/current" not in key for key in coordinator._persist)
    assert saved.called

    history = F1NextRaceHistoryCoordinator
    assert history._season_int("bad") == 0
    assert history._round_int(None) == 0
    assert history._race_date(None) is None
    assert history._race_date({"date": " "}) is None
    assert history._race_key(None) == ("", "")
    assert history._driver_name(None) is None
    assert history._driver_name({"givenName": "Lando", "familyName": "Norris"}) == (
        "Lando Norris"
    )
    assert history._driver_name({"code": "NOR"}) == "NOR"
    assert history._first_race(None) is None
    assert history._first_race({"MRData": {"RaceTable": {"Races": ["bad"]}}}) is None
    results = [{"position": "2"}, {"position": "1"}]
    assert history._find_result(results, "1") == {"position": "1"}
    assert history._find_result([{"position": "2"}], "1") == {"position": "2"}
    assert history._is_finisher_status(None) is False
    assert history._is_finisher_status("Finished") is True
    assert history._is_finisher_status("+1 Lap") is True
    assert history._normalize_winner({}, None) is None
    assert history._normalize_pole({}, None) is None
    assert history._normalize_podium({}, []) is None
    assert history._normalize_first_race(None) is None
