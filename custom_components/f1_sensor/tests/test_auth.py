from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import json

import pytest

from custom_components.f1_sensor.auth import (
    evaluate_f1tv_auth_header,
    validate_replacement_auth_header,
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
