"""Formation start tracking using the CarData stream."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import async_timeout
from aiohttp import ClientSession
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .helpers import parse_cardata_lines
from .signalr import LiveBus

_LOGGER = logging.getLogger(__name__)

_CARDATA_SEARCH_WINDOW = timedelta(seconds=90)
_CARDATA_PRE_WINDOW = timedelta(seconds=60)
_CARDATA_RETRY_DELAY = 20
_CARDATA_MAX_ATTEMPTS = 3
_CARDATA_TIMEOUT = 20


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            dt_val = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            dt_val = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt_val.tzinfo is None:
        dt_val = dt_val.replace(tzinfo=UTC)
    return dt_val.astimezone(UTC)


def _parse_offset(offset: str | None) -> timedelta:
    if not offset:
        return timedelta()
    try:
        sign = -1 if offset.startswith("-") else 1
        parts = offset.replace("+", "").replace("-", "").split(":")
        hours = int(parts[0]) if len(parts) > 0 else 0
        minutes = int(parts[1]) if len(parts) > 1 else 0
        seconds = int(parts[2]) if len(parts) > 2 else 0
        return timedelta(seconds=sign * (hours * 3600 + minutes * 60 + seconds))
    except Exception:  # noqa: BLE001
        return timedelta()


def _session_start_utc(payload: dict | None) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    start = payload.get("StartDate")
    if not start:
        return None
    gmt_offset = payload.get("GmtOffset")
    try:
        if isinstance(start, str) and start.endswith("Z"):
            dt_val = datetime.fromisoformat(start.replace("Z", "+00:00"))
        else:
            dt_val = datetime.fromisoformat(str(start))
    except ValueError:
        return None
    offset = _parse_offset(str(gmt_offset) if gmt_offset is not None else None)
    tzinfo = timezone(offset)
    if dt_val.tzinfo is None:
        dt_val = dt_val.replace(tzinfo=tzinfo)
    return dt_val.astimezone(UTC)


def _is_race_or_sprint(session_type: str | None, session_name: str | None) -> bool:
    joined = f"{session_type or ''} {session_name or ''}".lower()
    if "sprint" in joined and "qualifying" not in joined:
        return True
    return "race" in joined


def _build_static_url(path: str, resource: str) -> str:
    normalized = str(path or "").strip().strip("/")
    return f"https://livetiming.formula1.com/static/{normalized}/{resource}"


class FormationStartTracker:
    """Finds the formation start marker near the scheduled session start."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        bus: LiveBus,
        http_session: ClientSession,
    ) -> None:
        self._hass = hass
        self._bus = bus
        self._http = http_session
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._session_unsub: Callable[[], None] | None = None
        self._status_unsub: Callable[[], None] | None = None
        self._task: asyncio.Task | None = None
        self._session_id: str | None = None
        self._session_type: str | None = None
        self._session_name: str | None = None
        self._path: str | None = None
        self._scheduled_start_utc: datetime | None = None
        self._formation_start_utc: datetime | None = None
        self._delta_seconds: float | None = None
        self._status: str = "idle"
        self._source: str | None = None
        self._last_error: str | None = None

    @property
    def formation_start_utc(self) -> datetime | None:
        return self._formation_start_utc

    def snapshot(self) -> dict[str, Any]:
        def _fmt(value: datetime | None) -> str | None:
            if value is None:
                return None
            return value.isoformat(timespec="seconds")

        return {
            "status": self._status,
            "session_id": self._session_id,
            "session_type": self._session_type,
            "session_name": self._session_name,
            "path": self._path,
            "scheduled_start": _fmt(self._scheduled_start_utc),
            "formation_start": _fmt(self._formation_start_utc),
            "delta_seconds": self._delta_seconds,
            "source": self._source,
            "error": self._last_error,
        }

    def reset(self, *, status: str = "idle") -> None:
        """Clear any stored formation state and notify listeners."""
        self._cancel_task()
        self._session_id = None
        self._session_type = None
        self._session_name = None
        self._path = None
        self._scheduled_start_utc = None
        self._reset_state(status=status)
        self._notify_listeners()

    async def async_close(self) -> None:
        self._detach_bus()
        self._cancel_task()

    def add_listener(
        self, listener: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        self._listeners.append(listener)
        if len(self._listeners) == 1:
            self._attach_bus()
        try:
            listener(self.snapshot())
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Formation start listener raised during sync", exc_info=True)

        def _remove() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                return
            if not self._listeners:
                self._detach_bus()
                self._cancel_task()

        return _remove

    def _attach_bus(self) -> None:
        if self._session_unsub is not None:
            return
        try:
            self._session_unsub = self._bus.subscribe(
                "SessionInfo", self._handle_session_info
            )
        except Exception:  # noqa: BLE001
            self._session_unsub = None
            _LOGGER.debug("FormationStartTracker failed to subscribe to SessionInfo")
        try:
            self._status_unsub = self._bus.subscribe(
                "SessionStatus", self._handle_session_status
            )
        except Exception:  # noqa: BLE001
            self._status_unsub = None
            _LOGGER.debug("FormationStartTracker failed to subscribe to SessionStatus")

    def _detach_bus(self) -> None:
        if self._session_unsub is not None:
            with suppress(Exception):
                self._session_unsub()
            self._session_unsub = None
        if self._status_unsub is not None:
            with suppress(Exception):
                self._status_unsub()
            self._status_unsub = None

    def _notify_listeners(self) -> None:
        snapshot = self.snapshot()
        for listener in list(self._listeners):
            try:
                listener(snapshot)
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Formation start listener raised", exc_info=True)

    def _reset_state(self, *, status: str = "idle") -> None:
        self._status = status
        self._formation_start_utc = None
        self._delta_seconds = None
        self._source = None
        self._last_error = None

    def _handle_session_info(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        path = payload.get("Path")
        session_id = str(path or payload.get("Key") or "").strip() or None
        if session_id != self._session_id:
            self._session_id = session_id
            self._session_type = None
            self._session_name = None
            self._path = None
            self._scheduled_start_utc = None
            self._reset_state(status="idle")
            self._cancel_task()

        self._session_type = str(payload.get("Type") or self._session_type or "")
        self._session_name = str(payload.get("Name") or self._session_name or "")
        self._path = str(path or self._path or "").strip() or None
        self._scheduled_start_utc = (
            _session_start_utc(payload) or self._scheduled_start_utc
        )

        if not _is_race_or_sprint(self._session_type, self._session_name):
            if self._status != "not_applicable":
                self._reset_state(status="not_applicable")
                self._cancel_task()
                self._notify_listeners()
            return

        if self._formation_start_utc is not None:
            return

        if self._scheduled_start_utc and self._path:
            self._status = "pending"
            self._notify_listeners()
            self._schedule_probe()

    def _handle_session_status(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        message = str(payload.get("Status") or payload.get("Message") or "").strip()
        started = payload.get("Started")
        is_live = str(started).lower() in ("started", "true") or message in {
            "Started",
            "Green",
            "GreenFlag",
        }
        if not is_live:
            return
        if self._status == "ready":
            self._status = "live"
            self._notify_listeners()

    def _schedule_probe(self) -> None:
        if self._task is not None and not self._task.done():
            return
        if not self._scheduled_start_utc or not self._path:
            return
        delay = (
            self._scheduled_start_utc - dt_util.utcnow() - _CARDATA_PRE_WINDOW
        ).total_seconds()
        delay = max(0.0, delay)
        session_id = self._session_id
        self._task = self._hass.async_create_task(self._run_probe(delay, session_id))

    def _cancel_task(self) -> None:
        if self._task is None:
            return
        if not self._task.done():
            self._task.cancel()
        self._task = None

    async def _run_probe(self, delay: float, session_id: str | None) -> None:
        if delay > 0:
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return
        attempts = 0
        while attempts < _CARDATA_MAX_ATTEMPTS:
            if session_id != self._session_id:
                return
            found = await self._probe_cardata(session_id)
            if found:
                return
            attempts += 1
            if attempts < _CARDATA_MAX_ATTEMPTS:
                try:
                    await asyncio.sleep(_CARDATA_RETRY_DELAY)
                except asyncio.CancelledError:
                    return
        if self._status == "pending":
            self._status = "unavailable"
            self._notify_listeners()

    async def _probe_cardata(self, session_id: str | None) -> bool:
        if session_id != self._session_id:
            return False
        if not self._path or not self._scheduled_start_utc:
            return False
        url = _build_static_url(self._path, "CarData.z.jsonStream")
        target = self._scheduled_start_utc
        window_seconds = _CARDATA_SEARCH_WINDOW.total_seconds()
        best_utc: datetime | None = None
        best_delta: float | None = None
        max_seen: datetime | None = None
        stop_scan = False
        batch: list[str] = []
        try:
            async with async_timeout.timeout(_CARDATA_TIMEOUT):
                async with self._http.get(url) as resp:
                    if resp.status == 404:
                        self._last_error = "not_found"
                        return False
                    resp.raise_for_status()

                    def _process_utcs(utcs: list[datetime]) -> bool:
                        nonlocal best_delta, best_utc, max_seen, stop_scan
                        for utc_val in utcs:
                            if session_id != self._session_id:
                                return False
                            if max_seen is None or utc_val > max_seen:
                                max_seen = utc_val
                            delta = abs((utc_val - target).total_seconds())
                            if best_delta is None or delta < best_delta:
                                best_delta = delta
                                best_utc = utc_val
                            if utc_val > target + _CARDATA_SEARCH_WINDOW:
                                stop_scan = True
                                break
                        return True

                    while not stop_scan:
                        raw = await resp.content.readline()
                        if not raw:
                            break
                        line = raw.decode("utf-8", errors="ignore").strip()
                        if not line:
                            continue
                        batch.append(line)
                        if len(batch) >= 50:
                            utcs = await self._hass.async_add_executor_job(
                                parse_cardata_lines, list(batch), _parse_utc
                            )
                            batch.clear()
                            if not _process_utcs(utcs):
                                return False
                        if stop_scan:
                            break
                    if batch and not stop_scan:
                        utcs = await self._hass.async_add_executor_job(
                            parse_cardata_lines, list(batch), _parse_utc
                        )
                        if not _process_utcs(utcs):
                            return False
        except TimeoutError:
            self._last_error = "timeout"
            return False
        except Exception:  # noqa: BLE001
            self._last_error = "error"
            return False

        if max_seen is None:
            self._last_error = "empty"
            return False
        if max_seen < (target - timedelta(seconds=1)):
            self._last_error = "not_reached"
            return False
        if best_utc is None or best_delta is None:
            self._last_error = "no_match"
            return False
        if best_delta > window_seconds:
            self._last_error = "out_of_window"
            return False

        self._formation_start_utc = best_utc
        self._delta_seconds = best_delta
        self._status = "ready"
        self._source = "cardata"
        self._last_error = None
        self._notify_listeners()
        return True
