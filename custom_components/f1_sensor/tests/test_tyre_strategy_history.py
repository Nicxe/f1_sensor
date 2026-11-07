"""Tyre strategy history preserves physical sets, used ages and unknown data."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.f1_sensor import LiveDriversCoordinator
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.live_data_models import CurrentTyresModel


@pytest.fixture
async def coordinator(hass):
    coord = LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    yield coord
    await coord.async_close()


def timing(coord, laps, **fields):
    coord._on_timingdata({"Lines": {"44": {"NumberOfLaps": laps, **fields}}})


def tyres(coord, index, **fields):
    coord._on_timingapp({"Lines": {"44": {"Stints": {str(index): fields}}}})


def projected(coord):
    model = CurrentTyresModel(coord, None, None, None)
    assert model._update_from_coordinator()
    return model._attr_extra_state_attributes["drivers"][0]


@pytest.mark.parametrize("age", [0, "0", 3, "3"])
async def test_start_age_zero_is_known_and_used_age_is_not_added_twice(
    coordinator, age
):
    timing(coordinator, 0)
    tyres(
        coordinator,
        0,
        Compound="MEDIUM",
        New="true" if int(age) == 0 else "false",
        TyresNotChanged="0",
        StartLaps=age,
        TotalLaps=age,
    )
    timing(coordinator, 4)
    tyres(coordinator, 0, TotalLaps=int(age) + 4)
    row = projected(coordinator)
    stint = row["stints"][0]
    assert stint["tyre_age_at_start"] == int(age)
    assert stint["total_laps"] == int(age) + 4
    assert stint["stint_laps"] == 4
    assert stint["first_lap"] == 1
    assert stint["last_lap"] == 4
    assert stint["is_current"] is True
    assert row["stint_history_complete"] is True


async def test_real_change_preserves_previous_stint_and_used_mount_age(coordinator):
    timing(coordinator, 0)
    tyres(
        coordinator,
        0,
        Compound="MEDIUM",
        New="true",
        TyresNotChanged="0",
        StartLaps=0,
        TotalLaps=0,
    )
    timing(coordinator, 18, InPit=True)
    tyres(coordinator, 0, TotalLaps=18)
    tyres(
        coordinator,
        1,
        Compound="HARD",
        New="false",
        TyresNotChanged="0",
        StartLaps=3,
        TotalLaps=3,
    )
    timing(coordinator, 25, InPit=False)
    tyres(coordinator, 1, TotalLaps=10)
    row = projected(coordinator)
    assert len(row["stints"]) == 2
    first, current = row["stints"]
    assert (
        first["first_lap"],
        first["last_lap"],
        first["stint_laps"],
        first["total_laps"],
    ) == (1, 18, 18, 18)
    assert first["is_current"] is False
    assert (
        current["first_lap"],
        current["last_lap"],
        current["stint_laps"],
        current["tyre_age_at_start"],
        current["total_laps"],
    ) == (19, 25, 7, 3, 10)
    timing(coordinator, 25, Retired=True)
    retired = projected(coordinator)
    assert retired["stints"][1]["last_lap"] == 25
    assert retired["retired"] is True
    assert retired["in_pit"] is False
    coordinator._on_lapcount({"CurrentLap": 30, "TotalLaps": 56})
    assert projected(coordinator)["stints"][1]["last_lap"] == 25


@pytest.mark.parametrize("initial_laps,start_age", [(12, 3), (None, None)])
async def test_late_or_incomplete_feed_does_not_invent_lap_bounds(
    coordinator, initial_laps, start_age
):
    if initial_laps is not None:
        timing(coordinator, initial_laps)
    fields = {
        "Compound": "SOFT",
        "New": "false",
        "TyresNotChanged": "0",
        "TotalLaps": 7,
    }
    if start_age is not None:
        fields["StartLaps"] = start_age
    tyres(coordinator, 1, **fields)
    row = projected(coordinator)
    stint = row["stints"][0]
    assert stint["first_lap"] is None
    assert stint["last_lap"] is None
    assert stint["tyre_age_at_start"] == start_age
    assert stint["stint_laps"] == (4 if start_age is not None else None)
    assert stint["coverage"] == "partial"
    assert row["stint_history_complete"] is False
    assert row["completed_laps"] == initial_laps


@pytest.mark.parametrize(
    "sequence,driver,expected_laps",
    [("austin_leclerc", "16", 22), ("singapore_alonso", "14", 35)],
)
async def test_recorded_continuation_and_phantom_rows_are_one_set(
    coordinator, sequence, driver, expected_laps
):
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/issue920_current_tyres.json").read_text()
    )
    for frame in fixture[sequence]["frames"]:
        coordinator._on_timingapp(frame["payload"])
    row = projected(coordinator)
    assert row["racing_number"] == driver
    assert len(row["stints"]) == 1
    assert row["stints"][0]["total_laps"] == expected_laps
    assert row["stints"][0]["compound"] == "SOFT"


async def test_counter_correction_keeps_active_continuation_and_unknown_is_not_zero(
    coordinator,
):
    tyres(
        coordinator,
        0,
        Compound="SOFT",
        New="true",
        TyresNotChanged="0",
        StartLaps=0,
        TotalLaps=3,
    )
    tyres(
        coordinator,
        1,
        Compound="SOFT",
        New="false",
        TyresNotChanged="1",
        StartLaps=3,
        TotalLaps=5,
    )
    assert projected(coordinator)["stints"][0]["total_laps"] == 5
    tyres(coordinator, 1, TotalLaps=2)
    assert projected(coordinator)["stints"][0]["total_laps"] == 2
    tyres(coordinator, 2, Compound="HARD", TyresNotChanged="0")
    assert projected(coordinator)["stints"][0]["total_laps"] == 2
    assert projected(coordinator)["stints"][1]["total_laps"] is None
    assert projected(coordinator)["stints"][1]["tyre_age_at_start"] is None


async def test_snapshot_does_not_create_a_pit_change_or_retain_other_session(
    coordinator,
):
    timing(coordinator, 12, InPit=True)
    tyres(
        coordinator,
        0,
        Compound="MEDIUM",
        TyresNotChanged="0",
        StartLaps=0,
        TotalLaps=12,
    )
    coordinator._on_timingapp(
        {
            "_f1_snapshot": True,
            "Lines": {
                "44": {
                    "Stints": {
                        "1": {
                            "Compound": "HARD",
                            "TyresNotChanged": "0",
                            "StartLaps": 0,
                            "TotalLaps": 0,
                        }
                    }
                }
            },
        }
    )
    assert projected(coordinator)["stints"][1]["first_lap"] is None
    coordinator.reset_for_replay()
    tyres(
        coordinator, 0, Compound="SOFT", TyresNotChanged="0", StartLaps=0, TotalLaps=0
    )
    row = projected(coordinator)
    assert len(row["stints"]) == 1
    assert row["stints"][0]["compound"] == "SOFT"
    assert row["completed_laps"] is None


async def test_known_race_bounds_do_not_require_known_tyre_age(coordinator):
    timing(coordinator, 0)
    tyres(coordinator, 0, Compound="SOFT", TyresNotChanged="0")
    before = projected(coordinator)["stints"][0]
    assert before["first_lap"] == 1
    assert before["stint_laps"] == 0
    assert before["tyre_age_at_start"] is None
    assert before["total_laps"] is None
    timing(coordinator, 5, InPit=True)
    tyres(coordinator, 1, Compound="HARD", TyresNotChanged="0")
    first, current = projected(coordinator)["stints"]
    assert (first["first_lap"], first["last_lap"], first["stint_laps"]) == (1, 5, 5)
    assert current["first_lap"] == 6
    assert current["stint_laps"] == 0
    assert current["coverage"] == "partial"


async def test_pit_timing_may_arrive_after_the_tyre_change(coordinator):
    timing(coordinator, 0)
    tyres(
        coordinator, 0, Compound="SOFT", TyresNotChanged="0", StartLaps=0, TotalLaps=0
    )
    timing(coordinator, 5)
    tyres(
        coordinator, 1, Compound="HARD", TyresNotChanged="0", StartLaps=2, TotalLaps=2
    )
    assert projected(coordinator)["stints"][1]["first_lap"] is None
    timing(coordinator, 5, InPit=True)
    assert projected(coordinator)["stints"][1]["first_lap"] == 6


async def test_pit_lane_without_a_tyre_change_keeps_one_stint(coordinator):
    timing(coordinator, 0)
    tyres(
        coordinator, 0, Compound="SOFT", TyresNotChanged="0", StartLaps=0, TotalLaps=0
    )
    timing(coordinator, 4, InPit=True)
    tyres(coordinator, 0, TotalLaps=4)
    timing(coordinator, 5, InPit=False)
    tyres(coordinator, 0, TotalLaps=5)
    row = projected(coordinator)
    assert len(row["stints"]) == 1
    assert row["stints"][0]["stint_laps"] == 5


async def test_conflicting_age_and_observed_distance_remain_partial(coordinator):
    timing(coordinator, 0)
    tyres(
        coordinator, 0, Compound="SOFT", TyresNotChanged="0", StartLaps=0, TotalLaps=0
    )
    timing(coordinator, 4)
    tyres(coordinator, 0, TotalLaps=2)
    stint = projected(coordinator)["stints"][0]
    assert stint["stint_laps"] == 4
    assert stint["total_laps"] == 2
    assert stint["coverage"] == "partial"


@pytest.mark.parametrize(
    ("head_compound", "compound", "continuation_age", "expected_age"),
    [
        ("SOFT", "SOFT", 5, 5),
        ("SOFT", "UNKNOWN", 5, 5),
        ("SOFT", "HARD", 5, 3),
        ("SOFT", "SOFT", 3, 3),
        ("UNKNOWN", "SOFT", 5, 5),
    ],
)
async def test_late_snapshot_uses_known_historical_continuation_age(
    coordinator, head_compound, compound, continuation_age, expected_age
):
    coordinator._on_timingapp(
        {
            "_f1_snapshot": True,
            "Lines": {
                "44": {
                    "Stints": {
                        "0": {
                            "Compound": head_compound,
                            "TyresNotChanged": "0",
                            "StartLaps": 0,
                            "TotalLaps": 3,
                        },
                        "1": {
                            "Compound": compound,
                            "TyresNotChanged": "1",
                            "StartLaps": 3,
                            "TotalLaps": continuation_age,
                        },
                        "2": {
                            "Compound": "HARD",
                            "TyresNotChanged": "0",
                            "StartLaps": 2,
                            "TotalLaps": 6,
                        },
                    }
                }
            },
        }
    )
    first, current = projected(coordinator)["stints"]
    assert first["total_laps"] == expected_age
    assert first["stint_laps"] == expected_age
    assert first["first_lap"] is None
    assert first["coverage"] == "partial"
    assert current["total_laps"] == 6


async def test_reused_model_drops_previous_session_history_on_empty_reset(
    hass, coordinator
):
    hass.data[DOMAIN] = {
        "entry": {"live_state": SimpleNamespace(is_live=True, reason="live")}
    }
    coordinator._on_sessioninfo({"Key": 1})
    timing(coordinator, 0)
    tyres(
        coordinator, 0, Compound="SOFT", TyresNotChanged="0", StartLaps=0, TotalLaps=0
    )
    model = CurrentTyresModel(coordinator, None, "entry", None)
    before = model.snapshot()
    assert before.value == 1
    assert before.attributes["drivers"][0]["stints"]
    coordinator._on_sessioninfo({"Key": 2})
    assert coordinator.data["drivers"] == {}
    after = model.snapshot()
    assert after.value == 0
    assert after.attributes == {"drivers": [], "lap_current": None, "lap_total": None}
