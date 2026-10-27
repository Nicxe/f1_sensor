"""Typed runtime ownership for the F1 Sensor config entry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later

from .const import (
    CONF_INSTALL_DASHBOARD_CARDS,
    CONF_INSTALL_LEGACY_CARDS,
    CONF_LIVE_DELAY_REFERENCE,
    CONF_OPERATION_MODE,
    CONF_RACE_WEEK_START_DAY,
    CONF_REPLAY_FILE,
    CONF_REPLAY_START_REFERENCE,
    SUPPORTED_SENSOR_KEYS,
)
from .providers import ProviderRegistry
from .track_map import TrackMapRuntimeData

OPTION_KEYS = frozenset(
    {
        "disabled_sensors",
        "card_data_features",
        "exposed_sensor_keys",
        "enable_race_control",
        CONF_INSTALL_DASHBOARD_CARDS,
        CONF_INSTALL_LEGACY_CARDS,
        "live_delay_seconds",
        CONF_LIVE_DELAY_REFERENCE,
        CONF_OPERATION_MODE,
        CONF_RACE_WEEK_START_DAY,
        CONF_REPLAY_FILE,
        CONF_REPLAY_START_REFERENCE,
    }
)


@dataclass(slots=True)
class StaticRuntime:
    """Runtime objects for schedule, standings, results, and FIA data."""

    coordinators: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LiveRuntime:
    """Runtime objects for live timing and its derived coordinators."""

    bus: Any
    availability: Any
    supervisor: Any | None = None
    coordinators: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReplayRuntime:
    """Runtime objects for replay selection, playback, and track-map replay."""

    controller: Any
    track_map_adapter: Any


@dataclass(slots=True)
class CacheRuntime:
    """Entry-owned HTTP cache state."""

    persistent: Any
    memory: dict[str, Any]
    inflight: dict[str, Any]
    persisted: dict[str, Any]


@dataclass(slots=True)
class CapabilityState:
    """Requested and active provider capabilities for diagnostics and planning."""

    requested_features: frozenset[str]
    requested_streams: frozenset[str]
    active_streams: frozenset[str]
    stream_reasons: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderRuntime:
    """Provider registry and most recent normalized records."""

    registry: ProviderRegistry


@dataclass(slots=True)
class HistoryRuntime:
    """On-demand historical archive and optional live/replay lap analytics."""

    service: Any
    lap_analysis: Any | None = None


@dataclass(slots=True)
class AnalysisRuntime:
    """Phase 4 timeline, strategy, battles, and selected replay telemetry."""

    store: Any
    telemetry: Any


@dataclass(slots=True)
class F1RuntimeData:
    """Single typed owner for all config-entry runtime state.

    ``legacy`` remains during the staged platform migration so existing platform
    modules can keep their stable behavior while moving to typed fields one slice
    at a time.
    """

    static: StaticRuntime
    live: LiveRuntime | None
    replay: ReplayRuntime | None
    track_map: TrackMapRuntimeData
    cache: CacheRuntime
    providers: ProviderRuntime
    history: HistoryRuntime
    capabilities: CapabilityState
    legacy: dict[str, Any]
    analysis: AnalysisRuntime | None = None
    card_data: Any | None = None

    @property
    def track_map_store(self) -> Any:
        """Expose the existing track-map runtime contract during migration."""
        return self.track_map.track_map_store

    def get(self, key: str, default: Any = None) -> Any:
        """Read one compatibility value while platforms migrate by slice."""
        return self.legacy.get(key, default)


def entry_value(entry: ConfigEntry, key: str, default: Any = None) -> Any:
    """Return an option value with a backward-compatible data fallback."""
    if key == "disabled_sensors":
        selected = entry.options.get("exposed_sensor_keys")
        if isinstance(selected, (list, tuple)):
            return sorted(SUPPORTED_SENSOR_KEYS - set(selected))
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


def effective_entry_settings(entry: ConfigEntry) -> dict[str, Any]:
    """Return immutable config data overlaid with user-editable options."""
    settings = dict(entry.data)
    settings.update(entry.options)
    if isinstance(settings.get("exposed_sensor_keys"), (list, tuple)):
        settings["disabled_sensors"] = sorted(
            SUPPORTED_SENSOR_KEYS - set(settings["exposed_sensor_keys"])
        )
    return settings


def runtime_from_hass(
    hass: HomeAssistant,
    entry_id: str,
) -> F1RuntimeData | None:
    """Resolve typed runtime data without reading an untyped domain mapping."""
    entry = hass.config_entries.async_get_entry(entry_id)
    runtime = getattr(entry, "runtime_data", None) if entry is not None else None
    return runtime if isinstance(runtime, F1RuntimeData) else None


type F1ConfigEntry = ConfigEntry[F1RuntimeData]


def active_sensor_demand(
    hass: HomeAssistant, entry: ConfigEntry, selected: set[str]
) -> set[str]:
    """Registered disabled entities alone do not request expensive collection."""
    grouped: dict[str, list] = {}
    for entity in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        suffix = entity.unique_id.removeprefix(f"{entry.entry_id}_")
        key = (
            "top_three"
            if suffix.startswith("top_three_p")
            else "championship_prediction"
            if suffix.startswith("championship_prediction_")
            else suffix
        )
        if key in selected:
            grouped.setdefault(key, []).append(entity)
    return {
        key
        for key in selected
        if key not in grouped
        or any(entity.disabled_by is None for entity in grouped[key])
    }


def track_sensor_demand(hass: HomeAssistant, entry: ConfigEntry):
    """Replan once when HA entity disabling changes collection demand."""
    cancel = None

    @callback
    def reload_entry(_now):
        nonlocal cancel
        cancel = None
        hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))

    @callback
    def changed(event):
        nonlocal cancel
        if "disabled_by" not in event.data.get("changes", {}):
            return
        entity = er.async_get(hass).async_get(event.data.get("entity_id"))
        if entity is None or entity.config_entry_id != entry.entry_id:
            return
        if cancel is not None:
            cancel()
        cancel = async_call_later(hass, 1, reload_entry)

    unsubscribe = hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, changed)

    @callback
    def close():
        unsubscribe()
        if cancel is not None:
            cancel()

    return close
