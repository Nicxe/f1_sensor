"""Versioned WebSocket products for F1 Sensor Phase 4 analysis."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
import voluptuous as vol

from .analysis import PHASE4_ANALYSIS_STREAMS, Phase4AnalysisStore, historical_timeline
from .const import DOMAIN
from .runtime import F1RuntimeData, runtime_from_hass

ANALYSIS_WS_MARKER = "__analysis_ws_registered__"
ANALYSIS_GET_WS_TYPE = f"{DOMAIN}/analysis/get"
ANALYSIS_SUBSCRIBE_WS_TYPE = f"{DOMAIN}/analysis/subscribe"
ANALYSIS_HISTORY_TIMELINE_WS_TYPE = f"{DOMAIN}/analysis/history_timeline"
ANALYSIS_TELEMETRY_COMPARE_WS_TYPE = f"{DOMAIN}/analysis/telemetry_compare"
ANALYSIS_PROTOCOL_VERSION = 1
DEFAULT_ANALYSIS_THROTTLE_MS = 500

_ENTRY_ID_SCHEMA = vol.Optional("entry_id")
_ANALYSIS_HUBS: dict[Phase4AnalysisStore, _AnalysisBroadcastHub] = {}


def async_register_analysis_websocket(hass: HomeAssistant) -> None:
    """Register Phase 4 WebSocket commands once per Home Assistant runtime."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get(ANALYSIS_WS_MARKER):
        return
    websocket_api.async_register_command(hass, _ws_get_analysis)
    websocket_api.async_register_command(hass, _ws_subscribe_analysis)
    websocket_api.async_register_command(hass, _ws_get_history_timeline)
    websocket_api.async_register_command(hass, _ws_compare_replay_telemetry)
    root[ANALYSIS_WS_MARKER] = True


@websocket_api.websocket_command(
    {
        vol.Required("type"): ANALYSIS_GET_WS_TYPE,
        _ENTRY_ID_SCHEMA: str,
    }
)
@callback
def _ws_get_analysis(
    hass: HomeAssistant,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    """Return the current bounded analysis snapshot."""
    runtime = _resolve_runtime(hass, msg.get("entry_id"))
    if runtime is None or runtime.analysis is None:
        connection.send_error(msg["id"], "not_loaded", "F1 analysis is not loaded")
        return
    connection.send_result(msg["id"], _analysis_payload(runtime))


@websocket_api.websocket_command(
    {
        vol.Required("type"): ANALYSIS_SUBSCRIBE_WS_TYPE,
        _ENTRY_ID_SCHEMA: str,
        vol.Optional("throttle_ms", default=DEFAULT_ANALYSIS_THROTTLE_MS): vol.All(
            vol.Coerce(int), vol.Range(min=100, max=5000)
        ),
        vol.Optional("protocol_version", default=ANALYSIS_PROTOCOL_VERSION): vol.In(
            (ANALYSIS_PROTOCOL_VERSION,)
        ),
    }
)
@callback
def _ws_subscribe_analysis(
    hass: HomeAssistant,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    """Subscribe to shared throttled Weekend Hub analysis snapshots."""
    runtime = _resolve_runtime(hass, msg.get("entry_id"))
    store = runtime.analysis.store if runtime is not None and runtime.analysis else None
    if runtime is None or not isinstance(store, Phase4AnalysisStore) or store.closed:
        connection.send_error(msg["id"], "not_loaded", "F1 analysis is not loaded")
        return
    subscription = _AnalysisSubscription(
        hass,
        connection,
        msg["id"],
        _analysis_hub(hass, runtime, store),
        msg["throttle_ms"] / 1000,
    )
    connection.subscriptions[msg["id"]] = subscription.unsubscribe
    connection.send_result(msg["id"])
    subscription.async_send_initial()


@websocket_api.websocket_command(
    {
        vol.Required("type"): ANALYSIS_HISTORY_TIMELINE_WS_TYPE,
        vol.Required("year"): vol.All(vol.Coerce(int), vol.Range(min=1950, max=2200)),
        vol.Required("round"): vol.All(vol.Coerce(int), vol.Range(min=1, max=99)),
        vol.Required("session_type"): vol.All(str, vol.Length(min=1, max=80)),
        vol.Required("session_key"): vol.Any(int, vol.All(str, vol.Length(min=1))),
        _ENTRY_ID_SCHEMA: str,
        vol.Optional("force_refresh", default=False): bool,
    }
)
@websocket_api.async_response
async def _ws_get_history_timeline(
    hass: HomeAssistant,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    """Return historical classification events using the unified contract."""
    runtime = _resolve_runtime(hass, msg.get("entry_id"))
    if runtime is None:
        connection.send_error(msg["id"], "not_loaded", "F1 Sensor is not loaded")
        return
    try:
        result = await runtime.history.service.async_get_session_results(
            year=msg["year"],
            session_key=msg["session_key"],
            round_number=msg["round"],
            session_type=msg["session_type"],
            force_refresh=msg["force_refresh"],
        )
        payload = historical_timeline(
            year=msg["year"],
            round_number=msg["round"],
            session_type=msg["session_type"],
            results=result.get("results", []),
        )
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_request", str(err))
    except Exception:  # noqa: BLE001
        connection.send_error(
            msg["id"],
            "provider_unavailable",
            "Historical timeline data is unavailable",
        )
    else:
        connection.send_result(msg["id"], payload)


@websocket_api.websocket_command(
    {
        vol.Required("type"): ANALYSIS_TELEMETRY_COMPARE_WS_TYPE,
        vol.Required("selections"): vol.All(
            [
                {
                    vol.Required("driver_number"): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=99)
                    ),
                    vol.Required("lap_number"): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=500)
                    ),
                }
            ],
            vol.Length(min=1, max=4),
        ),
        _ENTRY_ID_SCHEMA: str,
    }
)
@websocket_api.async_response
async def _ws_compare_replay_telemetry(
    hass: HomeAssistant,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    """Return selected, bounded, downsampled replay lap telemetry."""
    runtime = _resolve_runtime(hass, msg.get("entry_id"))
    telemetry = (
        runtime.analysis.telemetry if runtime is not None and runtime.analysis else None
    )
    if telemetry is None:
        connection.send_error(msg["id"], "not_loaded", "Replay telemetry is not loaded")
        return
    try:
        result = await telemetry.async_compare(msg["selections"])
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_request", str(err))
    except Exception:  # noqa: BLE001
        connection.send_error(
            msg["id"],
            "provider_unavailable",
            "Replay telemetry is unavailable",
        )
    else:
        connection.send_result(msg["id"], result)


def _resolve_runtime(
    hass: HomeAssistant,
    entry_id: str | None,
) -> F1RuntimeData | None:
    if entry_id:
        return runtime_from_hass(hass, entry_id)
    runtimes = [
        runtime
        for entry in hass.config_entries.async_entries(DOMAIN)
        if (runtime := runtime_from_hass(hass, entry.entry_id)) is not None
    ]
    return runtimes[0] if len(runtimes) == 1 else None


def _analysis_payload(runtime: F1RuntimeData) -> dict[str, Any]:
    analysis = runtime.analysis
    if analysis is None:
        return {
            "protocol_version": ANALYSIS_PROTOCOL_VERSION,
            "status": "not_loaded",
        }
    payload = analysis.store.snapshot()
    capabilities = dict(payload.get("capabilities", {}))
    live = runtime.live
    availability = live.availability if live is not None else None
    replay = runtime.replay.controller if runtime.replay is not None else None
    replay_status = replay.get_playback_status() if replay is not None else {}
    session_manager = getattr(replay, "session_manager", None)
    get_index = getattr(session_manager, "get_loaded_index", None)
    replay_index = get_index() if callable(get_index) else None
    capabilities.update(
        {
            "requested_streams": sorted(runtime.capabilities.requested_streams),
            "active_streams": sorted(runtime.capabilities.active_streams),
            "connection": (
                "connected"
                if live is not None and bool(getattr(live.bus, "is_connected", False))
                else "waiting"
            ),
            "availability": {
                "is_live": bool(getattr(availability, "is_live", False)),
                "reason": getattr(availability, "reason", None),
            },
            "telemetry_compare": (
                "ready"
                if runtime.replay is not None
                and runtime.replay.controller.get_planned_playback_details()
                else "load_replay_first"
            ),
        }
    )
    return {
        **payload,
        "status": "ready",
        "capabilities": capabilities,
        "replay": {
            "session_id": getattr(replay_index, "session_id", None),
            "state": getattr(getattr(replay, "state", None), "value", "idle"),
            "position_ms": replay_status.get("position_ms"),
            "duration_ms": replay_status.get("duration_ms"),
            "paused": replay_status.get("paused", False),
        },
    }


def _analysis_hub(
    hass: HomeAssistant,
    runtime: F1RuntimeData,
    store: Phase4AnalysisStore,
) -> _AnalysisBroadcastHub:
    hub = _ANALYSIS_HUBS.get(store)
    if hub is None or hub.closed:
        hub = _AnalysisBroadcastHub(hass, runtime, store)
        _ANALYSIS_HUBS[store] = hub
    return hub


class _AnalysisBroadcastHub:
    """Build one Phase 4 snapshot for all connected dashboard clients."""

    def __init__(
        self,
        hass: HomeAssistant,
        runtime: F1RuntimeData,
        store: Phase4AnalysisStore,
    ) -> None:
        self._hass = hass
        self._runtime = runtime
        self._store = store
        self._subscribers: set[_AnalysisSubscription] = set()
        self._unsubscribe_store = store.add_listener(self._broadcast)
        self._unsubscribe_close = store.add_close_listener(self.async_close)
        self._demand_tasks: set[asyncio.Task] = set()
        self.closed = False

    def add(self, subscription: _AnalysisSubscription) -> Callable[[], None]:
        """Add one client and turn on card-requested streams when necessary."""
        first = not self._subscribers
        self._subscribers.add(subscription)
        if first:
            self._set_demand(active=True)

        @callback
        def _unsubscribe() -> None:
            if self.closed:
                return
            self._subscribers.discard(subscription)
            if self._subscribers or self.closed:
                return
            self.closed = True
            self._unsubscribe_store()
            _ANALYSIS_HUBS.pop(self._store, None)
            self._set_demand(active=False)
            self._release_close_listener()

        return _unsubscribe

    def payload(self) -> dict[str, Any]:
        """Return the latest complete Weekend Hub snapshot."""
        return _analysis_payload(self._runtime)

    @callback
    def _broadcast(self) -> None:
        if self.closed:
            return
        payload = self.payload()
        for subscriber in tuple(self._subscribers):
            subscriber.receive(payload)

    def _set_demand(self, *, active: bool, apply: bool = True) -> None:
        live = self._runtime.live
        bus = live.bus if live is not None else None
        update_streams = getattr(bus, "async_update_streams", None)
        if live is None or not callable(update_streams):
            return
        requested = set(self._runtime.capabilities.requested_streams)
        if active:
            requested.update(PHASE4_ANALYSIS_STREAMS)
            for stream in PHASE4_ANALYSIS_STREAMS:
                reasons = set(self._runtime.capabilities.stream_reasons.get(stream, ()))
                reasons.add("weekend_hub_card")
                self._runtime.capabilities.stream_reasons[stream] = tuple(
                    sorted(reasons)
                )
        else:
            for stream in PHASE4_ANALYSIS_STREAMS:
                reasons = set(self._runtime.capabilities.stream_reasons.get(stream, ()))
                reasons.discard("weekend_hub_card")
                if reasons:
                    self._runtime.capabilities.stream_reasons[stream] = tuple(
                        sorted(reasons)
                    )
                else:
                    self._runtime.capabilities.stream_reasons.pop(stream, None)
                    requested.discard(stream)
        self._runtime.capabilities.requested_streams = frozenset(requested)
        if not apply:
            return

        async def _async_apply() -> None:
            requested = set(self._runtime.capabilities.requested_streams)
            await update_streams(requested)
            if self._store.closed or requested != set(
                self._runtime.capabilities.requested_streams
            ):
                return
            should_run = bool(getattr(live.availability, "is_live", False))
            if requested and should_run:
                await bus.start()
            elif not requested:
                await bus.async_close()
            self._runtime.capabilities.active_streams = bus.active_streams
            legacy = self._runtime.get("signalr_stream_capabilities")
            if isinstance(legacy, dict):
                legacy["requested_streams"] = frozenset(requested)
                legacy["active_live_streams"] = bus.active_streams
                legacy["stream_reasons"] = dict(
                    self._runtime.capabilities.stream_reasons
                )

        task = self._hass.async_create_task(_async_apply())
        self._demand_tasks.add(task)
        task.add_done_callback(self._demand_done)

    def _demand_done(self, task: asyncio.Task) -> None:
        self._demand_tasks.discard(task)
        self._release_close_listener()

    def _release_close_listener(self) -> None:
        if self.closed and not self._demand_tasks:
            self._unsubscribe_close()

    async def async_close(self) -> None:
        """Terminate subscriptions and await work owned by the retiring store."""
        self.closed = True
        self._unsubscribe_store()
        if _ANALYSIS_HUBS.get(self._store) is self:
            _ANALYSIS_HUBS.pop(self._store, None)
        payload = {
            **self.payload(),
            "status": "closed",
            "retryable": True,
            "reason": "entry_unloaded",
        }
        for subscriber in tuple(self._subscribers):
            with suppress(Exception):
                subscriber.terminate(payload)
        self._subscribers.clear()
        self._set_demand(active=False, apply=False)
        tasks = tuple(self._demand_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._demand_tasks.clear()
        self._unsubscribe_close()


class _AnalysisSubscription:
    """Per-client throttle for complete Phase 4 snapshots."""

    def __init__(
        self,
        hass: HomeAssistant,
        connection: Any,
        msg_id: int,
        hub: _AnalysisBroadcastHub,
        throttle_seconds: float,
    ) -> None:
        self._hass = hass
        self._connection = connection
        self._msg_id = msg_id
        self._hub = hub
        self._throttle_seconds = throttle_seconds
        self._last_sent = 0.0
        self._pending_handle: asyncio.TimerHandle | None = None
        self._pending_payload: dict[str, Any] | None = None
        self._closed = False
        self._unsubscribe_hub = hub.add(self)

    @callback
    def async_send_initial(self) -> None:
        """Send the initial complete snapshot."""
        self._send(self._hub.payload())

    @callback
    def receive(self, payload: dict[str, Any]) -> None:
        """Coalesce rapid timing updates to the newest complete snapshot."""
        if self._closed:
            return
        self._pending_payload = payload
        if self._pending_handle is not None:
            return
        elapsed = self._hass.loop.time() - self._last_sent
        delay = max(0.0, self._throttle_seconds - elapsed)
        if delay == 0:
            self._send_pending()
        else:
            self._pending_handle = self._hass.loop.call_later(delay, self._send_pending)

    @callback
    def _send_pending(self) -> None:
        self._pending_handle = None
        payload = self._pending_payload
        self._pending_payload = None
        if payload is not None:
            self._send(payload)

    @callback
    def _send(self, payload: dict[str, Any]) -> None:
        self._last_sent = self._hass.loop.time()
        self._connection.send_event(self._msg_id, payload)

    @callback
    def unsubscribe(self) -> None:
        """Detach the client and cancel pending sends."""
        if self._closed:
            return
        self._closed = True
        self._unsubscribe_hub()
        if self._pending_handle is not None:
            self._pending_handle.cancel()
            self._pending_handle = None
        self._pending_payload = None

    def terminate(self, payload: dict[str, Any]) -> None:
        """Send the terminal state immediately, bypassing the throttle."""
        if self._closed:
            return
        try:
            self._send(payload)
        finally:
            self.unsubscribe()
            if self._connection.subscriptions.get(self._msg_id) == self.unsubscribe:
                self._connection.subscriptions.pop(self._msg_id, None)
