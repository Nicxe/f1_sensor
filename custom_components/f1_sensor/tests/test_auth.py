from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.f1_sensor.auth import (
    AUTH_RUNTIME_STATUS_REFRESH_UNSUB,
    F1TvAuthStatus,
    _next_refresh_delay,
    async_add_f1tv_auth_status_listener,
    async_cancel_f1tv_auth_status_refresh,
    async_schedule_f1tv_auth_status_refresh,
    async_set_runtime_f1tv_auth_status,
    evaluate_f1tv_auth_header,
    validate_replacement_auth_header,
)
from custom_components.f1_sensor.const import (
    CONF_LIVE_TIMING_AUTH_HEADER,
    DOMAIN,
)


def _part(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _jwt(payload: dict) -> str:
    return ".".join(
        (
            _part({"alg": "RS256", "typ": "JWT"}),
            _part(payload),
            "signature",
        )
    )


def test_evaluate_f1tv_auth_header_accepts_authorization_prefix() -> None:
    now = datetime(2026, 5, 1, tzinfo=UTC)
    token = _jwt({"exp": int((now + timedelta(days=2)).timestamp())})

    status = evaluate_f1tv_auth_header(f" Authorization: Bearer {token} ", now=now)

    assert status.status == "valid"
    assert status.configured is True
    assert status.header == f"Bearer {token}"
    assert status.expires_at == now + timedelta(days=2)
    assert status.as_safe_dict() == {
        "status": "valid",
        "configured": True,
        "expires_at": "2026-05-03T00:00:00+00:00",
        "reason": None,
        "used_for_live_timing": False,
    }


def test_evaluate_f1tv_auth_header_marks_expiring_soon() -> None:
    now = datetime(2026, 5, 1, tzinfo=UTC)
    token = _jwt({"exp": int((now + timedelta(hours=23)).timestamp())})

    status = evaluate_f1tv_auth_header(f"Bearer {token}", now=now)

    assert status.status == "expiring_soon"
    assert status.reason == "expiring_soon"


def test_evaluate_f1tv_auth_header_marks_expired() -> None:
    now = datetime(2026, 5, 1, tzinfo=UTC)
    token = _jwt({"exp": int((now - timedelta(seconds=1)).timestamp())})

    status = evaluate_f1tv_auth_header(f"Bearer {token}", now=now)

    assert status.status == "expired"
    assert status.reason == "expired"


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("Bearer not-a-jwt", "malformed_jwt"),
        ("raw-token", "missing_bearer_scheme"),
    ],
)
def test_evaluate_f1tv_auth_header_marks_malformed_values_invalid(
    value: str, reason: str
) -> None:
    status = evaluate_f1tv_auth_header(value)

    assert status.status == "invalid"
    assert status.configured is True
    assert reason in status.reason


def test_evaluate_f1tv_auth_header_requires_exp() -> None:
    status = evaluate_f1tv_auth_header(f"Bearer {_jwt({'iat': 1})}")

    assert status.status == "invalid"
    assert status.reason == "missing_exp"


def test_validate_replacement_auth_header_rejects_near_expiry_token() -> None:
    now = datetime(2026, 5, 1, tzinfo=UTC)
    token = _jwt({"exp": int((now + timedelta(minutes=9)).timestamp())})

    header, error, status = validate_replacement_auth_header(f"Bearer {token}", now=now)

    assert header is None
    assert error == "auth_token_expiring_soon"
    assert status.status == "expiring_soon"


def test_validate_replacement_auth_header_accepts_usable_token() -> None:
    now = datetime(2026, 5, 1, tzinfo=UTC)
    token = _jwt({"exp": int((now + timedelta(hours=1)).timestamp())})

    header, error, status = validate_replacement_auth_header(
        f"Authorization: Bearer {token}", now=now
    )

    assert header == f"Bearer {token}"
    assert error is None
    assert status.status == "expiring_soon"


def test_auth_runtime_listener_schedule_refresh_and_cancel_matrix(
    hass, monkeypatch
) -> None:
    entry = SimpleNamespace(
        entry_id="entry",
        title="F1",
        data={
            CONF_LIVE_TIMING_AUTH_HEADER: f"Bearer {_jwt({'exp': int((datetime.now(UTC) + timedelta(hours=2)).timestamp())})}"
        },
    )
    listener = Mock()
    noop = async_add_f1tv_auth_status_listener(hass, "missing", listener)
    noop()
    async_set_runtime_f1tv_auth_status(
        hass, "missing", F1TvAuthStatus(status="valid", configured=True)
    )

    runtime = {}
    hass.data.setdefault(DOMAIN, {})["entry"] = runtime
    remove = async_add_f1tv_auth_status_listener(hass, "entry", listener)
    status = evaluate_f1tv_auth_header(entry.data[CONF_LIVE_TIMING_AUTH_HEADER])
    async_set_runtime_f1tv_auth_status(hass, "entry", status)
    listener.assert_called_once_with(status)
    remove()
    remove()

    old_unsub = Mock()
    runtime[AUTH_RUNTIME_STATUS_REFRESH_UNSUB] = old_unsub
    scheduled = {}

    def call_later(_hass, delay, callback):
        scheduled.update(delay=delay, callback=callback)
        return Mock()

    monkeypatch.setattr("custom_components.f1_sensor.auth.async_call_later", call_later)
    async_schedule_f1tv_auth_status_refresh(hass, entry)
    old_unsub.assert_called_once()
    assert scheduled["delay"] > 0
    scheduled["callback"]()
    assert runtime.get("f1tv_auth_status") is not None
    async_cancel_f1tv_auth_status_refresh(hass, "entry")
    async_cancel_f1tv_auth_status_refresh(hass, "missing")

    assert (
        _next_refresh_delay(
            F1TvAuthStatus(status="expired", configured=True), datetime.now(UTC)
        )
        is None
    )
    assert (
        _next_refresh_delay(
            F1TvAuthStatus(
                status="valid",
                configured=True,
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            ),
            datetime.now(UTC),
        )
        == 0
    )


def test_auth_replacement_rejects_missing_header_and_non_object_jwt() -> None:
    header, error, _status = validate_replacement_auth_header(None)
    assert header is None
    assert error == "auth_header_required"
    token = ".".join((_part({"alg": "none"}), _part([]), "signature"))
    status = evaluate_f1tv_auth_header(f"Bearer {token}")
    assert status.status == "invalid"
