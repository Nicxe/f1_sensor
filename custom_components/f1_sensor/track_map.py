"""Track map decoding helpers for F1 Live Timing position data."""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import logging
import re
from statistics import median
import time
from typing import Any
import zlib

from .track_map_static_geometry import (
    STATIC_TRACK_GEOMETRIES,
    STATIC_TRACK_GEOMETRY_ALIAS_TO_KEY,
    get_static_track_geometry_provenance,
)

_LOGGER = logging.getLogger(__name__)
_FRACTIONAL_SECONDS_RE = re.compile(r"(\.\d{6})\d+")
_POSITION_STATUS_UNKNOWN = "Unknown"
DEFAULT_TRACK_MAP_STALE_AFTER = timedelta(seconds=10)
TRACK_MAP_STATUS_ACTIVE = "active"
TRACK_MAP_STATUS_CLOSED = "closed"
TRACK_MAP_STATUS_NO_POSITION_DATA = "no_position_data"
TRACK_MAP_STATUS_NO_SESSION = "no_session"
TRACK_MAP_STATUS_STALE = "stale"
TRACK_MAP_POSITION_STREAM = "Position.z"
TRACK_MAP_REPLAY_GEOMETRY_SOURCE = "replay_position_z"
TRACK_MAP_STATIC_GEOMETRY_SOURCE = "static_circuit_geometry"
TRACK_MAP_REPLAY_POSITIONS_KEY = "positions"
TRACK_MAP_FALLBACK_STATE_CUSTOM_GEOMETRY = "custom_geometry"
TRACK_MAP_FALLBACK_STATE_NO_SESSION = "no_session"
TRACK_MAP_FALLBACK_STATE_REPLAY_V2 = "replay_v2"
TRACK_MAP_FALLBACK_STATE_STATIC_CATALOG = "static_catalog"
TRACK_MAP_FALLBACK_STATE_WAITING_FOR_REPLAY_POSITION_Z = "waiting_for_replay_position_z"
DEFAULT_TRACK_MAP_GEOMETRY_SAMPLE_LIMIT = 50_000
DEFAULT_TRACK_MAP_GEOMETRY_REBUILD_FRAMES = 25
DEFAULT_TRACK_MAP_GEOMETRY_MIN_DRIVER_POINTS = 4
DEFAULT_TRACK_MAP_REPLAY_INTERPOLATION_TICK_SECONDS = 0.1
DEFAULT_TRACK_MAP_REPLAY_INTERPOLATION_MIN_SECONDS = 0.45
DEFAULT_TRACK_MAP_REPLAY_INTERPOLATION_MAX_SECONDS = 2.0
DEFAULT_TRACK_MAP_REPLAY_INTERPOLATION_FACTOR = 2.2
MAX_TRACK_MAP_RACING_NUMBER = 99
TRACK_MAP_SOURCE_REPLAY = "replay"


@dataclass(frozen=True, slots=True)
class TrackMapPosition:
    """Normalized position for one driver from Position.z."""

    racing_number: str
    timestamp: datetime
    x: int
    y: int
    z: int | None
    status: str


@dataclass(frozen=True, slots=True)
class TrackMapBounds:
    """Coordinate bounds for decoded position or geometry data."""

    min_x: int
    max_x: int
    min_y: int
    max_y: int
    min_z: int | None = None
    max_z: int | None = None


@dataclass(frozen=True, slots=True)
class TrackMapDataMetrics:
    """Small summary of decoded Position.z data."""

    frame_count: int
    sample_count: int
    decoded_positions: int
    driver_count: int
    average_drivers_per_sample: float
    on_track_count: int
    off_track_count: int
    zero_zero_count: int
    invalid_line_count: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    bounds: TrackMapBounds | None


@dataclass(frozen=True, slots=True)
class TrackGeometry:
    """Derived track geometry for the first track map prototype."""

    points: tuple[tuple[int, int], ...]
    bounds: TrackMapBounds
    source: str
    circuit_key: str | None = None
    rotation: float = 0.0


@dataclass(frozen=True, slots=True)
class TrackMapDriverMetadata:
    """Display metadata for one racing number."""

    racing_number: str
    tla: str | None = None
    full_name: str | None = None
    broadcast_name: str | None = None
    team_name: str | None = None
    team_color: str | None = None


@dataclass(frozen=True, slots=True)
class TrackMapSessionMetadata:
    """Small normalized subset of SessionInfo for track map snapshots."""

    session_key: str | None = None
    path: str | None = None
    meeting_key: str | None = None
    meeting_name: str | None = None
    session_name: str | None = None
    session_type: str | None = None
    circuit_key: str | None = None
    circuit_short_name: str | None = None


@dataclass(frozen=True, slots=True)
class TrackMapLocationContext:
    """Current location context for one driver."""

    racing_number: str
    timestamp: datetime
    x: int
    y: int
    z: int | None
    status: str
    stale: bool
    source: str
    session_key: str | None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable context payload."""
        return {
            "racing_number": self.racing_number,
            "timestamp": _format_utc(self.timestamp),
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "status": self.status,
            "stale": self.stale,
            "source": self.source,
            "session_key": self.session_key,
        }


@dataclass(slots=True)
class TrackMapRuntimeData:
    """Runtime-owned track map objects for one config entry."""

    track_map_store: TrackMapStore


@dataclass(frozen=True, slots=True)
class _ReplayInterpolationSegment:
    from_position: TrackMapPosition
    to_position: TrackMapPosition
    started_at: float
    duration: float


@dataclass(frozen=True, slots=True)
class _TrackGeometryCandidate:
    points: tuple[tuple[int, int], ...]
    bounds: TrackMapBounds
    path_length: float
    source_point_count: int
    closed_loop: bool
    closure_gap: float | None


@dataclass(frozen=True, slots=True)
class _ClosedGeometrySegment:
    positions: tuple[TrackMapPosition, ...]
    path_length: float
    closure_gap: float


class TrackMapReplayAdapter:
    """Feed TrackMapStore from replay/live-bus track map streams."""

    def __init__(
        self,
        store: TrackMapStore,
        bus: Any,
        *,
        hass: Any | None = None,
        replay_controller: Any | None = None,
        geometry_sample_limit: int = DEFAULT_TRACK_MAP_GEOMETRY_SAMPLE_LIMIT,
        geometry_rebuild_frames: int = DEFAULT_TRACK_MAP_GEOMETRY_REBUILD_FRAMES,
        geometry_min_driver_points: int = DEFAULT_TRACK_MAP_GEOMETRY_MIN_DRIVER_POINTS,
        interpolation_tick_seconds: float = DEFAULT_TRACK_MAP_REPLAY_INTERPOLATION_TICK_SECONDS,
    ) -> None:
        self._store = store
        self._bus = bus
        self._hass = hass
        self._replay_controller = replay_controller
        self._geometry_sample_limit = max(0, int(geometry_sample_limit))
        self._geometry_rebuild_frames = max(1, int(geometry_rebuild_frames))
        self._geometry_min_driver_points = max(1, int(geometry_min_driver_points))
        self._geometry_positions_by_driver: dict[str, list[TrackMapPosition]] = {}
        self._geometry_sample_count = 0
        self._geometry_preloaded = False
        self._position_frame_count = 0
        self._position_segments: dict[str, _ReplayInterpolationSegment] = {}
        self._last_driver_sample_at: dict[str, float] = {}
        self._driver_sample_interval_seconds = 0.0
        self._replay_state: str | None = None
        self._interpolation_tick_seconds = max(0.02, float(interpolation_tick_seconds))
        self._interpolation_handle: Any | None = None
        self._unsubs: list[Callable[[], None]] = []
        self._closed = False

    def start(self) -> None:
        """Subscribe to streams used by the track map store."""
        if self._closed or self._unsubs:
            return
        subscriptions = (
            ("SessionInfo", self._on_session_info),
            ("DriverList", self._on_driver_list),
            (TRACK_MAP_POSITION_STREAM, self._on_position_z),
        )
        for stream, callback in subscriptions:
            subscribe = getattr(self._bus, "subscribe", None)
            if not callable(subscribe):
                return
            try:
                self._unsubs.append(subscribe(stream, callback))
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Failed to subscribe track map stream %s", stream)
        replay_manager = getattr(self._replay_controller, "session_manager", None)
        add_replay_listener = getattr(replay_manager, "add_listener", None)
        if callable(add_replay_listener):
            try:
                self._unsubs.append(add_replay_listener(self._on_replay_state))
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Failed to subscribe track map replay state")

    async def async_close(self) -> None:
        """Unsubscribe from live bus callbacks."""
        self._closed = True
        for unsub in self._unsubs:
            with suppress(Exception):
                unsub()
        self._unsubs.clear()
        self._geometry_positions_by_driver.clear()
        self._geometry_sample_count = 0
        self._geometry_preloaded = False
        self._cancel_interpolation_timer()
        self._position_segments.clear()
        self._last_driver_sample_at.clear()

    def reset_for_replay(self) -> None:
        """Clear track map data before replay rebuild, rewind or stop."""
        self._geometry_positions_by_driver.clear()
        self._geometry_sample_count = 0
        self._geometry_preloaded = False
        self._position_frame_count = 0
        self._cancel_interpolation_timer()
        self._position_segments.clear()
        self._last_driver_sample_at.clear()
        self._driver_sample_interval_seconds = 0.0
        self._store.reset_for_replay()

    async def async_prepare_replay_index(self, replay_index: Any) -> None:
        """Preload replay track geometry from cached Position.z frames."""
        if self._closed:
            return
        add_executor_job = getattr(self._hass, "async_add_executor_job", None)
        if callable(add_executor_job):
            geometry = await add_executor_job(
                self._build_geometry_from_replay_index,
                replay_index,
            )
        else:
            geometry = self._build_geometry_from_replay_index(replay_index)
        if self._closed or geometry is None:
            return
        self._geometry_preloaded = True
        self._store.set_geometry(geometry)

    def _on_session_info(self, payload: Any) -> None:
        if self._closed or not isinstance(payload, Mapping):
            return
        self._store.update_session_info(payload)

    def _on_driver_list(self, payload: Any) -> None:
        if self._closed or not isinstance(payload, Mapping):
            return
        self._store.update_driver_list(payload)

    def _on_position_z(self, payload: Any) -> None:
        if self._closed:
            return
        positions = track_map_positions_from_payload(payload)
        if not positions:
            return
        self._position_frame_count += 1
        if self._replay_state == "playing":
            now = self._loop_time()
            self._set_interpolation_targets(positions, now)
            self._publish_interpolated_positions(now)
            self._schedule_interpolation_tick()
        else:
            self._cancel_interpolation_timer()
            self._position_segments.clear()
            self._store.update_positions(positions, source=TRACK_MAP_SOURCE_REPLAY)
        self._extend_geometry_positions(positions)
        self._maybe_rebuild_geometry()

    def _on_replay_state(self, snapshot: Mapping[str, Any]) -> None:
        if self._closed or not isinstance(snapshot, Mapping):
            return
        state = str(snapshot.get("state") or "").strip() or None
        self._replay_state = state
        self._store.update_replay_state(state)
        if state == "playing":
            self._schedule_interpolation_tick()
        else:
            self._cancel_interpolation_timer()
            self._position_segments.clear()

    def _extend_geometry_positions(
        self,
        positions: Iterable[TrackMapPosition],
    ) -> None:
        if self._geometry_sample_limit <= 0:
            return
        for position in positions:
            if self._geometry_sample_count >= self._geometry_sample_limit:
                return
            if position.status.strip().lower() != "ontrack":
                continue
            if position.x == 0 and position.y == 0:
                continue
            self._geometry_positions_by_driver.setdefault(
                position.racing_number,
                [],
            ).append(position)
            self._geometry_sample_count += 1

    def _maybe_rebuild_geometry(self) -> None:
        if self._geometry_preloaded:
            return
        if _is_static_track_geometry(self._store.geometry):
            return
        if (
            self._store.geometry is not None
            and self._position_frame_count % self._geometry_rebuild_frames != 0
        ):
            return
        session = self._store.session
        geometry = build_track_geometry_from_position_groups(
            self._geometry_positions_by_driver,
            circuit_key=session.circuit_key if session else None,
            source=TRACK_MAP_REPLAY_GEOMETRY_SOURCE,
            min_points=self._geometry_min_driver_points,
        )
        if geometry is not None:
            self._store.set_geometry(geometry)

    def _build_geometry_from_replay_index(
        self, replay_index: Any
    ) -> TrackGeometry | None:
        session = self._store.session
        static_geometry = get_static_track_geometry_for_session(session)
        if static_geometry is not None:
            return static_geometry

        frames_file = getattr(replay_index, "frames_file", None)
        if frames_file is None or self._geometry_sample_limit <= 0:
            return None

        positions_by_driver: dict[str, list[TrackMapPosition]] = {}
        sample_count = 0
        try:
            with open(frames_file, encoding="utf-8") as handle:
                for raw_line in handle:
                    if sample_count >= self._geometry_sample_limit:
                        break
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        frame = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if frame.get("s") != TRACK_MAP_POSITION_STREAM:
                        continue
                    for position in track_map_positions_from_payload(frame.get("p")):
                        if sample_count >= self._geometry_sample_limit:
                            break
                        if position.status.strip().lower() != "ontrack":
                            continue
                        if position.x == 0 and position.y == 0:
                            continue
                        positions_by_driver.setdefault(
                            position.racing_number,
                            [],
                        ).append(position)
                        sample_count += 1
        except OSError:
            return None

        return build_track_geometry_from_position_groups(
            positions_by_driver,
            circuit_key=session.circuit_key if session else None,
            source=TRACK_MAP_REPLAY_GEOMETRY_SOURCE,
            min_points=self._geometry_min_driver_points,
        )

    def _set_interpolation_targets(
        self,
        positions: Iterable[TrackMapPosition],
        now: float,
    ) -> None:
        for position in positions:
            current = self._current_interpolated_position(position.racing_number, now)
            last_sample_at = self._last_driver_sample_at.get(position.racing_number)
            if last_sample_at is not None:
                self._update_sample_interval(now - last_sample_at)
            self._last_driver_sample_at[position.racing_number] = now
            if current is None or _position_distance(current, position) > 2500:
                current = position
                duration = 0.0
            else:
                duration = self._interpolation_duration()
            self._position_segments[position.racing_number] = (
                _ReplayInterpolationSegment(
                    from_position=current,
                    to_position=position,
                    started_at=now,
                    duration=duration,
                )
            )

    def _publish_interpolated_positions(self, now: float) -> bool:
        if not self._position_segments:
            return False
        positions: list[TrackMapPosition] = []
        active = False
        for segment in self._position_segments.values():
            position = _interpolate_position_segment(segment, now)
            positions.append(position)
            if segment.duration > 0 and now < segment.started_at + segment.duration:
                active = True
        if positions:
            self._store.update_positions(positions, source=TRACK_MAP_SOURCE_REPLAY)
        return active

    def _current_interpolated_position(
        self,
        racing_number: str,
        now: float,
    ) -> TrackMapPosition | None:
        segment = self._position_segments.get(racing_number)
        if segment is None:
            return None
        return _interpolate_position_segment(segment, now)

    def _update_sample_interval(self, interval: float) -> None:
        if interval < 0.05 or interval > 5.0:
            return
        if self._driver_sample_interval_seconds <= 0:
            self._driver_sample_interval_seconds = interval
            return
        self._driver_sample_interval_seconds = (
            self._driver_sample_interval_seconds * 0.7
        ) + (interval * 0.3)

    def _interpolation_duration(self) -> float:
        if self._driver_sample_interval_seconds <= 0:
            return DEFAULT_TRACK_MAP_REPLAY_INTERPOLATION_MIN_SECONDS
        return max(
            DEFAULT_TRACK_MAP_REPLAY_INTERPOLATION_MIN_SECONDS,
            min(
                DEFAULT_TRACK_MAP_REPLAY_INTERPOLATION_MAX_SECONDS,
                self._driver_sample_interval_seconds
                * DEFAULT_TRACK_MAP_REPLAY_INTERPOLATION_FACTOR,
            ),
        )

    def _schedule_interpolation_tick(self) -> None:
        if self._closed or self._replay_state != "playing":
            return
        if self._interpolation_handle is not None:
            return
        loop = getattr(self._hass, "loop", None)
        call_later = getattr(loop, "call_later", None)
        if not callable(call_later):
            return
        self._interpolation_handle = call_later(
            self._interpolation_tick_seconds,
            self._run_interpolation_tick,
        )

    def _run_interpolation_tick(self) -> None:
        self._interpolation_handle = None
        if self._closed or self._replay_state != "playing":
            return
        active = self._publish_interpolated_positions(self._loop_time())
        if active:
            self._schedule_interpolation_tick()

    def _cancel_interpolation_timer(self) -> None:
        if self._interpolation_handle is None:
            return
        with suppress(Exception):
            self._interpolation_handle.cancel()
        self._interpolation_handle = None

    def _loop_time(self) -> float:
        loop = getattr(self._hass, "loop", None)
        loop_time = getattr(loop, "time", None)
        if callable(loop_time):
            return float(loop_time())
        return time.monotonic()


class TrackMapStore:
    """In-memory track map state for one config entry."""

    def __init__(
        self,
        entry_id: str,
        *,
        source: str = "runtime",
        stale_after: timedelta = DEFAULT_TRACK_MAP_STALE_AFTER,
    ) -> None:
        self.entry_id = entry_id
        self._source = source
        self._stale_after = stale_after
        self._session: TrackMapSessionMetadata | None = None
        self._driver_metadata: dict[str, TrackMapDriverMetadata] = {}
        self._latest_positions: dict[str, TrackMapPosition] = {}
        self._geometry: TrackGeometry | None = None
        self._stream_timestamp: datetime | None = None
        self._replay_state: str | None = None
        self._listeners: dict[int, Callable[[], None]] = {}
        self._next_listener_id = 0
        self._closed = False

    @property
    def source(self) -> str:
        """Return the latest ingestion source label."""
        return self._source

    @property
    def session(self) -> TrackMapSessionMetadata | None:
        """Return the current session metadata."""
        return self._session

    @property
    def geometry(self) -> TrackGeometry | None:
        """Return the current track geometry."""
        return self._geometry

    def update_session_info(self, payload: Mapping[str, Any] | None) -> None:
        """Update session metadata and clear session-bound data on switches."""
        if self._closed:
            return
        session = _session_metadata_from_payload(payload)
        if session is None:
            return
        old_key = self._session.session_key if self._session else None
        if old_key and session.session_key and old_key != session.session_key:
            self._reset_session_state()
        self._session = session
        static_geometry = get_static_track_geometry_for_session(session)
        if static_geometry is not None:
            self._geometry = static_geometry
        self._notify_listeners()

    def update_driver_list(self, payload: Mapping[Any, Any] | None) -> None:
        """Update driver metadata from DriverList payloads."""
        if self._closed or not isinstance(payload, Mapping):
            return
        driver_map = _extract_driver_list_payload(payload)
        changed = False
        for racing_number_raw, driver_payload in driver_map.items():
            if not isinstance(driver_payload, Mapping):
                continue
            racing_number = _normalize_racing_number(
                driver_payload.get("RacingNumber", racing_number_raw),
            )
            if racing_number is None:
                continue
            self._driver_metadata[racing_number] = _driver_metadata_from_payload(
                racing_number,
                driver_payload,
                self._driver_metadata.get(racing_number),
            )
            changed = True
        if changed:
            changed = self._prune_unknown_driver_positions() or changed
            self._notify_listeners()

    def update_positions(
        self,
        positions: Iterable[TrackMapPosition],
        *,
        source: str | None = None,
    ) -> None:
        """Store the latest known position for each driver."""
        if self._closed:
            return
        if source:
            self._source = source
        changed = False
        for position in positions:
            if (
                self._driver_metadata
                and position.racing_number not in self._driver_metadata
            ):
                continue
            self._latest_positions[position.racing_number] = position
            if (
                self._stream_timestamp is None
                or position.timestamp > self._stream_timestamp
            ):
                self._stream_timestamp = position.timestamp
            changed = True
        changed = self._prune_unknown_driver_positions() or changed
        if changed:
            self._notify_listeners()

    def set_geometry(self, geometry: TrackGeometry | None) -> None:
        """Set or clear the current track geometry."""
        if self._closed:
            return
        self._geometry = geometry
        self._notify_listeners()

    def update_replay_state(self, state: str | None) -> None:
        """Update replay playback state metadata for websocket consumers."""
        if self._closed:
            return
        state = state or None
        if state == self._replay_state:
            return
        self._replay_state = state
        self._notify_listeners()

    def reset_session(self) -> None:
        """Clear data that belongs to the current live timing session."""
        self._reset_session_state()
        self._notify_listeners()

    def _reset_session_state(self) -> None:
        self._session = None
        self._driver_metadata.clear()
        self._latest_positions.clear()
        self._geometry = None
        self._stream_timestamp = None
        self._replay_state = None

    def reset_for_replay(self) -> None:
        """Clear session-bound data before replay rebuild or rewind."""
        self.reset_session()

    def is_stale(self, now: datetime | None = None) -> bool:
        """Return whether the latest stream update is older than stale_after."""
        if self._source == TRACK_MAP_SOURCE_REPLAY:
            return False
        if self._stream_timestamp is None:
            return False
        now_utc = _snapshot_now(now)
        return now_utc - self._stream_timestamp > self._stale_after

    def location_context(
        self,
        racing_number: str | int,
        *,
        now: datetime | None = None,
    ) -> TrackMapLocationContext | None:
        """Return a compact current-position context for one driver."""
        normalized = _normalize_racing_number(racing_number)
        if normalized is None:
            return None
        position = self._latest_positions.get(normalized)
        if position is None:
            return None
        now_utc = _snapshot_now(now)
        return TrackMapLocationContext(
            racing_number=normalized,
            timestamp=position.timestamp,
            x=position.x,
            y=position.y,
            z=position.z,
            status=position.status,
            stale=self._position_is_stale(position, now_utc),
            source=self._source,
            session_key=self._session.session_key if self._session else None,
        )

    def snapshot(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of current track map state."""
        now_utc = _snapshot_now(now)
        return {
            "entry_id": self.entry_id,
            "source": self._source,
            "status": self._snapshot_status(now_utc),
            "generated_at": _format_utc(now_utc),
            "stream_timestamp": _format_utc(self._stream_timestamp),
            "replay_state": self._replay_state,
            "stale": self.is_stale(now_utc),
            "stale_after_seconds": self._stale_after.total_seconds(),
            "session": _session_payload(self._session),
            "track": _geometry_payload(self._geometry),
            "drivers": [
                self._driver_snapshot(position, now_utc)
                for position in sorted(
                    self._latest_positions.values(),
                    key=_racing_number_sort_key,
                )
            ],
        }

    def diagnostics(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Return a compact internal diagnostics summary."""
        now_utc = _snapshot_now(now)
        geometry = self._geometry
        session = self._session
        catalog_entry = _static_track_geometry_catalog_entry(session, geometry)
        provenance = (
            get_static_track_geometry_provenance(circuit_id=catalog_entry["circuit_id"])
            if catalog_entry is not None
            else None
        )
        circuit_key = (
            session.circuit_key
            if session is not None
            else geometry.circuit_key
            if geometry is not None
            else None
        )
        circuit_id = catalog_entry["circuit_id"] if catalog_entry is not None else None
        approval_status = (
            provenance.get("approval_status") if provenance is not None else None
        )
        return {
            "source": self._source,
            "status": self._snapshot_status(now_utc),
            "session_key": session.session_key if session else None,
            "replay_state": self._replay_state,
            "circuit_key": circuit_key,
            "circuit_short_name": session.circuit_short_name if session else None,
            "circuit_id": circuit_id,
            "geometry_source": geometry.source if geometry is not None else None,
            "point_count": len(geometry.points) if geometry is not None else 0,
            "rotation": geometry.rotation if geometry is not None else None,
            "approval_status": approval_status,
            "fallback_state": _track_map_fallback_state(
                session,
                geometry,
            ),
            "driver_count": len(self._latest_positions),
            "stale": self.is_stale(now_utc),
        }

    async def async_close(self) -> None:
        """Release runtime data owned by this store."""
        self._reset_session_state()
        self._closed = True
        self._notify_listeners()
        self._listeners.clear()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a state-change listener and return its unsubscribe callback."""
        if self._closed:
            return lambda: None

        listener_id = self._next_listener_id
        self._next_listener_id += 1
        self._listeners[listener_id] = listener

        def _unsubscribe() -> None:
            self._listeners.pop(listener_id, None)

        return _unsubscribe

    def _notify_listeners(self) -> None:
        for listener in tuple(self._listeners.values()):
            try:
                listener()
            except Exception:
                _LOGGER.debug("Track map listener failed", exc_info=True)

    def _prune_unknown_driver_positions(self) -> bool:
        if not self._driver_metadata or not self._latest_positions:
            return False
        known_racing_numbers = set(self._driver_metadata)
        stale_racing_numbers = [
            racing_number
            for racing_number in self._latest_positions
            if racing_number not in known_racing_numbers
        ]
        for racing_number in stale_racing_numbers:
            self._latest_positions.pop(racing_number, None)
        return bool(stale_racing_numbers)

    def _snapshot_status(self, now: datetime) -> str:
        if self._closed:
            return TRACK_MAP_STATUS_CLOSED
        if self._session is None:
            return TRACK_MAP_STATUS_NO_SESSION
        if not self._latest_positions:
            return TRACK_MAP_STATUS_NO_POSITION_DATA
        if self.is_stale(now):
            return TRACK_MAP_STATUS_STALE
        return TRACK_MAP_STATUS_ACTIVE

    def _driver_snapshot(
        self,
        position: TrackMapPosition,
        now: datetime,
    ) -> dict[str, Any]:
        metadata = self._driver_metadata.get(position.racing_number)
        return {
            "racing_number": position.racing_number,
            "tla": metadata.tla if metadata else None,
            "name": _driver_display_name(metadata),
            "full_name": metadata.full_name if metadata else None,
            "broadcast_name": metadata.broadcast_name if metadata else None,
            "team_name": metadata.team_name if metadata else None,
            "team_color": metadata.team_color if metadata else None,
            "timestamp": _format_utc(position.timestamp),
            "x": position.x,
            "y": position.y,
            "z": position.z,
            "status": position.status,
            "stale": self._position_is_stale(position, now),
        }

    def _position_is_stale(self, position: TrackMapPosition, now: datetime) -> bool:
        if self._source == TRACK_MAP_SOURCE_REPLAY:
            return False
        return now - position.timestamp > self._stale_after


def decode_position_z_payload(
    payload: Any,
    *,
    observed_at: datetime | str | None = None,
) -> list[TrackMapPosition]:
    """Decode raw or already-decoded Position.z payloads into positions."""
    default_timestamp = _parse_utc(observed_at)
    positions: list[TrackMapPosition] = []
    for sample in _extract_position_samples(payload):
        sample_timestamp = _parse_utc(
            sample.get("Timestamp"),
            default=default_timestamp,
        )
        if sample_timestamp is None:
            continue
        entries = sample.get("Entries")
        if not isinstance(entries, Mapping):
            continue
        positions.extend(_normalize_position_entries(entries, sample_timestamp))
    return positions


def parse_position_z_line(
    line: str,
    *,
    observed_at: datetime | str | None = None,
) -> list[TrackMapPosition]:
    """Decode one Position.z jsonStream line into normalized positions."""
    return decode_position_z_payload(line, observed_at=observed_at)


def parse_position_z_lines(
    lines: Iterable[str],
    *,
    observed_at: datetime | str | None = None,
) -> list[TrackMapPosition]:
    """Decode multiple Position.z jsonStream lines into normalized positions."""
    positions: list[TrackMapPosition] = []
    for line in lines:
        positions.extend(parse_position_z_line(line, observed_at=observed_at))
    return positions


def track_map_positions_to_payload(
    positions: Iterable[TrackMapPosition],
) -> dict[str, Any]:
    """Return a JSON-serializable replay payload for normalized positions."""
    return {
        TRACK_MAP_REPLAY_POSITIONS_KEY: [
            {
                "racing_number": position.racing_number,
                "timestamp": _format_utc(position.timestamp),
                "x": position.x,
                "y": position.y,
                "z": position.z,
                "status": position.status,
            }
            for position in positions
        ]
    }


def track_map_positions_from_payload(payload: Any) -> list[TrackMapPosition]:
    """Return normalized positions from replay or raw Position.z payloads."""
    if isinstance(payload, Mapping):
        replay_positions = payload.get(TRACK_MAP_REPLAY_POSITIONS_KEY)
        if isinstance(replay_positions, list):
            return _positions_from_replay_payload(replay_positions)
    return decode_position_z_payload(payload)


def _interpolate_position_segment(
    segment: _ReplayInterpolationSegment,
    now: float,
) -> TrackMapPosition:
    if segment.duration <= 0:
        return segment.to_position
    progress = max(0.0, min(1.0, (now - segment.started_at) / segment.duration))
    return _interpolate_positions(
        segment.from_position,
        segment.to_position,
        progress,
    )


def _interpolate_positions(
    start: TrackMapPosition,
    end: TrackMapPosition,
    progress: float,
) -> TrackMapPosition:
    progress = max(0.0, min(1.0, progress))
    timestamp_delta = end.timestamp - start.timestamp
    z: int | None
    if start.z is None or end.z is None:
        z = end.z
    else:
        z = round(start.z + ((end.z - start.z) * progress))
    return TrackMapPosition(
        racing_number=end.racing_number,
        timestamp=start.timestamp + (timestamp_delta * progress),
        x=round(start.x + ((end.x - start.x) * progress)),
        y=round(start.y + ((end.y - start.y) * progress)),
        z=z,
        status=end.status,
    )


def _position_distance(start: TrackMapPosition, end: TrackMapPosition) -> float:
    return ((end.x - start.x) ** 2 + (end.y - start.y) ** 2) ** 0.5


def analyze_position_z_lines(lines: Iterable[str]) -> TrackMapDataMetrics:
    """Return compact metrics for a Position.z jsonStream dump."""
    frame_count = 0
    sample_count = 0
    decoded_positions = 0
    driver_numbers: set[str] = set()
    total_entries = 0
    on_track_count = 0
    off_track_count = 0
    zero_zero_count = 0
    invalid_line_count = 0
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    bounds: TrackMapBounds | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("URL:"):
            continue
        decoded = _decode_position_z_line(line)
        if decoded is None:
            invalid_line_count += 1
            continue
        frame_count += 1
        for sample in _extract_position_samples(decoded):
            sample_count += 1
            timestamp = _parse_utc(sample.get("Timestamp"))
            if timestamp is not None:
                first_timestamp = first_timestamp or timestamp
                last_timestamp = timestamp
            entries = sample.get("Entries")
            if not isinstance(entries, Mapping):
                continue
            total_entries += len(entries)
            positions = _normalize_position_entries(
                entries,
                timestamp or datetime.min.replace(tzinfo=UTC),
            )
            decoded_positions += len(positions)
            for position in positions:
                driver_numbers.add(position.racing_number)
                bounds = _extend_bounds(bounds, position)
                if position.x == 0 and position.y == 0:
                    zero_zero_count += 1
                status = position.status.strip().lower()
                if status == "ontrack":
                    on_track_count += 1
                elif status == "offtrack":
                    off_track_count += 1

    average_drivers = total_entries / sample_count if sample_count else 0.0
    return TrackMapDataMetrics(
        frame_count=frame_count,
        sample_count=sample_count,
        decoded_positions=decoded_positions,
        driver_count=len(driver_numbers),
        average_drivers_per_sample=average_drivers,
        on_track_count=on_track_count,
        off_track_count=off_track_count,
        zero_zero_count=zero_zero_count,
        invalid_line_count=invalid_line_count,
        first_timestamp=first_timestamp,
        last_timestamp=last_timestamp,
        bounds=bounds,
    )


def build_track_geometry_from_positions(
    positions: Iterable[TrackMapPosition],
    *,
    circuit_key: str | None = None,
    source: str = "derived_position_z",
    max_points: int = 1000,
) -> TrackGeometry | None:
    """Build replay geometry from one ordered driver position sequence."""
    candidate = _build_track_geometry_candidate(
        positions,
        max_points=max_points,
        min_points=1,
    )
    if candidate is None:
        return None
    return TrackGeometry(
        points=candidate.points,
        bounds=candidate.bounds,
        source=source,
        circuit_key=circuit_key,
    )


def build_track_geometry_from_position_groups(
    position_groups: Mapping[Any, Iterable[TrackMapPosition]]
    | Iterable[Iterable[TrackMapPosition]],
    *,
    circuit_key: str | None = None,
    source: str = "derived_position_z",
    max_points: int = 1000,
    min_points: int = DEFAULT_TRACK_MAP_GEOMETRY_MIN_DRIVER_POINTS,
) -> TrackGeometry | None:
    """Build replay geometry from multiple driver sequences using v2 selection."""
    candidates: list[_TrackGeometryCandidate] = []
    stable_bounds: TrackMapBounds | None = None

    groups = (
        position_groups.values()
        if isinstance(position_groups, Mapping)
        else position_groups
    )
    for group in groups:
        positions = list(group)
        if not positions:
            continue
        filtered = _filter_geometry_positions(positions)
        for position in filtered:
            stable_bounds = _extend_bounds(stable_bounds, position)
        candidate = _build_track_geometry_candidate(
            filtered,
            max_points=max_points,
            min_points=min_points,
            already_filtered=True,
        )
        if candidate is not None:
            candidates.append(candidate)

    if not candidates:
        return None

    best = max(candidates, key=_geometry_candidate_score)
    return TrackGeometry(
        points=best.points,
        bounds=stable_bounds or best.bounds,
        source=source,
        circuit_key=circuit_key,
    )


def get_static_track_geometry_for_session(
    session: TrackMapSessionMetadata | None,
) -> TrackGeometry | None:
    """Return static catalog geometry for a session when available."""
    if session is None:
        return None
    return get_static_track_geometry(
        circuit_key=session.circuit_key,
        circuit_short_name=session.circuit_short_name,
    )


def get_static_track_geometry(
    *,
    circuit_key: str | None = None,
    circuit_short_name: str | None = None,
) -> TrackGeometry | None:
    """Return static catalog geometry by circuit key or short name."""
    normalized_key = _static_circuit_key(circuit_key, circuit_short_name)
    if normalized_key is None:
        return None

    entry = STATIC_TRACK_GEOMETRIES.get(normalized_key)
    if entry is None:
        return None

    points = entry["points"]
    bounds = _bounds_from_points(points)
    if bounds is None:
        return None
    return TrackGeometry(
        points=points,
        bounds=bounds,
        source=TRACK_MAP_STATIC_GEOMETRY_SOURCE,
        circuit_key=entry["circuit_key"],
        rotation=float(entry["rotation"]),
    )


def _extract_position_samples(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        position = payload.get("Position")
        if isinstance(position, list):
            return [sample for sample in position if isinstance(sample, Mapping)]
        if isinstance(payload.get("Entries"), Mapping):
            return [payload]
        return []
    if isinstance(payload, list):
        return [sample for sample in payload if isinstance(sample, Mapping)]

    text = _decode_text_payload(payload)
    if text is None:
        return []

    samples: list[Mapping[str, Any]] = []
    for line in text.splitlines() or [text]:
        decoded = _decode_position_z_line(line.strip())
        if decoded is None:
            continue
        samples.extend(_extract_position_samples(decoded))
    return samples


def _decode_text_payload(payload: Any) -> str | None:
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="ignore")
    if isinstance(payload, str):
        return payload
    return None


def _decode_position_z_line(line: str) -> Mapping[str, Any] | None:
    if not line or line.startswith("URL:"):
        return None
    encoded = line
    if '"' in line:
        try:
            _, rest = line.split('"', 1)
            encoded = rest.split('"', 1)[0]
        except ValueError:
            return None
    encoded = encoded.strip()
    if not encoded:
        return None
    try:
        raw = base64.b64decode(encoded, validate=True)
        payload = zlib.decompress(raw, wbits=-zlib.MAX_WBITS)
        decoded = json.loads(payload)
    except Exception:  # noqa: BLE001
        return None
    return decoded if isinstance(decoded, Mapping) else None


def _normalize_position_entries(
    entries: Mapping[Any, Any],
    timestamp: datetime,
) -> list[TrackMapPosition]:
    positions: list[TrackMapPosition] = []
    for rn_raw, entry in entries.items():
        if not isinstance(entry, Mapping):
            continue
        racing_number = _normalize_racing_number(
            entry.get("RacingNumber", rn_raw),
        )
        if racing_number is None:
            continue
        x = _coerce_int(entry.get("X"))
        y = _coerce_int(entry.get("Y"))
        if x is None or y is None:
            continue
        z = _coerce_int(entry.get("Z"))
        status = _normalize_status(entry.get("Status"))
        positions.append(
            TrackMapPosition(
                racing_number=racing_number,
                timestamp=timestamp,
                x=x,
                y=y,
                z=z,
                status=status,
            )
        )
    return positions


def _positions_from_replay_payload(
    raw_positions: Iterable[Any],
) -> list[TrackMapPosition]:
    positions: list[TrackMapPosition] = []
    for item in raw_positions:
        if not isinstance(item, Mapping):
            continue
        racing_number = _normalize_racing_number(
            item.get("racing_number", item.get("RacingNumber")),
        )
        timestamp = _parse_utc(item.get("timestamp", item.get("Timestamp")))
        x = _coerce_int(item.get("x", item.get("X")))
        y = _coerce_int(item.get("y", item.get("Y")))
        if racing_number is None or timestamp is None or x is None or y is None:
            continue
        positions.append(
            TrackMapPosition(
                racing_number=racing_number,
                timestamp=timestamp,
                x=x,
                y=y,
                z=_coerce_int(item.get("z", item.get("Z"))),
                status=_normalize_status(item.get("status", item.get("Status"))),
            )
        )
    return positions


def _extend_bounds(
    bounds: TrackMapBounds | None,
    position: TrackMapPosition,
) -> TrackMapBounds:
    if bounds is None:
        return TrackMapBounds(
            min_x=position.x,
            max_x=position.x,
            min_y=position.y,
            max_y=position.y,
            min_z=position.z,
            max_z=position.z,
        )
    min_z = bounds.min_z
    max_z = bounds.max_z
    if position.z is not None:
        min_z = position.z if min_z is None else min(min_z, position.z)
        max_z = position.z if max_z is None else max(max_z, position.z)
    return TrackMapBounds(
        min_x=min(bounds.min_x, position.x),
        max_x=max(bounds.max_x, position.x),
        min_y=min(bounds.min_y, position.y),
        max_y=max(bounds.max_y, position.y),
        min_z=min_z,
        max_z=max_z,
    )


def _filter_geometry_positions(
    positions: Iterable[TrackMapPosition],
) -> list[TrackMapPosition]:
    filtered = [
        position
        for position in positions
        if position.status.strip().lower() == "ontrack"
        and not (position.x == 0 and position.y == 0)
    ]
    if len(filtered) <= 4:
        return filtered

    xs = [position.x for position in filtered]
    ys = [position.y for position in filtered]
    median_x = median(xs)
    median_y = median(ys)
    mad_x = median(abs(value - median_x) for value in xs)
    mad_y = median(abs(value - median_y) for value in ys)
    threshold_x = max(1000.0, float(mad_x) * 20.0)
    threshold_y = max(1000.0, float(mad_y) * 20.0)
    return [
        position
        for position in filtered
        if abs(position.x - median_x) <= threshold_x
        and abs(position.y - median_y) <= threshold_y
    ]


def _build_track_geometry_candidate(
    positions: Iterable[TrackMapPosition],
    *,
    max_points: int,
    min_points: int,
    already_filtered: bool = False,
) -> _TrackGeometryCandidate | None:
    filtered = (
        list(positions) if already_filtered else _filter_geometry_positions(positions)
    )
    if len(filtered) < min_points:
        return None

    deduped = _dedupe_consecutive_positions(filtered)
    segments = _split_geometry_position_segments(deduped)
    candidates: list[_TrackGeometryCandidate] = []
    for segment in segments:
        if len(segment) < min_points:
            continue
        selected = _find_closed_geometry_segment(segment)
        closed_loop = selected is not None
        selected_positions = selected.positions if selected is not None else segment
        source_points = _positions_to_points(selected_positions)
        if not source_points:
            continue
        thinned = _thin_geometry_points(source_points, max_points)
        points = _downsample_points(thinned, max_points)
        if not points:
            continue
        bounds = _bounds_from_points(source_points)
        if bounds is None:
            continue
        path_length = (
            selected.path_length
            if selected is not None
            else _path_length(source_points)
        )
        candidates.append(
            _TrackGeometryCandidate(
                points=points,
                bounds=bounds,
                path_length=path_length,
                source_point_count=len(source_points),
                closed_loop=closed_loop,
                closure_gap=selected.closure_gap if selected is not None else None,
            )
        )

    if not candidates:
        return None
    return max(candidates, key=_geometry_candidate_score)


def _dedupe_consecutive_positions(
    positions: Iterable[TrackMapPosition],
) -> tuple[TrackMapPosition, ...]:
    deduped: list[TrackMapPosition] = []
    previous: tuple[int, int] | None = None
    for position in positions:
        point = (position.x, position.y)
        if point == previous:
            continue
        deduped.append(position)
        previous = point
    return tuple(deduped)


def _split_geometry_position_segments(
    positions: tuple[TrackMapPosition, ...],
) -> tuple[tuple[TrackMapPosition, ...], ...]:
    if len(positions) < 6:
        return (positions,)

    distances = [
        _point_distance(_position_point(start), _position_point(end))
        for start, end in zip(positions, positions[1:], strict=False)
    ]
    nonzero_distances = [distance for distance in distances if distance > 0]
    if not nonzero_distances:
        return (positions,)

    jump_threshold = max(2500.0, float(median(nonzero_distances)) * 8.0)
    segments: list[tuple[TrackMapPosition, ...]] = []
    current: list[TrackMapPosition] = [positions[0]]
    for distance, position in zip(distances, positions[1:], strict=False):
        if distance > jump_threshold and len(current) >= 2:
            segments.append(tuple(current))
            current = [position]
        else:
            current.append(position)
    if current:
        segments.append(tuple(current))
    return tuple(segments)


def _find_closed_geometry_segment(
    positions: tuple[TrackMapPosition, ...],
) -> _ClosedGeometrySegment | None:
    if len(positions) < 8:
        return None

    points = _positions_to_points(positions)
    bounds = _bounds_from_points(points)
    if bounds is None:
        return None

    cumulative = _cumulative_path_lengths(points)
    total_length = cumulative[-1]
    diagonal = _bounds_diagonal(bounds)
    min_loop_distance = max(3000.0, diagonal * 2.0)
    if total_length < min_loop_distance:
        return None

    close_distance = max(150.0, min(900.0, diagonal * 0.025))
    cell_size = close_distance
    cells: dict[tuple[int, int], int] = {}
    best: tuple[int, int, float, float] | None = None

    for index, point in enumerate(points):
        cell = _geometry_cell(point, cell_size)
        for nearby_cell in _nearby_geometry_cells(cell):
            start_index = cells.get(nearby_cell)
            if start_index is None or index - start_index < 6:
                continue
            path_length = cumulative[index] - cumulative[start_index]
            if path_length < min_loop_distance:
                continue
            closure_gap = _point_distance(points[start_index], point)
            if closure_gap > close_distance:
                continue
            if not _closure_direction_is_compatible(
                positions,
                start_index,
                index,
            ):
                continue
            if best is None or (path_length, closure_gap) < (best[2], best[3]):
                best = (start_index, index, path_length, closure_gap)
        cells.setdefault(cell, index)

    if best is None:
        return None

    start_index, end_index, path_length, closure_gap = best
    return _ClosedGeometrySegment(
        positions=positions[start_index : end_index + 1],
        path_length=path_length,
        closure_gap=closure_gap,
    )


def _closure_direction_is_compatible(
    positions: tuple[TrackMapPosition, ...],
    start_index: int,
    end_index: int,
) -> bool:
    start_heading = _geometry_heading(positions, start_index, forward=True)
    end_heading = _geometry_heading(positions, end_index, forward=False)
    if start_heading is None or end_heading is None:
        return True
    direction_dot = (start_heading[0] * end_heading[0]) + (
        start_heading[1] * end_heading[1]
    )
    if direction_dot < 0.25:
        return False

    start_z = positions[start_index].z
    end_z = positions[end_index].z
    return start_z is None or end_z is None or abs(start_z - end_z) <= 40


def _geometry_heading(
    positions: tuple[TrackMapPosition, ...],
    index: int,
    *,
    forward: bool,
) -> tuple[float, float] | None:
    if forward:
        if index + 1 >= len(positions):
            return None
        start = _position_point(positions[index])
        end = _position_point(positions[index + 1])
    else:
        if index <= 0:
            return None
        start = _position_point(positions[index - 1])
        end = _position_point(positions[index])
    distance = _point_distance(start, end)
    if distance <= 0:
        return None
    return ((end[0] - start[0]) / distance, (end[1] - start[1]) / distance)


def _thin_geometry_points(
    points: tuple[tuple[int, int], ...],
    max_points: int,
) -> tuple[tuple[int, int], ...]:
    if len(points) <= max(500, max_points * 2):
        return points

    bounds = _bounds_from_points(points)
    if bounds is None:
        return points
    min_distance = max(20.0, min(120.0, _bounds_diagonal(bounds) * 0.0015))
    thinned: list[tuple[int, int]] = []
    previous: tuple[int, int] | None = None
    for point in points:
        if previous is not None and _point_distance(previous, point) < min_distance:
            continue
        thinned.append(point)
        previous = point
    if thinned and thinned[-1] != points[-1]:
        thinned.append(points[-1])
    return tuple(thinned)


def _positions_to_points(
    positions: Iterable[TrackMapPosition],
) -> tuple[tuple[int, int], ...]:
    return tuple((position.x, position.y) for position in positions)


def _position_point(position: TrackMapPosition) -> tuple[int, int]:
    return (position.x, position.y)


def _cumulative_path_lengths(points: tuple[tuple[int, int], ...]) -> list[float]:
    cumulative = [0.0]
    for start, end in zip(points, points[1:], strict=False):
        cumulative.append(cumulative[-1] + _point_distance(start, end))
    return cumulative


def _path_length(points: tuple[tuple[int, int], ...]) -> float:
    if len(points) < 2:
        return 0.0
    return _cumulative_path_lengths(points)[-1]


def _point_distance(start: tuple[int, int], end: tuple[int, int]) -> float:
    return ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5


def _bounds_diagonal(bounds: TrackMapBounds) -> float:
    return (
        (bounds.max_x - bounds.min_x) ** 2 + (bounds.max_y - bounds.min_y) ** 2
    ) ** 0.5


def _geometry_cell(point: tuple[int, int], cell_size: float) -> tuple[int, int]:
    return (int(point[0] // cell_size), int(point[1] // cell_size))


def _nearby_geometry_cells(cell: tuple[int, int]) -> Iterable[tuple[int, int]]:
    x_cell, y_cell = cell
    for x_offset in (-1, 0, 1):
        for y_offset in (-1, 0, 1):
            yield (x_cell + x_offset, y_cell + y_offset)


def _geometry_candidate_score(
    candidate: _TrackGeometryCandidate,
) -> tuple[int, float, int, float]:
    closure_penalty = candidate.closure_gap or 0.0
    return (
        1 if candidate.closed_loop else 0,
        candidate.path_length,
        candidate.source_point_count,
        -closure_penalty,
    )


def _is_static_track_geometry(geometry: TrackGeometry | None) -> bool:
    return geometry is not None and geometry.source == TRACK_MAP_STATIC_GEOMETRY_SOURCE


def _track_map_fallback_state(
    session: TrackMapSessionMetadata | None,
    geometry: TrackGeometry | None,
) -> str:
    if session is None:
        return TRACK_MAP_FALLBACK_STATE_NO_SESSION
    if geometry is None:
        return TRACK_MAP_FALLBACK_STATE_WAITING_FOR_REPLAY_POSITION_Z
    if geometry.source == TRACK_MAP_STATIC_GEOMETRY_SOURCE:
        return TRACK_MAP_FALLBACK_STATE_STATIC_CATALOG
    if geometry.source == TRACK_MAP_REPLAY_GEOMETRY_SOURCE:
        return TRACK_MAP_FALLBACK_STATE_REPLAY_V2
    return TRACK_MAP_FALLBACK_STATE_CUSTOM_GEOMETRY


def _static_track_geometry_catalog_entry(
    session: TrackMapSessionMetadata | None,
    geometry: TrackGeometry | None,
) -> Mapping[str, Any] | None:
    catalog_key: str | None = None
    if _is_static_track_geometry(geometry):
        catalog_key = _string_or_none(geometry.circuit_key)
    if catalog_key not in STATIC_TRACK_GEOMETRIES:
        catalog_key = _static_circuit_key(
            session.circuit_key if session else None,
            session.circuit_short_name if session else None,
        )
    if catalog_key is None:
        return None
    return STATIC_TRACK_GEOMETRIES.get(catalog_key)


def _static_circuit_key(
    circuit_key: str | None,
    circuit_short_name: str | None,
) -> str | None:
    key = _string_or_none(circuit_key)
    if key in STATIC_TRACK_GEOMETRIES:
        return key

    alias = _static_circuit_alias(circuit_short_name)
    if alias is None:
        return None
    return STATIC_TRACK_GEOMETRY_ALIAS_TO_KEY.get(alias)


def _static_circuit_alias(value: str | None) -> str | None:
    text = _string_or_none(value)
    if text is None:
        return None
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _downsample_points(
    points: tuple[tuple[int, int], ...],
    max_points: int,
) -> tuple[tuple[int, int], ...]:
    if max_points <= 0:
        return ()
    if len(points) <= max_points:
        return points
    if max_points == 1:
        return (points[0],)
    step = (len(points) - 1) / (max_points - 1)
    return tuple(points[round(index * step)] for index in range(max_points))


def _bounds_from_points(points: Iterable[tuple[int, int]]) -> TrackMapBounds | None:
    point_list = list(points)
    if not point_list:
        return None
    xs = [point[0] for point in point_list]
    ys = [point[1] for point in point_list]
    return TrackMapBounds(
        min_x=min(xs),
        max_x=max(xs),
        min_y=min(ys),
        max_y=max(ys),
    )


def _normalize_racing_number(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value) if 0 < value <= MAX_TRACK_MAP_RACING_NUMBER else None
    text = str(value or "").strip()
    if not text.isdigit():
        return None
    number = int(text)
    return str(number) if 0 < number <= MAX_TRACK_MAP_RACING_NUMBER else None


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
    return None


def _normalize_status(value: Any) -> str:
    status = str(value or "").strip()
    return status or _POSITION_STATUS_UNKNOWN


def _extract_driver_list_payload(payload: Mapping[Any, Any]) -> Mapping[Any, Any]:
    driver_list = payload.get("DriverList")
    if isinstance(driver_list, Mapping):
        return driver_list
    lines = payload.get("Lines")
    if isinstance(lines, Mapping):
        return lines
    return payload


def _driver_metadata_from_payload(
    racing_number: str,
    payload: Mapping[str, Any],
    existing: TrackMapDriverMetadata | None,
) -> TrackMapDriverMetadata:
    first_name = _string_or_none(payload.get("FirstName"))
    last_name = _string_or_none(payload.get("LastName"))
    joined_name = " ".join(part for part in (first_name, last_name) if part) or None
    full_name = _first_text(
        payload.get("FullName"),
        joined_name,
        existing.full_name if existing else None,
    )
    broadcast_name = _first_text(
        payload.get("BroadcastName"),
        existing.broadcast_name if existing else None,
    )
    return TrackMapDriverMetadata(
        racing_number=racing_number,
        tla=_first_text(payload.get("Tla"), existing.tla if existing else None),
        full_name=full_name,
        broadcast_name=broadcast_name,
        team_name=_first_text(
            payload.get("TeamName"),
            existing.team_name if existing else None,
        ),
        team_color=_first_text(
            _normalize_color(payload.get("TeamColour") or payload.get("TeamColor")),
            existing.team_color if existing else None,
        ),
    )


def _session_metadata_from_payload(
    payload: Mapping[str, Any] | None,
) -> TrackMapSessionMetadata | None:
    if not isinstance(payload, Mapping):
        return None
    session_payload = payload.get("SessionInfo")
    if isinstance(session_payload, Mapping):
        payload = session_payload
    meeting = payload.get("Meeting")
    meeting = meeting if isinstance(meeting, Mapping) else {}
    circuit = meeting.get("Circuit")
    circuit = circuit if isinstance(circuit, Mapping) else {}
    return TrackMapSessionMetadata(
        session_key=_first_text(payload.get("Key"), payload.get("Path")),
        path=_first_text(payload.get("Path")),
        meeting_key=_first_text(meeting.get("Key")),
        meeting_name=_first_text(meeting.get("Name")),
        session_name=_first_text(payload.get("Name")),
        session_type=_first_text(payload.get("Type")),
        circuit_key=_first_text(circuit.get("Key")),
        circuit_short_name=_first_text(circuit.get("ShortName")),
    )


def _session_payload(
    session: TrackMapSessionMetadata | None,
) -> dict[str, Any] | None:
    if session is None:
        return None
    return {
        "session_key": session.session_key,
        "path": session.path,
        "meeting_key": session.meeting_key,
        "meeting_name": session.meeting_name,
        "session_name": session.session_name,
        "session_type": session.session_type,
        "circuit_key": session.circuit_key,
        "circuit_short_name": session.circuit_short_name,
    }


def _geometry_payload(geometry: TrackGeometry | None) -> dict[str, Any] | None:
    if geometry is None:
        return None
    return {
        "source": geometry.source,
        "circuit_key": geometry.circuit_key,
        "rotation": geometry.rotation,
        "bounds": _bounds_payload(geometry.bounds),
        "points": [[x, y] for x, y in geometry.points],
    }


def _bounds_payload(bounds: TrackMapBounds) -> dict[str, Any]:
    return {
        "min_x": bounds.min_x,
        "max_x": bounds.max_x,
        "min_y": bounds.min_y,
        "max_y": bounds.max_y,
        "min_z": bounds.min_z,
        "max_z": bounds.max_z,
    }


def _driver_display_name(metadata: TrackMapDriverMetadata | None) -> str | None:
    if metadata is None:
        return None
    return metadata.full_name or metadata.broadcast_name


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = _string_or_none(value)
        if text is not None:
            return text
    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_color(value: Any) -> str | None:
    text = _string_or_none(value)
    if text is None:
        return None
    return text.removeprefix("#")


def _racing_number_sort_key(position: TrackMapPosition) -> int:
    return int(position.racing_number)


def _snapshot_now(now: datetime | None) -> datetime:
    return _parse_utc(now, default=datetime.now(UTC)) or datetime.now(UTC)


def _format_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_utc(
    value: datetime | str | None,
    *,
    default: datetime | None = None,
) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        return default
    text = value.strip()
    if not text:
        return default
    text = _FRACTIONAL_SECONDS_RE.sub(r"\1", text)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return default
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
