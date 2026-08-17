"""Websocket API for shared F1 track map snapshots and deltas."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
import voluptuous as vol

from .const import DOMAIN
from .feature_plan import TRACK_MAP_STREAMS
from .runtime import runtime_from_hass
from .track_map import TRACK_MAP_STATUS_ACTIVE, TrackMapStore

TRACK_MAP_WS_MARKER = "__track_map_ws_registered__"
TRACK_MAP_WS_GET_TYPE = f"{DOMAIN}/track_map/get"
TRACK_MAP_WS_SUBSCRIBE_TYPE = f"{DOMAIN}/track_map/subscribe"
TRACK_MAP_WS_RESYNC_TYPE = f"{DOMAIN}/track_map/resync"
TRACK_MAP_API_STATUS_NOT_LOADED = "not_loaded"
TRACK_MAP_API_STATUS_NO_GEOMETRY = "no_geometry"
TRACK_MAP_WS_ERROR_NOT_LOADED = "not_loaded"
TRACK_MAP_PROTOCOL_V1 = 1
TRACK_MAP_PROTOCOL_V2 = 2
DEFAULT_TRACK_MAP_THROTTLE_MS = 500

_ENTRY_ID_SCHEMA = vol.Optional("entry_id")
_THROTTLE_MS_SCHEMA = vol.Optional(
    "throttle_ms",
    default=DEFAULT_TRACK_MAP_THROTTLE_MS,
)
_PROTOCOL_VERSION_SCHEMA = vol.Optional(
    "protocol_version",
    default=TRACK_MAP_PROTOCOL_V1,
)
_TRACK_MAP_HUBS: dict[TrackMapStore, _TrackMapBroadcastHub] = {}


def async_register_track_map_websocket(hass: HomeAssistant) -> None:
    """Register track map websocket commands once per Home Assistant runtime."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get(TRACK_MAP_WS_MARKER):
        return
    websocket_api.async_register_command(hass, _ws_get_track_map_snapshot)
    websocket_api.async_register_command(hass, _ws_subscribe_track_map_snapshot)
    websocket_api.async_register_command(hass, _ws_resync_track_map_snapshot)
    root[TRACK_MAP_WS_MARKER] = True


@websocket_api.websocket_command(
    {
        vol.Required("type"): TRACK_MAP_WS_GET_TYPE,
        _ENTRY_ID_SCHEMA: str,
    }
)
@websocket_api.async_response
async def _ws_get_track_map_snapshot(
    hass: HomeAssistant,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    """Return the current track map snapshot using the v1 contract."""
    connection.send_result(
        msg["id"],
        _track_map_payload(hass, msg.get("entry_id")),
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): TRACK_MAP_WS_RESYNC_TYPE,
        _ENTRY_ID_SCHEMA: str,
        _PROTOCOL_VERSION_SCHEMA: vol.In(
            (TRACK_MAP_PROTOCOL_V1, TRACK_MAP_PROTOCOL_V2)
        ),
    }
)
@websocket_api.async_response
async def _ws_resync_track_map_snapshot(
    hass: HomeAssistant,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    """Return a full state snapshot after a client detects a sequence gap."""
    store = _resolve_track_map_store(hass, msg.get("entry_id"))
    if store is None:
        connection.send_error(
            msg["id"],
            TRACK_MAP_WS_ERROR_NOT_LOADED,
            "Track map data is not loaded yet; retry the subscription",
        )
        return
    hub = _TRACK_MAP_HUBS.get(store)
    if hub is None:
        snapshot = store.snapshot()
        payload = (
            _v2_snapshot_payload(
                store,
                snapshot,
                sequence=0,
                geometry_revision=int(snapshot.get("track") is not None),
            )
            if msg.get("protocol_version", TRACK_MAP_PROTOCOL_V1)
            == TRACK_MAP_PROTOCOL_V2
            else _v1_payload(store, snapshot)
        )
    else:
        payload = hub.full_payload(msg.get("protocol_version", TRACK_MAP_PROTOCOL_V1))
    connection.send_result(
        msg["id"],
        payload,
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): TRACK_MAP_WS_SUBSCRIBE_TYPE,
        _ENTRY_ID_SCHEMA: str,
        _THROTTLE_MS_SCHEMA: vol.All(vol.Coerce(int), vol.Range(min=0, max=5000)),
        _PROTOCOL_VERSION_SCHEMA: vol.In(
            (TRACK_MAP_PROTOCOL_V1, TRACK_MAP_PROTOCOL_V2)
        ),
    }
)
@callback
def _ws_subscribe_track_map_snapshot(
    hass: HomeAssistant,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    """Subscribe to shared track map snapshot or delta updates."""
    store = _resolve_track_map_store(hass, msg.get("entry_id"))
    if store is None:
        connection.send_error(
            msg["id"],
            TRACK_MAP_WS_ERROR_NOT_LOADED,
            "Track map data is not loaded yet; retry the subscription",
        )
        return

    subscription = _TrackMapSnapshotSubscription(
        hass,
        connection,
        msg["id"],
        _track_map_hub(hass, store),
        msg.get("protocol_version", TRACK_MAP_PROTOCOL_V1),
        msg["throttle_ms"] / 1000,
    )
    connection.subscriptions[msg["id"]] = subscription.unsubscribe
    connection.send_result(msg["id"])
    subscription.async_send_initial()


def _track_map_payload(
    hass: HomeAssistant,
    entry_id: str | None = None,
) -> dict[str, Any]:
    store = _resolve_track_map_store(hass, entry_id)
    if store is None:
        return _not_loaded_payload(entry_id)
    snapshot = store.snapshot()
    return _v1_payload(store, snapshot)


def _not_loaded_payload(entry_id: str | None = None) -> dict[str, Any]:
    return {
        "entry_id": entry_id,
        "status": TRACK_MAP_API_STATUS_NOT_LOADED,
        "snapshot": None,
    }


def _resolve_track_map_store(
    hass: HomeAssistant,
    entry_id: str | None = None,
) -> TrackMapStore | None:
    if entry_id:
        runtime = runtime_from_hass(hass, entry_id)
        store = runtime.track_map_store if runtime is not None else None
        if isinstance(store, TrackMapStore):
            return store
        root = hass.data.get(DOMAIN)
        legacy = root.get(entry_id) if isinstance(root, dict) else None
        legacy_store = (
            legacy.get("track_map_store") if isinstance(legacy, dict) else None
        )
        return legacy_store if isinstance(legacy_store, TrackMapStore) else None

    stores = [
        runtime.track_map_store
        for entry in hass.config_entries.async_entries(DOMAIN)
        if (runtime := runtime_from_hass(hass, entry.entry_id)) is not None
        and isinstance(runtime.track_map_store, TrackMapStore)
    ]
    if len(stores) == 1:
        return stores[0]
    if stores:
        return None
    root = hass.data.get(DOMAIN)
    legacy_stores = (
        [
            store
            for value in root.values()
            if isinstance(root, dict) and isinstance(value, dict)
            if isinstance((store := value.get("track_map_store")), TrackMapStore)
        ]
        if isinstance(root, dict)
        else []
    )
    return legacy_stores[0] if len(legacy_stores) == 1 else None


def _track_map_hub(
    hass: HomeAssistant,
    store: TrackMapStore,
) -> _TrackMapBroadcastHub:
    hub = _TRACK_MAP_HUBS.get(store)
    if hub is None or hub.closed:
        hub = _TrackMapBroadcastHub(hass, store)
        _TRACK_MAP_HUBS[store] = hub
    return hub


class _TrackMapBroadcastHub:
    """Build each store snapshot and delta once for all websocket clients."""

    def __init__(self, hass: HomeAssistant, store: TrackMapStore) -> None:
        self._hass = hass
        self._store = store
        self._subscribers: set[_TrackMapSnapshotSubscription] = set()
        self._snapshot = store.snapshot()
        self._sequence = 0
        self._geometry_revision = int(self._snapshot.get("track") is not None)
        self._unsub_store = store.add_listener(self._broadcast_update)
        self.closed = False

    def add(self, subscription: _TrackMapSnapshotSubscription) -> Callable[[], None]:
        """Add a client and return its shared-hub unsubscribe callback."""
        first_subscriber = not self._subscribers
        self._subscribers.add(subscription)
        if first_subscriber:
            self._set_track_map_demand(active=True)

        @callback
        def _unsubscribe() -> None:
            self._subscribers.discard(subscription)
            if self._subscribers or self.closed:
                return
            self.closed = True
            self._unsub_store()
            _TRACK_MAP_HUBS.pop(self._store, None)
            self._set_track_map_demand(active=False)

        return _unsubscribe

    def _set_track_map_demand(self, *, active: bool) -> None:
        """Add or remove transient Track Map streams from the shared bus."""
        runtime = runtime_from_hass(self._hass, self._store.entry_id)
        live = runtime.live if runtime is not None else None
        bus = live.bus if live is not None else None
        update_streams = getattr(bus, "async_update_streams", None)
        if runtime is None or not callable(update_streams):
            return
        requested = set(runtime.capabilities.requested_streams)
        if active:
            requested.update(TRACK_MAP_STREAMS)
            for stream in TRACK_MAP_STREAMS:
                reasons = set(runtime.capabilities.stream_reasons.get(stream, ()))
                reasons.add("track_map_card")
                runtime.capabilities.stream_reasons[stream] = tuple(sorted(reasons))
        else:
            for stream in TRACK_MAP_STREAMS:
                reasons = set(runtime.capabilities.stream_reasons.get(stream, ()))
                reasons.discard("track_map_card")
                if reasons:
                    runtime.capabilities.stream_reasons[stream] = tuple(sorted(reasons))
                    continue
                runtime.capabilities.stream_reasons.pop(stream, None)
                requested.discard(stream)
        runtime.capabilities.requested_streams = frozenset(requested)

        async def _async_apply_demand() -> None:
            await update_streams(requested)
            availability = live.availability if live is not None else None
            should_run = active or bool(getattr(availability, "is_live", False))
            if requested and should_run:
                await bus.start()
            else:
                await bus.async_close()
            runtime.capabilities.active_streams = bus.active_streams
            legacy_capabilities = runtime.get("signalr_stream_capabilities")
            if isinstance(legacy_capabilities, dict):
                legacy_capabilities["requested_streams"] = frozenset(requested)
                legacy_capabilities["active_live_streams"] = bus.active_streams
                legacy_capabilities["stream_reasons"] = dict(
                    runtime.capabilities.stream_reasons
                )

        self._hass.async_create_task(_async_apply_demand())

    def full_payload(self, protocol_version: int) -> dict[str, Any]:
        """Return the latest full state for one protocol version."""
        if protocol_version == TRACK_MAP_PROTOCOL_V2:
            return _v2_snapshot_payload(
                self._store,
                self._snapshot,
                self._sequence,
                self._geometry_revision,
            )
        return _v1_payload(self._store, self._snapshot)

    @callback
    def _broadcast_update(self) -> None:
        previous = self._snapshot
        current = self._store.snapshot()
        self._sequence += 1
        if previous.get("track") != current.get("track"):
            self._geometry_revision += 1
        self._snapshot = current
        v1_payload = _v1_payload(self._store, current)
        v2_payload = _v2_delta_payload(
            self._store,
            previous,
            current,
            self._sequence,
            self._geometry_revision,
        )
        for subscriber in tuple(self._subscribers):
            subscriber.receive(v1_payload, v2_payload)


class _TrackMapSnapshotSubscription:
    """Per-client throttle around a shared track map broadcast hub."""

    def __init__(
        self,
        hass: HomeAssistant,
        connection: Any,
        msg_id: int,
        hub: _TrackMapBroadcastHub,
        protocol_version: int,
        throttle_seconds: float,
    ) -> None:
        self._hass = hass
        self._connection = connection
        self._msg_id = msg_id
        self._hub = hub
        self._protocol_version = protocol_version
        self._throttle_seconds = throttle_seconds
        self._last_sent = 0.0
        self._pending_handle: asyncio.TimerHandle | None = None
        self._pending_payload: dict[str, Any] | None = None
        self._unsub_hub = hub.add(self)

    @callback
    def async_send_initial(self) -> None:
        """Send a full initial state to the websocket connection."""
        self._send(self._hub.full_payload(self._protocol_version))

    @callback
    def receive(
        self,
        v1_payload: dict[str, Any],
        v2_payload: dict[str, Any],
    ) -> None:
        """Receive the already-built shared payload for this protocol."""
        if self._protocol_version == TRACK_MAP_PROTOCOL_V2:
            self._pending_payload = _merge_v2_deltas(
                self._pending_payload,
                v2_payload,
            )
        else:
            self._pending_payload = v1_payload
        if self._pending_handle is not None:
            return
        if self._throttle_seconds <= 0:
            self._send_pending()
            return
        elapsed = self._hass.loop.time() - self._last_sent
        delay = max(0.0, self._throttle_seconds - elapsed)
        if delay == 0:
            self._send_pending()
            return
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
        """Unsubscribe from the hub and cancel pending sends."""
        self._unsub_hub()
        if self._pending_handle is not None:
            self._pending_handle.cancel()
            self._pending_handle = None
        self._pending_payload = None


def _v1_payload(store: TrackMapStore, snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "entry_id": store.entry_id,
        "status": _snapshot_api_status(snapshot),
        "snapshot": snapshot,
    }


def _v2_snapshot_payload(
    store: TrackMapStore,
    snapshot: dict[str, Any],
    sequence: int,
    geometry_revision: int,
) -> dict[str, Any]:
    return {
        "protocol_version": TRACK_MAP_PROTOCOL_V2,
        "type": "snapshot",
        "entry_id": store.entry_id,
        "sequence": sequence,
        "geometry_revision": geometry_revision,
        "status": _snapshot_api_status(snapshot),
        "snapshot": snapshot,
    }


def _v2_delta_payload(
    store: TrackMapStore,
    previous: dict[str, Any],
    current: dict[str, Any],
    sequence: int,
    geometry_revision: int,
) -> dict[str, Any]:
    previous_drivers = {
        str(driver.get("racing_number")): driver
        for driver in previous.get("drivers", [])
        if isinstance(driver, dict) and driver.get("racing_number") is not None
    }
    current_drivers = {
        str(driver.get("racing_number")): driver
        for driver in current.get("drivers", [])
        if isinstance(driver, dict) and driver.get("racing_number") is not None
    }
    changes = {
        racing_number: driver
        for racing_number, driver in current_drivers.items()
        if previous_drivers.get(racing_number) != driver
    }
    removed = sorted(set(previous_drivers) - set(current_drivers))
    patch = {
        key: value
        for key, value in current.items()
        if key != "drivers" and previous.get(key) != value
    }
    return {
        "protocol_version": TRACK_MAP_PROTOCOL_V2,
        "type": "delta",
        "entry_id": store.entry_id,
        "base_sequence": sequence - 1,
        "sequence": sequence,
        "geometry_revision": geometry_revision,
        "status": _snapshot_api_status(current),
        "changes": changes,
        "removed": removed,
        "patch": patch,
    }


def _merge_v2_deltas(
    pending: dict[str, Any] | None,
    incoming: dict[str, Any],
) -> dict[str, Any]:
    """Coalesce throttled deltas without losing their original base sequence."""
    if pending is None or pending.get("type") != "delta":
        return incoming
    changes = dict(pending.get("changes", {}))
    removed = set(pending.get("removed", []))
    for racing_number, driver in incoming.get("changes", {}).items():
        changes[racing_number] = driver
        removed.discard(racing_number)
    for racing_number in incoming.get("removed", []):
        changes.pop(racing_number, None)
        removed.add(racing_number)
    return {
        **incoming,
        "base_sequence": pending.get("base_sequence", incoming["base_sequence"]),
        "changes": changes,
        "removed": sorted(removed),
        "patch": {**pending.get("patch", {}), **incoming.get("patch", {})},
    }


def _snapshot_api_status(snapshot: dict[str, Any]) -> str:
    if snapshot["status"] == TRACK_MAP_STATUS_ACTIVE and snapshot.get("track") is None:
        return TRACK_MAP_API_STATUS_NO_GEOMETRY
    return snapshot["status"]
