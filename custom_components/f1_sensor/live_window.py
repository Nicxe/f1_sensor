from __future__ import annotations
from contextlib import suppress

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import contextlib
import json
import re
import time
from typing import Any, Callable, Iterable, Protocol, TYPE_CHECKING

import async_timeout
from aiohttp import ClientSession
from homeassistant.util import dt as dt_util

from .signalr import LiveBus
from .const import (
    DOMAIN,
    EVENT_TRACKER_ACTIVE_CACHE_TTL,
    EVENT_TRACKER_API_BASE_URL,
    EVENT_TRACKER_DEFAULT_API_KEY,
    EVENT_TRACKER_DEFAULT_LOCALE,
    EVENT_TRACKER_ENDPOINT,
    EVENT_TRACKER_ENV_REFRESH_TTL,
    EVENT_TRACKER_ENV_SOURCE_URL,
    EVENT_TRACKER_FALLBACK_ENABLED,
    EVENT_TRACKER_IDLE_CACHE_TTL,
    EVENT_TRACKER_MEETING_ENDPOINT_PREFIX,
    EVENT_TRACKER_REQUEST_TIMEOUT,
)

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
PRIMARY_RECOVERY_CHECK_INTERVAL = timedelta(minutes=1)
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

    # Reasons that indicate replay mode is controlling state
    _REPLAY_REASONS = frozenset({"replay", "replay-completed", "replay-stopped"})

    def __init__(self) -> None:
        self._listeners: list[Callable[[bool, str | None], None]] = []
        self._state = False
        self._reason: str | None = "init"
        self._replay_locked = False  # When True, only replay can change state

    @property
    def is_live(self) -> bool:
        return self._state

    @property
    def reason(self) -> str | None:
        return self._reason

    def set_state(self, is_live: bool, reason: str | None = None) -> None:
        is_replay_reason = reason in self._REPLAY_REASONS

        # If replay has locked the state, only replay reasons can change it
        if self._replay_locked and not is_replay_reason:
            _LOGGER.debug(
                "Live state change blocked (replay active): would change to %s (%s)",
                "LIVE" if is_live else "IDLE",
                reason,
            )
            return

        # Update replay lock based on reason
        if reason == "replay":
            self._replay_locked = True
        elif reason in ("replay-completed", "replay-stopped"):
            self._replay_locked = False

        if self._state == is_live and (reason is None or reason == self._reason):
            return
        self._state = is_live
        self._reason = reason
        state_label = "LIVE" if is_live else "IDLE"
        if _LOGGER.isEnabledFor(logging.INFO):
            _LOGGER.info(
                "Live timing availability -> %s (%s)",
                state_label,
                reason or "no-reason",
            )
        for callback in list(self._listeners):
            try:
                callback(is_live, reason)
            except Exception:  # noqa: BLE001 - defensive
                _LOGGER.debug("Live availability listener raised", exc_info=True)

    def add_listener(
        self, callback: Callable[[bool, str | None], None]
    ) -> Callable[[], None]:
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
        parts = [
            abs(int(part))
            for part in offset.replace("+", "").replace("-", "").split(":")
            if part != ""
        ]
        if len(parts) == 1:
            hh, mm, ss = parts[0], 0, 0
        elif len(parts) == 2:
            hh, mm, ss = parts[0], parts[1], 0
        elif len(parts) >= 3:
            hh, mm, ss = parts[0], parts[1], parts[2]
        else:
            return timedelta()
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
            sessions = _ensure_sequence(
                meeting.get("Sessions") or meeting.get("sessions")
            )
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
                meeting_name=(
                    meeting.get("Name") or meeting.get("OfficialName") or "F1"
                ).strip(),
                session_name=(
                    session.get("Name") or session.get("Type") or "Session"
                ).strip(),
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


def _as_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return int(text)
    except (TypeError, ValueError):
        return None


def _clean_text(*values: Any, default: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


@dataclass
class ScheduleFetchResult:
    windows: list[SessionWindow]
    source: str
    index_http_status: int | None = None
    last_error: str | None = None


class LiveScheduleSource(Protocol):
    async def async_fetch_windows(
        self,
        *,
        pre_window: timedelta,
        post_window: timedelta,
        active: bool = False,
    ) -> ScheduleFetchResult:
        """Return schedule windows for this source."""


class IndexScheduleSource:
    """Primary schedule source backed by LiveTiming Index.json."""

    def __init__(self, session_coord: "LiveSessionCoordinator") -> None:
        self._session_coord = session_coord

    async def async_fetch_windows(
        self,
        *,
        pre_window: timedelta,
        post_window: timedelta,
        active: bool = False,
    ) -> ScheduleFetchResult:
        del active
        data = getattr(self._session_coord, "data", None)
        if not data:
            try:
                await self._session_coord.async_refresh()
                data = getattr(self._session_coord, "data", None)
            except Exception as err:  # noqa: BLE001
                return ScheduleFetchResult(
                    windows=[],
                    source="index",
                    index_http_status=getattr(
                        self._session_coord, "last_http_status", None
                    ),
                    last_error=str(err),
                )
        windows = build_session_windows(
            data, pre_window=pre_window, post_window=post_window
        )
        return ScheduleFetchResult(
            windows=windows,
            source="index",
            index_http_status=getattr(self._session_coord, "last_http_status", None),
        )


class _EventTrackerHttpError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


class EventTrackerScheduleSource:
    """Secondary schedule source backed by api.formula1.com event-tracker."""

    def __init__(
        self,
        http_session: ClientSession,
        *,
        fallback_enabled: bool = EVENT_TRACKER_FALLBACK_ENABLED,
        base_url: str = EVENT_TRACKER_API_BASE_URL,
        endpoint: str = EVENT_TRACKER_ENDPOINT,
        meeting_endpoint_prefix: str = EVENT_TRACKER_MEETING_ENDPOINT_PREFIX,
        api_key: str = EVENT_TRACKER_DEFAULT_API_KEY,
        locale: str = EVENT_TRACKER_DEFAULT_LOCALE,
        request_timeout: int = EVENT_TRACKER_REQUEST_TIMEOUT,
        active_cache_ttl: int = EVENT_TRACKER_ACTIVE_CACHE_TTL,
        idle_cache_ttl: int = EVENT_TRACKER_IDLE_CACHE_TTL,
        env_refresh_ttl: int = EVENT_TRACKER_ENV_REFRESH_TTL,
        env_source_url: str = EVENT_TRACKER_ENV_SOURCE_URL,
    ) -> None:
        self._http = http_session
        self._enabled = bool(fallback_enabled)
        self._base_url = str(base_url).rstrip("/")
        self._endpoint = self._normalize_endpoint(endpoint)
        self._meeting_endpoint_prefix = self._normalize_endpoint(meeting_endpoint_prefix)
        self._api_key = str(api_key or "").strip()
        self._locale = str(locale or "en").strip() or "en"
        self._timeout = int(10 if request_timeout is None else request_timeout)
        self._active_cache_ttl = max(
            0, int(60 if active_cache_ttl is None else active_cache_ttl)
        )
        self._idle_cache_ttl = max(0, int(900 if idle_cache_ttl is None else idle_cache_ttl))
        self._env_refresh_ttl = max(
            60, int(3600 if env_refresh_ttl is None else env_refresh_ttl)
        )
        self._env_source_url = str(env_source_url or EVENT_TRACKER_ENV_SOURCE_URL)

        self._cache_expires_at = 0.0
        self._cache_result = ScheduleFetchResult(windows=[], source="event_tracker")
        self._last_env_refresh = 0.0

    @staticmethod
    def _normalize_endpoint(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return "/"
        if not text.startswith("/"):
            text = f"/{text}"
        return text

    @staticmethod
    def _extract_env_value(raw_text: str, key: str) -> str | None:
        patterns = (
            rf'{re.escape(key)}":"(?P<value>[^"]+)"',
            rf'{re.escape(key)}\\":\\"(?P<value>[^"\\]+)\\"',
        )
        for pattern in patterns:
            match = re.search(pattern, raw_text)
            if not match:
                continue
            value = match.group("value").replace("\\/", "/").strip()
            if value:
                return value
        return None

    async def _refresh_dynamic_config(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_env_refresh < self._env_refresh_ttl:
            return
        self._last_env_refresh = now
        if not self._env_source_url:
            return
        try:
            async with async_timeout.timeout(self._timeout):
                async with self._http.get(self._env_source_url) as resp:
                    if resp.status != 200:
                        return
                    text = await resp.text()
        except Exception:  # noqa: BLE001
            return

        updated = False
        base_url = self._extract_env_value(text, "PUBLIC_GLOBAL_APIGEE_BASEURL")
        endpoint = self._extract_env_value(text, "PUBLIC_GLOBAL_EVENTTRACKER_ENDPOINT")
        meeting_prefix = self._extract_env_value(
            text, "PUBLIC_GLOBAL_EVENTTRACKER_MEETINGENDPOINT"
        )
        api_key = self._extract_env_value(text, "PUBLIC_GLOBAL_EVENTTRACKER_APIKEY")
        if base_url:
            self._base_url = base_url.rstrip("/")
            updated = True
        if endpoint:
            self._endpoint = self._normalize_endpoint(endpoint)
            updated = True
        if meeting_prefix:
            self._meeting_endpoint_prefix = self._normalize_endpoint(meeting_prefix)
            updated = True
        if api_key:
            self._api_key = api_key
            updated = True
        if updated and _LOGGER.isEnabledFor(logging.INFO):
            _LOGGER.info("Updated event-tracker fallback configuration from live-lite")

    def _build_url(self, endpoint: str) -> str:
        return f"{self._base_url}{endpoint}"

    def _meeting_endpoint(self, meeting_key: int) -> str:
        prefix = self._meeting_endpoint_prefix
        if "{meeting_key}" in prefix:
            return prefix.format(meeting_key=meeting_key)
        if not prefix.endswith("/"):
            prefix = f"{prefix}/"
        return f"{prefix}{meeting_key}"

    async def _fetch_tracker_json(
        self,
        endpoint: str,
        *,
        allow_retry: bool = True,
        endpoint_kind: str = "direct",
        meeting_key: int | None = None,
    ) -> dict:
        headers = {
            "apiKey": self._api_key,
            "locale": self._locale,
        }
        url = self._build_url(endpoint)
        async with async_timeout.timeout(self._timeout):
            async with self._http.get(url, headers=headers) as resp:
                text = await resp.text()
                if resp.status != 200:
                    preview = (text or "").strip()[:200]
                    if allow_retry and resp.status in (401, 403):
                        old_endpoint = self._endpoint
                        old_meeting_prefix = self._meeting_endpoint_prefix
                        await self._refresh_dynamic_config(force=True)
                        retry_endpoint = endpoint
                        if endpoint_kind == "root" and old_endpoint == endpoint:
                            retry_endpoint = self._endpoint
                        elif (
                            endpoint_kind == "meeting"
                            and meeting_key is not None
                            and old_meeting_prefix
                        ):
                            retry_endpoint = self._meeting_endpoint(meeting_key)
                        return await self._fetch_tracker_json(
                            retry_endpoint,
                            allow_retry=False,
                            endpoint_kind=endpoint_kind,
                            meeting_key=meeting_key,
                        )
                    raise _EventTrackerHttpError(resp.status, preview or "unknown-error")
        payload = json.loads((text or "null").lstrip("\ufeff"))
        if not isinstance(payload, dict):
            raise RuntimeError("event-tracker payload is not a dict")
        return payload

    @staticmethod
    def _extract_meeting_key(payload: dict | None) -> int | None:
        if not isinstance(payload, dict):
            return None
        season_ctx = payload.get("seasonContext") or {}
        meeting_ctx = payload.get("meetingContext") or {}
        for candidate in (
            season_ctx.get("currentOrNextMeetingKey"),
            meeting_ctx.get("meetingKey"),
            payload.get("fomRaceId"),
        ):
            meeting_key = _as_int(candidate)
            if meeting_key is not None:
                return meeting_key
        return None

    @staticmethod
    def _extract_timetables(payload: dict | None) -> list[dict]:
        if not isinstance(payload, dict):
            return []
        season_ctx = payload.get("seasonContext") or {}
        event = payload.get("event") or {}
        meeting_ctx = payload.get("meetingContext") or {}
        for candidate in (
            season_ctx.get("timetables"),
            event.get("timetables"),
            meeting_ctx.get("timetables"),
        ):
            if isinstance(candidate, list):
                rows = [item for item in candidate if isinstance(item, dict)]
                if rows:
                    return rows
        return []

    @staticmethod
    def _extract_meeting_name(payload: dict | None) -> str:
        if not isinstance(payload, dict):
            return "F1"
        race = payload.get("race") or {}
        event = payload.get("event") or {}
        meeting_ctx = payload.get("meetingContext") or {}
        return _clean_text(
            race.get("meetingOfficialName"),
            race.get("meetingName"),
            event.get("meetingOfficialName"),
            event.get("meetingName"),
            meeting_ctx.get("meetingKey"),
            default="F1",
        )

    def _windows_from_payload(
        self,
        payload: dict | None,
        *,
        pre_window: timedelta,
        post_window: timedelta,
        meeting_key: int | None = None,
    ) -> list[SessionWindow]:
        timetables = self._extract_timetables(payload)
        meeting_name = self._extract_meeting_name(payload)
        if meeting_key is None:
            meeting_key = self._extract_meeting_key(payload)
        windows: list[SessionWindow] = []
        for item in timetables:
            start = _to_utc(item.get("startTime"), item.get("gmtOffset"))
            end = _to_utc(item.get("endTime"), item.get("gmtOffset")) or start
            if not start:
                continue
            if not end or end <= start:
                end = start + timedelta(hours=2)
            session_name = _clean_text(
                item.get("description"),
                item.get("shortName"),
                item.get("sessionType"),
                item.get("session"),
                default="Session",
            )
            windows.append(
                SessionWindow(
                    meeting_name=meeting_name,
                    session_name=session_name,
                    path="",
                    start_utc=start,
                    end_utc=end,
                    connect_at=start - pre_window,
                    disconnect_at=end + post_window,
                    meeting_key=meeting_key,
                    session_key=_as_int(item.get("meetingSessionKey")),
                )
            )
        windows.sort(key=lambda w: w.start_utc)
        return windows

    async def async_fetch_windows(
        self,
        *,
        pre_window: timedelta,
        post_window: timedelta,
        active: bool = False,
    ) -> ScheduleFetchResult:
        if not self._enabled:
            return ScheduleFetchResult(
                windows=[],
                source="event_tracker",
                last_error="fallback-disabled",
            )

        now_mono = time.monotonic()
        if now_mono < self._cache_expires_at:
            return self._cache_result

        ttl = self._active_cache_ttl if active else self._idle_cache_ttl
        await self._refresh_dynamic_config()

        errors: list[str] = []
        windows: list[SessionWindow] = []
        meeting_key: int | None = None

        try:
            root_payload = await self._fetch_tracker_json(
                self._endpoint,
                endpoint_kind="root",
            )
            meeting_key = self._extract_meeting_key(root_payload)
            windows = self._windows_from_payload(
                root_payload,
                pre_window=pre_window,
                post_window=post_window,
                meeting_key=meeting_key,
            )
        except Exception as err:  # noqa: BLE001
            errors.append(f"root:{err}")
            root_payload = None

        if not windows and meeting_key is None:
            meeting_key = self._extract_meeting_key(root_payload)
        if not windows and meeting_key is not None:
            try:
                meeting_payload = await self._fetch_tracker_json(
                    self._meeting_endpoint(meeting_key),
                    endpoint_kind="meeting",
                    meeting_key=meeting_key,
                )
                windows = self._windows_from_payload(
                    meeting_payload,
                    pre_window=pre_window,
                    post_window=post_window,
                    meeting_key=meeting_key,
                )
            except Exception as err:  # noqa: BLE001
                errors.append(f"meeting:{err}")

        result = ScheduleFetchResult(
            windows=windows,
            source="event_tracker",
            last_error=("; ".join(errors) if errors else None),
        )
        self._cache_result = result
        self._cache_expires_at = now_mono + float(ttl)
        return result


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
        index_source: LiveScheduleSource | None = None,
        fallback_source: LiveScheduleSource | None = None,
        pre_window: timedelta = DEFAULT_PRE_WINDOW,
        post_window: timedelta = DEFAULT_POST_WINDOW,
    ) -> None:
        self._hass = hass
        self._session_coord = session_coord
        self._bus = bus
        self._http = http_session
        self._index_source = index_source or IndexScheduleSource(session_coord)
        self._fallback_source = fallback_source
        self._pre_window = pre_window
        self._post_window = post_window
        self._task: asyncio.Task | None = None
        self._stopped = False
        self._current_window: SessionWindow | None = None
        self._current_window_source: str = "none"
        self._availability = LiveAvailabilityTracker()
        self._schedule_source: str = "none"
        self._index_http_status: int | None = None
        self._fallback_active = False
        self._last_schedule_error: str | None = None
        self._last_primary_recovery_check = 0.0
        # Throttle noisy logs (e.g. missing index at season rollover)
        self._log_throttle: dict[str, float] = {}

    def _should_log(self, key: str, *, interval_seconds: float) -> bool:
        now = time.monotonic()
        last = self._log_throttle.get(key, 0.0)
        if now - last < interval_seconds:
            return False
        self._log_throttle[key] = now
        return True

    @property
    def availability(self) -> LiveAvailabilityTracker:
        return self._availability

    @property
    def current_window(self) -> SessionWindow | None:
        return self._current_window

    @property
    def current_window_source(self) -> str:
        return self._current_window_source

    @property
    def schedule_source(self) -> str:
        return self._schedule_source

    @property
    def index_http_status(self) -> int | None:
        return self._index_http_status

    @property
    def fallback_active(self) -> bool:
        return self._fallback_active

    @property
    def last_schedule_error(self) -> str | None:
        return self._last_schedule_error

    @property
    def fallback_source(self) -> LiveScheduleSource | None:
        return self._fallback_source

    def _set_schedule_state(
        self,
        *,
        source: str,
        fallback_active: bool,
        index_http_status: int | None = None,
        error: str | None = None,
        log_context: str | None = None,
    ) -> None:
        prev_source = self._schedule_source
        self._schedule_source = source
        self._fallback_active = fallback_active
        self._index_http_status = index_http_status
        self._last_schedule_error = error
        if source == "index" and prev_source != "index":
            if prev_source == "event_tracker":
                _LOGGER.info("switching back to index source")
            else:
                _LOGGER.info("schedule source selected: index")
            return
        if source == "event_tracker" and prev_source != "event_tracker":
            _LOGGER.info(
                "schedule source selected: event_tracker (%s)",
                log_context or "index-unavailable",
            )
            return
        if source == "none" and prev_source != "none":
            _LOGGER.info("schedule source selected: none (fail-closed idle)")

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
        with suppress(asyncio.CancelledError):
            while not self._stopped:
                window, source = await self._resolve_window()
                if window is None:
                    self._availability.set_state(False, "no-session-found")
                    await asyncio.sleep(IDLE_REFRESH.total_seconds())
                    continue
                now = dt_util.utcnow()
                if now < window.connect_at:
                    wait = max(
                        30.0,
                        min(
                            IDLE_REFRESH.total_seconds(),
                            (window.connect_at - now).total_seconds(),
                        ),
                    )
                    _LOGGER.debug(
                        "Next session %s opens in %.0fs (connect window %s – %s)",
                        window.label,
                        wait,
                        window.connect_at.isoformat(),
                        window.disconnect_at.isoformat(),
                    )
                    self._availability.set_state(
                        False, f"waiting-{window.session_name}"
                    )
                    await asyncio.sleep(wait)
                    continue
                await self._activate_window(window, source=source)

    async def _select_window(
        self,
        windows: list[SessionWindow],
        *,
        source: str,
    ) -> SessionWindow | None:
        if not windows:
            return None
        now = dt_util.utcnow()
        upcoming = [w for w in windows if now <= w.disconnect_at]
        if not upcoming:
            last = windows[-1]
            if source == "index" and last.path and await self._session_active(last):
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
                return extended
            if self._should_log(f"all_sessions_finished_{source}", interval_seconds=1800):
                _LOGGER.info(
                    "All sessions for source %s are finished (last disconnect %s UTC)",
                    source,
                    last.disconnect_at.isoformat(),
                )
            return None
        window = upcoming[0]
        _LOGGER.debug(
            "Selected session window %s from %s (start %s, end %s, connect %s, disconnect %s, now %s)",
            window.label,
            source,
            window.start_utc.isoformat(),
            window.end_utc.isoformat(),
            window.connect_at.isoformat(),
            window.disconnect_at.isoformat(),
            now.isoformat(),
        )
        return window

    async def _resolve_primary_window(self) -> SessionWindow | None:
        primary = await self._index_source.async_fetch_windows(
            pre_window=self._pre_window,
            post_window=self._post_window,
        )
        self._index_http_status = primary.index_http_status
        if primary.last_error:
            self._last_schedule_error = primary.last_error
        return await self._select_window(primary.windows, source="index")

    @staticmethod
    def _index_unavailable(primary: ScheduleFetchResult) -> tuple[bool, str]:
        if primary.last_error:
            return True, f"index error: {primary.last_error}"
        status = primary.index_http_status
        if status is not None and status != 200:
            return True, f"index unavailable: HTTP {status}"
        if not primary.windows:
            return True, "index unavailable: no valid session windows"
        return False, "index healthy"

    async def _resolve_window(self) -> tuple[SessionWindow | None, str]:
        primary = await self._index_source.async_fetch_windows(
            pre_window=self._pre_window,
            post_window=self._post_window,
        )
        self._index_http_status = primary.index_http_status
        if primary.last_error:
            self._last_schedule_error = primary.last_error

        primary_window = await self._select_window(primary.windows, source="index")
        if primary_window is not None:
            self._set_schedule_state(
                source="index",
                fallback_active=False,
                index_http_status=primary.index_http_status,
                error=primary.last_error,
            )
            return primary_window, "index"

        status = primary.index_http_status
        index_unavailable, fallback_context = self._index_unavailable(primary)
        if not index_unavailable:
            self._set_schedule_state(
                source="none",
                fallback_active=False,
                index_http_status=status,
                error=primary.last_error,
            )
            return None, "none"

        if self._fallback_source is None:
            self._set_schedule_state(
                source="none",
                fallback_active=False,
                index_http_status=status,
                error=primary.last_error,
            )
            return None, "none"

        fallback_result = await self._fallback_source.async_fetch_windows(
            pre_window=self._pre_window,
            post_window=self._post_window,
            active=self._fallback_active,
        )
        if fallback_result.last_error:
            self._last_schedule_error = fallback_result.last_error
        fallback_window = await self._select_window(
            fallback_result.windows, source="event_tracker"
        )
        if fallback_window is not None:
            self._set_schedule_state(
                source="event_tracker",
                fallback_active=True,
                index_http_status=status,
                error=fallback_result.last_error or primary.last_error,
                log_context=fallback_context,
            )
            return fallback_window, "event_tracker"

        self._set_schedule_state(
            source="none",
            fallback_active=False,
            index_http_status=status,
            error=fallback_result.last_error or primary.last_error,
        )
        return None, "none"

    async def _session_active(self, window: SessionWindow) -> bool:
        if not window.path:
            return False
        now = dt_util.utcnow()
        try:
            data = await self._fetch_json(
                _build_static_url(window.path, "SessionStatus.jsonStream")
            )
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
            _LOGGER.debug(
                "SessionStatus payload invalid for %s: %s", window.label, data
            )
            return False
        status = str(data.get("Status") or "").strip()
        started = str(data.get("Started") or "").strip()
        if status in SESSION_END_STATES:
            return False
        if started in SESSION_END_STATES:
            return False
        return True

    async def _activate_window(self, window: SessionWindow, *, source: str) -> None:
        self._current_window = window
        self._current_window_source = source
        label = window.label
        _LOGGER.info(
            "Arming live timing for %s via %s (connect=%s, disconnect=%s)",
            label,
            source,
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
            reason = await self._monitor_window(window, source=source)
        finally:
            self._bus.set_heartbeat_expectation(False)
            await self._bus.async_close()
            self._availability.set_state(False, f"finished-{window.session_name}")
            _LOGGER.info(
                "Live timing closed for %s (%s)",
                label,
                reason if "reason" in locals() else "no-reason",
            )
            self._current_window = None
            try:
                await self._session_coord.async_request_refresh()
            except Exception:  # noqa: BLE001
                _LOGGER.debug(
                    "Session index refresh failed after %s", label, exc_info=True
                )
            self._current_window_source = "none"

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
                    _LOGGER.debug(
                        "%s prime %s keys=%s",
                        window.label,
                        name,
                        list(payload.keys())[:5],
                    )
            except Exception:  # noqa: BLE001
                _LOGGER.debug(
                    "Failed priming %s for %s", name, window.label, exc_info=True
                )

    async def _monitor_window(self, window: SessionWindow, *, source: str) -> str:
        label = window.label
        reason = "disconnect-window-expired"
        max_disconnect_at = (
            window.disconnect_at + POST_WINDOW_EXTENSION_CAP
            if source == "index"
            else window.disconnect_at
        )
        while not self._stopped:
            await asyncio.sleep(ACTIVE_REFRESH.total_seconds())
            now = dt_util.utcnow()
            hb_age = self._bus.last_heartbeat_age()
            activity_age = self._bus.last_stream_activity_age(LIVE_ACTIVITY_STREAMS)
            if now >= window.disconnect_at:
                should_extend = (
                    source == "index"
                    and window.disconnect_at < max_disconnect_at
                    and (
                        (hb_age is not None and hb_age <= HEARTBEAT_DRAIN_SECONDS)
                        or (
                            activity_age is not None
                            and activity_age <= HEARTBEAT_DRAIN_SECONDS
                        )
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
                _LOGGER.info(
                    "Heartbeat aged %.0fs for %s; assuming feed idle", hb_age, label
                )
                reason = f"heartbeat-timeout-{hb_age:.0f}s"
                break
            if source == "event_tracker":
                mono_now = time.monotonic()
                if (
                    mono_now - self._last_primary_recovery_check
                    >= PRIMARY_RECOVERY_CHECK_INTERVAL.total_seconds()
                ):
                    self._last_primary_recovery_check = mono_now
                    candidate = await self._resolve_primary_window()
                    if candidate is not None:
                        _LOGGER.info(
                            "switching back to index source (recovered): %s",
                            candidate.label,
                        )
                        reason = "primary-source-recovered"
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
