"""Shared entity-independent data formatting and session helpers."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    LATEST_TRACK_STATUS,
)
from .helpers import (
    get_circuit_timezone,
    get_timezone,
    normalize_track_status,
)


def _extract_driver_position(info: dict | None) -> str | None:
    if not isinstance(info, dict):
        return None
    timing = info.get("timing")
    if not isinstance(timing, dict):
        return None
    pos = timing.get("position")
    if pos is None:
        return None
    try:
        pos_str = str(pos).strip()
    except Exception:
        return pos if isinstance(pos, str) else None
    return pos_str or None


def _parse_lap_time_to_secs(t: str) -> float:
    """Convert a lap time string like '1:23.247' or '23.247' to seconds."""
    if ":" in t:
        mins, secs = t.split(":", 1)
        return int(mins) * 60 + float(secs)
    return float(t)


def _combine_date_time(
    date_str: str | None, time_str: str | None, *, force_utc: bool = False
) -> str | None:
    if not date_str:
        return None
    if not time_str:
        time_str = "00:00:00Z"
    dt_str = f"{date_str}T{time_str}".replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(dt_str)
        if force_utc and dt.tzinfo is not None:
            dt = dt.astimezone(datetime.UTC)
        return dt.isoformat()
    except Exception:
        return None


def _timezone_from_location(lat, lon):
    return get_timezone(lat, lon)


def _timezone_from_circuit(circuit):
    loc = circuit.get("Location", {})
    return get_circuit_timezone(circuit.get("circuitId")) or _timezone_from_location(
        loc.get("lat"), loc.get("long")
    )


def _to_local(iso_ts, timezone):
    if not iso_ts or not timezone:
        return None
    try:
        dt = datetime.datetime.fromisoformat(iso_ts)
        return dt.astimezone(ZoneInfo(timezone)).isoformat()
    except Exception:
        return None


def _to_home(hass: HomeAssistant, iso_ts):
    if not iso_ts:
        return None
    try:
        dt = datetime.datetime.fromisoformat(iso_ts)
    except Exception:
        return None
    tzname = getattr(hass.config, "time_zone", None)
    if not tzname:
        return dt.isoformat()
    tzinfo = dt_util.get_time_zone(tzname)
    if tzinfo is None:
        return dt.isoformat()
    try:
        return dt.astimezone(tzinfo).isoformat()
    except Exception:
        return dt.isoformat()


def _to_float_value(value):
    try:
        if value is None:
            return 0.0
        s = str(value).strip()
        return float(s) if s else 0.0
    except Exception:
        return 0.0


def _hex_to_rgb(color: str | None) -> list[int] | None:
    """Convert '#RRGGBB' or 'RRGGBB' to [R, G, B], or None if invalid."""
    if not isinstance(color, str) or not color:
        return None
    s = color.lstrip("#").strip()
    if len(s) != 6:
        return None
    try:
        return [int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)]
    except ValueError:
        return None


def _map_session_status_payload(
    raw: dict | None,
    hass: HomeAssistant | None,
    *,
    is_qualifying_like: bool = False,
    qualifying_part: int | None = None,
    is_testing_session: bool = False,
) -> str | None:
    """Map raw SessionStatus payloads to semantic states."""
    if not raw:
        return None
    message = str(raw.get("Status") or raw.get("Message") or "").strip()
    started_hint = str(raw.get("Started") or "").strip()
    if message == "Started":
        return "live"
    if message == "Finished":
        if is_testing_session or (
            is_qualifying_like and qualifying_part in (None, 1, 2)
        ):
            return "break"
        return "finished"
    if message == "Finalised":
        return "finalised"
    if message == "Ends":
        return "ended"
    if message == "Inactive":
        if started_hint == "Finished":
            return "break"
        if started_hint == "Started":
            track_state = None
            try:
                cache = hass.data.get(LATEST_TRACK_STATUS) if hass is not None else None
                track_state = (
                    normalize_track_status(cache) if isinstance(cache, dict) else None
                )
            except Exception:
                track_state = None
            if track_state and track_state != "RED":
                return "live"
            return "suspended"
        return "pre"
    if message == "Aborted":
        if started_hint == "Started":
            track_state = None
            try:
                cache = hass.data.get(LATEST_TRACK_STATUS) if hass is not None else None
                track_state = (
                    normalize_track_status(cache) if isinstance(cache, dict) else None
                )
            except Exception:
                track_state = None
            if track_state and track_state != "RED":
                return "live"
            return "suspended"
        return "pre"
    return "pre"


def _session_status_mapping_context(
    coordinator, *, use_status_part: bool = False
) -> tuple[bool, int | None]:
    """Return announced qualifying context or the part owning the latest status."""
    is_qualifying_like = bool(getattr(coordinator, "is_qualifying_like_session", False))
    qualifying_part = getattr(coordinator, "qualifying_part", None)
    if use_status_part:
        status_part = getattr(coordinator, "status_qualifying_part", None)
        if status_part is not None:
            qualifying_part = status_part
    try:
        if qualifying_part is not None:
            qualifying_part = int(qualifying_part)
    except (TypeError, ValueError):
        qualifying_part = None
    return (is_qualifying_like, qualifying_part)


def _session_identity_year(value: object) -> int | None:
    """Return the UTC calendar year from a session start timestamp."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.year
