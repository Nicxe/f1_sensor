from __future__ import annotations

from copy import deepcopy

import pytest

from custom_components.f1_sensor.incident_detection import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    DATA_QUALITY_REPLAY,
    PHASE_CONFIRMED,
)
from custom_components.f1_sensor.tests.incident_replay import (
    MAX_REPLAY_CASE_BYTES,
    PUBLIC_REPLAY_STREAMS,
    extracted_cases,
    format_replay_timeline,
    load_fixture_manifest,
    replay_case_size_bytes,
    replay_manifest_case,
    validate_replay_case,
)

EXPECTED_REPLAY_INCIDENTS = {
    "2026_australian_gp_qualifying_ver_red_flag": {
        "drivers": {"3"},
        "reason": "timing_stopped_with_race_control",
        "session_type": "qualifying",
    },
    "2026_miami_gp_race_had_gas_safety_car": {
        "drivers": {"6", "10"},
        "reason": "timing_stopped_with_safety_car_context",
        "session_type": "race",
    },
    "2026_chinese_gp_sprint_hulkenberg_safety_car": {
        "drivers": {"27"},
        "reason": "timing_stopped_with_safety_car_context",
        "session_type": "sprint",
    },
    "2026_chinese_gp_practice_lindblad_vsc": {
        "drivers": {"41"},
        "reason": "timing_stopped_with_vsc_context",
        "session_type": "practice",
    },
}


def _case_by_id(case_id: str):
    return next(case for case in extracted_cases() if case["id"] == case_id)


def test_fixture_manifest_contains_only_public_phase_2_replay_streams() -> None:
    manifest = load_fixture_manifest()
    cases = extracted_cases(manifest)

    assert manifest["version"] == 1
    assert {case["id"] for case in cases} == set(EXPECTED_REPLAY_INCIDENTS)
    for case in cases:
        validate_replay_case(case)
        assert replay_case_size_bytes(case) < MAX_REPLAY_CASE_BYTES
        assert case["optional_streams_excluded"] == ["CarData.z"]
        assert set(case["included_streams"]).issubset(PUBLIC_REPLAY_STREAMS)
        assert {frame["stream"] for frame in case["frames"]}.issubset(
            PUBLIC_REPLAY_STREAMS
        )


@pytest.mark.parametrize("case_id", sorted(EXPECTED_REPLAY_INCIDENTS))
def test_replay_fixture_confirms_expected_incidents(case_id: str) -> None:
    expected = EXPECTED_REPLAY_INCIDENTS[case_id]

    result = replay_manifest_case(_case_by_id(case_id))
    confirmed = [change for change in result.changes if change.phase == PHASE_CONFIRMED]

    assert result.frames[0].offset == "state_before"
    assert result.frames[0].changes == ()
    assert {change.driver.racing_number for change in confirmed} == expected["drivers"]
    assert {change.confidence for change in confirmed} == {CONFIDENCE_HIGH}
    assert {change.reason for change in confirmed} == {expected["reason"]}
    assert {change.session.session_type for change in confirmed} == {
        expected["session_type"]
    }
    assert {change.data_quality for change in confirmed} == {DATA_QUALITY_REPLAY}
    assert all("timing_stopped" in change.signals for change in confirmed)
    assert all(change.track_status.status is not None for change in confirmed)


@pytest.mark.parametrize("case_id", sorted(EXPECTED_REPLAY_INCIDENTS))
def test_replay_fixture_dedupes_confirmed_incidents_per_driver(case_id: str) -> None:
    result = replay_manifest_case(_case_by_id(case_id))
    confirmed = [change for change in result.changes if change.phase == PHASE_CONFIRMED]

    assert len(confirmed) == len({change.driver.racing_number for change in confirmed})
    assert all(change.started_at == change.updated_at for change in confirmed)


def test_practice_replay_without_context_stays_medium_not_high() -> None:
    case = deepcopy(_case_by_id("2026_chinese_gp_practice_lindblad_vsc"))
    case["frames"] = [
        frame for frame in case["frames"] if frame["stream"] == "TimingData"
    ]

    result = replay_manifest_case(case)
    confirmed = [change for change in result.changes if change.phase == PHASE_CONFIRMED]

    assert len(confirmed) == 1
    assert confirmed[0].driver.racing_number == "41"
    assert confirmed[0].confidence == CONFIDENCE_MEDIUM
    assert confirmed[0].reason == "timing_stopped"


def test_replay_timeline_uses_neutral_incident_language() -> None:
    timeline = format_replay_timeline(
        replay_manifest_case(_case_by_id("2026_chinese_gp_practice_lindblad_vsc"))
    )

    assert "00:28:00.553 TimingData: confirmed high car 41" in timeline
    assert "crash" not in timeline.lower()
    assert "accident" not in timeline.lower()
    assert "mechanical failure" not in timeline.lower()
    assert "off track" not in timeline.lower()
