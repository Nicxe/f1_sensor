"""Diagnostics tests for F1 Sensor."""

from __future__ import annotations

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import diagnostics as diagnostics_module
from custom_components.f1_sensor.auth import (
    AUTH_RUNTIME_STATUS,
    evaluate_f1tv_auth_header,
)
from custom_components.f1_sensor.const import (
    CONF_LIVE_TIMING_AUTH_HEADER,
    CONF_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_LIVE,
)
from custom_components.f1_sensor.track_map import (
    TRACK_MAP_FALLBACK_STATE_STATIC_CATALOG,
    TRACK_MAP_STATIC_GEOMETRY_SOURCE,
    TrackMapStore,
)
from custom_components.f1_sensor.track_map_static_geometry import (
    STATIC_TRACK_GEOMETRY_APPROVAL_VISUAL_APPROVED,
)


def _static_track_map_session_payload() -> dict:
    return {
        "Key": "101",
        "Name": "Race",
        "Type": "Race",
        "Meeting": {
            "Name": "Miami Grand Prix",
            "Circuit": {"Key": "151", "ShortName": "Miami"},
        },
    }


async def test_diagnostics_redacts_auth_header_and_exposes_safe_runtime_state(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="F1",
        data={
            CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
            CONF_LIVE_TIMING_AUTH_HEADER: "Authorization: Bearer secret-token",
        },
    )
    entry.add_to_hass(hass)

    live_bus = MagicMock()
    live_bus.last_heartbeat_age.return_value = 5.0
    live_bus.last_stream_activity_age.return_value = 2.0
    live_bus.stream_diagnostics.return_value = {
        "ChampionshipPrediction": {
            "frame_count": 3,
            "last_seen_age_s": 1.0,
            "last_payload_keys": ["Drivers", "Teams"],
        }
    }
    incident_coordinator = MagicMock()
    incident_coordinator.available = True
    incident_coordinator.data = {
        "active_count": 1,
        "highest_confidence": "high",
        "latest_incident_id": "2026-miami-race-10-2026-05-03T17:00:01Z",
        "latest_driver_number": "10",
        "latest_driver_tla": "GAS",
        "latest_reason": "timing_stopped_with_race_control",
        "latest_phase": "confirmed",
        "session_type": "race",
        "session_name": "Race",
        "data_quality": "live",
        "active_incidents": [{"large": "detail"}],
    }
    track_map_store = TrackMapStore(entry.entry_id)
    track_map_store.update_session_info(_static_track_map_session_payload())
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "operation_mode": OPERATION_MODE_LIVE,
        "live_bus": live_bus,
        "incident_coordinator": incident_coordinator,
        "track_map_store": track_map_store,
        "signalr_stream_capabilities": {
            "public_live_streams": frozenset({"SessionStatus", "TrackStatus"}),
            "auth_gated_live_streams": frozenset(
                {
                    "CarData.z",
                    "ChampionshipPrediction",
                    "PitStopSeries",
                }
            ),
            "replay_only_streams": frozenset(),
            "active_live_streams": frozenset(
                {
                    "SessionStatus",
                    "TrackStatus",
                    "ChampionshipPrediction",
                    "PitStopSeries",
                }
            ),
            "auth_enabled": True,
        },
        AUTH_RUNTIME_STATUS: evaluate_f1tv_auth_header("Bearer secret-token"),
    }

    payload = await diagnostics_module.async_get_config_entry_diagnostics(hass, entry)

    assert payload["entry"]["data"][CONF_LIVE_TIMING_AUTH_HEADER] == "**REDACTED**"
    assert payload["runtime"]["auth_configured"] is True
    assert payload["runtime"]["f1tv_token"]["status"] == "invalid"
    assert payload["runtime"]["f1tv_token"]["used_for_live_timing"] is False
    assert payload["runtime"]["auth_enabled"] is True
    assert payload["runtime"]["signalr_stream_capabilities"] == {
        "auth_enabled": True,
        "public_live_streams": ["SessionStatus", "TrackStatus"],
        "auth_gated_live_streams": [
            "CarData.z",
            "ChampionshipPrediction",
            "PitStopSeries",
        ],
        "active_live_streams": [
            "ChampionshipPrediction",
            "PitStopSeries",
            "SessionStatus",
            "TrackStatus",
        ],
    }
    assert payload["runtime"]["live_timing"]["heartbeat_age_s"] == 5.0
    assert payload["runtime"]["live_timing"]["activity_age_s"] == 2.0
    assert payload["runtime"]["live_timing"]["streams"]["ChampionshipPrediction"] == {
        "frame_count": 3,
        "last_seen_age_s": 1.0,
        "last_payload_keys": ["Drivers", "Teams"],
    }
    diagnostic_streams = live_bus.stream_diagnostics.call_args.args[0]
    assert "Position.z" in diagnostic_streams
    assert payload["runtime"]["incident_detection"] == {
        "active_count": 1,
        "highest_confidence": "high",
        "latest_incident_id": "2026-miami-race-10-2026-05-03T17:00:01Z",
        "latest_driver_number": "10",
        "latest_driver_tla": "GAS",
        "latest_reason": "timing_stopped_with_race_control",
        "latest_phase": "confirmed",
        "session_type": "race",
        "session_name": "Race",
        "data_quality": "live",
        "latest_location": None,
        "available": True,
    }
    assert payload["runtime"]["track_map"]["geometry_source"] == (
        TRACK_MAP_STATIC_GEOMETRY_SOURCE
    )
    assert payload["runtime"]["track_map"]["circuit_key"] == "151"
    assert payload["runtime"]["track_map"]["circuit_id"] == "miami"
    assert payload["runtime"]["track_map"]["point_count"] > 50
    assert payload["runtime"]["track_map"]["rotation"] == 11.2
    assert payload["runtime"]["track_map"]["approval_status"] == (
        STATIC_TRACK_GEOMETRY_APPROVAL_VISUAL_APPROVED
    )
    assert payload["runtime"]["track_map"]["fallback_state"] == (
        TRACK_MAP_FALLBACK_STATE_STATIC_CATALOG
    )
    assert "active_incidents" not in str(payload["runtime"]["incident_detection"])
    assert "secret-token" not in str(payload)


async def test_diagnostics_hides_auth_state_when_f1tv_auth_disabled(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", False)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="F1",
        data={
            CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
            CONF_LIVE_TIMING_AUTH_HEADER: "Bearer secret-token",
        },
    )
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "operation_mode": OPERATION_MODE_LIVE,
        "signalr_stream_capabilities": {
            "public_live_streams": frozenset({"SessionStatus", "TrackStatus"}),
            "auth_gated_live_streams": frozenset(
                {
                    "CarData.z",
                    "ChampionshipPrediction",
                    "PitStopSeries",
                }
            ),
            "replay_only_streams": frozenset(),
            "active_live_streams": frozenset(
                {"SessionStatus", "ChampionshipPrediction"}
            ),
            "auth_enabled": True,
        },
    }

    payload = await diagnostics_module.async_get_config_entry_diagnostics(hass, entry)

    runtime = payload["runtime"]
    capabilities = runtime["signalr_stream_capabilities"]
    assert "auth_configured" not in runtime
    assert "f1tv_token" not in runtime
    assert "auth_enabled" not in runtime
    assert "auth_enabled" not in capabilities
    assert "auth_gated_live_streams" not in capabilities
    assert capabilities == {
        "public_live_streams": ["SessionStatus", "TrackStatus"],
        "active_live_streams": ["SessionStatus"],
    }
    assert CONF_LIVE_TIMING_AUTH_HEADER not in payload["entry"]["data"]
    assert "secret-token" not in str(payload)
