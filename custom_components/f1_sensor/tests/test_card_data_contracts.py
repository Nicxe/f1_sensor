"""Explicit API failures and selected feature dependencies remain predictable."""

from types import SimpleNamespace
from unittest.mock import Mock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor.card_data_websocket import _ws_subscribe_card_data
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.context_data import ReplayStatusProjection
from custom_components.f1_sensor.data_catalog import card_feature_requirements


def test_dataset_and_runtime_errors_do_not_start_a_subscription(hass):
    entry = MockConfigEntry(domain=DOMAIN, version=4, minor_version=3)
    entry.add_to_hass(hass)
    connection = Mock()
    message = {"id": 1, "entry_id": entry.entry_id, "data_keys": ["invalid"]}
    _ws_subscribe_card_data(hass, connection, message)
    assert connection.send_error.call_args.args[1] == "unsupported_dataset"
    message["data_keys"] = ["driver_standings"]
    _ws_subscribe_card_data(hass, connection, message)
    assert connection.send_error.call_args.args[1] == "not_loaded"
    connection.send_result.assert_not_called()


def test_special_and_composite_features_resolve_to_existing_demand():
    required = card_feature_requirements(
        {"championship_prediction_drivers", "track_map", "driver_list"}
    )
    assert {
        "championship_prediction",
        "driver_positions",
        "current_session",
        "session_status",
        "race_control",
        "driver_standings",
    } <= required
    assert card_feature_requirements({"archive"}) == set()


def test_replay_selection_uses_planned_start_before_playback_is_loaded():
    controller = SimpleNamespace(
        get_playback_status=lambda: {},
        get_sync_points=lambda: [],
        get_planned_playback_details=lambda: {
            "session_start_ms": 5000,
            "playback_start_ms": 3000,
            "duration_ms": 12000,
        },
    )
    snapshot = ReplayStatusProjection(controller).snapshot({"state": "selected"})
    assert snapshot.attributes["playback_total_s"] == 9
    assert snapshot.attributes["session_start_offset_s"] == 5
    assert ReplayStatusProjection._format_time(-1) == "00:00:00"
