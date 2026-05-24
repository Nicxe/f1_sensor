"""Diagnostics support for F1 Sensor."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .auth import (
    AUTH_RUNTIME_STATUS,
    F1TvAuthStatus,
    evaluate_f1tv_auth_header,
    is_auth_health_visible,
    is_auth_transport_enabled,
)
from .const import (
    CONF_LIVE_TIMING_AUTH_HEADER,
    CONF_OPERATION_MODE,
    DOMAIN,
)

TO_REDACT = {
    CONF_LIVE_TIMING_AUTH_HEADER,
    "Authorization",
    "authorization",
    "cookie",
    "cookies",
    "login-session",
    "nonce",
    "callback_body",
}
_TRACKED_STREAMS = (
    "SessionStatus",
    "TrackStatus",
    "RaceControlMessages",
    "TimingData",
    "DriverList",
    "TopThree",
    "TimingAppData",
    "ChampionshipPrediction",
    "DriverRaceInfo",
    "CarData.z",
    "PitStopSeries",
)


def _sorted_strings(value: object) -> list[str] | None:
    if not isinstance(value, (set, frozenset, tuple, list)):
        return None
    return sorted(str(item) for item in value)


def _serialize_signalr_stream_capabilities(
    capabilities: object, *, include_auth: bool
) -> dict[str, Any]:
    if not isinstance(capabilities, dict):
        return {}

    serialized: dict[str, Any] = {}
    if include_auth:
        serialized["auth_enabled"] = bool(capabilities.get("auth_enabled"))

    public_streams = _sorted_strings(capabilities.get("public_live_streams")) or []
    if public_streams:
        serialized["public_live_streams"] = public_streams

    replay_only_streams = _sorted_strings(capabilities.get("replay_only_streams")) or []
    if replay_only_streams:
        serialized["replay_only_streams"] = replay_only_streams

    if include_auth:
        if values := _sorted_strings(capabilities.get("auth_gated_live_streams")):
            serialized["auth_gated_live_streams"] = values

    for key in ("active_live_streams",):
        if values := _sorted_strings(capabilities.get(key)):
            if not include_auth:
                allowed = set(public_streams) | set(replay_only_streams)
                values = [stream for stream in values if stream in allowed]
                if not values:
                    continue
            serialized[key] = values
    return serialized


def _serialize_live_timing_runtime(live_bus: object) -> dict[str, Any]:
    runtime: dict[str, Any] = {}

    with suppress(Exception):
        runtime["heartbeat_age_s"] = live_bus.last_heartbeat_age()
    with suppress(Exception):
        runtime["activity_age_s"] = live_bus.last_stream_activity_age()
    with suppress(Exception):
        runtime["streams"] = live_bus.stream_diagnostics(_TRACKED_STREAMS)

    return runtime


def _serialize_incident_runtime(coordinator: object) -> dict[str, Any]:
    """Return a small incident detection diagnostics summary."""
    data = getattr(coordinator, "data", None)
    if not isinstance(data, dict):
        return {}

    return {
        "active_count": data.get("active_count"),
        "highest_confidence": data.get("highest_confidence"),
        "latest_incident_id": data.get("latest_incident_id"),
        "latest_driver_number": data.get("latest_driver_number"),
        "latest_driver_tla": data.get("latest_driver_tla"),
        "latest_reason": data.get("latest_reason"),
        "latest_phase": data.get("latest_phase"),
        "session_type": data.get("session_type"),
        "session_name": data.get("session_name"),
        "data_quality": data.get("data_quality"),
        "available": bool(getattr(coordinator, "available", False)),
    }


def _serialize_track_map_runtime(track_map_store: object) -> dict[str, Any]:
    """Return a compact track map diagnostics summary."""
    diagnostics = getattr(track_map_store, "diagnostics", None)
    if not callable(diagnostics):
        return {}
    payload: object = {}
    with suppress(Exception):
        payload = diagnostics()
    if not isinstance(payload, dict):
        return {}
    return payload


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for one config entry."""
    entry_runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}) or {}
    runtime_auth_status = entry_runtime.get(AUTH_RUNTIME_STATUS)
    include_auth_transport = is_auth_transport_enabled()
    auth_status = (
        runtime_auth_status
        if include_auth_transport and isinstance(runtime_auth_status, F1TvAuthStatus)
        else evaluate_f1tv_auth_header(entry.data.get(CONF_LIVE_TIMING_AUTH_HEADER, ""))
        if include_auth_transport
        else evaluate_f1tv_auth_header("")
    )
    include_auth_health = is_auth_health_visible(auth_status)
    capabilities = _serialize_signalr_stream_capabilities(
        entry_runtime.get("signalr_stream_capabilities"),
        include_auth=include_auth_transport,
    )
    runtime: dict[str, Any] = {
        "operation_mode": entry_runtime.get(
            "operation_mode", entry.data.get(CONF_OPERATION_MODE)
        ),
        "signalr_stream_capabilities": capabilities,
    }

    if include_auth_health:
        runtime["auth_configured"] = auth_status.configured
        runtime["f1tv_token"] = auth_status.as_safe_dict()
    if include_auth_transport:
        runtime["auth_enabled"] = bool(capabilities.get("auth_enabled"))

    live_bus = entry_runtime.get("live_bus")
    if live_bus is not None:
        runtime["live_timing"] = _serialize_live_timing_runtime(live_bus)

    incident_coordinator = entry_runtime.get("incident_coordinator")
    if incident_coordinator is not None:
        runtime["incident_detection"] = _serialize_incident_runtime(
            incident_coordinator
        )

    track_map_store = entry_runtime.get("track_map_store")
    if track_map_store is not None:
        runtime["track_map"] = _serialize_track_map_runtime(track_map_store)

    entry_data = dict(entry.data)
    if not include_auth_transport:
        entry_data.pop(CONF_LIVE_TIMING_AUTH_HEADER, None)

    payload: dict[str, Any] = {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "data": entry_data,
            "options": dict(entry.options),
        },
        "runtime": runtime,
    }

    return async_redact_data(payload, TO_REDACT)
