"""Websocket API for F1 track map snapshots."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
import voluptuous as vol

from .const import DOMAIN
from .track_map import TRACK_MAP_STATUS_ACTIVE, TrackMapStore

TRACK_MAP_WS_MARKER = "__track_map_ws_registered__"
TRACK_MAP_WS_GET_TYPE = f"{DOMAIN}/track_map/get"
TRACK_MAP_WS_SUBSCRIBE_TYPE = f"{DOMAIN}/track_map/subscribe"
TRACK_MAP_API_STATUS_NOT_LOADED = "not_loaded"
TRACK_MAP_API_STATUS_NO_GEOMETRY = "no_geometry"
DEFAULT_TRACK_MAP_THROTTLE_MS = 500

_ENTRY_ID_SCHEMA = vol.Optional("entry_id")
_THROTTLE_MS_SCHEMA = vol.Optional(
    "throttle_ms",
    default=DEFAULT_TRACK_MAP_THROTTLE_MS,
)


def async_register_track_map_websocket(hass: HomeAssistant) -> None:
    """Register track map websocket commands once per Home Assistant runtime."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get(TRACK_MAP_WS_MARKER):
        return
    websocket_api.async_register_command(hass, _ws_get_track_map_snapshot)
    websocket_api.async_register_command(hass, _ws_subscribe_track_map_snapshot)
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
    """Return the current track map snapshot."""
    connection.send_result(
        msg["id"],
        _track_map_payload(hass, msg.get("entry_id")),
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): TRACK_MAP_WS_SUBSCRIBE_TYPE,
        _ENTRY_ID_SCHEMA: str,
        _THROTTLE_MS_SCHEMA: vol.All(vol.Coerce(int), vol.Range(min=0, max=5000)),
    }
)
@callback
def _ws_subscribe_track_map_snapshot(
    hass: HomeAssistant,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    """Subscribe to track map snapshot updates."""
    store = _resolve_track_map_store(hass, msg.get("entry_id"))
    if store is None:
        connection.send_result(
            msg["id"],
            _not_loaded_payload(msg.get("entry_id")),
        )
        return

    subscription = _TrackMapSnapshotSubscription(
        hass,
        connection,
        msg["id"],
        store,
        msg["throttle_ms"] / 1000,
    )
    connection.subscriptions[msg["id"]] = subscription.unsubscribe
    connection.send_result(msg["id"])
    subscription.async_send_snapshot()


def _track_map_payload(
    hass: HomeAssistant,
    entry_id: str | None = None,
) -> dict[str, Any]:
    store = _resolve_track_map_store(hass, entry_id)
    if store is None:
        return _not_loaded_payload(entry_id)
    snapshot = store.snapshot()
    return {
        "entry_id": store.entry_id,
        "status": _snapshot_api_status(snapshot),
        "snapshot": snapshot,
    }


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
    root = hass.data.get(DOMAIN)
    if not isinstance(root, dict):
        return None
    if entry_id:
        data = root.get(entry_id)
        if not isinstance(data, dict):
            return None
        store = data.get("track_map_store")
        return store if isinstance(store, TrackMapStore) else None

    for data in root.values():
        if not isinstance(data, dict):
            continue
        store = data.get("track_map_store")
        if isinstance(store, TrackMapStore):
            return store
    return None


class _TrackMapSnapshotSubscription:
    """Per-connection track map subscription with throttled sends."""

    def __init__(
        self,
        hass: HomeAssistant,
        connection: Any,
        msg_id: int,
        store: TrackMapStore,
        throttle_seconds: float,
    ) -> None:
        self._hass = hass
        self._connection = connection
        self._msg_id = msg_id
        self._store = store
        self._throttle_seconds = throttle_seconds
        self._last_sent = 0.0
        self._pending_handle: asyncio.TimerHandle | None = None
        self._unsub_store = store.add_listener(self._schedule_snapshot)

    @callback
    def async_send_snapshot(self) -> None:
        """Send a snapshot event to the websocket connection."""
        self._pending_handle = None
        self._last_sent = self._hass.loop.time()
        snapshot = self._store.snapshot()
        self._connection.send_event(
            self._msg_id,
            {
                "entry_id": self._store.entry_id,
                "status": _snapshot_api_status(snapshot),
                "snapshot": snapshot,
            },
        )

    @callback
    def _schedule_snapshot(self) -> None:
        if self._pending_handle is not None:
            return
        if self._throttle_seconds <= 0:
            self.async_send_snapshot()
            return
        elapsed = self._hass.loop.time() - self._last_sent
        delay = max(0.0, self._throttle_seconds - elapsed)
        if delay == 0:
            self.async_send_snapshot()
            return
        self._pending_handle = self._hass.loop.call_later(
            delay,
            self.async_send_snapshot,
        )

    @callback
    def unsubscribe(self) -> None:
        """Unsubscribe from store updates and cancel pending sends."""
        self._unsub_store()
        if self._pending_handle is not None:
            self._pending_handle.cancel()
            self._pending_handle = None


def _snapshot_api_status(snapshot: dict[str, Any]) -> str:
    if snapshot["status"] == TRACK_MAP_STATUS_ACTIVE and snapshot.get("track") is None:
        return TRACK_MAP_API_STATUS_NO_GEOMETRY
    return snapshot["status"]
