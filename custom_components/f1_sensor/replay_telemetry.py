"""On-demand bounded replay telemetry comparison for selected laps only."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime
from functools import partial
import json
import math
from pathlib import Path
from typing import Any

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant

from .helpers import (
    CARDATA_MAX_DECOMPRESSED_BYTES,
    CARDATA_MAX_ENTRIES,
    CARDATA_MAX_LINE_BYTES,
    decode_raw_deflate_json_payload,
)
from .replay_mode import STATIC_BASE

MAX_TELEMETRY_SELECTIONS = 4
MAX_TELEMETRY_POINTS = 500
MAX_RAW_SELECTION_POINTS = 4_000
MAX_TELEMETRY_CACHE_ENTRIES = 8
TELEMETRY_HTTP_TIMEOUT = 120


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Mapping):
        value = value.get("Value")
    with suppress(TypeError, ValueError):
        return int(str(value).strip())
    return None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Mapping):
        value = value.get("Value")
    with suppress(TypeError, ValueError):
        parsed = float(str(value).strip())
        return parsed if math.isfinite(parsed) else None
    return None


def _parse_utc(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    with suppress(ValueError):
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def _frame_utc(payload: Mapping[str, Any]) -> datetime | None:
    for key in ("Utc", "utc", "Timestamp", "timestamp"):
        if parsed := _parse_utc(payload.get(key)):
            return parsed
    entries = payload.get("Entries")
    if isinstance(entries, Sequence) and not isinstance(entries, (str, bytes)):
        for entry in entries:
            if isinstance(entry, Mapping) and (parsed := _parse_utc(entry.get("Utc"))):
                return parsed
    return None


def _deep_merge(target: dict[str, Any], delta: Mapping[str, Any]) -> None:
    for key, value in delta.items():
        current = target.get(str(key))
        if isinstance(current, dict) and isinstance(value, Mapping):
            _deep_merge(current, value)
        else:
            target[str(key)] = deepcopy(value)


def _selection_key(driver: int, lap: int) -> str:
    return f"{driver}:{lap}"


def _scan_replay_windows(
    frames_file: Path,
    selections: tuple[tuple[int, int], ...],
    session_start_ms: int,
) -> tuple[dict[str, tuple[int, int]], tuple[datetime, int] | None]:
    """Find selected lap boundaries and one replay-ms to UTC anchor."""
    selected_drivers = {driver for driver, _lap in selections}
    state: dict[int, dict[str, Any]] = {}
    completion: dict[tuple[int, int], int] = {}
    anchor: tuple[datetime, int] | None = None
    with frames_file.open("rb") as handle:
        for raw_line in handle:
            with suppress(
                UnicodeDecodeError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ):
                decoded = json.loads(raw_line)
                frame_ms = int(decoded["t"])
                payload = decoded["p"]
                if not isinstance(payload, Mapping):
                    continue
                if anchor is None and (utc_value := _frame_utc(payload)) is not None:
                    anchor = (utc_value, frame_ms)
                if decoded.get("s") != "TimingData":
                    continue
                lines = payload.get("Lines")
                if not isinstance(lines, Mapping):
                    continue
                for driver_key, delta in lines.items():
                    driver = _as_int(driver_key)
                    if driver not in selected_drivers or not isinstance(delta, Mapping):
                        continue
                    target = state.setdefault(driver, {})
                    _deep_merge(target, delta)
                    lap = _as_int(target.get("NumberOfLaps"))
                    last_lap = target.get("LastLapTime")
                    if lap is not None and lap > 0 and last_lap is not None:
                        completion.setdefault((driver, lap), frame_ms)

    windows: dict[str, tuple[int, int]] = {}
    for driver, lap in selections:
        end_ms = completion.get((driver, lap))
        if end_ms is None:
            continue
        start_ms = completion.get((driver, lap - 1), session_start_ms)
        if start_ms < end_ms:
            windows[_selection_key(driver, lap)] = (start_ms, end_ms)
    return windows, anchor


def _channel_value(channels: Mapping[str, Any], key: str) -> float | None:
    return _as_float(channels.get(key))


def _decode_selected_batch(
    lines: list[str],
    *,
    anchor_utc: datetime,
    anchor_ms: int,
    windows: Mapping[str, tuple[int, int]],
) -> tuple[dict[str, list[dict[str, Any]]], int | None]:
    selected_drivers = {
        int(key.split(":", 1)[0]) for key in windows if key.split(":", 1)[0].isdecimal()
    }
    samples: dict[str, list[dict[str, Any]]] = {key: [] for key in windows}
    max_seen_ms: int | None = None
    for line in lines:
        payload = decode_raw_deflate_json_payload(
            line,
            max_line_bytes=CARDATA_MAX_LINE_BYTES,
            max_decompressed_bytes=CARDATA_MAX_DECOMPRESSED_BYTES,
        )
        entries = payload.get("Entries") if isinstance(payload, Mapping) else None
        if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
            continue
        if len(entries) > CARDATA_MAX_ENTRIES:
            continue
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            utc_value = _parse_utc(entry.get("Utc"))
            cars = entry.get("Cars")
            if utc_value is None or not isinstance(cars, Mapping):
                continue
            timestamp_ms = anchor_ms + round(
                (utc_value - anchor_utc).total_seconds() * 1000
            )
            max_seen_ms = max(timestamp_ms, max_seen_ms or timestamp_ms)
            for driver in selected_drivers:
                car = cars.get(str(driver), cars.get(driver))
                channels = _mapping(_mapping(car).get("Channels"))
                if not channels:
                    continue
                for key, (start_ms, end_ms) in windows.items():
                    if (
                        not key.startswith(f"{driver}:")
                        or not start_ms <= timestamp_ms <= end_ms
                    ):
                        continue
                    samples[key].append(
                        {
                            "timestamp_ms": timestamp_ms,
                            "time_s": round((timestamp_ms - start_ms) / 1000, 3),
                            "speed": _channel_value(channels, "2"),
                            "throttle": _channel_value(channels, "4"),
                            "brake": _channel_value(channels, "5"),
                            "gear": _as_int(channels.get("3")),
                            "drs": _as_int(channels.get("45")),
                            "rpm": _as_int(channels.get("0")),
                        }
                    )
    return samples, max_seen_ms


def _bounded_extend(target: list[dict[str, Any]], values: list[dict[str, Any]]) -> None:
    target.extend(values)
    if len(target) <= MAX_RAW_SELECTION_POINTS:
        return
    target[:] = target[::2]


def _add_distance(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(samples, key=lambda item: item["timestamp_ms"])
    distance = 0.0
    previous: dict[str, Any] | None = None
    for sample in ordered:
        if previous is not None:
            elapsed = max(0.0, sample["time_s"] - previous["time_s"])
            speed = sample.get("speed")
            previous_speed = previous.get("speed")
            if speed is not None and previous_speed is not None:
                distance += (((speed + previous_speed) / 2) / 3.6) * elapsed
        sample["distance"] = round(distance, 2)
        previous = sample
    return ordered


def _downsample(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(samples) <= MAX_TELEMETRY_POINTS:
        return samples
    step = (len(samples) - 1) / (MAX_TELEMETRY_POINTS - 1)
    indexes = {round(index * step) for index in range(MAX_TELEMETRY_POINTS)}
    return [sample for index, sample in enumerate(samples) if index in indexes]


def _time_at_distance(
    samples: Sequence[Mapping[str, Any]], distance: float
) -> float | None:
    if not samples:
        return None
    previous = samples[0]
    for current in samples[1:]:
        previous_distance = _as_float(previous.get("distance")) or 0.0
        current_distance = _as_float(current.get("distance")) or 0.0
        if current_distance < distance:
            previous = current
            continue
        previous_time = _as_float(previous.get("time_s")) or 0.0
        current_time = _as_float(current.get("time_s")) or previous_time
        if current_distance <= previous_distance:
            return current_time
        ratio = (distance - previous_distance) / (current_distance - previous_distance)
        return previous_time + (current_time - previous_time) * ratio
    return _as_float(samples[-1].get("time_s"))


class ReplayTelemetryService:
    """Fetch and retain only explicitly selected replay lap telemetry."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        session_manager: Any,
    ) -> None:
        self._hass = hass
        self._session = session
        self._session_manager = session_manager
        self._cache: OrderedDict[
            tuple[str, tuple[tuple[int, int], ...]], dict[str, Any]
        ] = OrderedDict()
        self._requests = 0
        self._cache_hits = 0

    @staticmethod
    def _normalize_selections(
        selections: Sequence[Mapping[str, Any]],
    ) -> tuple[tuple[int, int], ...]:
        normalized: set[tuple[int, int]] = set()
        for item in selections:
            driver = _as_int(item.get("driver_number"))
            lap = _as_int(item.get("lap_number"))
            if driver is None or lap is None or not 0 < driver < 100 or lap <= 0:
                raise ValueError(
                    "Each telemetry selection requires a valid driver_number and lap_number"
                )
            normalized.add((driver, lap))
        if not normalized:
            raise ValueError("At least one telemetry selection is required")
        if len(normalized) > MAX_TELEMETRY_SELECTIONS:
            raise ValueError(
                f"At most {MAX_TELEMETRY_SELECTIONS} telemetry selections are allowed"
            )
        return tuple(sorted(normalized))

    async def async_compare(
        self,
        selections: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Return downsampled telemetry for selected laps in the loaded replay."""
        normalized = self._normalize_selections(selections)
        if self._session_manager is None:
            raise ValueError("Load a replay session before requesting telemetry")
        index = self._session_manager.get_loaded_index()
        selected_session = self._session_manager.selected_session
        if index is None or selected_session is None:
            raise ValueError("Load a replay session before requesting telemetry")
        cache_key = (index.session_id, normalized)
        if cache_key in self._cache:
            self._cache_hits += 1
            self._cache.move_to_end(cache_key)
            return deepcopy(self._cache[cache_key])

        self._requests += 1
        windows, anchor = await self._hass.async_add_executor_job(
            _scan_replay_windows,
            index.frames_file,
            normalized,
            index.session_started_at_ms,
        )
        missing = [
            {"driver_number": driver, "lap_number": lap}
            for driver, lap in normalized
            if _selection_key(driver, lap) not in windows
        ]
        if missing:
            raise ValueError(f"Selected replay laps are unavailable: {missing}")
        if anchor is None:
            anchor = (
                selected_session.start_utc.astimezone(UTC),
                index.session_started_at_ms,
            )

        collected = {key: [] for key in windows}
        max_window_end = max(end for _start, end in windows.values())
        url = f"{STATIC_BASE}/{selected_session.path}/CarData.z.jsonStream"
        batch: list[str] = []
        stop_scan = False
        try:
            async with asyncio.timeout(TELEMETRY_HTTP_TIMEOUT):
                async with self._session.get(url) as response:
                    if response.status == 404:
                        raise ValueError(
                            "Telemetry is unavailable for the selected replay session"
                        )
                    if response.status != 200:
                        raise ValueError(
                            "Replay telemetry provider is temporarily unavailable"
                        )
                    while not stop_scan:
                        raw = await response.content.readline()
                        if not raw:
                            break
                        if len(raw) > CARDATA_MAX_LINE_BYTES:
                            continue
                        line = raw.decode("utf-8", errors="ignore").strip()
                        if not line:
                            continue
                        batch.append(line)
                        if len(batch) < 24:
                            continue
                        decoded, max_seen = await self._hass.async_add_executor_job(
                            partial(
                                _decode_selected_batch,
                                list(batch),
                                anchor_utc=anchor[0],
                                anchor_ms=anchor[1],
                                windows=windows,
                            )
                        )
                        batch.clear()
                        for key, values in decoded.items():
                            _bounded_extend(collected[key], values)
                        stop_scan = (
                            max_seen is not None and max_seen > max_window_end + 2_000
                        )
                    if batch and not stop_scan:
                        decoded, _max_seen = await self._hass.async_add_executor_job(
                            partial(
                                _decode_selected_batch,
                                list(batch),
                                anchor_utc=anchor[0],
                                anchor_ms=anchor[1],
                                windows=windows,
                            )
                        )
                        for key, values in decoded.items():
                            _bounded_extend(collected[key], values)
        except TimeoutError as err:
            raise ValueError("Replay telemetry request timed out") from err

        series: list[dict[str, Any]] = []
        for driver, lap in normalized:
            key = _selection_key(driver, lap)
            samples = _downsample(_add_distance(collected[key]))
            top_speed = max(
                (
                    sample["speed"]
                    for sample in samples
                    if sample.get("speed") is not None
                ),
                default=None,
            )
            series.append(
                {
                    "driver_number": driver,
                    "lap_number": lap,
                    "sample_count": len(samples),
                    "samples": samples,
                    "summary": {
                        "top_speed": top_speed,
                        "distance": samples[-1]["distance"] if samples else None,
                    },
                }
            )

        reference = series[0]["samples"] if series else []
        for item in series:
            for sample in item["samples"]:
                reference_time = _time_at_distance(reference, sample["distance"])
                sample["delta_s"] = (
                    round(sample["time_s"] - reference_time, 3)
                    if reference_time is not None
                    else None
                )

        result = {
            "protocol_version": 1,
            "provider": "replay",
            "session_id": index.session_id,
            "series": series,
            "coverage": {
                "speed": "available",
                "throttle": "available",
                "brake": "available",
                "gear": "available",
                "drs": "available",
                "distance_time_delta": "derived",
                "corner_annotations": "not_available",
                "raw_home_assistant_states": "not_exposed",
            },
            "limits": {
                "max_selections": MAX_TELEMETRY_SELECTIONS,
                "max_points_per_lap": MAX_TELEMETRY_POINTS,
                "cache_entries": MAX_TELEMETRY_CACHE_ENTRIES,
            },
        }
        self._cache[cache_key] = deepcopy(result)
        self._cache.move_to_end(cache_key)
        while len(self._cache) > MAX_TELEMETRY_CACHE_ENTRIES:
            self._cache.popitem(last=False)
        return result

    def diagnostics(self) -> dict[str, int]:
        """Return bounded cache counters without selections or samples."""
        return {
            "requests": self._requests,
            "cache_hits": self._cache_hits,
            "cache_entries": len(self._cache),
            "max_cache_entries": MAX_TELEMETRY_CACHE_ENTRIES,
            "max_selections": MAX_TELEMETRY_SELECTIONS,
            "max_points_per_lap": MAX_TELEMETRY_POINTS,
        }

    async def async_close(self) -> None:
        """Release cached selected telemetry."""
        self._cache.clear()
