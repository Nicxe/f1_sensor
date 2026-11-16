"""Behavior matrix for shared SignalR bus bookkeeping and dispatch."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiohttp import ClientResponseError
import pytest

from custom_components.f1_sensor import const
from custom_components.f1_sensor.signalr import (
    LiveBus,
    LiveConnectionState,
    _authorization_headers,
    _decode_core_records,
    _is_authentication_close_error,
    _is_authentication_error,
    _normalize_auth_header,
    _response_cookie_value,
)


def test_signalr_auth_cookie_and_record_helpers() -> None:
    assert _normalize_auth_header(None) is None
    assert _authorization_headers(None) == {}
    assert _authorization_headers("Bearer token") == {"Authorization": "Bearer token"}
    assert _is_authentication_error(RuntimeError("HTTP 403 forbidden")) is True
    assert (
        _is_authentication_error(
            ClientResponseError(None, (), status=401, message="unauthorized")
        )
        is True
    )
    assert _is_authentication_error(RuntimeError("network")) is False
    assert _is_authentication_close_error("401 unauthorized") is True
    assert _is_authentication_close_error(None) is False
    assert _decode_core_records('{}\x1e{"x":1}\x1e') == [{}, {"x": 1}]

    response = SimpleNamespace(
        cookies={"Cookie": SimpleNamespace(value="cookie-value")}, headers={}
    )
    assert _response_cookie_value(response, "Cookie") == "cookie-value"
    response = SimpleNamespace(
        cookies={}, headers={"Set-Cookie": "Cookie=header-value; Path=/; Secure"}
    )
    assert _response_cookie_value(response, "Cookie") == "header-value"
    assert (
        _response_cookie_value(SimpleNamespace(cookies={}, headers=None), "x") is None
    )


def test_live_bus_dispatch_subscription_activity_and_diagnostics(hass) -> None:
    now = [100.0]
    bus = LiveBus(
        hass,
        AsyncMock(),
        requested_streams={"TrackStatus", "Heartbeat"},
        monotonic=lambda: now[0],
    )
    assert bus.connection_state is LiveConnectionState.STOPPED
    assert bus.requested_streams == frozenset({"TrackStatus", "Heartbeat"})
    received = []
    bus._last_payload["TrackStatus"] = {"Status": "1"}
    remove = bus.subscribe("TrackStatus", received.append)
    assert received == [{"Status": "1"}]
    assert bus._process_payload(None) is False
    assert bus._process_payload({"M": ["bad", {"M": "other"}]}) is False
    assert (
        bus._process_payload(
            {
                "M": [
                    {"M": "feed", "A": []},
                    {"M": "feed", "A": [1, {}]},
                    {"M": "feed", "A": ["TrackStatus", {"Status": "2"}]},
                ],
                "R": {"Heartbeat": {"Utc": "t"}, 2: {}},
            }
        )
        is True
    )
    assert received[-1] == {"Status": "2"}
    assert bus.get_last_payload("TrackStatus") == {"Status": "2"}
    assert bus.get_last_payload("missing") is None
    assert bus.last_stream_activity_age(["missing"]) is None
    now[0] = 110.0
    assert bus.last_stream_activity_age(["TrackStatus"]) == 10.0
    assert bus.last_stream_activity_age() == 10.0
    diagnostics = bus.stream_diagnostics(["TrackStatus", "missing"])
    assert diagnostics["TrackStatus"]["frame_count"] == 1
    assert diagnostics["missing"]["last_seen_age_s"] is None
    bus.set_heartbeat_expectation(True)
    assert bus.last_heartbeat_age() == 10.0
    bus.set_heartbeat_expectation(False)
    assert bus.last_heartbeat_age() is None
    assert bus._retry_reason(RuntimeError("replay ended")) == "replay transport closed"
    assert bus._retry_reason(ValueError("bad")) == "ValueError"
    remove()
    remove()


def test_live_bus_summary_reports_elapsed_window_after_a_processing_gap(hass, caplog):
    now = [100.0]
    bus = LiveBus(hass, AsyncMock(), monotonic=lambda: now[0])
    with caplog.at_level(logging.DEBUG, logger="custom_components.f1_sensor.signalr"):
        bus._dispatch("Position.z", "sample")
        bus._dispatch("Heartbeat", {"Utc": "sample"})
        now[0] += 40.0
        bus._dispatch("TimingData", {"Lines": {}})

    summary = next(
        record.message
        for record in caplog.records
        if "LiveBus summary" in record.message
    )
    assert "last 40.0s" in summary
    assert "Position.z:1/1 (last 40.0s)" in summary
    assert "TimingData:1/1 (last 0.0s)" in summary
    assert bus._cnt["Position.z"] == 0


@pytest.mark.parametrize("callback_cost", [0.0, 0.003, 0.010])
async def test_live_bus_buffered_transport_yields_and_preserves_order(
    hass, monkeypatch, callback_cost
) -> None:
    now = [100.0]
    bus = LiveBus(hass, AsyncMock(), monotonic=lambda: now[0])
    received = []
    observations = []

    async def messages():
        yield {"R": {"TimingData": {"index": 0}, "SessionInfo": {"Key": 123}}}
        for index in range(1, 200):
            yield {"M": [{"M": "feed", "A": ["TimingData", {"index": index}]}]}
        bus._running = False

    def receive(payload):
        received.append(payload["index"])
        now[0] += callback_cost
        if payload["index"] == 0:
            hass.loop.call_soon(lambda: observations.append(len(received)))
            hass.loop.call_later(0, lambda: observations.append(len(received)))

    client = SimpleNamespace(
        ensure_connection=AsyncMock(), messages=messages, close=AsyncMock()
    )
    monkeypatch.setattr(bus, "_create_client", lambda: client)
    bus.subscribe("SessionInfo", lambda _payload: received.append("session"))
    bus.subscribe("TimingData", receive)
    bus._running = True

    await bus._run()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert received == ["session", *range(200)]
    assert len(observations) == 2
    assert all(1 < count < len(received) for count in observations)
    if callback_cost == 0.010:
        assert observations[0] == 2
    client.close.assert_awaited_once()


@pytest.mark.parametrize("retire", ["source", "client", "running"])
async def test_live_bus_buffered_reader_stops_when_yield_retires_ownership(
    hass, monkeypatch, retire
) -> None:
    source = ["live"]
    now = [100.0]
    bus = LiveBus(hass, AsyncMock(), monotonic=lambda: now[0])
    bus.configure_observations(
        "entry", None, lambda: None, source_provider=lambda: source[0]
    )
    received = []
    replacement = object()

    def retire_transport():
        if retire == "source":
            source[0] = "replay"
        elif retire == "client":
            bus._client = replacement
        else:
            bus._running = False

    async def messages():
        for index in range(200):
            yield {"M": [{"M": "feed", "A": ["TimingData", {"index": index}]}]}
        bus._running = False

    def receive(payload):
        received.append(payload["index"])
        now[0] += 0.003
        if payload["index"] == 0:
            hass.loop.call_soon(retire_transport)

    client = SimpleNamespace(
        ensure_connection=AsyncMock(), messages=messages, close=AsyncMock()
    )
    monkeypatch.setattr(bus, "_create_client", lambda: client)
    bus.subscribe("TimingData", receive)
    bus._running = True

    await bus._run()
    await asyncio.sleep(0)
    assert received == list(range(len(received)))
    assert 0 < len(received) < 200
    if retire == "client":
        assert bus._client is replacement
    client.close.assert_awaited_once()


async def test_live_bus_reconnects_when_heartbeat_closes_client_during_yield(
    hass, monkeypatch
) -> None:
    now = [100.0]
    bus = LiveBus(hass, AsyncMock(), monotonic=lambda: now[0])
    bus.set_heartbeat_expectation(True)
    bus._heartbeat_check_interval = 0
    received = []
    bus.subscribe("TrackStatus", received.append)

    async def inactive_messages():
        now[0] += bus._heartbeat_timeout + 1
        yield {"R": {}}
        yield {"R": {"TrackStatus": {"Status": "stale"}}}
        bus._running = False

    async def recovered_messages():
        yield {"R": {"TrackStatus": {"Status": "1"}}}
        bus._running = False

    inactive_client = SimpleNamespace(
        ensure_connection=AsyncMock(), messages=inactive_messages, close=AsyncMock()
    )
    recovered_client = SimpleNamespace(
        ensure_connection=AsyncMock(), messages=recovered_messages, close=AsyncMock()
    )
    clients = iter((inactive_client, recovered_client))
    retry = AsyncMock()
    monkeypatch.setattr(bus, "_create_client", lambda: next(clients))
    monkeypatch.setattr(bus, "_wait_before_retry", retry)
    bus._running = True
    heartbeat_guard = asyncio.create_task(bus._monitor_heartbeat())
    await asyncio.sleep(0)

    await bus._run()
    await heartbeat_guard

    retry.assert_awaited_once_with("connection closed")
    recovered_client.ensure_connection.assert_awaited_once()
    assert received == [{"Status": "1", "_f1_snapshot": True}]


async def test_live_bus_stream_updates_and_transport_swap(hass) -> None:
    bus = LiveBus(hass, AsyncMock(), requested_streams={"TrackStatus"})
    client = SimpleNamespace(update_streams=AsyncMock(), close=AsyncMock())
    bus._client = client
    await bus.async_update_streams({"TrackStatus"})
    assert client.update_streams.await_count == 0
    await bus.async_update_streams({"TrackStatus", "SessionInfo"})
    client.update_streams.assert_awaited_once()

    legacy_client = SimpleNamespace(close=AsyncMock())
    bus._client = legacy_client
    await bus.async_update_streams({"SessionInfo"})
    legacy_client.close.assert_awaited_once()

    transport = Mock()
    bus._last_payload["TrackStatus"] = {}
    bus._cnt["TrackStatus"] = 1
    bus._stream_frames["TrackStatus"] = 1
    bus._stream_last_keys["TrackStatus"] = ["Status"]
    bus._last_ts["TrackStatus"] = 1.0
    bus.start = AsyncMock()
    await bus.swap_transport(lambda: transport)
    bus.start.assert_awaited_once()
    assert bus._last_payload == {}
    assert bus.active_streams


async def test_live_bus_idle_client_selection_and_running_swap(
    hass, monkeypatch
) -> None:
    """Idle updates and both built-in transports preserve one bus lifecycle."""
    bus = LiveBus(hass, AsyncMock(), requested_streams={"TrackStatus"})
    await bus.async_update_streams({"SessionInfo"})

    bus.set_heartbeat_expectation(True)
    assert bus._last_heartbeat_at is not None
    assert bus.last_stream_activity_age() is None

    monkeypatch.setattr(const, "SIGNALR_USE_CORE", True)
    assert bus._create_client().__class__.__name__ == "SignalRCoreClient"
    monkeypatch.setattr(const, "SIGNALR_USE_CORE", False)
    assert bus._create_client().__class__.__name__ == "SignalRLegacyClient"

    bus._running = True
    bus.async_close = AsyncMock()
    bus.start = AsyncMock()
    await bus.swap_transport(None)
    bus.async_close.assert_awaited_once()
    bus.start.assert_awaited_once()
