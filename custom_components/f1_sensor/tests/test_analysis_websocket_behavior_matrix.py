"""Behavior matrix for analysis WebSocket commands and subscription throttling."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.f1_sensor import analysis_websocket as ws
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager


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
    hass.data.setdefault(DOMAIN, {})["no_spoiler_manager"] = NoSpoilerModeManager(hass)
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


@pytest.mark.asyncio
async def test_telemetry_catalog_reads_named_session_and_explains_unavailable(
    hass, monkeypatch
) -> None:
    hass.data.setdefault(DOMAIN, {})["no_spoiler_manager"] = NoSpoilerModeManager(hass)
    connection = _Connection()
    message = {"id": 44, "expected_session_id": "selected-replay"}
    monkeypatch.setattr(ws, "_resolve_runtime", Mock(return_value=None))
    ws._ws_replay_telemetry_catalog(hass, connection, message)
    await hass.async_block_till_done()
    assert connection.errors[-1][1] == "not_loaded"
    telemetry = SimpleNamespace(
        async_catalog=AsyncMock(
            return_value={"session_id": "selected-replay", "drivers": []}
        )
    )
    monkeypatch.setattr(
        ws,
        "_resolve_runtime",
        Mock(
            return_value=SimpleNamespace(analysis=SimpleNamespace(telemetry=telemetry))
        ),
    )
    ws._ws_replay_telemetry_catalog(hass, connection, message)
    await hass.async_block_till_done()
    telemetry.async_catalog.assert_awaited_once_with(
        expected_session_id="selected-replay"
    )
    assert connection.results[-1][1]["session_id"] == "selected-replay"
    for error, code in [
        (ValueError("changed"), "invalid_request"),
        (RuntimeError("offline"), "provider_unavailable"),
    ]:
        telemetry.async_catalog = AsyncMock(side_effect=error)
        ws._ws_replay_telemetry_catalog(hass, connection, message)
        await hass.async_block_till_done()
        assert connection.errors[-1][1] == code


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


class _LoopClock:
    """Advance the publication clock without real waits or transport work."""

    def __init__(self) -> None:
        self.now = 100.0
        self.timers = []

    def time(self) -> float:
        return self.now

    def call_at(self, deadline, callback):
        handle = SimpleNamespace(when=lambda: deadline, cancel=Mock())
        self.timers.append((deadline, callback, handle))
        return handle

    def call_later(self, delay, callback):
        return self.call_at(self.now + delay, callback)

    def advance(self, seconds) -> None:
        self.now += seconds
        while self.timers:
            entry = min(self.timers, key=lambda item: item[0])
            deadline, callback, handle = entry
            if deadline > self.now:
                return
            self.timers.remove(entry)
            if not handle.cancel.called:
                callback()


def _analysis_publication(monkeypatch):
    clock = _LoopClock()
    hass = SimpleNamespace(loop=clock)
    state = {"session_id": "first"}
    build = Mock(side_effect=lambda _runtime: dict(state))
    monkeypatch.setattr(ws, "_analysis_payload", build)
    store = Mock(
        add_listener=Mock(return_value=Mock()),
        add_close_listener=Mock(return_value=Mock()),
    )
    manager = SimpleNamespace(add_listener=Mock(return_value=Mock()))
    runtime = SimpleNamespace(
        live=None,
        replay=SimpleNamespace(controller=SimpleNamespace(session_manager=manager)),
    )
    hub = ws._AnalysisBroadcastHub(hass, runtime, store)
    return hass, clock, state, build, hub, store, manager


def test_analysis_builds_only_for_due_subscribers_and_shares_the_payload(
    monkeypatch,
) -> None:
    hass, clock, state, build, hub, store, _manager = _analysis_publication(monkeypatch)
    connection = _Connection()
    subscriptions = [
        ws._AnalysisSubscription(hass, connection, message_id, hub, interval)
        for message_id, interval in ((1, 1.0), (2, 1.0), (3, 2.0))
    ]
    try:
        for subscription in subscriptions:
            subscription.async_send_initial()
        assert connection.events == [
            (index, {"session_id": "first"}) for index in (1, 2, 3)
        ]
        build.reset_mock()
        publish = store.add_listener.call_args.args[0]
        for index in range(20):
            state["session_id"] = str(index)
            publish()
        build.assert_not_called()

        clock.advance(1.0)
        build.assert_called_once()
        assert {message_id for message_id, _payload in connection.events[3:]} == {1, 2}
        assert connection.events[-1][1] is connection.events[-2][1]
        assert connection.events[-1][1]["session_id"] == "19"

        state["session_id"] = "latest"
        publish()
        clock.advance(1.0)
        assert build.call_count == 2
        assert {message_id for message_id, _payload in connection.events[5:]} == {
            1,
            2,
            3,
        }
        assert all(
            payload["session_id"] == "latest" for _, payload in connection.events[5:]
        )
        publish()
    finally:
        for subscription in subscriptions:
            subscription.unsubscribe()
    clock.advance(5.0)
    assert build.call_count == 2
    store.add_listener.return_value.assert_called_once()


def test_analysis_shares_a_snapshot_with_clients_due_while_it_is_built(monkeypatch):
    hass, clock, state, build, hub, store, _manager = _analysis_publication(monkeypatch)
    connection = _Connection()
    first = ws._AnalysisSubscription(hass, connection, 1, hub, 1.0)
    second = ws._AnalysisSubscription(hass, connection, 2, hub, 1.0)
    try:
        first.async_send_initial()
        clock.advance(0.125)
        second.async_send_initial()
        build.reset_mock()

        def build_snapshot(_runtime):
            clock.now += 0.25
            return dict(state)

        build.side_effect = build_snapshot
        store.add_listener.call_args.args[0]()
        clock.advance(0.875)
        build.assert_called_once()
        assert {message_id for message_id, _payload in connection.events[2:]} == {1, 2}
    finally:
        first.unsubscribe()
        second.unsubscribe()


async def test_analysis_due_send_uses_current_replay_context_and_closes_pending_work(
    monkeypatch,
) -> None:
    hass, clock, state, build, hub, store, manager = _analysis_publication(monkeypatch)
    connection = _Connection()
    subscription = ws._AnalysisSubscription(hass, connection, 1, hub, 1.0)
    connection.subscriptions[1] = subscription.unsubscribe
    try:
        subscription.async_send_initial()
        publish = store.add_listener.call_args.args[0]
        publish()
        state["session_id"] = "new-replay"
        manager.add_listener.call_args.args[0]({})
        assert build.call_count == 1
        clock.advance(1.0)
        assert connection.events[-1] == (1, {"session_id": "new-replay"})
        publish()
        state["session_id"] = None
        await hub.async_close()
        assert connection.events[-1] == (
            1,
            {
                "session_id": None,
                "status": "closed",
                "retryable": True,
                "reason": "entry_unloaded",
            },
        )
        assert not connection.subscriptions
        clock.advance(5.0)
        assert build.call_count == len(connection.events) == 3
        manager.add_listener.return_value.assert_called_once()
    finally:
        subscription.unsubscribe()


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
    hub._store = SimpleNamespace(closed=False)
    hub._subscribers = set()
    hub._demand_tasks = set()
    hub._unsubscribe_close = Mock()
    hub.closed = False
    hub._set_demand(active=False)
    await hass.async_block_till_done()
    bus.async_close.assert_awaited_once()
    assert capabilities.requested_streams == frozenset()
    assert legacy["signalr_stream_capabilities"]["requested_streams"] == frozenset()

    no_live = object.__new__(ws._AnalysisBroadcastHub)
    no_live._runtime = SimpleNamespace(live=None)
    no_live._set_demand(active=True)
