"""HTTP pairing callback for F1TV Token Helper."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
import json
import logging
import secrets
from typing import Any
from urllib.parse import urlencode

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .auth import (
    F1TvAuthStatus,
    async_set_runtime_f1tv_auth_status,
    async_update_f1tv_auth_repair_issue,
    f1tv_auth_repair_issue_id,
    is_auth_feature_enabled,
    validate_replacement_auth_header,
)
from .const import CONF_LIVE_TIMING_AUTH_HEADER, DOMAIN

_LOGGER = logging.getLogger(__name__)

AUTH_CALLBACK_PATH = "/api/f1_sensor/auth/f1tv/callback"
AUTH_CALLBACK_NAME = "api:f1_sensor:f1tv_auth_callback"
AUTH_PAIRING_SESSIONS = "f1tv_auth_pairing_sessions"
AUTH_HTTP_VIEW_REGISTERED = "f1tv_auth_http_view_registered"
AUTH_PAIRING_TTL = timedelta(minutes=5)
AUTH_CALLBACK_MAX_BODY_BYTES = 16 * 1024
F1TV_HELPER_PAIRING_URL = "https://nicxe.github.io/f1_sensor/help/f1tv-token-helper"


@dataclass
class F1TvPairingSession:
    """Short-lived runtime pairing session."""

    session_id: str
    nonce: str
    entry_id: str | None
    callback_url: str
    helper_url: str
    created_at: datetime
    expires_at: datetime
    flow_id: str | None = None
    flow_manager: str | None = None
    used: bool = False
    auth_header: str | None = None
    auth_status: F1TvAuthStatus | None = None

    @property
    def expires_at_iso(self) -> str:
        """Return the expiry as an ISO-8601 string."""
        return self.expires_at.astimezone(UTC).isoformat()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _pairing_sessions(hass: HomeAssistant) -> dict[str, F1TvPairingSession]:
    root = hass.data.setdefault(DOMAIN, {})
    sessions = root.setdefault(AUTH_PAIRING_SESSIONS, {})
    return sessions if isinstance(sessions, dict) else {}


@callback
def _cleanup_expired_pairing_sessions(hass: HomeAssistant) -> None:
    sessions = _pairing_sessions(hass)
    now = _utcnow()
    for session_id, session in list(sessions.items()):
        if not isinstance(session, F1TvPairingSession) or session.expires_at <= now:
            sessions.pop(session_id, None)


def _build_helper_url(
    *,
    callback_url: str,
    session_id: str,
    nonce: str,
    expires_at: datetime,
    flow_id: str | None,
) -> str:
    query = {
        "callback_url": callback_url,
        "session_id": session_id,
        "nonce": nonce,
        "expires_at": expires_at.astimezone(UTC).isoformat(),
    }
    if flow_id:
        query["flow_id"] = flow_id
    return f"{F1TV_HELPER_PAIRING_URL}?{urlencode(query)}"


def async_get_f1tv_callback_url(hass: HomeAssistant) -> str:
    """Return the absolute callback URL for the current Home Assistant instance."""
    try:
        base_url = get_url(
            hass,
            allow_internal=True,
            allow_external=True,
            allow_cloud=True,
            allow_ip=True,
            prefer_external=False,
        )
    except NoURLAvailableError:
        base_url = ""

    if not base_url:
        return AUTH_CALLBACK_PATH
    return f"{base_url.rstrip('/')}{AUTH_CALLBACK_PATH}"


@callback
def async_create_f1tv_pairing_session(
    hass: HomeAssistant,
    entry: ConfigEntry | None = None,
    *,
    flow_id: str | None = None,
    flow_manager: str | None = None,
    callback_url: str | None = None,
) -> F1TvPairingSession | None:
    """Create a short-lived pairing session for one config entry or setup flow."""
    if not is_auth_feature_enabled() or (entry is None and flow_id is None):
        return None

    _cleanup_expired_pairing_sessions(hass)
    now = _utcnow()
    session_id = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(32)
    expires_at = now + AUTH_PAIRING_TTL
    callback = callback_url or async_get_f1tv_callback_url(hass)
    helper_url = _build_helper_url(
        callback_url=callback,
        session_id=session_id,
        nonce=nonce,
        expires_at=expires_at,
        flow_id=flow_id,
    )
    session = F1TvPairingSession(
        session_id=session_id,
        nonce=nonce,
        entry_id=entry.entry_id if entry is not None else None,
        callback_url=callback,
        helper_url=helper_url,
        created_at=now,
        expires_at=expires_at,
        flow_id=flow_id,
        flow_manager=flow_manager,
    )
    _pairing_sessions(hass)[session_id] = session
    return session


def async_pop_f1tv_pairing_session_result(
    hass: HomeAssistant, session_id: str, flow_id: str | None
) -> tuple[str, F1TvAuthStatus] | None:
    """Return and remove a completed flow-only pairing result."""
    session = _pairing_sessions(hass).get(session_id)
    if (
        session is None
        or session.entry_id is not None
        or session.flow_id != flow_id
        or not session.used
        or not session.auth_header
        or session.auth_status is None
    ):
        return None
    _pairing_sessions(hass).pop(session_id, None)
    return session.auth_header, session.auth_status


def _error_response(code: str, status: HTTPStatus) -> tuple[HTTPStatus, dict[str, Any]]:
    return status, {"ok": False, "code": code}


async def async_process_f1tv_pairing_callback(
    hass: HomeAssistant,
    payload: dict[str, Any],
    *,
    query: dict[str, str] | None = None,
    body_size: int | None = None,
) -> tuple[HTTPStatus, dict[str, Any]]:
    """Validate a helper callback and store the replacement token."""
    if not is_auth_feature_enabled():
        return _error_response("gate_closed", HTTPStatus.NOT_FOUND)

    if query and "subscription_token" in query:
        return _error_response("token_in_query", HTTPStatus.BAD_REQUEST)

    if body_size is not None and body_size > AUTH_CALLBACK_MAX_BODY_BYTES:
        return _error_response("body_too_large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)

    session_id = str(payload.get("session_id") or "").strip()
    nonce = str(payload.get("nonce") or "").strip()
    subscription_token = str(payload.get("subscription_token") or "").strip()
    if not session_id or not nonce or not subscription_token:
        return _error_response("missing_field", HTTPStatus.BAD_REQUEST)

    _cleanup_expired_pairing_sessions(hass)
    session = _pairing_sessions(hass).get(session_id)
    if session is None:
        return _error_response("expired_pairing", HTTPStatus.GONE)
    if session.used:
        return _error_response("pairing_already_used", HTTPStatus.GONE)
    if session.expires_at <= _utcnow():
        _pairing_sessions(hass).pop(session_id, None)
        return _error_response("expired_pairing", HTTPStatus.GONE)
    if not secrets.compare_digest(session.nonce, nonce):
        return _error_response("invalid_nonce", HTTPStatus.FORBIDDEN)

    auth_header, error, status = validate_replacement_auth_header(
        f"Bearer {subscription_token}"
    )
    if error is not None or auth_header is None:
        return _error_response(error or "invalid_auth_header", HTTPStatus.BAD_REQUEST)

    if session.entry_id is None:
        session.used = True
        session.auth_header = auth_header
        session.auth_status = status
        await _async_complete_pairing_flow(hass, session, session_id)
        return HTTPStatus.OK, {
            "ok": True,
            "code": "connected",
            "expires_at": status.expires_at_iso,
        }

    entry = hass.config_entries.async_get_entry(session.entry_id)
    if entry is None:
        return _error_response("entry_not_found", HTTPStatus.NOT_FOUND)

    session.used = True
    data = dict(entry.data)
    data[CONF_LIVE_TIMING_AUTH_HEADER] = auth_header
    hass.config_entries.async_update_entry(entry, data=data)
    async_update_f1tv_auth_repair_issue(hass, entry, status)
    async_set_runtime_f1tv_auth_status(hass, entry.entry_id, status)

    issue_id = f1tv_auth_repair_issue_id(entry.entry_id)
    ir.async_delete_issue(hass, DOMAIN, issue_id)
    await hass.config_entries.async_reload(entry.entry_id)

    await _async_complete_pairing_flow(hass, session, session_id)

    return HTTPStatus.OK, {
        "ok": True,
        "code": "connected",
        "expires_at": status.expires_at_iso,
    }


async def _async_complete_pairing_flow(
    hass: HomeAssistant, session: F1TvPairingSession, session_id: str
) -> None:
    """Notify the owning flow that helper pairing has completed."""
    if not session.flow_id:
        return
    with suppress(Exception):
        if session.flow_manager == "repairs":
            manager = repairs_flow_manager(hass)
            if manager is not None:
                await manager.async_configure(
                    session.flow_id, {"session_id": session_id}
                )
            return
        await hass.config_entries.flow.async_configure(
            session.flow_id, {"session_id": session_id}
        )


class F1TvAuthCallbackView(HomeAssistantView):
    """Receive token helper callbacks."""

    url = AUTH_CALLBACK_PATH
    name = AUTH_CALLBACK_NAME
    requires_auth = False
    cors_allowed = False

    async def post(self, request: web.Request) -> web.Response:
        """Receive a token from the browser extension."""
        hass = request.app[KEY_HASS]
        content_length = request.content_length
        if content_length is not None and content_length > AUTH_CALLBACK_MAX_BODY_BYTES:
            status, response = _error_response(
                "body_too_large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE
            )
            return self.json(response, status_code=status)

        try:
            body = await request.read()
        except Exception:  # noqa: BLE001
            status, response = _error_response("invalid_body", HTTPStatus.BAD_REQUEST)
            return self.json(response, status_code=status)

        if len(body) > AUTH_CALLBACK_MAX_BODY_BYTES:
            status, response = _error_response(
                "body_too_large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE
            )
            return self.json(response, status_code=status)

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            status, response = _error_response("invalid_json", HTTPStatus.BAD_REQUEST)
            return self.json(response, status_code=status)

        if not isinstance(payload, dict):
            status, response = _error_response("invalid_json", HTTPStatus.BAD_REQUEST)
            return self.json(response, status_code=status)

        status, response = await async_process_f1tv_pairing_callback(
            hass,
            payload,
            query=dict(request.query.items()),
            body_size=len(body),
        )
        return self.json(response, status_code=status)


@callback
def async_setup_f1tv_auth_http(hass: HomeAssistant) -> None:
    """Register the helper callback view when the auth feature is enabled."""
    if not is_auth_feature_enabled():
        return

    root = hass.data.setdefault(DOMAIN, {})
    if root.get(AUTH_HTTP_VIEW_REGISTERED):
        return
    http_server = getattr(hass, "http", None)
    if http_server is None:
        return
    http_server.register_view(F1TvAuthCallbackView)
    root[AUTH_HTTP_VIEW_REGISTERED] = True
