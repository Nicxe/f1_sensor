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
