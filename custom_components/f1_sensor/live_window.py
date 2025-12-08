from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import contextlib
import json
from typing import Any, Callable, Iterable, TYPE_CHECKING

import async_timeout
from aiohttp import ClientSession
from homeassistant.util import dt as dt_util

from .signalr import LiveBus
from .const import DOMAIN

if TYPE_CHECKING:
    from . import LiveSessionCoordinator

_LOGGER = logging.getLogger(f"custom_components.{DOMAIN}")

STATIC_BASE = "https://livetiming.formula1.com/static"
SESSION_END_STATES = {"Finished", "Finalised", "Ends"}
SESSION_RUNNING_STATES = {"Started", "Resumed"}
DEFAULT_PRE_WINDOW = timedelta(minutes=60)
DEFAULT_POST_WINDOW = timedelta(minutes=15)
POST_WINDOW_EXTENSION_CAP = timedelta(minutes=30)
POST_WINDOW_EXTENSION_STEP = timedelta(minutes=5)
IDLE_REFRESH = timedelta(minutes=15)
ACTIVE_REFRESH = timedelta(seconds=20)
HEARTBEAT_DRAIN_SECONDS = 60.0
FALLBACK_WINDOW_DURATION = timedelta(minutes=20)
LIVE_ACTIVITY_STREAMS: tuple[str, ...] = (
    "SessionStatus",
    "SessionInfo",
    "RaceControlMessages",
    "TrackStatus",
    "TimingData",
    "TimingAppData",
    "DriverList",
    "LapCount",
    "WeatherData",
)


@dataclass
class SessionWindow:
    meeting_name: str
    session_name: str
    path: str
    start_utc: datetime
    end_utc: datetime
    connect_at: datetime
    disconnect_at: datetime
    meeting_key: int | None = None
    session_key: int | None = None

    @property
    def label(self) -> str:
        return f"{self.meeting_name} – {self.session_name}".strip(" –")


class LiveAvailabilityTracker:
    """Fan-out tracker so coordinators can react to live/offline transitions."""

    def __init__(self) -> None:
        self._listeners: list[Callable[[bool, str | None], None]] = []
        self._state = False
        self._reason: str | None = "init"

    @property
    def is_live(self) -> bool:
        return self._state

    @property
    def reason(self) -> str | None:
        return self._reason

    def set_state(self, is_live: bool, reason: str | None = None) -> None:
        if self._state == is_live and (reason is None or reason == self._reason):
            return
        self._state = is_live
        self._reason = reason
        state_label = "LIVE" if is_live else "IDLE"
        if _LOGGER.isEnabledFor(logging.INFO):
            _LOGGER.info("Live timing availability -> %s (%s)", state_label, reason or "no-reason")
        for callback in list(self._listeners):
            try:
                callback(is_live, reason)
            except Exception:  # noqa: BLE001 - defensive
                _LOGGER.debug("Live availability listener raised", exc_info=True)

    def add_listener(self, callback: Callable[[bool, str | None], None]) -> Callable[[], None]:
        self._listeners.append(callback)
        # Fire immediately with current state
        try:
            callback(self._state, self._reason)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Live availability listener failed on attach", exc_info=True)

        def _remove() -> None:
            try:
                if callback in self._listeners:
                    self._listeners.remove(callback)
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Failed to remove availability listener", exc_info=True)

        return _remove


def _parse_offset(offset: str | None) -> timedelta:
    if not offset:
        return timedelta()
    try:
        sign = -1 if offset.startswith("-") else 1
        hh, mm, ss = (abs(int(part)) for part in offset.replace("+", "").replace("-", "").split(":"))
        return timedelta(seconds=sign * (hh * 3600 + mm * 60 + ss))
    except Exception:  # noqa: BLE001
        return timedelta()


def _to_utc(date_str: str | None, gmt_offset: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        if date_str.endswith("Z"):
            dt_val = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        else:
            dt_val = datetime.fromisoformat(date_str)
    except ValueError:
        return None
    try:
        offset = _parse_offset(gmt_offset)
        tzinfo = timezone(offset)
    except Exception:  # noqa: BLE001
        tzinfo = timezone.utc
    if dt_val.tzinfo is None:
        dt_val = dt_val.replace(tzinfo=tzinfo)
    return dt_val.astimezone(timezone.utc)


def _normalize_path(path: str | None) -> str | None:
    if not path:
        return None
    cleaned = path.strip().strip("/")
    if not cleaned:
        return None
    if not cleaned.endswith("/"):
        cleaned = f"{cleaned}/"
    return cleaned


def _ensure_sequence(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        try:
            return list(value.values())
        except Exception:  # noqa: BLE001
            return []
    return []


def _iter_meeting_sessions(index_payload: Any) -> Iterable[tuple[dict, dict]]:
    payload = index_payload or {}
    meetings = _ensure_sequence(payload.get("Meetings") or payload.get("meetings"))
    if meetings:
        for meeting in meetings:
            sessions = _ensure_sequence(meeting.get("Sessions") or meeting.get("sessions"))
            for session in sessions:
                yield meeting, session
        return
    # Fallback: some builds expose Sessions at root with embedded Meeting
    sessions = _ensure_sequence(payload.get("Sessions") or payload.get("sessions"))
    for session in sessions:
        meeting = session.get("Meeting") or session.get("meeting") or {}
        yield meeting, session


def _debug_payload_preview(payload: Any) -> str:
    try:
        if isinstance(payload, dict):
            keys = list(payload.keys())
            preview = {}
            for key in keys[:2]:
                preview[key] = payload.get(key)
            return json.dumps(
                {
                    "type": type(payload).__name__,
                    "keys": keys[:10],
                    "preview": preview,
                },
                default=str,
            )
        return f"type={type(payload).__name__}"
    except Exception:  # noqa: BLE001
        return "<unprintable>"


def build_session_windows(
    index_payload: Any,
    *,
    pre_window: timedelta = DEFAULT_PRE_WINDOW,
    post_window: timedelta = DEFAULT_POST_WINDOW,
) -> list[SessionWindow]:
    windows: list[SessionWindow] = []
    for meeting, session in _iter_meeting_sessions(index_payload):
        path = _normalize_path(session.get("Path"))
        start = _to_utc(session.get("StartDate"), session.get("GmtOffset"))
        end = _to_utc(session.get("EndDate"), session.get("GmtOffset")) or start
        if not start:
            continue
        if not end or end <= start:
            end = start + timedelta(hours=2)
        connect_at = start - pre_window
        disconnect_at = end + post_window
        windows.append(
            SessionWindow(
                meeting_name=(meeting.get("Name") or meeting.get("OfficialName") or "F1").strip(),
                session_name=(session.get("Name") or session.get("Type") or "Session").strip(),
                path=path or "",
                start_utc=start,
                end_utc=end,
                connect_at=connect_at,
                disconnect_at=disconnect_at,
                meeting_key=meeting.get("Key"),
                session_key=session.get("Key"),
            )
        )
    windows.sort(key=lambda w: w.start_utc)
    return windows


def _build_static_url(path: str, resource: str) -> str:
    normalized = path.strip("/")
    return f"{STATIC_BASE}/{normalized}/{resource}"


def _clock_finished(clock: dict | None) -> bool:
    if not isinstance(clock, dict):
        return False
    try:
        remaining = clock.get("Remaining") or ""
        extrapolating = bool(clock.get("Extrapolating"))
        if extrapolating:
            return False
        parts = remaining.split(":")
        if len(parts) != 3:
            return False
        hours, minutes, seconds = (int(part) for part in parts)
        return hours == minutes == seconds == 0
    except Exception:  # noqa: BLE001
        return False


class LiveSessionSupervisor:
    """Coordinates when the SignalR connection should run."""

    def __init__(
        self,
        hass,
        session_coord: "LiveSessionCoordinator",
        bus: LiveBus,
        *,
        http_session: ClientSession,
        pre_window: timedelta = DEFAULT_PRE_WINDOW,
        post_window: timedelta = DEFAULT_POST_WINDOW,
    ) -> None:
        self._hass = hass
        self._session_coord = session_coord
        self._bus = bus
        self._http = http_session
        self._pre_window = pre_window
        self._post_window = post_window
        self._task: asyncio.Task | None = None
        self._stopped = False
        self._current_window: SessionWindow | None = None
        self._availability = LiveAvailabilityTracker()

    @property
    def availability(self) -> LiveAvailabilityTracker:
        return self._availability

    @property
    def current_window(self) -> SessionWindow | None:
        return self._current_window

    async def async_start(self) -> None:
        if self._task is None or self._task.done():
            self._task = self._hass.loop.create_task(self._runner())

    async def async_close(self) -> None:
        self._stopped = True
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _runner(self) -> None:
        try:
            while not self._stopped:
                window, allow_fallback = await self._resolve_window()
                fallback = False
                if window is None:
                    # No window from index – either index is missing/broken (allow_fallback=True)
                    # or season is finished and there is nothing more to follow (allow_fallback=False).
                    self._availability.set_state(False, "no-session-found")
                    if not allow_fallback:
                        await asyncio.sleep(IDLE_REFRESH.total_seconds())
                        continue
                    fallback = True
                    window = self._make_fallback_window()
                    _LOGGER.warning(
                        "Falling back to legacy live connection for %s seconds",
                        FALLBACK_WINDOW_DURATION.total_seconds(),
                    )
                now = dt_util.utcnow()
                if now < window.connect_at:
                    wait = max(30.0, min(IDLE_REFRESH.total_seconds(), (window.connect_at - now).total_seconds()))
                    _LOGGER.debug(
                        "Next session %s opens in %.0fs (connect window %s – %s)",
                        window.label,
                        wait,
                        window.connect_at.isoformat(),
                        window.disconnect_at.isoformat(),
                    )
                    self._availability.set_state(False, f"waiting-{window.session_name}")
                    await asyncio.sleep(wait)
                    continue
                await self._activate_window(window, fallback=fallback)
        except asyncio.CancelledError:
            pass

    def _make_fallback_window(self) -> SessionWindow:
        now = dt_util.utcnow()
        return SessionWindow(
            meeting_name="Unknown",
            session_name="Fallback",
            path="",
            start_utc=now - timedelta(minutes=1),
            end_utc=now + FALLBACK_WINDOW_DURATION,
            connect_at=now - timedelta(minutes=1),
            disconnect_at=now + FALLBACK_WINDOW_DURATION,
        )

    async def _resolve_window(self) -> tuple[SessionWindow | None, bool]:
        """Resolve the best session window.

        Returns (window, allow_fallback).
        - window: SessionWindow or None
        - allow_fallback:
            * True  -> index missing/empty, it is reasonable to try legacy fallback.
            * False -> season finished / fully past known schedule; do NOT fallback.
        """
        data = getattr(self._session_coord, "data", None)
        if not data:
            try:
                await self._session_coord.async_refresh()
                data = getattr(self._session_coord, "data", None)
            except Exception:  # noqa: BLE001
                data = None
        windows = build_session_windows(data, pre_window=self._pre_window, post_window=self._post_window)
        if not windows:
            _LOGGER.warning(
                "Live timing index returned no sessions for year %s (payload=%s)",
                getattr(self._session_coord, "year", "unknown"),
                _debug_payload_preview(data),
            )
            # Index is missing / unusable; allow legacy fallback.
            return None, True
        now = dt_util.utcnow()
        upcoming = [w for w in windows if now <= w.disconnect_at]
        if not upcoming:
            last = windows[-1]
            if last.path and await self._session_active(last):
                extended = replace(
                    last,
                    connect_at=min(last.connect_at, now - timedelta(minutes=5)),
                    disconnect_at=now + FALLBACK_WINDOW_DURATION,
                )
                _LOGGER.info(
                    "Extending session window for %s until %s (SessionStatus still active)",
                    extended.label,
                    extended.disconnect_at.isoformat(),
                )
                return extended, False
            _LOGGER.info(
                "All sessions in index are finished (last disconnect %s UTC). Waiting for new event.",
                last.disconnect_at.isoformat(),
            )
            # All known sessions (including final event) are finished; do not
            # start legacy fallback – stay idle until a new year's index appears.
            return None, False
        window = upcoming[0]
        _LOGGER.debug(
            "Selected session window %s (start %s, end %s, connect %s, disconnect %s, now %s)",
            window.label,
            window.start_utc.isoformat(),
            window.end_utc.isoformat(),
            window.connect_at.isoformat(),
            window.disconnect_at.isoformat(),
            now.isoformat(),
        )
        return window, False

    async def _session_active(self, window: SessionWindow) -> bool:
        if not window.path:
            return False
        now = dt_util.utcnow()
        try:
            data = await self._fetch_json(_build_static_url(window.path, "SessionStatus.jsonStream"))
        except Exception as err:
            slack = window.end_utc + timedelta(hours=2)
            if now <= slack:
                _LOGGER.warning(
                    "SessionStatus fetch failed for %s (%s); assuming session still active",
                    window.label,
                    err,
                )
                return True
            _LOGGER.debug(
                "SessionStatus fetch failed for %s beyond slack window (%s)",
                window.label,
                err,
            )
            return False
        if not isinstance(data, dict):
            _LOGGER.debug("SessionStatus payload invalid for %s: %s", window.label, data)
            return False
        status = str(data.get("Status") or "").strip()
        started = str(data.get("Started") or "").strip()
        if status in SESSION_END_STATES:
            return False
        if started in SESSION_END_STATES:
            return False
        return True

    async def _activate_window(self, window: SessionWindow, *, fallback: bool = False) -> None:
        self._current_window = window
        label = window.label
        _LOGGER.info(
            "Arming live timing for %s (connect=%s, disconnect=%s)",
            label,
            window.connect_at.isoformat(),
            window.disconnect_at.isoformat(),
        )
        await self._bus.start()
        self._bus.set_heartbeat_expectation(True)
        self._availability.set_state(True, f"live-{window.session_name}")
        if window.path:
            await self._prime_metadata(window)
        else:
            _LOGGER.debug("Skipping metadata priming for %s (no path)", label)
        try:
            reason = await self._monitor_window(window, fallback=fallback)
        finally:
            self._bus.set_heartbeat_expectation(False)
            await self._bus.async_close()
            self._availability.set_state(False, f"finished-{window.session_name}")
            _LOGGER.info("Live timing closed for %s (%s)", label, reason if 'reason' in locals() else "no-reason")
            self._current_window = None
            try:
                await self._session_coord.async_request_refresh()
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Session index refresh failed after %s", label, exc_info=True)

    async def _prime_metadata(self, window: SessionWindow) -> None:
        url = _build_static_url(window.path, "SessionInfo.jsonStream")
        status_url = _build_static_url(window.path, "SessionStatus.jsonStream")
        data_url = _build_static_url(window.path, "SessionData.jsonStream")
        for name, target in (
            ("SessionInfo", url),
            ("SessionStatus", status_url),
            ("SessionData", data_url),
        ):
            try:
                payload = await self._fetch_json(target)
                if payload:
                    _LOGGER.debug("%s prime %s keys=%s", window.label, name, list(payload.keys())[:5])
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Failed priming %s for %s", name, window.label, exc_info=True)

    async def _monitor_window(self, window: SessionWindow, *, fallback: bool = False) -> str:
        label = window.label
        reason = "disconnect-window-expired"
        max_disconnect_at = (
            window.disconnect_at + POST_WINDOW_EXTENSION_CAP if not fallback else window.disconnect_at
        )
        while not self._stopped:
            await asyncio.sleep(ACTIVE_REFRESH.total_seconds())
            now = dt_util.utcnow()
            hb_age = self._bus.last_heartbeat_age()
            activity_age = self._bus.last_stream_activity_age(LIVE_ACTIVITY_STREAMS)
            if now >= window.disconnect_at:
                should_extend = (
                    not fallback
                    and window.disconnect_at < max_disconnect_at
                    and (
                        (hb_age is not None and hb_age <= HEARTBEAT_DRAIN_SECONDS)
                        or (activity_age is not None and activity_age <= HEARTBEAT_DRAIN_SECONDS)
                    )
                )
                if should_extend:
                    extension = min(
                        POST_WINDOW_EXTENSION_STEP,
                        max_disconnect_at - window.disconnect_at,
                    )
                    window.disconnect_at += extension
                    _LOGGER.info(
                        "Extending disconnect window for %s by %.0fs (new disconnect %s) "
                        "due to live feed activity (heartbeat_age=%s, activity_age=%s)",
                        label,
                        extension.total_seconds(),
                        window.disconnect_at.isoformat(),
                        f"{hb_age:.0f}s" if hb_age is not None else "n/a",
                        f"{activity_age:.0f}s" if activity_age is not None else "n/a",
                    )
                    continue
                _LOGGER.info("Disconnect window expired for %s", label)
                reason = "disconnect-window-expired"
                break
            if hb_age is not None and hb_age > HEARTBEAT_DRAIN_SECONDS:
                _LOGGER.info("Heartbeat aged %.0fs for %s; assuming feed idle", hb_age, label)
                reason = f"heartbeat-timeout-{hb_age:.0f}s"
                break
            if fallback:
                candidate, _ = await self._resolve_window()
                if candidate and candidate.session_name != "Fallback":
                    _LOGGER.info("Real session detected while fallback active; switching to %s", candidate.label)
                    reason = "fallback-replaced"
                    break
        return reason

    async def _session_finished(self, window: SessionWindow) -> bool:
        url = _build_static_url(window.path, "SessionStatus.jsonStream")
        try:
            data = await self._fetch_json(url)
        except Exception:  # noqa: BLE001
            return False
        status = (data or {}).get("Status")
        started = (data or {}).get("Started")
        if status in SESSION_END_STATES:
            return True
        if status in SESSION_RUNNING_STATES or started in SESSION_RUNNING_STATES:
            return False
        return False

    async def _fetch_json(self, url: str) -> Any:
        async with async_timeout.timeout(10):
            async with self._http.get(url) as resp:
                if resp.status == 404:
                    return None
                resp.raise_for_status()
                text = await resp.text()
        return json.loads(text.lstrip("\ufeff"))


