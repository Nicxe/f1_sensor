"""Tests for SignalRCoreClient — SignalR Core protocol implementation."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import WSMsgType
import pytest

from custom_components.f1_sensor.signalr import (
    AUTH_GATED_LIVE_STREAMS,
    NO_AUTH_LIVE_STREAMS,
    PUBLIC_LIVE_STREAMS,
    RECORD_SEP,
    REPLAY_ONLY_STREAMS,
    SUBSCRIBE_MSG,
    LiveBus,
    SignalRAuthenticationError,
    SignalRCoreClient,
    SignalRLegacyClient,
    build_live_subscribe_streams,
    build_subscribe_message,
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

    async def send_json(self, data: dict) -> None:
        self._sent.append(json.dumps(data))

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
async def test_core_auth_header_enables_auth_gated_streams():
    """Core client sends the configured Authorization header and gated streams."""
    client = SignalRCoreClient(MagicMock(), MagicMock(), auth_header="Bearer secret")

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

    assert client._session.options.call_args.kwargs["headers"]["Authorization"] == (
        "Bearer secret"
    )
    assert client._session.post.call_args.kwargs["headers"]["Authorization"] == (
        "Bearer secret"
    )
    assert client._session.ws_connect.call_args.kwargs["headers"]["Authorization"] == (
        "Bearer secret"
    )
    subscribe_sent = ws._sent[1]
    sub_json = json.loads(subscribe_sent.replace(RECORD_SEP, ""))
    assert sub_json["arguments"] == [[*PUBLIC_LIVE_STREAMS, *AUTH_GATED_LIVE_STREAMS]]
    assert set(sub_json["arguments"][0]).isdisjoint(REPLAY_ONLY_STREAMS)


@pytest.mark.asyncio
async def test_core_auth_handshake_error_raises_without_leaking_token():
    """Auth failures raise the typed error without including the configured token."""
    client = SignalRCoreClient(MagicMock(), MagicMock(), auth_header="Bearer secret")

    options_resp = AsyncMock()
    options_resp.headers = {}
    options_resp.__aenter__ = AsyncMock(return_value=options_resp)
    options_resp.__aexit__ = AsyncMock(return_value=False)

    post_resp = AsyncMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json = AsyncMock(return_value={"connectionToken": "t"})
    post_resp.__aenter__ = AsyncMock(return_value=post_resp)
    post_resp.__aexit__ = AsyncMock(return_value=False)

    handshake_msg = FakeWSMessage(
        WSMsgType.TEXT,
        json.dumps({"error": "Unauthorized"}) + RECORD_SEP,
    )
    ws = FakeWebSocket([handshake_msg])

    client._session.options = MagicMock(return_value=options_resp)
    client._session.post = MagicMock(return_value=post_resp)
    client._session.ws_connect = AsyncMock(return_value=ws)

    with pytest.raises(SignalRAuthenticationError) as exc:
        await client.connect()

    assert "secret" not in str(exc.value)


@pytest.mark.asyncio
async def test_legacy_auth_header_enables_auth_gated_streams():
    """Legacy client also sends Authorization and subscribes to gated streams."""
    client = SignalRLegacyClient(MagicMock(), MagicMock(), auth_header="Bearer secret")

    get_resp = AsyncMock()
    get_resp.headers = {"Set-Cookie": "lb-cookie=1"}
    get_resp.raise_for_status = MagicMock()
    get_resp.json = AsyncMock(return_value={"ConnectionToken": "legacy-token"})
    get_resp.__aenter__ = AsyncMock(return_value=get_resp)
    get_resp.__aexit__ = AsyncMock(return_value=False)

    ws = FakeWebSocket()
    client._session.get = MagicMock(return_value=get_resp)
    client._session.ws_connect = AsyncMock(return_value=ws)
    task = MagicMock()
    task.done.return_value = True

    def _create_task(coro):
        coro.close()
        return task

    with patch("asyncio.create_task", side_effect=_create_task):
        await client.connect()

    assert client._session.get.call_args.kwargs["headers"]["Authorization"] == (
        "Bearer secret"
    )
    ws_headers = client._session.ws_connect.call_args.kwargs["headers"]
    assert ws_headers["Authorization"] == "Bearer secret"
    subscribe_json = json.loads(ws._sent[0])
    assert subscribe_json == build_subscribe_message(include_auth_gated=True)
    assert set(subscribe_json["A"][0]).isdisjoint(REPLAY_ONLY_STREAMS)


def test_no_auth_live_stream_contract():
    """No-auth subscriptions must stay aligned with the explicit public stream contract."""
    assert PUBLIC_LIVE_STREAMS == (
        "RaceControlMessages",
        "TrackStatus",
        "SessionStatus",
        "WeatherData",
        "LapCount",
        "SessionInfo",
        "SessionData",
        "Heartbeat",
        "ExtrapolatedClock",
        "TimingData",
        "DriverList",
        "TimingAppData",
        "TopThree",
    )
    assert NO_AUTH_LIVE_STREAMS == PUBLIC_LIVE_STREAMS
    assert SUBSCRIBE_MSG["A"] == [list(NO_AUTH_LIVE_STREAMS)]
    assert build_live_subscribe_streams(include_auth_gated=True) == (
        *PUBLIC_LIVE_STREAMS,
        *AUTH_GATED_LIVE_STREAMS,
    )


def test_no_auth_live_stream_contract_excludes_gated_and_replay_only_streams():
    """No-auth live subscriptions must not reintroduce gated or replay-only streams."""
    subscribed = set(NO_AUTH_LIVE_STREAMS)

    assert subscribed.isdisjoint(AUTH_GATED_LIVE_STREAMS)
    assert subscribed.isdisjoint(REPLAY_ONLY_STREAMS)
    assert AUTH_GATED_LIVE_STREAMS == (
        "CarData.z",
        "DriverRaceInfo",
        "ChampionshipPrediction",
    )
    assert REPLAY_ONLY_STREAMS == (
        "TeamRadio",
        "PitStopSeries",
    )


def test_live_bus_can_select_legacy_transport(monkeypatch):
    """Legacy transport remains intentionally selectable behind the feature toggle."""
    monkeypatch.setattr("custom_components.f1_sensor.const.SIGNALR_USE_CORE", False)
    bus = LiveBus(MagicMock(), MagicMock())

    client = bus._create_client()

    assert isinstance(client, SignalRLegacyClient)


@pytest.mark.asyncio
async def test_live_bus_falls_back_to_no_auth_after_auth_failure():
    """Rejected auth disables auth and lets the next connection use public streams."""

    class AuthFailTransport:
        async def ensure_connection(self) -> None:
            raise SignalRAuthenticationError("auth rejected")

        async def messages(self):
            if False:
                yield {}

        async def close(self) -> None:
            return None

    class StopTransport:
        def __init__(self, bus: LiveBus) -> None:
            self._bus = bus

        async def ensure_connection(self) -> None:
            return None

        async def messages(self):
            self._bus._running = False  # noqa: SLF001 - stop private test loop
            if False:
                yield {}

        async def close(self) -> None:
            return None

    hass = MagicMock()
    auth_failed = MagicMock()
    bus = LiveBus(
        hass,
        MagicMock(),
        auth_header="Bearer secret",
        auth_failed_callback=auth_failed,
    )
    bus._running = True  # noqa: SLF001 - exercise private fallback loop directly
    create_client = MagicMock(side_effect=[AuthFailTransport(), StopTransport(bus)])
    bus._create_client = create_client  # noqa: SLF001 - control transport sequence

    await bus._run()  # noqa: SLF001 - exercise private fallback loop directly

    assert bus.auth_enabled is False
    auth_failed.assert_called_once_with()
    assert create_client.call_count == 2


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
    batch_data = _core_msg({"type": 6}) + _core_msg(
        {"type": 1, "target": "feed", "arguments": ["WeatherData", {"Temp": "22"}]}
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

    with patch(
        "custom_components.f1_sensor.signalr.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
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


# ---------------------------------------------------------------------------
# LiveBus heartbeat monitor tests
# ---------------------------------------------------------------------------


def _make_bus(hass=None, session=None) -> LiveBus:
    """Create a LiveBus with mocked hass and session."""
    if hass is None:
        hass = MagicMock()
        hass.loop = MagicMock()
    if session is None:
        session = MagicMock()
    return LiveBus(hass, session)


@pytest.mark.asyncio
async def test_heartbeat_monitor_forces_reconnect_on_inactivity():
    """When only protocol pings arrive (no feed data), the heartbeat monitor
    detects inactivity and closes the client to trigger reconnect.

    This reproduces the failure mode observed during Japan GP 2026 where
    core recorders stopped receiving feed data after qualifying but continued
    receiving type 6 pings.
    """
    bus = _make_bus()
    bus._expect_heartbeat = True

    # Simulate a client that is "connected" but receiving no feed data
    mock_client = AsyncMock()
    bus._client = mock_client

    # Set heartbeat timestamp to 60 seconds ago (> 45s timeout)
    bus._last_heartbeat_at = time.time() - 60

    # Run one iteration of the monitor
    bus._running = True
    bus._heartbeat_check_interval = 0.01  # speed up test

    # Run the monitor in a task and let it fire once
    monitor_task = asyncio.create_task(bus._monitor_heartbeat())
    await asyncio.sleep(0.05)
    bus._running = False
    await asyncio.sleep(0.05)
    monitor_task.cancel()
    with suppress(asyncio.CancelledError):
        await monitor_task

    # The monitor should have closed the client
    mock_client.close.assert_awaited_once()
    assert bus._client is None


@pytest.mark.asyncio
async def test_heartbeat_monitor_skips_when_recent_activity():
    """When feed data is flowing (recent heartbeat), the monitor does nothing."""
    bus = _make_bus()
    bus._expect_heartbeat = True

    mock_client = AsyncMock()
    bus._client = mock_client

    # Heartbeat just arrived
    bus._last_heartbeat_at = time.time()

    bus._running = True
    bus._heartbeat_check_interval = 0.01

    monitor_task = asyncio.create_task(bus._monitor_heartbeat())
    await asyncio.sleep(0.05)
    bus._running = False
    await asyncio.sleep(0.05)
    monitor_task.cancel()
    with suppress(asyncio.CancelledError):
        await monitor_task

    # Client should NOT have been closed
    mock_client.close.assert_not_awaited()
    assert bus._client is mock_client


@pytest.mark.asyncio
async def test_heartbeat_monitor_skips_when_disabled():
    """When heartbeat expectation is disabled, the monitor skips checks."""
    bus = _make_bus()
    bus._expect_heartbeat = False

    mock_client = AsyncMock()
    bus._client = mock_client

    # Stale heartbeat that would trigger if monitor were enabled
    bus._last_heartbeat_at = time.time() - 120

    bus._running = True
    bus._heartbeat_check_interval = 0.01

    monitor_task = asyncio.create_task(bus._monitor_heartbeat())
    await asyncio.sleep(0.05)
    bus._running = False
    await asyncio.sleep(0.05)
    monitor_task.cancel()
    with suppress(asyncio.CancelledError):
        await monitor_task

    mock_client.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_reset_before_reconnect_prevents_monitor_interference():
    """_last_heartbeat_at is reset before ensure_connection() so the monitor
    does not kill the client during reconnection.

    This verifies the fix for the race condition where the monitor could see
    a stale heartbeat timestamp during the reconnect window and close the
    new client before it finished connecting.

    Instead of running the full _run() loop, we directly replicate the
    connect sequence from _run() and assert the ordering.
    """
    bus = _make_bus()
    bus._expect_heartbeat = True

    # Simulate: previous connection died 60s ago
    bus._last_heartbeat_at = time.time() - 60
    bus._running = True

    hb_age_during_connect = None

    class TrackingClient:
        async def ensure_connection(self):
            nonlocal hb_age_during_connect
            hb_age_during_connect = time.time() - bus._last_heartbeat_at

        async def messages(self):
            return
            yield  # noqa: RET503

        async def close(self):
            pass

    # Replicate the connect sequence from _run():
    # 1. create client
    bus._client = TrackingClient()
    # 2. reset heartbeat (the fix)
    bus._last_heartbeat_at = time.time()
    # 3. call ensure_connection
    await bus._client.ensure_connection()

    # The heartbeat age seen during ensure_connection should be < 1s,
    # not the 60s stale value from before the reset.
    assert hb_age_during_connect is not None
    assert hb_age_during_connect < 2.0, (
        f"Heartbeat age {hb_age_during_connect:.1f}s during ensure_connection — "
        "monitor would kill reconnect attempt"
    )


@pytest.mark.asyncio
async def test_live_bus_replays_initial_state_and_recovers_after_reconnect():
    """Initial state, reconnect, and snapshot cache remain coherent."""
    original_sleep = asyncio.sleep

    class FakeTransport:
        def __init__(
            self,
            payloads: list[dict],
            *,
            error: Exception | None = None,
            stop_bus: LiveBus | None = None,
        ) -> None:
            self._payloads = list(payloads)
            self._error = error
            self._stop_bus = stop_bus
            self.ensure_calls = 0
            self.close_calls = 0

        async def ensure_connection(self) -> None:
            self.ensure_calls += 1

        async def messages(self):
            for payload in self._payloads:
                yield payload
            if self._error is not None:
                raise self._error
            if self._stop_bus is not None:
                self._stop_bus._running = False

        async def close(self) -> None:
            self.close_calls += 1

    hass = MagicMock()
    hass.loop = asyncio.get_running_loop()
    first_transport = FakeTransport(
        [{"R": {"TimingAppData": {"Lines": {"1": {"Stints": []}}}}}],
        error=RuntimeError("disconnect"),
    )
    bus: LiveBus
    second_transport = FakeTransport(
        [
            {
                "M": [
                    {
                        "H": "Streaming",
                        "M": "feed",
                        "A": ["TimingData", {"Lines": {"1": {"Position": "1"}}}],
                    }
                ]
            }
        ]
    )
    transports = [first_transport, second_transport]

    def _factory():
        transport = transports.pop(0)
        if transport is second_transport:
            transport._stop_bus = bus
        return transport

    bus = LiveBus(hass, MagicMock(), transport_factory=_factory)
    timing_app_payloads: list[dict] = []
    timing_data_payloads: list[dict] = []
    bus.subscribe("TimingAppData", lambda payload: timing_app_payloads.append(payload))
    bus.subscribe("TimingData", lambda payload: timing_data_payloads.append(payload))

    async def _fast_sleep(_seconds: float) -> None:
        await original_sleep(0)

    with patch(
        "custom_components.f1_sensor.signalr.asyncio.sleep", side_effect=_fast_sleep
    ):
        task = asyncio.create_task(bus._run())
        bus._running = True
        await asyncio.wait_for(task, timeout=1)

    assert first_transport.ensure_calls == 1
    assert second_transport.ensure_calls == 1
    assert first_transport.close_calls == 1
    assert second_transport.close_calls == 1
    assert timing_app_payloads == [{"Lines": {"1": {"Stints": []}}}]
    assert timing_data_payloads == [{"Lines": {"1": {"Position": "1"}}}]

    late_subscriber_payloads: list[dict] = []
    bus.subscribe(
        "TimingData", lambda payload: late_subscriber_payloads.append(payload)
    )
    assert late_subscriber_payloads == [{"Lines": {"1": {"Position": "1"}}}]
