"""Behavior matrix for consolidated live driver state."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from homeassistant import config_entries
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import LiveDriversCoordinator
from custom_components.f1_sensor.const import DOMAIN


class _Bus:
    def __init__(self) -> None:
        self.callbacks = {}
        self.removers = []

    def subscribe(self, stream, callback):
        self.callbacks[stream] = callback
        remover = Mock()
        self.removers.append(remover)
        return remover


async def test_driver_identity_merge_fastest_link_and_subscription_cleanup(
    hass,
) -> None:
    bus = _Bus()
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    object.__setattr__(
        entry, "state", config_entries.ConfigEntryState.SETUP_IN_PROGRESS
    )
    coordinator = LiveDriversCoordinator(
        hass, SimpleNamespace(data={}), bus=bus, config_entry=entry
    )
    coordinator._state["fastest_lap"] = {
        **coordinator._empty_fastest_lap(),
        "racing_number": "4",
    }
    payload = {
        "bad": "ignored",
        "4": {
            "RacingNumber": "4",
            "Tla": "NOR",
            "FullName": "Lando Norris",
            "BroadcastName": "L NORRIS",
            "TeamName": "McLaren",
            "TeamColour": "ff8700",
            "FirstName": "Lando",
            "LastName": "Norris",
            "HeadshotUrl": "https://example.test/norris.transform/2col/image.png",
            "Reference": "norris",
            "Line": "1",
        },
        "81": {
            "BroadcastName": "O PIASTRI",
            "HeadshotUrl": 123,
            "Line": "bad",
        },
    }
    assert coordinator._merge_driverlist(payload) is True
    identity = coordinator._state["drivers"]["4"]["identity"]
    assert identity["headshot_large"] == "https://example.test/norris"
    assert coordinator._state["fastest_lap"]["tla"] == "NOR"
    assert coordinator._state["drivers"]["4"]["lap_history"]["grid_position"] == "1"
    assert coordinator._merge_driverlist(payload) is False

    await coordinator.async_config_entry_first_refresh()
    assert set(bus.callbacks) == {
        "DriverList",
        "TimingData",
        "TimingAppData",
        "LapCount",
        "SessionStatus",
        "LapHistory",
        "DriverRaceInfo",
        "TrackStatus",
    }
    await coordinator.async_close()
    assert all(remover.called for remover in bus.removers)


async def test_live_driver_parsers_history_fastest_and_live_reset(
    hass, monkeypatch
) -> None:
    coordinator = LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    assert coordinator._parse_stream_int(None) is None
    assert coordinator._parse_stream_int(2) == 2
    assert coordinator._parse_stream_int(" ") is None
    assert coordinator._parse_stream_int("3") == 3
    assert coordinator._parse_stream_int("4.9") == 4
    assert coordinator._parse_stream_int("bad") is None
    assert list(coordinator._iter_qualifying_best_lap_times(None)) == []
    assert list(
        coordinator._iter_qualifying_best_lap_times(
            {"bad": {"Value": "1:00"}, "0": {}, "1": {"Value": "1:01"}}
        )
    ) == [(2, {"Value": "1:01"})]

    coordinator._on_driver_race_info(
        {
            "4": {"Position": "2", "PitStops": "1"},
            "81": {"Position": None, "PitStops": "bad"},
            "bad": "ignored",
        }
    )
    assert coordinator._state["drivers"]["4"]["timing"]["pit_stops"] == 1
    assert coordinator._state["drivers"]["4"]["lap_history"]["grid_position"] == "2"
    coordinator._on_lap_history(
        {
            "4": {
                "laps": {"1": "1:30.000", "bad": "bad"},
                "grid_position": "2",
                "last_recorded_lap": 1,
                "completed_laps": 1,
            },
            "81": {"laps": {"1": "1:29.000"}, "last_recorded_lap": 1},
            "bad": "ignored",
        }
    )
    coordinator._state["drivers"]["4"]["identity"].update(
        {"tla": "NOR", "name": "Lando", "team": "McLaren", "team_color": "ff8700"}
    )
    assert coordinator._recompute_fastest_lap_from_history() is True
    assert coordinator._state["fastest_lap"]["racing_number"] == "81"
    assert coordinator._recompute_fastest_lap_from_history() is False

    coordinator._merge_lapcount({"CurrentLap": "bad", "TotalLaps": "70"})
    assert coordinator._state["lap_current"] is None
    assert coordinator._state["lap_total"] == 70
    assert coordinator._extract(None, "LapCount") is None
    assert coordinator._extract(
        {"M": [{"A": ["LapCount", {"CurrentLap": 3}]}]}, "LapCount"
    ) == {"CurrentLap": 3}
    assert coordinator._extract({"R": {"LapCount": {"CurrentLap": 4}}}, "LapCount") == {
        "CurrentLap": 4
    }

    coordinator._state["leader_rn"] = "4"
    coordinator._handle_live_state(True, "init")
    coordinator._handle_live_state(True, "no-spoiler")
    coordinator._handle_live_state(False, "window-ended")
    assert coordinator._state["drivers"] == {}
    assert coordinator.available is False
    coordinator._handle_live_state(True, "replay")
    assert coordinator._replay_mode is True
    assert await coordinator._async_update_data() is coordinator._state


async def test_live_driver_stints_sectors_and_session_transitions(
    hass, monkeypatch
) -> None:
    coordinator = LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    assert coordinator._extract_stint_items(None) == []
    assert coordinator._extract_stint_items(
        {"000": {"Compound": "SOFT"}, "999999": {}, "bad": {}, "1": "bad"}
    ) == [(0, {"Compound": "SOFT"})]
    assert coordinator._extract_compound_presence({"Lines": "bad"}) == (0, [])
    assert coordinator._extract_compound_presence(
        {"Lines": {"4": {"Stints": [{"Compound": "inters"}]}}}
    ) == (1, ["4:INTERMEDIATE"])
    assert coordinator._normalize_compound("full wet") == "WET"
    assert coordinator._normalize_compound(3) == "3"
    assert coordinator._normalize_compound("  ") is None
    assert coordinator._normalize_team_color(None) is None
    assert coordinator._normalize_team_color("#abc") == "#abc"
    assert coordinator._format_laptime(None) is None
    assert coordinator._format_laptime(89.123) == "1:29.123"

    coordinator._state["drivers"] = {
        "4": {
            "identity": {"tla": "NOR", "last_name": "Norris"},
            "timing": {"position": "2"},
            "tyres": {},
            "laps": {},
            "lap_history": {
                "laps": {},
                "last_recorded_lap": 0,
                "grid_position": None,
                "completed_laps": 0,
            },
            "tyre_history": {"stints": [], "current_stint_index": None},
        }
    }
    assert (
        coordinator._merge_timingapp(
            {
                "Lines": {
                    "4": {
                        "Stints": [
                            {
                                "Compound": "SOFT",
                                "TotalLaps": "3",
                                "StartLaps": "0",
                                "New": "true",
                                "LapTime": "1:30.000",
                                "LapNumber": "bad",
                            },
                            {
                                "Compound": "MEDIUM",
                                "TotalLaps": "bad",
                                "StartLaps": "3",
                                "New": "false",
                            },
                        ]
                    }
                }
            }
        )
        is True
    )
    stats = coordinator._state["tyre_statistics"]
    assert stats["start_compounds"] == ["SOFT"]
    assert coordinator._record_lap_time_for_stint("missing", "1:20") is False
    assert coordinator._update_stint_history({}, -1, {}) is False
    coordinator._capture_grid_positions_if_needed()
    assert coordinator._state["drivers"]["4"]["lap_history"]["grid_position"] == "2"
    coordinator._merge_sessionstatus({"Status": "Started", "Started": True})
    assert coordinator._state["frozen"] is False
    coordinator._merge_sessionstatus({"Status": "Finalised"})
    assert coordinator._state["frozen"] is True
    coordinator._clear_lap_history()
    assert coordinator._state["drivers"]["4"]["lap_history"]["laps"] == {}


async def test_timing_data_merges_all_incremental_driver_fields(hass) -> None:
    coordinator = LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    payload = {
        "SessionPart": 1,
        "Lines": {
            "bad": "ignored",
            "4": {
                "NumberOfLaps": "2",
                "Position": "1",
                "GapToLeader": "+0.000",
                "IntervalToPositionAhead": {"Value": "+0.000"},
                "LastLapTime": {"Value": "1:20.000"},
                "BestLapTime": {"Value": "1:19.500", "Lap": "2"},
                "InPit": True,
                "PitOut": True,
                "NumberOfPitStops": "2",
                "Retired": True,
                "Stopped": True,
                "Status": 99,
                "KnockedOut": True,
                "BestLapTimes": {"0": {"Value": "1:20.100"}},
            },
            "81": {
                "NumberOfLaps": "bad",
                "Position": None,
                "NumberOfPitStops": "bad",
                "BestLapTime": {"Value": "1:18.000", "Lap": "bad"},
            },
        },
    }
    assert coordinator._merge_timingdata(payload) is True
    timing = coordinator._state["drivers"]["4"]["timing"]
    history = coordinator._state["drivers"]["4"]["lap_history"]
    assert history["completed_laps"] == 2
    assert timing == {
        "position": "1",
        "gap_to_leader": "+0.000",
        "interval": "+0.000",
        "last_lap": "1:20.000",
        "best_lap": "1:19.500",
        "official_best_lap": {"time": "1:19.500", "time_secs": 79.5, "lap": 2},
        "in_pit": True,
        "pit_out": True,
        "pit_stops": 2,
        "retired": True,
        "stopped": True,
        "status_code": 99,
    }
    assert coordinator._state["drivers"]["4"]["qualifying"]["knocked_out"] is True
    assert coordinator._state["drivers"]["4"]["qualifying"]["segments"][1] == {
        "best_time": "1:20.100",
        "participated": True,
    }

    sectors = coordinator._state["drivers"]["4"]["sectors"]
    sectors["current"][0]["time"] = "20.0"
    sectors["best"][0] = "19.0"
    assert coordinator._merge_timingdata({"SessionPart": 2, "Lines": {}}) is True
    assert sectors["current"][0]["time"] is None
    assert sectors["best"][0] is None
    assert coordinator._merge_timingdata({"Lines": []}) is False
    assert coordinator._normalize_current_sector({"time": "20.0"})["source"] == (
        "current"
    )
    assert coordinator._normalize_current_sector("bad")["time"] is None
    assert (
        coordinator._normalize_personal_best_sector({"time": "19.0"})["source"]
        == "personal_best"
    )


async def test_live_driver_sector_state_repair_progress_and_lap_completion(
    hass,
) -> None:
    coordinator = LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    assert coordinator._derive_sector_progress_state({"current": "bad"}) == (
        "awaiting_s1"
    )
    entry = {
        "sectors": {
            "current": "bad",
            "best": "bad",
            "personal_best": "bad",
        },
        "lap_history": {"completed_laps": "bad", "last_recorded_lap": 2},
    }
    sectors = coordinator._ensure_sector_state(entry)
    assert sectors["state"] == "awaiting_s1"
    assert sectors["best"] == {0: None, 1: None, 2: None}
    assert coordinator._driver_completed_laps(entry) == 2
    assert coordinator._driver_completed_laps({}) is None
    assert coordinator._clear_current_sector({}, 0) is False
    assert coordinator._clear_current_sector(sectors, 9) is False

    sectors["personal_best"] = {
        0: {"time": "20.0"},
        1: None,
        2: None,
    }
    sectors["best"] = {0: None, 1: None, 2: None}
    coordinator._ensure_sector_state(entry)
    assert sectors["best"][0] == 20.0

    assert coordinator._merge_sectors("4", entry, "bad") is False
    coordinator._state["track_status"] = "4"
    assert coordinator._merge_sectors("4", entry, [{"Value": "20.0"}]) is False
    coordinator._state["track_status"] = "1"
    assert (
        coordinator._merge_sectors(
            "4",
            entry,
            [
                {"Value": "20.0", "PersonalFastest": True},
                {"Value": "30.0", "OverallFastest": True},
                {"Value": "40.0"},
            ],
        )
        is True
    )
    assert sectors["state"] == "lap_complete"
    assert sectors["personal_best"][0]["source"] == "personal_best"
    assert coordinator._mark_sector_lap_completed(entry, 3) is True
    assert sectors["current"][2]["lap"] == 3

    coordinator._reset_sector_state(sectors, reset_best=False)
    sectors["current"][0] = {
        **coordinator._empty_current_sector(),
        "time": 20.0,
    }
    sectors["current_lap"] = 4
    sectors["state"] = "s1_done"
    assert coordinator._mark_sector_lap_completed(entry, 4) is True
    assert sectors["current_lap"] is None
    assert sectors["state"] == "awaiting_s1"

    assert (
        coordinator._merge_sectors(
            "4",
            entry,
            {
                "bad": {"Value": "1"},
                "0": {"Value": "", "Status": 2048},
                "1": {"Value": "bad"},
                "2": {"Value": "40.5", "Stopped": False},
            },
        )
        is True
    )
    assert sectors["state"] == "lap_complete"


async def test_live_driver_tyre_observability_leader_and_handler_guards(
    hass, monkeypatch
) -> None:
    coordinator = LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    coordinator._replay_mode = False
    coordinator._tyre_live_started_mono = 0.0
    monkeypatch.setattr(
        "custom_components.f1_sensor.time.monotonic",
        lambda: coordinator._TYRE_DATA_WARNING_THRESHOLD_S + 1,
    )
    coordinator._log_tyre_stream_observability({"Lines": {"4": {"Stints": {}}}})
    assert coordinator._tyre_missing_warning_logged is True
    coordinator._log_tyre_stream_observability(
        {"Lines": {"4": {"Stints": {"0": {"Compound": "SOFT"}}}}}
    )
    assert coordinator._tyre_first_compound_logged is True
    coordinator._log_tyre_stream_observability({"Lines": {}})

    coordinator._state["drivers"] = {
        "4": {"timing": {"position": "bad"}},
        "81": {"timing": {"position": "2"}},
        "1": {"timing": {"position": "1"}},
    }
    coordinator._recompute_leader_from_state()
    assert coordinator._state["leader_rn"] == "1"
    coordinator._state["drivers"]["1"]["timing"]["position"] = None
    coordinator._state["leader_rn"] = "4"
    coordinator._state["drivers"]["81"]["timing"]["position"] = None
    coordinator._recompute_leader_from_state()
    assert coordinator._state["leader_rn"] == "4"

    coordinator._state["frozen"] = True
    coordinator._replay_mode = False
    coordinator._on_timingapp({"Lines": {}})
    coordinator._on_lapcount({"CurrentLap": 2})
    coordinator._state["frozen"] = False
    coordinator._on_timingapp({"Lines": {}})
    coordinator._on_lapcount({})
    coordinator._on_driverlist({})


async def test_live_driver_lap_history_fastest_and_cleanup_matrix(
    hass, monkeypatch
) -> None:
    coordinator = LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    coordinator._merge_driverlist(
        {
            "4": {
                "Tla": "NOR",
                "FullName": "Lando Norris",
                "TeamName": "McLaren",
                "TeamColour": "ff8700",
            }
        }
    )
    entry = coordinator._state["drivers"]["4"]
    entry["timing"]["position"] = "1"
    entry["lap_history"] = {
        "laps": {},
        "last_recorded_lap": 0,
        "grid_position": None,
        "completed_laps": 0,
    }
    entry["sectors"] = coordinator._empty_sector_state()
    assert coordinator._record_lap_for_history("missing", "1:20") is False
    assert coordinator._record_lap_for_history("4", "1:20", "bad") is True
    assert entry["lap_history"]["grid_position"] == "1"
    assert coordinator._record_lap_for_history("4", "1:20", 1) is False
    assert coordinator._record_lap_for_history("4", "1:19", 2) is True
    assert coordinator._update_fastest_lap("4", 3, "bad") is False
    assert coordinator._update_fastest_lap("4", 3, "1:30") is False

    entry["tyre_history"] = {
        "stints": [{"best_lap_time_secs": 90.0}],
        "current_stint_index": 0,
    }
    assert coordinator._record_lap_time_for_stint("4", "bad") is False
    assert coordinator._record_lap_time_for_stint("4", "1:18") is True
    assert coordinator._record_lap_time_for_stint("4", "1:19") is False

    coordinator._state["fastest_lap"] = {"racing_number": "4"}
    entry["lap_history"]["laps"] = {"bad": "bad"}
    assert coordinator._recompute_fastest_lap_from_history() is True
    assert coordinator._state["fastest_lap"]["racing_number"] is None
    assert coordinator._recompute_fastest_lap_from_history() is False

    coordinator._on_driver_race_info("bad")
    coordinator._on_driver_race_info(
        {"4": {"Position": "2", "PitStops": "bad"}, "bad": "ignored"}
    )
    assert entry["lap_history"]["grid_position"] == "1"
    coordinator._on_lap_history("bad")
    coordinator._on_lap_history(
        {
            "81": {
                "laps": {"1": "1:21"},
                "grid_position": "2",
                "last_recorded_lap": 1,
                "completed_laps": "bad",
            },
            "bad": "ignored",
        }
    )
    assert coordinator._state["drivers"]["81"]["lap_history"]["completed_laps"] == 1
    assert coordinator._session_status_is_terminal({"Status": "Finished"}) is True
    assert coordinator._session_status_is_terminal("bad") is False
    assert coordinator._extract({"M": [{"A": []}]}, "LapCount") is None

    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: False
    )
    coordinator._deliver()
    assert coordinator.data is coordinator._state
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: True
    )
    coordinator._deliver()

    coordinator._unsubs = [Mock(), Mock()]
    coordinator._delay_listener = Mock()
    coordinator._live_state_unsub = Mock()
    coordinator._deliver_handle = Mock()
    coordinator._deliver_handles = [Mock()]
    coordinator._delay_scheduler_task = Mock()
    coordinator._delay_scheduler_task.done.return_value = False
    await coordinator.async_close()
    assert coordinator._unsubs == []
