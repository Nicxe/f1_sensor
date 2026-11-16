"""Timeline events keep unambiguous times without changing their raw identities."""

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path

import pytest

from custom_components.f1_sensor.analysis import Phase4AnalysisStore
from custom_components.f1_sensor.history import LapAnalysisStore
from custom_components.f1_sensor.tests.test_phase_4_analysis import _Bus


@pytest.fixture
async def timeline_store():
    """Exercise registered stream callbacks and their resulting event contract."""
    bus = _Bus()
    laps = LapAnalysisStore(bus, source_provider=lambda: "f1_live")
    analysis = Phase4AnalysisStore(bus, laps, source_provider=lambda: "f1_live")
    yield bus, analysis
    await analysis.async_close()
    await laps.async_close()
    assert not any(bus.callbacks.values())


def test_recorded_fp2_times_preserve_chronology_identity_and_repeated_snapshots(
    timeline_store,
):
    case = json.loads(
        (Path(__file__).parent / "fixtures/timeline_event_times.json").read_text()
    )
    bus, analysis = timeline_store
    bus.emit("SessionInfo", case["session"])
    bus.emit("TeamRadio", case["radio"])
    bus.emit("RaceControlMessages", case["race_control"])
    events = analysis.snapshot()["timeline"]["events"]
    by_id = {event["event_id"]: event for event in events}
    expected_ids = case["existing_event_ids"]
    race_control = by_id[expected_ids["race_control"]]
    radio = by_id[expected_ids["radio_23"]]

    assert race_control["occurred_at"] == "2026-11-06T19:30:19Z"
    assert radio["occurred_at"] == "2026-11-06T19:29:53.762Z"
    assert by_id[expected_ids["radio_30"]]["occurred_at"] == "2026-11-06T19:29:53.53Z"
    assert (
        datetime.fromisoformat(race_control["occurred_at"])
        - datetime.fromisoformat(radio["occurred_at"])
    ).total_seconds() == 25.238
    assert race_control["lap_number"] == 14
    assert race_control["driver_numbers"] == [18]

    bus.emit("TeamRadio", deepcopy(case["radio"]))
    bus.emit("RaceControlMessages", deepcopy(case["race_control"]))
    assert analysis.snapshot()["timeline"]["events"] == events
    assert all(event["revision"] == 1 for event in events)
    assert case["race_control"]["Messages"]["8"]["Utc"] == "2026-11-06T19:30:19"


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"Utc": "2025-07-06T14:05:48"}, "2025-07-06T14:05:48Z"),
        ({"utc": "2025-07-06T14:05:48"}, "2025-07-06T14:05:48Z"),
        ({"Utc": "2025-07-06T14:05:48Z"}, "2025-07-06T14:05:48Z"),
        ({"Utc": "2025-07-06T14:05:48z"}, "2025-07-06T14:05:48Z"),
        ({"Utc": "2025-07-06T16:05:48+02:00"}, "2025-07-06T16:05:48+02:00"),
        ({"Utc": "2025-07-06T09:05:48-05:00"}, "2025-07-06T09:05:48-05:00"),
        ({"Utc": "2026-11-06T19:19:44.7428222"}, "2026-11-06T19:19:44.7428222Z"),
        ({"Utc": "2026-11-06T19:19:44.7428222Z"}, "2026-11-06T19:19:44.7428222Z"),
        ({"Timestamp": "2025-07-06T14:05:48Z"}, "2025-07-06T14:05:48Z"),
        ({"timestamp": "2025-07-06T16:05:48+02:00"}, "2025-07-06T16:05:48+02:00"),
        ({"Date": "2025-07-06T14:05:48Z"}, "2025-07-06T14:05:48Z"),
        ({"Utc": " ", "utc": "2025-07-06T14:05:48"}, "2025-07-06T14:05:48Z"),
        ({"Utc": "2024-02-29T00:00:00"}, "2024-02-29T00:00:00Z"),
        ({"Utc": "1970-01-01T00:00:00"}, "1970-01-01T00:00:00Z"),
        ({"Timestamp": "2025-07-06T14:05:48"}, None),
        ({"timestamp": "2025-07-06T14:05:48"}, None),
        ({"Date": "2025-07-06T14:05:48"}, None),
        ({"Date": "2025-07-06"}, None),
        ({"Utc": "2025-07-06"}, None),
        ({"Utc": "2025-07-06T14:05"}, None),
        ({"Utc": "2025-07-06 14:05:48"}, None),
        ({"Utc": "2025-02-29T14:05:48"}, None),
        ({"Utc": "2025-02-30T14:05:48Z"}, None),
        ({"Utc": "2025-07-06T24:00:00Z"}, None),
        ({"Utc": "2025-07-06T14:05:60Z"}, None),
        ({"Utc": "2025-07-06T14:05:48+01:60"}, None),
        ({"Utc": "2025-07-06T14:05:48+24:00"}, None),
        ({"Utc": "0000-01-01T00:00:00Z"}, None),
        ({"Utc": "invalid"}, None),
        ({"Utc": 0}, None),
        ({"Utc": "invalid", "Timestamp": "2025-07-06T14:05:48Z"}, None),
        ({"Timestamp": "2025-07-06T14:05:48", "Date": "2025-07-06T14:05:48Z"}, None),
        ({}, None),
    ],
)
def test_event_times_require_known_utc_or_explicit_offset(
    timeline_store, fields, expected
):
    bus, analysis = timeline_store
    bus.emit("RaceControlMessages", {"Messages": {"1": {"Message": "CHECK", **fields}}})
    event = analysis.snapshot()["timeline"]["events"][-1]
    assert event["occurred_at"] == expected


def test_correction_preserves_event_identity_and_advances_revision_once(timeline_store):
    bus, analysis = timeline_store
    message = {
        "Utc": "2025-07-06T14:05:48",
        "Lap": 2,
        "Category": "SafetyCar",
        "Status": "DEPLOYED",
        "Mode": "VIRTUAL SAFETY CAR",
        "Message": "VIRTUAL SAFETY CAR DEPLOYED",
    }
    bus.emit("RaceControlMessages", {"Messages": {"67": message}})
    original = analysis.snapshot()["timeline"]["events"][-1]
    corrected = {**message, "Lap": 3}
    bus.emit("RaceControlMessages", {"Messages": {"67": corrected}})
    events = analysis.snapshot()["timeline"]["events"]
    assert len(events) == 1
    assert events[0]["event_id"] == original["event_id"]
    assert events[0]["sequence"] == original["sequence"]
    assert events[0]["revision"] == 2
    assert events[0]["lap_number"] == 3
    assert events[0]["occurred_at"] == "2025-07-06T14:05:48Z"
    bus.emit("RaceControlMessages", {"Messages": {"67": corrected}})
    assert analysis.snapshot()["timeline"]["events"] == events


def test_streams_without_event_time_do_not_borrow_observation_or_session_time(
    timeline_store,
):
    bus, analysis = timeline_store
    bus.emit(
        "SessionInfo",
        {"Key": "race", "Name": "Race", "StartDate": "2026-11-06T19:00:00"},
    )
    bus.emit("SessionStatus", {"Status": "Started"})
    bus.emit("TrackStatus", {"Status": "6", "Message": "VSCDeployed"})
    bus.emit("WeatherData", {"Rainfall": "1"})
    events = analysis.snapshot()["timeline"]["events"]
    assert {event["category"] for event in events} == {
        "session",
        "track_status",
        "weather",
    }
    assert all(event["occurred_at"] is None for event in events)
