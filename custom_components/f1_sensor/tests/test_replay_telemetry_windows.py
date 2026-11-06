"""Telemetry windows are observations, never inferred finish-line crossings."""

import json

import pytest

from custom_components.f1_sensor import replay_telemetry as telemetry
from custom_components.f1_sensor.tests.test_replay_telemetry_behavior_matrix import (
    _manager,
    _Response,
    _Session,
)


def _write_frames(tmp_path, rows):
    path = tmp_path / "frames.jsonl"
    path.write_text(
        "".join(
            json.dumps({"t": stamp, "s": stream, "p": payload}) + "\n"
            for stamp, stream, payload in rows
        )
    )
    return path


def _timing(stamp, **fields):
    return stamp, "TimingData", {"Lines": {"4": fields}}


@pytest.mark.parametrize(
    "updates",
    [
        [_timing(1000, NumberOfLaps=1), _timing(1500, LastLapTime={"Value": "1:20"})],
        [_timing(500, LastLapTime={"Value": "1:20"}), _timing(1000, NumberOfLaps=1)],
        [
            _timing(1000, NumberOfLaps=1),
            _timing(1400, Sectors={"2": {"Value": "25.0"}}),
            _timing(1500, LastLapTime={"Value": "1:20"}),
        ],
        [
            _timing(1000, NumberOfLaps=1, LastLapTime={"Value": "1:20"}),
            _timing(1500, NumberOfLaps=1, LastLapTime={"Value": "1:19"}),
        ],
    ],
)
def test_lap_count_observation_is_not_shifted_by_late_time_or_sector(tmp_path, updates):
    frames = _write_frames(
        tmp_path,
        [
            (0, "SessionStatus", {"Status": "Started"}),
            *updates,
            _timing(2000, NumberOfLaps=2),
            _timing(2500, LastLapTime={"Value": "1:18"}),
        ],
    )
    windows, _ = telemetry._scan_replay_windows(frames, ((4, 1), (4, 2)), 0)
    assert windows == {"4:1": (0, 1000), "4:2": (1000, 2000)}


def test_lap_one_requires_recorded_session_start(tmp_path):
    frames = _write_frames(
        tmp_path, [_timing(600_000, NumberOfLaps=1, LastLapTime={"Value": "1:20"})]
    )
    assert telemetry._scan_replay_windows(frames, ((4, 1),), 0)[0] == {}


def test_late_start_and_missing_count_never_invent_prior_boundaries(tmp_path):
    frames = _write_frames(
        tmp_path,
        [
            _timing(600_000, NumberOfLaps=40),
            _timing(680_000, NumberOfLaps=41),
            _timing(840_000, NumberOfLaps=43),
        ],
    )
    windows, _ = telemetry._scan_replay_windows(frames, ((4, 40), (4, 41), (4, 43)), 0)
    assert windows == {"4:41": (600_000, 680_000)}


def test_out_of_order_count_cannot_anchor_a_subsequent_window(tmp_path):
    frames = _write_frames(
        tmp_path,
        [
            _timing(2000, NumberOfLaps=1, LastLapTime={"Value": "1:20"}),
            _timing(1000, NumberOfLaps=2, LastLapTime={"Value": "1:20"}),
            _timing(3000, NumberOfLaps=3, LastLapTime={"Value": "1:20"}),
        ],
    )
    assert telemetry._scan_replay_windows(frames, ((4, 2), (4, 3)), 0)[0] == {}


def test_flags_and_time_corrections_do_not_shift_count_observations(tmp_path):
    frames = _write_frames(
        tmp_path,
        [
            _timing(1000, NumberOfLaps=1),
            (1500, "TrackStatus", {"Status": "4"}),
            _timing(2000, NumberOfLaps=2),
            (2500, "SessionStatus", {"Status": "Aborted"}),
            _timing(5000, LastLapTime={"Value": "1:18"}),
            (6000, "SessionStatus", {"Status": "Started"}),
            _timing(7000, NumberOfLaps=3),
        ],
    )
    assert telemetry._scan_replay_windows(frames, ((4, 2), (4, 3)), 6000)[0] == {
        "4:2": (1000, 2000),
        "4:3": (2000, 7000),
    }


async def test_telemetry_exposes_observation_windows_and_complete_recording_scope(
    hass, tmp_path
):
    frames = _write_frames(
        tmp_path,
        [
            (0, "SessionStatus", {"Status": "Started"}),
            _timing(1000, NumberOfLaps=1),
            _timing(1500, LastLapTime={"Value": "1:20"}),
            _timing(2000, NumberOfLaps=2),
        ],
    )
    manager = _manager(tmp_path)
    manager.get_loaded_index().frames_file = frames
    service = telemetry.ReplayTelemetryService(hass, _Session(_Response(200)), manager)
    catalog = await service.async_catalog(expected_session_id="session")
    assert catalog["analysis_scope"] == "complete_recording"
    assert catalog["coverage"]["lap_windows"] == "observation_based"
    assert catalog["coverage"]["passage_times_verified"] is False
    assert catalog["drivers"][0]["laps"] == [1, 2]
    result = await service.async_compare([{"driver_number": 4, "lap_number": 2}])
    assert result["analysis_scope"] == "complete_recording"
    assert result["series"][0]["window"] == {
        "start_ms": 1000,
        "end_ms": 2000,
        "basis": "observation_based",
        "start_source": "TimingData.NumberOfLaps",
        "end_source": "TimingData.NumberOfLaps",
        "passage_times_verified": False,
    }
    assert result["limits"]["max_selections"] == 4
    assert result["limits"]["max_points_per_lap"] == 500
    assert result["limits"]["cache_entries"] == 8
    cached = await service.async_compare([{"driver_number": 4, "lap_number": 2}])
    assert cached == result
    await service.async_close()
