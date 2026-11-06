"""Integrity, source coverage and pace suitability have separate meanings."""

import pytest

from custom_components.f1_sensor.models.history import assess_lap_quality


@pytest.mark.parametrize(
    ("changes", "integrity", "suitability", "deletion"),
    [
        ({}, "consistent", "eligible", "not_reported"),
        ({"track_status": None}, "consistent", "uncertain", "not_reported"),
        ({"race_control_observed": False}, "consistent", "eligible", "unknown"),
        ({"deleted": True}, "consistent", "excluded", "deleted"),
        ({"deleted": True, "reinstated": True}, "consistent", "eligible", "reinstated"),
        ({"is_pit_in_lap": True}, "consistent", "excluded", "not_reported"),
        ({"track_status": "4"}, "consistent", "excluded", "not_reported"),
        ({"lap_duration": 0}, "invalid", "uncertain", "not_reported"),
        ({"lap_duration": -90}, "invalid", "uncertain", "not_reported"),
        ({"lap_duration": float("nan")}, "incomplete", "uncertain", "not_reported"),
        ({"lap_duration": float("inf")}, "incomplete", "uncertain", "not_reported"),
        (
            {"sector_durations": [30, 30, None]},
            "incomplete",
            "uncertain",
            "not_reported",
        ),
        (
            {"sector_durations": [30, 30, 29.996]},
            "inconsistent",
            "uncertain",
            "not_reported",
        ),
        (
            {"sector_durations": [30, 30, 29.998]},
            "consistent",
            "eligible",
            "not_reported",
        ),
        (
            {"sector_durations": [30, 30, 30.004]},
            "inconsistent",
            "uncertain",
            "not_reported",
        ),
        (
            {"sector_durations": [30, 30, 30.002]},
            "consistent",
            "eligible",
            "not_reported",
        ),
        ({"inferred": True}, "consistent", "uncertain", "not_reported"),
    ],
)
def test_lap_quality_dimensions(changes, integrity, suitability, deletion):
    values = {
        "lap_duration": 90,
        "sector_durations": [30, 30, 30],
        "track_status": "1",
        "race_control_observed": True,
    }
    quality = assess_lap_quality(**(values | changes)).as_dict()
    assert quality["timing_integrity"] == integrity
    assert quality["pace_suitability"] == suitability
    assert quality["deletion_status"] == deletion
    assert quality["coverage"]["race_control"] == (
        "observed"
        if values.get("race_control_observed")
        and changes.get("race_control_observed", True)
        else "not_observed"
    )
    assert "confidence" in quality
    assert "deleted" in quality
    assert "clean" in quality


def test_unknown_context_does_not_rewrite_legacy_clean_contract():
    quality = assess_lap_quality(
        lap_duration=90, sector_durations=[30, 30, 30]
    ).as_dict()
    assert quality["clean"] is True
    assert quality["deleted"] is None
    assert quality["pace_suitability"] == "uncertain"
    assert quality["deletion_status"] == "unknown"
    assert "unknown_track_status" in quality["pace_reasons"]


@pytest.mark.parametrize("provider", ["f1_live", "replay"])
async def test_later_source_coverage_does_not_rewrite_observed_lap_context(provider):
    from custom_components.f1_sensor.history import LapAnalysisStore
    from custom_components.f1_sensor.tests.test_history_behavior_matrix import (
        _timing_lap,
    )
    from custom_components.f1_sensor.tests.test_phase_4_analysis import _Bus

    bus = _Bus()
    store = LapAnalysisStore(bus, source_provider=lambda: provider)
    try:
        bus.emit("TimingData", _timing_lap(lap=1))
        bus.emit("TrackStatus", {"Status": "1"})
        bus.emit("RaceControlMessages", {"Messages": []})
        bus.emit("TimingData", {"Lines": {"4": {"Speeds": {"I1": "300"}}}})
        first = store.get_lap(4, 1)["quality"]
        assert first["coverage"] == {
            "track_status": "not_observed",
            "race_control": "not_observed",
        }
        assert first["deletion_status"] == "unknown"
        assert first["pace_suitability"] == "uncertain"
        bus.emit("TimingData", _timing_lap(lap=2))
        second = store.get_lap(4, 2)["quality"]
        assert second["coverage"] == {
            "track_status": "observed",
            "race_control": "observed",
        }
        assert second["pace_suitability"] == "eligible"
    finally:
        await store.async_close()


@pytest.mark.parametrize("provider", ["f1_live", "replay"])
async def test_late_sectors_improve_integrity_with_stable_nullable_quality_keys(
    provider,
):
    from custom_components.f1_sensor.history import LapAnalysisStore
    from custom_components.f1_sensor.tests.test_phase_4_analysis import _Bus

    bus = _Bus()
    store = LapAnalysisStore(bus, source_provider=lambda: provider)
    try:
        bus.emit("TrackStatus", {"Status": "1"})
        bus.emit(
            "TimingData",
            {
                "Lines": {
                    "4": {
                        "NumberOfLaps": 1,
                        "LastLapTime": {"Value": "1:30.000"},
                        "Sectors": {"0": {"Value": "30.000"}, "1": {"Value": "30.000"}},
                    }
                }
            },
        )
        incomplete = store.get_lap(4, 1)["quality"]
        assert incomplete["timing_integrity"] == "incomplete"
        assert incomplete["pace_suitability"] == "uncertain"
        assert incomplete["deleted"] is None
        assert incomplete["deletion_reason"] is None
        bus.emit(
            "TimingData", {"Lines": {"4": {"Sectors": {"2": {"Value": "30.000"}}}}}
        )
        complete = store.get_lap(4, 1)["quality"]
        assert complete.keys() == incomplete.keys()
        assert complete["deleted"] is None
        assert complete["deletion_reason"] is None
        assert complete["timing_integrity"] == "consistent"
        assert complete["pace_suitability"] == "eligible"
    finally:
        await store.async_close()


@pytest.mark.parametrize("provider", ["f1_live", "replay"])
async def test_explicit_lap_time_revision_replaces_eligible_time_before_sectors_arrive(
    provider,
):
    from custom_components.f1_sensor.analysis import Phase4AnalysisStore
    from custom_components.f1_sensor.history import LapAnalysisStore
    from custom_components.f1_sensor.tests.test_history_behavior_matrix import (
        _timing_lap,
    )
    from custom_components.f1_sensor.tests.test_phase_4_analysis import _Bus

    bus = _Bus()
    store = LapAnalysisStore(bus, source_provider=lambda: provider)
    analysis = Phase4AnalysisStore(bus, store, source_provider=lambda: provider)
    try:
        bus.emit("SessionInfo", {"Key": 1, "Name": "Race", "Type": "Race"})
        bus.emit("TrackStatus", {"Status": "1"})
        bus.emit("TimingData", _timing_lap())
        assert store.get_lap(4, 1)["quality"]["pace_suitability"] == "eligible"
        bus.emit("TimingData", {"Lines": {"4": {"LastLapTime": {"Value": "1:31.000"}}}})
        corrected = store.get_lap(4, 1)
        assert corrected["lap_duration"] == 91
        assert corrected["quality"]["timing_integrity"] == "inconsistent"
        assert corrected["quality"]["pace_suitability"] == "uncertain"
        assert (
            analysis._strategy_laps[(4, 1)]["quality"]["pace_suitability"]
            == "uncertain"
        )
        # A later matching sector revision makes the new time usable again.
        bus.emit(
            "TimingData", {"Lines": {"4": {"Sectors": {"2": {"Value": "31.000"}}}}}
        )
        complete = store.get_lap(4, 1)
        assert complete["lap_duration"] == 91
        assert complete["quality"]["pace_suitability"] == "eligible"
        # Starting the next lap clears live sector fields, not the completed lap.
        bus.emit(
            "TimingData",
            {
                "Lines": {
                    "4": {"Sectors": {str(index): {"Value": ""} for index in range(3)}}
                }
            },
        )
        assert store.get_lap(4, 1) == complete
    finally:
        await analysis.async_close()
        await store.async_close()
