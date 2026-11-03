"""Replay bounded real timing deltas without future lap or sector references."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

from custom_components.f1_sensor.push_laps import PushLapTracker

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "push_laps_recorded.json").read_text()
)["sessions"]


def _replay(
    session_key: str,
    *,
    until: float = float("inf"),
    tracker: PushLapTracker | None = None,
):
    """Yield each online result after sending only its original stream prefix."""
    session = _FIXTURE[session_key]
    origin = datetime.fromisoformat(session["source_utc_origin"])
    tracker = tracker or PushLapTracker()
    for event in session["events"]:
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
        yield event, tracker


@pytest.mark.parametrize(
    ("session", "number", "pit_exit", "pitout_cleared", "start_line"),
    [
        ("us_qualifying", "11", 812.911, 844.045, 927.106),
        ("singapore_sprint_qualifying", "11", 753.562, 787.137, 862.101),
        ("us_practice_1", "63", 871.223, 917.021, 1011.210),
    ],
)
def test_recorded_pitout_false_does_not_finish_outlap(
    session, number, pit_exit, pitout_cleared, start_line
):
    """The feed clears PitOut well before the first timed start-line crossing."""
    after_clear = []
    for event, tracker in _replay(session, until=start_line - 0.001):
        if event["at"] < pit_exit:
            continue
        result = tracker.driver_snapshot(number)
        assert result["active"] is False
        if event["at"] >= pitout_cleared:
            after_clear.append(result["state"])
    assert after_clear
    assert set(after_clear) == {"outlap"}


@pytest.mark.parametrize(
    ("session", "number", "start_line", "completed"),
    [
        ("us_qualifying", "11", 927.106, 1025.495),
        ("singapore_sprint_qualifying", "11", 862.101, 971.363),
        ("us_practice_1", "63", 1011.210, 1110.421),
    ],
)
def test_recorded_first_attempt_is_detected_before_lap_completion(
    session, number, start_line, completed
):
    """Real first attempts can qualify before any completed fast lap exists."""
    detections = []
    for event, tracker in _replay(session, until=completed - 0.001):
        if event["at"] < start_line:
            continue
        result = tracker.driver_snapshot(number)
        assert result["last_lap_time"] is None
        if result["active"]:
            detections.append(event["at"])
            assert result["state"] in {"probable_push", "push"}
            assert 0 < result["progress"] < 1
            assert result["lap"] == 2
            if event["at"] - start_line < 15:
                assert result["progress"] < 1 / 3
    assert detections
    assert 0 <= detections[0] - start_line <= 40


@pytest.mark.parametrize(
    ("session", "number", "start", "end"),
    [
        ("us_qualifying", "63", 1203.460, 1343.635),
        ("us_qualifying", "63", 1343.635, 1475.798),
        ("us_practice_1", "63", 1110.421, 1270.167),
    ],
)
def test_recorded_slow_laps_do_not_keep_the_spotlight(session, number, start, end):
    """Sustained slow pace is rejected before the next lap is known."""
    observations = []
    for event, tracker in _replay(session, until=end - 0.001):
        if event["at"] < start + 15:
            continue
        observations.append(tracker.driver_snapshot(number))
    assert observations
    assert all(result["active"] is False for result in observations)


def test_recorded_push_after_two_slow_laps_is_detected_online():
    """A driver may prepare for two laps before trying another fast lap."""
    detections = []
    for event, tracker in _replay("us_qualifying", until=1571.597):
        if event["at"] < 1475.798:
            continue
        result = tracker.driver_snapshot("63")
        if result["active"]:
            detections.append(event["at"])
            # New S1 observations start at 00:24:40.737. Late previous-lap
            # S3 colours at 00:24:35.802 cannot launch the next attempt.
            assert event["at"] >= 1480.737
            if event["at"] < 1490.798:
                assert result["progress"] < 1 / 3
    assert detections
    assert detections[0] - 1475.798 <= 30


def test_recorded_progress_can_rank_concurrent_attempts():
    """The later sector should precede an earlier sector in a timing display."""
    observations = list(_replay("us_qualifying", until=1135))
    tracker = observations[-1][1]
    hamilton = tracker.driver_snapshot("44")
    russell = tracker.driver_snapshot("63")
    assert hamilton["active"] is True
    assert russell["active"] is True
    assert 0 < russell["progress"] < hamilton["progress"] < 1


def test_recorded_red_flag_and_aborted_session_clear_attempts():
    """All-clear track messages cannot restart an aborted session's focus."""
    observations = []
    for event, tracker in _replay("singapore_sprint_qualifying", until=1710.124):
        if event["at"] < 1101.510:
            continue
        observations.extend(tracker.driver_snapshot(number) for number in ("11", "63"))
    assert observations
    assert all(result["active"] is False for result in observations)


def test_recorded_qualifying_part_change_clears_lap_progress():
    """The next qualifying part must not inherit a previous attempt display."""
    observed_boundary = False
    for event, tracker in _replay("us_qualifying"):
        if event["payload"].get("SessionPart") != 2:
            continue
        observed_boundary = True
        for number in _FIXTURE["us_qualifying"]["drivers"]:
            result = tracker.driver_snapshot(number)
            assert result["active"] is False
            assert result["progress"] is None
    assert observed_boundary


def test_recorded_cold_outlap_seek_waits_for_current_lap_evidence():
    """A merged checkpoint cannot turn an unknown outlap into a push attempt."""
    preceding = list(_replay("us_qualifying", until=990))
    tracker = preceding[-1][1]
    tracker.reset()
    assert tracker.driver_snapshot("11")["active"] is False

    session = _FIXTURE["us_qualifying_outlap_seek"]
    checkpoint = session["events"][3]["payload"]["Lines"]["44"]
    assert checkpoint["NumberOfLaps"] == 1
    assert checkpoint["InPit"] is False
    assert checkpoint["PitOut"] is False
    assert checkpoint["Sectors"]["0"]["Value"] == ""

    fresh_improving_segments = 0
    for event, seek_tracker in _replay("us_qualifying_outlap_seek", tracker=tracker):
        result = seek_tracker.driver_snapshot("44")
        assert result["active"] is False
        assert result["progress"] is None
        if event["snapshot"]:
            continue
        sectors = event["payload"].get("Lines", {}).get("44", {}).get("Sectors", {})
        fresh_improving_segments += sum(
            segment.get("Status") in {2049, 2051}
            for sector in sectors.values()
            for segment in sector.get("Segments", {}).values()
        )
    assert fresh_improving_segments >= 2
