"""Shared helpers for authenticated team radio media."""

from __future__ import annotations

import hashlib
from typing import Any

STATIC_BASE = "https://livetiming.formula1.com/static"


def team_radio_clip_id(capture: dict[str, Any]) -> str:
    """Return a stable ID for one published team radio clip."""
    identity = "|".join(
        str(capture.get(key) or "").strip() for key in ("Utc", "RacingNumber", "Path")
    )
    return hashlib.sha256(identity.encode()).hexdigest()[:20]


def resolve_team_radio_source_url(
    capture: dict[str, Any],
    *,
    session_path: str | None = None,
    year: int | None = None,
) -> str | None:
    """Resolve one official archive URL without exposing authorization."""
    path = str(capture.get("Path") or "").strip()
    if not path:
        return None
    static_root = str(
        capture.get("_static_root") or capture.get("static_root") or ""
    ).strip()
    if static_root:
        return f"{static_root.rstrip('/')}/{path.lstrip('/')}"
    normalized_session = str(session_path or "").strip().strip("/")
    if not normalized_session:
        return None
    if year and not normalized_session.startswith(f"{int(year)}/"):
        normalized_session = f"{int(year)}/{normalized_session}"
    return f"{STATIC_BASE}/{normalized_session}/{path.lstrip('/')}"
