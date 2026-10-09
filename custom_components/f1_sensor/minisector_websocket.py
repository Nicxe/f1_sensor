"""Versioned shared WebSocket transport for bounded minisector statuses."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime
import json
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
import voluptuous as vol

from .const import DOMAIN
from .minisectors import MiniSectorStateStore

MINISECTOR_WS_MARKER = "__minisector_ws_registered__"
MINISECTOR_WS_SUBSCRIBE_TYPE = f"{DOMAIN}/minisectors/subscribe"
MINISECTOR_PROTOCOL_V1 = 1
MINISECTOR_WS_ERROR_NOT_LOADED = "not_loaded"
MINISECTOR_THROTTLE_SECONDS = 0.25
MAX_MINISECTOR_EVENT_BYTES = 32 * 1024
MINISECTOR_TRAFFIC_WINDOW_SECONDS = 10.0
MAX_MINISECTOR_TRAFFIC_BYTES = 16 * 1024 * 10

_MINISECTOR_HUBS: dict[MiniSectorStateStore, _MiniSectorBroadcastHub] = {}


def async_register_minisector_websocket(hass: HomeAssistant) -> None:
    """Register the minisector subscription exactly once per HA runtime."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get(MINISECTOR_WS_MARKER):
        return
    websocket_api.async_register_command(hass, _ws_subscribe_minisectors)
    root[MINISECTOR_WS_MARKER] = True


@websocket_api.websocket_command(
    {
        vol.Required("type"): MINISECTOR_WS_SUBSCRIBE_TYPE,
        vol.Required("protocol_version"): vol.In((MINISECTOR_PROTOCOL_V1,)),
        vol.Required("entry_id"): str,
        vol.Required("source"): vol.In(("live", "replay")),
        vol.Required("session_key"): str,
    }
)
@callback
def _ws_subscribe_minisectors(
    hass: HomeAssistant,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    """Subscribe one card consumer to the matching bounded source context."""
    entry_id = msg["entry_id"].strip()
    session_key = msg["session_key"].strip()
    store = _resolve_minisector_store(hass, entry_id)
    if store is None:
        connection.send_error(
            msg["id"],
            MINISECTOR_WS_ERROR_NOT_LOADED,
            "Minisector data is not loaded for this F1 Sensor entry",
        )
        return
    if not entry_id or not session_key:
        connection.send_error(
            msg["id"],
            "invalid_format",
            "entry_id and session_key must be non-empty strings",
        )
        return

    subscription = _MiniSectorSubscription(
        hass,
        connection,
        msg["id"],
        _minisector_hub(hass, store),
        entry_id=entry_id,
        source=msg["source"],
        session_key=session_key,
    )
    connection.subscriptions[msg["id"]] = subscription.unsubscribe
    connection.send_result(msg["id"])
    subscription.send_initial()


def _resolve_minisector_store(
    hass: HomeAssistant,
    entry_id: str,
) -> MiniSectorStateStore | None:
    root = hass.data.get(DOMAIN)
    entry_data = root.get(entry_id) if isinstance(root, Mapping) else None
    coordinator = (
        entry_data.get("drivers_coordinator")
        if isinstance(entry_data, Mapping)
        else None
    )
    store = getattr(coordinator, "minisector_store", None)
    return (
        store if isinstance(store, MiniSectorStateStore) and not store.closed else None
    )


def _entry_data(hass: HomeAssistant, entry_id: str) -> Mapping[str, Any] | None:
    root = hass.data.get(DOMAIN)
    value = root.get(entry_id) if isinstance(root, Mapping) else None
    return value if isinstance(value, Mapping) else None


def _active_session_key(
    hass: HomeAssistant,
    entry_id: str,
    source: str,
) -> str | None:
    data = _entry_data(hass, entry_id)
    if data is None:
        return None
    if source == "replay":
        controller = data.get("replay_controller")
        snapshot = getattr(controller, "snapshot", None)
        get_snapshot = getattr(controller, "_get_snapshot", None)
        if not isinstance(snapshot, Mapping) and callable(get_snapshot):
            with suppress(Exception):
                snapshot = get_snapshot()
        selected = (
            snapshot.get("selected_session_key")
            if isinstance(snapshot, Mapping)
            else None
        )
        if selected is not None:
            return str(selected)
    session_info = data.get("session_info_coordinator")
    session_payload = getattr(session_info, "data", None)
    if isinstance(session_payload, Mapping) and session_payload.get("Key") is not None:
        return str(session_payload["Key"])
    return None


def _minisector_hub(
    hass: HomeAssistant,
    store: MiniSectorStateStore,
) -> _MiniSectorBroadcastHub:
    hub = _MINISECTOR_HUBS.get(store)
    if hub is None or hub.closed:
        hub = _MiniSectorBroadcastHub(hass, store)
        _MINISECTOR_HUBS[store] = hub
    return hub


class _MiniSectorBroadcastHub:
    """Share one store listener and one coalescing timer across all cards."""

    def __init__(self, hass: HomeAssistant, store: MiniSectorStateStore) -> None:
        self._hass = hass
        self._store = store
        self._snapshot = store.snapshot()
        self._dirty = False
        self._subscribers: set[_MiniSectorSubscription] = set()
        self._pending_handle: asyncio.TimerHandle | None = None
        self._last_flush = hass.loop.time()
        self._unsub_store = store.add_listener(self._queue_update)
        self._unsub_close = store.add_close_listener(self.close)
        self.closed = False

    def add(self, subscriber: _MiniSectorSubscription) -> Callable[[], None]:
        """Add one consumer and return an idempotent release callback."""
        self._subscribers.add(subscriber)

        @callback
        def _unsubscribe() -> None:
            if self.closed:
                return
            self._subscribers.discard(subscriber)
            if not self._subscribers:
                self.close()

        return _unsubscribe

    def current_snapshot(self) -> dict[str, Any]:
        """Return the latest complete state, including a pending source frame."""
        if self._dirty:
            self._snapshot = self._store.snapshot()
            self._dirty = False
        return self._snapshot

    @callback
    def _queue_update(self) -> None:
        self._dirty = True
        if self.closed or not self._subscribers or self._pending_handle is not None:
            return
        elapsed = self._hass.loop.time() - self._last_flush
        delay = max(0.0, MINISECTOR_THROTTLE_SECONDS - elapsed)
        if delay == 0:
            self._flush()
            return
        self._pending_handle = self._hass.loop.call_later(delay, self._flush)

    @callback
    def _flush(self) -> None:
        self._pending_handle = None
        if self.closed:
            return
        self._last_flush = self._hass.loop.time()
        self._snapshot = self._store.snapshot()
        self._dirty = False
        for subscriber in tuple(self._subscribers):
            subscriber.receive(self._snapshot)

    @callback
    def close(self) -> None:
        """Release the sole source listener and terminate active consumers."""
        if self.closed:
            return
        self.closed = True
        if self._pending_handle is not None:
            self._pending_handle.cancel()
            self._pending_handle = None
        self._unsub_store()
        self._unsub_close()
        if _MINISECTOR_HUBS.get(self._store) is self:
            _MINISECTOR_HUBS.pop(self._store, None)
        for subscriber in tuple(self._subscribers):
            subscriber.terminate("source_inactive")
        self._subscribers.clear()


class _MiniSectorSubscription:
    """Track sequence, context and traffic bounds for one WebSocket consumer."""

    def __init__(
        self,
        hass: HomeAssistant,
        connection: Any,
        msg_id: int,
        hub: _MiniSectorBroadcastHub,
        *,
        entry_id: str,
        source: str,
        session_key: str,
    ) -> None:
        self._hass = hass
        self._connection = connection
        self._msg_id = msg_id
        self._hub = hub
        self._entry_id = entry_id
        self._source = source
        self._session_key = session_key
        self._snapshot: dict[str, Any] | None = None
        self._generation: str | None = None
        self._sequence = 0
        self._available = False
        self._unavailable_reason: str | None = None
        self._traffic: deque[tuple[float, int]] = deque()
        self._traffic_blocked_until = 0.0
        self._closed = False
        self._unsub_hub = hub.add(self)

    @callback
    def send_initial(self) -> None:
        """Send the complete current context at sequence zero."""
        self.receive(self._hub.current_snapshot(), initial=True)

    @callback
    def receive(self, snapshot: dict[str, Any], *, initial: bool = False) -> None:
        """Publish a complete snapshot, sparse delta, reset or unavailability."""
        if self._closed:
            return
        if self._hass.loop.time() < self._traffic_blocked_until:
            self._snapshot = snapshot
            return
        generation = str(snapshot.get("generation", "0"))
        unavailable_reason = self._availability_reason(snapshot)
        if unavailable_reason is not None:
            if (
                not initial
                and not self._available
                and unavailable_reason == self._unavailable_reason
                and generation == self._generation
            ):
                self._snapshot = snapshot
                return
            self._sequence = (
                0 if initial or generation != self._generation else self._sequence + 1
            )
            event = self._event_base("unavailable", generation, self._sequence)
            event.update({"reason": unavailable_reason, "retryable": True})
            self._snapshot = snapshot
            self._generation = generation
            self._available = False
            self._unavailable_reason = unavailable_reason
            self._send_bounded(event)
            return

        if initial or self._snapshot is None or generation != self._generation:
            self._sequence = 0
            event = self._snapshot_event(snapshot, generation, self._sequence)
        elif not self._available:
            self._sequence += 1
            event = self._snapshot_event(snapshot, generation, self._sequence)
        else:
            event = self._change_event(self._snapshot, snapshot, generation)
            if event is None:
                self._snapshot = snapshot
                return
            self._sequence += 1
            event["sequence"] = self._sequence

        self._snapshot = snapshot
        self._generation = generation
        self._available = True
        self._unavailable_reason = None
        if not self._send_bounded(event):
            self._available = False
            self._unavailable_reason = "bounds_exceeded"

    def _availability_reason(self, snapshot: Mapping[str, Any]) -> str | None:
        reason = snapshot.get("unavailable_reason")
        if isinstance(reason, str) and reason:
            return reason
        if snapshot.get("source") != self._source:
            return "source_inactive"
        if self._source == "live":
            root = self._hass.data.get(DOMAIN)
            manager = (
                root.get("no_spoiler_manager") if isinstance(root, Mapping) else None
            )
            if bool(getattr(manager, "is_active", False)):
                return "spoiler_protected"
            data = _entry_data(self._hass, self._entry_id)
            live_state = data.get("live_state") if data is not None else None
            if live_state is not None and getattr(live_state, "is_live", True) is False:
                return "source_inactive"
        active_session = _active_session_key(
            self._hass,
            self._entry_id,
            self._source,
        )
        if active_session != self._session_key:
            return "session_unavailable"
        return None

    def _snapshot_event(
        self,
        snapshot: Mapping[str, Any],
        generation: str,
        sequence: int,
    ) -> dict[str, Any]:
        event = self._event_base("snapshot", generation, sequence)
        event.update(
            {
                "reset_reason": _protocol_reset_reason(
                    snapshot.get("last_reset_reason")
                ),
                "drivers": _transport_drivers(snapshot.get("drivers")),
            }
        )
        return event

    def _change_event(
        self,
        previous: Mapping[str, Any],
        current: Mapping[str, Any],
        generation: str,
    ) -> dict[str, Any] | None:
        previous_drivers = _transport_drivers(previous.get("drivers"))
        current_drivers = _transport_drivers(current.get("drivers"))
        changed, removed = _driver_changes(
            previous_drivers,
            current_drivers,
        )
        if not changed and not removed:
            return None
        event_type = "reset" if removed else "delta"
        event = self._event_base(event_type, generation, self._sequence + 1)
        if event_type == "reset":
            affected = sorted(set(changed) | set(removed), key=_numeric_sort_key)
            event.update(
                {
                    "reason": _protocol_reset_reason(current.get("last_reset_reason")),
                    "scope": {"drivers": affected},
                    "drivers": {
                        driver: current_drivers[driver]
                        for driver in affected
                        if driver in current_drivers
                    },
                }
            )
        else:
            event["drivers"] = changed
        return event

    def _event_base(
        self,
        event_type: str,
        generation: str,
        sequence: int,
    ) -> dict[str, Any]:
        return {
            "protocol_version": MINISECTOR_PROTOCOL_V1,
            "type": event_type,
            "entry_id": self._entry_id,
            "source": self._source,
            "session_key": self._session_key,
            "generation": generation,
            "sequence": sequence,
            "generated_at": datetime.now(UTC).isoformat(),
            "stream_timestamp": None,
        }

    def _send_bounded(self, event: dict[str, Any]) -> bool:
        encoded_size = len(
            json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode()
        )
        now = self._hass.loop.time()
        while (
            self._traffic
            and now - self._traffic[0][0] >= MINISECTOR_TRAFFIC_WINDOW_SECONDS
        ):
            self._traffic.popleft()
        traffic_size = sum(size for _, size in self._traffic)
        if (
            encoded_size > MAX_MINISECTOR_EVENT_BYTES
            or traffic_size + encoded_size > MAX_MINISECTOR_TRAFFIC_BYTES
        ):
            bounded = self._event_base(
                "unavailable",
                str(event.get("generation", self._generation or "0")),
                int(event.get("sequence", self._sequence)),
            )
            bounded.update({"reason": "bounds_exceeded", "retryable": True})
            bounded_size = len(
                json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode()
            )
            if (
                bounded_size <= MAX_MINISECTOR_EVENT_BYTES
                and traffic_size + bounded_size <= MAX_MINISECTOR_TRAFFIC_BYTES
            ):
                self._connection.send_event(self._msg_id, bounded)
                self._traffic.append((now, bounded_size))
            self._traffic_blocked_until = now + MINISECTOR_TRAFFIC_WINDOW_SECONDS
            return False
        self._connection.send_event(self._msg_id, event)
        self._traffic.append((now, encoded_size))
        return True

    @callback
    def unsubscribe(self) -> None:
        """Release this consumer without affecting replay or other cards."""
        if self._closed:
            return
        self._closed = True
        self._unsub_hub()
        self._traffic.clear()

    @callback
    def terminate(self, reason: str) -> None:
        """Send one terminal availability event and remove the binding."""
        if self._closed:
            return
        event = self._event_base(
            "unavailable",
            self._generation or "0",
            self._sequence + 1,
        )
        event.update({"reason": reason, "retryable": True})
        with suppress(Exception):
            self._connection.send_event(self._msg_id, event)
        self.unsubscribe()
        if self._connection.subscriptions.get(self._msg_id) == self.unsubscribe:
            self._connection.subscriptions.pop(self._msg_id, None)


def _transport_drivers(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for driver, driver_state in value.items():
        if not isinstance(driver_state, Mapping):
            continue
        sectors_value = driver_state.get("sectors")
        sectors: dict[str, Any] = {}
        if isinstance(sectors_value, Mapping):
            for sector, sector_state in sectors_value.items():
                if not isinstance(sector_state, Mapping):
                    continue
                segments_value = sector_state.get("segments")
                segments: dict[str, Any] = {}
                if isinstance(segments_value, Mapping):
                    for segment, segment_state in segments_value.items():
                        if (
                            isinstance(segment_state, Mapping)
                            and "raw_status" in segment_state
                        ):
                            segments[str(segment)] = segment_state["raw_status"]
                if segments:
                    sectors[str(sector)] = {"segments": segments}
        result[str(driver)] = {
            "sectors": sectors,
        }
    return result


def _driver_changes(
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    changed: dict[str, Any] = {}
    removed = sorted(set(previous) - set(current), key=_numeric_sort_key)
    for driver, current_driver in current.items():
        previous_driver = previous.get(driver)
        if not isinstance(previous_driver, Mapping):
            changed[driver] = current_driver
            continue
        driver_delta: dict[str, Any] = {}
        previous_sectors = previous_driver.get("sectors", {})
        current_sectors = current_driver.get("sectors", {})
        sector_delta: dict[str, Any] = {}
        for sector, current_sector in current_sectors.items():
            old_segments = previous_sectors.get(sector, {}).get("segments", {})
            new_segments = current_sector.get("segments", {})
            segment_delta = {
                segment: status
                for segment, status in new_segments.items()
                if old_segments.get(segment) != status
            }
            if segment_delta:
                sector_delta[sector] = {"segments": segment_delta}
        if sector_delta:
            driver_delta["sectors"] = sector_delta
        if driver_delta:
            changed[driver] = driver_delta
        if _has_removed_segments(previous_driver, current_driver):
            removed.append(driver)
    return changed, sorted(set(removed), key=_numeric_sort_key)


def _has_removed_segments(
    previous_driver: Mapping[str, Any], current_driver: Mapping[str, Any]
) -> bool:
    previous_sectors = previous_driver.get("sectors", {})
    current_sectors = current_driver.get("sectors", {})
    for sector, previous_sector in previous_sectors.items():
        old_segments = previous_sector.get("segments", {})
        new_segments = current_sectors.get(sector, {}).get("segments", {})
        if set(old_segments) - set(new_segments):
            return True
    return False


def _protocol_reset_reason(value: object) -> str:
    return {
        "new_lap": "new_lap",
        "session_part": "session_part",
        "session_change": "session_change",
        "replay_seek": "seek",
        "source_change": "source_restart",
        "replay_reset": "source_restart",
        "live_delay_change": "source_restart",
        "source_unavailable": "source_restart",
    }.get(str(value), "unknown")


def _numeric_sort_key(value: str) -> tuple[int, str]:
    return (int(value), value) if value.isdecimal() else (10**9, value)
