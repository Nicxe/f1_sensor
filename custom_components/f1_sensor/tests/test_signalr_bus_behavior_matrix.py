"""Behavior matrix for shared SignalR bus bookkeeping and dispatch."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiohttp import ClientResponseError

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
