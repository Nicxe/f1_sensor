"""A deletion must identify a lap, not merely a nearest recorded duration."""

import pytest

from custom_components.f1_sensor.analysis import Phase4AnalysisStore
from custom_components.f1_sensor.history import LapAnalysisStore
from custom_components.f1_sensor.tests.test_history_behavior_matrix import _timing_lap
from custom_components.f1_sensor.tests.test_phase_4_analysis import _Bus


@pytest.mark.parametrize(
    ("message", "times", "expected_lap"),
    [
        ("CAR 4 LAP TIME 1:31.000 DELETED", ["1:30.000"], None),
        ("CAR 4 LAP TIME 1:30.000 DELETED", ["1:30.000", "1:30.000"], None),
        (
            "CAR 4 LAP TIME 1:30.000 DELETED - TRACK LIMITS LAP 2",
            ["1:30.000", "1:30.000"],
            2,
        ),
        ("CAR 99 LAP TIME 1:30.000 DELETED", ["1:30.000"], None),
        ("CAR 4 LAP TIME DELETED", ["1:30.000"], None),
        ("CAR 4 LAP TIME 1:30.000 DELETED", ["1:29.999", "1:30.000"], 2),
    ],
)
async def test_lap_control_requires_unique_duration_or_explicit_lap(
    message, times, expected_lap
):
    bus = _Bus()
    laps = LapAnalysisStore(bus, source_provider=lambda: "f1_live")
    try:
        for lap, duration in enumerate(times, 1):
            bus.emit("TimingData", _timing_lap(lap=lap, time=duration))
        bus.emit("RaceControlMessages", {"Messages": [{"Message": message}]})
        deleted = [
            item["lap_number"]
            for item in laps.snapshot()["laps"]
            if item["quality"]["deleted"]
        ]
        assert deleted == ([] if expected_lap is None else [expected_lap])
        assert laps._matching_lap(4, None) is None
    finally:
        await laps.async_close()


@pytest.mark.parametrize("provider", ["f1_live", "replay"])
@pytest.mark.parametrize(
    "delta",
    [
        {"Key": "A"},
        {"Name": "Race"},
        {"Meeting": {"Key": "10"}, "ArchiveStatus": {"Status": "Complete"}},
    ],
)
async def test_sparse_session_metadata_preserves_lap_control_and_strategy(
    provider, delta
):
    bus = _Bus()
    laps = LapAnalysisStore(bus, source_provider=lambda: provider)
    analysis = Phase4AnalysisStore(bus, laps, source_provider=lambda: provider)
    try:
        bus.emit(
            "SessionInfo",
            {"Key": "A", "Name": "Race", "Type": "Race", "Meeting": {"Key": 10}},
        )
        bus.emit("TrackStatus", {"Status": "1"})
        bus.emit("TimingData", _timing_lap())
        bus.emit("RaceControlMessages", {"Message": "CAR 4 LAP TIME 1:30.000 DELETED"})
        expected = laps.get_lap(4, 1)
        strategy = dict(analysis._strategy_laps)
        bus.emit("SessionInfo", delta)
        assert laps.get_lap(4, 1) == expected
        assert analysis._strategy_laps == strategy
        assert laps._effective_session_type() == "Race"
        bus.emit(
            "SessionInfo", {"Key": "B", "Name": "Qualifying", "Type": "Qualifying"}
        )
        assert laps.snapshot()["laps"] == []
        assert analysis._strategy_laps == {}
    finally:
        await analysis.async_close()
        await laps.async_close()


async def test_rewind_of_same_session_drops_lap_control_and_source_coverage():
    bus = _Bus()
    laps = LapAnalysisStore(bus, source_provider=lambda: "replay")
    try:
        session = {"Key": "A", "Name": "Race", "Type": "Race"}
        bus.emit("SessionInfo", session)
        bus.emit("TrackStatus", {"Status": "1"})
        bus.emit("TimingData", _timing_lap())
        bus.emit("RaceControlMessages", {"Message": "CAR 4 LAP TIME 1:30.000 DELETED"})
        laps.reset_for_replay()
        bus.emit("SessionInfo", session)
        bus.emit("TimingData", _timing_lap())
        quality = laps.get_lap(4, 1)["quality"]
        assert quality["deleted"] is None
        assert quality["deletion_status"] == "unknown"
        assert quality["coverage"] == {
            "track_status": "not_observed",
            "race_control": "not_observed",
        }
    finally:
        await laps.async_close()


async def test_old_lap_correction_reaches_strategy_and_reinstatement_is_idempotent():
    bus = _Bus()
    laps = LapAnalysisStore(bus, source_provider=lambda: "replay")
    analysis = Phase4AnalysisStore(bus, laps, source_provider=lambda: "replay")
    try:
        bus.emit("SessionInfo", {"Key": "A", "Type": "Race", "Name": "Race"})
        bus.emit("TrackStatus", {"Status": "1"})
        bus.emit("TimingData", _timing_lap(lap=1))
        bus.emit("TimingData", _timing_lap(lap=2, time="1:31.000"))
        deletion = {"Message": "CAR 4 LAP TIME 1:30.000 DELETED"}
        bus.emit("RaceControlMessages", deletion)
        assert (
            analysis._strategy_laps[(4, 1)]["quality"]["pace_suitability"] == "excluded"
        )
        before = laps.diagnostics()["updates"]
        bus.emit("RaceControlMessages", deletion)
        assert laps.diagnostics()["updates"] == before
        bus.emit(
            "RaceControlMessages", {"Message": "CAR 4 LAP TIME 1:30.000 REINSTATED"}
        )
        assert (
            analysis._strategy_laps[(4, 1)]["quality"]["pace_suitability"] == "eligible"
        )
        assert laps.get_lap(4, 1)["lap_duration"] == 90
        bus.emit("RaceControlMessages", deletion)
        assert laps.get_lap(4, 1)["quality"]["deleted"] is True
        bus.emit("SessionInfo", {"Key": "B", "Type": "Race", "Name": "Race"})
        bus.emit("RaceControlMessages", deletion)
        assert laps.snapshot()["laps"] == []
    finally:
        await analysis.async_close()
        await laps.async_close()


@pytest.mark.parametrize("reinstated", [False, True])
async def test_late_timing_correction_preserves_explicit_lap_control(reinstated):
    bus = _Bus()
    laps = LapAnalysisStore(bus, source_provider=lambda: "replay")
    try:
        bus.emit("TrackStatus", {"Status": "1"})
        bus.emit("TimingData", _timing_lap())
        bus.emit("RaceControlMessages", {"Message": "CAR 4 LAP TIME 1:30.000 DELETED"})
        if reinstated:
            bus.emit(
                "RaceControlMessages", {"Message": "CAR 4 LAP TIME 1:30.000 REINSTATED"}
            )
        bus.emit(
            "TimingData",
            {
                "Lines": {
                    "4": {
                        "LastLapTime": {"Value": "1:30.100"},
                        "Sectors": {"2": {"Value": "30.100"}},
                    }
                }
            },
        )
        lap = laps.get_lap(4, 1)
        assert lap["lap_duration"] == 90.1
        assert lap["quality"]["deleted"] is not reinstated
        assert lap["quality"]["deletion_status"] == (
            "reinstated" if reinstated else "deleted"
        )
        assert lap["quality"]["timing_integrity"] == "consistent"
        assert lap["quality"]["pace_suitability"] == (
            "eligible" if reinstated else "excluded"
        )
    finally:
        await laps.async_close()


async def test_unresolved_lap_control_duplicates_are_counted_once_but_can_later_resolve():
    bus = _Bus()
    laps = LapAnalysisStore(bus, source_provider=lambda: "replay")
    try:
        bus.emit("TimingData", _timing_lap())
        deletion = {
            "Message": "CAR 4 LAP TIME 1:31.000 DELETED",
            "Utc": "2026-11-06T12:00:00Z",
        }
        bus.emit("RaceControlMessages", deletion)
        before = laps.diagnostics()
        bus.emit("RaceControlMessages", dict(deletion))
        assert laps.diagnostics() == before
        assert before["unresolved_lap_controls"] == 1
        bus.emit("TimingData", _timing_lap(lap=2, time="1:31.000"))
        bus.emit("RaceControlMessages", dict(deletion))
        assert laps.get_lap(4, 2)["quality"]["deleted"] is True
        assert laps.diagnostics()["unresolved_lap_controls"] == 1
        laps.reset_for_replay()
        bus.emit("RaceControlMessages", dict(deletion))
        assert laps.diagnostics()["unresolved_lap_controls"] == 1
    finally:
        await laps.async_close()
