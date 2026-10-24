"""Entry-owned data products shared by dashboard subscriptions."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from copy import deepcopy
from time import monotonic
from typing import Any
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .context_data import ReplayStatusProjection
from .data_catalog import (
    CARD_FEATURE_KEYS,
    DATA_DEPENDENCIES,
    DATA_PRODUCTS,
    HISTORY_PRODUCTS,
    LIVE_PRODUCTS,
    NON_SPOILER_PRODUCTS,
)
from .data_helpers import _session_status_mapping_context
from .static_data_models import (
    ProjectionModel,
)

CONF_CARD_DATA_FEATURES = "card_data_features"
CONF_EXPOSED_SENSOR_KEYS = "exposed_sensor_keys"
DATA_PROTOCOL_VERSION = 1


def available_card_features(entry: ConfigEntry) -> frozenset[str]:
    """Offer supported card products automatically, independently of exposure.

    Live/authentication and privacy remain enforced by their existing sources.
    Obsolete card_data_features settings do not restrict card modules.
    """
    return CARD_FEATURE_KEYS


class CardDataStore:
    """Own coordinator listeners independently of optional HA entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, data: dict) -> None:
        self.hass = hass
        self.entry = entry
        self.data = data
        self.allowed = available_card_features(entry) & DATA_PRODUCTS.keys()
        self.generation = uuid4().hex
        self.closed = False
        self._listeners: dict[str, set[Callable]] = {}
        self._unsubs: dict[str, Callable] = {}
        self._snapshots: dict[str, dict] = {}
        self._models: dict[str, ProjectionModel] = {}
        self._spoiler_unsub: Callable | None = None
        self._started = False
        self._stop_unsub = None
        self._lifecycle_unsubs = []
        self._timer = None
        self._delayed = {}
        self._last_sent = {}
        self._replay_snapshot = {}
        self._context_token = None
        self._persisted = {}
        self._restored = set()
        self._published = {}
        self._waiting_for_source = set()
        self._storage = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}_card_data_v1")

    async def async_start(self):
        """Own selected incremental history even without an open dashboard."""
        if self._started or self.closed:
            return
        self._started = True
        self._stop_unsub = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self._async_stopping
        )
        saved = await self._storage.async_load()
        if isinstance(saved, dict):
            self._persisted = saved.get("products", {})
        controller = self.data.get("replay_controller")
        if controller is not None:
            self._lifecycle_unsubs.append(
                controller.session_manager.add_listener(self._replay_changed)
            )
        delay = self.data.get("live_delay_controller")
        if delay is not None:
            self._lifecycle_unsubs.append(
                delay.add_listener(
                    lambda _seconds: self._availability_changed(False, None)
                )
            )
        availability = self.data.get("live_state")
        if availability is not None:
            self._lifecycle_unsubs.append(
                availability.add_listener(self._availability_changed)
            )
        self._reconcile_listeners()
        for key in self._wanted():
            self.snapshot(key)
        self._ensure_clock()

    def _context(self):
        info = getattr(self.data.get("session_info_coordinator"), "data", None)
        info = info if isinstance(info, dict) else {}
        replay = (
            self._replay_snapshot.get("state", "idle") not in {"idle", "selected"}
            or self.data.get("operation_mode") == "development"
        )
        session = (
            self._replay_snapshot.get("selected_session_id")
            if replay
            else info.get("Key") or info.get("SessionKey") or info.get("Path")
        )
        tracker = self.data.get("live_state")
        delay = self.data.get("live_delay_controller")
        return (
            "replay" if replay else "live",
            str(session) if session is not None else None,
            getattr(tracker, "replay_generation", 0),
            getattr(delay, "current", 0),
        )

    def _check_context(self):
        token = self._context()
        if self._context_token is not None and token != self._context_token:
            previous = self._context_token
            saved = self._persisted
            self.reset_for_replay()
            if (
                previous[1] is None
                and previous[0] == token[0]
                and previous[2:] == token[2:]
            ):
                self._waiting_for_source.clear()
            # SessionInfo often arrives after startup. Preserve only accumulators
            # already bound to this exact source/session/delay, never another one.
            self._persisted.update(
                {
                    key: value
                    for key, value in saved.items()
                    if key in LIVE_PRODUCTS
                    and isinstance(value, dict)
                    and value.get("context") == list(token)
                }
            )
        self._context_token = token
        return token

    @callback
    def reset_for_replay(self):
        """Retire model state before a session/source change or replay rebuild."""
        self.generation = uuid4().hex
        self._models.clear()
        self._waiting_for_source = set(LIVE_PRODUCTS)
        self._restored.clear()
        self._persisted = {
            key: value
            for key, value in self._persisted.items()
            if key not in LIVE_PRODUCTS
        }
        self._context_token = None
        for cancel in self._delayed.values():
            cancel()
        self._delayed.clear()
        self._last_sent.clear()

    def _hydrate(self, key, model):
        if key in self._restored:
            return
        saved = self._persisted.get(key)
        if not isinstance(saved, dict):
            return
        if key in LIVE_PRODUCTS and (
            self._context()[1] is None or saved.get("context") != list(self._context())
        ):
            return
        payload = saved.get("payload")
        if not isinstance(payload, dict):
            return
        model._attr_native_value = payload.get("state")
        model._attr_extra_state_attributes = deepcopy(payload.get("attributes") or {})
        if normalize := getattr(model, "_normalize_restored_attributes", None):
            model._attr_extra_state_attributes = normalize(
                model._attr_extra_state_attributes
            )
        if restore_state := getattr(model, "restore_state", None):
            restore_state(saved.get("model_state", {}))
        self._restored.add(key)

    def _wanted(self):
        return set(self._listeners) | (
            {
                key
                for key in self.allowed & HISTORY_PRODUCTS
                if self.data.get(DATA_PRODUCTS[key][0]) is not None
            }
            if self._started
            else set()
        )

    @callback
    def _replay_changed(self, snapshot):
        self._replay_snapshot = deepcopy(snapshot)
        self._check_context()
        for key in tuple(self._listeners):
            self._publish(key)

    @callback
    def _availability_changed(self, _live, _reason):
        self._ensure_clock()
        for key in self._wanted():
            if key in self.allowed:
                self._publish(key)

    @callback
    def _ensure_clock(self):
        timed = self._wanted() & {
            "driver_positions",
            "investigations",
            "race_lap_count",
            "replay_status",
            "track_time",
        }
        tracker = self.data.get("live_state")
        if tracker is None or not tracker.is_live:
            timed -= LIVE_PRODUCTS.keys()
        needed = not self.closed and bool(timed)
        if not needed and self._timer is not None:
            self._timer()
            self._timer = None
        if needed and self._timer is None:
            interval = 60 if timed == {"track_time"} else 1
            self._timer = async_call_later(self.hass, interval, self._tick)

    @callback
    def _tick(self, _now):
        self._timer = None
        if self.closed:
            return
        for key in self._wanted() & {
            "driver_positions",
            "investigations",
            "race_lap_count",
            "replay_status",
            "track_time",
        }:
            self._schedule_publish(key)
        self._ensure_clock()

    @callback
    def _schedule_publish(self, key):
        if self.closed:
            return
        elapsed = monotonic() - self._last_sent.get(key, 0)
        if (
            key not in LIVE_PRODUCTS
            or key in {"current_session", "session_status"}
            or elapsed >= 1
        ):
            self._publish(key)
        elif key not in self._delayed:

            @callback
            def publish_later(_now):
                """Keep snapshots, storage and subscribers on the HA event loop."""
                self._publish(key)

            self._delayed[key] = async_call_later(self.hass, 1 - elapsed, publish_later)

    def snapshot(self, key: str) -> dict[str, Any]:
        """Read a protected projection without acquiring any background demand."""
        context_token = self._check_context()
        manager = self.hass.data.get(DOMAIN, {}).get("no_spoiler_manager")
        is_qualifying, qualifying_part = _session_status_mapping_context(
            self.data.get("session_status_coordinator")
        )
        if not is_qualifying or manager is None or manager.is_active:
            qualifying_part = None
        status, reason, payload = "ready", None, None
        if self.closed:
            status, reason = "closed", "entry_unloaded"
        elif key not in DATA_PRODUCTS:
            status, reason = "unsupported", "unsupported_dataset"
        elif key not in NON_SPOILER_PRODUCTS and (manager is None or manager.is_active):
            status, reason = "blocked", "no_spoiler"
        elif key in self._waiting_for_source:
            status, reason = "loading", "waiting_for_current_context"
        elif key == "session_context":
            payload = {
                "state": context_token[0],
                "attributes": {
                    "no_spoiler": bool(manager.is_active)
                    if manager is not None
                    else None,
                    "live_delay_seconds": context_token[3],
                    "qualifying_part": qualifying_part,
                    "replay_state": self._replay_snapshot.get("state", "idle"),
                },
            }
        elif key == "replay_status":
            projection = ReplayStatusProjection(
                self.data.get("replay_controller")
            ).snapshot(self._replay_snapshot)
            payload = {"state": projection.value, "attributes": projection.attributes}
        else:
            coordinator_key, projector = DATA_PRODUCTS[key]
            coordinator = self.data.get(coordinator_key)
            if coordinator is None:
                status, reason = "unavailable", "source_not_loaded"
            elif coordinator.data is None:
                status, reason = "loading", "waiting_for_data"
            else:
                if isinstance(projector, type) and issubclass(
                    projector, ProjectionModel
                ):
                    model = self._models.get(key)
                    if model is None:
                        model = projector(coordinator, None, self.entry.entry_id, None)
                        model.hass = self.hass
                        self._models[key] = model
                    self._hydrate(key, model)
                    projection = model.snapshot()
                else:
                    projection = projector(coordinator.data)
                payload = {
                    "state": projection.value,
                    "attributes": projection.attributes,
                }
                if key in LIVE_PRODUCTS and not model.available:
                    status, reason, payload = "unavailable", "source_inactive", None
                elif not getattr(coordinator, "last_update_success", True):
                    status, reason = "stale", "source_update_failed"
        attributes = payload["attributes"] if payload else {}
        live = key in LIVE_PRODUCTS or key in {"session_context", "replay_status"}
        context = (
            {
                "session_id": context_token[1],
                "replay_generation": context_token[2],
                "delay_seconds": context_token[3],
                "qualifying_part": qualifying_part,
            }
            if live
            else {name: attributes.get(name) for name in ("season", "round")}
        )
        candidate = {
            "protocol_version": DATA_PROTOCOL_VERSION,
            "entry_id": self.entry.entry_id,
            "dataset": key,
            "generation": self.generation,
            "source": context_token[0] if live else "static",
            "context": context,
            "status": status,
            "reason": reason,
            "payload": payload,
        }
        previous = self._snapshots.get(key)
        comparable = (
            {
                name: value
                for name, value in previous.items()
                if name not in {"revision", "timestamps"}
            }
            if previous
            else None
        )
        if candidate != comparable:
            candidate["revision"] = previous["revision"] + 1 if previous else 1
            candidate["timestamps"] = {
                "observed_at": None,
                "received_at": dt_util.utcnow().isoformat(),
            }
            self._snapshots[key] = candidate
            if payload is not None and not self.closed:
                self._persisted[key] = {
                    "context": list(context_token),
                    "payload": deepcopy(payload),
                    "model_state": (
                        self._models[key].export_state()
                        if key in self._models
                        and hasattr(self._models[key], "export_state")
                        else {}
                    ),
                }
                if self._started:
                    self._storage.async_delay_save(
                        lambda: {"products": self._persisted}, 30
                    )
        return deepcopy(self._snapshots[key])

    @callback
    def subscribe(self, keys: Iterable[str], listener: Callable) -> Callable:
        """Acquire each coordinator once, subscribe first, then send snapshots."""
        if self.closed:
            raise RuntimeError("Card data store is closed")
        keys = frozenset(keys)
        for key in keys:
            self._listeners.setdefault(key, set()).add(listener)
        self._reconcile_listeners()
        if self._spoiler_unsub is None:
            manager = self.hass.data.get(DOMAIN, {}).get("no_spoiler_manager")
            if manager is not None:
                self._spoiler_unsub = manager.add_listener(self._spoiler_changed)
        for key in sorted(keys):
            initial = self.snapshot(key)
            listener(initial)
            self._published.setdefault(
                key, (initial["generation"], initial["revision"])
            )
        self._ensure_clock()
        active = True

        @callback
        def unsubscribe() -> None:
            nonlocal active
            if not active:
                return
            active = False
            for key in keys:
                callbacks = self._listeners.get(key)
                if callbacks is None:
                    continue
                callbacks.discard(listener)
                if not callbacks:
                    self._listeners.pop(key, None)
            self._reconcile_listeners()
            if not self._listeners and self._spoiler_unsub is not None:
                self._spoiler_unsub()
                self._spoiler_unsub = None
            self._ensure_clock()

        return unsubscribe

    def _dependencies(self, key: str) -> tuple[str, ...]:
        return DATA_DEPENDENCIES.get(key, (DATA_PRODUCTS[key][0],))

    @callback
    def _reconcile_listeners(self) -> None:
        required = {
            name
            for key in self._wanted()
            if key in self.allowed
            for name in self._dependencies(key)
        }
        for name in self._unsubs.keys() - required:
            self._unsubs.pop(name)()
        for name in required - self._unsubs.keys():
            coordinator = self.data.get(name)
            if coordinator is not None:
                self._unsubs[name] = coordinator.async_add_listener(
                    lambda name=name: self._coordinator_changed(name)
                )
        if sources := self.data.get("card_data_sources"):
            sources.reconcile(required)

    @callback
    def _coordinator_changed(self, name: str) -> None:
        if sources := self.data.get("card_data_sources"):
            sources.mark_updated(name)
        previous = self.generation
        self._check_context()
        self._waiting_for_source.difference_update(
            key for key, (source, _model) in LIVE_PRODUCTS.items() if source == name
        )
        for key in self._wanted():
            if key in self.allowed and (
                previous != self.generation or name in self._dependencies(key)
            ):
                if previous != self.generation:
                    self._publish(key)
                else:
                    self._schedule_publish(key)

    @callback
    def _publish(self, key: str) -> None:
        if cancel := self._delayed.pop(key, None):
            cancel()
        self._last_sent[key] = monotonic()
        message = self.snapshot(key)
        identity = (message["generation"], message["revision"])
        if self._published.get(key) == identity:
            return
        self._published[key] = identity
        for listener in tuple(self._listeners.get(key, ())):
            listener(deepcopy(message))

    @callback
    def _spoiler_changed(self, _active: bool) -> None:
        for key in tuple(self._listeners):
            self._publish(key)

    async def _async_stopping(self, _event) -> None:
        self._stop_unsub = None
        if sources := self.data.get("card_data_sources"):
            await sources.async_close()
        await self.async_close()

    async def async_close(self) -> None:
        """Retire this generation and release all coordinator ownership."""
        if self.closed:
            return
        self.closed = True
        if self._stop_unsub is not None:
            self._stop_unsub()
            self._stop_unsub = None
        for key in tuple(self._listeners):
            self._publish(key)
        for remove in self._unsubs.values():
            remove()
        self._unsubs.clear()
        if sources := self.data.get("card_data_sources"):
            sources.reconcile(set())
        self._listeners.clear()
        for cancel in self._delayed.values():
            cancel()
        self._delayed.clear()
        for remove in self._lifecycle_unsubs:
            remove()
        self._lifecycle_unsubs.clear()
        if self._timer is not None:
            self._timer()
            self._timer = None
        if self._spoiler_unsub is not None:
            self._spoiler_unsub()
            self._spoiler_unsub = None
        if self._started and self.allowed:
            await self._storage.async_save({"products": self._persisted})
