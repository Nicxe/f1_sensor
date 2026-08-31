"""Bounded Phase 4 timeline, strategy, and race analysis."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import math
from statistics import median
from typing import Any

from .history import LapAnalysisStore

PHASE4_ANALYSIS_STREAMS = frozenset(
    {
        "DriverList",
        "PitStopSeries",
        "RaceControlMessages",
        "SessionInfo",
        "SessionStatus",
        "TeamRadio",
        "TimingAppData",
        "TimingData",
        "TrackStatus",
        "WeatherData",
    }
)
MAX_TIMELINE_EVENTS = 500
MAX_STRATEGY_LAPS = 2200
MAX_EXCHANGES = 120
MAX_BATTLES = 60
BATTLE_GAP_SECONDS = 1.0
OVERTAKE_GAP_SECONDS = 2.0
BATTLE_START_FRAMES = 3
BATTLE_END_FRAMES = 2
POSITION_EXCHANGE_CONFIRM_FRAMES = 2


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _items(value: object) -> list[tuple[str, Mapping[str, Any]]]:
    if isinstance(value, Mapping):
        return [
            (str(key), item) for key, item in value.items() if isinstance(item, Mapping)
        ]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [
            (str(index), item)
            for index, item in enumerate(value)
            if isinstance(item, Mapping)
        ]
    return []


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _value_text(value: object) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("Value")
    return _text(value)


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Mapping):
        value = value.get("Value")
    with suppress(TypeError, ValueError):
        return int(str(value).strip())
    return None


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Mapping):
        value = value.get("Value")
    text = str(value).strip()
    if not text:
        return None
    with suppress(TypeError, ValueError):
        if text.startswith("+"):
            text = text[1:]
        if ":" in text:
            minutes, seconds = text.rsplit(":", 1)
            parsed = int(minutes) * 60 + float(seconds)
        else:
            parsed = float(text.rstrip("s"))
        return parsed if math.isfinite(parsed) else None
    return None


def _utc_text(payload: Mapping[str, Any]) -> str | None:
    for key in ("Utc", "utc", "Timestamp", "timestamp", "Date"):
        value = _text(payload.get(key))
        if value:
            return value
    return None


def _stable_id(*parts: object) -> str:
    value = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(value.encode(), usedforsecurity=False).hexdigest()[:20]


def _deep_merge(target: dict[str, Any], delta: Mapping[str, Any]) -> None:
    for key, value in delta.items():
        current = target.get(str(key))
        if isinstance(current, dict) and isinstance(value, Mapping):
            _deep_merge(current, value)
        else:
            target[str(key)] = deepcopy(value)


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    """One provider-neutral timeline event."""

    event_id: str
    revision: int
    sequence: int
    provider: str
    session_id: str | None
    occurred_at: str | None
    offset_ms: int | None
    category: str
    kind: str
    title: str
    description: str | None = None
    driver_numbers: tuple[int, ...] = ()
    lap_number: int | None = None
    severity: str = "info"
    confidence: float = 1.0
    final: bool = False
    supporting_signals: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return the stable WebSocket event contract."""
        return {
            "event_id": self.event_id,
            "revision": self.revision,
            "sequence": self.sequence,
            "provider": self.provider,
            "session_id": self.session_id,
            "occurred_at": self.occurred_at,
            "offset_ms": self.offset_ms,
            "category": self.category,
            "kind": self.kind,
            "title": self.title,
            "description": self.description,
            "driver_numbers": list(self.driver_numbers),
            "lap_number": self.lap_number,
            "severity": self.severity,
            "confidence": round(max(0.0, min(1.0, self.confidence)), 2),
            "final": self.final,
            "supporting_signals": list(self.supporting_signals),
        }


class UnifiedTimelineStore:
    """Deduplicate and revise bounded live, replay, or history events."""

    def __init__(self, *, max_events: int = MAX_TIMELINE_EVENTS) -> None:
        self._max_events = max(20, int(max_events))
        self._events: OrderedDict[str, TimelineEvent] = OrderedDict()
        self._sequence = 0

    def upsert(self, event: TimelineEvent) -> TimelineEvent:
        """Insert an event or revise its existing contract."""
        current = self._events.get(event.event_id)
        if current is not None:
            candidate = replace(
                event,
                revision=current.revision,
                sequence=current.sequence,
            )
            if candidate == current:
                return current
            event = replace(
                event,
                revision=current.revision + 1,
                sequence=current.sequence,
            )
        else:
            self._sequence += 1
            event = replace(event, revision=1, sequence=self._sequence)
        self._events[event.event_id] = event
        self._events.move_to_end(event.event_id)
        while len(self._events) > self._max_events:
            self._events.popitem(last=False)
        return event

    def clear(self) -> None:
        """Remove events while keeping sequence monotonic."""
        self._events.clear()

    def snapshot(self) -> list[dict[str, Any]]:
        """Return events in their stable sequence order."""
        return [event.as_dict() for event in self._events.values()]


def _linear_slope(samples: list[tuple[int, float]]) -> float | None:
    if len(samples) < 3:
        return None
    count = len(samples)
    x_mean = sum(item[0] for item in samples) / count
    y_mean = sum(item[1] for item in samples) / count
    denominator = sum((item[0] - x_mean) ** 2 for item in samples)
    if denominator <= 0:
        return None
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in samples)
    return round(numerator / denominator, 4)


def _linear_fit(samples: Sequence[tuple[float, float]]) -> tuple[float, float] | None:
    """Return an intercept and slope for a bounded set of numeric samples."""
    if len(samples) < 3:
        return None
    count = len(samples)
    x_mean = sum(item[0] for item in samples) / count
    y_mean = sum(item[1] for item in samples) / count
    denominator = sum((item[0] - x_mean) ** 2 for item in samples)
    if denominator <= 0:
        return None
    slope = sum((x - x_mean) * (y - y_mean) for x, y in samples) / denominator
    return y_mean - slope * x_mean, slope


def _compound_crossover_indications(
    samples: Mapping[str, Sequence[tuple[float, float]]],
) -> list[dict[str, Any]]:
    """Estimate compound pace crossovers only inside observed tyre-age ranges."""
    models: dict[str, tuple[float, float, float, float, int]] = {}
    for compound, values in samples.items():
        fit = _linear_fit(values)
        if fit is None:
            continue
        ages = [item[0] for item in values]
        models[compound] = (*fit, min(ages), max(ages), len(values))

    indications: list[dict[str, Any]] = []
    compounds = sorted(models)
    for index, first in enumerate(compounds):
        for second in compounds[index + 1 :]:
            first_intercept, first_slope, first_min, first_max, first_count = models[
                first
            ]
            second_intercept, second_slope, second_min, second_max, second_count = (
                models[second]
            )
            slope_delta = first_slope - second_slope
            if abs(slope_delta) < 0.001:
                continue
            crossover_age = (second_intercept - first_intercept) / slope_delta
            observed_min = max(first_min, second_min)
            observed_max = min(first_max, second_max)
            if crossover_age < observed_min or crossover_age > observed_max:
                continue
            indications.append(
                {
                    "compounds": [first, second],
                    "estimated_tyre_age_laps": round(crossover_age, 1),
                    "observed_age_range": [
                        round(observed_min, 1),
                        round(observed_max, 1),
                    ],
                    "pace_at_crossover": round(
                        first_intercept + first_slope * crossover_age, 3
                    ),
                    "confidence": round(
                        min(1.0, min(first_count, second_count) / 8), 2
                    ),
                    "status": "observed_range_estimate",
                }
            )
    return indications


def _position_at(
    laps: Sequence[Mapping[str, Any]], driver: int, lap_number: int
) -> int | None:
    return next(
        (
            position
            for item in laps
            if _as_int(item.get("driver_number")) == driver
            and _as_int(item.get("lap_number")) == lap_number
            and (position := _as_int(item.get("position"))) is not None
        ),
        None,
    )


def _strategy_outcomes(
    laps: Sequence[Mapping[str, Any]],
    driver_meta: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Classify teammate pit-cycle outcomes when order is observable."""
    driver_laps: dict[int, list[Mapping[str, Any]]] = {}
    for item in laps:
        driver = _as_int(item.get("driver_number"))
        lap_number = _as_int(item.get("lap_number"))
        if driver is not None and lap_number is not None:
            driver_laps.setdefault(driver, []).append(item)
    for values in driver_laps.values():
        values.sort(key=lambda item: _as_int(item.get("lap_number")) or 0)

    transitions: dict[int, list[int]] = {}
    for driver, values in driver_laps.items():
        previous_stint: int | None = None
        for item in values:
            stint = _as_int(item.get("stint_index")) or 0
            lap_number = _as_int(item.get("lap_number"))
            if previous_stint is not None and stint > previous_stint and lap_number:
                transitions.setdefault(driver, []).append(lap_number)
            previous_stint = stint

    teams: dict[str, list[int]] = {}
    for driver in driver_laps:
        team = _text(driver_meta.get(str(driver), {}).get("team"))
        if team:
            teams.setdefault(team, []).append(driver)

    outcomes: list[dict[str, Any]] = []
    seen_cycles: set[tuple[int, int, int, int]] = set()
    for team, drivers in sorted(teams.items()):
        if len(drivers) != 2:
            continue
        first_driver, second_driver = sorted(drivers)
        for first_stop in transitions.get(first_driver, []):
            candidates = [
                stop
                for stop in transitions.get(second_driver, [])
                if 1 <= abs(stop - first_stop) <= 5
            ]
            if not candidates:
                continue
            second_stop = min(candidates, key=lambda stop: abs(stop - first_stop))
            cycle = (first_driver, second_driver, first_stop, second_stop)
            if cycle in seen_cycles:
                continue
            seen_cycles.add(cycle)
            earlier_driver, later_driver = (
                (first_driver, second_driver)
                if first_stop < second_stop
                else (second_driver, first_driver)
            )
            before_lap = min(first_stop, second_stop) - 1
            after_lap = max(first_stop, second_stop) + 1
            earlier_before = _position_at(laps, earlier_driver, before_lap)
            later_before = _position_at(laps, later_driver, before_lap)
            earlier_after = _position_at(laps, earlier_driver, after_lap)
            later_after = _position_at(laps, later_driver, after_lap)
            if None in (earlier_before, later_before, earlier_after, later_after):
                continue
            before_order = earlier_before < later_before
            after_order = earlier_after < later_after
            if before_order == after_order:
                result = "order_held"
                successful_driver = None
            elif not before_order and after_order:
                result = "undercut_succeeded"
                successful_driver = earlier_driver
            else:
                result = "overcut_succeeded"
                successful_driver = later_driver
            outcomes.append(
                {
                    "team": team,
                    "drivers": [earlier_driver, later_driver],
                    "earlier_stop_driver": earlier_driver,
                    "later_stop_driver": later_driver,
                    "stop_laps": {
                        str(earlier_driver): min(first_stop, second_stop),
                        str(later_driver): max(first_stop, second_stop),
                    },
                    "positions_before": {
                        str(earlier_driver): earlier_before,
                        str(later_driver): later_before,
                    },
                    "positions_after": {
                        str(earlier_driver): earlier_after,
                        str(later_driver): later_after,
                    },
                    "result": result,
                    "successful_driver": successful_driver,
                    "confidence": 0.8,
                    "supporting_signals": [
                        "stint_transition",
                        "lap_position_before",
                        "lap_position_after",
                    ],
                }
            )
    return outcomes


def _confidence_label(value: float) -> str:
    if value >= 0.8:
        return "high"
    if value >= 0.55:
        return "medium"
    return "low"


def analyze_strategy(
    laps: Sequence[Mapping[str, Any]],
    drivers: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Derive conservative stint pace, degradation, and teammate comparisons."""
    driver_meta = drivers or {}
    grouped: dict[tuple[int, int], list[Mapping[str, Any]]] = {}
    for lap in laps:
        driver = _as_int(lap.get("driver_number"))
        lap_number = _as_int(lap.get("lap_number"))
        duration = _as_float(lap.get("lap_duration"))
        if driver is None or lap_number is None or duration is None:
            continue
        stint_index = _as_int(lap.get("stint_index")) or 0
        grouped.setdefault((driver, stint_index), []).append(lap)

    stints: list[dict[str, Any]] = []
    driver_adjusted: dict[int, list[float]] = {}
    compound_times: dict[str, list[float]] = {}
    compound_age_samples: dict[str, list[tuple[float, float]]] = {}
    observed_compounds: set[str] = set()
    excluded_reason_counts: dict[str, int] = {}
    for (driver, stint_index), stint_laps in sorted(grouped.items()):
        ordered = sorted(
            stint_laps, key=lambda item: _as_int(item.get("lap_number")) or 0
        )
        raw_samples = [
            duration
            for item in ordered
            if (duration := _as_float(item.get("lap_duration"))) is not None
        ]
        clean_samples: list[tuple[int, float]] = []
        quality_confidence: list[float] = []
        stint_excluded_reason_counts: dict[str, int] = {}
        for item in ordered:
            quality = _mapping(item.get("quality"))
            duration = _as_float(item.get("lap_duration"))
            lap_number = _as_int(item.get("lap_number"))
            if (
                quality.get("clean") is not True
                or duration is None
                or lap_number is None
            ):
                reasons = quality.get("reasons")
                normalized_reasons = (
                    [str(reason) for reason in reasons if _text(reason)]
                    if isinstance(reasons, Sequence)
                    and not isinstance(reasons, (str, bytes))
                    else ["quality_not_clean"]
                )
                for reason in normalized_reasons or ["quality_not_clean"]:
                    stint_excluded_reason_counts[reason] = (
                        stint_excluded_reason_counts.get(reason, 0) + 1
                    )
                    excluded_reason_counts[reason] = (
                        excluded_reason_counts.get(reason, 0) + 1
                    )
                continue
            clean_samples.append((lap_number, duration))
            quality_confidence.append(_as_float(quality.get("confidence")) or 0.0)
        adjusted = [item[1] for item in clean_samples]
        compound = (_text(ordered[-1].get("compound")) or "UNKNOWN").upper()
        if compound != "UNKNOWN":
            observed_compounds.add(compound)
        sample_factor = min(1.0, len(adjusted) / 5)
        quality_factor = (
            sum(quality_confidence) / len(quality_confidence)
            if quality_confidence
            else 0.0
        )
        confidence = round(sample_factor * quality_factor, 2)
        raw_median = round(float(median(raw_samples)), 3) if raw_samples else None
        adjusted_median = round(float(median(adjusted)), 3) if adjusted else None
        if adjusted:
            driver_adjusted.setdefault(driver, []).extend(adjusted)
            if compound != "UNKNOWN":
                compound_times.setdefault(compound, []).extend(adjusted)
                first_lap_number = _as_int(ordered[0].get("lap_number")) or 0
                starting_age = _as_int(ordered[0].get("tyre_age_at_start")) or 0
                compound_age_samples.setdefault(compound, []).extend(
                    (
                        float(starting_age + lap_number - first_lap_number),
                        duration,
                    )
                    for lap_number, duration in clean_samples
                )
        stints.append(
            {
                "driver_number": driver,
                "driver_name": _text(driver_meta.get(str(driver), {}).get("name")),
                "team": _text(driver_meta.get(str(driver), {}).get("team")),
                "stint_index": stint_index,
                "compound": compound,
                "first_lap": _as_int(ordered[0].get("lap_number")),
                "last_lap": _as_int(ordered[-1].get("lap_number")),
                "tyre_age_at_start": _as_int(ordered[0].get("tyre_age_at_start")),
                "sample_count": len(adjusted),
                "raw_sample_count": len(raw_samples),
                "raw_median_pace": raw_median,
                "adjusted_median_clean_pace": adjusted_median,
                "degradation_seconds_per_lap": _linear_slope(clean_samples),
                "confidence": confidence,
                "confidence_label": _confidence_label(confidence),
                "excluded_laps": max(0, len(raw_samples) - len(adjusted)),
                "excluded_reason_counts": dict(
                    sorted(stint_excluded_reason_counts.items())
                ),
            }
        )

    for index, stint in enumerate(stints):
        previous = next(
            (
                candidate
                for candidate in reversed(stints[:index])
                if candidate["driver_number"] == stint["driver_number"]
            ),
            None,
        )
        first_lap = next(
            (
                lap
                for lap in laps
                if _as_int(lap.get("driver_number")) == stint["driver_number"]
                and _as_int(lap.get("lap_number")) == stint["first_lap"]
            ),
            None,
        )
        first_duration = _as_float(first_lap.get("lap_duration")) if first_lap else None
        previous_pace = previous.get("adjusted_median_clean_pace") if previous else None
        stint["pit_loss_seconds"] = (
            round(first_duration - previous_pace, 3)
            if first_duration is not None and previous_pace is not None
            else None
        )

    compound_comparison = [
        {
            "compound": compound,
            "median_clean_pace": round(float(median(values)), 3),
            "sample_count": len(values),
            "confidence": round(min(1.0, len(values) / 8), 2),
        }
        for compound, values in sorted(compound_times.items())
    ]
    compound_comparison.sort(key=lambda item: item["median_clean_pace"])
    if compound_comparison:
        fastest = compound_comparison[0]["median_clean_pace"]
        for item in compound_comparison:
            item["delta_to_fastest"] = round(item["median_clean_pace"] - fastest, 3)

    teammate_comparisons: list[dict[str, Any]] = []
    teams: dict[str, list[int]] = {}
    for driver in driver_adjusted:
        team = _text(driver_meta.get(str(driver), {}).get("team"))
        if team:
            teams.setdefault(team, []).append(driver)
    for team, team_drivers in sorted(teams.items()):
        if len(team_drivers) != 2:
            continue
        first, second = sorted(team_drivers)
        first_pace = float(median(driver_adjusted[first]))
        second_pace = float(median(driver_adjusted[second]))
        teammate_comparisons.append(
            {
                "team": team,
                "drivers": [first, second],
                "median_clean_pace": {
                    str(first): round(first_pace, 3),
                    str(second): round(second_pace, 3),
                },
                "delta_seconds": round(abs(first_pace - second_pace), 3),
                "faster_driver": first if first_pace <= second_pace else second,
                "confidence": round(
                    min(
                        1.0,
                        min(len(driver_adjusted[first]), len(driver_adjusted[second]))
                        / 5,
                    ),
                    2,
                ),
            }
        )

    raw_lap_count = sum(item["raw_sample_count"] for item in stints)
    clean_lap_count = sum(item["sample_count"] for item in stints)
    return {
        "status": "ready" if clean_lap_count else "waiting_for_clean_laps",
        "analysis_type": "local_estimate",
        "coverage": {
            "raw_laps": raw_lap_count,
            "clean_laps": clean_lap_count,
            "excluded_laps": max(0, raw_lap_count - clean_lap_count),
            "observed_compounds": sorted(observed_compounds),
            "excluded_reason_counts": dict(sorted(excluded_reason_counts.items())),
        },
        "stints": stints,
        "compound_comparison": compound_comparison,
        "compound_crossover_indications": _compound_crossover_indications(
            compound_age_samples
        ),
        "teammate_comparisons": teammate_comparisons,
        "undercut_overcut_outcomes": _strategy_outcomes(laps, driver_meta),
        "assumptions": [
            "Clean laps exclude pit in/out, deleted or inaccurate laps, missing sectors, SC/VSC and the first relevant post-SC lap",
            "Pace and degradation are local estimates, not official strategy or predictions",
        ],
    }


class Phase4AnalysisStore:
    """Accumulate Phase 4 products from the shared live or replay bus."""

    def __init__(
        self,
        bus: Any,
        lap_analysis: LapAnalysisStore,
        *,
        source_provider: Callable[[], str],
    ) -> None:
        self._bus = bus
        self._lap_analysis = lap_analysis
        self._source_provider = source_provider
        self._timeline = UnifiedTimelineStore()
        self._session_id: str | None = None
        self._session_name: str | None = None
        self._session_status: str | None = None
        self._track_status: str | None = None
        self._drivers: dict[str, dict[str, Any]] = {}
        self._timing: dict[str, dict[str, Any]] = {}
        self._timing_app: dict[str, dict[str, Any]] = {}
        self._strategy_laps: OrderedDict[tuple[int, int], dict[str, Any]] = (
            OrderedDict()
        )
        self._previous_positions: dict[int, int] = {}
        self._position_candidate: dict[int, int] = {}
        self._position_candidate_frames = 0
        self._exchange_history: list[dict[str, Any]] = []
        self._exchange_total = 0
        self._battle_counts: dict[tuple[int, int], int] = {}
        self._battle_end_counts: dict[tuple[int, int], int] = {}
        self._active_battles: dict[tuple[int, int], dict[str, Any]] = {}
        self._battle_history: list[dict[str, Any]] = []
        self._pit_context: dict[int, set[int]] = {}
        self._penalty_context: dict[int, set[int]] = {}
        self._observed_streams: set[str] = set()
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[Callable[[], None]] = []
        self._updates = 0
        self._attach()

    def _attach(self) -> None:
        callbacks = {
            "DriverList": self._on_driver_list,
            "PitStopSeries": self._on_pit_stops,
            "RaceControlMessages": self._on_race_control,
            "SessionInfo": self._on_session_info,
            "SessionStatus": self._on_session_status,
            "TeamRadio": self._on_team_radio,
            "TimingAppData": self._on_timing_app,
            "TimingData": self._on_timing_data,
            "TrackStatus": self._on_track_status,
            "WeatherData": self._on_weather,
        }
        for stream, handler in callbacks.items():
            with suppress(Exception):
                self._unsubs.append(
                    self._bus.subscribe(
                        stream,
                        lambda payload, stream=stream, handler=handler: self._dispatch(
                            stream, handler, payload
                        ),
                    )
                )

    def _dispatch(
        self,
        stream: str,
        handler: Callable[[Any], None],
        payload: Any,
    ) -> None:
        self._observed_streams.add(stream)
        handler(payload)
        self._updates += 1
        for listener in tuple(self._listeners):
            with suppress(Exception):
                listener()

    def add_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Subscribe a WebSocket broadcast hub to analysis updates."""
        self._listeners.append(callback)

        def _unsubscribe() -> None:
            with suppress(ValueError):
                self._listeners.remove(callback)

        return _unsubscribe

    def _provider(self) -> str:
        return self._source_provider()

    def _event(
        self,
        *,
        identity: str,
        category: str,
        kind: str,
        title: str,
        payload: Mapping[str, Any] | None = None,
        description: str | None = None,
        drivers: tuple[int, ...] = (),
        lap_number: int | None = None,
        severity: str = "info",
        confidence: float = 1.0,
        signals: tuple[str, ...] = (),
        final: bool = False,
    ) -> TimelineEvent:
        source = payload or {}
        return self._timeline.upsert(
            TimelineEvent(
                event_id=_stable_id(self._session_id, category, identity),
                revision=0,
                sequence=0,
                provider=self._provider(),
                session_id=self._session_id,
                occurred_at=_utc_text(source),
                offset_ms=_as_int(source.get("offset_ms")),
                category=category,
                kind=kind,
                title=title,
                description=description,
                driver_numbers=drivers,
                lap_number=lap_number,
                severity=severity,
                confidence=confidence,
                final=final,
                supporting_signals=signals,
            )
        )

    def _reset_session(self) -> None:
        self._timeline.clear()
        self._session_status = None
        self._track_status = None
        self._drivers.clear()
        self._timing.clear()
        self._timing_app.clear()
        self._strategy_laps.clear()
        self._previous_positions.clear()
        self._position_candidate.clear()
        self._position_candidate_frames = 0
        self._exchange_history.clear()
        self._exchange_total = 0
        self._battle_counts.clear()
        self._battle_end_counts.clear()
        self._active_battles.clear()
        self._battle_history.clear()
        self._pit_context.clear()
        self._penalty_context.clear()
        self._observed_streams.clear()

    def reset_for_replay(self) -> None:
        """Reset all accumulated state before replay playback is rebuilt."""
        self._reset_session()
        self._session_id = None
        self._session_name = None

    def _on_session_info(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        meeting = _mapping(payload.get("Meeting"))
        parts = (
            _text(meeting.get("Key") or meeting.get("Id")),
            _text(
                payload.get("Key") or payload.get("SessionKey") or payload.get("Path")
            ),
            _text(payload.get("Name")),
        )
        session_id = ":".join(part for part in parts if part)
        restarting_same_replay = (
            self._provider() == "replay"
            and session_id
            and session_id == self._session_id
            and _text(payload.get("SessionStatus")) == "Inactive"
            and self._session_status is not None
        )
        if restarting_same_replay:
            self._reset_session()
            self._lap_analysis.reset_session()
            self._observed_streams.add("SessionInfo")
        if session_id and session_id != self._session_id:
            if self._session_id is not None:
                self._reset_session()
                self._observed_streams.add("SessionInfo")
            self._session_id = session_id
        self._session_name = _text(payload.get("Name") or payload.get("Type"))
        if self._session_id:
            self._event(
                identity="session_info",
                category="session",
                kind="session_available",
                title=self._session_name or "Session available",
                payload=payload,
                description=_text(meeting.get("Name") or meeting.get("OfficialName")),
            )

    def _on_session_status(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        status = _text(payload.get("Status") or payload.get("Message"))
        if status is None or status == self._session_status:
            return
        self._session_status = status
        final = status in {"Finished", "Finalised", "Ends"}
        self._event(
            identity=f"status:{status}",
            category="session",
            kind="session_status",
            title=status,
            payload=payload,
            severity="success" if status in {"Started", "Green"} else "info",
            final=final,
        )
        if final:
            self._close_active_battles_for_session_end()

    def _on_track_status(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        status = _text(payload.get("Status") or payload.get("Message"))
        if status is None or status == self._track_status:
            return
        self._track_status = status
        disrupted = status in {"2", "4", "5", "6", "7"}
        self._event(
            identity=f"track:{status}:{_utc_text(payload)}",
            category="track_status",
            kind="track_status_changed",
            title=_text(payload.get("Message")) or f"Track status {status}",
            payload=payload,
            severity="warning" if disrupted else "success",
        )

    def _on_driver_list(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        source = payload.get("Lines", payload)
        for key, item in _items(source):
            driver = _as_int(item.get("RacingNumber") or key)
            if driver is None:
                continue
            target = self._drivers.setdefault(
                str(driver),
                {
                    "driver_number": driver,
                    "name": None,
                    "tla": None,
                    "team": None,
                    "team_color": None,
                },
            )
            updates = {
                "name": _text(
                    item.get("FullName") or item.get("BroadcastName") or item.get("Tla")
                ),
                "tla": _text(item.get("Tla")),
                "team": _text(item.get("TeamName")),
                "team_color": _text(item.get("TeamColour")),
            }
            for name, value in updates.items():
                if value is not None:
                    target[name] = value

    def _on_timing_app(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        for key, item in _items(payload.get("Lines")):
            target = self._timing_app.setdefault(key, {})
            _deep_merge(target, item)

    def _on_timing_data(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        updated_drivers: list[int] = []
        for key, item in _items(payload.get("Lines")):
            target = self._timing.setdefault(key, {})
            _deep_merge(target, item)
            if (driver := _as_int(key)) is not None:
                updated_drivers.append(driver)
        self._capture_strategy_laps(updated_drivers)
        self._detect_position_exchanges()
        self._detect_battles()

    def _current_stint(self, driver: int) -> tuple[int, Mapping[str, Any]]:
        app = self._timing_app.get(str(driver), {})
        stints = _items(app.get("Stints"))
        if not stints:
            return 0, {}
        key, stint = stints[-1]
        return _as_int(key) or 0, stint

    def _capture_strategy_laps(self, drivers: Sequence[int] | None = None) -> None:
        if drivers is None:
            laps = self._lap_analysis.snapshot().get("laps", [])
        else:
            laps = []
            for driver in set(drivers):
                timing = self._timing.get(str(driver), {})
                lap_number = _as_int(timing.get("NumberOfLaps"))
                if lap_number is None:
                    continue
                lap = self._lap_analysis.get_lap(driver, lap_number)
                if lap is not None:
                    laps.append(lap)
        for lap in laps:
            if not isinstance(lap, Mapping):
                continue
            driver = _as_int(lap.get("driver_number"))
            lap_number = _as_int(lap.get("lap_number"))
            if driver is None or lap_number is None:
                continue
            timing = self._timing.get(str(driver), {})
            key = (driver, lap_number)
            existing = self._strategy_laps.get(key)
            if existing is None:
                stint_index, stint = self._current_stint(driver)
                compound = _text(stint.get("Compound"))
                tyre_age_at_start = _as_int(stint.get("StartLaps"))
                position = _as_int(timing.get("Position"))
            else:
                stint_index = _as_int(existing.get("stint_index")) or 0
                compound = _text(existing.get("compound"))
                tyre_age_at_start = _as_int(existing.get("tyre_age_at_start"))
                position = _as_int(existing.get("position"))
            lap_contract = dict(lap)
            lap_contract.pop("source_payload", None)
            record = {
                **lap_contract,
                "stint_index": stint_index,
                "compound": compound,
                "tyre_age_at_start": tyre_age_at_start,
                "position": position,
            }
            is_new = key not in self._strategy_laps
            self._strategy_laps[key] = record
            self._strategy_laps.move_to_end(key)
            while len(self._strategy_laps) > MAX_STRATEGY_LAPS:
                self._strategy_laps.popitem(last=False)
            if is_new:
                quality = _mapping(record.get("quality"))
                self._event(
                    identity=f"lap:{driver}:{lap_number}",
                    category="lap",
                    kind="lap_completed",
                    title=f"Car {driver} completed lap {lap_number}",
                    drivers=(driver,),
                    lap_number=lap_number,
                    confidence=_as_float(quality.get("confidence")) or 0.0,
                    signals=("TimingData",),
                )

    def _on_pit_stops(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        source = payload.get("PitTimes", payload.get("Lines", {}))
        for driver_key, driver_entries in _items(source):
            driver = _as_int(driver_key)
            if driver is None:
                continue
            for item_key, item in _items(driver_entries):
                pit = _mapping(item.get("PitStop")) or item
                lap = _as_int(pit.get("Lap") or item.get("Lap"))
                if lap is not None:
                    self._pit_context.setdefault(driver, set()).add(lap)
                self._event(
                    identity=f"pit:{driver}:{lap}:{item_key}",
                    category="pit",
                    kind="pit_stop_completed",
                    title=f"Car {driver} pit stop",
                    payload=item,
                    description=_text(pit.get("Duration") or item.get("Duration")),
                    drivers=(driver,),
                    lap_number=lap,
                    confidence=0.95,
                    signals=("PitStopSeries",),
                )

    def _on_race_control(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        messages = payload.get("Messages")
        entries = _items(messages) if messages is not None else [("0", payload)]
        for key, item in entries:
            message = _text(item.get("Message") or item.get("message"))
            if not message:
                continue
            upper = message.upper()
            drivers = tuple(
                sorted(
                    {
                        parsed
                        for token in upper.replace("-", " ").split()
                        if token.isdecimal()
                        and (parsed := _as_int(token)) is not None
                        and 0 < parsed < 100
                    }
                )
            )[:4]
            if any(word in upper for word in ("PENALTY", "INVESTIGATION", "NOTED")):
                lap = _as_int(item.get("Lap"))
                if lap is not None:
                    for driver in drivers:
                        self._penalty_context.setdefault(driver, set()).add(lap)
            if "DELETED" in upper:
                kind = "lap_deleted"
                category = "lap_control"
                severity = "warning"
            elif "REINSTATED" in upper:
                kind = "lap_reinstated"
                category = "lap_control"
                severity = "success"
            elif "PENALTY" in upper:
                kind = "penalty"
                category = "investigation"
                severity = "warning"
            else:
                kind = "race_control_message"
                category = "race_control"
                severity = "info"
            self._event(
                identity=f"rc:{item.get('Id') or item.get('id') or key}:{_utc_text(item)}:{message}",
                category=category,
                kind=kind,
                title=message,
                payload=item,
                drivers=drivers,
                lap_number=_as_int(item.get("Lap")),
                severity=severity,
                signals=("RaceControlMessages",),
            )
        self._capture_strategy_laps()

    def _on_weather(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        rainfall = _text(payload.get("Rainfall"))
        if rainfall is None:
            return
        self._event(
            identity=f"weather:rain:{rainfall}",
            category="weather",
            kind="rainfall_changed",
            title="Rain detected"
            if rainfall not in {"0", "False", "false"}
            else "Rain cleared",
            payload=payload,
            description=f"Rainfall: {rainfall}",
            severity="warning" if rainfall not in {"0", "False", "false"} else "info",
            signals=("WeatherData",),
        )

    def _on_team_radio(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        captures = payload.get("Captures", payload.get("Lines"))
        for key, item in _items(captures):
            driver = _as_int(item.get("RacingNumber"))
            self._event(
                identity=f"radio:{key}:{_utc_text(item)}",
                category="radio",
                kind="team_radio_available",
                title=f"Team radio available{f' for car {driver}' if driver else ''}",
                payload=item,
                drivers=(driver,) if driver else (),
                confidence=1.0,
                signals=("TeamRadio",),
            )

    def _position_snapshot(self) -> dict[int, int]:
        positions: dict[int, int] = {}
        for driver_key, state in self._timing.items():
            driver = _as_int(driver_key)
            position = _as_int(state.get("Position"))
            if driver is not None and position is not None and position > 0:
                positions[driver] = position
        return positions

    @staticmethod
    def _has_lap_context(
        context: Mapping[int, set[int]], driver: int, lap_number: int | None
    ) -> bool:
        if lap_number is None:
            return False
        return any(
            abs(context_lap - lap_number) <= 1
            for context_lap in context.get(driver, ())
        )

    def _detect_position_exchanges(self) -> None:
        current = self._position_snapshot()
        if len(set(current.values())) != len(current):
            return
        if len(current) < 2:
            return
        if len(self._previous_positions) < 2:
            self._previous_positions = current
            return
        if current == self._previous_positions:
            self._position_candidate.clear()
            self._position_candidate_frames = 0
            return
        if current == self._position_candidate:
            self._position_candidate_frames += 1
        else:
            self._position_candidate = dict(current)
            self._position_candidate_frames = 1
        if self._position_candidate_frames < POSITION_EXCHANGE_CONFIRM_FRAMES:
            return

        previous = self._previous_positions
        drivers = sorted(set(current) & set(previous))
        for index, first in enumerate(drivers):
            for second in drivers[index + 1 :]:
                before = previous[first] - previous[second]
                after = current[first] - current[second]
                if before == 0 or after == 0 or before * after >= 0:
                    continue
                changed = first if before > 0 and after < 0 else second
                first_laps = _as_int(
                    self._timing.get(str(first), {}).get("NumberOfLaps")
                )
                second_laps = _as_int(
                    self._timing.get(str(second), {}).get("NumberOfLaps")
                )
                if (
                    first_laps is None
                    or first_laps <= 0
                    or second_laps is None
                    or second_laps <= 0
                ):
                    continue
                first_state = self._timing.get(str(first), {})
                second_state = self._timing.get(str(second), {})
                pit = self._has_lap_context(
                    self._pit_context, first, first_laps
                ) or self._has_lap_context(self._pit_context, second, second_laps)
                pit_state = any(
                    _as_bool(state.get("InPit")) or _as_bool(state.get("PitOut"))
                    for state in (first_state, second_state)
                )
                penalty = self._has_lap_context(
                    self._penalty_context, first, first_laps
                ) or self._has_lap_context(self._penalty_context, second, second_laps)
                lapping = (
                    first_laps is not None
                    and second_laps is not None
                    and first_laps != second_laps
                )
                disrupted = self._track_status in {"2", "4", "5", "6", "7"}
                behind = first if current[first] > current[second] else second
                exchange_gap = self._gap_to_ahead(behind)
                close_gap = (
                    exchange_gap is not None
                    and 0 <= exchange_gap <= OVERTAKE_GAP_SECONDS
                )
                on_track = close_gap and not any(
                    (pit, pit_state, penalty, lapping, disrupted)
                )
                signals = ["TimingData"]
                if close_gap:
                    signals.append("close_gap")
                if pit:
                    signals.append("pit_context")
                if pit_state:
                    signals.append("pit_state")
                if penalty:
                    signals.append("penalty_context")
                if lapping:
                    signals.append("lap_difference")
                if disrupted:
                    signals.append("track_status")
                exchange = {
                    "event_id": _stable_id(
                        self._session_id,
                        "exchange",
                        first,
                        second,
                        previous[first],
                        current[first],
                        len(self._exchange_history),
                    ),
                    "kind": "likely_on_track_overtake"
                    if on_track
                    else "position_exchange",
                    "driver_numbers": [first, second],
                    "gaining_driver": changed,
                    "gap_seconds": exchange_gap,
                    "positions_before": {
                        str(first): previous[first],
                        str(second): previous[second],
                    },
                    "positions_after": {
                        str(first): current[first],
                        str(second): current[second],
                    },
                    "confidence": 0.85 if on_track else 0.55,
                    "supporting_signals": signals,
                }
                self._exchange_total += 1
                self._exchange_history.append(exchange)
                self._exchange_history = self._exchange_history[-MAX_EXCHANGES:]
                self._event(
                    identity=exchange["event_id"],
                    category="position",
                    kind=exchange["kind"],
                    title=f"Cars {first} and {second} exchanged position",
                    drivers=(first, second),
                    confidence=exchange["confidence"],
                    signals=tuple(signals),
                )
        self._previous_positions = current
        self._position_candidate.clear()
        self._position_candidate_frames = 0

    def _gap_to_ahead(self, driver: int) -> float | None:
        state = self._timing.get(str(driver), {})
        return _as_float(state.get("IntervalToPositionAhead") or state.get("Interval"))

    def _timing_snapshot(self) -> list[dict[str, Any]]:
        timing: list[dict[str, Any]] = []
        for driver_key, state in self._timing.items():
            driver = _as_int(driver_key)
            if driver is None:
                continue
            timing.append(
                {
                    "driver_number": driver,
                    "position": _as_int(state.get("Position")),
                    "laps_completed": _as_int(state.get("NumberOfLaps")),
                    "gap_to_leader": _value_text(state.get("GapToLeader")),
                    "interval_to_ahead": _value_text(
                        state.get("IntervalToPositionAhead") or state.get("Interval")
                    ),
                    "last_lap": _value_text(state.get("LastLapTime")),
                }
            )
        return sorted(
            timing,
            key=lambda item: (
                item["position"] is None,
                item["position"] or 999,
                item["driver_number"],
            ),
        )

    def _detect_battles(self) -> None:
        positions = self._position_snapshot()
        ordered = sorted(positions, key=positions.get)
        close_pairs: set[tuple[int, int]] = set()
        for behind in ordered[1:]:
            ahead_position = positions[behind] - 1
            ahead = next(
                (
                    driver
                    for driver, position in positions.items()
                    if position == ahead_position
                ),
                None,
            )
            gap = self._gap_to_ahead(behind)
            behind_laps = _as_int(self._timing.get(str(behind), {}).get("NumberOfLaps"))
            ahead_laps = _as_int(self._timing.get(str(ahead), {}).get("NumberOfLaps"))
            if (
                ahead is None
                or behind_laps is None
                or behind_laps <= 0
                or ahead_laps is None
                or ahead_laps != behind_laps
                or gap is None
                or gap > BATTLE_GAP_SECONDS
            ):
                continue
            pair = (ahead, behind)
            close_pairs.add(pair)
            self._battle_counts[pair] = self._battle_counts.get(pair, 0) + 1
            self._battle_end_counts[pair] = 0
            if self._battle_counts[pair] < BATTLE_START_FRAMES:
                continue
            if pair in self._active_battles:
                self._active_battles[pair]["gap_seconds"] = gap
                continue
            battle = {
                "battle_id": _stable_id(
                    self._session_id, "battle", ahead, behind, len(self._battle_history)
                ),
                "kind": "battle_started",
                "driver_numbers": [ahead, behind],
                "gap_seconds": gap,
                "confidence": 0.8,
                "supporting_signals": ["TimingData", "consecutive_gap_frames"],
                "active": True,
            }
            self._active_battles[pair] = battle
            self._battle_history.append(dict(battle))
            self._battle_history = self._battle_history[-MAX_BATTLES:]
            self._event(
                identity=battle["battle_id"],
                category="battle",
                kind="battle_started",
                title=f"Battle started: car {ahead} vs {behind}",
                drivers=(ahead, behind),
                confidence=0.8,
                signals=("TimingData", "consecutive_gap_frames"),
            )

        for pair in list(self._active_battles):
            if pair in close_pairs:
                continue
            self._battle_end_counts[pair] = self._battle_end_counts.get(pair, 0) + 1
            if self._battle_end_counts[pair] < BATTLE_END_FRAMES:
                continue
            battle = self._active_battles.pop(pair)
            ended = {
                **battle,
                "kind": "battle_ended",
                "active": False,
                "confidence": 0.75,
            }
            self._battle_history.append(ended)
            self._battle_history = self._battle_history[-MAX_BATTLES:]
            self._event(
                identity=f"{battle['battle_id']}:ended",
                category="battle",
                kind="battle_ended",
                title=f"Battle ended: car {pair[0]} vs {pair[1]}",
                drivers=pair,
                confidence=0.75,
                signals=("TimingData", "gap_opened"),
            )
            self._battle_counts.pop(pair, None)
            self._battle_end_counts.pop(pair, None)

    def _close_active_battles_for_session_end(self) -> None:
        for pair, battle in tuple(self._active_battles.items()):
            ended = {
                **battle,
                "kind": "battle_ended",
                "active": False,
                "confidence": 0.75,
                "supporting_signals": ["SessionStatus", "session_finished"],
            }
            self._battle_history.append(ended)
            self._battle_history = self._battle_history[-MAX_BATTLES:]
            self._event(
                identity=f"{battle['battle_id']}:session-ended",
                category="battle",
                kind="battle_ended",
                title=f"Battle ended: car {pair[0]} vs {pair[1]}",
                drivers=pair,
                confidence=0.75,
                signals=("SessionStatus", "session_finished"),
                final=True,
            )
        self._active_battles.clear()
        self._battle_counts.clear()
        self._battle_end_counts.clear()

    def _phase(self) -> str:
        if self._session_status in {"Started", "Green", "GreenFlag"}:
            return "live"
        if self._session_status in {"Finished", "Finalised", "Ends"}:
            return "after"
        return "before"

    def snapshot(self) -> dict[str, Any]:
        """Return the bounded Phase 4 dashboard product."""
        strategy = analyze_strategy(list(self._strategy_laps.values()), self._drivers)
        active_battles = [dict(item) for item in self._active_battles.values()]
        return {
            "protocol_version": 1,
            "provider": self._provider(),
            "session_id": self._session_id,
            "session_name": self._session_name,
            "session_status": self._session_status,
            "phase": self._phase(),
            "drivers": list(self._drivers.values()),
            "timing": self._timing_snapshot(),
            "timeline": {
                "events": self._timeline.snapshot(),
                "count": len(self._timeline.snapshot()),
            },
            "strategy": strategy,
            "position_exchanges": list(self._exchange_history),
            "position_exchange_count": self._exchange_total,
            "position_exchange_retained_count": len(self._exchange_history),
            "battles": {
                "active": active_battles,
                "history": list(self._battle_history),
                "threshold_seconds": BATTLE_GAP_SECONDS,
            },
            "capabilities": {
                "observed_streams": sorted(self._observed_streams),
                "timeline": "ready"
                if self._timeline.snapshot()
                else "waiting_for_events",
                "strategy": strategy["status"],
                "position_exchanges": "ready"
                if self._previous_positions
                else "waiting_for_positions",
                "battles": "ready"
                if self._previous_positions
                else "waiting_for_positions",
            },
        }

    def diagnostics(self) -> dict[str, Any]:
        """Return safe counts without event or telemetry payloads."""
        return {
            "provider": self._provider(),
            "session_id": self._session_id,
            "phase": self._phase(),
            "updates": self._updates,
            "timeline_events": len(self._timeline.snapshot()),
            "strategy_laps": len(self._strategy_laps),
            "position_exchanges": len(self._exchange_history),
            "position_exchanges_total": self._exchange_total,
            "active_battles": len(self._active_battles),
            "observed_streams": sorted(self._observed_streams),
        }

    async def async_close(self) -> None:
        """Detach all stream and WebSocket listeners."""
        for unsubscribe in self._unsubs:
            with suppress(Exception):
                unsubscribe()
        self._unsubs.clear()
        self._listeners.clear()


def historical_timeline(
    *,
    year: int,
    round_number: int,
    session_type: str,
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the shared event contract without inventing historical telemetry."""
    session_id = f"jolpica:{year}:{round_number}:{session_type.lower()}"
    store = UnifiedTimelineStore(max_events=80)
    store.upsert(
        TimelineEvent(
            event_id=_stable_id(session_id, "session", "final"),
            revision=0,
            sequence=0,
            provider="jolpica",
            session_id=session_id,
            occurred_at=None,
            offset_ms=None,
            category="session",
            kind="session_finalised",
            title=f"{session_type} classification finalised",
            final=True,
            supporting_signals=("Jolpica classification",),
        )
    )
    for result in results[:30]:
        driver = _as_int(result.get("driver_number"))
        position = _as_int(result.get("position"))
        if driver is None or position is None:
            continue
        store.upsert(
            TimelineEvent(
                event_id=_stable_id(session_id, "classification", driver),
                revision=0,
                sequence=0,
                provider="jolpica",
                session_id=session_id,
                occurred_at=None,
                offset_ms=None,
                category="classification",
                kind="final_classification",
                title=f"P{position} car {driver}",
                description=_text(result.get("driver_name")),
                driver_numbers=(driver,),
                confidence=1.0,
                final=True,
                supporting_signals=("Jolpica classification",),
            )
        )
    return {
        "protocol_version": 1,
        "provider": "jolpica",
        "session_id": session_id,
        "phase": "after",
        "events": store.snapshot(),
        "coverage": {
            "classification": "available",
            "race_control": "not_available_from_jolpica",
            "strategy": "not_available_from_jolpica",
            "telemetry": "not_available_from_jolpica",
            "position_exchanges": "not_inferred_from_results",
            "final": True,
        },
    }
