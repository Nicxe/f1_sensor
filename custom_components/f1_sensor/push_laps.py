"""Conservative, bounded push-lap inference from the public timing stream."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
import math
from typing import Any

COMPLETED_HOLD_SECONDS = 6.0
STALE_SECONDS = 45.0
_RECORDED = {2048, 2049, 2051}
_IMPROVED = {2049, 2051}


def empty_push_lap() -> dict[str, Any]:
    """Return the stable public contract, including unavailable values."""
    return {
        "state": "unknown",
        "active": False,
        "confidence": None,
        "lap": None,
        "progress": None,
        "observed_at": None,
        "completed_at": None,
        "last_lap_time": None,
        "reason": "insufficient_data",
    }


def _number(value: object) -> float | None:
    if isinstance(value, Mapping):
        value = value.get("Value")
    if isinstance(value, bool) or value is None:
        return None
    try:
        parts = str(value).split(":")
        result = 0.0
        for part in parts:
            result = result * 60 + float(part)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def _items(value: object, limit: int):
    if isinstance(value, Mapping):
        items = value.items()
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = enumerate(value)
    else:
        return
    for key, item in items:
        if str(key).isdigit() and 0 <= int(key) < limit and isinstance(item, Mapping):
            yield int(key), item


@dataclass(slots=True)
class _Driver:
    completed: int | None = None
    lap: int | None = None
    in_pit: bool = False
    outlap: bool = False
    stopped: bool = False
    retired: bool = False
    state: str = "unknown"
    confidence: str | None = None
    reason: str = "insufficient_data"
    progress: float | None = None
    observed_at: str | None = None
    activity: float | None = None
    segments: dict[tuple[int, int], int] = field(default_factory=dict)
    layout: dict[int, int] = field(default_factory=dict)
    fresh: set[tuple[int, int]] = field(default_factory=set)
    improved: set[tuple[int, int]] = field(default_factory=set)
    sectors: dict[int, float] = field(default_factory=dict)
    sector_reference: dict[int, float] = field(default_factory=dict)
    interval_reference: dict[tuple[int, int], float] = field(default_factory=dict)
    crossing_reference: dict[tuple[int, int], float] = field(default_factory=dict)
    crossings: dict[tuple[int, int], float] = field(default_factory=dict)
    lap_start: float | None = None
    lap_anchored: bool = False
    snapshot_origin: bool = False
    previous_crossing: tuple[int, int] | None = None
    previous_crossing_time: float | None = None
    slow_intervals: int = 0
    completed_result: dict[str, Any] | None = None
    completed_time: float | None = None
    boundary_time: float | None = None
    pending_completed_lap: int | None = None
    pending_was_push: bool = False


class PushLapTracker:
    """Infer current effort without telemetry, future data, or wall-clock timers."""

    def __init__(self) -> None:
        self._supported: bool | None = None
        self._session: str | None = None
        self.reset()

    def reset(self) -> None:
        """Discard one playback/source generation, retaining session capability."""
        self._drivers: dict[str, _Driver] = {}
        self._now: float | None = None
        self._relative_clock = False
        self._explicit_clock = False
        self._utc: str | None = None
        self._part: object = None
        self._clear_track = True
        self._finalised = False
        self._session_running = True
        self._finished_laps: dict[str, int | None] | None = None
        self._has_timing = False

    @property
    def status(self) -> str:
        """Return capability separately from whether any driver is pushing."""
        if self._supported is False:
            return "unsupported"
        if not self._supported or not self._has_timing:
            return "waiting"
        on_track = {
            key: driver
            for key, driver in self._drivers.items()
            if not (driver.in_pit or driver.stopped or driver.retired)
        }
        # Pit snapshots must not hide missing evidence for cars on the circuit.
        for key, driver in (on_track or self._drivers).items():
            effort = self.driver_snapshot(key)
            if effort["state"] not in {
                "pit",
                "outlap",
                "probable_push",
                "push",
                "cooldown",
                "completed",
            }:
                continue
            if (
                effort["state"] == "outlap"
                and driver.activity is not None
                and self._now is not None
                and self._now - driver.activity > STALE_SECONDS
            ):
                continue
            return "available"
        return "waiting"

    @property
    def stream_time(self) -> str | None:
        """Return a real provider UTC timestamp when one is available."""
        return self._utc

    def _clock(self, payload: Mapping[str, Any]) -> bool:
        utc = payload.get("_f1_source_utc")
        if utc is None and not self._relative_clock:
            utc = payload.get("Utc") or payload.get("Timestamp")
        parsed = None
        if isinstance(utc, str):
            try:
                parsed = datetime.fromisoformat(utc.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = None
            except ValueError:
                pass
        now = _number(payload.get("_f1_source_time"))
        explicit = now is not None or payload.get("_f1_source_utc") is not None
        if now is not None and now < 1_000_000_000:
            if not self._explicit_clock:
                self._now = None
            self._relative_clock = True
        if now is None and parsed is not None:
            now = parsed.timestamp()
        if now is not None and self._now is not None and now < self._now:
            return False
        if now is not None:
            self._now = now
            self._utc = parsed.astimezone(UTC).isoformat() if parsed else None
            self._explicit_clock = self._explicit_clock or explicit
        return True

    def update(self, stream: str, payload: object) -> None:
        """Apply one ordered, already-delayed public source event."""
        if not isinstance(payload, Mapping):
            return
        if stream == "Heartbeat" and not any(
            key in payload for key in ("_f1_source_time", "_f1_source_utc")
        ):
            # Initial replay snapshots can contain UTC but no replay offset.
            # They must not establish an epoch clock before relative playback.
            return
        if stream == "SessionInfo":
            session = (
                str(payload.get("Key")) if payload.get("Key") is not None else None
            )
            if (
                session is not None
                and self._session is not None
                and session != self._session
            ):
                self.reset()
            if session is not None:
                self._session = session
            if "Type" in payload or "Name" in payload:
                name = f"{payload.get('Type', '')} {payload.get('Name', '')}".lower()
                self._supported = any(
                    word in name for word in ("qualifying", "shootout", "practice")
                )
            return
        if not self._clock(payload):
            return
        if stream == "TrackStatus":
            self._clear_track = str(payload.get("Status", "1")) == "1"
            if not self._clear_track:
                for driver in self._drivers.values():
                    self._set(driver, "cooldown", None, "track_not_clear")
                    driver.completed_result = None
                    driver.improved.clear()
            return
        if stream == "SessionStatus":
            status = payload.get("Status")
            self._finalised = status in {"Finalised", "Ends"}
            if (
                status in {"Started", "Green", "GreenFlag"}
                or payload.get("Started") is True
            ):
                self._session_running = True
                self._finished_laps = None
            if status == "Finished":
                self._finished_laps = {
                    key: driver.lap
                    for key, driver in self._drivers.items()
                    if not driver.in_pit and not driver.outlap
                }
            if status in {"Aborted", "Inactive", "Finalised", "Ends"}:
                self._session_running = False
                for driver in self._drivers.values():
                    self._set(driver, "unknown", None, "session_not_running")
                    driver.completed_result = None
            return
        if stream != "TimingData" or self._supported is not True:
            return
        part = payload.get("SessionPart")
        if part is not None and self._part is not None and part != self._part:
            self._drivers.clear()
        if part is not None:
            self._part = part
        self._has_timing = True
        snapshot = payload.get("_f1_snapshot") is True
        lines = payload.get("Lines")
        if not isinstance(lines, Mapping):
            return
        for rn, line in lines.items():
            key = str(rn)
            if not key.isdigit() or len(key) > 3 or not isinstance(line, Mapping):
                continue
            if key not in self._drivers and len(self._drivers) >= 32:
                continue
            if snapshot:
                self._drivers[key] = _Driver()
            driver = self._drivers.setdefault(key, _Driver())
            self._merge(driver, line, snapshot)

    @staticmethod
    def _set(driver: _Driver, state: str, confidence: str | None, reason: str) -> None:
        driver.state, driver.confidence, driver.reason = state, confidence, reason

    def _new_lap(self, driver: _Driver, completed: int) -> None:
        driver.pending_completed_lap = driver.lap
        driver.pending_was_push = driver.state in {"push", "probable_push"}
        driver.boundary_time = self._now
        driver.lap_start = self._now
        driver.lap_anchored = True
        driver.snapshot_origin = False
        driver.completed = completed
        driver.lap = completed
        driver.outlap = False
        driver.fresh.clear()
        driver.improved.clear()
        driver.sectors.clear()
        driver.crossings.clear()
        driver.previous_crossing = None
        driver.previous_crossing_time = None
        driver.slow_intervals = 0
        driver.progress = 0.0
        self._set(driver, "unknown", None, "new_lap")

    def _merge(self, driver: _Driver, line: Mapping[str, Any], snapshot: bool) -> None:
        raw_laps = _number(line.get("NumberOfLaps"))
        completed = int(raw_laps) if raw_laps is not None else None
        if snapshot:
            driver.snapshot_origin = True
            driver.completed_result = None
            driver.fresh.clear()
            driver.improved.clear()
            self._set(driver, "unknown", None, "snapshot_only")
        elif (
            completed is not None
            and driver.completed is not None
            and completed > driver.completed
        ):
            self._new_lap(driver, completed)
        elif (
            completed is not None
            and driver.completed is not None
            and completed < driver.completed
        ):
            # Seeking/restarting requires rebuilding references from observed events.
            replacement = _Driver()
            for name in _Driver.__dataclass_fields__:
                setattr(driver, name, getattr(replacement, name))
        if completed is not None:
            if driver.completed is None and not snapshot:
                driver.lap_start = self._now
                driver.lap_anchored = True
            driver.completed, driver.lap = completed, completed
        old_pit = driver.in_pit
        if "InPit" in line:
            driver.in_pit = line["InPit"] is True
        if (
            line.get("PitOut") is True
            or old_pit
            and "InPit" in line
            and not driver.in_pit
        ):
            driver.outlap = True
            driver.completed_result = None
        if "Stopped" in line:
            driver.stopped = line["Stopped"] is True
        if "Retired" in line:
            driver.retired = line["Retired"] is True
        lap_time = _number(line.get("LastLapTime"))
        if (
            not snapshot
            and lap_time
            and driver.pending_was_push
            and driver.boundary_time is not None
            and self._now is not None
            and self._now - driver.boundary_time <= 5
        ):
            driver.completed_time = self._now
            driver.completed_result = {
                **empty_push_lap(),
                "state": "completed",
                "confidence": "high",
                "lap": driver.pending_completed_lap,
                "progress": 1.0,
                "observed_at": self._utc,
                "completed_at": self._utc,
                "last_lap_time": lap_time,
                "reason": "lap_completed",
            }
            driver.pending_was_push = False
        changed = False
        for sector, delta in _items(line.get("Sectors"), 3):
            segment_items = list(_items(delta.get("Segments"), 32))
            if segment_items:
                driver.layout[sector] = max(
                    driver.layout.get(sector, 0),
                    max(index for index, _ in segment_items) + 1,
                )
            fresh = []
            late_completed_sector = (
                sector > 0
                and (driver.boundary_time is not None or driver.snapshot_origin)
                and sector - 1 not in driver.sectors
                and not any(point[0] == sector - 1 for point in driver.fresh)
            )
            for index, segment in segment_items:
                status = segment.get("Status")
                if not isinstance(status, int) or isinstance(status, bool):
                    continue
                point = (sector, index)
                previous = driver.segments.get(point)
                driver.segments[point] = status
                if (
                    snapshot
                    or late_completed_sector
                    or status not in _RECORDED
                    or previous in _RECORDED
                ):
                    continue
                driver.fresh.add(point)
                fresh.append(point)
                if status in _IMPROVED:
                    driver.improved.add(point)
                changed = True
                length = driver.layout.get(sector, index + 1)
                driver.progress = max(
                    driver.progress or 0, (sector + (index + 1) / max(length, 1)) / 3
                )
            self._segment_pace(driver, fresh)
            seconds = _number(delta.get("Value"))
            if (
                not snapshot
                and seconds
                and delta.get("Stopped") is not True
                and not late_completed_sector
                and seconds != driver.sectors.get(sector)
            ):
                if sector == 0 and not self._lap_is_observed(driver):
                    # Late checkpoint sectors cannot provide current-lap progress.
                    driver.progress = 0.0
                    driver.sectors.clear()
                    driver.fresh = {point for point in driver.fresh if point[0] == 0}
                    driver.improved = {
                        point for point in driver.improved if point[0] == 0
                    }
                    driver.crossings.clear()
                    driver.previous_crossing = None
                    driver.previous_crossing_time = None
                driver.sectors[sector] = seconds
                driver.progress = max(driver.progress or 0, (sector + 1) / 3)
                changed = True
                reference = driver.sector_reference.get(sector)
                if self._eligible(driver):
                    if (
                        delta.get("PersonalFastest") is True
                        or delta.get("OverallFastest") is True
                    ):
                        self._set(driver, "push", "high", "competitive_sector")
                    elif reference is not None and seconds <= reference * 1.12:
                        self._set(driver, "push", "medium", "competitive_sector_pace")
                    elif reference is not None and seconds > reference * 1.25:
                        self._set(driver, "cooldown", "medium", "slow_sector")
                if self._eligible(driver):
                    driver.sector_reference[sector] = min(seconds, reference or seconds)
        if changed or any(key in line for key in ("InPit", "PitOut", "NumberOfLaps")):
            driver.activity, driver.observed_at = self._now, self._utc
        if (
            self._eligible(driver)
            and driver.state == "unknown"
            and len(driver.improved) >= 2
        ):
            self._set(driver, "probable_push", "medium", "fresh_improving_minisectors")
        if self._eligible(driver) and driver.state in {"push", "probable_push"}:
            for point, elapsed in driver.crossings.items():
                reference = driver.crossing_reference.get(point)
                driver.crossing_reference[point] = min(elapsed, reference or elapsed)
        if driver.progress is not None:
            driver.progress = min(driver.progress, 0.99)
        if driver.in_pit:
            self._set(driver, "pit", None, "in_pit")
            driver.completed_result = None
        elif driver.stopped or driver.retired:
            self._set(driver, "unknown", None, "driver_stopped")
            driver.completed_result = None
        elif driver.outlap:
            self._set(driver, "outlap", "high", "pit_exit_lap")

    @staticmethod
    def _lap_is_observed(driver: _Driver) -> bool:
        return driver.lap_anchored or 0 in driver.sectors

    def _eligible(self, driver: _Driver) -> bool:
        finished_lap = self._finished_laps is None or any(
            item is driver and self._finished_laps.get(key) == driver.lap
            for key, item in self._drivers.items()
        )
        return (
            not (
                driver.in_pit
                or driver.outlap
                or driver.stopped
                or driver.retired
                or self._finalised
                or not self._session_running
            )
            and self._clear_track
            and finished_lap
            and self._lap_is_observed(driver)
        )

    def _segment_pace(self, driver: _Driver, fresh: list[tuple[int, int]]) -> None:
        for point in sorted(fresh):
            cumulative_reference = driver.crossing_reference.get(point)
            cumulative_elapsed = (
                self._now - driver.lap_start
                if self._now is not None and driver.lap_start is not None
                else None
            )
            cumulative_slow = False
            if cumulative_elapsed is not None and cumulative_elapsed > 0:
                driver.crossings[point] = cumulative_elapsed
                if cumulative_reference and self._eligible(driver):
                    if cumulative_elapsed <= cumulative_reference * 1.18:
                        self._set(
                            driver, "push", "medium", "competitive_minisector_pace"
                        )
                    elif cumulative_elapsed > cumulative_reference * 1.25:
                        self._set(driver, "cooldown", "medium", "slow_minisector_pace")
                        cumulative_slow = True
            previous = driver.previous_crossing
            at = driver.previous_crossing_time
            if (
                len(fresh) == 1
                and self._now is not None
                and at is not None
                and previous == (point[0], point[1] - 1)
            ):
                elapsed = self._now - at
                reference = driver.interval_reference.get(point)
                if self._eligible(driver) and elapsed > 0 and not cumulative_slow:
                    if reference and elapsed <= reference * 1.20:
                        driver.slow_intervals = 0
                        self._set(
                            driver, "push", "medium", "competitive_minisector_pace"
                        )
                    elif reference and elapsed > reference * 1.40:
                        driver.slow_intervals += 1
                        if driver.slow_intervals >= 2:
                            self._set(
                                driver, "cooldown", "medium", "slow_minisector_pace"
                            )
                    if driver.state in {"push", "probable_push"}:
                        driver.interval_reference[point] = min(
                            elapsed, reference or elapsed
                        )
            driver.previous_crossing, driver.previous_crossing_time = point, self._now

    def driver_snapshot(self, racing_number: str) -> dict[str, Any]:
        """Project current effort and the brief completed-result hold separately."""
        driver = self._drivers.get(str(racing_number))
        if driver is None:
            return empty_push_lap()
        if (
            driver.completed_result is not None
            and driver.completed_time is not None
            and self._now is not None
            and self._now - driver.completed_time < COMPLETED_HOLD_SECONDS
        ):
            return dict(driver.completed_result)
        result = {
            **empty_push_lap(),
            "state": driver.state,
            "active": driver.state in {"push", "probable_push"},
            "confidence": driver.confidence,
            "lap": driver.lap,
            "progress": driver.progress,
            "observed_at": driver.observed_at,
            "reason": driver.reason,
        }
        if not self._lap_is_observed(driver) and not (driver.in_pit or driver.outlap):
            result.update(state="unknown", active=False, confidence=None, progress=None)
        if (
            driver.activity is not None
            and self._now is not None
            and self._now - driver.activity > STALE_SECONDS
            and driver.state not in {"pit", "outlap"}
        ):
            result.update(
                state="unknown", active=False, confidence=None, reason="stale_timing"
            )
        if (
            self._supported is not True
            or self._finalised
            or not self._clear_track
            or not self._session_running
        ):
            result.update(active=False)
        return result
