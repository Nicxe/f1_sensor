from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.f1_sensor.__init__ import LiveDriversCoordinator
from custom_components.f1_sensor.sensor import F1DriverPositionsSensor


class DummyCoordinator(SimpleNamespace):
    def async_add_listener(self, _listener):
        return lambda: None


def _make_coord(hass) -> LiveDriversCoordinator:
    return LiveDriversCoordinator(
        hass,
        SimpleNamespace(),
        delay_seconds=0,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
    )


@pytest.mark.asyncio
async def test_fastest_lap_updates_from_last_lap(hass) -> None:
    coord = _make_coord(hass)
    coord._merge_timingdata(
        {"Lines": {"1": {"NumberOfLaps": 5, "LastLapTime": {"Value": "1:30.000"}}}}
    )
    fastest = coord._state["fastest_lap"]
    assert fastest["racing_number"] == "1"
    assert fastest["lap"] == 5
    assert fastest["time"] == "1:30.000"
    assert fastest["time_secs"] == pytest.approx(90.0)

    coord._merge_timingdata(
        {"Lines": {"2": {"NumberOfLaps": 6, "LastLapTime": {"Value": "1:29.500"}}}}
    )
    fastest = coord._state["fastest_lap"]
    assert fastest["racing_number"] == "2"
    assert fastest["lap"] == 6
    assert fastest["time"] == "1:29.500"
    assert fastest["time_secs"] == pytest.approx(89.5)

    coord._merge_timingdata(
        {"Lines": {"3": {"NumberOfLaps": 7, "LastLapTime": {"Value": "1:29.500"}}}}
    )
    fastest = coord._state["fastest_lap"]
    assert fastest["racing_number"] == "2"


@pytest.mark.asyncio
async def test_fastest_lap_seeded_from_best_lap(hass) -> None:
    coord = _make_coord(hass)
    coord._merge_timingdata(
        {"Lines": {"1": {"BestLapTime": {"Value": "1:32.000", "Lap": 12}}}}
    )
    fastest = coord._state["fastest_lap"]
    assert fastest["racing_number"] == "1"
    assert fastest["lap"] == 12
    assert fastest["time"] == "1:32.000"


@pytest.mark.asyncio
async def test_fastest_lap_stays_in_sync_when_timingapp_arrives_first(hass) -> None:
    coord = _make_coord(hass)
    coord._merge_tyre_stints(
        {
            "Stints": {
                "16": {"0": {"Compound": "MEDIUM"}},
                "12": {"0": {"Compound": "MEDIUM"}},
            }
        }
    )
    coord._merge_timingapp(
        {"Lines": {"16": {"Stints": {"0": {"LapTime": "1:23.981", "LapNumber": 5}}}}}
    )
    coord._merge_timingapp(
        {"Lines": {"12": {"Stints": {"0": {"LapTime": "1:23.835", "LapNumber": 7}}}}}
    )

    fastest = coord._state["fastest_lap"]
    tyre = coord._state["tyre_statistics"]
    assert fastest["racing_number"] == "12"
    assert fastest["time"] == "1:23.835"
    assert fastest["time_secs"] == pytest.approx(83.835)
    assert tyre["fastest_compound"] == "MEDIUM"
    assert tyre["fastest_time_secs"] == pytest.approx(83.835)

    coord._merge_timingdata(
        {
            "Lines": {
                "12": {
                    "NumberOfLaps": 7,
                    "LastLapTime": {"Value": "1:23.835", "PersonalFastest": False},
                }
            }
        }
    )
    fastest = coord._state["fastest_lap"]
    tyre = coord._state["tyre_statistics"]
    assert fastest["racing_number"] == "12"
    assert fastest["time_secs"] == pytest.approx(tyre["fastest_time_secs"])


@pytest.mark.asyncio
async def test_fastest_lap_stays_in_sync_when_timingdata_arrives_first(hass) -> None:
    coord = _make_coord(hass)
    coord._merge_tyre_stints(
        {
            "Stints": {
                "16": {"0": {"Compound": "MEDIUM"}},
                "12": {"0": {"Compound": "MEDIUM"}},
            }
        }
    )
    coord._merge_timingdata(
        {"Lines": {"16": {"NumberOfLaps": 5, "LastLapTime": {"Value": "1:23.981"}}}}
    )
    coord._merge_timingdata(
        {"Lines": {"12": {"NumberOfLaps": 7, "LastLapTime": {"Value": "1:23.835"}}}}
    )

    fastest = coord._state["fastest_lap"]
    tyre = coord._state["tyre_statistics"]
    assert fastest["racing_number"] == "12"
    assert fastest["time_secs"] == pytest.approx(83.835)
    assert tyre["fastest_time_secs"] == pytest.approx(83.835)

    coord._merge_timingapp(
        {"Lines": {"12": {"Stints": {"0": {"LapTime": "1:23.835", "LapNumber": 7}}}}}
    )
    fastest = coord._state["fastest_lap"]
    tyre = coord._state["tyre_statistics"]
    assert fastest["racing_number"] == "12"
    assert fastest["time_secs"] == pytest.approx(tyre["fastest_time_secs"])
    assert len(tyre["compounds"]["MEDIUM"]["best_times"]) == 2


@pytest.mark.asyncio
async def test_australian_race_replay_keeps_fastest_lap_and_tyre_stats_in_sync(
    hass,
) -> None:
    coord = _make_coord(hass)
    entries: list[tuple[str, str, dict]] = [
        (
            "01:12:27.027",
            "timingdata",
            {"Lines": {"3": {"Sectors": {"2": {"Segments": {"5": {"Status": 2048}}}}}}},
        ),
        (
            "01:12:27.587",
            "stints",
            {
                "Stints": {
                    "16": {"0": {"Compound": "MEDIUM", "New": "true"}},
                    "12": {"0": {"Compound": "MEDIUM", "New": "true"}},
                }
            },
        ),
        (
            "01:12:27.587",
            "timingapp",
            {
                "Lines": {
                    "12": {"Stints": {"0": {"LapTime": "1:23.835", "LapNumber": 7}}}
                }
            },
        ),
        (
            "01:12:27.587",
            "timingdata",
            {
                "Lines": {
                    "16": {
                        "NumberOfLaps": 5,
                        "LastLapTime": {"Value": "1:23.981", "PersonalFastest": True},
                        "BestLapTime": {"Value": "1:23.981", "Lap": 5},
                    },
                    "12": {
                        "NumberOfLaps": 7,
                        "Sectors": {"2": {"Value": "36.246"}},
                        "LastLapTime": {"Value": "1:23.835", "PersonalFastest": False},
                    },
                }
            },
        ),
        (
            "01:12:27.624",
            "timingapp",
            {"Lines": {"12": {"Stints": {"0": {"LapFlags": 3}}}}},
        ),
        (
            "01:12:27.624",
            "timingdata",
            {
                "Lines": {
                    "12": {
                        "Sectors": {
                            "2": {"OverallFastest": True, "PersonalFastest": True}
                        },
                        "BestLapTime": {"Value": "1:23.835", "Lap": 7},
                        "LastLapTime": {
                            "OverallFastest": True,
                            "PersonalFastest": True,
                        },
                    }
                }
            },
        ),
    ]

    for timestamp, kind, payload in entries:
        if kind == "stints":
            coord._merge_tyre_stints(payload)
        elif kind == "timingapp":
            coord._merge_timingapp(payload)
        else:
            coord._merge_timingdata(payload)

        fastest = coord._state["fastest_lap"]
        tyre = coord._state["tyre_statistics"]
        fastest_secs = fastest.get("time_secs")
        tyre_secs = tyre.get("fastest_time_secs")
        if fastest_secs is not None and tyre_secs is not None:
            assert fastest_secs == pytest.approx(tyre_secs), (
                f"mismatch at {timestamp}: {fastest} vs {tyre}"
            )


def _driver_positions_payload() -> dict:
    return {
        "drivers": {
            "1": {
                "identity": {
                    "tla": "AAA",
                    "name": "Driver A",
                    "team": "Team A",
                    "team_color": "FF0000",
                },
                "lap_history": {
                    "laps": {"1": "1:30.000"},
                    "grid_position": "1",
                    "completed_laps": 1,
                },
                "timing": {"position": "1"},
            },
            "2": {
                "identity": {
                    "tla": "BBB",
                    "name": "Driver B",
                    "team": "Team B",
                    "team_color": "00FF00",
                },
                "lap_history": {
                    "laps": {"1": "1:30.500"},
                    "grid_position": "2",
                    "completed_laps": 1,
                },
                "timing": {"position": "2"},
            },
        },
        "lap_current": 1,
        "lap_total": 50,
        "fastest_lap": {
            "racing_number": "1",
            "lap": 1,
            "time": "1:30.000",
            "time_secs": 90.0,
            "tla": "AAA",
            "name": "Driver A",
            "team": "Team A",
            "team_color": "#FF0000",
        },
    }


def test_driver_positions_fastest_lap_race(hass) -> None:
    coord = DummyCoordinator(data=_driver_positions_payload())
    sensor = F1DriverPositionsSensor(coord, "uid", "entry", "F1")
    sensor.hass = hass
    sensor._session_info_coordinator = SimpleNamespace(
        data={"Type": "Race", "Name": "Race"}
    )
    assert sensor._update_from_coordinator(initial=True) is True
    attrs = sensor._attr_extra_state_attributes
    assert attrs["fastest_lap"]["racing_number"] == "1"
    fastest_driver = next(
        drv for drv in attrs["drivers"] if drv["racing_number"] == "1"
    )
    assert fastest_driver["fastest_lap"] is True
    assert fastest_driver["fastest_lap_time"] == "1:30.000"
    assert fastest_driver["fastest_lap_lap"] == 1


def test_driver_positions_fastest_lap_hidden_non_race(hass) -> None:
    coord = DummyCoordinator(data=_driver_positions_payload())
    sensor = F1DriverPositionsSensor(coord, "uid", "entry", "F1")
    sensor.hass = hass
    sensor._session_info_coordinator = SimpleNamespace(
        data={"Type": "Practice", "Name": "Practice 1"}
    )
    assert sensor._update_from_coordinator(initial=True) is True
    attrs = sensor._attr_extra_state_attributes
    assert attrs["fastest_lap"] is None
    for drv in attrs["drivers"]:
        assert drv["fastest_lap"] is False
        assert drv["fastest_lap_time"] is None
        assert drv["fastest_lap_lap"] is None
