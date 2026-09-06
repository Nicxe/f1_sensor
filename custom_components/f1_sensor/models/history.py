"""Provider-neutral historical session, lap-quality, and timing models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any


def _as_float(value: object) -> float | None:
    """Return one finite floating-point value."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Mapping):
        value = value.get("Value")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if ":" in text:
            parts = text.split(":")
            try:
                seconds = float(parts[-1])
                multiplier = 60.0
                for part in reversed(parts[:-1]):
                    seconds += float(part) * multiplier
                    multiplier *= 60.0
                return seconds if math.isfinite(seconds) else None
            except ValueError:
                return None
        value = text
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _as_int(value: object) -> int | None:
    """Return one integer without accepting booleans."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _track_status_has_disruption(value: object) -> bool:
    """Return whether an F1 timing status contains SC, VSC, or red flag."""
    text = str(value or "").strip()
    return any(code in text for code in ("4", "5", "6", "7"))


@dataclass(frozen=True, slots=True)
class LapQuality:
    """Explain whether a lap is suitable for pace analysis."""

    deleted: bool | None
    deletion_reason: str | None
    clean: bool
    inferred: bool
    confidence: float
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable quality description."""
        return {
            "deleted": self.deleted,
            "deletion_reason": self.deletion_reason,
            "clean": self.clean,
            "inferred": self.inferred,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
        }


def assess_lap_quality(
    *,
    deleted: bool | None = None,
    deletion_reason: str | None = None,
    reinstated: bool = False,
    is_pit_out_lap: bool = False,
    is_pit_in_lap: bool = False,
    lap_duration: float | int | str | None = None,
    sector_durations: Sequence[float | int | str | None] = (),
    track_status: str | None = None,
    previous_track_status: str | None = None,
    inferred: bool = False,
) -> LapQuality:
    """Classify one live or replay lap using the local quality contract.

    The model is intentionally conservative. It separates source certainty from
    suitability for clean-pace analysis, and it never turns an inferred lap into
    an official fact.
    """
    effective_deleted = False if reinstated else deleted
    effective_reason = None if reinstated else (deletion_reason or None)
    reasons: list[str] = []
    confidence = 1.0

    if effective_deleted:
        reasons.append("deleted")
    if is_pit_out_lap:
        reasons.append("pit_out")
    if is_pit_in_lap:
        reasons.append("pit_in")
    if inferred:
        reasons.append("inferred")
        confidence -= 0.25

    parsed_lap = _as_float(lap_duration)
    parsed_sectors = tuple(_as_float(value) for value in sector_durations)
    if parsed_lap is None:
        reasons.append("missing_lap_time")
        confidence -= 0.15
    if len(parsed_sectors) != 3 or any(value is None for value in parsed_sectors):
        reasons.append("missing_sectors")
        confidence -= 0.1
    elif parsed_lap is not None:
        sector_sum = sum(value for value in parsed_sectors if value is not None)
        if not math.isclose(sector_sum, parsed_lap, abs_tol=0.003, rel_tol=0.0):
            reasons.append("sector_sum_mismatch")
            confidence -= 0.25

    if _track_status_has_disruption(track_status):
        reasons.append("safety_car_or_red_flag")
    if _track_status_has_disruption(previous_track_status):
        reasons.append("first_lap_after_safety_car")

    return LapQuality(
        deleted=effective_deleted,
        deletion_reason=effective_reason,
        clean=not reasons,
        inferred=bool(inferred),
        confidence=round(max(0.0, min(1.0, confidence)), 2),
        reasons=tuple(reasons),
    )


@dataclass(frozen=True, slots=True)
class SpeedTrapSet:
    """Normalized speeds at the four timing-line measurements."""

    i1: float | None = None
    i2: float | None = None
    finish: float | None = None
    straight: float | None = None

    @property
    def available(self) -> bool:
        """Return whether at least one trap value is present."""
        return any(
            value is not None
            for value in (self.i1, self.i2, self.finish, self.straight)
        )

    def as_dict(self) -> dict[str, float | None]:
        """Return stable speed-trap keys."""
        return {
            "i1": self.i1,
            "i2": self.i2,
            "finish": self.finish,
            "straight": self.straight,
        }


@dataclass(frozen=True, slots=True)
class MiniSector:
    """One provider-neutral minisector status sample."""

    sector: int
    index: int
    status: int | str | None

    def as_dict(self) -> dict[str, int | str | None]:
        """Return a JSON-serializable minisector sample."""
        return {"sector": self.sector, "index": self.index, "status": self.status}


@dataclass(frozen=True, slots=True)
class LapRecord:
    """Normalized lap data shared by history, live, and replay."""

    provider: str
    driver_number: int | None
    lap_number: int | None
    lap_duration: float | None
    sector_durations: tuple[float | None, float | None, float | None]
    speed_traps: SpeedTrapSet
    minisectors: tuple[MiniSector, ...]
    quality: LapQuality
    coverage: dict[str, str]
    source_payload: dict[str, Any]

    def as_dict(self, *, include_source: bool = False) -> dict[str, Any]:
        """Return a bounded JSON representation without raw source data by default."""
        result: dict[str, Any] = {
            "provider": self.provider,
            "driver_number": self.driver_number,
            "lap_number": self.lap_number,
            "lap_duration": self.lap_duration,
            "sector_durations": list(self.sector_durations),
            "speed_traps": self.speed_traps.as_dict(),
            "minisectors": [item.as_dict() for item in self.minisectors],
            "quality": self.quality.as_dict(),
            "coverage": dict(self.coverage),
        }
        if include_source:
            result["source_payload"] = dict(self.source_payload)
        return result


@dataclass(frozen=True, slots=True)
class HistoricalLapTiming:
    """One provider-neutral historical race-lap timing row."""

    provider: str
    driver_id: str
    lap_number: int
    position: int | None
    lap_duration: float | None

    def as_dict(self) -> dict[str, Any]:
        """Return the stable historical timing contract."""
        return {
            "provider": self.provider,
            "driver_id": self.driver_id,
            "lap_number": self.lap_number,
            "position": self.position,
            "lap_duration": self.lap_duration,
        }


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _ordered_mapping_values(value: object) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):

        def _sort_key(item: tuple[object, object]) -> tuple[int, str]:
            key = str(item[0])
            return (int(key), key) if key.isdecimal() else (10_000, key)

        return [
            item
            for _, item in sorted(value.items(), key=_sort_key)
            if isinstance(item, Mapping)
        ]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _live_sectors(
    payload: Mapping[str, Any],
) -> tuple[tuple[float | None, float | None, float | None], tuple[MiniSector, ...]]:
    sector_items = _ordered_mapping_values(payload.get("Sectors"))
    durations: list[float | None] = []
    minisectors: list[MiniSector] = []
    for sector_index in range(3):
        sector = sector_items[sector_index] if sector_index < len(sector_items) else {}
        durations.append(_as_float(sector.get("Value")))
        for mini_index, segment in enumerate(
            _ordered_mapping_values(sector.get("Segments"))
        ):
            minisectors.append(
                MiniSector(
                    sector=sector_index + 1,
                    index=mini_index,
                    status=segment.get("Status"),
                )
            )
    return (durations[0], durations[1], durations[2]), tuple(minisectors)


def normalize_lap_record(
    payload: Mapping[str, Any],
    *,
    provider: str,
    session_type: str | None = None,
    previous_track_status: str | None = None,
) -> LapRecord:
    """Normalize F1 live or replay timing into one lap model."""
    source = dict(payload)
    sectors, minisectors = _live_sectors(payload)
    speed_data = _mapping(payload.get("Speeds"))
    speeds = SpeedTrapSet(
        i1=_as_float(speed_data.get("I1")),
        i2=_as_float(speed_data.get("I2")),
        finish=_as_float(speed_data.get("FL")),
        straight=_as_float(speed_data.get("ST")),
    )
    lap_duration = _as_float(payload.get("LastLapTime") or payload.get("LapTime"))
    driver_number = _as_int(payload.get("RacingNumber") or payload.get("DriverNumber"))
    lap_number = _as_int(payload.get("NumberOfLaps") or payload.get("LapNumber"))
    is_pit_out_lap = bool(payload.get("IsPitOutLap") or payload.get("is_pit_out_lap"))
    minisector_coverage = "available" if minisectors else "no_data"

    quality = assess_lap_quality(
        deleted=payload.get("deleted", payload.get("Deleted")),
        deletion_reason=payload.get("deletion_reason", payload.get("DeletedReason")),
        reinstated=bool(payload.get("reinstated", payload.get("Reinstated"))),
        is_pit_out_lap=is_pit_out_lap,
        is_pit_in_lap=bool(payload.get("is_pit_in_lap", payload.get("IsPitInLap"))),
        lap_duration=lap_duration,
        sector_durations=sectors,
        track_status=payload.get("track_status", payload.get("TrackStatus")),
        previous_track_status=previous_track_status,
        inferred=bool(payload.get("inferred", payload.get("Inferred"))),
    )
    return LapRecord(
        provider=provider,
        driver_number=driver_number,
        lap_number=lap_number,
        lap_duration=lap_duration,
        sector_durations=sectors,
        speed_traps=speeds,
        minisectors=minisectors,
        quality=quality,
        coverage={
            "speed_traps": "available" if speeds.available else "no_data",
            "minisectors": minisector_coverage,
        },
        source_payload=source,
    )
