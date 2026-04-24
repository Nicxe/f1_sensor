"""Diagnostics support for F1 Sensor."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_LIVE_TIMING_AUTH_HEADER,
    CONF_OPERATION_MODE,
    DOMAIN,
    ENABLE_DEVELOPMENT_MODE_UI,
)
from .helpers import normalize_live_timing_auth_header

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
    "TopThree",
    "TimingAppData",
    "ChampionshipPrediction",
    "DriverRaceInfo",
    "CarData.z",
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


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for one config entry."""
    entry_runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}) or {}
    include_auth = ENABLE_DEVELOPMENT_MODE_UI
    capabilities = _serialize_signalr_stream_capabilities(
        entry_runtime.get("signalr_stream_capabilities"),
        include_auth=include_auth,
    )
    runtime: dict[str, Any] = {
        "operation_mode": entry_runtime.get(
            "operation_mode", entry.data.get(CONF_OPERATION_MODE)
        ),
        "signalr_stream_capabilities": capabilities,
    }

    if include_auth:
        runtime["auth_configured"] = bool(
            normalize_live_timing_auth_header(
                entry.data.get(CONF_LIVE_TIMING_AUTH_HEADER, "")
            )
        )
        runtime["auth_enabled"] = bool(capabilities.get("auth_enabled"))

    live_bus = entry_runtime.get("live_bus")
    if live_bus is not None:
        runtime["live_timing"] = _serialize_live_timing_runtime(live_bus)

    payload: dict[str, Any] = {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "runtime": runtime,
    }

    return async_redact_data(payload, TO_REDACT)
