"""Typed runtime ownership for the F1 Sensor config entry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_LIVE_DELAY_REFERENCE,
    CONF_OPERATION_MODE,
    CONF_RACE_WEEK_START_DAY,
    CONF_REPLAY_FILE,
    CONF_REPLAY_START_REFERENCE,
)
from .providers import ProviderRegistry
from .track_map import TrackMapRuntimeData

OPTION_KEYS = frozenset(
    {
        "disabled_sensors",
        "enable_race_control",
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

    @property
    def track_map_store(self) -> Any:
        """Expose the existing track-map runtime contract during migration."""
        return self.track_map.track_map_store

    def get(self, key: str, default: Any = None) -> Any:
        """Read one compatibility value while platforms migrate by slice."""
        return self.legacy.get(key, default)


def entry_value(entry: ConfigEntry, key: str, default: Any = None) -> Any:
    """Return an option value with a backward-compatible data fallback."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


def effective_entry_settings(entry: ConfigEntry) -> dict[str, Any]:
    """Return immutable config data overlaid with user-editable options."""
    settings = dict(entry.data)
    settings.update(entry.options)
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
