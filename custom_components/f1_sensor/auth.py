"""Safe F1TV token status helpers."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import json
import logging
import math
from typing import Any

from aiohttp import ClientError, ClientTimeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later

from . import const
from .const import CONF_LIVE_TIMING_AUTH_HEADER, DOMAIN
from .helpers import normalize_live_timing_auth_header

_LOGGER = logging.getLogger(__name__)

F1_RETRIEVE_SUBSCRIBER_URL = (
    "https://api.formula1.com/v1/account/Subscriber/RetrieveSubscriber"
)
F1_API_KEY = "fCUCjWrKPu9ylJwRAv8BpGLEgiAuThx7"
F1_SYSTEM_ID = "60a9ad84-e93d-480f-80d6-af37494f2e22"

AUTH_STATUS_NOT_CONFIGURED = "not_configured"
AUTH_STATUS_VALID = "valid"
AUTH_STATUS_EXPIRING_SOON = "expiring_soon"
AUTH_STATUS_EXPIRED = "expired"
AUTH_STATUS_INVALID = "invalid"
AUTH_STATUS_REJECTED = "rejected"

AUTH_STATUS_OPTIONS = (
    AUTH_STATUS_NOT_CONFIGURED,
    AUTH_STATUS_VALID,
    AUTH_STATUS_EXPIRING_SOON,
    AUTH_STATUS_EXPIRED,
    AUTH_STATUS_INVALID,
    AUTH_STATUS_REJECTED,
)

AUTH_EXPIRING_SOON = timedelta(hours=24)
AUTH_MIN_REPLACEMENT_REMAINING = timedelta(minutes=10)
AUTH_REPAIR_STATUSES = frozenset(
    {AUTH_STATUS_EXPIRED, AUTH_STATUS_INVALID, AUTH_STATUS_REJECTED}
)
AUTH_REPAIR_TRANSLATION_KEY = "f1tv_token_attention_required"

AUTH_RUNTIME_STATUS = "f1tv_auth_status"
AUTH_RUNTIME_STATUS_LISTENERS = "f1tv_auth_status_listeners"
AUTH_RUNTIME_STATUS_REFRESH_UNSUB = "f1tv_auth_status_refresh_unsub"
AUTH_RUNTIME_RENEWAL = "f1tv_token_renewal"
AUTH_RENEWAL_RETRY_SECONDS = 60
AUTH_RENEWAL_MAX_RETRY_SECONDS = 3600


@dataclass(frozen=True)
class F1TvAuthStatus:
    """Redacted F1TV token status."""

    status: str
    configured: bool
    header: str = field(default="", repr=False, compare=False)
    expires_at: datetime | None = None
    reason: str | None = None
    used_for_live_timing: bool = False

    @property
    def issue_required(self) -> bool:
        """Return True when Home Assistant should show a repair issue."""
        return self.configured and self.status in AUTH_REPAIR_STATUSES

    @property
    def expires_at_iso(self) -> str | None:
        """Return the token expiry as an ISO-8601 string."""
        if self.expires_at is None:
            return None
        return self.expires_at.astimezone(UTC).isoformat()

    def as_safe_dict(self) -> dict[str, Any]:
        """Return diagnostics-safe metadata."""
        return {
            "status": self.status,
            "configured": self.configured,
            "expires_at": self.expires_at_iso,
            "reason": self.reason,
            "used_for_live_timing": self.used_for_live_timing,
        }


def is_auth_transport_enabled() -> bool:
    """Return True when F1TV auth may be used for live timing transport."""
    return is_auth_feature_enabled()


def is_auth_feature_enabled() -> bool:
    """Return True when any F1TV auth surface may be visible or active."""
    return const.ENABLE_F1TV_AUTH


def is_auth_health_visible(status: F1TvAuthStatus | None) -> bool:
    """Return True when redacted token health may be shown."""
    return is_auth_feature_enabled()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _decode_jwt_part(part: str) -> dict[str, Any]:
    padded = part + "=" * (-len(part) % 4)
    decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    value = json.loads(decoded.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JWT part is not a JSON object")
    return value


def _extract_bearer_token(header: str) -> str:
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise ValueError("missing_bearer_scheme")
    return parts[1].strip()


def extract_f1tv_session_id(header: str | None) -> str | None:
    """Extract the Ascendon SessionId from an F1TV live timing JWT."""
    header = normalize_live_timing_auth_header(header)
    if not header:
        return None
    try:
        token = _extract_bearer_token(header)
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = _decode_jwt_part(parts[1])
        session_id = payload.get("SessionId")
        if isinstance(session_id, str) and session_id.strip():
            return session_id.strip()
    except (ValueError, TypeError):
        return None
    return None


def evaluate_f1tv_auth_header(
    value: object,
    *,
    now: datetime | None = None,
    used_for_live_timing: bool = False,
) -> F1TvAuthStatus:
    """Return redacted status for a saved F1TV authorization header."""
    header = normalize_live_timing_auth_header(value)
    if not header:
        return F1TvAuthStatus(
            status=AUTH_STATUS_NOT_CONFIGURED,
            configured=False,
            used_for_live_timing=False,
        )

    now = (now or _utcnow()).astimezone(UTC)

    try:
        token = _extract_bearer_token(header)
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("malformed_jwt")
        _decode_jwt_part(parts[0])
        payload = _decode_jwt_part(parts[1])
        exp = payload.get("exp")
        if not isinstance(exp, (int, float)):
            return F1TvAuthStatus(
                status=AUTH_STATUS_INVALID,
                configured=True,
                header=header,
                reason="missing_exp",
            )
        expires_at = datetime.fromtimestamp(exp, tz=UTC)
    except Exception as err:
        return F1TvAuthStatus(
            status=AUTH_STATUS_INVALID,
            configured=True,
            header=header,
            reason=str(err) or "invalid_jwt",
        )

    if expires_at <= now:
        status = AUTH_STATUS_EXPIRED
        reason = "expired"
        used_for_live_timing = False
    elif expires_at - now <= AUTH_EXPIRING_SOON:
        status = AUTH_STATUS_EXPIRING_SOON
        reason = "expiring_soon"
    else:
        status = AUTH_STATUS_VALID
        reason = None

    return F1TvAuthStatus(
        status=status,
        configured=True,
        header=header,
        expires_at=expires_at,
        reason=reason,
        used_for_live_timing=used_for_live_timing,
    )


def validate_replacement_auth_header(
    value: object, *, now: datetime | None = None
) -> tuple[str | None, str | None, F1TvAuthStatus]:
    """Validate a user-submitted replacement token.

    Returns ``(normalized_header, error_key, status)``. ``error_key`` is ``None``
    when the header can be saved.
    """
    status = evaluate_f1tv_auth_header(value, now=now)
    if not status.configured:
        return None, "auth_header_required", status
    if status.status == AUTH_STATUS_INVALID:
        reason = status.reason or "invalid_auth_header"
        if reason == "missing_exp":
            return None, "auth_token_missing_exp", status
        return None, "invalid_auth_header", status
    if status.status == AUTH_STATUS_EXPIRED:
        return None, "auth_token_expired", status

    now = (now or _utcnow()).astimezone(UTC)
    if status.expires_at is None:
        return None, "auth_token_missing_exp", status
    if status.expires_at - now <= AUTH_MIN_REPLACEMENT_REMAINING:
        return None, "auth_token_expiring_soon", status
    return status.header, None, status


class F1TvRenewalResult(StrEnum):
    """Separate temporary renewal failures from a required browser sign-in."""

    RENEWED = "renewed"
    RETRY_LATER = "retry_later"
    PAIRING_REQUIRED = "pairing_required"
    CANCELLED = "cancelled"


def _session_expired(session_id: str) -> bool:
    """Use an embedded expiry when available; let F1 validate opaque sessions."""
    try:
        parts = session_id.split(".")
        if len(parts) != 3:
            return False
        expiry = _decode_jwt_part(parts[1]).get("exp")
        return (
            isinstance(expiry, (int, float))
            and math.isfinite(expiry)
            and expiry <= _utcnow().timestamp()
        )
    except (ValueError, TypeError):
        return False


class F1TvTokenRenewal:
    """Own one renewal request and its retry timer for a loaded config entry."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, runtime: dict[str, Any]
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.runtime = runtime
        self.task: asyncio.Task[F1TvRenewalResult] | None = None
        self.retry_unsub: Callable[[], None] | None = None
        self.retry_delay = AUTH_RENEWAL_RETRY_SECONDS
        self.closed = False
        self.blocked_header: str | None = None
        self.replacement_header: str | None = None

    def _is_current(self, header: str | None) -> bool:
        return (
            not self.closed
            and is_auth_feature_enabled()
            and _runtime_data(self.hass, self.entry.entry_id) is self.runtime
            and self.hass.config_entries.async_get_entry(self.entry.entry_id)
            is self.entry
            and self.entry.disabled_by is None
            and self.entry.data.get(CONF_LIVE_TIMING_AUTH_HEADER) == header
        )

    @callback
    def async_start(self) -> asyncio.Task[F1TvRenewalResult] | None:
        """Start at most one request, respecting a pending retry or session failure."""
        header = self.entry.data.get(CONF_LIVE_TIMING_AUTH_HEADER)
        if not self._is_current(header) or self.blocked_header == header:
            return None
        if self.task is not None and not self.task.done():
            return self.task
        if self.retry_unsub is not None:
            return None
        self.task = self.entry.async_create_background_task(
            self.hass,
            self._async_attempt(header),
            "Renew F1TV access",
            eager_start=False,
        )
        self.task.add_done_callback(self._async_finished)
        return self.task

    @callback
    def _async_finished(self, task: asyncio.Task[F1TvRenewalResult]) -> None:
        """Reload only after the entry-owned request has finished."""
        if (
            not task.cancelled()
            and task.result() == F1TvRenewalResult.RENEWED
            and self._is_current(self.replacement_header)
        ):
            self.hass.config_entries.async_schedule_reload(self.entry.entry_id)

    @callback
    def _retry(self) -> F1TvRenewalResult:
        """Retry temporary failures with a capped exponential backoff."""
        if self.retry_delay == AUTH_RENEWAL_RETRY_SECONDS:
            _LOGGER.warning("Unable to renew F1TV access; retrying automatically")
        delay = self.retry_delay
        self.retry_delay = min(delay * 2, AUTH_RENEWAL_MAX_RETRY_SECONDS)

        @callback
        def retry(_now: datetime | None = None) -> None:
            self.retry_unsub = None
            self.async_start()

        self.retry_unsub = async_call_later(self.hass, delay, retry)
        return F1TvRenewalResult.RETRY_LATER

    @callback
    def _require_pairing(self, header: str) -> F1TvRenewalResult:
        """Stop renewing this session and expose the existing repair flow."""
        self.blocked_header = header
        status = evaluate_f1tv_auth_header(header)
        # A failed renewal need not invalidate the still-usable access token.
        # Leave runtime token health alone, but surface the required sign-in.
        async_update_f1tv_auth_repair_issue(
            self.hass,
            self.entry,
            replace(status, status=AUTH_STATUS_REJECTED, reason="session_rejected"),
        )
        return F1TvRenewalResult.PAIRING_REQUIRED

    async def _async_attempt(self, current_header: str) -> F1TvRenewalResult:
        if not self._is_current(current_header):
            return F1TvRenewalResult.CANCELLED
        session_id = extract_f1tv_session_id(current_header)
        if not session_id or _session_expired(session_id):
            return self._require_pairing(current_header)

        session = async_get_clientsession(self.hass)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like"
                " Gecko) Chrome/133.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/json",
            "apikey": F1_API_KEY,
            "CD-SystemId": F1_SYSTEM_ID,
            "cd-sessionid": session_id,
            "orderSubmitted": "true",
        }
        try:
            async with session.post(
                F1_RETRIEVE_SUBSCRIBER_URL,
                headers=headers,
                json={},
                timeout=ClientTimeout(total=15),
                allow_redirects=False,
            ) as response:
                http_status = response.status
                data = await response.json() if http_status == 200 else None
        except (ClientError, TimeoutError, ValueError):
            if not self._is_current(current_header):
                return F1TvRenewalResult.CANCELLED
            return self._retry()

        if not self._is_current(current_header):
            return F1TvRenewalResult.CANCELLED
        if http_status in (401, 403):
            return self._require_pairing(current_header)
        if http_status != 200:
            return self._retry()

        subscriber = data.get("data") if isinstance(data, dict) else None
        sub_token = (
            subscriber.get("subscriptionToken")
            if isinstance(subscriber, dict)
            else None
        )
        if not isinstance(sub_token, str) or not sub_token.strip():
            return self._retry()
        auth_header, error, status = validate_replacement_auth_header(
            f"Bearer {sub_token}"
        )
        previous = evaluate_f1tv_auth_header(current_header)
        if (
            error is not None
            or auth_header is None
            or status.status != AUTH_STATUS_VALID
            or auth_header == current_header
            or (
                previous.expires_at is not None
                and status.expires_at <= previous.expires_at
            )
        ):
            return self._retry()

        new_data = dict(self.entry.data)
        new_data[CONF_LIVE_TIMING_AUTH_HEADER] = auth_header
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        async_update_f1tv_auth_repair_issue(self.hass, self.entry, status)
        async_set_runtime_f1tv_auth_status(self.hass, self.entry.entry_id, status)
        self.replacement_header = auth_header
        _LOGGER.info("Renewed F1TV access until %s", status.expires_at_iso)
        return F1TvRenewalResult.RENEWED

    async def async_close(self) -> None:
        """Cancel retries and requests on unload, including setup rollback."""
        self.closed = True
        if self.retry_unsub is not None:
            self.retry_unsub()
            self.retry_unsub = None
        if self.task is not None and not self.task.done():
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task


@callback
def _renewal_manager(
    hass: HomeAssistant, entry: ConfigEntry
) -> F1TvTokenRenewal | None:
    runtime = _runtime_data(hass, entry.entry_id)
    if (
        runtime is None
        or hass.config_entries.async_get_entry(entry.entry_id) is not entry
    ):
        return None
    manager = runtime.get(AUTH_RUNTIME_RENEWAL)
    if not isinstance(manager, F1TvTokenRenewal):
        manager = runtime[AUTH_RUNTIME_RENEWAL] = F1TvTokenRenewal(hass, entry, runtime)
    return manager


async def async_renew_f1tv_token(
    hass: HomeAssistant, entry: ConfigEntry
) -> F1TvRenewalResult:
    """Renew access or tell the manual button whether browser pairing is needed."""
    if not is_auth_feature_enabled():
        return F1TvRenewalResult.CANCELLED
    header = entry.data.get(CONF_LIVE_TIMING_AUTH_HEADER)
    if not extract_f1tv_session_id(header):
        return F1TvRenewalResult.PAIRING_REQUIRED
    manager = _renewal_manager(hass, entry)
    if manager is None or manager.closed:
        return F1TvRenewalResult.CANCELLED
    if manager.blocked_header == header:
        return F1TvRenewalResult.PAIRING_REQUIRED
    task = manager.async_start()
    if task is None:
        return F1TvRenewalResult.RETRY_LATER
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        if task.cancelled():
            return F1TvRenewalResult.CANCELLED
        raise


def rejected_f1tv_auth_status(status: F1TvAuthStatus) -> F1TvAuthStatus:
    """Return a rejected status for a token the server refused."""
    return replace(
        status,
        status=AUTH_STATUS_REJECTED,
        reason="signalr_rejected",
        used_for_live_timing=False,
    )


def _issue_id(entry_id: str) -> str:
    return f"f1tv_token_{entry_id}"


def f1tv_auth_repair_issue_id(entry_id: str) -> str:
    """Return the stable repair issue id for a config entry."""
    return _issue_id(entry_id)


@callback
def async_update_f1tv_auth_repair_issue(
    hass: HomeAssistant, entry: ConfigEntry, status: F1TvAuthStatus
) -> None:
    """Create or clear the redacted F1TV token repair issue."""
    issue_id = _issue_id(entry.entry_id)
    if not is_auth_feature_enabled():
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    runtime = _runtime_data(hass, entry.entry_id) or {}
    renewal = runtime.get(AUTH_RUNTIME_RENEWAL)
    if (
        isinstance(renewal, F1TvTokenRenewal)
        and not renewal.closed
        and renewal.blocked_header == status.header
    ):
        status = replace(status, status=AUTH_STATUS_REJECTED, reason="session_rejected")
    if not status.issue_required:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return

    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        data={
            "entry_id": entry.entry_id,
            "status": status.status,
            "expires_at": status.expires_at_iso,
        },
        is_fixable=True,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=AUTH_REPAIR_TRANSLATION_KEY,
        translation_placeholders={
            "name": entry.title or entry.data.get("sensor_name", "F1"),
            "status": status.status,
            "expires_at": status.expires_at_iso or "unknown",
        },
    )


def _runtime_data(hass: HomeAssistant, entry_id: str) -> dict[str, Any] | None:
    root = hass.data.get(DOMAIN)
    if not isinstance(root, dict):
        return None
    data = root.get(entry_id)
    return data if isinstance(data, dict) else None


@callback
def async_set_runtime_f1tv_auth_status(
    hass: HomeAssistant, entry_id: str, status: F1TvAuthStatus
) -> None:
    """Store runtime auth status and notify listeners."""
    data = _runtime_data(hass, entry_id)
    if data is None:
        return
    data[AUTH_RUNTIME_STATUS] = status
    listeners = list(data.get(AUTH_RUNTIME_STATUS_LISTENERS) or [])
    for listener in listeners:
        listener(status)


@callback
def async_add_f1tv_auth_status_listener(
    hass: HomeAssistant,
    entry_id: str,
    listener: Callable[[F1TvAuthStatus], None],
) -> Callable[[], None]:
    """Listen for token health updates for one entry."""
    data = _runtime_data(hass, entry_id)
    if data is None:
        return lambda: None
    listeners = data.setdefault(AUTH_RUNTIME_STATUS_LISTENERS, [])
    listeners.append(listener)

    def _remove() -> None:
        if listener in listeners:
            listeners.remove(listener)

    return _remove


def _next_refresh_delay(status: F1TvAuthStatus, now: datetime) -> float | None:
    if status.expires_at is None or status.status in (
        AUTH_STATUS_NOT_CONFIGURED,
        AUTH_STATUS_EXPIRED,
        AUTH_STATUS_INVALID,
        AUTH_STATUS_REJECTED,
    ):
        return None

    target = status.expires_at
    if status.status == AUTH_STATUS_VALID:
        target = status.expires_at - AUTH_EXPIRING_SOON
        if target <= now:
            target = status.expires_at

    delay = (target - now).total_seconds()
    if delay <= 0:
        return 0
    return delay


@callback
def async_schedule_f1tv_auth_status_refresh(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Schedule the next token status transition without polling."""
    data = _runtime_data(hass, entry.entry_id)
    if data is None:
        return

    if old_unsub := data.pop(AUTH_RUNTIME_STATUS_REFRESH_UNSUB, None):
        old_unsub()

    if not is_auth_feature_enabled():
        async_update_f1tv_auth_repair_issue(
            hass,
            entry,
            F1TvAuthStatus(
                status=AUTH_STATUS_NOT_CONFIGURED,
                configured=False,
                used_for_live_timing=False,
            ),
        )
        return

    current = data.get(AUTH_RUNTIME_STATUS)
    if not isinstance(current, F1TvAuthStatus):
        current = evaluate_f1tv_auth_header(
            entry.data.get(CONF_LIVE_TIMING_AUTH_HEADER)
        )

    delay = _next_refresh_delay(current, _utcnow())
    if current.status in (AUTH_STATUS_EXPIRING_SOON, AUTH_STATUS_EXPIRED):
        if extract_f1tv_session_id(entry.data.get(CONF_LIVE_TIMING_AUTH_HEADER)):
            if manager := _renewal_manager(hass, entry):
                manager.async_start()
    if delay is None:
        return

    @callback
    def _refresh(_now: datetime | None = None) -> None:
        previous = data.get(AUTH_RUNTIME_STATUS)
        used = bool(
            isinstance(previous, F1TvAuthStatus) and previous.used_for_live_timing
        )
        status = evaluate_f1tv_auth_header(
            entry.data.get(CONF_LIVE_TIMING_AUTH_HEADER),
            used_for_live_timing=used,
        )
        if status.status in AUTH_REPAIR_STATUSES:
            status = replace(status, used_for_live_timing=False)
        async_set_runtime_f1tv_auth_status(hass, entry.entry_id, status)
        async_update_f1tv_auth_repair_issue(hass, entry, status)

        async_schedule_f1tv_auth_status_refresh(hass, entry)

    data[AUTH_RUNTIME_STATUS_REFRESH_UNSUB] = async_call_later(hass, delay, _refresh)


@callback
def async_cancel_f1tv_auth_status_refresh(hass: HomeAssistant, entry_id: str) -> None:
    """Cancel a scheduled token status transition."""
    data = _runtime_data(hass, entry_id)
    if data is None:
        return
    if old_unsub := data.pop(AUTH_RUNTIME_STATUS_REFRESH_UNSUB, None):
        old_unsub()
