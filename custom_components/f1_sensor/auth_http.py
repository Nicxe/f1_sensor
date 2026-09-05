"""HTTP pairing callback for F1TV Token Helper."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
import ipaddress
import json
import logging
import secrets
from typing import Any
from urllib.parse import urlencode, urlsplit

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import http, issue_registry as ir
from homeassistant.helpers.config_entry_oauth2_flow import HEADER_FRONTEND_BASE
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
AUTH_CALLBACK_ATTEMPTS = "f1tv_auth_callback_attempts"
AUTH_CALLBACK_METRICS = "f1tv_auth_callback_metrics"
AUTH_PAIRING_TTL = timedelta(minutes=5)
AUTH_CALLBACK_MAX_BODY_BYTES = 16 * 1024
AUTH_CALLBACK_RATE_LIMIT = 12
AUTH_CALLBACK_RATE_WINDOW = timedelta(minutes=1)
F1TV_HELPER_PAIRING_URL = "https://nicxe.github.io/f1_sensor/help/f1tv-token-helper"


@dataclass
class F1TvPairingSession:
    """Short-lived runtime pairing session."""

    session_id: str = field(repr=False, compare=False)
    nonce: str = field(repr=False, compare=False)
    entry_id: str | None
    callback_url: str = field(repr=False, compare=False)
    helper_url: str = field(repr=False, compare=False)
    created_at: datetime
    expires_at: datetime
    flow_id: str | None = None
    flow_manager: str | None = None
    used: bool = False
    auth_header: str | None = field(default=None, repr=False, compare=False)
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


def _is_local_callback_host(hostname: str) -> bool:
    """Return whether an HTTP callback host is local to the HA installation."""
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost" or normalized.endswith(".local"):
        return True
    with suppress(ValueError):
        address = ipaddress.ip_address(normalized)
        return address.is_loopback or address.is_private or address.is_link_local
    return False


def _is_safe_callback_url(value: str) -> bool:
    """Allow HTTPS callbacks and explicitly configured local HTTP callbacks."""
    if value == AUTH_CALLBACK_PATH:
        return True
    parsed = urlsplit(value)
    if (
        parsed.path != AUTH_CALLBACK_PATH
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or not parsed.hostname
    ):
        return False
    if parsed.scheme == "https":
        return True
    return parsed.scheme == "http" and _is_local_callback_host(parsed.hostname)


def _callback_rate_limited(hass: HomeAssistant, client_id: str) -> bool:
    """Apply a bounded per-client sliding-window callback limit."""
    root = hass.data.setdefault(DOMAIN, {})
    state = root.setdefault(AUTH_CALLBACK_ATTEMPTS, {})
    if not isinstance(state, dict):
        state = {}
        root[AUTH_CALLBACK_ATTEMPTS] = state
    now = _utcnow().timestamp()
    cutoff = now - AUTH_CALLBACK_RATE_WINDOW.total_seconds()
    attempts = [
        timestamp
        for timestamp in state.get(client_id, [])
        if isinstance(timestamp, (int, float)) and timestamp > cutoff
    ]
    if len(attempts) >= AUTH_CALLBACK_RATE_LIMIT:
        state[client_id] = attempts
        return True
    attempts.append(now)
    state[client_id] = attempts
    return False


def _record_callback_failure(hass: HomeAssistant, code: str) -> None:
    """Record aggregate failure telemetry without client or token details."""
    root = hass.data.setdefault(DOMAIN, {})
    metrics = root.setdefault(
        AUTH_CALLBACK_METRICS,
        {"failures_total": 0, "failure_codes": {}},
    )
    if not isinstance(metrics, dict):
        return
    metrics["failures_total"] = int(metrics.get("failures_total", 0)) + 1
    failure_codes = metrics.setdefault("failure_codes", {})
    if isinstance(failure_codes, dict):
        failure_codes[code] = int(failure_codes.get(code, 0)) + 1


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
    if (request := http.current_request.get()) is not None and (
        frontend_base := request.headers.get(HEADER_FRONTEND_BASE)
    ):
        candidate = f"{frontend_base.rstrip('/')}{AUTH_CALLBACK_PATH}"
        if _is_safe_callback_url(candidate):
            return candidate
        _LOGGER.warning("Ignored unsafe browser-visible F1TV callback URL")

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
    candidate = f"{base_url.rstrip('/')}{AUTH_CALLBACK_PATH}"
    if _is_safe_callback_url(candidate):
        return candidate
    _LOGGER.warning("Ignored unsafe configured F1TV callback URL")
    return AUTH_CALLBACK_PATH


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
    if not _is_safe_callback_url(callback):
        _LOGGER.warning("Refused to create F1TV pairing with an unsafe callback URL")
        return None
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

    def _json_response(
        self,
        hass: HomeAssistant,
        payload: dict[str, Any],
        status: HTTPStatus,
    ) -> web.Response:
        """Return a non-cacheable response and record only aggregate failures."""
        response = self.json(payload, status_code=status)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if status >= HTTPStatus.BAD_REQUEST:
            _record_callback_failure(hass, str(payload.get("code") or "unknown"))
        return response

    async def post(self, request: web.Request) -> web.Response:
        """Receive a token from the browser extension."""
        hass = request.app[KEY_HASS]
        client_id = request.remote or "unknown"
        if _callback_rate_limited(hass, client_id):
            status, response = _error_response(
                "rate_limited", HTTPStatus.TOO_MANY_REQUESTS
            )
            result = self._json_response(hass, response, status)
            result.headers["Retry-After"] = str(
                int(AUTH_CALLBACK_RATE_WINDOW.total_seconds())
            )
            return result
        content_length = request.content_length
        if content_length is not None and content_length > AUTH_CALLBACK_MAX_BODY_BYTES:
            status, response = _error_response(
                "body_too_large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE
            )
            return self._json_response(hass, response, status)

        try:
            body = await request.read()
        except Exception:  # noqa: BLE001
            status, response = _error_response("invalid_body", HTTPStatus.BAD_REQUEST)
            return self._json_response(hass, response, status)

        if len(body) > AUTH_CALLBACK_MAX_BODY_BYTES:
            status, response = _error_response(
                "body_too_large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE
            )
            return self._json_response(hass, response, status)

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            status, response = _error_response("invalid_json", HTTPStatus.BAD_REQUEST)
            return self._json_response(hass, response, status)

        if not isinstance(payload, dict):
            status, response = _error_response("invalid_json", HTTPStatus.BAD_REQUEST)
            return self._json_response(hass, response, status)

        status, response = await async_process_f1tv_pairing_callback(
            hass,
            payload,
            query=dict(request.query.items()),
            body_size=len(body),
        )
        return self._json_response(hass, response, status)


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
