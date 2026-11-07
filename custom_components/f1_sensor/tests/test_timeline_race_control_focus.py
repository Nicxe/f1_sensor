"""Race Control timeline identifies cars and laps without treating other numbers as cars."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.f1_sensor.analysis import Phase4AnalysisStore


@pytest.mark.parametrize(
    ("message", "drivers", "lap"),
    [
        (
            "CAR 18 (STR) TIME 1:24.540 DELETED - TRACK LIMITS AT TURN 1 LAP 14 16:28:55",
            [18],
            14,
        ),
        ("CAR 1 (VER) TIME 1:32.000 DELETED - TRACK LIMITS AT TURN 7 LAP 8", [1], 8),
        ("CARS 4 AND 81 INCIDENT AT TURN 3", [4, 81], None),
        ("TURN 1 LAP 14 NOTED", [], 14),
    ],
)
def test_race_control_event_association(message, drivers, lap):
    lap_store = SimpleNamespace(
        snapshot=Mock(return_value={"laps": []}), get_lap=Mock(return_value=None)
    )
    store = Phase4AnalysisStore(Mock(), lap_store, source_provider=lambda: "f1_live")
    store._on_race_control(
        {"Messages": [{"Message": message, "Utc": "2026-11-06T19:30:19Z"}]}
    )
    event = store.snapshot()["timeline"]["events"][-1]
    assert event["driver_numbers"] == drivers
    assert event["lap_number"] == lap


@pytest.mark.parametrize(
    ("item", "drivers", "lap"),
    [
        ({"Message": "CAR 18 LAP 14 DELETED", "RacingNumber": 18, "Lap": 15}, [18], 14),
        ({"Message": "CAR 18 LAP 14 DELETED", "RacingNumber": 4}, [], 14),
        ({"Message": "CAR 18 LAP 14 DELETED LAP 15", "RacingNumber": 18}, [18], None),
        ({"Message": "TURN 3 NOTED", "RacingNumber": 4}, [4], None),
        ({"Message": "CARS 1, 2, 3, 4 AND 5 NOTED"}, [], None),
        ({"Message": "CAR 18 LAP DELETED", "Lap": 15}, [18], None),
    ],
)
def test_race_control_handles_conflicting_and_incomplete_associations(
    item, drivers, lap
):
    lap_store = SimpleNamespace(
        snapshot=Mock(return_value={"laps": []}), get_lap=Mock(return_value=None)
    )
    store = Phase4AnalysisStore(Mock(), lap_store, source_provider=lambda: "f1_live")
    store._on_race_control(item)
    event = store.snapshot()["timeline"]["events"][-1]
    assert event["driver_numbers"] == drivers
    assert event["lap_number"] == lap


def test_penalty_context_does_not_treat_penalty_seconds_as_a_car():
    lap_store = SimpleNamespace(
        snapshot=Mock(return_value={"laps": []}), get_lap=Mock(return_value=None)
    )
    store = Phase4AnalysisStore(Mock(), lap_store, source_provider=lambda: "f1_live")
    store._on_race_control({"Message": "5 SECOND PENALTY FOR CAR 4", "Lap": 8})
    assert store._penalty_context == {4: {8}}
