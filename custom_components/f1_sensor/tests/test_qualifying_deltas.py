"""Qualifying split comparisons use coherent, corrected actual lap profiles."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from homeassistant.config_entries import ConfigEntryState
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import f1_sensor as f1
from custom_components.f1_sensor import LiveDriversCoordinator
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.push_laps import PushLapTracker
from custom_components.f1_sensor.sensor import F1DriverPositionsSensor
from custom_components.f1_sensor.signalr import LiveBus


def _tracker(kind: str = "Qualifying") -> PushLapTracker:
    tracker = PushLapTracker()
    tracker.update("SessionInfo", {"Type": kind, "Key": 1})
    tracker.update("TimingData", {"SessionPart": 1, "_f1_source_time": 0})
    return tracker


def _send(tracker: PushLapTracker, number: str, at: float, **line) -> dict:
    tracker.update("TimingData", {"_f1_source_time": at, "Lines": {number: line}})
    return tracker.delta_snapshot(number)


def _sector(index: int, value: str, **extra) -> dict:
    return {str(index): {"Value": value, "PersonalFastest": True, **extra}}


def _reference(tracker: PushLapTracker, number: str = "16") -> None:
    _send(tracker, number, 0, NumberOfLaps=1)
    _send(tracker, number, 25, Sectors=_sector(0, "25.000"))
    _send(tracker, number, 65, Sectors=_sector(1, "40.000"))
    _send(
        tracker,
        number,
        95,
        NumberOfLaps=2,
        Sectors=_sector(2, "30.000"),
        LastLapTime={"Value": "1:35.000"},
        BestLapTime={"Value": "1:35.000", "Lap": 1},
        BestLapTimes={"0": {"Value": "1:35.000", "Lap": 1}},
    )


def _s1(tracker: PushLapTracker) -> dict:
    _send(tracker, "63", 96, NumberOfLaps=1)
    return _send(tracker, "63", 120, Sectors=_sector(0, "24.900"))


def test_checkpoint_deltas_are_cumulative_and_final_result_precedes_new_best() -> None:
    tracker = _tracker()
    _reference(tracker)
    first = _s1(tracker)
    assert first["sector_1"] == -0.1
    assert first["latest_sector"] == 1
    assert first["sector_2"] is None
    second = _send(tracker, "63", 160, Sectors=_sector(1, "39.900"))
    assert second["sector_2"] == -0.2
    assert second["reference"] == {"racing_number": "16", "lap": 1, "time": 95.0}
    final = _send(
        tracker,
        "63",
        190,
        NumberOfLaps=2,
        Sectors=_sector(2, "30.000"),
        LastLapTime={"Value": "1:34.800"},
        BestLapTimes={"0": {"Value": "1:34.800", "Lap": 1}},
    )
    assert final["sector_3"] == -0.2
    assert final["latest_sector"] == 3
    assert final["lap"] == tracker.driver_snapshot("63")["lap"] == 1
    assert final["reference"] == first["reference"]
    tracker.update("Heartbeat", {"_f1_source_time": 197})
    assert tracker.delta_snapshot("63")["reference"] is None


def test_legal_new_leader_does_not_change_a_frozen_attempt_reference() -> None:
    tracker = _tracker()
    _reference(tracker)
    first = _s1(tracker)
    _send(tracker, "1", 130, BestLapTimes={"0": {"Value": "1:34.000", "Lap": 2}})
    second = _send(tracker, "63", 160, Sectors=_sector(1, "39.900"))
    assert second["reference"] == first["reference"]
    assert second["sector_2"] == -0.2


def test_unobserved_faster_official_best_blocks_slower_observed_reference() -> None:
    tracker = _tracker()
    _reference(tracker)
    _send(tracker, "1", 96, BestLapTimes={"0": {"Value": "1:34.000", "Lap": 2}})
    result = _s1(tracker)
    assert result["reference"] is None
    assert result["reason"] == "reference_sectors_missing"


@pytest.mark.parametrize("kind", ["Practice", "Race", "Sprint"])
def test_other_session_types_never_offer_comparisons(kind) -> None:
    tracker = _tracker(kind)
    result = _send(tracker, "63", 25, NumberOfLaps=1, Sectors=_sector(0, "25.000"))
    assert result["status"] == "unsupported"
    assert result["reference"] is None


@pytest.mark.parametrize("kind", ["Qualifying", "Sprint Qualifying", "Sprint Shootout"])
def test_qualifying_session_names_are_supported(kind) -> None:
    tracker = _tracker(kind)
    _reference(tracker)
    assert _s1(tracker)["status"] == "available"


def test_cold_snapshot_never_combines_cached_sectors_into_a_reference() -> None:
    tracker = _tracker()
    tracker.update(
        "TimingData",
        {
            "_f1_snapshot": True,
            "_f1_source_time": 95,
            "Lines": {
                "16": {
                    "NumberOfLaps": 2,
                    "Sectors": {
                        **_sector(0, "25.000"),
                        **_sector(1, "40.000"),
                        **_sector(2, "30.000"),
                    },
                    "BestLapTimes": {"0": {"Value": "1:35.000", "Lap": 1}},
                }
            },
        },
    )
    assert _s1(tracker)["reference"] is None


def test_previous_values_and_late_previous_sector_do_not_complete_reference() -> None:
    tracker = _tracker()
    _send(tracker, "16", 0, NumberOfLaps=1)
    _send(tracker, "16", 25, Sectors=_sector(0, "25.000"))
    _send(tracker, "16", 65, Sectors={"1": {"PreviousValue": "40.000"}})
    _send(
        tracker,
        "16",
        95,
        NumberOfLaps=2,
        Sectors=_sector(2, "30.000"),
        LastLapTime={"Value": "1:35.000"},
        BestLapTimes={"0": {"Value": "1:35.000", "Lap": 1}},
    )
    assert _s1(tracker)["reference"] is None


def test_new_qualifying_part_and_source_reset_discard_reference() -> None:
    tracker = _tracker()
    _reference(tracker)
    assert _s1(tracker)["reference"] is not None
    tracker.update("TimingData", {"SessionPart": 2, "_f1_source_time": 121})
    assert tracker.delta_snapshot("63")["reference"] is None
    result = _send(tracker, "63", 150, NumberOfLaps=3, Sectors=_sector(0, "24.000"))
    assert result["session_part"] == 2
    assert result["reference"] is None
    tracker.reset()
    assert tracker.delta_snapshot("63")["reference"] is None


@pytest.mark.parametrize(
    "correction",
    [
        {"BestLapTimes": {"0": {"Value": "1:36.000", "Lap": 2}}},
        {"BestLapTimes": {"0": {"Value": ""}}},
        {"BestLapTimes": {"0": None}},
        {"BestLapTime": {"Value": "1:36.000", "Lap": 2}},
        {"BestLapTime": {"Deleted": True}},
        {"BestLapTime": None},
    ],
)
def test_corrected_official_best_invalidates_frozen_reference(correction) -> None:
    tracker = _tracker()
    _reference(tracker)
    assert _s1(tracker)["status"] == "available"
    _send(tracker, "16", 121, **correction)
    result = tracker.delta_snapshot("63")
    assert result["status"] == "unavailable"
    assert result["reason"] == "reference_invalidated"
    assert result["sector_1"] is None


def test_race_control_deletion_and_reinstatement_update_frozen_reference() -> None:
    tracker = _tracker()
    _reference(tracker)
    assert _s1(tracker)["status"] == "available"
    tracker.update(
        "RaceControlMessages",
        {
            "Messages": {
                "1": {"Message": "CAR 16 (LEC) TIME 1:35.000 DELETED - TRACK LIMITS"}
            }
        },
    )
    assert tracker.delta_snapshot("63")["status"] == "unavailable"
    tracker.update(
        "RaceControlMessages",
        {"Messages": {"2": {"Message": "CAR 16 (LEC) TIME 1:35.000 REINSTATED"}}},
    )
    assert tracker.delta_snapshot("63")["sector_1"] == -0.1


def test_authoritative_restoration_revalidates_a_corrected_reference() -> None:
    tracker = _tracker()
    _reference(tracker)
    _s1(tracker)
    _send(tracker, "16", 121, BestLapTimes={"0": {"Value": "1:36.000", "Lap": 2}})
    assert tracker.delta_snapshot("63")["status"] == "unavailable"
    _send(tracker, "16", 122, BestLapTimes={"0": {"Value": "1:35.000", "Lap": 1}})
    assert tracker.delta_snapshot("63")["sector_1"] == -0.1


def test_missing_first_sector_and_old_frames_never_create_split_deltas() -> None:
    tracker = _tracker()
    _reference(tracker)
    _send(tracker, "63", 96, NumberOfLaps=1)
    _send(tracker, "63", 160, Sectors=_sector(1, "39.900"))
    assert tracker.delta_snapshot("63")["reference"] is None
    _send(tracker, "63", 120, Sectors=_sector(0, "24.900"))
    assert tracker.delta_snapshot("63")["reference"] is None


def test_late_s3_can_complete_a_reference_after_the_lap_time() -> None:
    tracker = _tracker()
    _send(tracker, "16", 0, NumberOfLaps=1)
    _send(tracker, "16", 25, Sectors=_sector(0, "25.000"))
    _send(tracker, "16", 65, Sectors=_sector(1, "40.000"))
    _send(
        tracker,
        "16",
        95,
        NumberOfLaps=2,
        LastLapTime={"Value": "1:35.000"},
        BestLapTimes={"0": {"Value": "1:35.000", "Lap": 1}},
    )
    _send(tracker, "16", 95.1, Sectors=_sector(2, "30.000"))
    assert _s1(tracker)["sector_1"] == -0.1


def test_final_lap_difference_does_not_wait_for_delayed_s3() -> None:
    tracker = _tracker()
    _reference(tracker)
    _s1(tracker)
    _send(tracker, "63", 160, Sectors=_sector(1, "39.900"))
    result = _send(
        tracker, "63", 190, NumberOfLaps=2, LastLapTime={"Value": "1:34.800"}
    )
    assert result["sector_3"] == -0.2
    assert result["latest_sector"] == 3


def test_direct_race_control_payload_invalidates_a_frozen_reference() -> None:
    tracker = _tracker()
    _reference(tracker)
    _s1(tracker)
    tracker.update(
        "RaceControlMessages",
        {"Message": "CAR 16 (LEC) TIME 1:35.000 DELETED - TRACK LIMITS"},
    )
    assert tracker.delta_snapshot("63")["status"] == "unavailable"


async def test_public_driver_comparison_and_race_control_share_the_delayed_bus(
    hass, monkeypatch
) -> None:
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", ConfigEntryState.SETUP_IN_PROGRESS)
    bus = LiveBus(hass, Mock())
    coordinator = LiveDriversCoordinator(
        hass, SimpleNamespace(data={}), bus=bus, config_entry=entry, delay_seconds=30
    )
    await coordinator.async_config_entry_first_refresh()
    sensor = F1DriverPositionsSensor(coordinator, "delta", entry.entry_id, "F1")
    sensor.hass = hass
    sensor._session_info_coordinator = SimpleNamespace(
        data={"Type": "Qualifying", "Name": "Qualifying"}
    )

    def comparison():
        sensor._update_from_coordinator()
        return next(
            driver["push_lap_delta"]
            for driver in sensor.extra_state_attributes["drivers"]
            if driver["racing_number"] == "63"
        )

    try:
        bus._dispatch("SessionInfo", {"Type": "Qualifying", "Key": 1})
        bus._dispatch("TimingData", {"SessionPart": 1, "_f1_source_time": 0})
        relay = SimpleNamespace(update=bus._dispatch, delta_snapshot=lambda _: {})
        _reference(relay)
        _s1(relay)
        assert not coordinator.data["drivers"]
        clock.value = 130.0
        f1._drain_delayed_ingest_queue(coordinator)
        assert comparison()["sector_1"] == -0.1
        assert comparison()["reference"]["racing_number"] == "16"
        bus._dispatch(
            "RaceControlMessages",
            {
                "Messages": {
                    "1": {
                        "Message": "CAR 16 (LEC) TIME 1:35.000 DELETED - TRACK LIMITS"
                    }
                }
            },
        )
        assert comparison()["status"] == "available"
        clock.value = 159.9
        f1._drain_delayed_ingest_queue(coordinator)
        assert comparison()["status"] == "available"
        clock.value = 160.0
        f1._drain_delayed_ingest_queue(coordinator)
        assert comparison()["status"] == "unavailable"
        assert comparison()["sector_1"] is None
    finally:
        await coordinator.async_close()
        await bus.async_close()
