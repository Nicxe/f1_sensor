"""Publish bounded lap inference only when its public inputs have changed."""

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.f1_sensor import LiveDriversCoordinator
from custom_components.f1_sensor.push_laps import PushLapTracker


def _coordinator(hass, kind="Race"):
    coordinator = LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    coordinator._push_laps.update("SessionInfo", {"Key": 1, "Type": kind})
    coordinator._merge_driverlist(
        {str(number): {"RacingNumber": str(number)} for number in range(1, 23)}
    )
    coordinator._publish_push_laps()
    return coordinator


def _timing(coordinator, at, number="1", **line):
    coordinator._merge_timingdata({"_f1_source_time": at, "Lines": {number: line}})


def _assert_projection(coordinator):
    for number, driver in coordinator._state["drivers"].items():
        assert driver["push_lap"] == coordinator._push_laps.driver_snapshot(number)
        assert driver["push_lap_delta"] == coordinator._push_laps.delta_snapshot(number)


async def test_race_deltas_reuse_defaults_and_initialize_new_drivers(hass):
    """Unsupported race timing must not rebuild 22 empty projections per frame."""
    coordinator = _coordinator(hass)
    tracker = coordinator._push_laps
    tracker.delta_snapshot = Mock(wraps=tracker.delta_snapshot)
    before = deepcopy(coordinator._state["drivers"]["1"]["push_lap_delta"])

    for at in range(100):
        _timing(coordinator, at, GapToLeader=str(at))

    assert tracker.delta_snapshot.call_count == 0
    assert coordinator._state["drivers"]["1"]["push_lap_delta"] == before
    assert (
        coordinator._state["drivers"]["1"]["push_lap"]
        is not coordinator._state["drivers"]["2"]["push_lap"]
    )
    _timing(coordinator, 101, number="63", NumberOfLaps=1)
    assert tracker.delta_snapshot.call_count == 1
    _assert_projection(coordinator)
    await coordinator.async_close()


@pytest.mark.parametrize("kind", ["Practice", "Qualifying"])
async def test_only_changed_driver_rebuilds_a_supported_projection(hass, kind):
    coordinator = _coordinator(hass, kind)
    _timing(coordinator, 0, NumberOfLaps=1)
    tracker = coordinator._push_laps
    tracker.delta_snapshot = Mock(wraps=tracker.delta_snapshot)

    _timing(
        coordinator,
        25,
        Sectors={"0": {"Value": "25.000", "PersonalFastest": True}},
    )

    assert [call.args[0] for call in tracker.delta_snapshot.call_args_list] == ["1"]
    assert coordinator._state["drivers"]["1"]["push_lap"]["active"] is True
    tracker.delta_snapshot.reset_mock()
    coordinator._on_push_lap_clock({"_f1_source_time": 26})
    assert tracker.delta_snapshot.call_count == 0
    _assert_projection(coordinator)
    await coordinator.async_close()


async def test_clock_expiry_and_resets_refresh_cached_publication(hass):
    coordinator = _coordinator(hass, "Qualifying")
    _timing(coordinator, 0, NumberOfLaps=1)
    _timing(
        coordinator,
        25,
        Sectors={"0": {"Value": "25.000", "PersonalFastest": True}},
    )
    coordinator._on_push_lap_clock({"_f1_source_time": 71})
    assert coordinator._state["drivers"]["1"]["push_lap"]["reason"] == "stale_timing"
    _assert_projection(coordinator)

    _timing(coordinator, 72, NumberOfLaps=2, LastLapTime={"Value": "1:12.000"})
    assert coordinator._state["drivers"]["1"]["push_lap"]["state"] == "completed"
    coordinator._on_push_lap_clock({"_f1_source_time": 78})
    assert coordinator._state["drivers"]["1"]["push_lap"]["state"] != "completed"
    _assert_projection(coordinator)

    for key, kind in ((2, "Race"), (3, "Practice"), (4, "Qualifying")):
        coordinator._on_sessioninfo({"Key": key, "Type": kind})
        _timing(coordinator, 0, NumberOfLaps=1)
        _assert_projection(coordinator)
        assert coordinator._state["drivers"]["1"]["push_lap"]["active"] is False
    coordinator._push_laps.reset()
    coordinator._publish_push_laps()
    _assert_projection(coordinator)
    await coordinator.async_close()


async def test_frozen_reference_deletion_refreshes_another_driver(hass):
    """A reference can change without a new TimingData row for its consumer."""
    coordinator = _coordinator(hass, "Qualifying")
    coordinator._merge_timingdata({"SessionPart": 1, "_f1_source_time": 0})
    _timing(coordinator, 0, number="16", NumberOfLaps=1)
    for at, index, value in ((25, 0, "25.000"), (65, 1, "40.000")):
        _timing(
            coordinator,
            at,
            number="16",
            Sectors={str(index): {"Value": value, "PersonalFastest": True}},
        )
    _timing(
        coordinator,
        95,
        number="16",
        NumberOfLaps=2,
        Sectors={"2": {"Value": "30.000", "PersonalFastest": True}},
        LastLapTime={"Value": "1:35.000"},
        BestLapTime={"Value": "1:35.000", "Lap": 1},
        BestLapTimes={"0": {"Value": "1:35.000", "Lap": 1}},
    )
    _timing(coordinator, 96, NumberOfLaps=1)
    _timing(
        coordinator,
        120,
        Sectors={"0": {"Value": "24.900", "PersonalFastest": True}},
    )
    driver = coordinator._state["drivers"]["1"]
    assert driver["push_lap_delta"]["status"] == "available"
    original = deepcopy(driver["push_lap_delta"])

    for at, action, expected in (
        (121, "DELETED", "unavailable"),
        (122, "REINSTATED", "available"),
    ):
        coordinator._on_push_lap_race_control(
            {
                "_f1_source_time": at,
                "Messages": {"0": {"Message": f"CAR 16 (LEC) TIME 1:35.000 {action}"}},
            }
        )
        assert driver["push_lap_delta"]["status"] == expected
        _assert_projection(coordinator)
    assert driver["push_lap_delta"] == original

    replacement = deepcopy(driver)
    replacement.pop("push_lap")
    replacement.pop("push_lap_delta")
    coordinator._state["drivers"]["1"] = replacement
    coordinator._publish_push_laps()
    assert replacement["push_lap_delta"] == original
    assert replacement["push_lap_delta"] is not driver["push_lap_delta"]
    assert (
        replacement["push_lap_delta"]["reference"]
        is not driver["push_lap_delta"]["reference"]
    )
    await coordinator.async_close()


@pytest.mark.parametrize(
    ("fixture_file", "session"),
    [
        ("push_laps_recorded.json", "us_qualifying"),
        ("push_laps_recorded.json", "singapore_sprint_qualifying"),
        ("push_laps_recorded.json", "us_practice_1"),
        ("push_laps_recorded.json", "us_qualifying_outlap_seek"),
        ("push_lap_deltas_recorded.json", "us_qualifying"),
        ("push_lap_deltas_recorded.json", "singapore_sprint_qualifying"),
    ],
)
async def test_cached_publication_matches_every_original_recorded_event(
    hass, fixture_file, session
):
    """Keep the uncached contract at each actual checkpoint and part transition."""
    recording = json.loads(
        (Path(__file__).parent / "fixtures" / fixture_file).read_text()
    )["sessions"][session]
    origin = datetime.fromisoformat(recording["source_utc_origin"])
    coordinator = LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    coordinator._merge_driverlist(
        {number: {"RacingNumber": number} for number in recording["drivers"]}
    )
    expected = PushLapTracker()
    for event in recording["events"]:
        payload = deepcopy(event["payload"])
        payload["_f1_source_time"] = event["at"]
        payload["_f1_source_utc"] = (
            origin + timedelta(seconds=event["at"])
        ).isoformat()
        if event["snapshot"]:
            payload["_f1_snapshot"] = True
        stream = event["stream"]
        expected.update(stream, payload)
        if stream == "TimingData":
            coordinator._merge_timingdata(payload)
        else:
            coordinator._push_laps.update(stream, payload)
            coordinator._publish_push_laps()
        for number, driver in coordinator._state["drivers"].items():
            assert driver["push_lap"] == expected.driver_snapshot(number)
            assert driver["push_lap_delta"] == expected.delta_snapshot(number)
        assert coordinator._state["push_laps_status"] == expected.status
    await coordinator.async_close()
