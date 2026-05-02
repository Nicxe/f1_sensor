"""Safe F1TV token status helpers."""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import json
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later

from . import const
from .const import CONF_LIVE_TIMING_AUTH_HEADER, DOMAIN
from .helpers import normalize_live_timing_auth_header

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


@dataclass(frozen=True)
class F1TvAuthStatus:
    """Redacted F1TV token status."""

    status: str
    configured: bool
    header: str = ""
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
    return const.ENABLE_DEVELOPMENT_MODE_UI


def is_auth_health_visible(status: F1TvAuthStatus | None) -> bool:
    """Return True when redacted token health may be shown."""
    return bool(is_auth_transport_enabled() or (status and status.configured))


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

    current = data.get(AUTH_RUNTIME_STATUS)
    if not isinstance(current, F1TvAuthStatus):
        current = evaluate_f1tv_auth_header(
            entry.data.get(CONF_LIVE_TIMING_AUTH_HEADER)
        )

    delay = _next_refresh_delay(current, _utcnow())
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
