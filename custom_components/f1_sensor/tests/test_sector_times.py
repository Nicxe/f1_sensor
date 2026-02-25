from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.f1_sensor.__init__ import LiveDriversCoordinator
from custom_components.f1_sensor.sensor import F1DriverPositionsSensor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _sector_payload(rn: str, s1=None, s2=None, s3=None) -> dict:
    """Build a TimingData-style payload with three sectors for a driver."""

    def _make_sector(time_str, personal_fastest=False, overall_fastest=False):
        if time_str is None:
            return {
                "Value": "",
                "Status": 2048,
                "OverallFastest": False,
                "PersonalFastest": False,
            }
        status = 0
        if overall_fastest:
            status = 2051
        elif personal_fastest:
            status = 2049
        return {
            "Value": time_str,
            "Status": status,
            "OverallFastest": overall_fastest,
            "PersonalFastest": personal_fastest,
        }

    return {
        "Lines": {
            rn: {
                "Sectors": [
                    _make_sector(**(s1 or {"time_str": None}))
                    if isinstance(s1, dict)
                    else _make_sector(s1),
                    _make_sector(**(s2 or {"time_str": None}))
                    if isinstance(s2, dict)
                    else _make_sector(s2),
                    _make_sector(**(s3 or {"time_str": None}))
                    if isinstance(s3, dict)
                    else _make_sector(s3),
                ]
            }
        }
    }


# ---------------------------------------------------------------------------
# Test 1: S1 arrival clears previous S2 and S3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s1_arrival_clears_previous_s2_s3(hass) -> None:
    coord = _make_coord(hass)

    # Complete lap: all three sectors set
    coord._merge_timingdata(_sector_payload("44", "27.0", "32.0", "28.0"))
    sectors = coord._state["drivers"]["44"]["sectors"]
    assert sectors["current"][0]["time"] == pytest.approx(27.0)
    assert sectors["current"][1]["time"] == pytest.approx(32.0)
    assert sectors["current"][2]["time"] == pytest.approx(28.0)

    # New lap: S1 arrives only, S2 and S3 should be cleared
    coord._merge_timingdata(_sector_payload("44", "26.5", None, None))
    sectors = coord._state["drivers"]["44"]["sectors"]
    assert sectors["current"][0]["time"] == pytest.approx(26.5)
    assert sectors["current"][1]["time"] is None
    assert sectors["current"][2]["time"] is None


# ---------------------------------------------------------------------------
# Test 2: S2 and S3 not cleared when updated together with S1 in same message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s1_does_not_clear_s2_s3_when_all_arrive_together(hass) -> None:
    coord = _make_coord(hass)

    # All three sectors in a single message (e.g. replay catch-up)
    coord._merge_timingdata(_sector_payload("44", "27.0", "32.0", "28.0"))
    sectors = coord._state["drivers"]["44"]["sectors"]
    assert sectors["current"][0]["time"] == pytest.approx(27.0)
    assert sectors["current"][1]["time"] == pytest.approx(32.0)
    assert sectors["current"][2]["time"] == pytest.approx(28.0)


# ---------------------------------------------------------------------------
# Test 3: PersonalFastest flag updates best sector; non-personal does not
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_personal_fastest_updates_best_sector(hass) -> None:
    coord = _make_coord(hass)

    # First S1 with PersonalFastest — should store best
    coord._merge_timingdata(
        {
            "Lines": {
                "44": {
                    "Sectors": [
                        {
                            "Value": "26.5",
                            "Status": 2049,
                            "OverallFastest": False,
                            "PersonalFastest": True,
                        },
                        {
                            "Value": "",
                            "Status": 2048,
                            "OverallFastest": False,
                            "PersonalFastest": False,
                        },
                        {
                            "Value": "",
                            "Status": 2048,
                            "OverallFastest": False,
                            "PersonalFastest": False,
                        },
                    ]
                }
            }
        }
    )
    sectors = coord._state["drivers"]["44"]["sectors"]
    assert sectors["best"][0] == pytest.approx(26.5)

    # New lap: slower S1 without PersonalFastest — best should not change
    coord._merge_timingdata(
        {
            "Lines": {
                "44": {
                    "Sectors": [
                        {
                            "Value": "27.1",
                            "Status": 0,
                            "OverallFastest": False,
                            "PersonalFastest": False,
                        },
                        {
                            "Value": "",
                            "Status": 2048,
                            "OverallFastest": False,
                            "PersonalFastest": False,
                        },
                        {
                            "Value": "",
                            "Status": 2048,
                            "OverallFastest": False,
                            "PersonalFastest": False,
                        },
                    ]
                }
            }
        }
    )
    sectors = coord._state["drivers"]["44"]["sectors"]
    assert sectors["best"][0] == pytest.approx(26.5)  # unchanged


# ---------------------------------------------------------------------------
# Test 4: OverallFastest flag passes through to current sector data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overall_fastest_flag_propagated(hass) -> None:
    coord = _make_coord(hass)

    coord._merge_timingdata(
        {
            "Lines": {
                "44": {
                    "Sectors": [
                        {
                            "Value": "25.9",
                            "Status": 2051,
                            "OverallFastest": True,
                            "PersonalFastest": True,
                        },
                        {
                            "Value": "",
                            "Status": 2048,
                            "OverallFastest": False,
                            "PersonalFastest": False,
                        },
                        {
                            "Value": "",
                            "Status": 2048,
                            "OverallFastest": False,
                            "PersonalFastest": False,
                        },
                    ]
                }
            }
        }
    )
    sectors = coord._state["drivers"]["44"]["sectors"]
    assert sectors["current"][0]["overall_fastest"] is True
    assert sectors["current"][0]["personal_fastest"] is True
    assert sectors["current"][0]["time"] == pytest.approx(25.9)


# ---------------------------------------------------------------------------
# Test 5: SC transition clears current sectors but preserves best times
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sc_clears_current_sectors_not_best(hass) -> None:
    coord = _make_coord(hass)

    # Set up personal bests and current sectors
    coord._merge_timingdata(
        {
            "Lines": {
                "44": {
                    "Sectors": [
                        {
                            "Value": "26.5",
                            "Status": 2049,
                            "OverallFastest": False,
                            "PersonalFastest": True,
                        },
                        {
                            "Value": "31.0",
                            "Status": 2049,
                            "OverallFastest": False,
                            "PersonalFastest": True,
                        },
                        {
                            "Value": "27.8",
                            "Status": 2049,
                            "OverallFastest": False,
                            "PersonalFastest": True,
                        },
                    ]
                }
            }
        }
    )
    sectors = coord._state["drivers"]["44"]["sectors"]
    assert sectors["best"][0] == pytest.approx(26.5)

    # SC begins
    coord._on_trackstatus({"Status": "2"})

    sectors = coord._state["drivers"]["44"]["sectors"]
    # Current sectors should be cleared
    assert sectors["current"][0]["time"] is None
    assert sectors["current"][1]["time"] is None
    assert sectors["current"][2]["time"] is None
    # Best times must survive
    assert sectors["best"][0] == pytest.approx(26.5)
    assert sectors["best"][1] == pytest.approx(31.0)
    assert sectors["best"][2] == pytest.approx(27.8)


# ---------------------------------------------------------------------------
# Test 6: Sector updates are skipped while SC/VSC is active
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sector_updates_skipped_during_sc(hass) -> None:
    coord = _make_coord(hass)

    # SC is already active (state set directly to simulate)
    coord._state["track_status"] = "2"

    coord._merge_timingdata(_sector_payload("44", "27.0", None, None))
    # Driver entry may not exist yet if SC was set before any TimingData
    driver = coord._state["drivers"].get("44")
    if driver:
        assert (
            driver.get("sectors", {}).get("current", {}).get(0, {}).get("time") is None
        )


# ---------------------------------------------------------------------------
# Test 7: SessionPart change resets best sectors for all drivers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_part_change_resets_best_sectors(hass) -> None:
    coord = _make_coord(hass)

    # Q1: set personal best for driver 44
    coord._merge_timingdata(
        {
            "Lines": {
                "44": {
                    "Sectors": [
                        {
                            "Value": "26.5",
                            "Status": 2049,
                            "OverallFastest": False,
                            "PersonalFastest": True,
                        },
                        {
                            "Value": "",
                            "Status": 2048,
                            "OverallFastest": False,
                            "PersonalFastest": False,
                        },
                        {
                            "Value": "",
                            "Status": 2048,
                            "OverallFastest": False,
                            "PersonalFastest": False,
                        },
                    ]
                }
            },
            "SessionPart": 1,
        }
    )
    assert coord._state["drivers"]["44"]["sectors"]["best"][0] == pytest.approx(26.5)

    # Q2 begins
    coord._merge_timingdata(
        {
            "Lines": {},
            "SessionPart": 2,
        }
    )

    sectors = coord._state["drivers"]["44"]["sectors"]
    assert sectors["best"][0] is None
    assert sectors["best"][1] is None
    assert sectors["best"][2] is None
    assert sectors["current"][0]["time"] is None


# ---------------------------------------------------------------------------
# Test 8: Invalid sector times (Status 2048, empty Value, Stopped) are ignored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_sectors_ignored(hass) -> None:
    coord = _make_coord(hass)

    # Status 2048 with a value should be ignored
    coord._merge_timingdata(
        {
            "Lines": {
                "44": {
                    "Sectors": [
                        {
                            "Value": "27.0",
                            "Status": 2048,
                            "OverallFastest": False,
                            "PersonalFastest": False,
                        },
                        {
                            "Value": "",
                            "Status": 2048,
                            "OverallFastest": False,
                            "PersonalFastest": False,
                        },
                        {
                            "Value": "",
                            "Status": 2048,
                            "OverallFastest": False,
                            "PersonalFastest": False,
                        },
                    ]
                }
            }
        }
    )
    sectors = coord._state["drivers"]["44"]["sectors"]
    assert sectors["current"][0]["time"] is None

    # Stopped=True should be ignored
    coord._merge_timingdata(
        {
            "Lines": {
                "44": {
                    "Sectors": [
                        {
                            "Value": "27.0",
                            "Status": 0,
                            "Stopped": True,
                            "OverallFastest": False,
                            "PersonalFastest": False,
                        },
                        {
                            "Value": "",
                            "Status": 2048,
                            "OverallFastest": False,
                            "PersonalFastest": False,
                        },
                        {
                            "Value": "",
                            "Status": 2048,
                            "OverallFastest": False,
                            "PersonalFastest": False,
                        },
                    ]
                }
            }
        }
    )
    sectors = coord._state["drivers"]["44"]["sectors"]
    assert sectors["current"][0]["time"] is None


# ---------------------------------------------------------------------------
# Test 8b: Real-world format — sector completed without Status field
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sector_without_status_field_is_accepted(hass) -> None:
    """Real F1 sector-complete messages omit Status entirely.

    Format: {"Lines":{"1":{"Sectors":{"1":{"Value":"38.489","OverallFastest":true,"PersonalFastest":true}}}}}
    The previous code defaulted Status to 2048 (= no time) and silently dropped these.
    """
    coord = _make_coord(hass)

    coord._merge_timingdata(
        {
            "Lines": {
                "1": {
                    "Sectors": {
                        "1": {
                            "Value": "38.489",
                            "OverallFastest": True,
                            "PersonalFastest": True,
                        }
                    }
                }
            }
        }
    )
    sectors = coord._state["drivers"]["1"]["sectors"]
    assert sectors["current"][1]["time"] == pytest.approx(38.489)
    assert sectors["current"][1]["overall_fastest"] is True
    assert sectors["current"][1]["personal_fastest"] is True
    assert sectors["best"][1] == pytest.approx(38.489)


# ---------------------------------------------------------------------------
# Test 9: Sensor maps sector fields correctly to driver attributes
# ---------------------------------------------------------------------------


class DummyCoordinator(SimpleNamespace):
    def async_add_listener(self, _listener):
        return lambda: None


def _payload_with_sectors() -> dict:
    return {
        "drivers": {
            "44": {
                "identity": {
                    "tla": "HAM",
                    "name": "Lewis Hamilton",
                    "team": "Mercedes",
                    "team_color": "00D26E",
                },
                "timing": {"position": "1"},
                "lap_history": {
                    "laps": {},
                    "grid_position": "1",
                    "completed_laps": 3,
                },
                "sectors": {
                    "current": {
                        0: {
                            "time": 27.456,
                            "overall_fastest": False,
                            "personal_fastest": True,
                        },
                        1: {
                            "time": None,
                            "overall_fastest": None,
                            "personal_fastest": None,
                        },
                        2: {
                            "time": None,
                            "overall_fastest": None,
                            "personal_fastest": None,
                        },
                    },
                    "best": {0: 26.789, 1: None, 2: None},
                },
            }
        },
        "lap_current": 3,
        "lap_total": 50,
        "fastest_lap": None,
    }


def test_sensor_maps_sector_fields(hass) -> None:
    coord = DummyCoordinator(data=_payload_with_sectors())
    sensor = F1DriverPositionsSensor(coord, "uid", "entry", "F1")
    sensor.hass = hass
    sensor._session_info_coordinator = SimpleNamespace(
        data={"Type": "Race", "Name": "Race"}
    )
    assert sensor._update_from_coordinator(initial=True) is True

    attrs = sensor._attr_extra_state_attributes
    driver = next(d for d in attrs["drivers"] if d["racing_number"] == "44")

    assert driver["sector_1"] == pytest.approx(27.456)
    assert driver["sector_1_personal_fastest"] is True
    assert driver["sector_1_overall_fastest"] is False
    assert driver["sector_2"] is None
    assert driver["sector_2_personal_fastest"] is None
    assert driver["sector_3"] is None
    assert driver["best_sector_1"] == pytest.approx(26.789)
    assert driver["best_sector_2"] is None
    assert driver["best_sector_3"] is None


def test_sensor_sector_fields_absent_when_no_sector_data(hass) -> None:
    """Driver entries without a sectors key should produce None fields, not crash."""
    payload = {
        "drivers": {
            "1": {
                "identity": {
                    "tla": "VER",
                    "name": "Max Verstappen",
                    "team": "Red Bull",
                    "team_color": "3671C6",
                },
                "timing": {"position": "1"},
                "lap_history": {"laps": {}, "grid_position": "1", "completed_laps": 1},
                # No "sectors" key
            }
        },
        "lap_current": 1,
        "lap_total": 50,
        "fastest_lap": None,
    }
    coord = DummyCoordinator(data=payload)
    sensor = F1DriverPositionsSensor(coord, "uid", "entry", "F1")
    sensor.hass = hass
    sensor._session_info_coordinator = SimpleNamespace(
        data={"Type": "Race", "Name": "Race"}
    )
    assert sensor._update_from_coordinator(initial=True) is True

    attrs = sensor._attr_extra_state_attributes
    driver = attrs["drivers"][0]
    assert driver["sector_1"] is None
    assert driver["best_sector_1"] is None
