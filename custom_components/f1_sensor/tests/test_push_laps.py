"""Regression coverage for conservative push-lap inference from public timing."""

from __future__ import annotations

from custom_components.f1_sensor.push_laps import PushLapTracker


def _tracker() -> PushLapTracker:
    tracker = PushLapTracker()
    tracker.update("SessionInfo", {"Type": "Qualifying", "Key": 1})
    return tracker


def _send(tracker: PushLapTracker, at: float, **line) -> dict:
    tracker.update("TimingData", {"_f1_source_time": at, "Lines": {"63": line}})
    return tracker.driver_snapshot("63")


def _segments(values: dict[int, int], sector: int = 0) -> dict:
    return {
        str(sector): {
            "Segments": {str(key): {"Status": value} for key, value in values.items()}
        }
    }


def test_pit_out_false_does_not_end_the_outlap() -> None:
    tracker = _tracker()
    _send(tracker, 0, InPit=True, NumberOfLaps=0)
    _send(tracker, 5, InPit=False, PitOut=True)
    assert _send(tracker, 10, PitOut=False)["state"] == "outlap"
    assert not _send(tracker, 15, Sectors=_segments({0: 2049, 1: 2051}))["active"]
    assert _send(tracker, 70, NumberOfLaps=1)["state"] == "unknown"
    assert _send(tracker, 72, Sectors=_segments({0: 0, 1: 0}))["active"] is False
    assert _send(tracker, 74, Sectors=_segments({0: 2049}))["active"] is False
    result = _send(tracker, 78, Sectors=_segments({1: 2049}))
    assert result["state"] == "probable_push"
    assert result["confidence"] == "medium"


def test_first_attempt_uses_fresh_green_progress_before_first_sector() -> None:
    tracker = _tracker()
    _send(tracker, 0, NumberOfLaps=1, Sectors=_segments({0: 0, 1: 0, 2: 0}))
    _send(tracker, 4, Sectors=_segments({0: 2049}))
    result = _send(tracker, 8, Sectors=_segments({1: 2051}))
    assert result["active"] is True
    assert result["state"] == "probable_push"
    assert result["lap"] == 1
    result = _send(
        tracker, 25, Sectors={"0": {"Value": "25.000", "PersonalFastest": True}}
    )
    assert result["state"] == "push"
    assert result["confidence"] == "high"


def test_same_driver_sector_pace_separates_fast_slow_and_fast_without_green() -> None:
    tracker = _tracker()
    _send(tracker, 0, NumberOfLaps=1)
    assert _send(
        tracker, 25, Sectors={"0": {"Value": "25.000", "PersonalFastest": True}}
    )["active"]
    _send(tracker, 85, NumberOfLaps=2, LastLapTime={"Value": "1:25.000"})
    result = _send(tracker, 122, Sectors={"0": {"Value": "37.000"}})
    assert result["state"] == "cooldown"
    _send(tracker, 210, NumberOfLaps=3, LastLapTime={"Value": "2:05.000"})
    result = _send(tracker, 236, Sectors={"0": {"Value": "26.000"}})
    assert result["state"] == "push"
    assert result["confidence"] == "medium"


def test_completed_result_expires_on_source_clock_and_new_lap_is_independent() -> None:
    tracker = _tracker()
    _send(tracker, 0, NumberOfLaps=1)
    _send(tracker, 25, Sectors={"0": {"Value": "25.000", "PersonalFastest": True}})
    result = _send(tracker, 85, NumberOfLaps=2, LastLapTime={"Value": "1:25.000"})
    assert result["state"] == "completed"
    assert result["last_lap_time"] == 85
    assert result["lap"] == 1
    assert result["active"] is False
    assert _send(tracker, 89)["state"] == "completed"
    assert _send(tracker, 92)["state"] == "unknown"
    assert tracker.driver_snapshot("63")["lap"] == 2


def test_snapshots_reordered_frames_and_stale_data_never_create_push() -> None:
    tracker = _tracker()
    tracker.update(
        "TimingData",
        {
            "_f1_source_time": 20,
            "_f1_snapshot": True,
            "Lines": {
                "63": {"NumberOfLaps": 1, "Sectors": _segments({0: 2049, 1: 2051})}
            },
        },
    )
    assert not tracker.driver_snapshot("63")["active"]
    _send(tracker, 10, Sectors=_segments({2: 2051}))
    assert not tracker.driver_snapshot("63")["active"]
    _send(tracker, 25, Sectors={"0": {"Value": "25.000", "PersonalFastest": True}})
    assert tracker.driver_snapshot("63")["active"]
    tracker.update(
        "TimingData", {"_f1_source_time": 80, "Lines": {"4": {"Position": "1"}}}
    )
    result = tracker.driver_snapshot("63")
    assert result["state"] == "unknown"
    assert result["reason"] == "stale_timing"


def test_track_disruption_session_part_and_source_reset_clear_inference() -> None:
    tracker = _tracker()
    tracker.update("TimingData", {"SessionPart": 1})
    _send(tracker, 0, NumberOfLaps=1)
    _send(tracker, 25, Sectors={"0": {"Value": "25.000", "PersonalFastest": True}})
    tracker.update("TrackStatus", {"Status": "5", "_f1_source_time": 26})
    assert not tracker.driver_snapshot("63")["active"]
    tracker.update("TimingData", {"SessionPart": 2, "_f1_source_time": 27})
    assert tracker.driver_snapshot("63")["state"] == "unknown"
    tracker.reset()
    assert tracker.status == "waiting"
    assert tracker.driver_snapshot("63")["observed_at"] is None


def test_unsupported_sessions_and_stable_empty_contract() -> None:
    tracker = PushLapTracker()
    empty = tracker.driver_snapshot("63")
    assert set(empty) == {
        "state",
        "active",
        "confidence",
        "lap",
        "progress",
        "observed_at",
        "completed_at",
        "last_lap_time",
        "reason",
    }
    tracker.update("SessionInfo", {"Type": "Race", "Name": "Sprint"})
    assert tracker.status == "unsupported"
    tracker.update("SessionInfo", {"Type": "Qualifying", "Name": "Sprint Qualifying"})
    assert tracker.status == "waiting"


def test_unknown_session_minisectors_do_not_expose_effort_or_progress() -> None:
    tracker = PushLapTracker()
    empty = tracker.driver_snapshot("63")
    _send(tracker, 0, NumberOfLaps=1, Sectors=_segments({0: 0, 1: 0}))
    _send(tracker, 4, Sectors=_segments({0: 2049}))
    _send(tracker, 8, Sectors=_segments({1: 2051}))
    assert tracker.driver_snapshot("63") == empty
    assert tracker.status == "waiting"


def test_snapshot_only_on_track_rows_wait_even_when_other_drivers_are_in_pit() -> None:
    tracker = _tracker()
    tracker.update(
        "TimingData",
        {
            "_f1_snapshot": True,
            "_f1_source_time": 100,
            "Lines": {
                "63": {
                    "NumberOfLaps": 2,
                    "InPit": False,
                    "Sectors": _segments({0: 2049, 1: 2051}),
                },
                "44": {"InPit": True},
            },
        },
    )
    assert tracker.driver_snapshot("63")["reason"] == "snapshot_only"
    assert tracker.status == "waiting"
    tracker.update("Heartbeat", {"_f1_source_time": 110})
    assert tracker.status == "waiting"
    _send(tracker, 125, Sectors={"0": {"Value": "25.000", "PersonalFastest": True}})
    assert tracker.status == "available"


def test_cold_checkpoint_outlap_cannot_promote_from_fresh_s2_or_late_s3() -> None:
    tracker = _tracker()
    tracker.update(
        "TimingData",
        {
            "_f1_snapshot": True,
            "_f1_source_time": 100,
            "Lines": {"63": {"NumberOfLaps": 1, "InPit": False, "PitOut": False}},
        },
    )
    _send(tracker, 105, Sectors=_segments({3: 2049, 4: 2049}, sector=1))
    result = _send(
        tracker,
        110,
        Sectors={
            "2": {
                "Value": "35.000",
                "PersonalFastest": True,
                "Segments": {"7": {"Status": 2051}},
            }
        },
    )
    assert result["active"] is False
    assert result["state"] == "unknown"
    assert result["progress"] is None
    assert tracker.status == "waiting"
    _send(tracker, 120, NumberOfLaps=2)
    _send(tracker, 125, Sectors=_segments({0: 2049}))
    assert _send(tracker, 128, Sectors=_segments({1: 2049}))["active"] is True


def test_fresh_competitive_s1_can_establish_effort_after_a_cold_checkpoint() -> None:
    tracker = _tracker()
    tracker.update(
        "TimingData",
        {
            "_f1_snapshot": True,
            "_f1_source_time": 100,
            "Lines": {"63": {"NumberOfLaps": 5, "InPit": False, "PitOut": False}},
        },
    )
    _send(tracker, 105, Sectors=_segments({4: 2049, 5: 2049}, sector=1))
    result = _send(
        tracker, 125, Sectors={"0": {"Value": "25.000", "PersonalFastest": True}}
    )
    assert result["active"] is True
    assert result["state"] == "push"
    assert result["progress"] == 1 / 3
    result = _send(
        tracker,
        126,
        Sectors={
            "2": {
                "Value": "35.000",
                "PersonalFastest": True,
                "Segments": {"7": {"Status": 2051}},
            }
        },
    )
    assert result["progress"] == 1 / 3


def test_status_waits_when_all_on_track_timing_is_stale_despite_live_heartbeat() -> (
    None
):
    tracker = _tracker()
    _send(tracker, 0, NumberOfLaps=1)
    _send(tracker, 25, Sectors={"0": {"Value": "25.000", "PersonalFastest": True}})
    tracker.update(
        "TimingData", {"_f1_source_time": 26, "Lines": {"44": {"InPit": True}}}
    )
    assert tracker.status == "available"
    tracker.update("Heartbeat", {"_f1_source_time": 80})
    assert tracker.driver_snapshot("63")["reason"] == "stale_timing"
    assert tracker.status == "waiting"


def test_known_pit_outlap_and_slow_timing_are_available_without_active_push() -> None:
    tracker = _tracker()
    assert not _send(tracker, 0, InPit=True, NumberOfLaps=1)["active"]
    assert tracker.status == "available"
    assert _send(tracker, 5, InPit=False, PitOut=True)["state"] == "outlap"
    assert tracker.status == "available"
    _send(tracker, 70, NumberOfLaps=2)
    _send(tracker, 95, Sectors={"0": {"Value": "25.000", "PersonalFastest": True}})
    _send(tracker, 155, NumberOfLaps=3, LastLapTime={"Value": "1:25.000"})
    assert (
        _send(tracker, 192, Sectors={"0": {"Value": "37.000"}})["state"] == "cooldown"
    )
    assert tracker.status == "available"


async def test_unknown_session_metadata_does_not_publish_minisector_clock(hass) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock

    from custom_components.f1_sensor import LiveDriversCoordinator

    coordinator = LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    coordinator._schedule_deliver = Mock()
    coordinator._on_timingdata(
        {
            "_f1_source_time": 12,
            "_f1_source_utc": "2026-10-24T21:00:12+00:00",
            "Lines": {"63": {"Sectors": _segments({0: 2049, 1: 2051})}},
        }
    )
    coordinator._schedule_deliver.assert_not_called()
    assert coordinator._state["push_laps_stream_time"] is None
    assert coordinator._state["drivers"]["63"]["push_lap"]["progress"] is None
    await coordinator.async_close()


def test_abort_is_latched_until_start_and_retirement_is_not_cleared_by_stopped() -> (
    None
):
    tracker = _tracker()
    _send(tracker, 0, NumberOfLaps=1)
    tracker.update("SessionStatus", {"Status": "Aborted", "_f1_source_time": 1})
    assert not _send(
        tracker, 25, Sectors={"0": {"Value": "25.000", "PersonalFastest": True}}
    )["active"]
    tracker.update("SessionStatus", {"Status": "Started", "_f1_source_time": 30})
    assert _send(
        tracker, 60, Sectors={"1": {"Value": "30.000", "PersonalFastest": True}}
    )["active"]
    assert not _send(tracker, 61, Retired=True)["active"]
    assert not _send(
        tracker,
        62,
        Stopped=False,
        Sectors={"2": {"Value": "31.000", "PersonalFastest": True}},
    )["active"]


def test_finished_allows_existing_lap_but_not_new_attempts() -> None:
    tracker = _tracker()
    _send(tracker, 0, NumberOfLaps=1)
    _send(tracker, 25, Sectors={"0": {"Value": "25.000", "PersonalFastest": True}})
    tracker.update("SessionStatus", {"Status": "Finished", "_f1_source_time": 30})
    assert _send(
        tracker, 55, Sectors={"1": {"Value": "30.000", "PersonalFastest": True}}
    )["active"]
    _send(tracker, 85, NumberOfLaps=2, LastLapTime={"Value": "1:25.000"})
    assert not _send(
        tracker, 110, Sectors={"0": {"Value": "25.000", "PersonalFastest": True}}
    )["active"]


def test_replay_heartbeat_snapshot_does_not_mix_utc_and_relative_clocks() -> None:
    tracker = _tracker()
    tracker.update("Heartbeat", {"Utc": "2026-10-24T21:00:00+00:00"})
    _send(tracker, 0, NumberOfLaps=1)
    tracker.update("TrackStatus", {"Status": "1", "Utc": "2026-10-24T21:00:01+00:00"})
    assert _send(
        tracker, 25, Sectors={"0": {"Value": "25.000", "PersonalFastest": True}}
    )["active"]


def test_late_s3_flags_belong_to_completed_lap_not_the_new_attempt() -> None:
    tracker = _tracker()
    _send(tracker, 0, NumberOfLaps=1)
    _send(tracker, 25, Sectors={"0": {"Value": "25.000", "PersonalFastest": True}})
    _send(tracker, 85, NumberOfLaps=2)
    result = _send(
        tracker,
        85.01,
        Sectors={
            "2": {
                "Value": "30.000",
                "PersonalFastest": True,
                "Segments": {"5": {"Status": 2049}},
            }
        },
    )
    assert result["active"] is False
    assert result["progress"] == 0


async def test_coordinator_and_projection_publish_clock_expiry_and_stable_contract(
    hass,
) -> None:
    from types import SimpleNamespace

    from custom_components.f1_sensor import LiveDriversCoordinator
    from custom_components.f1_sensor.live_data_models import DriverPositionsModel

    coordinator = LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    coordinator._on_sessioninfo({"Key": 1, "Type": "Qualifying"})
    coordinator._on_timingdata(
        {"_f1_source_time": 0, "Lines": {"63": {"NumberOfLaps": 1}}}
    )
    coordinator._on_timingdata(
        {
            "_f1_source_time": 25,
            "Lines": {
                "63": {"Sectors": {"0": {"Value": "25.000", "PersonalFastest": True}}}
            },
        }
    )
    model = DriverPositionsModel(coordinator, "positions", "entry", "F1")
    model.hass = hass
    assert model._update_from_coordinator()
    assert model.extra_state_attributes["push_laps_status"] == "available"
    assert model.extra_state_attributes["drivers"][0]["push_lap"]["active"]
    coordinator._on_push_lap_clock({"_f1_source_time": 80})
    assert model._update_from_coordinator()
    assert (
        model.extra_state_attributes["drivers"][0]["push_lap"]["reason"]
        == "stale_timing"
    )
    await coordinator.async_close()
