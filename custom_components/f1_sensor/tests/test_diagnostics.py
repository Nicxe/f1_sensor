"""Diagnostics tests for F1 Sensor."""

from __future__ import annotations

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import diagnostics as diagnostics_module
from custom_components.f1_sensor.const import (
    CONF_LIVE_TIMING_AUTH_HEADER,
    CONF_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_LIVE,
)


async def test_diagnostics_redacts_auth_header_and_exposes_safe_runtime_state(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(diagnostics_module, "ENABLE_DEVELOPMENT_MODE_UI", True)
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
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "operation_mode": OPERATION_MODE_LIVE,
        "live_bus": live_bus,
        "signalr_stream_capabilities": {
            "public_live_streams": frozenset({"SessionStatus", "TrackStatus"}),
            "auth_gated_live_streams": frozenset(
                {"CarData.z", "ChampionshipPrediction"}
            ),
            "replay_only_streams": frozenset({"TeamRadio"}),
            "active_live_streams": frozenset(
                {"SessionStatus", "TrackStatus", "ChampionshipPrediction"}
            ),
            "auth_enabled": True,
        },
    }

    payload = await diagnostics_module.async_get_config_entry_diagnostics(hass, entry)

    assert payload["entry"]["data"][CONF_LIVE_TIMING_AUTH_HEADER] == "**REDACTED**"
    assert payload["runtime"]["auth_configured"] is True
    assert payload["runtime"]["auth_enabled"] is True
    assert payload["runtime"]["signalr_stream_capabilities"] == {
        "auth_enabled": True,
        "public_live_streams": ["SessionStatus", "TrackStatus"],
        "auth_gated_live_streams": ["CarData.z", "ChampionshipPrediction"],
        "replay_only_streams": ["TeamRadio"],
        "active_live_streams": [
            "ChampionshipPrediction",
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
    assert "secret-token" not in str(payload)


async def test_diagnostics_hides_auth_state_when_development_ui_disabled(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(diagnostics_module, "ENABLE_DEVELOPMENT_MODE_UI", False)
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
                {"CarData.z", "ChampionshipPrediction"}
            ),
            "replay_only_streams": frozenset({"TeamRadio"}),
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
    assert "auth_enabled" not in runtime
    assert "auth_enabled" not in capabilities
    assert "auth_gated_live_streams" not in capabilities
    assert capabilities == {
        "public_live_streams": ["SessionStatus", "TrackStatus"],
        "replay_only_streams": ["TeamRadio"],
        "active_live_streams": ["SessionStatus"],
    }
    assert payload["entry"]["data"][CONF_LIVE_TIMING_AUTH_HEADER] == "**REDACTED**"
    assert "secret-token" not in str(payload)
