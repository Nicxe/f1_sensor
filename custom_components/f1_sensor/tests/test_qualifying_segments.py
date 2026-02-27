"""Tests for qualifying segment data (Q1/Q2/Q3) in LiveDriversCoordinator and
F1DriverPositionsSensor."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.f1_sensor.__init__ import LiveDriversCoordinator
from custom_components.f1_sensor.sensor import (
    F1DriverPositionsSensor,
    _parse_lap_time_to_secs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_sensor(
    hass,
    coord,
    *,
    session_type: str = "Qualifying",
    session_name: str = "Qualifying",
) -> F1DriverPositionsSensor:
    sensor = F1DriverPositionsSensor(coord, "uid", "entry", "F1")
    sensor.hass = hass
    sensor._session_info_coordinator = SimpleNamespace(
        data={"Type": session_type, "Name": session_name}
    )
    return sensor


def _driver_entry(
    rn: str,
    *,
    position: str = "1",
    q1: str | None = None,
    q2: str | None = None,
    q3: str | None = None,
    q1_participated: bool = False,
    q2_participated: bool = False,
    q3_participated: bool = False,
    knocked_out: bool = False,
) -> dict:
    """Build a coordinator driver entry with qualifying data."""
    return {
        "identity": {
            "tla": f"D{rn}",
            "name": f"Driver {rn}",
            "team": "Team A",
            "team_color": "FF0000",
        },
        "lap_history": {
            "laps": {},
            "grid_position": position,
            "completed_laps": 0,
        },
        "timing": {"position": position},
        "qualifying": {
            "segments": {
                1: {"best_time": q1, "participated": q1_participated},
                2: {"best_time": q2, "participated": q2_participated},
                3: {"best_time": q3, "participated": q3_participated},
            },
            "knocked_out": knocked_out,
        },
    }


# ---------------------------------------------------------------------------
# Coordinator tests: _merge_timingdata qualifying fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coordinator_merges_best_lap_times_q1(hass) -> None:
    """BestLapTimes["0"] (Q1) is stored in qualifying.segments[1].best_time."""
    coord = _make_coord(hass)
    coord._merge_timingdata(
        {
            "SessionPart": 1,
            "Lines": {
                "81": {
                    "BestLapTimes": {
                        "0": {"Value": "1:22.605", "Lap": 5},
                    },
                }
            },
        }
    )
    q = coord._state["drivers"]["81"]["qualifying"]
    assert q["segments"][1]["best_time"] == "1:22.605"
    assert q["segments"][2]["best_time"] is None
    assert q["segments"][3]["best_time"] is None


@pytest.mark.asyncio
async def test_coordinator_merges_best_lap_times_all_segments(hass) -> None:
    """BestLapTimes with all three qualifying segments populated."""
    coord = _make_coord(hass)
    coord._merge_timingdata(
        {
            "SessionPart": 3,
            "Lines": {
                "1": {
                    "BestLapTimes": {
                        "0": {"Value": "1:23.100", "Lap": 4},
                        "1": {"Value": "1:22.500", "Lap": 3},
                        "2": {"Value": "1:21.987", "Lap": 6},
                    },
                }
            },
        }
    )
    q = coord._state["drivers"]["1"]["qualifying"]
    assert q["segments"][1]["best_time"] == "1:23.100"
    assert q["segments"][2]["best_time"] == "1:22.500"
    assert q["segments"][3]["best_time"] == "1:21.987"


@pytest.mark.asyncio
async def test_coordinator_ignores_empty_best_lap_time_value(hass) -> None:
    """An empty Value string does not overwrite an existing stored time."""
    coord = _make_coord(hass)
    coord._merge_timingdata(
        {
            "SessionPart": 1,
            "Lines": {
                "16": {"BestLapTimes": {"0": {"Value": "1:22.300", "Lap": 3}}},
            },
        }
    )
    # Empty value arrives – stored time must be preserved
    coord._merge_timingdata(
        {
            "SessionPart": 2,
            "Lines": {
                "16": {"BestLapTimes": {"0": {"Value": "", "Lap": 0}}},
            },
        }
    )
    q = coord._state["drivers"]["16"]["qualifying"]
    assert q["segments"][1]["best_time"] == "1:22.300"


@pytest.mark.asyncio
async def test_coordinator_merges_knocked_out_true(hass) -> None:
    """KnockedOut: true is stored in qualifying.knocked_out."""
    coord = _make_coord(hass)
    coord._merge_timingdata(
        {
            "SessionPart": 2,
            "Lines": {"10": {"KnockedOut": True}},
        }
    )
    assert coord._state["drivers"]["10"]["qualifying"]["knocked_out"] is True


@pytest.mark.asyncio
async def test_coordinator_merges_knocked_out_false(hass) -> None:
    """KnockedOut: false is stored correctly."""
    coord = _make_coord(hass)
    coord._merge_timingdata(
        {
            "SessionPart": 1,
            "Lines": {"63": {"KnockedOut": False}},
        }
    )
    assert coord._state["drivers"]["63"]["qualifying"]["knocked_out"] is False


@pytest.mark.asyncio
async def test_coordinator_marks_participation_q1(hass) -> None:
    """Driver appearing during SessionPart=1 gets segments[1].participated=True."""
    coord = _make_coord(hass)
    coord._merge_timingdata(
        {
            "SessionPart": 1,
            "Lines": {"44": {"NumberOfLaps": 3}},
        }
    )
    q = coord._state["drivers"]["44"]["qualifying"]
    assert q["segments"][1]["participated"] is True
    assert q["segments"][2]["participated"] is False
    assert q["segments"][3]["participated"] is False


@pytest.mark.asyncio
async def test_coordinator_marks_participation_q2(hass) -> None:
    """Driver appearing in Q1 then Q2 gets participation in both segments."""
    coord = _make_coord(hass)
    coord._merge_timingdata({"SessionPart": 1, "Lines": {"44": {"NumberOfLaps": 3}}})
    coord._merge_timingdata({"SessionPart": 2, "Lines": {"44": {"NumberOfLaps": 5}}})
    q = coord._state["drivers"]["44"]["qualifying"]
    assert q["segments"][1]["participated"] is True
    assert q["segments"][2]["participated"] is True
    assert q["segments"][3]["participated"] is False


@pytest.mark.asyncio
async def test_coordinator_participation_falls_back_to_stored_part(hass) -> None:
    """When SessionPart is absent, the previously stored part is used."""
    coord = _make_coord(hass)
    # Set stored part to 2
    coord._merge_timingdata({"SessionPart": 2, "Lines": {}})
    # Payload without SessionPart – should still mark participation in part 2
    coord._merge_timingdata({"Lines": {"55": {"NumberOfLaps": 2}}})
    q = coord._state["drivers"]["55"]["qualifying"]
    assert q["segments"][2]["participated"] is True


# ---------------------------------------------------------------------------
# Sensor tests: qualifying attributes
# ---------------------------------------------------------------------------


def test_sensor_q_fields_present_during_qualifying(hass) -> None:
    """q1/q2/q3 time, knocked_out and position fields appear during qualifying."""
    data = {
        "drivers": {
            "1": _driver_entry(
                "1",
                position="1",
                q1="1:23.100",
                q2="1:22.500",
                q3="1:21.987",
                q1_participated=True,
                q2_participated=True,
                q3_participated=True,
            ),
        },
        "lap_current": None,
        "lap_total": None,
        "session": {"part": 3},
    }
    sensor = _make_sensor(hass, DummyCoordinator(data=data))
    assert sensor._update_from_coordinator(initial=True) is True

    drv = sensor._attr_extra_state_attributes["drivers"][0]
    assert drv["q1_time"] == "1:23.100"
    assert drv["q2_time"] == "1:22.500"
    assert drv["q3_time"] == "1:21.987"
    assert drv["q1_knocked_out"] is False
    assert drv["q2_knocked_out"] is False
    assert drv["q3_knocked_out"] is False


def test_sensor_q_fields_none_during_race(hass) -> None:
    """All q-fields are None when session type is Race."""
    data = {
        "drivers": {
            "1": _driver_entry("1", position="1", q1="1:23.100", q1_participated=True),
        },
        "lap_current": 45,
        "lap_total": 70,
    }
    sensor = _make_sensor(
        hass,
        DummyCoordinator(data=data),
        session_type="Race",
        session_name="Formula 1 Race",
    )
    assert sensor._update_from_coordinator(initial=True) is True

    attrs = sensor._attr_extra_state_attributes
    drv = attrs["drivers"][0]
    assert drv["q1_time"] is None
    assert drv["q2_time"] is None
    assert drv["q3_time"] is None
    assert drv["q1_knocked_out"] is None
    assert drv["q2_knocked_out"] is None
    assert drv["q3_knocked_out"] is None
    assert attrs["current_qualifying_part"] is None


def test_sensor_q_fields_none_during_practice(hass) -> None:
    """All q-fields are None when session type is Practice."""
    data = {
        "drivers": {
            "1": _driver_entry("1", position="1", q1="1:23.100", q1_participated=True),
        },
        "lap_current": None,
        "lap_total": None,
    }
    sensor = _make_sensor(
        hass,
        DummyCoordinator(data=data),
        session_type="Practice",
        session_name="Practice 1",
    )
    assert sensor._update_from_coordinator(initial=True) is True

    drv = sensor._attr_extra_state_attributes["drivers"][0]
    assert drv["q1_time"] is None
    assert drv["q2_time"] is None
    assert drv["q3_time"] is None


def test_sensor_qualifying_positions_computed_correctly(hass) -> None:
    """Drivers are ranked by lap time within each segment (fastest = position 1)."""
    data = {
        "drivers": {
            "1": _driver_entry("1", position="3", q1="1:23.300", q1_participated=True),
            "2": _driver_entry("2", position="1", q1="1:22.900", q1_participated=True),
            "3": _driver_entry("3", position="2", q1="1:23.100", q1_participated=True),
        },
        "lap_current": None,
        "lap_total": None,
        "session": {"part": 1},
    }
    sensor = _make_sensor(hass, DummyCoordinator(data=data))
    assert sensor._update_from_coordinator(initial=True) is True

    by_rn = {
        d["racing_number"]: d for d in sensor._attr_extra_state_attributes["drivers"]
    }
    # Fastest Q1: rn=2 (1:22.900), rn=3 (1:23.100), rn=1 (1:23.300)
    assert by_rn["2"]["q1_position"] == 1
    assert by_rn["3"]["q1_position"] == 2
    assert by_rn["1"]["q1_position"] == 3


def test_sensor_driver_without_segment_time_gets_no_position(hass) -> None:
    """A driver with no time in a segment gets q_position=None."""
    data = {
        "drivers": {
            "1": _driver_entry("1", position="1", q1="1:23.100", q1_participated=True),
            "2": _driver_entry(
                "2", position="2", q1=None, q1_participated=True, knocked_out=True
            ),
        },
        "lap_current": None,
        "lap_total": None,
        "session": {"part": 1},
    }
    sensor = _make_sensor(hass, DummyCoordinator(data=data))
    assert sensor._update_from_coordinator(initial=True) is True

    by_rn = {
        d["racing_number"]: d for d in sensor._attr_extra_state_attributes["drivers"]
    }
    assert by_rn["1"]["q1_position"] == 1
    assert by_rn["2"]["q1_position"] is None


def test_sensor_q1_knocked_out_for_driver_never_in_q2(hass) -> None:
    """q1_knocked_out=True when knocked_out=True and driver never participated in Q2."""
    data = {
        "drivers": {
            "10": _driver_entry(
                "10",
                q1="1:24.500",
                q1_participated=True,
                q2_participated=False,
                knocked_out=True,
            ),
        },
        "lap_current": None,
        "lap_total": None,
        "session": {"part": 2},
    }
    sensor = _make_sensor(hass, DummyCoordinator(data=data))
    sensor._update_from_coordinator(initial=True)

    drv = sensor._attr_extra_state_attributes["drivers"][0]
    assert drv["q1_knocked_out"] is True
    assert drv["q2_knocked_out"] is False
    assert drv["q3_knocked_out"] is False


def test_sensor_q2_knocked_out_for_driver_in_q2_not_q3(hass) -> None:
    """q2_knocked_out=True when driver participated in Q2 but not Q3."""
    data = {
        "drivers": {
            "5": _driver_entry(
                "5",
                q1="1:23.000",
                q2="1:22.800",
                q1_participated=True,
                q2_participated=True,
                q3_participated=False,
                knocked_out=True,
            ),
        },
        "lap_current": None,
        "lap_total": None,
        "session": {"part": 3},
    }
    sensor = _make_sensor(hass, DummyCoordinator(data=data))
    sensor._update_from_coordinator(initial=True)

    drv = sensor._attr_extra_state_attributes["drivers"][0]
    assert drv["q1_knocked_out"] is False
    assert drv["q2_knocked_out"] is True
    assert drv["q3_knocked_out"] is False


def test_sensor_dnf_in_q2_without_time_is_q2_knocked_out(hass) -> None:
    """Driver who crashed in Q2 (participated but set no time) gets q2_knocked_out=True."""
    data = {
        "drivers": {
            "77": _driver_entry(
                "77",
                q1="1:23.500",
                q2=None,  # crashed before setting Q2 time
                q1_participated=True,
                q2_participated=True,  # was in Q2 session
                q3_participated=False,
                knocked_out=True,
            ),
        },
        "lap_current": None,
        "lap_total": None,
        "session": {"part": 3},
    }
    sensor = _make_sensor(hass, DummyCoordinator(data=data))
    sensor._update_from_coordinator(initial=True)

    drv = sensor._attr_extra_state_attributes["drivers"][0]
    assert drv["q1_knocked_out"] is False  # advanced to Q2
    assert drv["q2_knocked_out"] is True  # did not reach Q3
    assert drv["q3_knocked_out"] is False


def test_sensor_current_qualifying_part_in_attributes(hass) -> None:
    """current_qualifying_part is exposed as a top-level attribute during qualifying."""
    data = {
        "drivers": {
            "1": _driver_entry("1", position="1", q1_participated=True),
        },
        "lap_current": None,
        "lap_total": None,
        "session": {"part": 2},
    }
    sensor = _make_sensor(hass, DummyCoordinator(data=data))
    sensor._update_from_coordinator(initial=True)

    assert sensor._attr_extra_state_attributes["current_qualifying_part"] == 2


def test_sensor_shootout_session_is_qualifying_like(hass) -> None:
    """Sprint Shootout sessions are treated as qualifying-like."""
    data = {
        "drivers": {
            "1": _driver_entry("1", position="1", q1="1:20.000", q1_participated=True),
        },
        "lap_current": None,
        "lap_total": None,
        "session": {"part": 1},
    }
    sensor = _make_sensor(
        hass,
        DummyCoordinator(data=data),
        session_type="Qualifying",
        session_name="Sprint Shootout",
    )
    sensor._update_from_coordinator(initial=True)

    drv = sensor._attr_extra_state_attributes["drivers"][0]
    assert drv["q1_time"] == "1:20.000"


def test_sensor_all_20_drivers_have_q_fields(hass) -> None:
    """All drivers have q-fields, even those with no qualifying times."""
    drivers = {
        str(i): _driver_entry(
            str(i),
            position=str(i),
            q1="1:23.000" if i <= 15 else None,
            q1_participated=True,
            knocked_out=(i > 15),
        )
        for i in range(1, 21)
    }
    data = {
        "drivers": drivers,
        "lap_current": None,
        "lap_total": None,
        "session": {"part": 1},
    }
    sensor = _make_sensor(hass, DummyCoordinator(data=data))
    sensor._update_from_coordinator(initial=True)

    result_drivers = sensor._attr_extra_state_attributes["drivers"]
    assert len(result_drivers) == 20
    for drv in result_drivers:
        assert "q1_time" in drv
        assert "q1_knocked_out" in drv
        assert "q1_position" in drv


# ---------------------------------------------------------------------------
# _parse_lap_time_to_secs unit tests
# ---------------------------------------------------------------------------


def test_parse_lap_time_minutes_and_seconds() -> None:
    assert _parse_lap_time_to_secs("1:23.247") == pytest.approx(83.247)


def test_parse_lap_time_only_seconds() -> None:
    assert _parse_lap_time_to_secs("58.312") == pytest.approx(58.312)


def test_parse_lap_time_two_minutes() -> None:
    assert _parse_lap_time_to_secs("2:01.500") == pytest.approx(121.5)
