"""Authenticated Home Assistant proxy for Formula 1 team radio clips."""

from __future__ import annotations

from datetime import timedelta
from http import HTTPStatus
from typing import Any

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant

from .archive import (
    F1ArchiveAuthenticationRequired,
    F1ArchiveClient,
    F1ArchiveResponseError,
)
from .const import DOMAIN
from .team_radio_common import resolve_team_radio_source_url, team_radio_clip_id

TEAM_RADIO_MEDIA_VIEW_REGISTERED = "team_radio_media_view_registered"
TEAM_RADIO_MEDIA_PATH = f"/api/{DOMAIN}/team-radio/{{entry_id}}/{{clip_id}}"
TEAM_RADIO_MEDIA_MAX_BYTES = 10 * 1024 * 1024
TEAM_RADIO_MEDIA_CONTENT_TYPES = frozenset(
    {"audio/mpeg", "audio/mp3", "application/octet-stream"}
)


def team_radio_media_url(
    hass: HomeAssistant,
    entry_id: str,
    capture: dict[str, Any],
) -> str | None:
    """Return a temporary signed Home Assistant URL for one clip."""
    if not str(capture.get("Path") or "").strip():
        return None
    path = TEAM_RADIO_MEDIA_PATH.format(
        entry_id=entry_id,
        clip_id=team_radio_clip_id(capture),
    )
    try:
        return async_sign_path(
            hass,
            path,
            timedelta(hours=12),
            use_content_user=True,
        )
    except KeyError:
        # Minimal test harnesses may not initialize HTTP auth. A real Home
        # Assistant runtime always signs this path before exposing it.
        return path


def _find_capture(coordinator: Any, clip_id: str) -> dict[str, Any] | None:
    data = getattr(coordinator, "data", None)
    if not isinstance(data, dict):
        return None
    candidates = [data.get("latest"), *(data.get("history") or [])]
    return next(
        (
            dict(candidate)
            for candidate in candidates
            if isinstance(candidate, dict) and team_radio_clip_id(candidate) == clip_id
        ),
        None,
    )


def _source_url(runtime: dict[str, Any], capture: dict[str, Any]) -> str | None:
    supervisor = runtime.get("live_supervisor")
    window = getattr(supervisor, "current_window", None)
    session_coordinator = runtime.get("session_coordinator")
    return resolve_team_radio_source_url(
        capture,
        session_path=getattr(window, "path", None),
        session_key=getattr(window, "session_key", None),
        session_info=getattr(runtime.get("session_info_coordinator"), "data", None),
        year=getattr(session_coordinator, "year", None),
    )


class TeamRadioMediaView(HomeAssistantView):
    """Return one authenticated Formula 1 team radio clip."""

    url = TEAM_RADIO_MEDIA_PATH
    name = f"api:{DOMAIN}:team_radio_media"
    requires_auth = True

    async def get(
        self,
        request: web.Request,
        entry_id: str,
        clip_id: str,
    ) -> web.Response:
        """Proxy one known clip without exposing the F1TV token."""
        hass: HomeAssistant = request.app[KEY_HASS]
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            return self.json(
                {"error": "Entry not found"}, status_code=HTTPStatus.NOT_FOUND
            )
        runtime = hass.data.get(DOMAIN, {}).get(entry_id)
        if not isinstance(runtime, dict):
            return self.json(
                {"error": "Team radio is temporarily unavailable"},
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            )
        archive_client = runtime.get("archive_client")
        if not isinstance(archive_client, F1ArchiveClient):
            return self.json(
                {"error": "F1TV access is required"},
                status_code=HTTPStatus.FORBIDDEN,
            )
        capture = _find_capture(runtime.get("team_radio_coordinator"), clip_id)
        if capture is None:
            return self.json(
                {"error": "Clip not found"}, status_code=HTTPStatus.NOT_FOUND
            )
        source_url = _source_url(runtime, capture)
        if source_url is None:
            return self.json(
                {"error": "Clip not found"}, status_code=HTTPStatus.NOT_FOUND
            )
        try:
            audio, content_type = await archive_client.async_get_bytes(
                source_url,
                timeout_seconds=30,
                max_bytes=TEAM_RADIO_MEDIA_MAX_BYTES,
                allowed_content_types=TEAM_RADIO_MEDIA_CONTENT_TYPES,
            )
        except F1ArchiveAuthenticationRequired:
            return self.json(
                {"error": "F1TV access is required"},
                status_code=HTTPStatus.FORBIDDEN,
            )
        except (F1ArchiveResponseError, TimeoutError, ValueError):
            return self.json(
                {"error": "Team radio clip is unavailable"},
                status_code=HTTPStatus.BAD_GATEWAY,
            )
        return web.Response(
            body=audio,
            content_type=content_type,
            headers={
                "Cache-Control": "private, max-age=3600",
                "X-Content-Type-Options": "nosniff",
            },
        )


def async_register_team_radio_media_view(hass: HomeAssistant) -> None:
    """Register the authenticated media proxy once."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get(TEAM_RADIO_MEDIA_VIEW_REGISTERED):
        return
    http_server = getattr(hass, "http", None)
    if http_server is None:
        return
    http_server.register_view(TeamRadioMediaView())
    root[TEAM_RADIO_MEDIA_VIEW_REGISTERED] = True
