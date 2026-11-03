"""Validate qualifying checkpoint comparisons against original ordered timing."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

from custom_components.f1_sensor.push_laps import PushLapTracker

_SESSIONS = json.loads(
    (Path(__file__).parent / "fixtures" / "push_lap_deltas_recorded.json").read_text()
)["sessions"]


def _replay(session: str, *, until: float) -> PushLapTracker:
    """Use only the original stream prefix available at each checkpoint."""
    recording = _SESSIONS[session]
    origin = datetime.fromisoformat(recording["source_utc_origin"])
    tracker = PushLapTracker()
    for event in recording["events"]:
        if event["at"] > until:
            break
        payload = deepcopy(event["payload"])
        payload["_f1_source_time"] = event["at"]
        payload["_f1_source_utc"] = (
            origin + timedelta(seconds=event["at"])
        ).isoformat()
        if event["snapshot"]:
            payload["_f1_snapshot"] = True
        tracker.update(event["stream"], payload)
    return tracker


@pytest.mark.parametrize(
    ("session", "number", "reference", "checkpoints", "expected"),
    [
        (
            "us_qualifying",
            "63",
            {"racing_number": "16", "lap": 2, "time": 95.200},
            (1132.924, 1171.097, 1203.460),
            (-0.008, 0.357, 1.041),
        ),
        (
            "us_qualifying",
            "1",
            {"racing_number": "16", "lap": 2, "time": 95.200},
            (1837.888, 1875.477, 1907.414),
            (-0.154, -0.350, -0.171),
        ),
        (
            "singapore_sprint_qualifying",
            "63",
            {"racing_number": "44", "lap": 2, "time": 93.748},
            (1867.434, 1907.188, 1933.663),
            (0.166, 0.384, 0.583),
        ),
        (
            "singapore_sprint_qualifying",
            "3",
            {"racing_number": "44", "lap": 2, "time": 93.748},
            (2062.079, 2101.320, 2127.687),
            (-0.002, -0.268, -0.271),
        ),
        (
            "singapore_sprint_qualifying",
            "63",
            {"racing_number": "44", "lap": 2, "time": 93.748},
            (2086.661, 2126.093, 2161.316),
            (-0.227, -0.374, -0.175),
        ),
    ],
    ids=[
        "qualifying-ahead-then-behind",
        "qualifying-new-best-keeps-negative-final",
        "sprint-qualifying-reference-not-classified-push",
        "sprint-qualifying-new-best-keeps-negative-final",
        "sprint-qualifying-reference-frozen-across-new-leader",
    ],
)
def test_recorded_cumulative_push_lap_comparisons(
    session, number, reference, checkpoints, expected
) -> None:
    """Each split compares the same real fastest lap, never future best sectors."""
    for sector, (at, value) in enumerate(zip(checkpoints, expected, strict=True), 1):
        tracker = _replay(session, until=at)
        effort = tracker.driver_snapshot(number)
        result = tracker.delta_snapshot(number)
        assert effort["active"] or effort["state"] == "completed"
        assert result["status"] == "available"
        assert result["lap"] == effort["lap"]
        assert result["session_part"] == 1
        assert result["reference"]["racing_number"] == reference["racing_number"]
        assert result["reference"]["lap"] == reference["lap"]
        assert result["reference"]["time"] == pytest.approx(reference["time"])
        assert result["latest_sector"] == sector
        for index in range(1, 4):
            if index <= sector:
                assert result[f"sector_{index}"] == pytest.approx(expected[index - 1])
            else:
                assert result[f"sector_{index}"] is None
        assert result[f"sector_{sector}"] == pytest.approx(value)


def test_recorded_first_laps_do_not_use_future_reference_times() -> None:
    """The first official timed lap is not available before its own finish."""
    tracker = _replay("us_qualifying", until=1021.570)
    for number in _SESSIONS["us_qualifying"]["drivers"]:
        result = tracker.delta_snapshot(number)
        assert result["status"] != "available"
        assert result["reference"] is None
        assert all(result[f"sector_{index}"] is None for index in range(1, 4))


@pytest.mark.parametrize(
    ("session", "boundary"),
    [("us_qualifying", 2247.781), ("singapore_sprint_qualifying", 3125.438)],
)
def test_recorded_qualifying_part_changes_discard_previous_references(
    session, boundary
) -> None:
    """Q2/SQ2 cannot inherit the completed Q1/SQ1 comparison or benchmark."""
    tracker = _replay(session, until=boundary)
    for number in _SESSIONS[session]["drivers"]:
        result = tracker.delta_snapshot(number)
        assert result["session_part"] == 2
        assert result["status"] != "available"
        assert result["reference"] is None
        assert result["latest_sector"] is None
        assert all(result[f"sector_{index}"] is None for index in range(1, 4))


def test_recorded_comparison_waits_for_actual_next_sector() -> None:
    """A passed minisector cannot reveal the next complete-sector delta early."""
    tracker = _replay("us_qualifying", until=1171.096)
    result = tracker.delta_snapshot("63")
    assert result["status"] == "available"
    assert result["sector_1"] == pytest.approx(-0.008)
    assert result["latest_sector"] == 1
    assert result["sector_2"] is None
    assert result["sector_3"] is None


def test_recorded_completed_comparison_expires_with_push_result() -> None:
    """The six-second source-time result hold also owns the final comparison."""
    tracker = _replay("us_qualifying", until=1215.000)
    assert tracker.driver_snapshot("63")["state"] != "completed"
    result = tracker.delta_snapshot("63")
    assert result["status"] != "available"
    assert result["reference"] is None
    assert all(result[f"sector_{index}"] is None for index in range(1, 4))
