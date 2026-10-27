"""Replay context can be displayed without a status sensor."""

from types import SimpleNamespace

from custom_components.f1_sensor.context_data import ReplayStatusProjection


def test_replay_context_keeps_selected_session_and_relative_playback_time():
    controller = SimpleNamespace(
        get_playback_status=lambda: {
            "position_ms": 75000,
            "playback_start_ms": 15000,
            "duration_ms": 135000,
            "paused": True,
        },
        get_sync_points=lambda: [],
    )
    projection = ReplayStatusProjection(controller).snapshot(
        {
            "state": "paused",
            "selected_session_id": "race-2026-1",
            "selected_session_year": 2026,
            "selected_session_key": 123,
        }
    )
    assert projection.value == "paused"
    assert projection.attributes["playback_position_s"] == 60
    assert projection.attributes["playback_total_s"] == 120
    assert projection.attributes["selected_session_id"] == "race-2026-1"


def test_no_replay_runtime_has_an_explicit_idle_context():
    projection = ReplayStatusProjection(None).snapshot({})
    assert projection.value == "idle"
