"""Provider-neutral session archive and historical lap analysis."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime
import re
from typing import Any

from homeassistant.core import HomeAssistant

from .helpers import fetch_json
from .jolpica_pagination import (
    async_paginate_jolpica,
    lap_leaf_keys,
    race_leaf_keys,
    result_leaf_keys,
    validate_single_page_jolpica,
)
from .models import HistoricalLapTiming, LapRecord, normalize_lap_record
from .providers import ProviderRegistry

JOLPICA_BASE_URL = "https://api.jolpi.ca/ergast/f1"
JOLPICA_ATTRIBUTION = "Data provided by Jolpica (jolpi.ca)"
LAP_ANALYSIS_STREAMS = frozenset(
    {"RaceControlMessages", "SessionInfo", "TimingData", "TrackStatus"}
)
DISRUPTED_TRACK_STATUSES = frozenset({"4", "5", "6", "7"})


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    with suppress(TypeError, ValueError):
        return int(str(value).strip())
    return None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    with suppress(TypeError, ValueError):
        parts = text.split(":")
        seconds = float(parts[-1])
        multiplier = 60.0
        for part in reversed(parts[:-1]):
            seconds += float(part) * multiplier
            multiplier *= 60.0
        return seconds
    return None


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _parse_utc(value: object) -> datetime | None:
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _session_kind(name: object, session_type: object) -> str:
    text = f"{name or ''} {session_type or ''}".lower()
    if "sprint" in text and any(
        marker in text for marker in ("qualifying", "shootout")
    ):
        return "sprint_qualifying"
    if "practice" in text:
        return "practice"
    if "sprint" in text and not any(
        marker in text for marker in ("qualifying", "shootout")
    ):
        return "sprint"
    if any(marker in text for marker in ("qualifying", "shootout")):
        return "qualifying"
    if "race" in text:
        return "race"
    return "other"


def _combine_date_time(date_value: object, time_value: object) -> str | None:
    date_text = _text(date_value)
    if date_text is None:
        return None
    time_text = _text(time_value) or "00:00:00Z"
    return f"{date_text}T{time_text}"


class HistoryService:
    """Expose a cached historical archive backed only by Jolpica."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: Any,
        *,
        cache: dict[str, tuple[float, Any]],
        inflight: dict[str, Any],
        persisted: dict[str, Any],
        persist_save: Callable[[], None],
        registry: ProviderRegistry,
    ) -> None:
        self._hass = hass
        self._session = session
        self._cache = cache
        self._inflight = inflight
        self._persisted = persisted
        self._persist_save = persist_save
        self._registry = registry
        self._catalog_requests = 0
        self._result_requests = 0
        self._lap_requests = 0

    async def async_get_catalog(
        self,
        year: int,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Return year -> meeting -> session from the sole history provider."""
        self._catalog_requests += 1
        year = int(year)
        payload = await self._async_fetch_json(
            f"{JOLPICA_BASE_URL}/{year}.json",
            year=year,
            params={"limit": 100, "offset": 0},
            force_refresh=force_refresh,
            validator=lambda data: validate_single_page_jolpica(data, race_leaf_keys),
        )
        return self._normalize_catalog(year, payload)

    async def async_get_session_results(
        self,
        *,
        year: int,
        session_key: int | str,
        round_number: int,
        session_type: str,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Return the classification Jolpica publishes for a session."""
        del session_key
        self._result_requests += 1
        kind = _session_kind(session_type, session_type)
        endpoint = {
            "qualifying": ("qualifying", "QualifyingResults"),
            "sprint": ("sprint", "SprintResults"),
            "race": ("results", "Results"),
        }.get(kind)
        if endpoint is None:
            return self._unsupported_results()

        endpoint_name, source_key = endpoint
        payload = await self._async_fetch_json(
            f"{JOLPICA_BASE_URL}/{year}/{int(round_number)}/{endpoint_name}.json",
            year=year,
            params={"limit": 100, "offset": 0},
            force_refresh=force_refresh,
            validator=lambda data: validate_single_page_jolpica(
                data, lambda value: result_leaf_keys(value, source_key)
            ),
        )
        return self._normalize_results(payload, source_key)

    async def async_get_laps(
        self,
        *,
        year: int,
        round_number: int,
        session_type: str,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Return complete race-lap timing rows with explicit data limitations."""
        self._lap_requests += 1
        kind = _session_kind(session_type, session_type)
        if kind != "race":
            return self._unsupported_laps(kind)

        ttl = self._ttl_for_year(year)

        async def _fetch_page(
            limit: int,
            offset: int,
            ttl_seconds: int,
            refresh_page: bool,
            validator: Callable[[dict[str, Any]], None],
        ) -> dict[str, Any]:
            return await self._async_fetch_json(
                f"{JOLPICA_BASE_URL}/{year}/{int(round_number)}/laps.json",
                year=year,
                params={"limit": limit, "offset": offset},
                force_refresh=force_refresh or refresh_page,
                validator=validator,
                ttl_seconds=ttl_seconds,
            )

        paginated = await async_paginate_jolpica(
            _fetch_page,
            lap_leaf_keys,
            ttl_stable=ttl,
            ttl_recent=ttl,
            ttl_latest=ttl,
            ttl_probe=ttl,
        )
        timings: dict[tuple[int, str], HistoricalLapTiming] = {}
        for page in paginated.pages:
            race_table = _mapping(_mapping(page.payload).get("MRData")).get("RaceTable")
            for race in _sequence(_mapping(race_table).get("Races")):
                for lap in _sequence(race.get("Laps")):
                    lap_number = _as_int(lap.get("number"))
                    if lap_number is None:
                        continue
                    for timing in _sequence(lap.get("Timings")):
                        driver_id = _text(timing.get("driverId"))
                        if driver_id is None:
                            continue
                        timings[(lap_number, driver_id)] = HistoricalLapTiming(
                            provider="jolpica",
                            driver_id=driver_id,
                            lap_number=lap_number,
                            position=_as_int(timing.get("position")),
                            lap_duration=_as_float(timing.get("time")),
                        )

        ordered = sorted(
            timings.values(),
            key=lambda item: (item.lap_number, item.position or 10_000, item.driver_id),
        )
        lap_numbers = [item.lap_number for item in ordered]
        self._registry.normalize(
            "jolpica",
            "historical_laps",
            {"year": year, "round": round_number, "count": len(ordered)},
            final=True,
            coverage_reason="race_lap_timing_only",
        )
        return {
            "year": int(year),
            "round": int(round_number),
            "session_type": session_type,
            "laps": [item.as_dict() for item in ordered],
            "lap_summary": {
                "total": len(ordered),
                "timed": sum(item.lap_duration is not None for item in ordered),
                "drivers": len({item.driver_id for item in ordered}),
                "first_lap": min(lap_numbers, default=None),
                "last_lap": max(lap_numbers, default=None),
            },
            "coverage": self._lap_coverage(
                lap_times="available" if ordered else "no_data",
                positions=(
                    "available"
                    if any(item.position is not None for item in ordered)
                    else "no_data"
                ),
                final=True,
            ),
            "attribution": JOLPICA_ATTRIBUTION,
        }

    def _normalize_catalog(self, year: int, payload: Any) -> dict[str, Any]:
        race_table = _mapping(_mapping(payload).get("MRData")).get("RaceTable")
        races = _sequence(_mapping(race_table).get("Races"))
        meetings: list[dict[str, Any]] = []
        for race in races:
            round_number = _as_int(race.get("round")) or len(meetings) + 1
            circuit = _mapping(race.get("Circuit"))
            location = _mapping(circuit.get("Location"))
            session_specs = (
                ("FirstPractice", "Practice 1", "practice"),
                ("SecondPractice", "Practice 2", "practice"),
                ("ThirdPractice", "Practice 3", "practice"),
                (
                    "SprintQualifying",
                    "Sprint Qualifying",
                    "sprint_qualifying",
                ),
                ("Sprint", "Sprint", "sprint"),
                ("Qualifying", "Qualifying", "qualifying"),
            )
            sessions: list[dict[str, Any]] = []
            for key, name, kind in session_specs:
                value = _mapping(race.get(key))
                if not value:
                    continue
                sessions.append(
                    self._jolpica_session(
                        year,
                        round_number,
                        name,
                        kind,
                        value.get("date"),
                        value.get("time"),
                    )
                )
            sessions.append(
                self._jolpica_session(
                    year,
                    round_number,
                    "Race",
                    "race",
                    race.get("date"),
                    race.get("time"),
                )
            )
            sessions.sort(key=lambda item: item.get("start") or "")
            meetings.append(
                {
                    "meeting_key": f"jolpica:{year}:{round_number}",
                    "round": round_number,
                    "name": _text(race.get("raceName")) or f"Round {round_number}",
                    "circuit": _text(circuit.get("circuitName")),
                    "country": _text(location.get("country")),
                    "location": _text(location.get("locality")),
                    "sessions": sessions,
                }
            )
        self._registry.normalize(
            "jolpica",
            "session_catalog",
            payload,
            final=year < datetime.now(UTC).year,
            coverage_reason="jolpica_only",
        )
        return {
            "year": year,
            "meetings": meetings,
            "coverage": {
                "provider": "jolpica",
                "historical_source": "jolpica_only",
                "results": "session_dependent",
                "lap_times": "race_only",
                "speed_traps": "not_available_from_jolpica",
                "minisectors": "not_available_from_jolpica",
                "final": year < datetime.now(UTC).year,
            },
            "attribution": JOLPICA_ATTRIBUTION,
        }

    @staticmethod
    def _jolpica_session(
        year: int,
        round_number: int,
        name: str,
        kind: str,
        date_value: object,
        time_value: object,
    ) -> dict[str, Any]:
        start = _combine_date_time(date_value, time_value)
        results_coverage = (
            "available"
            if kind in {"qualifying", "sprint", "race"}
            else "not_available_from_jolpica"
        )
        return {
            "session_key": f"jolpica:{year}:{round_number}:{kind}:{name}",
            "canonical_session_id": f"{year}:{round_number}:{kind}:{name}",
            "name": name,
            "kind": kind,
            "start": start,
            "end": None,
            "cancelled": False,
            "provider": "jolpica",
            "final": bool((parsed := _parse_utc(start)) and parsed < datetime.now(UTC)),
            "coverage": {
                "results": results_coverage,
                "lap_times": "available"
                if kind == "race"
                else "not_available_for_session",
                "speed_traps": "not_available_from_jolpica",
                "minisectors": "not_available_from_jolpica",
            },
        }

    def _normalize_results(self, payload: Any, source_key: str) -> dict[str, Any]:
        race_table = _mapping(_mapping(payload).get("MRData")).get("RaceTable")
        race = next(iter(_sequence(_mapping(race_table).get("Races"))), {})
        normalized: list[dict[str, Any]] = []
        for item in _sequence(_mapping(race).get(source_key)):
            driver = _mapping(item.get("Driver"))
            constructor = _mapping(item.get("Constructor"))
            status_text = (_text(item.get("status")) or "classified").lower()
            status = (
                "disqualified"
                if "disqual" in status_text
                else "did_not_start"
                if "not start" in status_text
                else "did_not_finish"
                if status_text not in {"finished", "classified"}
                and not status_text.startswith("+")
                else "classified"
            )
            normalized.append(
                {
                    "driver_number": _as_int(item.get("number")),
                    "driver_name": " ".join(
                        part
                        for part in (
                            _text(driver.get("givenName")),
                            _text(driver.get("familyName")),
                        )
                        if part
                    )
                    or None,
                    "driver_acronym": _text(driver.get("code")),
                    "constructor_name": _text(constructor.get("name")),
                    "position": _as_int(item.get("position")),
                    "grid": _as_int(item.get("grid")),
                    "points": _as_float(item.get("points")),
                    "status": status,
                    "status_detail": _text(item.get("status")),
                    "laps": _as_int(item.get("laps")),
                    "duration": _mapping(item.get("Time")).get("time"),
                    "gap_to_leader": _mapping(item.get("Time")).get("time"),
                    "q1": item.get("Q1"),
                    "q2": item.get("Q2"),
                    "q3": item.get("Q3"),
                }
            )
        self._registry.normalize(
            "jolpica",
            "session_results",
            payload,
            final=True,
            coverage_reason="jolpica_only",
        )
        return {
            "results": normalized,
            "coverage": {
                "provider": "jolpica",
                "historical_source": "jolpica_only",
                "results": "available" if normalized else "no_data",
                "final": True,
            },
            "attribution": JOLPICA_ATTRIBUTION,
        }

    @staticmethod
    def _unsupported_results() -> dict[str, Any]:
        return {
            "results": [],
            "coverage": {
                "provider": "jolpica",
                "historical_source": "jolpica_only",
                "results": "not_available",
                "reason": "session_results_not_available_from_jolpica",
                "final": True,
            },
            "attribution": JOLPICA_ATTRIBUTION,
        }

    @classmethod
    def _unsupported_laps(cls, kind: str) -> dict[str, Any]:
        return {
            "session_type": kind,
            "laps": [],
            "lap_summary": {
                "total": 0,
                "timed": 0,
                "drivers": 0,
                "first_lap": None,
                "last_lap": None,
            },
            "coverage": cls._lap_coverage(
                lap_times="not_available_for_session",
                positions="not_available_for_session",
                final=True,
            ),
            "attribution": JOLPICA_ATTRIBUTION,
        }

    @staticmethod
    def _lap_coverage(*, lap_times: str, positions: str, final: bool) -> dict[str, Any]:
        return {
            "provider": "jolpica",
            "lap_times": lap_times,
            "positions": positions,
            "speed_traps": "not_available_from_jolpica",
            "sectors": "not_available_from_jolpica",
            "minisectors": "not_available_from_jolpica",
            "lap_quality": "timing_only",
            "final": final,
        }

    async def _async_fetch_json(
        self,
        url: str,
        *,
        year: int,
        params: dict[str, Any],
        force_refresh: bool,
        validator: Callable[[dict[str, Any]], None],
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        payload = await fetch_json(
            self._hass,
            self._session,
            url,
            params=params,
            ttl_seconds=ttl_seconds or self._ttl_for_year(year),
            cache=self._cache,
            inflight=self._inflight,
            persist_map=self._persisted,
            persist_save=self._persist_save,
            force_refresh=force_refresh,
            validator=validator,
        )
        if not isinstance(payload, dict):
            raise ValueError("Jolpica historical response must be an object")
        return payload

    @staticmethod
    def _ttl_for_year(year: int) -> int:
        return 6 * 3600 if year >= datetime.now(UTC).year else 30 * 24 * 3600

    def diagnostics(self) -> dict[str, Any]:
        """Return compact provider coverage and request counters."""
        return {
            "provider": "jolpica",
            "catalog_requests": self._catalog_requests,
            "result_requests": self._result_requests,
            "lap_requests": self._lap_requests,
        }


_DELETED_LAP_RE = re.compile(
    r"CAR\s+(?P<driver>\d{1,2}).*?TIME\s+(?P<time>\d+:\d{2}\.\d{3})\s+DELETED(?:\s*-\s*(?P<reason>.*))?",
    re.IGNORECASE,
)
_REINSTATED_LAP_RE = re.compile(
    r"CAR\s+(?P<driver>\d{1,2}).*?TIME\s+(?P<time>\d+:\d{2}\.\d{3}).*?REINSTATED",
    re.IGNORECASE,
)


class LapAnalysisStore:
    """Accumulate the same lap contract from live or replay TimingData."""

    def __init__(
        self,
        bus: Any,
        *,
        source_provider: Callable[[], str],
        session_type: Callable[[], str | None] | None = None,
        max_laps: int = 500,
    ) -> None:
        self._bus = bus
        self._source_provider = source_provider
        self._session_type = session_type or (lambda: None)
        self._max_laps = max(20, int(max_laps))
        self._driver_state: dict[str, dict[str, Any]] = {}
        self._laps: dict[tuple[int, int], LapRecord] = {}
        self._order: list[tuple[int, int]] = []
        self._track_status: str | None = None
        self._previous_track_status: str | None = None
        self._post_disruption_baselines: dict[int, int | None] = {}
        self._post_disruption_laps: dict[int, int] = {}
        self._lap_track_context: dict[
            tuple[int, int], tuple[str | None, str | None]
        ] = {}
        self._active_session_id: str | None = None
        self._active_session_type: str | None = None
        self._unsubs: list[Callable[[], None]] = []
        self._updates = 0
        self._attach()

    def _attach(self) -> None:
        for stream, callback in (
            ("SessionInfo", self._on_session_info),
            ("TimingData", self._on_timing_data),
            ("TrackStatus", self._on_track_status),
            ("RaceControlMessages", self._on_race_control),
        ):
            with suppress(Exception):
                self._unsubs.append(self._bus.subscribe(stream, callback))

    def _on_session_info(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        meeting = _mapping(payload.get("Meeting"))
        session_id_parts = (
            _text(meeting.get("Key") or meeting.get("Id")),
            _text(
                payload.get("Key") or payload.get("SessionKey") or payload.get("Path")
            ),
            _text(payload.get("Name")),
        )
        session_id = ":".join(part for part in session_id_parts if part)
        if session_id and self._active_session_id not in {None, session_id}:
            self._reset_session()
        if session_id:
            self._active_session_id = session_id
        self._active_session_type = _text(
            payload.get("Type") or payload.get("SessionType") or payload.get("Name")
        )

    def _reset_session(self) -> None:
        self._driver_state.clear()
        self._laps.clear()
        self._order.clear()
        self._track_status = None
        self._previous_track_status = None
        self._post_disruption_baselines.clear()
        self._post_disruption_laps.clear()
        self._lap_track_context.clear()

    def reset_session(self) -> None:
        """Reset replay lap state when the same session starts again."""
        self._reset_session()

    def reset_for_replay(self) -> None:
        """Reset all accumulated state before replay playback is rebuilt."""
        self._reset_session()
        self._active_session_id = None
        self._active_session_type = None

    def _effective_session_type(self) -> str | None:
        return self._active_session_type or self._session_type()

    def _on_track_status(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        status = _text(payload.get("Status") or payload.get("status"))
        if status is None or status == self._track_status:
            return
        previous = self._track_status
        self._previous_track_status = previous
        self._track_status = status
        self._post_disruption_baselines.clear()
        self._post_disruption_laps.clear()
        if (
            previous in DISRUPTED_TRACK_STATUSES
            and status not in DISRUPTED_TRACK_STATUSES
        ):
            self._post_disruption_baselines = {
                driver: _as_int(state.get("NumberOfLaps"))
                for driver_key, state in self._driver_state.items()
                if (driver := _as_int(driver_key)) is not None
            }

    def _previous_status_for_lap(self, driver: int, lap_number: int) -> str | None:
        if (
            self._previous_track_status not in DISRUPTED_TRACK_STATUSES
            or self._track_status in DISRUPTED_TRACK_STATUSES
        ):
            return None
        first_post_disruption_lap = self._post_disruption_laps.get(driver)
        if first_post_disruption_lap is None:
            baseline = self._post_disruption_baselines.get(driver)
            if baseline is not None and lap_number <= baseline:
                return None
            first_post_disruption_lap = lap_number
            self._post_disruption_laps[driver] = lap_number
        if lap_number == first_post_disruption_lap:
            return self._previous_track_status
        return None

    def _on_timing_data(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        lines = payload.get("Lines")
        if not isinstance(lines, Mapping):
            return
        for driver_key, delta in lines.items():
            if not isinstance(delta, Mapping):
                continue
            driver = _as_int(driver_key)
            if driver is None:
                continue
            state = self._driver_state.setdefault(str(driver), {})
            self._deep_merge(state, delta)
            lap_number = _as_int(state.get("NumberOfLaps"))
            lap_time = state.get("LastLapTime")
            if lap_number is None or lap_number <= 0 or lap_time is None:
                continue
            key = (driver, lap_number)
            if key not in self._lap_track_context:
                self._lap_track_context[key] = (
                    self._track_status,
                    self._previous_status_for_lap(driver, lap_number),
                )
            track_status, previous_track_status = self._lap_track_context[key]
            normalized_payload = deepcopy(state)
            normalized_payload["RacingNumber"] = str(driver)
            normalized_payload["TrackStatus"] = track_status
            lap = normalize_lap_record(
                normalized_payload,
                provider=self._source_provider(),
                session_type=self._effective_session_type(),
                previous_track_status=previous_track_status,
            )
            current_lap = self._laps.get(key)
            if current_lap is not None and not self._prefer_lap_candidate(
                current_lap, lap
            ):
                continue
            if current_lap == lap:
                continue
            if key not in self._laps:
                self._order.append(key)
            self._laps[key] = lap
            self._updates += 1
            self._prune()

    @staticmethod
    def _prefer_lap_candidate(current: LapRecord, candidate: LapRecord) -> bool:
        """Keep the most complete revision when the next lap clears sectors."""
        if current.quality.deleted is not candidate.quality.deleted:
            return candidate.quality.deleted is True

        def _completeness(lap: LapRecord) -> tuple[int, int, int, float, int]:
            return (
                sum(value is not None for value in lap.sector_durations),
                sum(value is not None for value in lap.speed_traps.as_dict().values()),
                len(lap.minisectors),
                lap.quality.confidence,
                -len(lap.quality.reasons),
            )

        return _completeness(candidate) >= _completeness(current)

    def _on_race_control(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        messages = payload.get("Messages")
        if isinstance(messages, Mapping):
            items = [item for item in messages.values() if isinstance(item, Mapping)]
        elif isinstance(messages, Sequence) and not isinstance(messages, (str, bytes)):
            items = [item for item in messages if isinstance(item, Mapping)]
        else:
            items = [payload]
        for item in items:
            message = _text(item.get("Message") or item.get("message"))
            if message is None:
                continue
            reinstated = _REINSTATED_LAP_RE.search(message)
            deleted = _DELETED_LAP_RE.search(message)
            match = reinstated or deleted
            if match is None:
                continue
            driver = int(match.group("driver"))
            duration = self._duration_seconds(match.group("time"))
            target = self._matching_lap(driver, duration)
            if target is None:
                continue
            source = dict(target.source_payload)
            if reinstated is not None:
                source["reinstated"] = True
                source["deleted"] = False
                source.pop("deletion_reason", None)
            else:
                source["deleted"] = True
                source["deletion_reason"] = deleted.group("reason") or "Lap deleted"
            key = (driver, target.lap_number or 0)
            track_status, previous_track_status = self._lap_track_context.get(
                key, (source.get("TrackStatus"), None)
            )
            source["TrackStatus"] = track_status
            updated = normalize_lap_record(
                source,
                provider=target.provider,
                session_type=self._effective_session_type(),
                previous_track_status=previous_track_status,
            )
            self._laps[key] = updated
            self._updates += 1

    @staticmethod
    def _duration_seconds(value: str) -> float | None:
        minutes, _, seconds = value.partition(":")
        with suppress(ValueError):
            return int(minutes) * 60 + float(seconds)
        return None

    def _matching_lap(self, driver: int, duration: float | None) -> LapRecord | None:
        candidates = [
            lap
            for (lap_driver, _), lap in self._laps.items()
            if lap_driver == driver and lap.lap_duration is not None
        ]
        if not candidates:
            return None
        if duration is None:
            return candidates[-1]
        return min(candidates, key=lambda lap: abs((lap.lap_duration or 0) - duration))

    @classmethod
    def _deep_merge(cls, target: dict[str, Any], delta: Mapping[str, Any]) -> None:
        for key, value in delta.items():
            current = target.get(str(key))
            if isinstance(current, dict) and isinstance(value, Mapping):
                cls._deep_merge(current, value)
            else:
                target[str(key)] = deepcopy(value)

    def _prune(self) -> None:
        while len(self._order) > self._max_laps:
            key = self._order.pop(0)
            self._laps.pop(key, None)
            self._lap_track_context.pop(key, None)

    def get_lap(self, driver: int, lap_number: int) -> dict[str, Any] | None:
        """Return one normalized lap without materializing the full lap store."""
        lap = self._laps.get((driver, lap_number))
        return lap.as_dict() if lap is not None else None

    def snapshot(self) -> dict[str, Any]:
        """Return bounded live/replay lap analytics for a WebSocket consumer."""
        laps = [self._laps[key] for key in self._order if key in self._laps]
        bests: dict[str, float | None] = {
            "i1": None,
            "i2": None,
            "finish": None,
            "straight": None,
        }
        for lap in laps:
            for name, value in lap.speed_traps.as_dict().items():
                if value is not None and (bests[name] is None or value > bests[name]):
                    bests[name] = value
        return {
            "provider": self._source_provider(),
            "session_id": self._active_session_id,
            "laps": [lap.as_dict() for lap in laps],
            "speed_traps": {"session_best": bests},
            "lap_quality": {
                "total": len(laps),
                "clean": sum(lap.quality.clean for lap in laps),
                "deleted": sum(lap.quality.deleted is True for lap in laps),
                "inferred": sum(lap.quality.inferred for lap in laps),
            },
            "coverage": {
                "speed_traps": "available"
                if any(value is not None for value in bests.values())
                else "no_data",
                "minisectors": "available"
                if any(lap.minisectors for lap in laps)
                else "no_data",
            },
        }

    def diagnostics(self) -> dict[str, Any]:
        """Return safe counts without lap payloads."""
        return {
            "provider": self._source_provider(),
            "session_id": self._active_session_id,
            "laps": len(self._laps),
            "drivers": len({driver for driver, _ in self._laps}),
            "updates": self._updates,
            "max_laps": self._max_laps,
        }

    async def async_close(self) -> None:
        """Detach live/replay stream listeners."""
        for unsub in self._unsubs:
            with suppress(Exception):
                unsub()
        self._unsubs.clear()
