"""Tests for qualifying segment data (Q1/Q2/Q3) in LiveDriversCoordinator and
F1DriverPositionsSensor."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import pytest

from custom_components.f1_sensor.__init__ import LiveDriversCoordinator
from custom_components.f1_sensor.const import (
    CONF_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
)
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


def _build_coordinator(hass, data: dict) -> DataUpdateCoordinator:
    coordinator = DataUpdateCoordinator(
        hass,
        logging.getLogger(__name__),
        name="test",
        update_method=None,
    )
    coordinator.data = data
    coordinator.available = True
    return coordinator


async def _add_sensors(hass, sensors: list) -> None:
    component = EntityComponent(None, "sensor", hass)
    await component.async_add_entities(sensors)
    await hass.async_block_till_done()


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
    entry_id: str = "entry",
    session_type: str = "Qualifying",
    session_name: str = "Qualifying",
) -> F1DriverPositionsSensor:
    sensor = F1DriverPositionsSensor(coord, "uid", entry_id, "F1")
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


def _australian_q1_start_snapshot() -> dict:
    """Reduced Q1 start payload using list-style BestLapTimes placeholders."""
    return {
        "SessionPart": 1,
        "Lines": {
            "63": {"BestLapTimes": [{"Value": ""}, {}, {}], "KnockedOut": False},
            "23": {"BestLapTimes": [{"Value": ""}, {}, {}], "KnockedOut": False},
            "14": {"BestLapTimes": [{"Value": ""}, {}, {}], "KnockedOut": False},
        },
    }


def _australian_q2_start_snapshot() -> dict:
    """Reduced Q2 start payload with a Q1-eliminated driver still in the snapshot."""
    return {
        "SessionPart": 2,
        "Lines": {
            "63": {"BestLapTimes": {"1": {"Value": ""}}, "KnockedOut": False},
            "23": {"BestLapTimes": {"1": {"Value": ""}}, "KnockedOut": False},
            "14": {"KnockedOut": True},
        },
    }


def _australian_q3_start_snapshot() -> dict:
    """Reduced Q3 start payload with a Q2-eliminated driver still in the snapshot."""
    return {
        "SessionPart": 3,
        "Lines": {
            "63": {"BestLapTimes": {"2": {"Value": ""}}, "KnockedOut": False},
            "23": {"KnockedOut": True},
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
    """List-style BestLapTimes placeholders mark only the active Q1 segment."""
    coord = _make_coord(hass)
    coord._merge_timingdata(
        {"SessionPart": 1, "Lines": {"44": {"BestLapTimes": [{"Value": ""}, {}, {}]}}}
    )
    q = coord._state["drivers"]["44"]["qualifying"]
    assert q["segments"][1]["participated"] is True
    assert q["segments"][2]["participated"] is False
    assert q["segments"][3]["participated"] is False


@pytest.mark.asyncio
async def test_coordinator_marks_participation_q2(hass) -> None:
    """Segment placeholders mark Q2 participation without over-marking Q3."""
    coord = _make_coord(hass)
    coord._merge_timingdata(
        {"SessionPart": 1, "Lines": {"44": {"BestLapTimes": [{"Value": ""}, {}, {}]}}}
    )
    coord._merge_timingdata(
        {"SessionPart": 2, "Lines": {"44": {"BestLapTimes": {"1": {"Value": ""}}}}}
    )
    q = coord._state["drivers"]["44"]["qualifying"]
    assert q["segments"][1]["participated"] is True
    assert q["segments"][2]["participated"] is True
    assert q["segments"][3]["participated"] is False


@pytest.mark.asyncio
async def test_coordinator_snapshot_keeps_eliminated_drivers_out_of_future_segments(
    hass,
) -> None:
    """Eliminated drivers staying in the snapshot do not gain future participation."""
    coord = _make_coord(hass)
    coord._merge_timingdata(_australian_q1_start_snapshot())
    coord._merge_timingdata(_australian_q2_start_snapshot())
    coord._merge_timingdata(_australian_q3_start_snapshot())

    q1_eliminated = coord._state["drivers"]["14"]["qualifying"]
    q2_eliminated = coord._state["drivers"]["23"]["qualifying"]
    q3_driver = coord._state["drivers"]["63"]["qualifying"]

    assert q1_eliminated["segments"][1]["participated"] is True
    assert q1_eliminated["segments"][2]["participated"] is False
    assert q1_eliminated["segments"][3]["participated"] is False
    assert q2_eliminated["segments"][2]["participated"] is True
    assert q2_eliminated["segments"][3]["participated"] is False
    assert q3_driver["segments"][3]["participated"] is True


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


@pytest.mark.asyncio
async def test_sensor_qualifying_knockout_flags_follow_q2_q3_transition_snapshots(
    hass,
) -> None:
    """Australian-style Q2/Q3 snapshots keep Q1 and Q2 eliminations distinct."""
    coord = _make_coord(hass)
    coord._merge_timingdata(_australian_q1_start_snapshot())
    coord._merge_timingdata(_australian_q2_start_snapshot())
    coord._merge_timingdata(_australian_q3_start_snapshot())

    sensor = _make_sensor(hass, DummyCoordinator(data=coord._state))
    assert sensor._update_from_coordinator(initial=True) is True

    by_rn = {
        d["racing_number"]: d for d in sensor._attr_extra_state_attributes["drivers"]
    }
    assert by_rn["14"]["q1_knocked_out"] is True
    assert by_rn["14"]["q2_knocked_out"] is False
    assert by_rn["23"]["q1_knocked_out"] is False
    assert by_rn["23"]["q2_knocked_out"] is True
    assert by_rn["63"]["q1_knocked_out"] is False
    assert by_rn["63"]["q2_knocked_out"] is False


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


def test_sensor_current_qualifying_part_falls_back_to_session_status(hass) -> None:
    """SessionStatus qualifying_part backfills the attribute before segment laps exist."""
    data = {
        "drivers": {
            "1": _driver_entry(
                "1",
                position="1",
                q1="1:20.000",
                q1_participated=True,
            ),
        },
        "lap_current": None,
        "lap_total": None,
    }
    sensor = _make_sensor(hass, DummyCoordinator(data=data))
    sensor._session_status_coordinator = SimpleNamespace(
        is_qualifying_like_session=True,
        qualifying_part=2,
    )
    sensor._update_from_coordinator(initial=True)

    assert sensor._attr_extra_state_attributes["current_qualifying_part"] == 2


def test_sensor_current_qualifying_part_falls_back_for_sprint_shootout(hass) -> None:
    """Sprint Shootout uses the same status-coordinator fallback."""
    data = {
        "drivers": {
            "1": _driver_entry(
                "1",
                position="1",
                q1="1:20.000",
                q1_participated=True,
            ),
        },
        "lap_current": None,
        "lap_total": None,
    }
    sensor = _make_sensor(
        hass,
        DummyCoordinator(data=data),
        session_type="Qualifying",
        session_name="Sprint Shootout",
    )
    sensor._session_status_coordinator = SimpleNamespace(
        is_qualifying_like_session=True,
        qualifying_part=3,
    )
    sensor._update_from_coordinator(initial=True)

    assert sensor._attr_extra_state_attributes["current_qualifying_part"] == 3


def test_sensor_current_qualifying_part_stays_none_outside_qualifying(hass) -> None:
    """Non-qualifying sessions do not expose a qualifying part from stale status data."""
    data = {
        "drivers": {
            "1": _driver_entry("1", position="1"),
        },
        "lap_current": 5,
        "lap_total": 57,
    }
    sensor = _make_sensor(
        hass,
        DummyCoordinator(data=data),
        session_type="Race",
        session_name="Formula 1 Race",
    )
    sensor._session_status_coordinator = SimpleNamespace(
        is_qualifying_like_session=False,
        qualifying_part=2,
    )
    sensor._update_from_coordinator(initial=True)

    assert sensor._attr_extra_state_attributes["current_qualifying_part"] is None


@pytest.mark.asyncio
async def test_sensor_session_status_update_refreshes_current_qualifying_part(
    hass,
) -> None:
    """A SessionStatus context update changes the exported Q-part without new TimingData."""
    entry_id = "test_entry_q_part_status_update"
    drivers_coordinator = _build_coordinator(
        hass,
        {
            "drivers": {
                "1": _driver_entry(
                    "1",
                    position="1",
                    q1="1:20.000",
                    q1_participated=True,
                ),
            },
            "lap_current": None,
            "lap_total": None,
        },
    )
    status_coordinator = _build_coordinator(hass, {"Status": "Started"})
    status_coordinator.is_qualifying_like_session = True
    status_coordinator.qualifying_part = 1
    info_coordinator = _build_coordinator(
        hass,
        {"Type": "Qualifying", "Name": "Qualifying"},
    )

    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": SimpleNamespace(is_live=True),
        "session_info_coordinator": info_coordinator,
        "session_status_coordinator": status_coordinator,
    }

    sensor = F1DriverPositionsSensor(drivers_coordinator, "uid_status", entry_id, "F1")
    await _add_sensors(hass, [sensor])

    state = hass.states.get(sensor.entity_id)
    assert state is not None
    assert state.attributes["current_qualifying_part"] == 1

    status_coordinator.qualifying_part = 2
    status_coordinator.async_set_updated_data({"Status": "Started"})
    await hass.async_block_till_done()

    updated_state = hass.states.get(sensor.entity_id)
    assert updated_state is not None
    assert updated_state.attributes["current_qualifying_part"] == 2


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
