"""HTTP regressions for bounded unauthenticated callback rate limiting."""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.components.http import KEY_HASS
import pytest

from custom_components.f1_sensor import auth_http
from custom_components.f1_sensor.const import DOMAIN


@pytest.fixture
def rate_limit_clock(monkeypatch):
    """Use a small client budget and advance only the callback clock."""
    clock = SimpleNamespace(now=datetime.now(UTC))
    monkeypatch.setattr(auth_http, "_utcnow", lambda: clock.now)
    monkeypatch.setattr(auth_http, "AUTH_CALLBACK_MAX_CLIENTS", 4, raising=False)
    return clock


def _request(hass, remote: str | None, *, body: bytes = b"{") -> Mock:
    request = Mock(content_length=len(body), query={}, remote=remote)
    request.app = {KEY_HASS: hass}
    request.read = AsyncMock(return_value=body)
    return request


def _new_pairing_request(
    hass, remote: str
) -> tuple[auth_http.F1TvPairingSession, str, Mock]:
    session = auth_http.async_create_f1tv_pairing_session(
        hass,
        flow_id="rate-limit-pairing",
        callback_url="https://ha.example.com/api/f1_sensor/auth/f1tv/callback",
    )
    assert session is not None
    claims = (
        {"alg": "RS256", "typ": "JWT"},
        {"exp": int((datetime.now(UTC) + timedelta(days=2)).timestamp())},
    )
    encoded_parts = [
        base64.urlsafe_b64encode(json.dumps(part).encode()).rstrip(b"=").decode()
        for part in claims
    ]
    token = ".".join([*encoded_parts, "signature"])
    request = _request(
        hass,
        remote,
        body=json.dumps(
            {
                "session_id": session.session_id,
                "nonce": session.nonce,
                "subscription_token": token,
            }
        ).encode(),
    )
    return session, token, request


@pytest.mark.parametrize("address_prefix", ["192.0.2.", "2001:db8::"])
async def test_callback_address_churn_keeps_client_table_bounded(
    hass, rate_limit_clock, address_prefix
) -> None:
    """New unauthenticated addresses cannot grow retained limiter state."""
    view = auth_http.F1TvAuthCallbackView()
    capacity = auth_http.AUTH_CALLBACK_MAX_CLIENTS

    for index in range(capacity * 5):
        request = _request(hass, f"{address_prefix}{index + 1}")
        response = await view.post(request)
        attempts = hass.data[DOMAIN][auth_http.AUTH_CALLBACK_ATTEMPTS]

        assert len(attempts) <= capacity
        if index < capacity:
            assert response.status == HTTPStatus.BAD_REQUEST
            request.read.assert_awaited_once()
        else:
            assert response.status == HTTPStatus.TOO_MANY_REQUESTS
            assert json.loads(response.body) == {"ok": False, "code": "rate_limited"}
            assert response.headers["Retry-After"] == "60"
            request.read.assert_not_awaited()
            assert request.remote not in attempts


async def test_callback_other_traffic_reclaims_clients_at_exact_window_end(
    hass, rate_limit_clock
) -> None:
    """Expired sources disappear even if they never contact the view again."""
    view = auth_http.F1TvAuthCallbackView()
    for index in range(auth_http.AUTH_CALLBACK_MAX_CLIENTS):
        await view.post(_request(hass, f"192.0.2.{index + 1}"))

    rate_limit_clock.now += auth_http.AUTH_CALLBACK_RATE_WINDOW - timedelta(seconds=1)
    request = _request(hass, "2001:db8::99")
    response = await view.post(request)
    assert response.status == HTTPStatus.TOO_MANY_REQUESTS
    request.read.assert_not_awaited()
    assert request.remote not in hass.data[DOMAIN][auth_http.AUTH_CALLBACK_ATTEMPTS]

    rate_limit_clock.now += timedelta(seconds=1)
    response = await view.post(request)

    assert response.status == HTTPStatus.BAD_REQUEST
    request.read.assert_awaited_once()
    attempts = hass.data[DOMAIN][auth_http.AUTH_CALLBACK_ATTEMPTS]
    assert attempts == {request.remote: [rate_limit_clock.now.timestamp()]}


async def test_callback_address_churn_cannot_reset_an_active_clients_quota(
    hass, rate_limit_clock
) -> None:
    """Capacity pressure cannot evict a source that has exhausted its quota."""
    view = auth_http.F1TvAuthCallbackView()
    limited_remote = "192.0.2.1"
    for _ in range(auth_http.AUTH_CALLBACK_RATE_LIMIT):
        response = await view.post(_request(hass, limited_remote))
        assert response.status == HTTPStatus.BAD_REQUEST
    for index in range(1, auth_http.AUTH_CALLBACK_MAX_CLIENTS):
        await view.post(_request(hass, f"192.0.2.{index + 1}"))
    attempts = hass.data[DOMAIN][auth_http.AUTH_CALLBACK_ATTEMPTS]
    original_attempts = {
        remote: timestamps.copy() for remote, timestamps in attempts.items()
    }

    for index in range(auth_http.AUTH_CALLBACK_MAX_CLIENTS * 5):
        request = _request(hass, f"2001:db8::{index + 1}")
        response = await view.post(request)
        assert response.status == HTTPStatus.TOO_MANY_REQUESTS
        request.read.assert_not_awaited()

    request = _request(hass, limited_remote)
    response = await view.post(request)

    assert response.status == HTTPStatus.TOO_MANY_REQUESTS
    request.read.assert_not_awaited()
    assert hass.data[DOMAIN][auth_http.AUTH_CALLBACK_ATTEMPTS] == original_attempts


async def test_callback_tracked_client_can_complete_pairing_at_capacity(
    hass, monkeypatch, rate_limit_clock
) -> None:
    """A full address table does not deny an admitted user's valid pairing."""
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
    view = auth_http.F1TvAuthCallbackView()
    remote = "192.0.2.1"
    for index in range(auth_http.AUTH_CALLBACK_MAX_CLIENTS):
        await view.post(_request(hass, f"192.0.2.{index + 1}"))
    session, token, request = _new_pairing_request(hass, remote)

    response = await view.post(request)

    assert response.status == HTTPStatus.OK
    assert json.loads(response.body)["code"] == "connected"
    request.read.assert_awaited_once()
    result = auth_http.async_pop_f1tv_pairing_session_result(
        hass, session.session_id, "rate-limit-pairing"
    )
    assert result is not None
    assert result[0] == f"Bearer {token}"
    assert result[1].configured is True
    assert len(hass.data[DOMAIN][auth_http.AUTH_CALLBACK_ATTEMPTS]) == (
        auth_http.AUTH_CALLBACK_MAX_CLIENTS
    )


async def test_callback_new_valid_pairing_recovers_after_capacity_expires(
    hass, monkeypatch, rate_limit_clock
) -> None:
    """Capacity rejection preserves a valid session for the next available slot."""
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
    view = auth_http.F1TvAuthCallbackView()
    for index in range(auth_http.AUTH_CALLBACK_MAX_CLIENTS):
        await view.post(_request(hass, f"192.0.2.{index + 1}"))
    session, token, request = _new_pairing_request(hass, "2001:db8::99")
    rate_limit_clock.now += auth_http.AUTH_CALLBACK_RATE_WINDOW - timedelta(seconds=1)

    response = await view.post(request)

    assert response.status == HTTPStatus.TOO_MANY_REQUESTS
    assert json.loads(response.body) == {"ok": False, "code": "rate_limited"}
    assert response.headers["Retry-After"] == "60"
    request.read.assert_not_awaited()
    assert session.used is False
    assert session.auth_header is None
    assert session.session_id in hass.data[DOMAIN][auth_http.AUTH_PAIRING_SESSIONS]
    assert request.remote not in hass.data[DOMAIN][auth_http.AUTH_CALLBACK_ATTEMPTS]

    rate_limit_clock.now += timedelta(seconds=1)
    response = await view.post(request)

    assert response.status == HTTPStatus.OK
    assert json.loads(response.body)["code"] == "connected"
    request.read.assert_awaited_once()
    result = auth_http.async_pop_f1tv_pairing_session_result(
        hass, session.session_id, "rate-limit-pairing"
    )
    assert result is not None
    assert result[0] == f"Bearer {token}"
    assert result[1].configured is True
    assert hass.data[DOMAIN][auth_http.AUTH_CALLBACK_ATTEMPTS] == {
        request.remote: [rate_limit_clock.now.timestamp()]
    }


@pytest.mark.parametrize("remote", ["192.0.2.1", None])
async def test_callback_blocked_attempts_do_not_extend_the_window(
    hass, rate_limit_clock, remote
) -> None:
    """A source recovers at the original deadline despite rejected retries."""
    view = auth_http.F1TvAuthCallbackView()
    for _ in range(auth_http.AUTH_CALLBACK_RATE_LIMIT):
        response = await view.post(_request(hass, remote))
        assert response.status == HTTPStatus.BAD_REQUEST
    admitted_at = rate_limit_clock.now.timestamp()
    rate_limit_clock.now += auth_http.AUTH_CALLBACK_RATE_WINDOW - timedelta(seconds=1)

    for _ in range(3):
        request = _request(hass, remote)
        response = await view.post(request)
        assert response.status == HTTPStatus.TOO_MANY_REQUESTS
        request.read.assert_not_awaited()
    assert hass.data[DOMAIN][auth_http.AUTH_CALLBACK_ATTEMPTS] == {
        remote or "unknown": [admitted_at] * auth_http.AUTH_CALLBACK_RATE_LIMIT
    }

    rate_limit_clock.now += timedelta(seconds=1)
    response = await view.post(_request(hass, remote))

    assert response.status == HTTPStatus.BAD_REQUEST
    assert hass.data[DOMAIN][auth_http.AUTH_CALLBACK_ATTEMPTS] == {
        remote or "unknown": [rate_limit_clock.now.timestamp()]
    }


async def test_callback_expiry_reopens_only_the_expired_part_of_client_quota(
    hass, rate_limit_clock
) -> None:
    """Sliding expiry retains newer attempts and restores only expired slots."""
    view = auth_http.F1TvAuthCallbackView()
    remote = "192.0.2.1"
    first_batch = auth_http.AUTH_CALLBACK_RATE_LIMIT // 2
    second_batch = auth_http.AUTH_CALLBACK_RATE_LIMIT - first_batch
    for _ in range(first_batch):
        await view.post(_request(hass, remote))
    rate_limit_clock.now += auth_http.AUTH_CALLBACK_RATE_WINDOW / 2
    second_batch_at = rate_limit_clock.now.timestamp()
    for _ in range(second_batch):
        await view.post(_request(hass, remote))
    assert (
        await view.post(_request(hass, remote))
    ).status == HTTPStatus.TOO_MANY_REQUESTS

    rate_limit_clock.now += auth_http.AUTH_CALLBACK_RATE_WINDOW / 2
    for _ in range(first_batch):
        response = await view.post(_request(hass, remote))
        assert response.status == HTTPStatus.BAD_REQUEST
    request = _request(hass, remote)
    response = await view.post(request)

    assert response.status == HTTPStatus.TOO_MANY_REQUESTS
    request.read.assert_not_awaited()
    assert hass.data[DOMAIN][auth_http.AUTH_CALLBACK_ATTEMPTS][remote] == (
        [second_batch_at] * second_batch
        + [rate_limit_clock.now.timestamp()] * first_batch
    )


async def test_callback_concurrent_new_sources_reserve_capacity_before_body_read(
    hass, rate_limit_clock
) -> None:
    """Requests suspended in body reads already count against table capacity."""
    view = auth_http.F1TvAuthCallbackView()
    capacity = auth_http.AUTH_CALLBACK_MAX_CLIENTS
    reads_started = asyncio.Event()
    release_reads = asyncio.Event()
    started = 0

    async def read_body() -> bytes:
        nonlocal started
        started += 1
        if started >= capacity:
            reads_started.set()
        await release_reads.wait()
        return b"{"

    requests = [
        _request(hass, f"2001:db8::{index + 1}") for index in range(capacity * 3)
    ]
    for request in requests:
        request.read = AsyncMock(side_effect=read_body)
    tasks = [asyncio.create_task(view.post(request)) for request in requests]
    try:
        await asyncio.wait_for(reads_started.wait(), timeout=5)
        attempts = hass.data[DOMAIN][auth_http.AUTH_CALLBACK_ATTEMPTS]
        assert len(attempts) == capacity
        assert started == capacity
        assert sum(task.done() for task in tasks) == len(requests) - capacity
    finally:
        release_reads.set()
        responses = await asyncio.gather(*tasks)

    assert (
        sum(response.status == HTTPStatus.BAD_REQUEST for response in responses)
        == capacity
    )
    assert (
        sum(response.status == HTTPStatus.TOO_MANY_REQUESTS for response in responses)
        == len(requests) - capacity
    )
    assert sum(request.read.await_count for request in requests) == capacity


async def test_callback_concurrent_requests_cannot_exceed_one_clients_quota(
    hass, rate_limit_clock
) -> None:
    """Concurrent reads do not let a single source bypass its sliding quota."""
    view = auth_http.F1TvAuthCallbackView()
    quota = auth_http.AUTH_CALLBACK_RATE_LIMIT
    reads_started = asyncio.Event()
    release_reads = asyncio.Event()
    started = 0

    async def read_body() -> bytes:
        nonlocal started
        started += 1
        if started >= quota:
            reads_started.set()
        await release_reads.wait()
        return b"{"

    requests = [_request(hass, "192.0.2.1") for _ in range(quota + 3)]
    for request in requests:
        request.read = AsyncMock(side_effect=read_body)
    tasks = [asyncio.create_task(view.post(request)) for request in requests]
    try:
        await asyncio.wait_for(reads_started.wait(), timeout=5)
        assert started == quota
        assert sum(task.done() for task in tasks) == 3
        assert hass.data[DOMAIN][auth_http.AUTH_CALLBACK_ATTEMPTS] == {
            "192.0.2.1": [rate_limit_clock.now.timestamp()] * quota
        }
    finally:
        release_reads.set()
        responses = await asyncio.gather(*tasks)

    assert (
        sum(response.status == HTTPStatus.BAD_REQUEST for response in responses)
        == quota
    )
    assert (
        sum(response.status == HTTPStatus.TOO_MANY_REQUESTS for response in responses)
        == 3
    )
