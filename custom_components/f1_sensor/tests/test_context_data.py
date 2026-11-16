"""Replay context can be displayed without a status sensor."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.f1_sensor.context_data import ReplayStatusProjection
from custom_components.f1_sensor.replay_entities import F1ReplayStatusSensor


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


@pytest.mark.parametrize(
    "code", ["archive_identity_conflict", "cache_normalization_incompatible", None]
)
def test_replay_errors_and_archive_identity_reach_both_display_transports(code):
    controller = SimpleNamespace(
        get_playback_status=lambda: {"duration_ms": 1000},
        get_sync_points=lambda: [],
    )
    snapshot = {
        "state": "selected",
        "download_error": "Cannot load replay" if code else None,
        "download_error_code": code,
        "archive_identity": {"status": "missing", "session_key": None},
    }
    projection = ReplayStatusProjection(controller).snapshot(snapshot)
    sensor = F1ReplayStatusSensor(controller, "replay-status", "entry", "F1")
    sensor.async_write_ha_state = Mock()
    sensor._handle_update(snapshot)
    for attributes in [projection.attributes, sensor.extra_state_attributes]:
        assert attributes["download_error_code"] == code
        assert attributes["archive_identity"] == snapshot["archive_identity"]
    snapshot["archive_identity"]["status"] = "conflict"
    assert projection.attributes["archive_identity"]["status"] == "missing"
    assert sensor.extra_state_attributes["archive_identity"]["status"] == "missing"
