"""Diagnostics for the F1 Sensor integration.

Exposes compact runtime stats to aid troubleshooting without verbose logging.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

TO_REDACT: set[str] = set()


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    try:
        return dt_util.utcnow().fromtimestamp(ts, tz=dt_util.UTC).isoformat(timespec="seconds")  # type: ignore[attr-defined]
    except Exception:
        return None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    reg = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})

    # Options snapshot (non-sensitive)
    options = {
        "enable_race_control": bool(entry.data.get("enable_race_control", False)),
        "live_delay_seconds": entry.data.get("live_delay_seconds"),
        "enabled_sensors": list(entry.data.get("enabled_sensors", [])),
    }

    # LiveBus stats
    bus = reg.get("live_bus")
    live_bus: dict[str, Any] = {}
    if bus is not None:
        try:
            subs = getattr(bus, "_subs", {}) or {}
            cnt = getattr(bus, "_cnt", {}) or {}
            last_ts = getattr(bus, "_last_ts", {}) or {}
            interval = getattr(bus, "_log_interval", None)
            live_bus = {
                "subscribers": {k: len(v or []) for k, v in subs.items()},
                "counts": dict(cnt),
                "last_seen_age_seconds": {
                    k: (dt_util.utcnow().timestamp() - (last_ts.get(k) or 0.0)) for k in cnt.keys()
                },
                "summary_interval_seconds": interval,
            }
        except Exception:
            live_bus = {"error": "unavailable"}

    def _coord_diag(obj: Any) -> dict[str, Any]:
        if obj is None:
            return {"present": False}
        out: dict[str, Any] = {"present": True}
        try:
            out["available"] = bool(getattr(obj, "available", True))
        except Exception:
            pass
        try:
            data = getattr(obj, "data", None)
            if isinstance(data, dict):
                # RaceControl special fields
                if "Messages" in data or "Category" in data:
                    out["last_message_keys"] = list(data.keys())[:6]
            out["has_data"] = data is not None
        except Exception:
            pass
        # Race control dedupe window
        try:
            win = getattr(obj, "_seen_ids_order", None)
            if win is not None:
                out["racecontrol_dedupe_size"] = len(win)
                out["racecontrol_window_maxlen"] = getattr(win, "maxlen", None)
        except Exception:
            pass
        # Drivers coordinator snapshot
        try:
            state = getattr(obj, "_state", None)
            if isinstance(state, dict):
                drivers = state.get("drivers") or {}
                out["drivers_count"] = len(drivers)
                out["leader_rn"] = state.get("leader_rn")
                out["frozen"] = bool(state.get("frozen"))
        except Exception:
            pass
        return out

    diags: dict[str, Any] = {
        "options": async_redact_data(options, TO_REDACT),
        "live_bus": live_bus,
        "coordinators": {
            "track_status": _coord_diag(reg.get("track_status_coordinator")),
            "session_status": _coord_diag(reg.get("session_status_coordinator")),
            "session_info": _coord_diag(reg.get("session_info_coordinator")),
            "race_control": _coord_diag(reg.get("race_control_coordinator")),
            "weather_data": _coord_diag(reg.get("weather_data_coordinator")),
            "lap_count": _coord_diag(reg.get("lap_count_coordinator")),
            "drivers": _coord_diag(reg.get("drivers_coordinator")),
        },
    }

    return diags


