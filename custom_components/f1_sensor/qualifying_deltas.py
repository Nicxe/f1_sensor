"""Cumulative qualifying splits against one observed, officially valid lap."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
import re
from typing import Any

_TIME_ACTION = re.compile(
    r"CAR\s+(?P<driver>\d{1,3}).*?TIME\s+(?P<time>\d+:\d{2}\.\d{3}).*?(?P<action>DELETED|REINSTATED)",
    re.IGNORECASE,
)
_LAP_ACTION = re.compile(
    r"CAR\s+(?P<driver>\d{1,3}).*?LAP\s+DELETED.*?\bLAP\s+(?P<lap>\d+)",
    re.IGNORECASE,
)


def empty_push_lap_delta() -> dict[str, Any]:
    """Return stable keys when a qualifying comparison is unavailable."""
    return {
        "status": "waiting",
        "lap": None,
        "session_part": None,
        "reference": None,
        "sector_1": None,
        "sector_2": None,
        "sector_3": None,
        "latest_sector": None,
        "reason": "insufficient_data",
    }


def _seconds(value: object) -> float | None:
    if isinstance(value, Mapping):
        value = value.get("Value")
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = 0.0
        for part in str(value).split(":"):
            result = result * 60 + float(part)
        return result if math.isfinite(result) and result > 0 else None
    except (ValueError, TypeError):
        return None


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(str(value))
        return result if result >= 0 else None
    except (ValueError, TypeError):
        return None


def _items(value: object):
    if isinstance(value, Mapping):
        return value.items()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return enumerate(value)
    return ()


@dataclass(slots=True)
class _Profile:
    driver: str
    lap: int
    part: int
    time: float
    sectors: tuple[float, float, float]
    valid: bool = True


@dataclass(slots=True)
class _Attempt:
    lap: int | None
    sectors: dict[int, float] = field(default_factory=dict)
    reference: _Profile | None = None
    reference_selected: bool = False
    time: float | None = None
    official_lap: int | None = None


@dataclass(slots=True)
class _Car:
    current: _Attempt = field(default_factory=lambda: _Attempt(None))
    previous: _Attempt | None = None


class QualifyingDeltaTracker:
    """Retain bounded lap profiles without extrapolation or wall-clock timing."""

    def __init__(self) -> None:
        self.supported: bool | None = None
        self.reset()

    def reset(self) -> None:
        """Discard the source generation, preserving the known session kind."""
        self.part: int | None = None
        self._cars: dict[str, _Car] = {}
        self._profiles: list[_Profile] = []
        self._official: dict[str, tuple[float, int | None]] = {}
        self._deleted: set[tuple[str, float]] = set()
        self._deleted_laps: set[tuple[str, int]] = set()

    def session_info(self, payload: Mapping[str, Any]) -> None:
        if "Type" in payload or "Name" in payload:
            name = f"{payload.get('Type', '')} {payload.get('Name', '')}".lower()
            self.supported = "qualifying" in name or "shootout" in name

    def _reference(self) -> _Profile | None:
        if not self._official:
            return None
        fastest = min(value[0] for value in self._official.values())
        for profile in reversed(self._profiles):
            official = self._official.get(profile.driver)
            if (
                profile.valid
                and profile.part == self.part
                and official is not None
                and abs(profile.time - fastest) < 0.0005
                and abs(profile.time - official[0]) < 0.0005
                and (official[1] is None or profile.lap == official[1])
            ):
                return profile
        # A slower observed lap must never replace an unobserved official best.
        return None

    def update(self, payload: Mapping[str, Any]) -> None:
        """Consume one ordered TimingData frame after push-lap inference."""
        if self.supported is not True:
            return
        part = _integer(payload.get("SessionPart"))
        if part in {1, 2, 3} and part != self.part:
            self.reset()
            self.part = part
        if self.part is None:
            return
        lines = payload.get("Lines")
        if not isinstance(lines, Mapping):
            return
        reference = self._reference()
        snapshot = payload.get("_f1_snapshot") is True
        for raw_number, line in lines.items():
            number = str(raw_number)
            if not number.isdigit() or len(number) > 3 or not isinstance(line, Mapping):
                continue
            if number not in self._cars and len(self._cars) >= 32:
                continue
            car = self._cars.setdefault(number, _Car())
            if snapshot:
                car.current = _Attempt(_integer(line.get("NumberOfLaps")))
                car.previous = None
                continue
            count = _integer(line.get("NumberOfLaps"))
            if count is not None and count != car.current.lap:
                if car.current.lap is not None and count > car.current.lap:
                    car.previous = car.current
                else:
                    car.previous = None
                car.current = _Attempt(count)
            for raw_index, sector in _items(line.get("Sectors")):
                index = _integer(raw_index)
                if index not in {0, 1, 2} or not isinstance(sector, Mapping):
                    continue
                value = _seconds(sector.get("Value"))
                if value is None or sector.get("Stopped") is True:
                    continue
                attempt = car.current
                if index == 2 and 1 not in attempt.sectors and car.previous is not None:
                    attempt = car.previous
                # A late previous-lap S2/S3 cannot seed the current attempt.
                if index and index - 1 not in attempt.sectors:
                    continue
                if index == 0 and attempt.time is not None:
                    car.previous = attempt
                    car.current = attempt = _Attempt(count)
                if index == 0 and not attempt.reference_selected:
                    attempt.reference = reference
                    attempt.reference_selected = True
                attempt.sectors[index] = value
            lap_time = _seconds(line.get("LastLapTime"))
            if lap_time is not None:
                attempt = car.previous or car.current
                attempt.time = lap_time
                best = line.get("BestLapTime")
                if isinstance(best, Mapping) and _seconds(best) == lap_time:
                    attempt.official_lap = _integer(best.get("Lap"))
            for attempt in (car.previous, car.current):
                if (
                    attempt is not None
                    and attempt.lap is not None
                    and attempt.time is not None
                    and {0, 1, 2} <= attempt.sectors.keys()
                    and abs(sum(attempt.sectors.values()) - attempt.time) <= 0.006
                ):
                    self._save_profile(number, attempt)
        # Freeze attempts against the pre-frame leader before publishing a new best.
        for raw_number, line in lines.items():
            number = str(raw_number)
            if number in self._cars and isinstance(line, Mapping):
                self._merge_official(number, line)

    def _save_profile(self, number: str, attempt: _Attempt) -> None:
        lap = attempt.official_lap if attempt.official_lap is not None else attempt.lap
        if lap is None or attempt.time is None or self.part is None:
            return
        if any(
            profile.driver == number
            and profile.lap == lap
            and profile.part == self.part
            and profile.time == attempt.time
            for profile in self._profiles
        ):
            return
        self._profiles.append(
            _Profile(
                number,
                lap,
                self.part,
                attempt.time,
                tuple(attempt.sectors[index] for index in (0, 1, 2)),
                (number, attempt.time) not in self._deleted
                and (number, lap) not in self._deleted_laps,
            )
        )
        if len(self._profiles) > 512:
            self._profiles.pop(0)

    def _merge_official(self, number: str, line: Mapping[str, Any]) -> None:
        segment_best = dict(_items(line.get("BestLapTimes")))
        index = self.part - 1
        selected = segment_best.get(str(index), segment_best.get(index))
        supplied = str(index) in segment_best or index in segment_best
        if supplied:
            best = selected
        elif "BestLapTime" in line and (self.part == 1 or number in self._official):
            supplied, best = True, line["BestLapTime"]
        else:
            return
        if not supplied:
            return
        # Lap-only or flag-only corrections do not erase an authoritative time.
        previous = self._official.get(number)
        if (
            isinstance(best, Mapping)
            and "Value" not in best
            and not best.get("Deleted")
        ):
            if previous is not None and "Lap" in best:
                self._official[number] = (previous[0], _integer(best["Lap"]))
            return
        value = _seconds(best)
        if isinstance(best, Mapping) and best.get("Deleted") is True:
            value = None
        lap = _integer(best.get("Lap")) if isinstance(best, Mapping) else None
        if previous is not None and (value is None or value > previous[0] + 0.0005):
            for profile in self._profiles:
                if (
                    profile.driver == number
                    and abs(profile.time - previous[0]) < 0.0005
                ):
                    profile.valid = False
        if value is None:
            self._official.pop(number, None)
        else:
            self._official[number] = (value, lap)
            for profile in self._profiles:
                if (
                    profile.driver == number
                    and abs(profile.time - value) < 0.0005
                    and (lap is None or profile.lap == lap)
                    and (number, profile.time) not in self._deleted
                    and (number, profile.lap) not in self._deleted_laps
                ):
                    profile.valid = True

    def race_control(self, payload: Mapping[str, Any]) -> None:
        """Invalidate frozen references as soon as lap deletion is announced."""
        messages = (
            _items(payload.get("Messages"))
            if "Messages" in payload
            else ((0, payload),)
        )
        for _, item in messages:
            if not isinstance(item, Mapping):
                continue
            message = item.get("Message")
            if not isinstance(message, str):
                continue
            match = _TIME_ACTION.search(message)
            lap_match = _LAP_ACTION.search(message)
            if match is not None:
                number = match["driver"]
                value = _seconds(match["time"])
                deleted = match["action"].upper() == "DELETED"
                if value is None:
                    continue
                key = (number, value)
                if deleted:
                    self._deleted.add(key)
                else:
                    self._deleted.discard(key)
                for profile in self._profiles:
                    if profile.driver == number and abs(profile.time - value) < 0.0005:
                        profile.valid = not deleted
            elif lap_match is not None:
                number, lap = lap_match["driver"], int(lap_match["lap"])
                self._deleted_laps.add((number, lap))
                for profile in self._profiles:
                    if profile.driver == number and profile.lap == lap:
                        profile.valid = False
        # Malformed inputs cannot grow session memory without limit.
        if len(self._deleted) > 512:
            self._deleted = set(sorted(self._deleted)[-512:])
        if len(self._deleted_laps) > 512:
            self._deleted_laps = set(sorted(self._deleted_laps)[-512:])

    def snapshot(self, number: str, effort: Mapping[str, Any]) -> dict[str, Any]:
        """Project only active attempts and the classifier's completed-result hold."""
        result = {**empty_push_lap_delta(), "session_part": self.part}
        if self.supported is None:
            return result
        if self.supported is False:
            return {**result, "status": "unsupported", "reason": "session_unsupported"}
        if not effort.get("active") and effort.get("state") != "completed":
            return {**result, "reason": "no_push_lap"}
        car = self._cars.get(str(number))
        lap = effort.get("lap")
        result["lap"] = lap
        attempt = (
            next(
                (
                    item
                    for item in (car.current, car.previous)
                    if item is not None and item.lap == lap
                ),
                None,
            )
            if car
            else None
        )
        if attempt is None:
            return result
        reference = attempt.reference
        if reference is None:
            return {**result, "reason": "reference_sectors_missing"}
        if not reference.valid:
            return {
                **result,
                "status": "unavailable",
                "reason": "reference_invalidated",
            }
        if (str(number), attempt.time) in self._deleted or (
            str(number),
            lap,
        ) in self._deleted_laps:
            return {**result, "status": "unavailable", "reason": "lap_deleted"}
        result.update(
            status="available",
            reference={
                "racing_number": reference.driver,
                "lap": reference.lap,
                "time": reference.time,
            },
            reason="frozen_reference",
        )
        total, baseline = 0.0, 0.0
        for index in (0, 1, 2):
            if index not in attempt.sectors:
                break
            total += attempt.sectors[index]
            baseline += reference.sectors[index]
            if index == 2:
                if effort.get("state") != "completed" or attempt.time is None:
                    break
                total, baseline = attempt.time, reference.time
            result[f"sector_{index + 1}"] = round(total - baseline, 3)
            result["latest_sector"] = index + 1
        if effort.get("state") == "completed" and attempt.time is not None:
            result["sector_3"] = round(attempt.time - reference.time, 3)
            result["latest_sector"] = 3
        return result
