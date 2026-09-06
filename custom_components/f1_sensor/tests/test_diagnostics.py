"""Diagnostics tests for F1 Sensor."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import diagnostics as diagnostics_module
from custom_components.f1_sensor.auth import (
    AUTH_RUNTIME_STATUS,
    evaluate_f1tv_auth_header,
)
from custom_components.f1_sensor.auth_http import AUTH_CALLBACK_METRICS
from custom_components.f1_sensor.const import (
    CONF_LIVE_TIMING_AUTH_HEADER,
    CONF_OPERATION_MODE,
    CONF_REPLAY_FILE,
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
                    "TeamRadio",
                }
            ),
            "replay_only_streams": frozenset(),
            "active_live_streams": frozenset(
                {
                    "SessionStatus",
                    "TrackStatus",
                    "ChampionshipPrediction",
                    "PitStopSeries",
                    "TeamRadio",
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
            "TeamRadio",
        ],
        "active_live_streams": [
            "ChampionshipPrediction",
            "PitStopSeries",
            "SessionStatus",
            "TeamRadio",
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
                    "TeamRadio",
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


async def test_diagnostics_exposes_only_safe_jolpica_runtime_scalars(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="F1",
        data={CONF_OPERATION_MODE: OPERATION_MODE_LIVE},
    )
    entry.add_to_hass(hass)

    client = MagicMock()
    client.diagnostics.return_value = {
        "user_agent_configured": True,
        "second_limit": 3,
        "hour_limit": 450,
        "max_queue_wait_seconds": 5.0,
        "requests_last_second": 2,
        "requests_last_hour": 27,
        "queue_length": 1,
        "blocked_requests": 4,
        "cooldown_remaining_seconds": 5.5,
        "latest_429": "2026-07-28T10:00:00+00:00",
        "cache_entries": 8,
        "inflight_requests": 1,
        "request_urls": ["https://api.jolpi.ca/ergast/f1/current.json"],
        "headers": {"User-Agent": "must-not-be-exposed"},
        "cache_keys": ["sensitive-request-key"],
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "operation_mode": OPERATION_MODE_LIVE,
        "jolpica_client": client,
        "http_cache": {"first": object(), "second": object()},
    }

    payload = await diagnostics_module.async_get_config_entry_diagnostics(hass, entry)

    assert payload["runtime"]["jolpica"] == {
        "user_agent_configured": True,
        "second_limit": 3,
        "hour_limit": 450,
        "max_queue_wait_seconds": 5.0,
        "requests_last_second": 2,
        "requests_last_hour": 27,
        "queue_length": 1,
        "blocked_requests": 4,
        "cooldown_remaining_seconds": 5.5,
        "latest_429": "2026-07-28T10:00:00+00:00",
        "cache_entries": 2,
        "inflight_requests": 1,
    }
    assert "api.jolpi.ca" not in str(payload)
    assert "must-not-be-exposed" not in str(payload)
    assert "sensitive-request-key" not in str(payload)


async def test_diagnostics_redacts_generic_secrets_and_replay_directory(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="F1",
        data={
            CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
            CONF_REPLAY_FILE: "/private/replays/secret-session.jsonStream",
            "future": {
                "token": "token-secret",
                "subscription_token": "subscription-secret",
                "session_id": "session-secret",
                "callback_url": "https://ha.example/callback-secret",
                "helper_url": "https://helper.example/helper-secret",
                "api_key": "api-secret",
            },
        },
    )
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "operation_mode": OPERATION_MODE_LIVE,
    }
    hass.data[DOMAIN][AUTH_CALLBACK_METRICS] = {
        "failures_total": 3,
        "failure_codes": {"invalid_nonce": 2, "rate_limited": 1},
    }

    payload = await diagnostics_module.async_get_config_entry_diagnostics(hass, entry)

    assert payload["entry"]["data"][CONF_REPLAY_FILE] == "secret-session.jsonStream"
    assert payload["runtime"]["auth_pairing"] == {
        "failures_total": 3,
        "failure_codes": {"invalid_nonce": 2, "rate_limited": 1},
    }
    serialized = str(payload)
    assert "/private/replays" not in serialized
    for secret in (
        "token-secret",
        "subscription-secret",
        "session-secret",
        "callback-secret",
        "helper-secret",
        "api-secret",
    ):
        assert secret not in serialized


async def test_diagnostics_serializes_full_runtime_service_tree(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="F1", data={}, options={"x": 1})
    entry.add_to_hass(hass)

    def _diagnostics(value):
        return SimpleNamespace(diagnostics=lambda: value)

    entry.runtime_data = SimpleNamespace(
        providers=SimpleNamespace(
            registry=SimpleNamespace(diagnostics=lambda: {"provider": "jolpica"})
        ),
        history=SimpleNamespace(
            service=_diagnostics({"requests": 2}),
            lap_analysis=_diagnostics({"live_replay_laps": 3}),
        ),
        analysis=SimpleNamespace(
            store=_diagnostics({"incidents": 1}),
            telemetry=_diagnostics({"comparisons": 2}),
        ),
        replay=SimpleNamespace(
            controller=SimpleNamespace(
                session_manager=SimpleNamespace(cache_diagnostics={"entries": 4})
            )
        ),
    )
    persistent = _diagnostics({"entries": 5, "bytes": 100})
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "http_persistent_cache": persistent,
        "signalr_stream_capabilities": {
            "public_live_streams": ["SessionStatus"],
            "replay_only_streams": ["CarData.z"],
            "requested_streams": ["SessionStatus", "CarData.z"],
            "stream_reasons": {
                "SessionStatus": {"sensor"},
                "bad": "ignored",
            },
        },
    }

    payload = await diagnostics_module.async_get_config_entry_diagnostics(hass, entry)
    runtime = payload["runtime"]
    assert runtime["providers"] == {"provider": "jolpica"}
    assert runtime["persistent_cache"] == {"entries": 5, "bytes": 100}
    assert runtime["history"] == {
        "requests": 2,
        "live_replay_laps": {"live_replay_laps": 3},
    }
    assert runtime["analysis"] == {
        "incidents": 1,
        "replay_telemetry": {"comparisons": 2},
    }
    assert runtime["replay_cache"] == {"entries": 4}
    assert runtime["signalr_stream_capabilities"]["stream_reasons"] == {
        "SessionStatus": ["sensor"]
    }


def test_diagnostic_serializers_fail_closed() -> None:
    assert diagnostics_module._serialize_incident_runtime(object()) == {}
    assert diagnostics_module._serialize_track_map_runtime(object()) == {}
    assert diagnostics_module._serialize_jolpica_runtime(object()) == {}
    assert diagnostics_module._safe_diagnostics(object()) == {}

    broken = SimpleNamespace(diagnostics=lambda: (_ for _ in ()).throw(RuntimeError()))
    assert diagnostics_module._serialize_track_map_runtime(broken) == {}
    assert diagnostics_module._serialize_jolpica_runtime(broken) == {}
    assert diagnostics_module._safe_diagnostics(broken) == {}

    non_mapping = SimpleNamespace(diagnostics=lambda: ["bad"])
    assert diagnostics_module._serialize_track_map_runtime(non_mapping) == {}
    assert diagnostics_module._serialize_jolpica_runtime(non_mapping) == {}
