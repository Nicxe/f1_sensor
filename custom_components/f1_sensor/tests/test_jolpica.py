from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
import json
import time
from unittest.mock import AsyncMock, patch

from aiohttp import ClientConnectionError, ClientResponseError
import pytest

from custom_components.f1_sensor.jolpica import (
    JolpicaClient,
    JolpicaConfigurationError,
    JolpicaHTTPError,
    JolpicaInvalidRequestError,
    JolpicaRateLimitError,
    JolpicaRouteNotFoundError,
    JolpicaTemporaryError,
)

_URL = "https://api.jolpi.ca/ergast/f1/current.json"
_USER_AGENT = "HomeAssistantF1Sensor/1.0.0 HomeAssistant/2026.7.0"


class _Response:
    def __init__(
        self,
        status: int = 200,
        *,
        payload: object | None = None,
        headers: dict[str, str] | None = None,
        gate: asyncio.Event | None = None,
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self._payload = payload if payload is not None else {"MRData": {}}
        self._gate = gate

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise ClientResponseError(
                None,
                (),
                status=self.status,
                message=f"HTTP {self.status}",
                headers=self.headers,
            )

    async def text(self) -> str:
        if self._gate is not None:
            await self._gate.wait()
        return json.dumps(self._payload)


class _Session:
    def __init__(
        self,
        responses: list[_Response] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.responses = list(responses or [_Response()])
        self.error = error
        self.calls: list[dict[str, object]] = []

    def get(self, url, *, params=None, headers=None, allow_redirects=True):
        self.calls.append(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "allow_redirects": allow_redirects,
            }
        )
        if self.error is not None:
            raise self.error
        if not self.responses:
            raise AssertionError("Unexpected request")
        return self.responses.pop(0)


async def _client(hass, session: _Session, **kwargs) -> JolpicaClient:
    client = JolpicaClient(hass, session, _USER_AGENT, **kwargs)
    with patch.object(client._store, "async_load", AsyncMock(return_value=None)):
        await client.async_initialize()
    return client


async def test_requires_canonical_user_agent(hass) -> None:
    client = JolpicaClient(hass, _Session(), "Python/3")
    with (
        patch.object(client._store, "async_load", AsyncMock(return_value=None)),
        pytest.raises(JolpicaConfigurationError),
    ):
        await client.async_initialize()


@pytest.mark.parametrize(
    ("url", "params"),
    [
        ("http://api.jolpi.ca/ergast/f1/current.json", None),
        ("https://www.api.jolpi.ca/ergast/f1/current.json", None),
        ("https://api.jolpi.ca:443/ergast/f1/current.json", None),
        (_URL, {"limit": 101}),
        (_URL, {"limit": 0}),
        (f"{_URL}?limit=200", None),
    ],
)
async def test_rejects_noncanonical_or_excessive_requests(
    hass, url: str, params: dict[str, int] | None
) -> None:
    session = _Session()
    client = await _client(hass, session)

    with pytest.raises(JolpicaInvalidRequestError):
        await client.async_get_json(url, params=params)

    assert session.calls == []


async def test_identical_concurrent_requests_are_coalesced_and_shielded(hass) -> None:
    gate = asyncio.Event()
    session = _Session([_Response(gate=gate)])
    client = await _client(hass, session)

    first = asyncio.create_task(
        client.async_get_json(_URL, params={"limit": 1, "offset": 0})
    )
    second = asyncio.create_task(
        client.async_get_json(_URL, params={"offset": 0, "limit": 1})
    )
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    gate.set()
    assert await second == {"MRData": {}}
    assert len(session.calls) == 1
    assert session.calls[0]["headers"] == {"User-Agent": _USER_AGENT}
    assert session.calls[0]["allow_redirects"] is False


async def test_five_concurrent_requests_respect_second_limit(hass) -> None:
    session = _Session([_Response() for _ in range(5)])
    client = await _client(hass, session)

    with patch("custom_components.f1_sensor.jolpica._SECOND_WINDOW", 0.01):
        await asyncio.gather(
            *(
                client.async_get_json(
                    _URL,
                    params={"limit": 1, "offset": offset},
                )
                for offset in range(5)
            )
        )

    assert len(session.calls) == 5
    assert all(call["headers"] == {"User-Agent": _USER_AGENT} for call in session.calls)
    assert client.diagnostics()["requests_last_hour"] == 5


async def test_451st_hourly_attempt_is_blocked_without_network(hass) -> None:
    session = _Session()
    client = await _client(hass, session, max_queue_wait=0.001)
    client._hour_requests.extend([time.time()] * 450)

    with pytest.raises(JolpicaRateLimitError) as raised:
        await client.async_get_json(_URL, params={"limit": 1})

    assert raised.value.source == "local"
    assert session.calls == []
    assert client.diagnostics()["blocked_requests"] == 1


async def test_diagnostics_count_entry_cache_without_exposing_keys(hass) -> None:
    client = await _client(hass, _Session())
    hass.data.setdefault("f1_sensor", {})["entry"] = {
        "http_cache": {"private-request-a": object(), "private-request-b": object()}
    }

    diagnostics = client.diagnostics()

    assert diagnostics["cache_entries"] == 2
    assert "private-request-a" not in str(diagnostics)


async def test_numeric_retry_after_retries_once(hass) -> None:
    session = _Session(
        [
            _Response(429, headers={"Retry-After": "0"}),
            _Response(payload={"ok": True}),
        ]
    )
    client = await _client(hass, session)

    assert await client.async_get_json(_URL, params={"limit": 1}) == {"ok": True}
    assert len(session.calls) == 2
    assert client.diagnostics()["requests_last_hour"] == 2
    assert client.diagnostics()["latest_429"] is not None


async def test_second_429_is_not_retried(hass) -> None:
    session = _Session(
        [
            _Response(429, headers={"Retry-After": "0"}),
            _Response(429, headers={"Retry-After": "0"}),
        ]
    )
    client = await _client(hass, session)

    with pytest.raises(JolpicaRateLimitError) as raised:
        await client.async_get_json(_URL, params={"limit": 1})

    assert raised.value.source == "server"
    assert len(session.calls) == 2


async def test_rate_limit_retry_can_be_disabled_for_diagnostic_request(
    hass,
) -> None:
    session = _Session(
        [
            _Response(429, headers={"Retry-After": "0"}),
            _Response(payload={"would": "hide the rate limit"}),
        ]
    )
    client = await _client(hass, session)

    with pytest.raises(JolpicaRateLimitError):
        await client.async_get_json(
            _URL,
            params={"limit": 1},
            retry_on_rate_limit=False,
        )

    assert len(session.calls) == 1


def test_retry_after_supports_http_date_and_missing_backoff() -> None:
    now = datetime.now(tz=UTC).replace(microsecond=0)
    future = now + timedelta(seconds=8)
    delay = JolpicaClient._parse_retry_after(
        format_datetime(future, usegmt=True), now=now.timestamp()
    )
    assert delay == 8
    assert JolpicaClient._parse_retry_after(None, now=now.timestamp()) is None


async def test_missing_retry_after_backoff_is_shared_and_capped(hass) -> None:
    client = await _client(hass, _Session())

    delays = []
    for _ in range(8):
        client._cooldown_until = 0
        delays.append(client._record_server_limit(None))

    assert delays == [1, 2, 4, 8, 16, 32, 60, 60]
    with patch.object(client._store, "async_save", AsyncMock()):
        await client.async_close()


async def test_missing_retry_after_uses_backoff_without_retry_past_budget(
    hass,
) -> None:
    session = _Session([_Response(429)])
    client = await _client(hass, session)

    with pytest.raises(JolpicaRateLimitError) as raised:
        await client.async_get_json(_URL, params={"limit": 1}, timeout=0.01)

    assert raised.value.retry_after == 1
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    ("status", "exception_type"),
    [
        (302, JolpicaHTTPError),
        (404, JolpicaRouteNotFoundError),
        (400, JolpicaHTTPError),
        (500, JolpicaHTTPError),
    ],
)
async def test_http_errors_are_not_retried(
    hass, status: int, exception_type: type[Exception]
) -> None:
    session = _Session([_Response(status)])
    client = await _client(hass, session)

    with pytest.raises(exception_type):
        await client.async_get_json(_URL, params={"limit": 1})

    assert len(session.calls) == 1


async def test_network_errors_are_not_retried(hass) -> None:
    session = _Session(error=ClientConnectionError("offline"))
    client = await _client(hass, session)

    with pytest.raises(JolpicaTemporaryError):
        await client.async_get_json(_URL, params={"limit": 1})

    assert len(session.calls) == 1


async def test_persisted_budget_and_cooldown_survive_reload(hass) -> None:
    now = time.time()
    stored = {
        "request_timestamps": [now - 30, now - 10],
        "cooldown_until": now + 30,
        "backoff_step": 3,
        "latest_429": now - 1,
    }
    client = JolpicaClient(hass, _Session(), _USER_AGENT)
    with patch.object(client._store, "async_load", AsyncMock(return_value=stored)):
        await client.async_initialize()

    diagnostics = client.diagnostics()
    assert diagnostics["requests_last_hour"] == 2
    assert diagnostics["cooldown_remaining_seconds"] > 0
    assert diagnostics["latest_429"] is not None

    save = AsyncMock()
    with patch.object(client._store, "async_save", save):
        await client.async_close()
    payload = save.await_args.args[0]
    assert len(payload["request_timestamps"]) == 2
    assert payload["cooldown_until"] == stored["cooldown_until"]


async def test_close_cancels_inflight_request_and_flushes_once(hass) -> None:
    gate = asyncio.Event()
    client = await _client(hass, _Session([_Response(gate=gate)]))
    request = asyncio.create_task(client.async_get_json(_URL, params={"limit": 1}))
    await asyncio.sleep(0)

    save = AsyncMock()
    with patch.object(client._store, "async_save", save):
        await client.async_close()

    with pytest.raises(asyncio.CancelledError):
        await request
    save.assert_awaited_once()
