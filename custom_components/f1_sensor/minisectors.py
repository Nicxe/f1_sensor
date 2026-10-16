"""Bounded sessionscoped state for F1 timing segment statuses."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import suppress
from copy import deepcopy
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

MAX_MINISECTOR_DRIVERS = 32
MAX_MINISECTOR_SECTORS = 3
MAX_MINISECTORS_PER_SECTOR = 32
_MAX_DRIVER_NUMBER_CHARS = 3
_MAX_STATUS_TEXT_CHARS = 32
_INVALID = object()


def _bounded_index(value: object, upper_bound: int) -> int | None:
    """Return a non-negative numeric source index inside one explicit bound."""
    if isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text.isdecimal() or len(text) > len(str(upper_bound - 1)):
        return None
    index = int(text)
    return index if 0 <= index < upper_bound else None


def _indexed_items(value: object, upper_bound: int) -> Iterator[tuple[int, Any]]:
    """Yield list positions or numeric mapping keys without renumbering gaps."""
    if isinstance(value, Mapping):
        items = value.items()
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = enumerate(value)
    else:
        return
    for raw_index, item in items:
        index = _bounded_index(raw_index, upper_bound)
        if index is not None:
            yield index, item


def _driver_key(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text.isdecimal() or len(text) > _MAX_DRIVER_NUMBER_CHARS or int(text) <= 0:
        return None
    return str(int(text))


def _stream_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip()
    if not text.isdecimal() or len(text) > 6:
        return None
    return int(text)


def _raw_status(value: object) -> object:
    """Keep bounded JSON scalar statuses and reject compound source values."""
    if value is None or isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip()
        return text[:_MAX_STATUS_TEXT_CHARS]
    return _INVALID


class MiniSectorStateStore:
    """Merge high-frequency TimingData segment deltas without HA state writes."""

    def __init__(self, *, entry_id: str | None = None) -> None:
        self._entry_id = entry_id
        self._generation = 0
        self._source = "live"
        self._session_id: str | None = None
        self._session_part: int | str | None = None
        self._last_reset_reason = "initial"
        self._unavailable_reason: str | None = None
        self._drivers: dict[str, dict[str, Any]] = {}
        self._listeners: dict[int, Callable[[], None]] = {}
        self._close_listeners: list[Callable[[], None]] = []
        self._next_listener_id = 0
        self._closed = False

    @property
    def entry_id(self) -> str | None:
        """Return the config entry that owns this bounded store."""
        return self._entry_id

    @property
    def closed(self) -> bool:
        """Return whether the owning coordinator has released the store."""
        return self._closed

    @property
    def listener_count(self) -> int:
        """Return the active state-listener count for load and cleanup checks."""
        return len(self._listeners)

    @property
    def generation(self) -> str:
        """Return the opaque generation identifier for later transport use."""
        return str(self._generation)

    def snapshot(self) -> dict[str, Any]:
        """Return an isolated, bounded snapshot of the current generation."""
        return {
            "entry_id": self._entry_id,
            "source": self._source,
            "session_id": self._session_id,
            "session_part": self._session_part,
            "generation": self.generation,
            "last_reset_reason": self._last_reset_reason,
            "unavailable_reason": self._unavailable_reason,
            "drivers": deepcopy(self._drivers),
        }

    def reset(
        self,
        reason: str,
        *,
        new_generation: bool = True,
        source: str | None = None,
        session_id: str | None = None,
        _notify: bool = True,
    ) -> bool:
        """Clear all segment state and optionally start a new generation."""
        normalized_reason = str(reason or "unknown")
        changed = bool(self._drivers) or new_generation
        self._drivers.clear()
        if new_generation:
            self._generation += 1
        if source is not None:
            changed = changed or source != self._source
            self._source = source
        if session_id is not None:
            changed = changed or session_id != self._session_id
            self._session_id = session_id
        changed = changed or normalized_reason != self._last_reset_reason
        self._last_reset_reason = normalized_reason
        unavailable_reason = {
            "spoiler_protected": "spoiler_protected",
            "source_unavailable": "source_inactive",
            "unload": "source_inactive",
        }.get(normalized_reason)
        changed = changed or unavailable_reason != self._unavailable_reason
        self._unavailable_reason = unavailable_reason
        if _notify and changed:
            self._notify_listeners()
        return changed

    def reset_driver(self, driver: object, reason: str = "new_lap") -> bool:
        """Clear one driver's current-lap statuses without changing generation."""
        key = _driver_key(driver)
        if key is None:
            return False
        removed = self._drivers.pop(key, None) is not None
        if removed:
            self._last_reset_reason = reason
            self._notify_listeners()
        return removed

    def set_session(self, session_id: str | None) -> bool:
        """Bind state to one session and clear it when that identity changes."""
        normalized = str(session_id).strip() if session_id is not None else None
        normalized = normalized or None
        if normalized == self._session_id:
            return False
        if self._session_id is None:
            self._session_id = normalized
            self._notify_listeners()
            return False
        self.reset("session_change", _notify=False)
        self._session_id = normalized
        self._notify_listeners()
        return True

    def set_source(self, source: str) -> bool:
        """Start a clean generation when switching between live and replay."""
        normalized = "replay" if source == "replay" else "live"
        if normalized == self._source:
            return False
        self.reset("source_change", source=normalized, _notify=False)
        self._notify_listeners()
        return True

    def merge_timing_data(self, payload: object) -> bool:
        """Merge one complete source frame atomically on the event-loop thread."""
        if self._closed or not isinstance(payload, Mapping):
            return False

        changed = self._apply_session_part(payload.get("SessionPart"), _notify=False)
        lines = payload.get("Lines")
        if not isinstance(lines, Mapping):
            if changed:
                self._unavailable_reason = None
                self._notify_listeners()
            return changed

        if self._contains_lap_rewind(lines):
            self.reset("replay_seek", _notify=False)
            changed = True

        for raw_driver, driver_delta in lines.items():
            driver = _driver_key(raw_driver)
            if driver is None or not isinstance(driver_delta, Mapping):
                continue
            existing = self._drivers.get(driver)
            if existing is None and not self._has_segment_data(driver_delta):
                continue
            if existing is None and len(self._drivers) >= MAX_MINISECTOR_DRIVERS:
                continue

            completed_laps = _stream_int(driver_delta.get("NumberOfLaps"))
            driver_state = existing
            if driver_state is None:
                driver_state = {
                    "completed_laps": completed_laps,
                    "current_lap": (
                        completed_laps + 1 if completed_laps is not None else None
                    ),
                    "sectors": {},
                }
                self._drivers[driver] = driver_state
                changed = True
            elif completed_laps is not None:
                if driver_state.get("completed_laps") != completed_laps:
                    driver_state["completed_laps"] = completed_laps
                    changed = True
                current_lap = completed_laps + 1
                if driver_state.get("current_lap") != current_lap:
                    driver_state["current_lap"] = current_lap
                    changed = True

            if self._merge_driver_segments(driver_state, driver_delta.get("Sectors")):
                changed = True

        if changed:
            self._unavailable_reason = None
            self._notify_listeners()
        return changed

    def close(self) -> None:
        """Discard all retained statuses and reject later source frames."""
        if self._closed:
            return
        self.reset("unload", _notify=False)
        self._closed = True
        self._notify_listeners()
        for listener in tuple(self._close_listeners):
            with suppress(Exception):
                listener()
        self._close_listeners.clear()
        self._listeners.clear()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register one atomic-frame listener and return its cleanup callback."""
        if self._closed:
            return lambda: None
        listener_id = self._next_listener_id
        self._next_listener_id += 1
        self._listeners[listener_id] = listener

        def _unsubscribe() -> None:
            self._listeners.pop(listener_id, None)

        return _unsubscribe

    def add_close_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Bind transport cleanup to the store lifetime."""
        if self._closed:
            return lambda: None
        self._close_listeners.append(listener)

        def _unsubscribe() -> None:
            with suppress(ValueError):
                self._close_listeners.remove(listener)

        return _unsubscribe

    def _notify_listeners(self) -> None:
        for listener in tuple(self._listeners.values()):
            try:
                listener()
            except Exception:
                _LOGGER.debug("Minisector listener failed", exc_info=True)

    def _apply_session_part(self, value: object, *, _notify: bool = True) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            normalized: int | str = str(value).lower()
        else:
            parsed = _stream_int(value)
            normalized = parsed if parsed is not None else str(value).strip()[:32]
        if normalized == self._session_part:
            return False
        if self._session_part is None:
            self._session_part = normalized
            return False
        self.reset("session_part", _notify=False)
        self._session_part = normalized
        if _notify:
            self._notify_listeners()
        return True

    def _contains_lap_rewind(self, lines: Mapping[object, object]) -> bool:
        for raw_driver, driver_delta in lines.items():
            driver = _driver_key(raw_driver)
            if driver is None or not isinstance(driver_delta, Mapping):
                continue
            completed_laps = _stream_int(driver_delta.get("NumberOfLaps"))
            existing = self._drivers.get(driver)
            previous = existing.get("completed_laps") if existing else None
            if (
                completed_laps is not None
                and isinstance(previous, int)
                and completed_laps < previous
            ):
                return True
        return False

    @staticmethod
    def _has_segment_data(driver_delta: Mapping[object, object]) -> bool:
        sectors = driver_delta.get("Sectors")
        return any(
            isinstance(sector, Mapping) and "Segments" in sector
            for _, sector in _indexed_items(sectors, MAX_MINISECTOR_SECTORS)
        )

    @staticmethod
    def _merge_driver_segments(
        driver_state: dict[str, Any], sectors_value: object
    ) -> bool:
        changed = False
        sectors = driver_state["sectors"]
        for sector_index, sector_delta in _indexed_items(
            sectors_value, MAX_MINISECTOR_SECTORS
        ):
            if not isinstance(sector_delta, Mapping) or "Segments" not in sector_delta:
                continue
            segments_value = sector_delta.get("Segments")
            sector_key = str(sector_index)
            sector_state = sectors.get(sector_key)
            if not isinstance(sector_state, dict):
                sector_state = {"segments": {}}
                sectors[sector_key] = sector_state
                changed = True
            segments = sector_state["segments"]
            if isinstance(segments_value, Sequence) and not isinstance(
                segments_value, (str, bytes)
            ):
                if segments:
                    segments.clear()
                    changed = True
            for segment_index, segment_delta in _indexed_items(
                segments_value, MAX_MINISECTORS_PER_SECTOR
            ):
                if (
                    not isinstance(segment_delta, Mapping)
                    or "Status" not in segment_delta
                ):
                    continue
                status = _raw_status(segment_delta.get("Status"))
                if status is _INVALID:
                    continue
                segment_key = str(segment_index)
                value = {"raw_status": status}
                if segments.get(segment_key) != value:
                    segments[segment_key] = value
                    changed = True
        return changed
