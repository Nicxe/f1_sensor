"""Behavior matrix for legacy/Core SignalR transport lifecycle paths."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import WSMsgType
import pytest

from custom_components.f1_sensor.signalr import (
    LiveBus,
    LiveConnectionState,
    SignalRAuthenticationError,
    SignalRCoreClient,
    SignalRLegacyClient,
    _response_cookie_value,
)


class _Context:
    def __init__(self, value) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return None


class _WebSocket:
    def __init__(self, messages=None, *, closed=False) -> None:
        self.messages = list(messages or [])
        self.closed = closed
        self.sent_json: list[dict] = []
        self.sent_str: list[str] = []
        self.close = AsyncMock()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop(0)

    async def send_json(self, payload) -> None:
        self.sent_json.append(payload)

    async def send_str(self, payload) -> None:
        self.sent_str.append(payload)


def _message(msg_type, data=""):
    return SimpleNamespace(type=msg_type, data=data)


def test_cookie_header_collection_path() -> None:
    headers = SimpleNamespace(
        getall=Mock(return_value=["Other=x", "ARRAffinity=abc; Path=/"])
    )
    response = SimpleNamespace(cookies={}, headers=headers)
    assert _response_cookie_value(response, "ARRAffinity") == "abc"
    assert _response_cookie_value(response, "missing") is None


@pytest.mark.asyncio
async def test_legacy_negotiation_messages_update_and_close(hass) -> None:
    response = SimpleNamespace(
        raise_for_status=Mock(),
        json=AsyncMock(return_value={"ConnectionToken": "token"}),
        cookies={"ARRAffinity": SimpleNamespace(value="cookie")},
        headers={},
    )
    websocket = _WebSocket(
        [
            _message(WSMsgType.TEXT, "bad json"),
            _message(WSMsgType.TEXT, json.dumps({"M": [{"M": "feed"}]})),
            _message(WSMsgType.TEXT, json.dumps({"R": {"TrackStatus": {}}})),
            _message(WSMsgType.CLOSED),
        ]
    )
    session = SimpleNamespace(
        get=Mock(return_value=_Context(response)),
        ws_connect=AsyncMock(return_value=websocket),
    )
    client = SignalRLegacyClient(hass, session)
    fake_task = SimpleNamespace(done=lambda: False)

    def _capture_task(coro):
        coro.close()
        return fake_task

    with patch("asyncio.create_task", side_effect=_capture_task):
        await client.connect()
    assert session.ws_connect.await_args.kwargs["headers"]["Cookie"] == (
        "ARRAffinity=cookie"
    )
    assert len(websocket.sent_json) == 1

    payloads = [payload async for payload in client.messages()]
    assert len(payloads) == 2
    await client.update_streams(["TrackStatus"])
    assert len(websocket.sent_json) == 2
    client._heartbeat_task = None
    await client.close()
    websocket.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_negotiation_and_authentication_failures(hass) -> None:
    response = SimpleNamespace(
        raise_for_status=Mock(),
        json=AsyncMock(return_value={}),
        cookies={},
        headers={},
    )
    client = SignalRLegacyClient(
        hass,
        SimpleNamespace(get=Mock(return_value=_Context(response))),
        auth_header="Bearer token",
    )
    with pytest.raises(ConnectionError, match="no connection token"):
        await client.connect()

    client.connect = AsyncMock(side_effect=RuntimeError("HTTP 403 forbidden"))
    with pytest.raises(SignalRAuthenticationError):
        await client.ensure_connection()
    client.connect = AsyncMock(side_effect=SignalRAuthenticationError("rejected"))
    with pytest.raises(SignalRAuthenticationError):
        await client.ensure_connection()

    client._ws = _WebSocket(
        [_message(WSMsgType.TEXT, json.dumps({"E": "Unauthorized"}))]
    )
    with pytest.raises(SignalRAuthenticationError):
        _ = [payload async for payload in client.messages()]


@pytest.mark.asyncio
async def test_legacy_heartbeat_closed_failure_and_cancellation(hass) -> None:
    client = SignalRLegacyClient(hass, SimpleNamespace())
    client._ws = _WebSocket(closed=True)
    with patch("asyncio.sleep", new=AsyncMock()):
        await client._heartbeat()

    client._ws = _WebSocket()
    client._ws.send_json = AsyncMock(side_effect=RuntimeError("send failed"))
    with patch("asyncio.sleep", new=AsyncMock()):
        await client._heartbeat()

    with patch("asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)):
        await client._heartbeat()


@pytest.mark.asyncio
async def test_core_negotiation_close_pending_and_stream_updates(hass) -> None:
    post_response = SimpleNamespace(
        raise_for_status=Mock(),
        json=AsyncMock(return_value={"ConnectionToken": "fallback-token"}),
    )
    websocket = _WebSocket()
    websocket.receive = AsyncMock(
        return_value=_message(
            WSMsgType.TEXT,
            '{}\x1e{"type":1,"target":"feed","arguments":["A",{}]}\x1e',
        )
    )
    session = SimpleNamespace(
        options=Mock(side_effect=RuntimeError("options unavailable")),
        post=Mock(return_value=_Context(post_response)),
        ws_connect=AsyncMock(return_value=websocket),
    )
    client = SignalRCoreClient(hass, session)
    await client.connect()
    pending = [payload async for payload in client.messages()]
    assert pending[0]["M"][0]["M"] == "feed"
    await client.update_streams(["TrackStatus"])
    await client.update_streams(["SessionInfo"])
    assert client._next_invocation_id == 3
    await client.close()
    websocket.close.assert_awaited_once()

    missing = SignalRCoreClient(hass, session)
    post_response.json = AsyncMock(return_value={})
    with pytest.raises(ConnectionError, match="no connection token"):
        await missing.connect()


@pytest.mark.asyncio
async def test_core_messages_close_records_and_auth_mapping(hass) -> None:
    client = SignalRCoreClient(hass, SimpleNamespace(), auth_header="Bearer token")
    client._ws = _WebSocket()
    assert [payload async for payload in client.messages()] == []
    assert await client._translate_record({"type": 3, "result": "bad"}) is None
    assert await client._translate_record({"type": 99}) is None
    client._raise_for_close_record({"type": 7})
    with pytest.raises(ConnectionError, match="server closed"):
        client._raise_for_close_record({"type": 7, "error": "server problem"})
    with pytest.raises(SignalRAuthenticationError):
        client._raise_for_close_record({"type": 7, "error": "403 forbidden"})

    client.connect = AsyncMock(side_effect=RuntimeError("401 unauthorized"))
    with pytest.raises(SignalRAuthenticationError):
        await client.ensure_connection()


@pytest.mark.asyncio
async def test_live_bus_start_retry_shutdown_and_live_recovery(
    hass, monkeypatch
) -> None:
    empty = LiveBus(hass, AsyncMock(), requested_streams=set())
    await empty.start()
    assert empty.connection_state is LiveConnectionState.STOPPED

    bus = LiveBus(hass, AsyncMock(), jitter_source=lambda _a, _b: 0)
    bus._running = True
    await bus.start()
    bus._outage_logged = True
    bus._connection_state = LiveConnectionState.RETRYING
    bus._mark_connection_live()
    assert bus.connection_state is LiveConnectionState.LIVE
    assert bus._outage_logged is False
    bus._mark_connection_live()

    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    await bus._wait_before_retry("connection closed")
    await bus._wait_before_retry("network error")
    await bus._wait_before_retry("network error")
    assert bus.connection_state is LiveConnectionState.RETRYING

    bus._running = False
    client = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("close failed")))
    bus._client = client
    await bus.async_close()
    assert bus._client is None


@pytest.mark.asyncio
async def test_transport_empty_close_and_protocol_edge_paths(hass) -> None:
    """Transport lifecycle branches stay bounded on empty and closed sockets."""
    legacy = SignalRLegacyClient(hass, SimpleNamespace())
    assert [payload async for payload in legacy.messages()] == []
    legacy.connect = AsyncMock(side_effect=RuntimeError("network unavailable"))
    with pytest.raises(RuntimeError, match="network unavailable"):
        await legacy.ensure_connection()

    legacy._ws = _WebSocket()
    with patch(
        "asyncio.sleep",
        new=AsyncMock(side_effect=[None, asyncio.CancelledError()]),
    ):
        await legacy._heartbeat()
    assert legacy._ws.sent_json == [legacy._subscribe_msg]

    legacy._heartbeat_task = asyncio.create_task(asyncio.sleep(60))
    await legacy.close()
    assert legacy._heartbeat_task is None

    core = SignalRCoreClient(hass, SimpleNamespace())
    assert [payload async for payload in core.messages()] == []
    await core.update_streams(["TrackStatus"])
    core.connect = AsyncMock(side_effect=SignalRAuthenticationError("rejected"))
    with pytest.raises(SignalRAuthenticationError):
        await core.ensure_connection()

    core._pending_records = [{"type": 7}]
    assert [payload async for payload in core.messages()] == []
    core._pending_records = []
    core._ws = _WebSocket(
        [
            _message(WSMsgType.TEXT, "invalid json"),
            _message(WSMsgType.TEXT, json.dumps({"type": 7})),
            _message(WSMsgType.CLOSED),
        ]
    )
    assert [payload async for payload in core.messages()] == []


@pytest.mark.asyncio
async def test_core_handshake_rejects_closed_socket(hass) -> None:
    response = SimpleNamespace(
        raise_for_status=Mock(),
        json=AsyncMock(return_value={"connectionToken": "token"}),
    )
    websocket = _WebSocket()
    websocket.receive = AsyncMock(return_value=_message(WSMsgType.CLOSED))
    session = SimpleNamespace(
        options=Mock(side_effect=RuntimeError("options unavailable")),
        post=Mock(return_value=_Context(response)),
        ws_connect=AsyncMock(return_value=websocket),
    )

    with pytest.raises(ConnectionError, match="closed during handshake"):
        await SignalRCoreClient(hass, session).connect()
