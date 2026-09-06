"""Targeted Silver coverage for coordinator fallback and lifecycle behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import pytest

from custom_components.f1_sensor import (
    ChampionshipPredictionCoordinator,
    F1LapPositionProgressionCoordinator,
    F1NextRaceHistoryCoordinator,
    LiveDriversCoordinator,
    PitStopCoordinator,
)
from custom_components.f1_sensor.jolpica_pagination import JolpicaPaginationError


def _race_payload() -> dict:
    return {
        "season": "2026",
        "round": "1",
        "raceName": "Test Grand Prix",
        "Results": [
            "bad",
            {"Driver": {}},
            {
                "position": "2",
                "grid": "3",
                "Driver": {
                    "driverId": "norris",
                    "code": "NOR",
                    "givenName": "Lando",
                    "familyName": "Norris",
                },
                "Constructor": {"constructorId": "unknown"},
            },
        ],
    }


class _BadHeadshot(str):
    def find(self, *_args) -> int:
        raise RuntimeError("find")


class _BadPosition:
    def __str__(self) -> str:
        raise TypeError("position")


class _BadGetDict(dict):
    def get(self, _key, _default=None):
        raise RuntimeError("get")


@pytest.mark.asyncio
async def test_lap_position_silver_fallback_and_payload_matrix(
    hass, monkeypatch
) -> None:
    race = _race_payload()
    season_results = SimpleNamespace(
        data={"MRData": {"RaceTable": {"season": "2026", "Races": [race]}}}
    )
    sprint_results = SimpleNamespace(
        data={
            "MRData": {
                "RaceTable": {
                    "season": "2026",
                    "Races": [
                        {
                            "season": "2026",
                            "round": "1",
                            "raceName": "Test Sprint",
                            "SprintResults": [{}],
                        }
                    ],
                }
            }
        }
    )
    coordinator = F1LapPositionProgressionCoordinator(
        hass,
        race_coordinator=None,
        season_results_coordinator=season_results,
        sprint_results_coordinator=sprint_results,
        name="Silver lap positions",
        session=Mock(),
    )

    assert await coordinator.async_close() is None
    assert coordinator._empty_result("2026")["sessions"] == []
    coordinator._race_coordinator = None
    coordinator._season_results_coordinator = None
    coordinator._sprint_results_coordinator = None
    assert coordinator._effective_season().isdigit()
    coordinator._season_results_coordinator = season_results
    coordinator._sprint_results_coordinator = sprint_results

    assert coordinator._round_number({"round": "bad"}) is None
    assert coordinator._to_int(None) is None
    assert coordinator._to_int(" ") is None
    assert coordinator._to_int("bad") is None
    assert coordinator._constructor_color({}, 0)
    assert coordinator._constructor_color({}, -1) is None
    assert coordinator._page_ttl({"round": "1"}, 2) == coordinator._ttl_stable

    with pytest.raises(JolpicaPaginationError):
        await coordinator._fetch_lap_page("2026", "1", 101, 0, 1)
    assert await coordinator._fetch_laps_for_race("", race, 1) == (None, [], False)

    paginated = SimpleNamespace(
        pages=[
            SimpleNamespace(
                payload={
                    "MRData": {
                        "RaceTable": {
                            "Races": [
                                {
                                    **race,
                                    "Laps": [
                                        {"number": "bad", "Timings": []},
                                        {
                                            "number": "1",
                                            "Timings": [
                                                "bad",
                                                {"driverId": ""},
                                                {
                                                    "driverId": "norris",
                                                    "position": "1",
                                                },
                                            ],
                                        },
                                    ],
                                }
                            ]
                        }
                    }
                }
            )
        ],
        total=1,
    )
    monkeypatch.setattr(
        "custom_components.f1_sensor.async_paginate_jolpica",
        AsyncMock(return_value=paginated),
    )
    race_meta, laps, saw_payload = await coordinator._fetch_laps_for_race(
        "2026", race, 1
    )
    assert race_meta["raceName"] == "Test Grand Prix"
    assert laps == [
        {
            "number": "1",
            "Timings": [{"driverId": "norris", "position": "1"}],
        }
    ]
    assert saw_payload is True

    metadata = coordinator._result_metadata(race)
    assert set(metadata) == {"norris"}
    drivers, labels, series = coordinator._build_driver_rows(
        race,
        [
            {"number": "bad", "Timings": []},
            {
                "number": "1",
                "Timings": [
                    "bad",
                    {"driverId": "", "position": "1"},
                    {"driverId": "norris", "position": "1"},
                ],
            },
        ],
    )
    assert labels == ["Lbad", "L1"]
    assert drivers[0]["finish_position"] == 2
    assert series[0]["data"] == [1]
    race_without_finish = {
        **race,
        "Results": [
            {
                "grid": "3",
                "Driver": {"driverId": "norris", "code": "NOR"},
                "Constructor": {},
            }
        ],
    }
    fallback_drivers, _, _ = coordinator._build_driver_rows(
        race_without_finish,
        [{"number": "1", "Timings": [{"driverId": "norris", "position": "1"}]}],
    )
    assert fallback_drivers[0]["finish_position"] == 1
    assert coordinator._session_sort_key({"round": "bad", "key": "x"})[0] == 0
    assert coordinator._find_race_for_session("sprint:2026:1", "2026") is None

    coordinator._metadata_sessions = Mock(return_value=[])
    assert (await coordinator.async_get_session("missing"))["status"] == "not_found"
    sprint = {"key": "sprint:2026:1", "type": "sprint", "status": "unsupported"}
    coordinator._metadata_sessions = Mock(return_value=[sprint])
    assert (await coordinator.async_get_session(sprint["key"]))["status"] == (
        "unsupported"
    )
    missing_race = {"key": "race:2026:9", "type": "race", "status": "available"}
    coordinator._metadata_sessions = Mock(return_value=[missing_race])
    coordinator._find_race_for_session = Mock(return_value=None)
    assert (await coordinator.async_get_session(missing_race["key"]))["status"] == (
        "not_found"
    )

    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_jolpica_blocked",
        lambda _coordinator: True,
    )
    coordinator.data = {"cached": True}
    assert await coordinator._async_update_data() == {"cached": True}
    coordinator.data = None
    assert (await coordinator._async_update_data())["sessions"] == []


@pytest.mark.asyncio
async def test_next_race_history_silver_http_and_source_update_matrix(
    hass, monkeypatch
) -> None:
    race_source = SimpleNamespace(data={}, async_add_listener=Mock(return_value=Mock()))
    coordinator = F1NextRaceHistoryCoordinator(
        hass,
        race_source,
        "Silver next race history",
        session=Mock(),
    )
    assert coordinator._find_result([], "1") is None
    assert (
        coordinator._target_key_from_race(
            {"Circuit": {"circuitId": "test"}, "date": ""}
        )
        is None
    )

    validation = Mock()
    monkeypatch.setattr(
        "custom_components.f1_sensor.validate_single_page_jolpica", validation
    )

    async def _fetch_json(*_args, validator=None, **_kwargs):
        validator({})
        return {"ok": True}

    monkeypatch.setattr("custom_components.f1_sensor.fetch_json", _fetch_json)
    for url in (
        coordinator._history_url("2025", "1", "qualifying.json"),
        coordinator._history_url("2025", "1", "results.json"),
        coordinator._history_url("circuits", "test", "races.json"),
    ):
        assert await coordinator._fetch_url(url) == {"ok": True}
    assert validation.call_count == 3

    coordinator._target_race = Mock(return_value=None)
    coordinator.async_request_refresh = AsyncMock()
    coordinator._handle_race_source_update()
    coordinator.async_request_refresh.assert_not_awaited()
    target = {
        "season": "2026",
        "round": "1",
        "date": "2026-09-01",
        "Circuit": {"circuitId": "test"},
    }
    coordinator._target_race = Mock(return_value=target)
    coordinator._target_key = None
    coordinator._handle_race_source_update()
    await hass.async_block_till_done()
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_next_race_history_silver_update_edge_matrix(hass, monkeypatch) -> None:
    race_source = SimpleNamespace(data={})
    coordinator = F1NextRaceHistoryCoordinator(
        hass,
        race_source,
        "Silver next race history edges",
        session=Mock(),
    )
    target = {
        "season": "2026",
        "round": "9",
        "raceName": "Target GP",
        "date": "2026-09-01",
        "Circuit": {"circuitId": "test"},
    }
    coordinator._target_race = Mock(return_value=target)

    coordinator._target_key_from_race = Mock(return_value=("test", "2026-09-01", "9"))
    malformed_target = {**target, "Circuit": {}, "date": None}
    coordinator._target_race = Mock(return_value=malformed_target)
    assert (await coordinator._async_update_data())["races_held_here"] == 0

    coordinator._target_race = Mock(return_value=target)
    coordinator._target_key_from_race = (
        F1NextRaceHistoryCoordinator._target_key_from_race
    )
    coordinator._fetch_url = AsyncMock(
        side_effect=[
            {"MRData": {"RaceTable": {"Races": []}}},
            {"MRData": {"RaceTable": {"Races": []}}},
        ]
    )
    assert (await coordinator._async_update_data())["races_held_here"] == 0

    completed_2023 = {
        "season": "2023",
        "round": "1",
        "raceName": "Old GP",
        "date": "2023-08-01",
    }
    completed_2025 = {
        "season": "2025",
        "round": "1",
        "raceName": "Recent GP",
        "date": "2025-08-01",
    }

    def _result(season: str, *, position: str = "1") -> dict:
        return {
            "position": position,
            "grid": "1",
            "status": "Finished",
            "Driver": {
                "driverId": "norris",
                "code": "NOR",
                "givenName": "Lando",
                "familyName": "Norris",
            },
            "Constructor": {"constructorId": "mclaren", "name": "McLaren"},
            "season": season,
        }

    winner_2024 = {
        **completed_2023,
        "season": "2024",
        "date": "2024-08-01",
        "Results": [_result("2024")],
    }
    winner_2025 = {**completed_2025, "Results": [_result("2025")]}
    future_winner = {
        **target,
        "date": "2027-01-01",
        "Results": [_result("2027")],
    }
    no_winner = {
        **completed_2023,
        "season": "2022",
        "date": "2022-08-01",
        "Results": [],
    }

    async def _fetch_url(url: str):
        if "/circuits/test/races" in url:
            return {
                "MRData": {"RaceTable": {"Races": [completed_2023, completed_2025]}}
            }
        if "/circuits/test/results/1" in url:
            return {
                "MRData": {
                    "RaceTable": {
                        "Races": [
                            "bad",
                            future_winner,
                            no_winner,
                            winner_2024,
                            winner_2025,
                        ]
                    }
                }
            }
        if "/results.json" in url:
            race = completed_2025 if "/2025/" in url else completed_2023
            return {
                "MRData": {
                    "RaceTable": {
                        "Races": [{**race, "Results": [_result(race["season"])]}]
                    }
                }
            }
        if "/qualifying.json" in url:
            race = completed_2025 if "/2025/" in url else completed_2023
            return {
                "MRData": {
                    "RaceTable": {
                        "Races": [
                            {
                                **race,
                                "QualifyingResults": [
                                    {**_result(race["season"]), "position": "2"}
                                ],
                            }
                        ]
                    }
                }
            }
        raise AssertionError(url)

    coordinator._fetch_url = _fetch_url
    history = await coordinator._async_update_data()
    assert history["races_held_here"] == 2
    assert history["defending_pole_sitter"]["driver_id"] == "norris"
    assert history["top_5_driver_wins_here"][0]["last_win_season"] == "2025"
    assert history["top_5_constructor_wins_here"][0]["last_win_season"] == "2025"

    coordinator._target_race = Mock(side_effect=RuntimeError("target"))
    with pytest.raises(UpdateFailed, match="next race history"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_championship_prediction_silver_defensive_matrix(
    hass, monkeypatch
) -> None:
    delay_controller = SimpleNamespace(add_listener=Mock(return_value=Mock()))
    coordinator = ChampionshipPredictionCoordinator(
        hass,
        session_coord=SimpleNamespace(data={}),
        bus=SimpleNamespace(auth_enabled=True),
        delay_controller=delay_controller,
    )
    delay_controller.add_listener.assert_called_once()
    coordinator._handle_live_state(True, "no-spoiler")
    coordinator.set_delay(2)
    assert coordinator._deep_merge("bad", {"nested": {"x": 1}}) == {"nested": {"x": 1}}
    coordinator._ingest_prediction("bad")
    coordinator._ingest_prediction(
        {
            "Drivers": {"": {"RacingNumber": ""}},
            "Teams": {"": {"PredictedPosition": 1}},
        }
    )
    coordinator._on_driverlist("bad")
    coordinator._on_driverlist({"": {"RacingNumber": ""}})
    assert coordinator._to_int(" ") is None
    assert coordinator._to_float(" ") is None
    coordinator._drivers = {"bad": "bad", "missing": {"PredictedPosition": None}}
    assert coordinator._pick_predicted_driver_p1() == (None, None)
    coordinator._teams = {"bad": "bad", "missing": {"PredictedPosition": None}}
    assert coordinator._pick_predicted_team_p1() == (None, None)
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked",
        lambda _coordinator: True,
    )
    coordinator._deliver()
    coordinator._on_bus_message("bad")


@pytest.mark.asyncio
async def test_pit_stop_silver_fallback_matrix(hass, monkeypatch) -> None:
    delay_controller = SimpleNamespace(add_listener=Mock(return_value=Mock()))
    drivers = SimpleNamespace(data=None)
    coordinator = PitStopCoordinator(
        hass,
        session_coord=SimpleNamespace(data={}),
        bus=SimpleNamespace(auth_enabled=True),
        delay_controller=delay_controller,
        drivers_coordinator=drivers,
    )
    delay_controller.add_listener.assert_called_once()
    coordinator.set_delay(2)
    stop = {
        "lap": 1,
        "timestamp": "one",
        "pit_stop_time": 2.0,
        "pit_lane_time": 20.0,
    }
    coordinator._add_stop("4", stop)
    coordinator._add_stop("4", stop)
    assert len(coordinator._by_car["4"]) == 1

    monkeypatch.setattr("custom_components.f1_sensor.PITSTOP_MAX_CARS_PER_PAYLOAD", 1)
    coordinator._ingest_pitstopseries({"PitTimes": {"4": [], "81": []}})
    monkeypatch.setattr(
        "custom_components.f1_sensor.PITSTOP_MAX_ENTRIES_PER_PAYLOAD", 1
    )
    coordinator._ingest_pitstopseries(
        {
            "PitTimes": {
                "4": [
                    {"PitStop": {"RacingNumber": "4", "Lap": 2}},
                    {"PitStop": {"RacingNumber": "4", "Lap": 3}},
                ]
            }
        }
    )

    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked",
        lambda _coordinator: True,
    )
    coordinator._deliver()
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked",
        lambda _coordinator: False,
    )
    with monkeypatch.context() as context:
        context.setattr(
            coordinator,
            "_get_identity",
            Mock(side_effect=RuntimeError("identity")),
        )
        context.setattr("builtins.sum", Mock(side_effect=RuntimeError("sum")))
        coordinator._deliver()
    assert coordinator.data["total_stops"] == 0

    coordinator._drivers_coord = None
    assert coordinator._refresh_pit_counts_from_coordinator() is False
    assert coordinator._refresh_driver_map_from_coordinator() is False
    coordinator._drivers_coord = drivers
    for payload in ("bad", {"drivers": "bad"}):
        drivers.data = payload
        assert coordinator._refresh_pit_counts_from_coordinator() is False
        assert coordinator._refresh_driver_map_from_coordinator() is False
    drivers.data = {
        "drivers": {
            "4": {"timing": "bad"},
            "81": {"timing": {"pit_stops": None}},
        }
    }
    assert coordinator._refresh_pit_counts_from_coordinator() is False

    coordinator._driver_map = {}
    for payload in ("bad", {"drivers": "bad"}, {"drivers": {"4": "bad"}}):
        drivers.data = payload
        assert coordinator._get_identity("4") == {}

    coordinator._by_car = {"4": "bad", "81": ["bad"]}
    assert coordinator._refresh_pit_deltas() is False
    coordinator._by_car = {}
    drivers.data = "bad"
    assert coordinator._get_lap_history("4") is None
    drivers.data = {"drivers": "bad"}
    assert coordinator._get_lap_history("4") is None
    drivers.data = {"drivers": {"4": "bad"}}
    assert coordinator._get_lap_history("4") is None
    drivers.data = {"drivers": {"4": {"lap_history": {"laps": "bad"}}}}
    assert coordinator._get_lap_history("4") is None
    coordinator._get_lap_history = Mock(return_value={"1": "1:30", "2": "1:45"})
    assert coordinator._compute_pit_delta("4", {"lap": 1}) is None
    assert (
        coordinator._select_reference_lap_secs({"12": "1:31", "13": "1:32"}, 10) == 91.5
    )


@pytest.mark.asyncio
async def test_pit_stop_silver_first_refresh_and_driver_update_matrix(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        DataUpdateCoordinator,
        "async_config_entry_first_refresh",
        AsyncMock(),
    )
    session = SimpleNamespace(
        data={}, async_add_listener=Mock(side_effect=RuntimeError("session"))
    )
    drivers = SimpleNamespace(
        data={}, async_add_listener=Mock(side_effect=RuntimeError("drivers"))
    )
    coordinator = PitStopCoordinator(
        hass,
        session_coord=session,
        bus=SimpleNamespace(subscribe=Mock(side_effect=RuntimeError("subscribe"))),
        drivers_coordinator=drivers,
    )
    coordinator._seed_driver_map_from_ergast = Mock()
    coordinator._refresh_pit_counts_from_coordinator = Mock(return_value=False)
    coordinator._refresh_driver_map_from_coordinator = Mock(return_value=False)
    coordinator._refresh_pit_deltas = Mock(return_value=True)
    coordinator._schedule_deliver = Mock()
    await coordinator.async_config_entry_first_refresh()
    assert coordinator._session_unsub is None
    assert coordinator._drivers_unsub is None
    coordinator._schedule_deliver.assert_called_once()

    coordinator._schedule_deliver.reset_mock()
    coordinator._refresh_pit_counts_from_coordinator = Mock(return_value=False)
    coordinator._refresh_pit_deltas = Mock(return_value=True)
    coordinator._refresh_driver_map_from_coordinator = Mock(return_value=True)
    coordinator._on_drivers_update()
    coordinator._schedule_deliver.assert_called_once()


@pytest.mark.asyncio
async def test_live_drivers_silver_state_and_sector_matrix(hass, monkeypatch) -> None:
    delay_controller = SimpleNamespace(add_listener=Mock(return_value=Mock()))
    live_state = SimpleNamespace(add_listener=Mock(return_value=Mock()))
    coordinator = LiveDriversCoordinator(
        hass,
        session_coord=SimpleNamespace(data={}),
        bus=SimpleNamespace(auth_enabled=True),
        delay_controller=delay_controller,
        live_state=live_state,
    )
    delay_controller.add_listener.assert_called_once()
    live_state.add_listener.assert_called_once()

    assert coordinator._merge_driverlist(
        {"4": {"HeadshotUrl": _BadHeadshot("https://image.test")}}
    )
    assert coordinator._ingest_completed_lap("4", "") is False
    assert coordinator._normalize_personal_best_sector(None, "30.0")["time"] == ("30.0")
    assert (
        coordinator._driver_completed_laps(
            {"lap_history": {"completed_laps": "bad", "last_recorded_lap": "bad"}}
        )
        is None
    )
    coordinator.set_delay(2)

    monkeypatch.setattr("custom_components.f1_sensor.MAX_TYRE_STINT_INDEX", 0)
    assert coordinator._extract_stint_items([{}, {}]) == [(0, {})]
    assert coordinator._extract_compound_presence({"Lines": {"4": "bad"}}) == (
        0,
        [],
    )
    coordinator._replay_mode = False
    coordinator._tyre_live_started_mono = 1e30
    coordinator._log_tyre_stream_observability({"Lines": {}})

    assert coordinator._merge_timingapp({"Lines": "bad"}) is False
    assert coordinator._merge_timingapp({"Lines": {"4": "bad"}}) is False
    coordinator._state["drivers"] = {}
    assert coordinator._merge_timingapp(
        {
            "Lines": {
                "4": {
                    "Stints": [
                        {
                            "Compound": "SOFT",
                            "New": "unknown",
                            "LapTime": "1:30.000",
                            "LapNumber": _BadPosition(),
                        }
                    ]
                }
            }
        }
    )
    driver = coordinator._state["drivers"]["4"]
    assert driver["tyres"]["new"] == "unknown"
    assert coordinator._update_stint_history(
        driver["tyre_history"], 0, {"New": "maybe"}
    )

    coordinator._state["drivers"]["missing_tyre"] = {}
    assert coordinator._record_lap_time_for_stint("missing_tyre", "1:30") is False
    assert coordinator._record_lap_for_history("missing_tyre", "1:30") is False

    sector_entry = {"sectors": coordinator._empty_sector_state()}
    sectors = coordinator._ensure_sector_state(sector_entry)
    sectors["current"][2] = {
        "time": 30.0,
        "value": "30.0",
        "lap": None,
        "overall_fastest": False,
        "personal_fastest": True,
        "source": "current",
    }
    assert coordinator._mark_sector_lap_completed(sector_entry, 3) is True
    assert sectors["state"] == "lap_complete"
    assert sectors["current_lap"] == 3

    coordinator._state["fastest_lap"] = "bad"
    assert coordinator._update_fastest_lap("4", 3, "1:29.000") is True
    coordinator._state["drivers"] = {
        "a": {"lap_history": {"laps": "bad"}},
        "b": {"lap_history": {"laps": {"1": None}}},
        "c": {"identity": {}, "lap_history": {"laps": {"bad": "1:29"}}},
        "d": {"lap_history": {"laps": {"2": "1:30"}}},
    }
    assert coordinator._recompute_fastest_lap_from_history() is True
    assert coordinator._state["fastest_lap"]["racing_number"] == "c"

    coordinator._state["drivers"] = {"4": {}}
    coordinator._merge_lapcount(
        {"CurrentLap": _BadPosition(), "TotalLaps": _BadPosition()}
    )
    assert coordinator._state["lap_current"] is None
    assert coordinator._state["lap_total"] is None
    coordinator._capture_grid_positions_if_needed()

    coordinator._merge_driverlist = Mock(return_value=True)
    coordinator._recompute_tyre_statistics = Mock()
    coordinator._schedule_deliver = Mock()
    coordinator._on_driverlist({})
    coordinator._recompute_tyre_statistics.assert_called_once()
    coordinator._schedule_deliver.assert_called_once()
    coordinator._schedule_deliver.reset_mock()
    coordinator._merge_timingapp = Mock(return_value=True)
    coordinator._on_timingapp({})
    coordinator._schedule_deliver.assert_called_once()

    coordinator._state["drivers"] = {}
    coordinator._on_driver_race_info(
        {
            "4": {"Position": _BadPosition()},
            "81": {"Position": ""},
        }
    )


@pytest.mark.asyncio
async def test_live_drivers_silver_failed_bus_lookup(hass, monkeypatch) -> None:
    monkeypatch.setattr(
        DataUpdateCoordinator,
        "async_config_entry_first_refresh",
        AsyncMock(),
    )
    coordinator = LiveDriversCoordinator(
        hass,
        session_coord=SimpleNamespace(data={}),
        bus=None,
    )
    coordinator.hass = SimpleNamespace(data=_BadGetDict())
    await coordinator.async_config_entry_first_refresh()
    assert coordinator._unsubs == []
