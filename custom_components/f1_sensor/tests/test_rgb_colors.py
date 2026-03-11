from __future__ import annotations

import logging
from types import SimpleNamespace

from custom_components.f1_sensor.sensor import (
    F1CurrentTyresSensor,
    F1DriverListSensor,
    F1DriverPositionsSensor,
    F1TopThreePositionSensor,
    F1TyreStatisticsSensor,
    _hex_to_rgb,
)

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class DummyCoordinator(SimpleNamespace):
    def async_add_listener(self, _listener):
        return lambda: None


# ---------------------------------------------------------------------------
# _hex_to_rgb unit tests
# ---------------------------------------------------------------------------


def test_hex_to_rgb_with_hash():
    assert _hex_to_rgb("#FF0000") == [255, 0, 0]


def test_hex_to_rgb_without_hash():
    assert _hex_to_rgb("00FF00") == [0, 255, 0]


def test_hex_to_rgb_mixed_case():
    assert _hex_to_rgb("#dc0000") == [220, 0, 0]


def test_hex_to_rgb_none():
    assert _hex_to_rgb(None) is None


def test_hex_to_rgb_empty_string():
    assert _hex_to_rgb("") is None


def test_hex_to_rgb_invalid_length():
    assert _hex_to_rgb("#FFF") is None


def test_hex_to_rgb_invalid_chars():
    assert _hex_to_rgb("#GGHHII") is None


# ---------------------------------------------------------------------------
# F1TopThreePositionSensor
# ---------------------------------------------------------------------------


def test_top_three_team_color_rgb(hass):
    coord = DummyCoordinator(data=None)
    sensor = F1TopThreePositionSensor(coord, "uid_p1", "entry", "F1", position_index=0)
    sensor.hass = hass

    # Simulate a feed line with a team color
    attrs = sensor._build_attrs(
        state=None,
        line={
            "TeamColour": "E8002D",
            "Position": "1",
            "RacingNumber": "1",
            "Tla": "VER",
            "BroadcastName": "M VERSTAPPEN",
            "FullName": "Max Verstappen",
            "FirstName": "Max",
            "LastName": "Verstappen",
            "Team": "Red Bull Racing",
            "LapTime": "1:30.000",
            "OverallFastest": False,
            "PersonalFastest": False,
        },
    )

    assert attrs["team_color"] == "#E8002D"
    assert attrs["team_color_rgb"] == [232, 0, 45]


def test_top_three_team_color_rgb_none_when_missing(hass):
    coord = DummyCoordinator(data=None)
    sensor = F1TopThreePositionSensor(coord, "uid_p1", "entry", "F1", position_index=0)
    sensor.hass = hass

    attrs = sensor._build_attrs(state=None, line=None)
    assert attrs["team_color"] is None
    assert attrs["team_color_rgb"] is None


# ---------------------------------------------------------------------------
# F1DriverListSensor
# ---------------------------------------------------------------------------


def test_driver_list_team_color_rgb(hass):
    coord = DummyCoordinator(
        data={
            "drivers": {
                "16": {
                    "identity": {
                        "racing_number": "16",
                        "tla": "LEC",
                        "name": "Charles Leclerc",
                        "team": "Ferrari",
                        "team_color": "DC0000",
                    }
                }
            }
        }
    )
    sensor = F1DriverListSensor(coord, "uid", "entry", "F1")
    sensor.hass = hass
    sensor._update_from_coordinator()

    drivers = sensor._attr_extra_state_attributes["drivers"]
    assert len(drivers) == 1
    drv = drivers[0]
    assert drv["team_color"] == "#DC0000"
    assert drv["team_color_rgb"] == [220, 0, 0]


def test_driver_list_team_color_rgb_none_when_no_color(hass):
    coord = DummyCoordinator(
        data={
            "drivers": {
                "1": {
                    "identity": {
                        "racing_number": "1",
                        "tla": "TST",
                        "name": "Test Driver",
                        "team": "Test Team",
                        "team_color": None,
                    }
                }
            }
        }
    )
    sensor = F1DriverListSensor(coord, "uid", "entry", "F1")
    sensor.hass = hass
    sensor._update_from_coordinator()

    drv = sensor._attr_extra_state_attributes["drivers"][0]
    assert drv["team_color"] is None
    assert drv["team_color_rgb"] is None


# ---------------------------------------------------------------------------
# F1CurrentTyresSensor
# ---------------------------------------------------------------------------


def test_current_tyres_team_color_rgb(hass):
    coord = DummyCoordinator(
        data={
            "drivers": {
                "1": {
                    "identity": {
                        "racing_number": "1",
                        "tla": "VER",
                        "team_color": "3671C6",
                    },
                    "timing": {"position": "1"},
                    "tyres": {"compound": "SOFT", "stint_laps": 10, "new": False},
                }
            }
        }
    )
    sensor = F1CurrentTyresSensor(coord, "uid", "entry", "F1")
    sensor.hass = hass
    sensor._update_from_coordinator()

    drv = sensor._attr_extra_state_attributes["drivers"][0]
    assert drv["team_color"] == "#3671C6"
    assert drv["team_color_rgb"] == [54, 113, 198]
    assert drv["compound_color"] == "#FF0000"
    assert drv["compound_color_rgb"] == [255, 0, 0]


def test_current_tyres_compound_color_rgb_for_all_compounds(hass):
    expected = {
        "SOFT": [255, 0, 0],
        "MEDIUM": [255, 255, 0],
        "HARD": [255, 255, 255],
        "INTERMEDIATE": [0, 255, 0],
        "WET": [0, 0, 255],
    }
    for compound, rgb in expected.items():
        coord = DummyCoordinator(
            data={
                "drivers": {
                    "1": {
                        "identity": {"tla": "TST", "team_color": None},
                        "timing": {"position": "1"},
                        "tyres": {
                            "compound": compound,
                            "stint_laps": 5,
                            "new": True,
                        },
                    }
                }
            }
        )
        sensor = F1CurrentTyresSensor(coord, "uid", "entry", "F1")
        sensor.hass = hass
        sensor._update_from_coordinator()
        drv = sensor._attr_extra_state_attributes["drivers"][0]
        assert drv["compound_color_rgb"] == rgb, f"Failed for {compound}"


# ---------------------------------------------------------------------------
# F1TyreStatisticsSensor
# ---------------------------------------------------------------------------


def test_tyre_statistics_compound_color_rgb(hass):
    coord = DummyCoordinator(
        data={
            "tyre_statistics": {
                "fastest_compound": "SOFT",
                "fastest_time": "1:29.000",
                "fastest_time_secs": 89.0,
                "deltas": {"SOFT": 0.0, "MEDIUM": 1.2},
                "start_compounds": ["SOFT"],
                "compounds": {
                    "SOFT": {
                        "best_times": [
                            {
                                "racing_number": "1",
                                "tla": "VER",
                                "name": "Max Verstappen",
                                "team": "Red Bull",
                                "time": "1:29.000",
                                "lap": 20,
                            }
                        ],
                        "total_laps": 30,
                        "sets_used": 2,
                        "sets_used_total": 4,
                    }
                },
            }
        }
    )
    sensor = F1TyreStatisticsSensor(coord, "uid", "entry", "F1")
    sensor.hass = hass
    sensor._update_from_coordinator()

    compounds = sensor._attr_extra_state_attributes["compounds"]
    assert "SOFT" in compounds
    soft = compounds["SOFT"]
    assert soft["compound_color"] == "#FF0000"
    assert soft["compound_color_rgb"] == [255, 0, 0]


# ---------------------------------------------------------------------------
# F1DriverPositionsSensor
# ---------------------------------------------------------------------------


def _driver_positions_data() -> dict:
    return {
        "drivers": {
            "16": {
                "identity": {
                    "tla": "LEC",
                    "name": "Charles Leclerc",
                    "team": "Ferrari",
                    "team_color": "DC0000",
                },
                "lap_history": {
                    "laps": {"1": "1:30.000"},
                    "grid_position": "1",
                    "completed_laps": 1,
                },
                "timing": {"position": "1"},
            },
        },
        "lap_current": 1,
        "lap_total": 58,
        "fastest_lap": {
            "racing_number": "16",
            "lap": 1,
            "time": "1:30.000",
            "time_secs": 90.0,
            "tla": "LEC",
            "name": "Charles Leclerc",
            "team": "Ferrari",
            "team_color": "#DC0000",
        },
    }


def test_driver_positions_team_color_rgb(hass):
    coord = DummyCoordinator(data=_driver_positions_data())
    sensor = F1DriverPositionsSensor(coord, "uid", "entry", "F1")
    sensor.hass = hass
    sensor._session_info_coordinator = SimpleNamespace(
        data={"Type": "Race", "Name": "Race"}
    )
    sensor._update_from_coordinator(initial=True)

    attrs = sensor._attr_extra_state_attributes
    drv = next(d for d in attrs["drivers"] if d["racing_number"] == "16")
    assert drv["team_color"] == "#DC0000"
    assert drv["team_color_rgb"] == [220, 0, 0]


def test_driver_positions_fastest_lap_team_color_rgb(hass):
    coord = DummyCoordinator(data=_driver_positions_data())
    sensor = F1DriverPositionsSensor(coord, "uid", "entry", "F1")
    sensor.hass = hass
    sensor._session_info_coordinator = SimpleNamespace(
        data={"Type": "Race", "Name": "Race"}
    )
    sensor._update_from_coordinator(initial=True)

    fastest = sensor._attr_extra_state_attributes["fastest_lap"]
    assert fastest is not None
    assert fastest["team_color"] == "#DC0000"
    assert fastest["team_color_rgb"] == [220, 0, 0]


def test_driver_positions_team_color_rgb_none_when_no_color(hass):
    data = _driver_positions_data()
    data["drivers"]["16"]["identity"]["team_color"] = None
    data["fastest_lap"] = None

    coord = DummyCoordinator(data=data)
    sensor = F1DriverPositionsSensor(coord, "uid", "entry", "F1")
    sensor.hass = hass
    sensor._session_info_coordinator = SimpleNamespace(
        data={"Type": "Race", "Name": "Race"}
    )
    sensor._update_from_coordinator(initial=True)

    attrs = sensor._attr_extra_state_attributes
    drv = next(d for d in attrs["drivers"] if d["racing_number"] == "16")
    assert drv["team_color"] is None
    assert drv["team_color_rgb"] is None
    assert attrs["fastest_lap"] is None
