"""Typed runtime ownership for the F1 Sensor config entry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .track_map import TrackMapRuntimeData


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
class F1RuntimeData:
    """Single typed owner for all config-entry runtime state.

    ``legacy`` remains during the staged platform migration so existing platform
    modules can keep their stable behavior while moving to typed fields one slice
    at a time.
    """

    static: StaticRuntime
    live: LiveRuntime
    replay: ReplayRuntime
    track_map: TrackMapRuntimeData
    cache: CacheRuntime
    capabilities: CapabilityState
    legacy: dict[str, Any]

    @property
    def track_map_store(self) -> Any:
        """Expose the existing track-map runtime contract during migration."""
        return self.track_map.track_map_store


type F1ConfigEntry = ConfigEntry[F1RuntimeData]
