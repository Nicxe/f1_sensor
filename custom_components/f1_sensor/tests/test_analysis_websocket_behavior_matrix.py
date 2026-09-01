"""Behavior matrix for analysis WebSocket commands and subscription throttling."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.f1_sensor import analysis_websocket as ws


class _Connection:
    def __init__(self) -> None:
        self.results = []
        self.errors = []
        self.events = []
        self.subscriptions = {}

    def send_result(self, *args) -> None:
        self.results.append(args)

    def send_error(self, *args) -> None:
        self.errors.append(args)

    def send_event(self, *args) -> None:
        self.events.append(args)


def test_get_analysis_not_loaded_and_success(hass, monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(ws, "_resolve_runtime", Mock(return_value=None))
    ws._ws_get_analysis(hass, connection, {"id": 1})
    assert connection.errors[-1][1] == "not_loaded"

    runtime = SimpleNamespace(analysis=SimpleNamespace())
    monkeypatch.setattr(ws, "_resolve_runtime", Mock(return_value=runtime))
    monkeypatch.setattr(ws, "_analysis_payload", Mock(return_value={"status": "ready"}))
    ws._ws_get_analysis(hass, connection, {"id": 2})
    assert connection.results[-1] == (2, {"status": "ready"})


@pytest.mark.asyncio
async def test_history_timeline_not_loaded_success_and_errors(
    hass, monkeypatch
) -> None:
    connection = _Connection()
    message = {
        "id": 3,
        "year": 2026,
        "round": 1,
        "session_type": "Race",
        "session_key": 2,
        "force_refresh": False,
    }
    monkeypatch.setattr(ws, "_resolve_runtime", Mock(return_value=None))
    ws._ws_get_history_timeline(hass, connection, message)
    await hass.async_block_till_done()
    assert connection.errors[-1][1] == "not_loaded"

    service = SimpleNamespace(
        async_get_session_results=AsyncMock(return_value={"results": []})
    )
    runtime = SimpleNamespace(history=SimpleNamespace(service=service))
    monkeypatch.setattr(ws, "_resolve_runtime", Mock(return_value=runtime))
    monkeypatch.setattr(ws, "historical_timeline", Mock(return_value={"events": []}))
    ws._ws_get_history_timeline(hass, connection, message)
    await hass.async_block_till_done()
    assert connection.results[-1] == (3, {"events": []})

    service.async_get_session_results = AsyncMock(side_effect=ValueError("bad request"))
    ws._ws_get_history_timeline(hass, connection, message)
    await hass.async_block_till_done()
    assert connection.errors[-1][1:] == ("invalid_request", "bad request")
    service.async_get_session_results = AsyncMock(side_effect=RuntimeError("offline"))
    ws._ws_get_history_timeline(hass, connection, message)
    await hass.async_block_till_done()
    assert connection.errors[-1][1] == "provider_unavailable"


@pytest.mark.asyncio
async def test_telemetry_compare_not_loaded_success_and_errors(
    hass, monkeypatch
) -> None:
    connection = _Connection()
    message = {"id": 4, "selections": [{"driver_number": 4, "lap_number": 1}]}
    monkeypatch.setattr(ws, "_resolve_runtime", Mock(return_value=None))
    ws._ws_compare_replay_telemetry(hass, connection, message)
    await hass.async_block_till_done()
    assert connection.errors[-1][1] == "not_loaded"

    telemetry = SimpleNamespace(async_compare=AsyncMock(return_value={"series": []}))
    runtime = SimpleNamespace(analysis=SimpleNamespace(telemetry=telemetry))
    monkeypatch.setattr(ws, "_resolve_runtime", Mock(return_value=runtime))
    ws._ws_compare_replay_telemetry(hass, connection, message)
    await hass.async_block_till_done()
    assert connection.results[-1] == (4, {"series": []})
    telemetry.async_compare = AsyncMock(side_effect=ValueError("bad selection"))
    ws._ws_compare_replay_telemetry(hass, connection, message)
    await hass.async_block_till_done()
    assert connection.errors[-1][1] == "invalid_request"
    telemetry.async_compare = AsyncMock(side_effect=RuntimeError("offline"))
    ws._ws_compare_replay_telemetry(hass, connection, message)
    await hass.async_block_till_done()
    assert connection.errors[-1][1] == "provider_unavailable"


def test_runtime_resolution_and_not_loaded_payload(hass, monkeypatch) -> None:
    runtime = SimpleNamespace(analysis=None)
    monkeypatch.setattr(ws, "runtime_from_hass", Mock(return_value=runtime))
    assert ws._resolve_runtime(hass, "entry") is runtime
    monkeypatch.setattr(ws, "runtime_from_hass", Mock(return_value=None))
    assert ws._resolve_runtime(hass, None) is None
    assert ws._analysis_payload(runtime) == {
        "protocol_version": ws.ANALYSIS_PROTOCOL_VERSION,
        "status": "not_loaded",
    }


def test_subscription_coalesces_sends_and_cancels_pending(hass) -> None:
    connection = _Connection()
    hub = SimpleNamespace(
        add=Mock(return_value=Mock()), payload=Mock(return_value={"initial": True})
    )
    subscription = ws._AnalysisSubscription(hass, connection, 5, hub, 1.0)
    subscription.async_send_initial()
    assert connection.events[-1] == (5, {"initial": True})

    subscription.receive({"value": 1})
    subscription.receive({"value": 2})
    assert subscription._pending_handle is not None
    subscription._send_pending()
    assert connection.events[-1] == (5, {"value": 2})

    handle = Mock()
    subscription._pending_handle = handle
    subscription.unsubscribe()
    handle.cancel.assert_called_once()
    hub.add.return_value.assert_called_once()


@pytest.mark.asyncio
async def test_hub_demand_can_close_empty_bus_and_update_legacy_state(hass) -> None:
    bus = SimpleNamespace(
        async_update_streams=AsyncMock(),
        start=AsyncMock(),
        async_close=AsyncMock(),
        active_streams=frozenset(),
    )
    capabilities = SimpleNamespace(
        requested_streams=frozenset(ws.PHASE4_ANALYSIS_STREAMS),
        active_streams=frozenset(),
        stream_reasons=dict.fromkeys(ws.PHASE4_ANALYSIS_STREAMS, ("weekend_hub_card",)),
    )
    legacy = {"signalr_stream_capabilities": {}}
    runtime = SimpleNamespace(
        live=SimpleNamespace(bus=bus, availability=SimpleNamespace(is_live=False)),
        capabilities=capabilities,
        get=legacy.get,
    )
    hub = object.__new__(ws._AnalysisBroadcastHub)
    hub._hass = hass
    hub._runtime = runtime
    hub._store = Mock()
    hub._subscribers = set()
    hub.closed = False
    hub._set_demand(active=False)
    await hass.async_block_till_done()
    bus.async_close.assert_awaited_once()
    assert capabilities.requested_streams == frozenset()
    assert legacy["signalr_stream_capabilities"]["requested_streams"] == frozenset()

    no_live = object.__new__(ws._AnalysisBroadcastHub)
    no_live._runtime = SimpleNamespace(live=None)
    no_live._set_demand(active=True)
