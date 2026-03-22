"""Tests for SignalRCoreClient — SignalR Core protocol implementation."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import WSMsgType

from custom_components.f1_sensor.signalr import (
    RECORD_SEP,
    SUBSCRIBE_MSG,
    SignalRCoreClient,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeWSMessage:
    """Simulate an aiohttp WebSocket message."""

    def __init__(self, msg_type: WSMsgType, data: str = "") -> None:
        self.type = msg_type
        self.data = data


class FakeWebSocket:
    """Minimal async-iterable WebSocket mock."""

    def __init__(self, messages: list[FakeWSMessage] | None = None) -> None:
        self._messages = list(messages or [])
        self._sent: list[str] = []
        self.closed = False

    async def send_str(self, data: str) -> None:
        self._sent.append(data)

    async def receive(self) -> FakeWSMessage:
        if self._messages:
            return self._messages.pop(0)
        return FakeWSMessage(WSMsgType.CLOSED)

    async def close(self) -> None:
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self) -> FakeWSMessage:
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)


def _make_client() -> SignalRCoreClient:
    hass = MagicMock()
    session = MagicMock()
    return SignalRCoreClient(hass, session)


def _core_msg(payload: dict) -> str:
    """Encode a SignalR Core message with record separator."""
    return json.dumps(payload) + RECORD_SEP


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_negotiate_options_captures_cookie():
    """OPTIONS response Set-Cookie header is parsed for AWSALBCORS."""
    client = _make_client()

    options_resp = AsyncMock()
    options_resp.headers = {"Set-Cookie": "AWSALBCORS=abc123; Path=/; Secure"}
    options_resp.__aenter__ = AsyncMock(return_value=options_resp)
    options_resp.__aexit__ = AsyncMock(return_value=False)

    post_resp = AsyncMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json = AsyncMock(return_value={"connectionToken": "tok"})
    post_resp.__aenter__ = AsyncMock(return_value=post_resp)
    post_resp.__aexit__ = AsyncMock(return_value=False)

    handshake_msg = FakeWSMessage(WSMsgType.TEXT, "{}" + RECORD_SEP)
    ws = FakeWebSocket([handshake_msg])

    client._session.options = MagicMock(return_value=options_resp)
    client._session.post = MagicMock(return_value=post_resp)
    client._session.ws_connect = AsyncMock(return_value=ws)

    await client.connect()

    assert client._cookie == "abc123"


@pytest.mark.asyncio
async def test_negotiate_post_extracts_token():
    """POST negotiate response connectionToken is used in WS connect URL."""
    client = _make_client()

    options_resp = AsyncMock()
    options_resp.headers = {}
    options_resp.__aenter__ = AsyncMock(return_value=options_resp)
    options_resp.__aexit__ = AsyncMock(return_value=False)

    post_resp = AsyncMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json = AsyncMock(return_value={"connectionToken": "my_token_42"})
    post_resp.__aenter__ = AsyncMock(return_value=post_resp)
    post_resp.__aexit__ = AsyncMock(return_value=False)

    handshake_msg = FakeWSMessage(WSMsgType.TEXT, "{}" + RECORD_SEP)
    ws = FakeWebSocket([handshake_msg])

    client._session.options = MagicMock(return_value=options_resp)
    client._session.post = MagicMock(return_value=post_resp)
    client._session.ws_connect = AsyncMock(return_value=ws)

    await client.connect()

    # Verify ws_connect was called with id=my_token_42
    call_kwargs = client._session.ws_connect.call_args
    assert call_kwargs[1]["params"]["id"] == "my_token_42"


@pytest.mark.asyncio
async def test_handshake_send_and_receive():
    """Client sends handshake and accepts empty ack."""
    client = _make_client()

    options_resp = AsyncMock()
    options_resp.headers = {}
    options_resp.__aenter__ = AsyncMock(return_value=options_resp)
    options_resp.__aexit__ = AsyncMock(return_value=False)

    post_resp = AsyncMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json = AsyncMock(return_value={"connectionToken": "t"})
    post_resp.__aenter__ = AsyncMock(return_value=post_resp)
    post_resp.__aexit__ = AsyncMock(return_value=False)

    handshake_msg = FakeWSMessage(WSMsgType.TEXT, "{}" + RECORD_SEP)
    ws = FakeWebSocket([handshake_msg])

    client._session.options = MagicMock(return_value=options_resp)
    client._session.post = MagicMock(return_value=post_resp)
    client._session.ws_connect = AsyncMock(return_value=ws)

    await client.connect()

    # First send_str should be the handshake
    handshake_sent = ws._sent[0]
    hs_json = json.loads(handshake_sent.replace(RECORD_SEP, ""))
    assert hs_json == {"protocol": "json", "version": 1}
    assert handshake_sent.endswith(RECORD_SEP)


@pytest.mark.asyncio
async def test_handshake_error_raises():
    """Handshake response with error field raises ConnectionError."""
    client = _make_client()

    options_resp = AsyncMock()
    options_resp.headers = {}
    options_resp.__aenter__ = AsyncMock(return_value=options_resp)
    options_resp.__aexit__ = AsyncMock(return_value=False)

    post_resp = AsyncMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json = AsyncMock(return_value={"connectionToken": "t"})
    post_resp.__aenter__ = AsyncMock(return_value=post_resp)
    post_resp.__aexit__ = AsyncMock(return_value=False)

    error_hs = FakeWSMessage(
        WSMsgType.TEXT,
        json.dumps({"error": "Unsupported protocol"}) + RECORD_SEP,
    )
    ws = FakeWebSocket([error_hs])

    client._session.options = MagicMock(return_value=options_resp)
    client._session.post = MagicMock(return_value=post_resp)
    client._session.ws_connect = AsyncMock(return_value=ws)

    with pytest.raises(ConnectionError, match="handshake error"):
        await client.connect()


@pytest.mark.asyncio
async def test_subscribe_format():
    """Subscribe message has correct Core format with stream list."""
    client = _make_client()

    options_resp = AsyncMock()
    options_resp.headers = {}
    options_resp.__aenter__ = AsyncMock(return_value=options_resp)
    options_resp.__aexit__ = AsyncMock(return_value=False)

    post_resp = AsyncMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json = AsyncMock(return_value={"connectionToken": "t"})
    post_resp.__aenter__ = AsyncMock(return_value=post_resp)
    post_resp.__aexit__ = AsyncMock(return_value=False)

    handshake_msg = FakeWSMessage(WSMsgType.TEXT, "{}" + RECORD_SEP)
    ws = FakeWebSocket([handshake_msg])

    client._session.options = MagicMock(return_value=options_resp)
    client._session.post = MagicMock(return_value=post_resp)
    client._session.ws_connect = AsyncMock(return_value=ws)

    await client.connect()

    # Second send_str should be the subscribe message
    subscribe_sent = ws._sent[1]
    sub_json = json.loads(subscribe_sent.replace(RECORD_SEP, ""))
    assert sub_json["type"] == 1
    assert sub_json["target"] == "Subscribe"
    assert sub_json["arguments"] == SUBSCRIBE_MSG["A"]
    assert sub_json["invocationId"] == "0"
    assert subscribe_sent.endswith(RECORD_SEP)


@pytest.mark.asyncio
async def test_type1_feed_translated():
    """Type 1 invocation (feed) is translated to legacy M-format."""
    client = _make_client()
    feed_msg = FakeWSMessage(
        WSMsgType.TEXT,
        _core_msg(
            {
                "type": 1,
                "target": "feed",
                "arguments": ["TrackStatus", {"Status": "1", "Message": "AllClear"}],
            }
        ),
    )
    client._ws = FakeWebSocket([feed_msg])

    results = []
    async for payload in client.messages():
        results.append(payload)

    assert len(results) == 1
    assert results[0] == {
        "M": [
            {
                "H": "Streaming",
                "M": "feed",
                "A": ["TrackStatus", {"Status": "1", "Message": "AllClear"}],
            }
        ]
    }


@pytest.mark.asyncio
async def test_type3_completion_translated():
    """Type 3 completion (initial state) is translated to legacy R-format."""
    client = _make_client()
    completion_msg = FakeWSMessage(
        WSMsgType.TEXT,
        _core_msg(
            {
                "type": 3,
                "invocationId": "0",
                "result": {
                    "SessionStatus": {"Status": "Started"},
                    "TrackStatus": {"Status": "1"},
                },
            }
        ),
    )
    client._ws = FakeWebSocket([completion_msg])

    results = []
    async for payload in client.messages():
        results.append(payload)

    assert len(results) == 1
    assert results[0] == {
        "R": {
            "SessionStatus": {"Status": "Started"},
            "TrackStatus": {"Status": "1"},
        }
    }


@pytest.mark.asyncio
async def test_type6_ping_pong():
    """Type 6 ping is answered with pong and nothing is yielded."""
    client = _make_client()
    ping_msg = FakeWSMessage(WSMsgType.TEXT, _core_msg({"type": 6}))
    # Add a feed message after ping to ensure the generator continues
    feed_msg = FakeWSMessage(
        WSMsgType.TEXT,
        _core_msg({"type": 1, "target": "feed", "arguments": ["Heartbeat", {}]}),
    )
    ws = FakeWebSocket([ping_msg, feed_msg])
    client._ws = ws

    results = []
    async for payload in client.messages():
        results.append(payload)

    # Only the feed message should be yielded, not the ping
    assert len(results) == 1
    assert results[0]["M"][0]["A"][0] == "Heartbeat"

    # Verify pong was sent
    pong_sent = [s for s in ws._sent if '"type": 6' in s or '"type":6' in s]
    assert len(pong_sent) == 1
    pong_json = json.loads(pong_sent[0].replace(RECORD_SEP, ""))
    assert pong_json == {"type": 6}


@pytest.mark.asyncio
async def test_type7_close_breaks_loop():
    """Type 7 close terminates the message generator."""
    client = _make_client()
    close_msg = FakeWSMessage(
        WSMsgType.TEXT,
        _core_msg({"type": 7, "error": "Server shutting down"}),
    )
    # This message should never be reached
    feed_msg = FakeWSMessage(
        WSMsgType.TEXT,
        _core_msg({"type": 1, "target": "feed", "arguments": ["Heartbeat", {}]}),
    )
    client._ws = FakeWebSocket([close_msg, feed_msg])

    results = []
    async for payload in client.messages():
        results.append(payload)

    assert len(results) == 0


@pytest.mark.asyncio
async def test_record_separator_batch():
    """Multiple messages in a single WS frame separated by \\x1e are all handled."""
    client = _make_client()
    # Batch: ping + feed in one WS text frame
    batch_data = (
        _core_msg({"type": 6})
        + _core_msg(
            {"type": 1, "target": "feed", "arguments": ["WeatherData", {"Temp": "22"}]}
        )
    )
    batch_msg = FakeWSMessage(WSMsgType.TEXT, batch_data)
    ws = FakeWebSocket([batch_msg])
    client._ws = ws

    results = []
    async for payload in client.messages():
        results.append(payload)

    # Only the feed should be yielded
    assert len(results) == 1
    assert results[0]["M"][0]["A"][0] == "WeatherData"

    # Pong should have been sent for the ping
    pong_sent = [s for s in ws._sent if "6" in s]
    assert len(pong_sent) >= 1


@pytest.mark.asyncio
async def test_ensure_connection_retry():
    """ensure_connection retries with exponential backoff on failure."""
    client = _make_client()
    call_count = 0

    async def mock_connect():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("fail")

    client.connect = mock_connect

    with patch("custom_components.f1_sensor.signalr.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await client.ensure_connection()

    assert call_count == 3
    # First retry: 5s, second retry: 10s
    assert mock_sleep.call_count == 2
    assert mock_sleep.call_args_list[0][0][0] == 5
    assert mock_sleep.call_args_list[1][0][0] == 10


@pytest.mark.asyncio
async def test_cookie_forwarded_to_websocket():
    """AWSALBCORS cookie from OPTIONS is included in WS connect headers."""
    client = _make_client()

    options_resp = AsyncMock()
    options_resp.headers = {"Set-Cookie": "AWSALBCORS=sticky_val; Path=/"}
    options_resp.__aenter__ = AsyncMock(return_value=options_resp)
    options_resp.__aexit__ = AsyncMock(return_value=False)

    post_resp = AsyncMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json = AsyncMock(return_value={"connectionToken": "t"})
    post_resp.__aenter__ = AsyncMock(return_value=post_resp)
    post_resp.__aexit__ = AsyncMock(return_value=False)

    handshake_msg = FakeWSMessage(WSMsgType.TEXT, "{}" + RECORD_SEP)
    ws = FakeWebSocket([handshake_msg])

    client._session.options = MagicMock(return_value=options_resp)
    client._session.post = MagicMock(return_value=post_resp)
    client._session.ws_connect = AsyncMock(return_value=ws)

    await client.connect()

    # Verify cookie was forwarded to ws_connect
    ws_call = client._session.ws_connect.call_args
    assert ws_call[1]["headers"]["Cookie"] == "AWSALBCORS=sticky_val"

    # Verify cookie was forwarded to POST negotiate
    post_call = client._session.post.call_args
    assert post_call[1]["headers"]["Cookie"] == "AWSALBCORS=sticky_val"


@pytest.mark.asyncio
async def test_close_cleanup():
    """close() closes the WebSocket and sets it to None."""
    client = _make_client()
    ws = FakeWebSocket()
    client._ws = ws

    await client.close()

    assert ws.closed is True
    assert client._ws is None


@pytest.mark.asyncio
async def test_no_heartbeat_task():
    """SignalRCoreClient has no heartbeat task — server pings replace it."""
    client = _make_client()
    assert not hasattr(client, "_heartbeat_task")
    assert not hasattr(client, "_heartbeat")
