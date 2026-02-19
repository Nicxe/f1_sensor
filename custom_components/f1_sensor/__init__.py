from __future__ import annotations
from contextlib import suppress

import json
import logging
import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from collections import deque
from urllib.parse import urljoin
from pathlib import Path
import time

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    API_URL,
    CONSTRUCTOR_STANDINGS_URL,
    DOMAIN,
    DRIVER_STANDINGS_URL,
    LAST_RACE_RESULTS_URL,
    LIVETIMING_INDEX_URL,
    PLATFORMS,
    SEASON_RESULTS_URL,
    SPRINT_RESULTS_URL,
    LATEST_TRACK_STATUS,
    FIA_DOCUMENTS_BASE_URL,
    FIA_SEASON_LIST_URL,
    FIA_SEASON_FALLBACK_URL,
    FIA_DOCS_POLL_INTERVAL,
    FIA_DOCS_FETCH_TIMEOUT,
    CONF_LIVE_DELAY_REFERENCE,
    CONF_OPERATION_MODE,
    CONF_REPLAY_FILE,
    CONF_REPLAY_START_REFERENCE,
    DEFAULT_LIVE_DELAY_REFERENCE,
    DEFAULT_OPERATION_MODE,
    DEFAULT_REPLAY_START_REFERENCE,
    OPERATION_MODE_DEVELOPMENT,
    OPERATION_MODE_LIVE,
    ENABLE_DEVELOPMENT_MODE_UI,
    RACE_SWITCH_GRACE,
    SUPPORTED_SENSOR_KEYS,
)
from .signalr import LiveBus
from .replay import ReplaySignalRClient
from .live_window import (
    EventTrackerScheduleSource,
    LiveAvailabilityTracker,
    LiveSessionSupervisor,
)
from .helpers import (
    build_user_agent,
    fetch_json,
    fetch_text,
    get_next_race,
    parse_fia_documents,
    PersistentCache,
)
from .formation_start import FormationStartTracker
from .live_delay import LiveDelayController, LiveDelayReferenceController
from .replay_start import ReplayStartReferenceController
from .calibration import LiveDelayCalibrationManager
from .replay_mode import ReplayController

_LOGGER = logging.getLogger(__name__)

_JOLPICA_STATS_KEY = "__jolpica_stats__"
_REPLAY_DELAY_REASONS = frozenset({"replay", "replay-mode", "replay-preparing"})


def _is_replay_delay_reason(reason: str | None) -> bool:
    return reason in _REPLAY_DELAY_REASONS


def _compute_session_fingerprint(index_payload: Any) -> str | None:
    """Best-effort fingerprint used to reset between sessions/weekends."""
    if not isinstance(index_payload, dict):
        return None
    try:
        meetings = index_payload.get("Meetings") or index_payload.get("meetings")
        sessions = index_payload.get("Sessions") or index_payload.get("sessions")
        minimal = {"Meetings": meetings, "Sessions": sessions}
        return json.dumps(minimal, sort_keys=True, default=str)[:20000]
    except Exception:
        return None


def _refresh_session_fingerprint(
    current: str | None, index_payload: Any
) -> tuple[str | None, bool]:
    fp = _compute_session_fingerprint(index_payload)
    if fp is None:
        return current, False
    if current is None:
        return fp, False
    return fp, fp != current


def _schedule_deliver_handle(
    loop: asyncio.AbstractEventLoop,
    handle: asyncio.Handle | None,
    delay: int,
    callback: Callable[[], None],
) -> asyncio.Handle | None:
    if handle:
        with suppress(Exception):
            handle.cancel()
    try:
        if delay > 0:
            return loop.call_later(delay, callback)
        return loop.call_soon(callback)
    except Exception:
        return None


def _schedule_message_delivery(
    loop: asyncio.AbstractEventLoop,
    handle: asyncio.Handle | None,
    delay: int,
    deliver: Callable[[dict], None],
    msg: dict,
) -> asyncio.Handle | None:
    return _schedule_deliver_handle(loop, handle, delay, lambda m=msg: deliver(m))


def _cancel_handle(handle: asyncio.Handle | None) -> asyncio.Handle | None:
    if handle:
        with suppress(Exception):
            handle.cancel()
    return None


def _call_unsub(unsub: Callable[[], None] | None) -> Callable[[], None] | None:
    if unsub:
        with suppress(Exception):
            unsub()
    return None


def _close_unsubs(unsubs: list[Callable[[], None]]) -> None:
    for u in list(unsubs):
        _call_unsub(u)
    unsubs.clear()


def _cancel_handles(handles: list[asyncio.Handle]) -> None:
    for handle in list(handles):
        with suppress(Exception):
            handle.cancel()
    handles.clear()


def _apply_delay_simple(instance: Any, seconds: int) -> None:
    new_delay = max(0, int(seconds or 0))
    if new_delay == instance._delay:
        return
    instance._delay = new_delay
    instance._deliver_handle = _cancel_handle(instance._deliver_handle)


def _init_stream_delay_state(
    instance: Any,
    delay_seconds: int,
    *,
    bus: LiveBus | None,
    delay_controller: LiveDelayController | None,
    live_state: LiveAvailabilityTracker | None,
) -> None:
    instance._deliver_handle = None
    instance._bus = bus
    instance._unsub = None
    instance._delay_listener = None
    instance._delay = max(0, int(delay_seconds or 0))
    instance._replay_mode = False
    if delay_controller is not None:
        instance._delay_listener = delay_controller.add_listener(instance.set_delay)
    instance._live_state_unsub = None
    if live_state is not None:
        instance._live_state_unsub = live_state.add_listener(
            instance._handle_live_state
        )


def _close_stream_delay_state(instance: Any) -> None:
    instance._unsub = _call_unsub(instance._unsub)
    instance._deliver_handle = _cancel_handle(instance._deliver_handle)
    instance._delay_listener = _call_unsub(instance._delay_listener)
    instance._live_state_unsub = _call_unsub(instance._live_state_unsub)


def _apply_delay_handles_only(
    instance: Any, seconds: int, handles: list[asyncio.Handle]
) -> None:
    new_delay = max(0, int(seconds or 0))
    if new_delay == instance._delay:
        return
    instance._delay = new_delay
    _cancel_handles(handles)


def _apply_delay_with_handles(
    instance: Any, seconds: int, handles: list[asyncio.Handle]
) -> None:
    new_delay = max(0, int(seconds or 0))
    if new_delay == instance._delay:
        return
    instance._delay = new_delay
    instance._deliver_handle = _cancel_handle(instance._deliver_handle)
    _cancel_handles(handles)


def _init_signalr_state(
    instance: Any,
    hass: HomeAssistant,
    session_coord: Any,
    delay_seconds: int,
    *,
    bus: LiveBus | None,
    delay_controller: LiveDelayController | None,
    live_state: LiveAvailabilityTracker | None,
) -> None:
    instance._session = async_get_clientsession(hass)
    instance._session_coord = session_coord
    instance.available = True
    instance._last_message = None
    instance.data_list = []
    instance._deliver_handle = None
    instance._bus = bus
    instance._unsub = None
    instance._delay_listener = None
    instance._delay = max(0, int(delay_seconds or 0))
    instance._replay_mode = False
    if delay_controller is not None:
        instance._delay_listener = delay_controller.add_listener(instance.set_delay)
    instance._live_state_unsub = None
    if live_state is not None:
        instance._live_state_unsub = live_state.add_listener(
            instance._handle_live_state
        )


class _SessionFingerprintMixin:
    _session_coord: Any
    _session_fingerprint: str | None

    def _on_session_index_update(self) -> None:
        fp, changed = _refresh_session_fingerprint(
            self._session_fingerprint, getattr(self._session_coord, "data", None)
        )
        if fp is None:
            return
        self._session_fingerprint = fp
        if changed:
            self._reset_store()


def _seed_driver_map_from_ergast(
    hass: HomeAssistant,
    config_entry: ConfigEntry | None,
    driver_map: dict[str, dict[str, Any]],
) -> None:
    """Fallback identity mapping using Ergast/Jolpica driver standings."""
    try:
        if not config_entry:
            return
        reg = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
        if not isinstance(reg, dict):
            return
        driver_coord = reg.get("driver_coordinator")
        data = getattr(driver_coord, "data", None) or {}
        standings = (
            (data.get("MRData") or {})
            .get("StandingsTable", {})
            .get("StandingsLists", [])
        )
        if not isinstance(standings, list) or not standings:
            return
        ds = (standings[0] or {}).get("DriverStandings", [])
        if not isinstance(ds, list):
            return
        for item in ds:
            if not isinstance(item, dict):
                continue
            driver = item.get("Driver") or {}
            if not isinstance(driver, dict):
                continue
            rn = str(driver.get("permanentNumber") or "").strip()
            if not rn:
                continue
            existing = driver_map.get(rn)
            if isinstance(existing, dict) and (
                existing.get("tla") or existing.get("name") or existing.get("team")
            ):
                continue
            code = driver.get("code") or driver.get("driverId")
            given = driver.get("givenName")
            family = driver.get("familyName")
            name = None
            try:
                parts = [p for p in (given, family) if p]
                name = " ".join(parts) if parts else None
            except Exception:
                name = None
            constructors = item.get("Constructors") or []
            team = None
            if isinstance(constructors, list) and constructors:
                c0 = constructors[0]
                if isinstance(c0, dict):
                    team = c0.get("name")
            driver_map[rn] = {"tla": code, "name": name, "team": team}
    except Exception:
        return


def _ensure_jolpica_stats_reporting(hass: HomeAssistant) -> None:
    """Register a dev-only periodic log of Jolpica network MISS counts."""
    if not ENABLE_DEVELOPMENT_MODE_UI:
        return
    root = hass.data.setdefault(DOMAIN, {})
    stats = root.get(_JOLPICA_STATS_KEY)
    if isinstance(stats, dict) and callable(stats.get("unsub")):
        return

    root[_JOLPICA_STATS_KEY] = {
        "since": dt_util.utcnow().isoformat(),
        "unsub": None,
    }

    async def _log_and_reset(_now) -> None:
        # Snapshot and reset counts (counts live in hass.data[DOMAIN][_JOLPICA_STATS_KEY])
        root2 = hass.data.get(DOMAIN, {}) or {}
        s = root2.get(_JOLPICA_STATS_KEY) or {}
        counts = s.get("counts") if isinstance(s, dict) else None
        if not isinstance(counts, dict) or not counts:
            # Still update since to avoid misleading "since" windows.
            with suppress(Exception):
                s["since"] = dt_util.utcnow().isoformat()
            return

        total = 0
        try:
            total = int(sum(int(v) for v in counts.values()))
        except Exception:
            total = 0

        # Top endpoints by MISS count
        try:
            top = sorted(counts.items(), key=lambda kv: int(kv[1]), reverse=True)[:10]
        except Exception:
            top = []

        since = s.get("since")
        until = dt_util.utcnow().isoformat()
        _LOGGER.info(
            "Jolpica MISS summary (dev) since=%s until=%s total=%s top=%s",
            since,
            until,
            total,
            [(k, int(v)) for k, v in top],
        )

        # Reset
        with suppress(Exception):
            s["counts"] = {}
            s["since"] = until

    unsub = async_track_time_interval(hass, _log_and_reset, timedelta(days=1))
    with suppress(Exception):
        root[_JOLPICA_STATS_KEY]["unsub"] = unsub


# Keep treating the current Grand Prix as "next" for a short period after
# lights out, so helpers and sensors do not jump to the following weekend
# immediately when a race starts.


class CoordinatorLogger(logging.LoggerAdapter):
    """Logger adapter that can suppress noisy manual-update debug lines."""

    def __init__(
        self,
        logger: logging.Logger,
        *,
        suppress_manual: bool = False,
        extra: dict | None = None,
    ) -> None:
        super().__init__(logger, extra or {})
        self._suppress_manual = suppress_manual

    def debug(self, msg: str, *args, **kwargs):
        if (
            self._suppress_manual
            and isinstance(msg, str)
            and msg.startswith("Manually updated ")
        ):
            return
        super().debug(msg, *args, **kwargs)


def coordinator_logger(
    name: str, *, suppress_manual: bool = False
) -> CoordinatorLogger:
    return CoordinatorLogger(
        logging.getLogger(f"{__name__}.{name}"),
        suppress_manual=suppress_manual,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration via config flow."""
    # Dev-only: periodically report how many Jolpica requests actually hit the network.
    _ensure_jolpica_stats_reporting(hass)
    # Build the effective set of enabled sensors.
    # ``disabled_sensors`` stores the keys the user explicitly unchecked.
    # Everything else (including new keys added in future versions) is enabled.
    raw_disabled = entry.data.get("disabled_sensors") or []
    disabled: set[str] = {k for k in raw_disabled if k in SUPPORTED_SENSOR_KEYS}
    enabled = SUPPORTED_SENSOR_KEYS - disabled

    # Determine which Jolpica/Ergast coordinators are actually required.
    need_race = any(
        k in enabled
        for k in (
            "next_race",
            "current_season",
            "weather",
            "race_week",
            "track_time",
            "fia_documents",
            "driver_points_progression",
            "constructor_points_progression",
            "season_results",
            "sprint_results",
            "calendar",
        )
    )
    need_driver = any(
        k in enabled for k in ("driver_standings", "driver_points_progression")
    )
    need_constructor = any(
        k in enabled
        for k in ("constructor_standings", "constructor_points_progression")
    )
    need_last_race = "last_race_results" in enabled
    need_season_results = any(
        k in enabled
        for k in (
            "season_results",
            "driver_points_progression",
            "constructor_points_progression",
        )
    )
    need_sprint_results = any(
        k in enabled
        for k in (
            "sprint_results",
            "driver_points_progression",
            "constructor_points_progression",
        )
    )
    need_fia_docs = "fia_documents" in enabled

    # Jolpica/Ergast TTL strategy (network-efficient; dashboards can tolerate delay).
    # Units: seconds.
    TTL_CURRENT = 24 * 3600  # current season schedule (rarely changes)
    TTL_STANDINGS = 24 * 3600  # standings change after race weekends
    TTL_LAST_RESULTS = 24 * 3600
    TTL_SPRINT = 24 * 3600
    # Season results are paginated; we refresh the latest page more often inside the coordinator.
    TTL_SEASON_STABLE_PAGE = 30 * 24 * 3600  # older pages: effectively static
    TTL_SEASON_RECENT_PAGE = 24 * 3600  # second-to-last-ish pages
    TTL_SEASON_LATEST_PAGE = 6 * 3600  # latest page: updated after weekends

    # Build custom User-Agent for Jolpica/Ergast. Note: HA's async_create_clientsession
    # does not reliably override the default UA in recent core versions, so we apply
    # this UA per request in the coordinators instead.
    ua_string = await build_user_agent(hass)
    http_session = async_get_clientsession(hass)
    _LOGGER.debug(
        "Configured User-Agent for Jolpica/Ergast (per-request): %s", ua_string
    )

    # Per-entry shared HTTP cache and in-flight maps (for Jolpica/Ergast only)
    http_cache: dict = {}
    http_inflight: dict = {}
    # Persistent cache (across restarts) for rarely-changing endpoints
    persisted = PersistentCache(hass, entry.entry_id)
    persisted_map = await persisted.load()

    # Seed in-memory cache from persisted content with conservative startup TTLs
    with suppress(Exception):
        from yarl import URL
        from time import monotonic as _mono

        now = _mono()
        wall_now = time.time()

        def _startup_ttl_for_key(k: str) -> int:
            """Return TTL for persisted cache entries (seconds).

            This is a conservative mapping that favors fewer network requests
            while ensuring the newest season results page refreshes within hours.
            """
            kk = str(k)
            if "/ergast/f1/current.json" in kk:
                return TTL_CURRENT
            if (
                "/ergast/f1/current/driverstandings.json" in kk
                or "/ergast/f1/current/constructorstandings.json" in kk
            ):
                return TTL_STANDINGS
            if "/ergast/f1/current/last/results.json" in kk:
                return TTL_LAST_RESULTS
            if "/ergast/f1/current/sprint.json" in kk:
                return TTL_SPRINT
            if "/ergast/f1/current/results.json" in kk:
                # Best-effort per-page TTL from offset (latest pages have higher offsets).
                try:
                    q = URL(kk).query
                    offset_raw = str(q.get("offset") or "0")
                    offset = int(offset_raw) if offset_raw.isdigit() else 0
                except Exception:
                    offset = 0
                # Heuristic: higher offsets tend to be nearer the latest results.
                if offset >= 300:
                    return TTL_SEASON_LATEST_PAGE
                if offset >= 100:
                    return TTL_SEASON_RECENT_PAGE
                return 7 * 24 * 3600
            # Default: keep a modest TTL
            return 6 * 3600

        for k, v in (persisted_map or {}).items():
            data = v.get("data") if isinstance(v, dict) else None
            if data is None:
                continue
            ttl = int(_startup_ttl_for_key(str(k)) or 0)
            saved_at = None
            try:
                saved_at = float(v.get("saved_at")) if isinstance(v, dict) else None
            except Exception:
                saved_at = None
            # Apply remaining TTL relative to saved_at, so old persisted data does not
            # get an artificially "fresh" expiry after restarts.
            try:
                age = max(0.0, wall_now - float(saved_at)) if saved_at else 0.0
            except Exception:
                age = 0.0
            remaining = max(0.0, float(ttl) - float(age))
            http_cache[k] = (now + remaining, data)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Seeded in-memory cache from persistent store with %d keys",
                len(http_cache),
            )
    race_coordinator = (
        F1DataCoordinator(
            hass,
            API_URL,
            "F1 Race Data Coordinator",
            session=http_session,
            user_agent=ua_string,
            cache=http_cache,
            inflight=http_inflight,
            ttl_seconds=TTL_CURRENT,
            persist_map=persisted_map,
            persist_save=persisted.schedule_save,
            config_entry=entry,
        )
        if need_race
        else None
    )
    driver_coordinator = (
        F1DataCoordinator(
            hass,
            DRIVER_STANDINGS_URL,
            "F1 Driver Standings Coordinator",
            session=http_session,
            user_agent=ua_string,
            cache=http_cache,
            inflight=http_inflight,
            ttl_seconds=TTL_STANDINGS,
            persist_map=persisted_map,
            persist_save=persisted.schedule_save,
            config_entry=entry,
        )
        if need_driver
        else None
    )
    constructor_coordinator = (
        F1DataCoordinator(
            hass,
            CONSTRUCTOR_STANDINGS_URL,
            "F1 Constructor Standings Coordinator",
            session=http_session,
            user_agent=ua_string,
            cache=http_cache,
            inflight=http_inflight,
            ttl_seconds=TTL_STANDINGS,
            persist_map=persisted_map,
            persist_save=persisted.schedule_save,
            config_entry=entry,
        )
        if need_constructor
        else None
    )
    last_race_coordinator = (
        F1DataCoordinator(
            hass,
            LAST_RACE_RESULTS_URL,
            "F1 Last Race Results Coordinator",
            session=http_session,
            user_agent=ua_string,
            cache=http_cache,
            inflight=http_inflight,
            ttl_seconds=TTL_LAST_RESULTS,
            persist_map=persisted_map,
            persist_save=persisted.schedule_save,
            config_entry=entry,
        )
        if need_last_race
        else None
    )
    season_results_coordinator = (
        F1SeasonResultsCoordinator(
            hass,
            SEASON_RESULTS_URL,
            "F1 Season Results Coordinator",
            session=http_session,
            user_agent=ua_string,
            cache=http_cache,
            inflight=http_inflight,
            ttl_seconds=TTL_SEASON_LATEST_PAGE,
            ttl_stable=TTL_SEASON_STABLE_PAGE,
            ttl_recent=TTL_SEASON_RECENT_PAGE,
            ttl_latest=TTL_SEASON_LATEST_PAGE,
            persist_map=persisted_map,
            persist_save=persisted.schedule_save,
            config_entry=entry,
            season_source=race_coordinator,
        )
        if need_season_results
        else None
    )
    sprint_results_coordinator = (
        F1SprintResultsCoordinator(
            hass,
            SPRINT_RESULTS_URL,
            "F1 Sprint Results Coordinator",
            session=http_session,
            user_agent=ua_string,
            cache=http_cache,
            inflight=http_inflight,
            ttl_seconds=TTL_SPRINT,
            persist_map=persisted_map,
            persist_save=persisted.schedule_save,
            config_entry=entry,
        )
        if need_sprint_results
        else None
    )
    fia_documents_coordinator = (
        FiaDocumentsCoordinator(
            hass,
            race_coordinator,
            session=http_session,
            cache=http_cache,
            inflight=http_inflight,
            ttl_seconds=FIA_DOCS_POLL_INTERVAL,
            persist_map=persisted_map,
            persist_save=persisted.schedule_save,
            config_entry=entry,
        )
        if (need_fia_docs and race_coordinator is not None)
        else None
    )
    year = dt_util.utcnow().year
    session_coordinator = LiveSessionCoordinator(hass, year, config_entry=entry)
    enable_rc = entry.data.get("enable_race_control", False)
    configured_delay = int(entry.data.get("live_delay_seconds", 0) or 0)
    delay_controller = LiveDelayController(hass, entry.entry_id)
    live_delay = await delay_controller.async_initialize(configured_delay)
    reference_controller = LiveDelayReferenceController(hass, entry.entry_id)
    await reference_controller.async_initialize(
        entry.data.get(CONF_LIVE_DELAY_REFERENCE, DEFAULT_LIVE_DELAY_REFERENCE)
    )
    replay_start_reference_controller = ReplayStartReferenceController(
        hass, entry.entry_id
    )
    await replay_start_reference_controller.async_initialize(
        entry.data.get(CONF_REPLAY_START_REFERENCE, DEFAULT_REPLAY_START_REFERENCE)
    )
    operation_mode = entry.data.get(CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE)
    replay_source = str(entry.data.get(CONF_REPLAY_FILE, "") or "").strip()
    transport_factory = None
    if operation_mode == OPERATION_MODE_DEVELOPMENT:
        if not replay_source:
            _LOGGER.warning(
                "Development mode selected but no replay file configured; falling back to live SignalR"
            )
            operation_mode = OPERATION_MODE_LIVE
        else:
            replay_path = Path(replay_source).expanduser()
            if not replay_path.exists():
                _LOGGER.warning(
                    "Replay file %s not found; falling back to live SignalR",
                    replay_path,
                )
                operation_mode = OPERATION_MODE_LIVE
            else:
                _LOGGER.info(
                    "Starting F1 Sensor in development replay mode using %s",
                    replay_path,
                )

                def _transport_factory() -> ReplaySignalRClient:
                    return ReplaySignalRClient(hass, replay_path)

                transport_factory = _transport_factory
    track_status_coordinator = None
    session_status_coordinator = None
    session_info_coordinator = None
    session_clock_coordinator = None
    weather_data_coordinator = None
    lap_count_coordinator = None
    race_control_coordinator = None
    top_three_coordinator = None
    hass.data[LATEST_TRACK_STATUS] = None
    # Create shared LiveBus (single SignalR connection). Live mode defers start to supervisor.
    session = async_get_clientsession(hass)
    live_bus = LiveBus(hass, session, transport_factory=transport_factory)
    live_supervisor: LiveSessionSupervisor | None = None
    event_tracker_source: EventTrackerScheduleSource | None = None
    live_state: LiveAvailabilityTracker
    if operation_mode == OPERATION_MODE_LIVE:
        event_tracker_source = EventTrackerScheduleSource(session)
        live_supervisor = LiveSessionSupervisor(
            hass,
            session_coordinator,
            live_bus,
            http_session=session,
            fallback_source=event_tracker_source,
        )
        await live_supervisor.async_start()
        live_state = live_supervisor.availability
    else:
        await live_bus.start()
        live_state = LiveAvailabilityTracker()
        live_state.set_state(True, "replay-mode")

    formation_tracker = None
    if operation_mode == OPERATION_MODE_LIVE:
        formation_tracker = FormationStartTracker(
            hass,
            bus=live_bus,
            http_session=session,
        )

    def _reload_entry():
        hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))

    # Create replay controller for historical session playback
    replay_controller = ReplayController(
        hass,
        entry.entry_id,
        http_session,
        live_bus,
        live_state=live_state,
        start_reference_controller=replay_start_reference_controller,
        formation_tracker=formation_tracker,
        on_replay_ended=live_supervisor.wake if live_supervisor else None,
    )
    await replay_controller.async_initialize()

    calibration_manager = LiveDelayCalibrationManager(
        hass,
        delay_controller,
        bus=live_bus,
        timeout_seconds=120,
        reload_callback=_reload_entry,
        reference_controller=reference_controller,
        formation_tracker=formation_tracker,
        replay_controller=replay_controller,
    )

    if enable_rc:
        track_status_coordinator = TrackStatusCoordinator(
            hass,
            session_coordinator,
            live_delay,
            bus=live_bus,
            config_entry=entry,
            delay_controller=delay_controller,
            live_state=live_state,
        )
        session_status_coordinator = SessionStatusCoordinator(
            hass,
            session_coordinator,
            live_delay,
            bus=live_bus,
            config_entry=entry,
            delay_controller=delay_controller,
            live_state=live_state,
        )
        session_info_coordinator = SessionInfoCoordinator(
            hass,
            session_coordinator,
            live_delay,
            bus=live_bus,
            config_entry=entry,
            delay_controller=delay_controller,
            live_state=live_state,
        )
        race_control_coordinator = RaceControlCoordinator(
            hass,
            session_coordinator,
            live_delay,
            bus=live_bus,
            config_entry=entry,
            delay_controller=delay_controller,
            live_state=live_state,
        )
        weather_data_coordinator = WeatherDataCoordinator(
            hass,
            session_coordinator,
            live_delay,
            bus=live_bus,
            config_entry=entry,
            delay_controller=delay_controller,
            live_state=live_state,
        )
        lap_count_coordinator = LapCountCoordinator(
            hass,
            session_coordinator,
            live_delay,
            bus=live_bus,
            config_entry=entry,
            delay_controller=delay_controller,
            live_state=live_state,
        )

    if race_coordinator:
        await race_coordinator.async_config_entry_first_refresh()
    if driver_coordinator:
        await driver_coordinator.async_config_entry_first_refresh()
    if constructor_coordinator:
        await constructor_coordinator.async_config_entry_first_refresh()
    if last_race_coordinator:
        await last_race_coordinator.async_config_entry_first_refresh()
    if season_results_coordinator:
        await season_results_coordinator.async_config_entry_first_refresh()
    if sprint_results_coordinator:
        await sprint_results_coordinator.async_config_entry_first_refresh()
    if fia_documents_coordinator:
        await fia_documents_coordinator.async_config_entry_first_refresh()
    await session_coordinator.async_config_entry_first_refresh()
    if track_status_coordinator:
        await track_status_coordinator.async_config_entry_first_refresh()
    if session_status_coordinator:
        await session_status_coordinator.async_config_entry_first_refresh()
    if session_info_coordinator:
        await session_info_coordinator.async_config_entry_first_refresh()
    if race_control_coordinator:
        await race_control_coordinator.async_config_entry_first_refresh()
    if weather_data_coordinator:
        await weather_data_coordinator.async_config_entry_first_refresh()
    if lap_count_coordinator:
        await lap_count_coordinator.async_config_entry_first_refresh()

    # Conditionally create live-stream coordinators (require enable_rc + sensor enabled).
    need_drivers = any(k in enabled for k in ("driver_list",))
    need_top_three = any(k in enabled for k in ("top_three",))
    need_team_radio = any(k in enabled for k in ("team_radio",))
    need_pitstops = any(k in enabled for k in ("pitstops",))
    need_championship_prediction = any(
        k in enabled for k in ("championship_prediction",)
    )
    need_session_clock = any(
        k in enabled
        for k in (
            "session_time_remaining",
            "session_time_elapsed",
            "race_time_to_three_hour_limit",
        )
    )
    if enable_rc and need_session_clock:
        session_clock_coordinator = SessionClockCoordinator(
            hass,
            session_coordinator,
            live_delay,
            bus=live_bus,
            config_entry=entry,
            delay_controller=delay_controller,
            live_state=live_state,
            live_supervisor=live_supervisor,
        )
        await session_clock_coordinator.async_config_entry_first_refresh()

    drivers_coordinator = None
    if enable_rc and need_drivers:
        drivers_coordinator = LiveDriversCoordinator(
            hass,
            session_coordinator,
            delay_seconds=live_delay,
            bus=live_bus,
            config_entry=entry,
            delay_controller=delay_controller,
            live_state=live_state,
        )
        await drivers_coordinator.async_config_entry_first_refresh()

    if enable_rc and need_top_three:
        top_three_coordinator = TopThreeCoordinator(
            hass,
            session_coordinator,
            live_delay,
            bus=live_bus,
            config_entry=entry,
            delay_controller=delay_controller,
            live_state=live_state,
        )
        await top_three_coordinator.async_config_entry_first_refresh()

    team_radio_coordinator = None
    if enable_rc and need_team_radio:
        team_radio_coordinator = TeamRadioCoordinator(
            hass,
            session_coordinator,
            live_delay,
            bus=live_bus,
            config_entry=entry,
            delay_controller=delay_controller,
            live_state=live_state,
        )
        await team_radio_coordinator.async_config_entry_first_refresh()

    pitstop_coordinator = None
    if enable_rc and need_pitstops:
        pitstop_coordinator = PitStopCoordinator(
            hass,
            session_coordinator,
            live_delay,
            bus=live_bus,
            config_entry=entry,
            delay_controller=delay_controller,
            live_state=live_state,
            history_limit=10,
            drivers_coordinator=drivers_coordinator,
        )
        await pitstop_coordinator.async_config_entry_first_refresh()

    championship_prediction_coordinator = None
    if enable_rc and need_championship_prediction:
        championship_prediction_coordinator = ChampionshipPredictionCoordinator(
            hass,
            session_coordinator,
            live_delay,
            bus=live_bus,
            config_entry=entry,
            delay_controller=delay_controller,
            live_state=live_state,
        )
        await championship_prediction_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "http_session": http_session,
        "user_agent": ua_string,
        "http_cache": http_cache,
        "http_inflight": http_inflight,
        "http_persist": persisted_map,
        "race_coordinator": race_coordinator,
        "driver_coordinator": driver_coordinator,
        "constructor_coordinator": constructor_coordinator,
        "last_race_coordinator": last_race_coordinator,
        "season_results_coordinator": season_results_coordinator,
        "sprint_results_coordinator": sprint_results_coordinator,
        "session_coordinator": session_coordinator,
        "track_status_coordinator": track_status_coordinator,
        "session_status_coordinator": session_status_coordinator,
        "session_info_coordinator": session_info_coordinator,
        "session_clock_coordinator": session_clock_coordinator,
        "race_control_coordinator": race_control_coordinator if enable_rc else None,
        "weather_data_coordinator": weather_data_coordinator if enable_rc else None,
        "lap_count_coordinator": lap_count_coordinator if enable_rc else None,
        "top_three_coordinator": top_three_coordinator,
        "team_radio_coordinator": team_radio_coordinator,
        "pitstop_coordinator": pitstop_coordinator,
        "championship_prediction_coordinator": championship_prediction_coordinator,
        "drivers_coordinator": drivers_coordinator,
        "fia_documents_coordinator": fia_documents_coordinator,
        "live_bus": live_bus,
        "live_supervisor": live_supervisor,
        "live_schedule_fallback_source": event_tracker_source,
        "live_state": live_state,
        "operation_mode": operation_mode,
        "replay_file": replay_source,
        "live_delay_controller": delay_controller,
        "delay_reference_controller": reference_controller,
        "replay_start_reference_controller": replay_start_reference_controller,
        "calibration_manager": calibration_manager,
        "formation_start_tracker": formation_tracker,
        "replay_controller": replay_controller,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


class WeatherDataCoordinator(DataUpdateCoordinator):
    """Coordinator for WeatherData updates using SignalR, mirrors Track/Session behavior."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: "LiveSessionCoordinator",
        delay_seconds: int = 0,
        bus: LiveBus | None = None,
        config_entry: ConfigEntry | None = None,
        delay_controller: LiveDelayController | None = None,
        live_state: LiveAvailabilityTracker | None = None,
    ):
        super().__init__(
            hass,
            coordinator_logger("weather", suppress_manual=True),
            name="F1 Weather Data Coordinator",
            update_interval=None,
            config_entry=config_entry,
        )
        _init_signalr_state(
            self,
            hass,
            session_coord,
            delay_seconds,
            bus=bus,
            delay_controller=delay_controller,
            live_state=live_state,
        )

    async def async_close(self, *_):
        self._unsub = _call_unsub(self._unsub)
        self._deliver_handle = _cancel_handle(self._deliver_handle)
        self._delay_listener = _call_unsub(self._delay_listener)
        self._live_state_unsub = _call_unsub(self._live_state_unsub)

    async def _async_update_data(self):
        return self._last_message

    def _on_bus_message(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        # Skip duplicate snapshots without timestamp to avoid heartbeat churn
        if self._should_skip_duplicate(msg):
            return
        delay = 0 if self._replay_mode else self._delay
        self._deliver_handle = _schedule_message_delivery(
            self.hass.loop, self._deliver_handle, delay, self._deliver, msg
        )

    @staticmethod
    def _has_timestamp(d: dict) -> bool:
        try:
            return any(k in d for k in ("Utc", "utc", "processedAt", "timestamp"))
        except Exception:
            return False

    def _should_skip_duplicate(self, msg: dict) -> bool:
        """Return True if msg is duplicate of last and has no timestamp.

        Compares core weather fields to avoid treating heartbeat-returned snapshots
        as fresh data.
        """
        if not isinstance(msg, dict):
            return False
        if self._has_timestamp(msg):
            return False
        last = self._last_message if isinstance(self._last_message, dict) else None
        if not last:
            return False
        keys = (
            "AirTemp",
            "TrackTemp",
            "Humidity",
            "Pressure",
            "Rainfall",
            "WindDirection",
            "WindSpeed",
        )
        try:
            for k in keys:
                if str(last.get(k)) != str(msg.get(k)):
                    return False
            return True
        except Exception:
            return False

    @staticmethod
    def _parse_message(data):
        if not isinstance(data, dict):
            return None
        messages = data.get("M")
        if isinstance(messages, list):
            for update in messages:
                args = update.get("A", [])
                if len(args) >= 2 and args[0] == "WeatherData":
                    return args[1]
        result = data.get("R")
        if isinstance(result, dict) and "WeatherData" in result:
            return result.get("WeatherData")
        return None

    def _deliver(self, msg: dict) -> None:
        self.available = True
        self._last_message = msg
        self.data_list = [msg]
        self.async_set_updated_data(msg)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            with suppress(Exception):
                keys = [k for k in (msg or {}).keys()][:6]
                _LOGGER.debug(
                    "WeatherData delivered at %s keys=%s",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                    keys,
                )

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        # Subscribe to shared live bus
        try:
            self._unsub = (
                self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")
            ).subscribe("WeatherData", self._on_bus_message)  # type: ignore[attr-defined]
        except Exception:
            self._unsub = None

    def set_delay(self, seconds: int) -> None:
        _apply_delay_simple(self, seconds)

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        # Ignore initial attach callback so we don't mark entities unavailable
        # before the LiveSessionSupervisor has decided whether to arm a window.
        if reason == "init":
            return
        self._replay_mode = _is_replay_delay_reason(reason)
        if self._replay_mode:
            self._deliver_handle = _cancel_handle(self._deliver_handle)
        self.available = is_live
        if not is_live:
            self._last_message = None
            self.data_list = []
            # Notify entities to clear their state
            self.async_set_updated_data(self._last_message)


class RaceControlCoordinator(DataUpdateCoordinator):
    """Coordinator for RaceControlMessages that publishes HA events for new items.

    - Mirrors logging/delay patterns from Track/Session coordinators
    - Publishes Home Assistant events only for new Race Control items (avoids replay on startup)
    """

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: "LiveSessionCoordinator",
        delay_seconds: int = 0,
        bus: LiveBus | None = None,
        config_entry: ConfigEntry | None = None,
        delay_controller: LiveDelayController | None = None,
        live_state: LiveAvailabilityTracker | None = None,
    ):
        super().__init__(
            hass,
            coordinator_logger("race_control", suppress_manual=True),
            name="F1 Race Control Coordinator",
            update_interval=None,
            config_entry=config_entry,
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._last_message = None
        self.data_list: list[dict] = []
        self._deliver_handles: list[asyncio.Handle] = []
        self._bus = bus
        self._unsub: Optional[Callable[[], None]] = None
        self._delay_listener: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))
        self._replay_mode = False
        if delay_controller is not None:
            self._delay_listener = delay_controller.add_listener(self.set_delay)
        # For duplicate filtering and startup replay suppression
        self._seen_ids_set: set[str] = set()
        self._seen_ids_order = deque(maxlen=1024)
        self._startup_cutoff: datetime | None = None
        self._dev_mode = (
            bool(config_entry)
            and config_entry.data.get(CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE)
            == OPERATION_MODE_DEVELOPMENT
        )
        self._live_state_unsub: Optional[Callable[[], None]] = None
        if live_state is not None:
            self._live_state_unsub = live_state.add_listener(self._handle_live_state)

    async def async_close(self, *_):
        if self._unsub:
            with suppress(Exception):
                self._unsub()
            self._unsub = None
        if self._deliver_handles:
            for handle in list(self._deliver_handles):
                with suppress(Exception):
                    handle.cancel()
            self._deliver_handles.clear()
        if self._delay_listener:
            with suppress(Exception):
                self._delay_listener()
            self._delay_listener = None
        if self._live_state_unsub:
            with suppress(Exception):
                self._live_state_unsub()
            self._live_state_unsub = None

    async def _async_update_data(self):
        return self._last_message

    @staticmethod
    def _parse_message(data):
        if not isinstance(data, dict):
            return None
        # Live feed entries
        messages = data.get("M")
        if isinstance(messages, list):
            for update in messages:
                args = update.get("A", [])
                if len(args) >= 2 and args[0] == "RaceControlMessages":
                    return args[1]
        # RPC response
        result = data.get("R")
        if isinstance(result, dict) and "RaceControlMessages" in result:
            return result.get("RaceControlMessages")
        return None

    @staticmethod
    def _extract_items(msg) -> list[dict]:
        # RaceControl feed can be a list of entries or a dict with list under key
        if isinstance(msg, list):
            return [m for m in msg if isinstance(m, dict)]
        if isinstance(msg, dict):
            # Some payloads contain { "Messages": [ ... ] }
            messages = msg.get("Messages")
            if isinstance(messages, list):
                return [m for m in messages if isinstance(m, dict)]
            # Some payloads contain { "Messages": { "1": {...}, "2": {...}, ... } }
            if isinstance(messages, dict) and messages:
                try:
                    numeric_keys = [k for k in messages.keys() if str(k).isdigit()]
                    # Sort by numeric key to preserve order if automations iterate
                    numeric_keys.sort(key=lambda x: int(x))
                    result: list[dict] = []
                    for key in numeric_keys:
                        val = messages.get(key)
                        if isinstance(val, dict):
                            item = dict(val)
                            # Provide stable id if not present
                            item.setdefault("id", int(key))
                            result.append(item)
                    if result:
                        return result
                except Exception:  # noqa: BLE001
                    _LOGGER.debug(
                        "RaceControlMessages: failed to normalize Messages dict",
                        exc_info=True,
                    )
            # Or a single message
            return [msg]
        return []

    @staticmethod
    def _message_id(item: dict) -> str:
        # Compose a stable id from typical fields
        try:
            ts = str(
                item.get("Utc")
                or item.get("utc")
                or item.get("processedAt")
                or item.get("timestamp")
                or ""
            )
            text = str(
                item.get("Message") or item.get("Text") or item.get("Flag") or ""
            )
            cat = str(item.get("Category") or item.get("CategoryType") or "")
            return f"{ts}|{cat}|{text}"
        except Exception:
            return json.dumps(item, sort_keys=True, default=str)

    def _on_bus_message(self, msg: dict) -> None:
        if not isinstance(msg, (dict, list)):
            return
        items = self._extract_items(msg)
        if not items:
            return
        for item in items:
            # Startup cutoff: ignore historical within 30s before now
            with suppress(Exception):
                ts_raw = (
                    item.get("Utc")
                    or item.get("utc")
                    or item.get("processedAt")
                    or item.get("timestamp")
                )
                if ts_raw:
                    ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        from datetime import timezone as _tz

                        ts = ts.replace(tzinfo=_tz.utc)
                    if self._startup_cutoff and ts < self._startup_cutoff:
                        continue
            ident = self._message_id(item)
            if ident in self._seen_ids_set:
                continue
            # Evict if needed then add
            if len(self._seen_ids_order) == self._seen_ids_order.maxlen:
                with suppress(Exception):
                    old = self._seen_ids_order.popleft()
                    self._seen_ids_set.discard(old)
            self._seen_ids_order.append(ident)
            self._seen_ids_set.add(ident)
            # Schedule/coalesce delivery
            self._schedule_deliver(item)

    def _schedule_deliver(self, item: dict) -> None:
        handle: asyncio.Handle | None = None

        def _callback(m=item):
            nonlocal handle
            try:
                self._deliver(m)
            finally:
                if handle:
                    with suppress(ValueError):
                        self._deliver_handles.remove(handle)
                    handle = None

        loop = self.hass.loop
        delay = 0 if self._replay_mode else self._delay
        if delay > 0:
            handle = loop.call_later(delay, _callback)
        else:
            handle = loop.call_soon(_callback)
        self._deliver_handles.append(handle)

    def set_delay(self, seconds: int) -> None:
        _apply_delay_handles_only(self, seconds, self._deliver_handles)

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        if reason == "init":
            return
        self._replay_mode = _is_replay_delay_reason(reason)
        if self._replay_mode and self._deliver_handles:
            for handle in list(self._deliver_handles):
                with suppress(Exception):
                    handle.cancel()
            self._deliver_handles.clear()
        self.available = is_live
        if not is_live:
            self._last_message = None
            self.data_list = []
            # Notify entities to clear their state
            self.async_set_updated_data(self._last_message)
        # In replay mode, disable the startup cutoff so historical messages are accepted
        if is_live and reason == "replay":
            self._startup_cutoff = None
            self._seen_ids_set.clear()
            self._seen_ids_order.clear()
            _LOGGER.debug("RaceControl: disabled startup cutoff for replay mode")

    def _deliver(self, item: dict) -> None:
        self.available = True
        # Maintain last message for visibility and parity with other coordinators
        self._last_message = item
        self.data_list = [item]
        self.async_set_updated_data(item)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            with suppress(Exception):
                cat = item.get("Category") or item.get("CategoryType")
                flag = item.get("Flag")
                text = item.get("Message") or item.get("Text")
                ts = item.get("Utc") or item.get("utc") or item.get("timestamp")
                _LOGGER.debug(
                    "RaceControl delivered at %s ts=%s cat=%s flag=%s text=%s",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                    ts,
                    cat,
                    flag,
                    (str(text)[:60] if isinstance(text, str) else text),
                )
        # Publish on HA event bus with a consistent event name
        try:
            self.hass.bus.async_fire(
                f"{DOMAIN}_race_control_event",
                {
                    "message": item,
                    "received_at": dt_util.utcnow().isoformat(timespec="seconds"),
                },
            )
        except Exception:
            _LOGGER.debug("RaceControl: Failed to publish event for item")

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        # Establish startup cutoff for replay suppression
        if self._dev_mode:
            self._startup_cutoff = None
        else:
            try:
                from datetime import timezone

                t0 = datetime.now(timezone.utc)
                self._startup_cutoff = t0 - timedelta(seconds=30)
            except Exception:
                self._startup_cutoff = None
        # Subscribe to LiveBus
        try:
            self._unsub = (
                self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")
            ).subscribe("RaceControlMessages", self._on_bus_message)  # type: ignore[attr-defined]
        except Exception:
            self._unsub = None


class LapCountCoordinator(DataUpdateCoordinator):
    """Coordinator for LapCount updates using SignalR, mirrors other live feeds."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: "LiveSessionCoordinator",
        delay_seconds: int = 0,
        bus: LiveBus | None = None,
        config_entry: ConfigEntry | None = None,
        delay_controller: LiveDelayController | None = None,
        live_state: LiveAvailabilityTracker | None = None,
    ):
        super().__init__(
            hass,
            coordinator_logger("lap_count", suppress_manual=True),
            name="F1 Lap Count Coordinator",
            update_interval=None,
            config_entry=config_entry,
        )
        _init_signalr_state(
            self,
            hass,
            session_coord,
            delay_seconds,
            bus=bus,
            delay_controller=delay_controller,
            live_state=live_state,
        )

    async def async_close(self, *_):
        self._unsub = _call_unsub(self._unsub)
        self._deliver_handle = _cancel_handle(self._deliver_handle)
        self._delay_listener = _call_unsub(self._delay_listener)
        self._live_state_unsub = _call_unsub(self._live_state_unsub)

    async def _async_update_data(self):
        return self._last_message

    @staticmethod
    def _parse_message(data):
        if not isinstance(data, dict):
            return None
        messages = data.get("M")
        if isinstance(messages, list):
            for update in messages:
                args = update.get("A", [])
                if len(args) >= 2 and args[0] == "LapCount":
                    return args[1]
        result = data.get("R")
        if isinstance(result, dict) and "LapCount" in result:
            return result.get("LapCount")
        return None

    def _on_bus_message(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        delay = 0 if self._replay_mode else self._delay
        self._deliver_handle = _schedule_message_delivery(
            self.hass.loop, self._deliver_handle, delay, self._deliver, msg
        )

    def _deliver(self, msg: dict) -> None:
        self.available = True
        self._last_message = msg
        self.data_list = [msg]
        self.async_set_updated_data(msg)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            with suppress(Exception):
                _LOGGER.debug(
                    "LapCount delivered at %s current=%s total=%s",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                    (msg or {}).get("CurrentLap") or (msg or {}).get("LapCount"),
                    (msg or {}).get("TotalLaps"),
                )

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        try:
            self._unsub = (
                self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")
            ).subscribe("LapCount", self._on_bus_message)  # type: ignore[attr-defined]
        except Exception:
            self._unsub = None

    def set_delay(self, seconds: int) -> None:
        _apply_delay_simple(self, seconds)

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        if reason == "init":
            return
        self._replay_mode = _is_replay_delay_reason(reason)
        if self._replay_mode:
            self._deliver_handle = _cancel_handle(self._deliver_handle)
        self.available = is_live
        if not is_live:
            self._last_message = None
            self.data_list = []
            # Notify entities to clear their state
            self.async_set_updated_data(self._last_message)


class TeamRadioCoordinator(DataUpdateCoordinator):
    """Coordinator for TeamRadio updates using SignalR.

    Normaliserar TeamRadio-flödet till en enkel struktur:
        data = {
            "latest": { ...normaliserad capture... } | None,
            "history": [ { ...capture... }, ... ],
        }
    """

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: "LiveSessionCoordinator",
        delay_seconds: int = 0,
        bus: LiveBus | None = None,
        config_entry: ConfigEntry | None = None,
        delay_controller: LiveDelayController | None = None,
        live_state: LiveAvailabilityTracker | None = None,
        history_limit: int = 20,
    ) -> None:
        super().__init__(
            hass,
            coordinator_logger("team_radio", suppress_manual=True),
            name="F1 Team Radio Coordinator",
            update_interval=None,
            config_entry=config_entry,
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._state: dict[str, Any] = {
            "latest": None,
            "history": [],
        }
        self._history_limit = max(1, int(history_limit or 20))
        self._deliver_handle: Optional[asyncio.Handle] = None
        self._bus = bus
        self._unsub: Optional[Callable[[], None]] = None
        self._delay_listener: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))
        self._replay_mode = False
        if delay_controller is not None:
            self._delay_listener = delay_controller.add_listener(self.set_delay)
        self._config_entry = config_entry
        self._dev_mode = (
            bool(config_entry)
            and config_entry.data.get(CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE)
            == OPERATION_MODE_DEVELOPMENT
        )
        self._replay_static_root: str | None = None
        self._live_state_unsub: Optional[Callable[[], None]] = None
        if live_state is not None:
            self._live_state_unsub = live_state.add_listener(self._handle_live_state)

    async def async_close(self, *_):
        self._unsub = _call_unsub(self._unsub)
        self._deliver_handle = _cancel_handle(self._deliver_handle)
        self._delay_listener = _call_unsub(self._delay_listener)
        self._live_state_unsub = _call_unsub(self._live_state_unsub)

    async def _async_update_data(self):
        return self._state

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        if reason == "init":
            return
        self._replay_mode = _is_replay_delay_reason(reason)
        if self._replay_mode:
            self._deliver_handle = _cancel_handle(self._deliver_handle)
        self.available = is_live
        if not is_live:
            self._state = {"latest": None, "history": []}
            # Notify entities to clear their state
            self.async_set_updated_data(self._state)

    def set_delay(self, seconds: int) -> None:
        _apply_delay_simple(self, seconds)

    def _on_bus_message(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        delay = 0 if self._replay_mode else self._delay
        self._deliver_handle = _schedule_message_delivery(
            self.hass.loop, self._deliver_handle, delay, self._deliver, msg
        )

    @staticmethod
    def _normalize_captures(payload: dict) -> list[dict]:
        """Extract a flat list of capture dicts from a TeamRadio payload."""
        if not isinstance(payload, dict):
            return []
        captures = payload.get("Captures")
        static_root = payload.get("_static_root")
        result: list[dict] = []
        try:
            if isinstance(captures, list):
                for item in captures:
                    if isinstance(item, dict):
                        copy = dict(item)
                        if static_root and "_static_root" not in copy:
                            copy["_static_root"] = static_root
                        result.append(copy)
            elif isinstance(captures, dict):
                # Some dumps use numeric keys: {"Captures":{"1":{...},"2":{...}}}
                numeric_keys = [k for k in captures.keys() if str(k).isdigit()]
                if numeric_keys:
                    numeric_keys.sort(key=lambda x: int(x))
                    for key in numeric_keys:
                        val = captures.get(key)
                        if isinstance(val, dict):
                            copy = dict(val)
                            if static_root and "_static_root" not in copy:
                                copy["_static_root"] = static_root
                            result.append(copy)
                else:
                    for val in captures.values():
                        if isinstance(val, dict):
                            copy = dict(val)
                            if static_root and "_static_root" not in copy:
                                copy["_static_root"] = static_root
                            result.append(copy)
        except Exception:
            return result
        return result

    def _deliver(self, msg: dict) -> None:
        self.available = True
        # In replay/development mode, try to provide a static root URL even if the
        # transport did not annotate the payload (robust against file encoding quirks).
        with suppress(Exception):
            if (
                self._dev_mode
                and self._replay_static_root
                and isinstance(msg, dict)
                and "_static_root" not in msg
            ):
                msg = dict(msg)
                msg["_static_root"] = self._replay_static_root
        captures = self._normalize_captures(msg)
        if not captures:
            return
        # Use the last capture as "latest"
        latest = captures[-1]
        history: list[dict] = list(self._state.get("history") or [])
        history.extend(captures)
        if len(history) > self._history_limit:
            history = history[-self._history_limit :]
        self._state = {
            "latest": latest,
            "history": history,
        }
        self.async_set_updated_data(self._state)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            with suppress(Exception):
                _LOGGER.debug(
                    "TeamRadio delivered at %s latest=%s history_len=%s",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                    {
                        "Utc": latest.get("Utc"),
                        "RacingNumber": latest.get("RacingNumber"),
                        "Path": latest.get("Path"),
                    },
                    len(history),
                )

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        # Best-effort: derive static root from the replay file's URL header so sensors
        # can build full clip URLs during replay.
        if self._dev_mode and self._config_entry:
            with suppress(Exception):
                from pathlib import Path as _Path

                replay_source = str(
                    self._config_entry.data.get(CONF_REPLAY_FILE, "") or ""
                ).strip()
                if replay_source:
                    replay_path = _Path(replay_source).expanduser()

                    def _read_static_root() -> str | None:
                        try:
                            with replay_path.open("r", encoding="utf-8") as fh:
                                # Scan a bit deeper than the first non-empty line; some dumps
                                # may have the URL header later (or be prepended with comments).
                                # We keep this bounded to avoid reading huge files in full.
                                max_lines = 500
                                for idx, raw in enumerate(fh):
                                    if idx >= max_lines:
                                        break
                                    line = raw.lstrip("\ufeff").strip()
                                    if not line:
                                        continue
                                    if line.upper().startswith("URL:"):
                                        try:
                                            _, url = line.split(":", 1)
                                        except ValueError:
                                            return None
                                        full_url = url.strip().rstrip("/")
                                        if not full_url:
                                            return None
                                        parts = full_url.split("/")
                                        if len(parts) <= 1:
                                            return None
                                        # Drop the final segment (e.g. TeamRadio.jsonStream)
                                        return "/".join(parts[:-1])
                        except Exception:
                            return None
                        return None

                    static_root = await self.hass.async_add_executor_job(
                        _read_static_root
                    )
                    if static_root:
                        self._replay_static_root = str(static_root)
        try:
            self._unsub = (
                self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")
            ).subscribe("TeamRadio", self._on_bus_message)  # type: ignore[attr-defined]
        except Exception:
            self._unsub = None


class PitStopCoordinator(_SessionFingerprintMixin, DataUpdateCoordinator):
    """Coordinator aggregating live pit stops for all cars.

    Exposes:
        data = {
          "total_stops": int,
          "cars": {
            "44": {"count": 2, "stops": [ {stop}, ... ]},
            ...
          },
          "last_update": "2025-12-07T14:07:19+00:00",
        }
    """

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: "LiveSessionCoordinator",
        delay_seconds: int = 0,
        bus: LiveBus | None = None,
        config_entry: ConfigEntry | None = None,
        delay_controller: LiveDelayController | None = None,
        live_state: LiveAvailabilityTracker | None = None,
        history_limit: int = 10,
        drivers_coordinator: "LiveDriversCoordinator | None" = None,
    ) -> None:
        super().__init__(
            hass,
            coordinator_logger("pitstops", suppress_manual=True),
            name="F1 PitStop Coordinator",
            update_interval=None,
            config_entry=config_entry,
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._bus = bus
        self._config_entry = config_entry
        self._unsubs: list[Callable[[], None]] = []
        self._drivers_unsub: Optional[Callable[[], None]] = None
        self._delay_listener: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))
        self._replay_mode = False
        if delay_controller is not None:
            self._delay_listener = delay_controller.add_listener(self.set_delay)
        self._live_state_unsub: Optional[Callable[[], None]] = None
        if live_state is not None:
            self._live_state_unsub = live_state.add_listener(self._handle_live_state)

        self._session_unsub: Optional[Callable[[], None]] = None
        self._session_fingerprint: str | None = None

        self._history_limit = max(1, int(history_limit or 10))
        self._by_car: dict[str, list[dict]] = {}
        self._dedup: set[tuple] = set()
        self._driver_map: dict[str, dict[str, Any]] = {}
        self._deliver_handle: Optional[asyncio.Handle] = None
        self._drivers_coord = drivers_coordinator

        self._state: dict[str, Any] = {
            "total_stops": 0,
            "cars": {},
            "last_update": None,
        }

    async def async_close(self, *_):
        _close_unsubs(self._unsubs)
        self._deliver_handle = _cancel_handle(self._deliver_handle)
        self._delay_listener = _call_unsub(self._delay_listener)
        self._live_state_unsub = _call_unsub(self._live_state_unsub)
        self._drivers_unsub = _call_unsub(self._drivers_unsub)
        self._session_unsub = _call_unsub(self._session_unsub)

    async def _async_update_data(self):
        return self._state

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        if reason == "init":
            return
        self._replay_mode = _is_replay_delay_reason(reason)
        if self._replay_mode:
            self._deliver_handle = _cancel_handle(self._deliver_handle)
        self.available = is_live
        if not is_live:
            self._reset_store()

    def set_delay(self, seconds: int) -> None:
        _apply_delay_simple(self, seconds)

    def _reset_store(self) -> None:
        self._by_car = {}
        self._dedup = set()
        self._state = {"total_stops": 0, "cars": {}, "last_update": None}
        with suppress(Exception):
            self.async_set_updated_data(self._state)

    @staticmethod
    def _parse_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            if isinstance(value, int):
                return value
            text = str(value).strip()
            if not text:
                return None
            if text.isdigit():
                return int(text)
            return int(float(text))
        except Exception:
            return None

    @staticmethod
    def _parse_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return float(value)
            text = str(value).strip()
            if not text:
                return None
            return float(text)
        except Exception:
            return None

    def _schedule_deliver(self) -> None:
        delay = 0 if self._replay_mode else self._delay
        self._deliver_handle = _schedule_deliver_handle(
            self.hass.loop, self._deliver_handle, delay, self._deliver
        )

    def _add_stop(self, racing_number: str, stop: dict) -> None:
        rn = str(racing_number or "").strip()
        if not rn:
            return
        lap = self._parse_int(stop.get("lap"))
        ts = stop.get("timestamp")
        pit_stop_time = self._parse_float(stop.get("pit_stop_time"))
        pit_lane_time = self._parse_float(stop.get("pit_lane_time"))

        # Dedup: prefer timestamp when present, else fall back to lap/times.
        if ts:
            key = (rn, "ts", str(ts), pit_lane_time, pit_stop_time)
        else:
            key = (rn, "no_ts", lap, pit_lane_time, pit_stop_time)
        if key in self._dedup:
            return
        self._dedup.add(key)

        entry = {
            "lap": lap,
            "timestamp": str(ts) if ts else None,
            "pit_stop_time": pit_stop_time,
            "pit_lane_time": pit_lane_time,
            "pit_delta": None,
        }
        self._maybe_update_pit_delta(rn, entry)
        lst = self._by_car.setdefault(rn, [])
        lst.append(entry)
        if len(lst) > self._history_limit:
            self._by_car[rn] = lst[-self._history_limit :]

    def _ingest_pitstopseries(self, msg: dict) -> None:
        pit_times = (msg or {}).get("PitTimes")
        if not isinstance(pit_times, dict):
            return
        for rn, entries in pit_times.items():
            if isinstance(entries, list):
                iterable = entries
            elif isinstance(entries, dict):
                iterable = list(entries.values())
            else:
                continue
            for item in iterable:
                if not isinstance(item, dict):
                    continue
                pitstop = item.get("PitStop")
                if not isinstance(pitstop, dict):
                    continue
                timestamp = item.get("Timestamp")
                self._add_stop(
                    str(pitstop.get("RacingNumber") or rn),
                    {
                        "lap": pitstop.get("Lap"),
                        "timestamp": timestamp,
                        "pit_stop_time": pitstop.get("PitStopTime"),
                        "pit_lane_time": pitstop.get("PitLaneTime"),
                    },
                )

    def _on_driverlist(self, payload: dict) -> None:
        """Merge DriverList into an rn -> {tla,name,team} mapping."""
        if not isinstance(payload, dict):
            return
        for rn, info in (payload or {}).items():
            if not isinstance(info, dict):
                continue
            racing_number = str(info.get("RacingNumber") or rn).strip()
            if not racing_number:
                continue
            self._driver_map[racing_number] = {
                "tla": info.get("Tla"),
                "name": info.get("FullName") or info.get("BroadcastName"),
                "team": info.get("TeamName"),
            }

    def _seed_driver_map_from_ergast(self) -> None:
        """Fallback identity mapping using Ergast/Jolpica driver standings.

        This is especially important in replay mode where only one stream dump
        (e.g. PitStopSeries) is replayed, meaning DriverList frames are absent.
        """
        _seed_driver_map_from_ergast(
            self.hass,
            self._config_entry,
            self._driver_map,
        )

    def _on_bus_pitstopseries(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        self._ingest_pitstopseries(msg)
        self._schedule_deliver()

    def _deliver(self) -> None:
        self.available = True
        self._refresh_pit_deltas()
        cars: dict[str, Any] = {}
        total = 0
        try:
            for rn, stops in sorted(
                self._by_car.items(),
                key=lambda kv: int(str(kv[0])) if str(kv[0]).isdigit() else str(kv[0]),
            ):
                lst = list(stops or [])
                ident = self._get_identity(str(rn))
                cars[str(rn)] = {
                    "tla": ident.get("tla"),
                    "name": ident.get("name"),
                    "team": ident.get("team"),
                    "count": len(lst),
                    "stops": lst,
                }
                total += len(lst)
        except Exception:
            cars = {
                str(rn): {"count": len(stops or []), "stops": list(stops or [])}
                for rn, stops in (self._by_car or {}).items()
            }
            try:
                total = sum(
                    v.get("count", 0) for v in cars.values() if isinstance(v, dict)
                )
            except Exception:
                total = 0

        self._state = {
            "total_stops": int(total),
            "cars": cars,
            "last_update": dt_util.utcnow().isoformat(timespec="seconds"),
        }
        self.async_set_updated_data(self._state)

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        # Seed identity mapping from Ergast/Jolpica so replay mode still shows TLA/name/team.
        self._seed_driver_map_from_ergast()
        # Reset when LiveTiming index changes (session/weekend rollover)
        try:
            self._session_fingerprint = _compute_session_fingerprint(
                getattr(self._session_coord, "data", None)
            )
            self._session_unsub = self._session_coord.async_add_listener(
                self._on_session_index_update
            )
        except Exception:
            self._session_unsub = None
        # Subscribe to shared live bus streams
        bus = self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")
        with suppress(Exception):
            self._unsubs.append(bus.subscribe("DriverList", self._on_driverlist))  # type: ignore[attr-defined]
        with suppress(Exception):
            self._unsubs.append(
                bus.subscribe("PitStopSeries", self._on_bus_pitstopseries)  # type: ignore[attr-defined]
            )
        if self._drivers_coord is not None:
            try:
                self._drivers_unsub = self._drivers_coord.async_add_listener(
                    self._on_drivers_update
                )
            except Exception:
                self._drivers_unsub = None

    def _on_drivers_update(self) -> None:
        changed = self._refresh_pit_deltas()
        if self._refresh_driver_map_from_coordinator():
            changed = True
        if changed:
            self._schedule_deliver()

    def _refresh_driver_map_from_coordinator(self) -> bool:
        updated = False
        if not self._drivers_coord:
            return False
        data = self._drivers_coord.data
        if not isinstance(data, dict):
            return False
        drivers = data.get("drivers")
        if not isinstance(drivers, dict):
            return False
        for rn, info in drivers.items():
            if not isinstance(info, dict):
                continue
            identity = info.get("identity")
            if not isinstance(identity, dict):
                continue
            key = str(rn)
            entry = self._driver_map.setdefault(key, {})
            new_tla = identity.get("tla")
            new_name = identity.get("name")
            new_team = identity.get("team")
            if new_tla and entry.get("tla") != new_tla:
                entry["tla"] = new_tla
                updated = True
            if new_name and entry.get("name") != new_name:
                entry["name"] = new_name
                updated = True
            if new_team and entry.get("team") != new_team:
                entry["team"] = new_team
                updated = True
        return updated

    def _get_identity(self, rn: str) -> dict[str, Any]:
        ident = (
            self._driver_map.get(str(rn), {})
            if isinstance(self._driver_map, dict)
            else {}
        )
        if ident.get("tla") or ident.get("name") or ident.get("team"):
            return ident
        if not self._drivers_coord:
            return ident
        data = self._drivers_coord.data
        if not isinstance(data, dict):
            return ident
        drivers = data.get("drivers")
        if not isinstance(drivers, dict):
            return ident
        info = drivers.get(str(rn))
        if not isinstance(info, dict):
            return ident
        identity = info.get("identity")
        if not isinstance(identity, dict):
            return ident
        return {
            "tla": identity.get("tla"),
            "name": identity.get("name"),
            "team": identity.get("team"),
        }

    def _refresh_pit_deltas(self) -> bool:
        changed = False
        if not self._drivers_coord:
            return False
        for rn, stops in (self._by_car or {}).items():
            if not isinstance(stops, list):
                continue
            for stop in stops:
                if not isinstance(stop, dict):
                    continue
                if self._maybe_update_pit_delta(str(rn), stop):
                    changed = True
        return changed

    def _maybe_update_pit_delta(self, rn: str, stop: dict) -> bool:
        if stop.get("pit_delta") is not None:
            return False
        delta = self._compute_pit_delta(rn, stop)
        if delta is None:
            with suppress(Exception):
                lap = self._parse_int(stop.get("lap"))
                if lap is not None:
                    laps = self._get_lap_history(rn) or {}
                    if str(lap + 1) not in laps:
                        _LOGGER.debug(
                            "Pit delta pending for %s (lap %s): waiting for lap %s time",
                            rn,
                            lap,
                            lap + 1,
                        )
            return False
        stop["pit_delta"] = delta
        with suppress(Exception):
            lap = self._parse_int(stop.get("lap"))
            _LOGGER.debug(
                "Pit delta computed for %s (lap %s): %.3fs",
                rn,
                lap if lap is not None else "?",
                delta,
            )
        return True

    def _compute_pit_delta(self, rn: str, stop: dict) -> float | None:
        lap = self._parse_int(stop.get("lap"))
        if lap is None:
            return None
        laps = self._get_lap_history(rn)
        if not laps:
            return None
        pit_secs = self._select_pit_lap_secs(laps, lap)
        if pit_secs is None:
            return None
        normal_secs = self._select_reference_lap_secs(laps, lap)
        if normal_secs is None:
            return None
        return round(pit_secs - normal_secs, 3)

    def _get_lap_history(self, rn: str) -> dict[str, str] | None:
        if not self._drivers_coord:
            return None
        data = self._drivers_coord.data
        if not isinstance(data, dict):
            return None
        drivers = data.get("drivers")
        if not isinstance(drivers, dict):
            return None
        info = drivers.get(str(rn))
        if not isinstance(info, dict):
            return None
        lap_history = info.get("lap_history")
        if not isinstance(lap_history, dict):
            return None
        laps = lap_history.get("laps")
        if not isinstance(laps, dict):
            return None
        return laps

    @staticmethod
    def _select_pit_lap_secs(laps: dict[str, str], lap: int) -> float | None:
        next_lap_time = laps.get(str(lap + 1))
        if next_lap_time is None:
            return None
        candidates: list[float] = []
        for lap_time in (laps.get(str(lap)), next_lap_time):
            lap_secs = LiveDriversCoordinator._parse_laptime_secs(lap_time)
            if lap_secs is not None:
                candidates.append(lap_secs)
        if not candidates:
            return None
        return max(candidates)

    @staticmethod
    def _select_reference_lap_secs(laps: dict[str, str], lap: int) -> float | None:
        candidates: list[float] = []
        for offset in (1, 2, 3):
            lap_time = laps.get(str(lap - offset))
            lap_secs = LiveDriversCoordinator._parse_laptime_secs(lap_time)
            if lap_secs is not None:
                candidates.append(lap_secs)
        if not candidates:
            for offset in (2, 3, 4):
                lap_time = laps.get(str(lap + offset))
                lap_secs = LiveDriversCoordinator._parse_laptime_secs(lap_time)
                if lap_secs is not None:
                    candidates.append(lap_secs)
        if not candidates:
            return None
        candidates.sort()
        mid = len(candidates) // 2
        if len(candidates) % 2 == 1:
            return candidates[mid]
        return (candidates[mid - 1] + candidates[mid]) / 2.0


class ChampionshipPredictionCoordinator(
    _SessionFingerprintMixin, DataUpdateCoordinator
):
    """Coordinator for ChampionshipPrediction updates using SignalR.

    Maintains merged state across incremental payloads:
        data = {
          "drivers": { rn: {...merged fields...}, ... },
          "teams": { team_key: {...merged fields...}, ... },
          "predicted_driver_p1": { "racing_number": str|None, "tla": str|None, "points": float|None, "entry": dict|None },
          "predicted_team_p1": { "team_key": str|None, "team_name": str|None, "points": float|None, "entry": dict|None },
          "last_update": ISO string,
        }
    """

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: "LiveSessionCoordinator",
        delay_seconds: int = 0,
        bus: LiveBus | None = None,
        config_entry: ConfigEntry | None = None,
        delay_controller: LiveDelayController | None = None,
        live_state: LiveAvailabilityTracker | None = None,
    ) -> None:
        super().__init__(
            hass,
            coordinator_logger("championship_prediction", suppress_manual=True),
            name="F1 Championship Prediction Coordinator",
            update_interval=None,
            config_entry=config_entry,
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._bus = bus
        self._config_entry = config_entry

        self._unsubs: list[Callable[[], None]] = []
        self._delay_listener: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))
        self._replay_mode = False
        if delay_controller is not None:
            self._delay_listener = delay_controller.add_listener(self.set_delay)

        self._live_state_unsub: Optional[Callable[[], None]] = None
        if live_state is not None:
            self._live_state_unsub = live_state.add_listener(self._handle_live_state)

        self._session_unsub: Optional[Callable[[], None]] = None
        self._session_fingerprint: str | None = None

        self._drivers: dict[str, dict[str, Any]] = {}
        self._teams: dict[str, dict[str, Any]] = {}
        self._driver_map: dict[str, dict[str, Any]] = {}

        self._deliver_handle: Optional[asyncio.Handle] = None
        self._state: dict[str, Any] = {
            "drivers": {},
            "teams": {},
            "predicted_driver_p1": {
                "racing_number": None,
                "tla": None,
                "points": None,
                "entry": None,
            },
            "predicted_team_p1": {
                "team_key": None,
                "team_name": None,
                "points": None,
                "entry": None,
            },
            "last_update": None,
        }

    async def async_close(self, *_):
        _close_unsubs(self._unsubs)
        self._deliver_handle = _cancel_handle(self._deliver_handle)
        self._delay_listener = _call_unsub(self._delay_listener)
        self._live_state_unsub = _call_unsub(self._live_state_unsub)
        self._session_unsub = _call_unsub(self._session_unsub)

    async def _async_update_data(self):
        return self._state

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        if reason == "init":
            return
        self._replay_mode = _is_replay_delay_reason(reason)
        if self._replay_mode:
            self._deliver_handle = _cancel_handle(self._deliver_handle)
        self.available = is_live
        if not is_live:
            self._reset_store()

    def set_delay(self, seconds: int) -> None:
        _apply_delay_simple(self, seconds)

    def _reset_store(self) -> None:
        self._drivers = {}
        self._teams = {}
        self._state = {
            "drivers": {},
            "teams": {},
            "predicted_driver_p1": {
                "racing_number": None,
                "tla": None,
                "points": None,
                "entry": None,
            },
            "predicted_team_p1": {
                "team_key": None,
                "team_name": None,
                "points": None,
                "entry": None,
            },
            "last_update": None,
        }
        with suppress(Exception):
            self.async_set_updated_data(self._state)

    def _schedule_deliver(self) -> None:
        delay = 0 if self._replay_mode else self._delay
        self._deliver_handle = _schedule_deliver_handle(
            self.hass.loop, self._deliver_handle, delay, self._deliver
        )

    @staticmethod
    def _deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
        """Shallow/deep merge dicts: nested dicts are merged recursively."""
        if not isinstance(dst, dict):
            dst = {}
        for k, v in (src or {}).items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                dst[k] = ChampionshipPredictionCoordinator._deep_merge(
                    dst.get(k) or {}, v
                )
            else:
                dst[k] = v
        return dst

    def _ingest_prediction(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        drivers = msg.get("Drivers")
        if isinstance(drivers, dict):
            for key, patch in drivers.items():
                if not isinstance(patch, dict):
                    continue
                rn = str(patch.get("RacingNumber") or key).strip()
                if not rn:
                    continue
                cur = self._drivers.get(rn) or {}
                # Ensure RacingNumber is stable
                cur.setdefault("RacingNumber", rn)
                self._drivers[rn] = self._deep_merge(cur, patch)

        teams = msg.get("Teams")
        if isinstance(teams, dict):
            for team_key, patch in teams.items():
                if not isinstance(patch, dict):
                    continue
                tk = str(team_key).strip()
                if not tk:
                    continue
                cur = self._teams.get(tk) or {}
                cur.setdefault("TeamKey", tk)
                self._teams[tk] = self._deep_merge(cur, patch)

    def _on_driverlist(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        for rn, info in (payload or {}).items():
            if not isinstance(info, dict):
                continue
            racing_number = str(info.get("RacingNumber") or rn).strip()
            if not racing_number:
                continue
            self._driver_map[racing_number] = {
                "tla": info.get("Tla"),
                "name": info.get("FullName") or info.get("BroadcastName"),
                "team": info.get("TeamName"),
            }
        # identity update can change sensor state even without prediction deltas
        self._schedule_deliver()

    def _seed_driver_map_from_ergast(self) -> None:
        """Fallback identity mapping using Ergast/Jolpica driver standings (replay-friendly)."""
        _seed_driver_map_from_ergast(
            self.hass,
            self._config_entry,
            self._driver_map,
        )

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            if isinstance(value, int):
                return value
            text = str(value).strip()
            if not text:
                return None
            if text.isdigit():
                return int(text)
            return int(float(text))
        except Exception:
            return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return float(value)
            text = str(value).strip()
            if not text:
                return None
            return float(text)
        except Exception:
            return None

    def _pick_predicted_driver_p1(self) -> tuple[str | None, dict | None]:
        best_rn = None
        best_entry = None
        best_pos = None
        for rn, entry in (self._drivers or {}).items():
            if not isinstance(entry, dict):
                continue
            pos = self._to_int(entry.get("PredictedPosition"))
            if pos is None:
                continue
            if best_pos is None or pos < best_pos:
                best_pos = pos
                best_rn = str(entry.get("RacingNumber") or rn)
                best_entry = entry
        return best_rn, best_entry

    def _pick_predicted_team_p1(self) -> tuple[str | None, dict | None]:
        best_key = None
        best_entry = None
        best_pos = None
        for key, entry in (self._teams or {}).items():
            if not isinstance(entry, dict):
                continue
            pos = self._to_int(entry.get("PredictedPosition"))
            if pos is None:
                continue
            if best_pos is None or pos < best_pos:
                best_pos = pos
                best_key = str(entry.get("TeamKey") or key)
                best_entry = entry
        return best_key, best_entry

    def _deliver(self) -> None:
        self.available = True

        p1_rn, p1_entry = self._pick_predicted_driver_p1()
        ident = self._driver_map.get(str(p1_rn), {}) if p1_rn else {}
        p1_tla = ident.get("tla") if isinstance(ident, dict) else None
        p1_pts = (
            self._to_float((p1_entry or {}).get("PredictedPoints"))
            if isinstance(p1_entry, dict)
            else None
        )

        t1_key, t1_entry = self._pick_predicted_team_p1()
        team_name = None
        if isinstance(t1_entry, dict):
            team_name = t1_entry.get("TeamName") or t1_entry.get("teamName")
        if not team_name and t1_key:
            team_name = str(t1_key)
        t1_pts = (
            self._to_float((t1_entry or {}).get("PredictedPoints"))
            if isinstance(t1_entry, dict)
            else None
        )

        self._state = {
            "drivers": dict(self._drivers),
            "teams": dict(self._teams),
            "predicted_driver_p1": {
                "racing_number": p1_rn,
                "tla": p1_tla,
                "points": p1_pts,
                "entry": dict(p1_entry) if isinstance(p1_entry, dict) else None,
            },
            "predicted_team_p1": {
                "team_key": t1_key,
                "team_name": team_name,
                "points": t1_pts,
                "entry": dict(t1_entry) if isinstance(t1_entry, dict) else None,
            },
            "last_update": dt_util.utcnow().isoformat(timespec="seconds"),
        }
        self.async_set_updated_data(self._state)

    def _on_bus_message(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        self._ingest_prediction(msg)
        self._schedule_deliver()

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        # Seed driver identity for replay mode (single-stream dump).
        self._seed_driver_map_from_ergast()
        # Reset on index/session rollover
        try:
            self._session_fingerprint = _compute_session_fingerprint(
                getattr(self._session_coord, "data", None)
            )
            self._session_unsub = self._session_coord.async_add_listener(
                self._on_session_index_update
            )
        except Exception:
            self._session_unsub = None
        # Subscriptions
        bus = self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")
        with suppress(Exception):
            self._unsubs.append(
                bus.subscribe("ChampionshipPrediction", self._on_bus_message)  # type: ignore[attr-defined]
            )
        with suppress(Exception):
            self._unsubs.append(
                bus.subscribe("DriverList", self._on_driverlist)  # type: ignore[attr-defined]
            )


class LiveDriversCoordinator(DataUpdateCoordinator):
    """Coordinator aggregating DriverList, TimingData, TimingAppData, LapCount and SessionStatus.

    Exposes a consolidated structure suitable for sensors:
    data = {
      "drivers": {
         rn: {
            "identity": {"tla","name","team","team_color","racing_number"},
            "timing": {"position","gap_to_leader","interval","last_lap","best_lap","in_pit","pit_out","retired","stopped","status_code"},
            "tyres": {"compound","stint_laps","new"},
            "laps": {"lap_current","lap_total"},
         },
      },
      "leader_rn": rn | None,
      "lap_current": int | None,
      "lap_total": int | None,
      "session_status": dict | None,
      "frozen": bool,
      "fastest_lap": {
         "racing_number": str | None,
         "lap": int | None,
         "time": str | None,
         "time_secs": float | None,
         "tla": str | None,
         "name": str | None,
         "team": str | None,
         "team_color": str | None,
      },
    }
    """

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: "LiveSessionCoordinator",
        delay_seconds: int = 0,
        bus: LiveBus | None = None,
        config_entry: ConfigEntry | None = None,
        delay_controller: LiveDelayController | None = None,
        live_state: LiveAvailabilityTracker | None = None,
    ) -> None:
        super().__init__(
            hass,
            coordinator_logger("live_drivers", suppress_manual=True),
            name="F1 Live Drivers Coordinator",
            update_interval=None,
            config_entry=config_entry,
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self._deliver_handle: Optional[asyncio.Handle] = None
        self._bus = bus
        self._unsubs: list[Callable[[], None]] = []
        self._delay_listener: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))
        self._replay_mode = False
        if delay_controller is not None:
            self._delay_listener = delay_controller.add_listener(self.set_delay)
        self.available = True
        self._state: dict[str, Any] = {
            "drivers": {},
            "leader_rn": None,
            "lap_current": None,
            "lap_total": None,
            "session_status": None,
            "frozen": False,
            "tyre_statistics": {},
            "fastest_lap": self._empty_fastest_lap(),
        }
        self._live_state_unsub: Optional[Callable[[], None]] = None
        if live_state is not None:
            self._live_state_unsub = live_state.add_listener(self._handle_live_state)

    async def async_close(self, *_):
        for u in list(self._unsubs):
            with suppress(Exception):
                u()
        self._unsubs.clear()
        if self._deliver_handle:
            with suppress(Exception):
                self._deliver_handle.cancel()
            self._deliver_handle = None
        if self._delay_listener:
            with suppress(Exception):
                self._delay_listener()
            self._delay_listener = None
        if self._live_state_unsub:
            with suppress(Exception):
                self._live_state_unsub()
            self._live_state_unsub = None

    async def _async_update_data(self):
        return self._state

    def _merge_driverlist(self, payload: dict) -> bool:
        # payload: { rn: {Tla, FullName, TeamName, TeamColour, ...}, ... }
        drivers = self._state["drivers"]
        changed = False
        for rn, info in (payload or {}).items():
            if not isinstance(info, dict):
                continue
            rn_key = str(rn)
            # Derive headshot URLs in both small (transform) and large (original) forms
            headshot_raw = info.get("HeadshotUrl")
            headshot_small = headshot_raw if isinstance(headshot_raw, str) else None
            headshot_large = headshot_small
            try:
                if isinstance(headshot_raw, str):
                    idx = headshot_raw.find(".transform/")
                    if idx != -1:
                        headshot_large = headshot_raw[:idx]
            except Exception:
                headshot_large = headshot_small
            ident = drivers.setdefault(rn_key, {})
            ident.setdefault("identity", {})
            ident.setdefault("timing", {})
            ident.setdefault("tyres", {})
            ident.setdefault("laps", {})
            identity_updates: dict[str, Any] = {}
            if "RacingNumber" in info or "racing_number" not in ident["identity"]:
                identity_updates["racing_number"] = str(
                    info.get("RacingNumber") or rn_key
                )
            if "Tla" in info:
                identity_updates["tla"] = info.get("Tla")
            if "FullName" in info or "BroadcastName" in info:
                name = info.get("FullName") or info.get("BroadcastName")
                if name is not None:
                    identity_updates["name"] = name
            if "TeamName" in info:
                identity_updates["team"] = info.get("TeamName")
            if "TeamColour" in info:
                identity_updates["team_color"] = info.get("TeamColour")
            if "FirstName" in info:
                identity_updates["first_name"] = info.get("FirstName")
            if "LastName" in info:
                identity_updates["last_name"] = info.get("LastName")
            if headshot_small is not None:
                identity_updates["headshot_small"] = headshot_small
                identity_updates["headshot_large"] = headshot_large
            if "Reference" in info:
                identity_updates["reference"] = info.get("Reference")

            if identity_updates:
                driver_changed = False
                for key, value in identity_updates.items():
                    if ident["identity"].get(key) != value:
                        driver_changed = True
                        break
                if driver_changed:
                    ident["identity"].update(identity_updates)
                    changed = True

            fastest = self._state.get("fastest_lap")
            if isinstance(fastest, dict) and fastest.get("racing_number") == rn_key:
                team_color = self._normalize_team_color(
                    ident["identity"].get("team_color")
                )
                fastest_updates = {
                    "tla": ident["identity"].get("tla"),
                    "name": ident["identity"].get("name"),
                    "team": ident["identity"].get("team"),
                    "team_color": team_color,
                }
                if any(fastest.get(k) != v for k, v in fastest_updates.items()):
                    fastest.update(fastest_updates)
                    changed = True

            # Capture Line field as grid position (backup if DriverRaceInfo not available)
            if "Line" in info:
                line_raw = info.get("Line")
                try:
                    line_pos = str(int(line_raw)) if line_raw is not None else None
                except (TypeError, ValueError):
                    line_pos = None
                if line_pos is not None:
                    ident.setdefault(
                        "lap_history",
                        {
                            "laps": {},
                            "last_recorded_lap": 0,
                            "grid_position": None,
                            "completed_laps": 0,
                        },
                    )
                    lap_history = ident["lap_history"]
                    if (
                        lap_history.get("grid_position") is None
                        and (lap_history.get("completed_laps") or 0) == 0
                    ):
                        lap_history["grid_position"] = line_pos
                        changed = True

        return changed

    @staticmethod
    def _get_value(d: dict | None, *path, default: Any = None):
        cur: Any = d
        for p in path:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(p)
        return cur if cur is not None else default

    def _merge_timingdata(self, payload: dict) -> bool:
        # payload: {"Lines": { rn: {...timing...} } }
        lines = (payload or {}).get("Lines", {})
        if not isinstance(lines, dict):
            return False
        drivers = self._state["drivers"]
        changed = False
        position_changed = False
        # 1) Apply incremental updates to stored driver timing
        for rn, td in lines.items():
            if not isinstance(td, dict):
                continue
            entry = drivers.setdefault(rn, {})
            entry.setdefault("identity", {})
            entry.setdefault("timing", {})
            entry.setdefault("tyres", {})
            entry.setdefault("laps", {})
            entry.setdefault(
                "tyre_history", {"stints": [], "current_stint_index": None}
            )
            entry.setdefault(
                "lap_history",
                {
                    "laps": {},
                    "last_recorded_lap": 0,
                    "grid_position": None,
                    "completed_laps": 0,
                },
            )
            timing = entry["timing"]
            lap_history = entry["lap_history"]

            number_of_laps: int | None = None
            if "NumberOfLaps" in td:
                try:
                    num_raw = td.get("NumberOfLaps")
                    number_of_laps = int(num_raw) if num_raw is not None else None
                except (TypeError, ValueError):
                    number_of_laps = None
                if number_of_laps is not None:
                    if lap_history.get("completed_laps") != number_of_laps:
                        lap_history["completed_laps"] = number_of_laps
                        changed = True
            # IMPORTANT: Only set fields that are present in this delta payload.
            if "Position" in td:
                pos_raw = td.get("Position")
                pos_str = str(pos_raw).strip() if pos_raw is not None else None
                pos_value = pos_str or None
                if timing.get("position") != pos_value:
                    timing["position"] = pos_value
                    changed = True
                    position_changed = True
                if (
                    pos_value
                    and lap_history.get("grid_position") is None
                    and (lap_history.get("completed_laps") or 0) == 0
                ):
                    lap_history["grid_position"] = pos_value
                    changed = True
            if "GapToLeader" in td:
                gap_val = td.get("GapToLeader")
                if timing.get("gap_to_leader") != gap_val:
                    timing["gap_to_leader"] = gap_val
                    changed = True
            ival = self._get_value(td, "IntervalToPositionAhead", "Value")
            if ival is not None:
                if timing.get("interval") != ival:
                    timing["interval"] = ival
                    changed = True
            last_lap = self._get_value(td, "LastLapTime", "Value")
            if last_lap is not None:
                if timing.get("last_lap") != last_lap:
                    # Record for lap history before updating timing
                    lap_num = number_of_laps
                    if lap_num is None:
                        completed = lap_history.get("completed_laps")
                        lap_num = completed if isinstance(completed, int) else None
                    if self._record_lap_for_history(rn, last_lap, lap_num):
                        changed = True
                    timing["last_lap"] = last_lap
                    changed = True
                # Record lap time for tyre statistics (correlate with current stint)
                if self._record_lap_time_for_stint(rn, last_lap):
                    changed = True
            best_lap = self._get_value(td, "BestLapTime", "Value")
            best_lap_num_raw = self._get_value(td, "BestLapTime", "Lap")
            best_lap_num: int | None = None
            if best_lap_num_raw is not None:
                try:
                    best_lap_num = int(best_lap_num_raw)
                except (TypeError, ValueError):
                    best_lap_num = None
            if best_lap is not None:
                if timing.get("best_lap") != best_lap:
                    timing["best_lap"] = best_lap
                    changed = True
                if best_lap_num is not None and self._update_fastest_lap(
                    rn, best_lap_num, best_lap
                ):
                    changed = True
            if "InPit" in td:
                in_pit = bool(td.get("InPit"))
                if timing.get("in_pit") != in_pit:
                    timing["in_pit"] = in_pit
                    changed = True
            if "PitOut" in td:
                pit_out = bool(td.get("PitOut"))
                if timing.get("pit_out") != pit_out:
                    timing["pit_out"] = pit_out
                    changed = True
            if "Retired" in td:
                retired = bool(td.get("Retired"))
                if timing.get("retired") != retired:
                    timing["retired"] = retired
                    changed = True
            if "Stopped" in td:
                stopped = bool(td.get("Stopped"))
                if timing.get("stopped") != stopped:
                    timing["stopped"] = stopped
                    changed = True
            if "Status" in td:
                status = td.get("Status")
                if timing.get("status_code") != status:
                    timing["status_code"] = status
                    changed = True
        # SessionPart (for Q1/Q2/Q3 detection)
        with suppress(Exception):
            part = payload.get("SessionPart")
            if part is not None:
                self._state.setdefault("session", {})
                if self._state["session"].get("part") != part:
                    self._state["session"]["part"] = part
                    changed = True
        if position_changed:
            self._recompute_leader_from_state()
        return changed

    def set_delay(self, seconds: int) -> None:
        _apply_delay_simple(self, seconds)

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        if reason == "init":
            return
        self._replay_mode = _is_replay_delay_reason(reason)
        if self._replay_mode:
            self._deliver_handle = _cancel_handle(self._deliver_handle)
        self.available = is_live
        if not is_live:
            # Clear consolidated state so a future session window does not briefly
            # show stale driver/timing information before the first live frames.
            with suppress(Exception):
                self._state = {
                    "drivers": {},
                    "leader_rn": None,
                    "lap_current": None,
                    "lap_total": None,
                    "session_status": None,
                    "frozen": False,
                    "tyre_statistics": {},
                    "fastest_lap": self._empty_fastest_lap(),
                }
                self.async_set_updated_data(self._state)
            return
        # 2) Recompute leader from full stored state (not just current delta)
        self._recompute_leader_from_state()

    def _recompute_leader_from_state(self) -> None:
        drivers = self._state.get("drivers", {}) or {}
        prev = self._state.get("leader_rn")
        # Prefer explicit position == "1"
        leader_rn = None
        for rn, info in drivers.items():
            pos = (info.get("timing", {}) or {}).get("position")
            if str(pos or "").strip() == "1":
                leader_rn = rn
                break
        if leader_rn is None:
            # Fallback: minimal numeric position across all stored drivers
            best: tuple[int, str] | None = None
            for rn, info in drivers.items():
                pos_str = str(
                    (info.get("timing", {}) or {}).get("position") or ""
                ).strip()
                try:
                    pos_int = int(pos_str) if pos_str.isdigit() else None
                except Exception:
                    pos_int = None
                if isinstance(pos_int, int):
                    if best is None or pos_int < best[0]:
                        best = (pos_int, rn)
            if best is not None:
                leader_rn = best[1]
        if leader_rn is None and prev:
            # If we cannot determine a leader from current positions, keep previous to avoid flapping
            leader_rn = prev
        if leader_rn is not None and leader_rn != prev:
            with suppress(Exception):
                _LOGGER.debug("LiveDrivers: leader changed %s -> %s", prev, leader_rn)
            self._state["leader_rn"] = leader_rn

    def _merge_timingapp(self, payload: dict) -> bool:
        """Merge TimingAppData payloads.

        We now use the dedicated TyreStintSeries stream for tyre information, so this
        handler is only responsible for lap time fields from the embedded Stints.
        """
        # payload: {"Lines": { rn: {"Stints": { idx or list } } } }
        lines = (payload or {}).get("Lines", {})
        if not isinstance(lines, dict):
            return False
        drivers = self._state["drivers"]
        changed = False
        for rn, app in lines.items():
            if not isinstance(app, dict):
                continue
            entry = drivers.setdefault(rn, {})
            entry.setdefault("timing", {})
            stints = app.get("Stints")

            # Extract the latest stint entry for lap time updates
            latest: dict | None = None
            if isinstance(stints, list) and stints:
                latest = stints[-1] if isinstance(stints[-1], dict) else None
            elif isinstance(stints, dict) and stints:
                # Often indexed by numeric keys or 0/1
                try:
                    keys = [int(k) for k in stints.keys() if str(k).isdigit()]
                    if keys:
                        latest = stints.get(str(max(keys)))
                except Exception:
                    # Fallback: try key '0'
                    latest = (
                        stints.get("0") if isinstance(stints.get("0"), dict) else None
                    )

            if isinstance(latest, dict):
                # Lap times: map latest LapTime to timing.last_lap and update best_lap
                lap_time = latest.get("LapTime")
                if isinstance(lap_time, str) and lap_time:
                    timing = entry.setdefault("timing", {})
                    if timing.get("last_lap") != lap_time:
                        timing["last_lap"] = lap_time
                        changed = True
                    prev_best = timing.get("best_lap")
                    new_secs = self._parse_laptime_secs(lap_time)
                    prev_secs = (
                        self._parse_laptime_secs(prev_best)
                        if isinstance(prev_best, str)
                        else None
                    )
                    if new_secs is not None and (
                        prev_secs is None or new_secs < prev_secs
                    ):
                        timing["best_lap"] = lap_time
                        changed = True

        return changed

    def _merge_tyre_stints(self, payload: dict) -> bool:
        """Merge TyreStintSeries payloads into per-driver tyre state.

        Expected payload shape (from SignalR stream \"TyreStintSeries\"):
            {"Stints": { rn: { idx: {Compound, New, TotalLaps, ...}, ... }, ... }}

        This method now tracks full stint history for tyre statistics in addition
        to maintaining the existing tyres dict for backward compatibility.
        """
        stints_root = (payload or {}).get("Stints", {})
        if not isinstance(stints_root, dict):
            return False
        drivers = self._state["drivers"]
        stints_changed = False

        for rn, stints in stints_root.items():
            if not isinstance(stints, (dict, list)):
                continue
            entry = drivers.setdefault(rn, {})
            entry.setdefault("tyres", {})
            entry.setdefault(
                "tyre_history", {"stints": [], "current_stint_index": None}
            )
            tyres = entry["tyres"]
            tyre_history = entry["tyre_history"]

            # Process ALL stint indices to build full history
            stint_items: list[tuple[int, dict]] = []
            if isinstance(stints, list):
                for i, s in enumerate(stints):
                    if isinstance(s, dict):
                        stint_items.append((i, s))
            elif isinstance(stints, dict):
                for k, v in stints.items():
                    if isinstance(v, dict) and str(k).isdigit():
                        with suppress(ValueError):
                            stint_items.append((int(k), v))
            for stint_idx, stint_data in stint_items:
                if self._update_stint_history(tyre_history, stint_idx, stint_data):
                    stints_changed = True

                # Update current stint tracking (highest index = current)
                if (
                    tyre_history["current_stint_index"] is None
                    or stint_idx >= tyre_history["current_stint_index"]
                ):
                    if tyre_history["current_stint_index"] != stint_idx:
                        tyre_history["current_stint_index"] = stint_idx
                        stints_changed = True

            # Maintain backward compatibility: update tyres dict with latest stint
            latest: dict | None = None
            if isinstance(stints, list) and stints:
                latest = stints[-1] if isinstance(stints[-1], dict) else None
            elif isinstance(stints, dict) and stints:
                try:
                    keys = [int(k) for k in stints.keys() if str(k).isdigit()]
                    if keys:
                        latest = stints.get(str(max(keys)))
                except Exception:
                    latest = (
                        stints.get("0") if isinstance(stints.get("0"), dict) else None
                    )
            if isinstance(latest, dict):
                if "Compound" in latest:
                    compound = self._normalize_compound(latest.get("Compound"))
                    if tyres.get("compound") != compound:
                        tyres["compound"] = compound
                        stints_changed = True
                if "TotalLaps" in latest:
                    stint_laps = latest.get("TotalLaps")
                    stint_laps_val = (
                        int(stint_laps)
                        if str(stint_laps or "").isdigit()
                        else stint_laps
                    )
                    if tyres.get("stint_laps") != stint_laps_val:
                        tyres["stint_laps"] = stint_laps_val
                        stints_changed = True
                if "New" in latest:
                    is_new = latest.get("New")
                    s = str(is_new).lower()
                    if s == "true":
                        new_val: Any = True
                    elif s == "false":
                        new_val = False
                    else:
                        new_val = is_new
                    if tyres.get("new") != new_val:
                        tyres["new"] = new_val
                        stints_changed = True

        # Recompute tyre statistics if any stints changed
        if stints_changed:
            self._recompute_tyre_statistics()

        # Tyre changes can also interact with leader logic (pit stops etc.)
        if stints_changed:
            self._recompute_leader_from_state()
        return stints_changed

    def _update_stint_history(
        self, tyre_history: dict, stint_idx: int, stint_data: dict
    ) -> bool:
        """Update or create a stint entry in tyre_history.

        Handles incremental updates where only TotalLaps may be present.
        """
        stints_list = tyre_history["stints"]
        changed = False

        # Ensure the list is large enough
        while len(stints_list) <= stint_idx:
            stints_list.append(
                {
                    "stint_index": len(stints_list),
                    "compound": None,
                    "new": None,
                    "total_laps": 0,
                    "start_laps": None,
                    "best_lap_time": None,
                    "best_lap_time_secs": None,
                }
            )
            changed = True

        stint = stints_list[stint_idx]

        # Only update fields that are present in the delta
        if "Compound" in stint_data:
            compound = self._normalize_compound(stint_data.get("Compound"))
            if stint.get("compound") != compound:
                stint["compound"] = compound
                changed = True
        if "TotalLaps" in stint_data:
            total_laps = stint_data.get("TotalLaps")
            total_laps_val = int(total_laps) if str(total_laps or "").isdigit() else 0
            if stint.get("total_laps") != total_laps_val:
                stint["total_laps"] = total_laps_val
                changed = True
        if "StartLaps" in stint_data:
            start_laps = stint_data.get("StartLaps")
            start_laps_val = (
                int(start_laps) if str(start_laps or "").isdigit() else None
            )
            if stint.get("start_laps") != start_laps_val:
                stint["start_laps"] = start_laps_val
                changed = True
        if "New" in stint_data:
            is_new = stint_data.get("New")
            s = str(is_new).lower()
            if s == "true":
                new_val: Any = True
            elif s == "false":
                new_val = False
            else:
                new_val = is_new
            if stint.get("new") != new_val:
                stint["new"] = new_val
                changed = True
        return changed

    def _record_lap_time_for_stint(self, rn: str, lap_time: str) -> bool:
        """Associate a lap time with the driver's current stint for tyre statistics."""
        entry = self._state["drivers"].get(rn)
        if not entry:
            return False

        tyre_history = entry.get("tyre_history")
        if not tyre_history:
            return False

        current_idx = tyre_history.get("current_stint_index")
        stints_list = tyre_history.get("stints", [])

        if current_idx is None or current_idx >= len(stints_list):
            return False

        stint = stints_list[current_idx]
        lap_secs = self._parse_laptime_secs(lap_time)
        if lap_secs is None:
            return False

        # Update best lap for this stint if faster
        current_best = stint.get("best_lap_time_secs")
        if current_best is None or lap_secs < current_best:
            stint["best_lap_time"] = lap_time
            stint["best_lap_time_secs"] = lap_secs
            # Recompute statistics when a new best lap is set
            self._recompute_tyre_statistics()
            return True
        return False

    def _record_lap_for_history(
        self, rn: str, lap_time: str, lap_num: int | None = None
    ) -> bool:
        """Record a completed lap time in the driver's lap history.

        Called when LastLapTime changes, indicating a new lap was completed.
        """
        entry = self._state["drivers"].get(rn)
        if not entry:
            return False

        lap_history = entry.get("lap_history")
        if not lap_history:
            return False

        timing = entry.get("timing", {})
        current_position = timing.get("position")

        # Determine lap number: use provided lap_num when available
        last_lap_num = lap_history.get("last_recorded_lap", 0)
        try:
            use_lap_num = int(lap_num) if lap_num is not None else None
        except (TypeError, ValueError):
            use_lap_num = None
        if not use_lap_num or use_lap_num <= 0:
            use_lap_num = last_lap_num + 1

        # Capture grid position on first lap if not already set
        if use_lap_num == 1 and lap_history.get("grid_position") is None:
            lap_history["grid_position"] = current_position

        # Store the lap time (just the time, position is tracked separately)
        lap_key = str(use_lap_num)
        prev_time = lap_history["laps"].get(lap_key)
        if prev_time == lap_time and last_lap_num >= use_lap_num:
            return False
        lap_history["laps"][lap_key] = lap_time
        if last_lap_num < use_lap_num:
            lap_history["last_recorded_lap"] = use_lap_num
        # Keep completed_laps in sync with highest seen lap
        with suppress(Exception):
            completed = lap_history.get("completed_laps", 0) or 0
            if isinstance(completed, int) and completed < use_lap_num:
                lap_history["completed_laps"] = use_lap_num

        self._update_fastest_lap(rn, use_lap_num, lap_time)
        return True

    def _update_fastest_lap(self, rn: str, lap_num: int | None, lap_time: str) -> bool:
        """Update overall fastest lap if the provided lap is quicker."""
        lap_secs = self._parse_laptime_secs(lap_time)
        if lap_secs is None:
            return False

        fastest = self._state.get("fastest_lap")
        if not isinstance(fastest, dict):
            fastest = self._empty_fastest_lap()

        prev_secs = fastest.get("time_secs")
        if prev_secs is not None and lap_secs >= prev_secs:
            return False

        rn_key = str(rn)
        entry = self._state.get("drivers", {}).get(rn_key, {}) or {}
        identity = entry.get("identity", {}) if isinstance(entry, dict) else {}
        team_color = self._normalize_team_color(identity.get("team_color"))

        self._state["fastest_lap"] = {
            "racing_number": rn_key,
            "lap": lap_num,
            "time": lap_time,
            "time_secs": lap_secs,
            "tla": identity.get("tla"),
            "name": identity.get("name"),
            "team": identity.get("team"),
            "team_color": team_color,
        }
        return True

    def _recompute_fastest_lap_from_history(self) -> bool:
        """Recompute fastest lap by scanning lap history (replay init)."""
        drivers = self._state.get("drivers", {}) or {}
        best_secs: float | None = None
        best_rn: str | None = None
        best_lap: int | None = None
        best_time: str | None = None

        for rn in sorted(drivers.keys(), key=str):
            entry = drivers.get(rn, {}) or {}
            lap_history = entry.get("lap_history", {}) or {}
            laps = lap_history.get("laps", {})
            if not isinstance(laps, dict):
                continue
            for lap_key, lap_time in laps.items():
                if not isinstance(lap_time, str) or not lap_time:
                    continue
                lap_secs = self._parse_laptime_secs(lap_time)
                if lap_secs is None:
                    continue
                if best_secs is not None and lap_secs >= best_secs:
                    continue
                try:
                    lap_num = int(lap_key)
                except (TypeError, ValueError):
                    lap_num = None
                best_secs = lap_secs
                best_rn = str(rn)
                best_lap = lap_num
                best_time = lap_time

        if best_secs is None or best_rn is None or best_time is None:
            empty = self._empty_fastest_lap()
            if self._state.get("fastest_lap") != empty:
                self._state["fastest_lap"] = empty
                return True
            return False

        entry = drivers.get(best_rn, {}) or {}
        identity = entry.get("identity", {}) if isinstance(entry, dict) else {}
        team_color = self._normalize_team_color(identity.get("team_color"))

        fastest = {
            "racing_number": best_rn,
            "lap": best_lap,
            "time": best_time,
            "time_secs": best_secs,
            "tla": identity.get("tla"),
            "name": identity.get("name"),
            "team": identity.get("team"),
            "team_color": team_color,
        }
        if self._state.get("fastest_lap") != fastest:
            self._state["fastest_lap"] = fastest
            return True
        return False

    def _recompute_tyre_statistics(self) -> None:
        """Recompute aggregated tyre statistics from all driver stint history."""
        compounds_data: dict[str, dict] = {}
        start_compounds: set[str] = set()
        drivers = self._state.get("drivers", {})

        for rn, info in drivers.items():
            tyre_history = info.get("tyre_history", {})
            identity = info.get("identity", {})
            driver_name = identity.get("last_name") or identity.get("name")
            team_color = identity.get("team_color")

            for stint in tyre_history.get("stints", []):
                compound = self._normalize_compound(stint.get("compound"))
                if not compound or compound == "UNKNOWN":
                    continue
                if stint.get("stint_index") == 0:
                    start_compounds.add(compound)

                comp = compounds_data.setdefault(
                    compound,
                    {
                        "best_times": [],
                        "total_laps": 0,
                        "sets_used": 0,
                        "sets_used_total": 0,
                    },
                )

                # Accumulate laps
                comp["total_laps"] += stint.get("total_laps", 0) or 0
                comp["sets_used_total"] += 1
                if stint.get("new") is True:
                    comp["sets_used"] += 1

                # Track best times (only if we have a recorded time)
                if stint.get("best_lap_time_secs") is not None:
                    comp["best_times"].append(
                        {
                            "time": stint["best_lap_time"],
                            "time_secs": stint["best_lap_time_secs"],
                            "racing_number": rn,
                            "driver_name": driver_name,
                            "driver_tla": identity.get("tla"),
                            "team_color": team_color,
                            "stint_index": stint.get("stint_index"),
                            "new_tyre": stint.get("new"),
                        }
                    )

        # Sort and trim to top 3 per compound
        for comp in compounds_data.values():
            comp["best_times"].sort(key=lambda x: x["time_secs"])
            comp["best_times"] = comp["best_times"][:3]

        # Calculate fastest compound and deltas
        fastest_time: float | None = None
        fastest_compound: str | None = None
        for compound, data in compounds_data.items():
            if data["best_times"]:
                t = data["best_times"][0]["time_secs"]
                if fastest_time is None or t < fastest_time:
                    fastest_time = t
                    fastest_compound = compound

        deltas: dict[str, float] = {}
        for compound, data in compounds_data.items():
            if data["best_times"] and fastest_time is not None:
                deltas[compound] = round(
                    data["best_times"][0]["time_secs"] - fastest_time, 3
                )

        self._state["tyre_statistics"] = {
            "compounds": compounds_data,
            "fastest_compound": fastest_compound,
            "fastest_time": (
                self._format_laptime(fastest_time) if fastest_time else None
            ),
            "fastest_time_secs": fastest_time,
            "deltas": deltas,
            "start_compounds": self._sort_compounds(start_compounds),
        }

    @staticmethod
    def _format_laptime(secs: float | None) -> str | None:
        """Format seconds as M:SS.mmm lap time string."""
        if secs is None:
            return None
        minutes = int(secs // 60)
        remaining = secs - (minutes * 60)
        return f"{minutes}:{remaining:06.3f}"

    @staticmethod
    def _empty_fastest_lap() -> dict[str, Any]:
        return {
            "racing_number": None,
            "lap": None,
            "time": None,
            "time_secs": None,
            "tla": None,
            "name": None,
            "team": None,
            "team_color": None,
        }

    @staticmethod
    def _normalize_team_color(value: Any) -> Any:
        if not isinstance(value, str) or not value:
            return value
        if value.startswith("#"):
            return value
        return f"#{value}"

    def _merge_lapcount(self, payload: dict) -> None:
        # payload may be either {CurrentLap, TotalLaps} or wrapped
        curr = payload.get("CurrentLap") or payload.get("LapCount")
        total = payload.get("TotalLaps")
        try:
            curr_i = int(curr) if curr is not None else None
        except Exception:
            curr_i = None
        try:
            total_i = int(total) if total is not None else None
        except Exception:
            total_i = None
        self._state["lap_current"] = curr_i
        self._state["lap_total"] = total_i
        # Mirror into each driver for convenience
        for entry in self._state["drivers"].values():
            entry.setdefault("laps", {})
            entry["laps"].update({"lap_current": curr_i, "lap_total": total_i})
        # Recompute leader as lap and position updates can interact
        self._recompute_leader_from_state()

    @staticmethod
    def _parse_laptime_secs(value: str | None) -> float | None:
        """Parse a lap time formatted like 'M:SS.mmm' or 'SS.mmm' to seconds."""
        if not value:
            return None
        try:
            s = value.strip()
            if ":" in s:
                minutes_str, sec_str = s.split(":", 1)
                minutes = int(minutes_str)
                seconds = float(sec_str)
                return minutes * 60.0 + seconds
            return float(s)
        except Exception:
            return None

    @staticmethod
    def _normalize_compound(value: Any) -> str | None:
        if not isinstance(value, str):
            return value if value is None else str(value)
        comp = value.strip().upper()
        if not comp:
            return None
        if comp in {"INTER", "INTERS", "INTERMEDIATES"}:
            return "INTERMEDIATE"
        if comp in {"WETS", "FULLWET", "FULL WET", "FULL_WET"}:
            return "WET"
        return comp

    @staticmethod
    def _sort_compounds(compounds: set[str]) -> list[str]:
        order = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]
        order_index = {name: idx for idx, name in enumerate(order)}
        return sorted(
            compounds,
            key=lambda name: (order_index.get(name, len(order_index)), name),
        )

    def _capture_grid_positions_if_needed(self) -> None:
        """Capture current positions as grid positions on session start.

        Only captures once per session (when grid_position is still None).
        """
        drivers = self._state.get("drivers", {})
        for rn, entry in drivers.items():
            lap_history = entry.get("lap_history")
            if not lap_history:
                continue
            # Only capture if not already set
            if lap_history.get("grid_position") is None:
                current_pos = entry.get("timing", {}).get("position")
                if current_pos:
                    lap_history["grid_position"] = current_pos

    def _clear_lap_history(self) -> None:
        """Clear lap history for all drivers on session end."""
        drivers = self._state.get("drivers", {})
        for rn, entry in drivers.items():
            entry["lap_history"] = {
                "laps": {},
                "last_recorded_lap": 0,
                "grid_position": None,
                "completed_laps": 0,
            }

    def _merge_sessionstatus(self, payload: dict) -> None:
        self._state["session_status"] = payload
        with suppress(Exception):
            msg = str(payload.get("Status") or payload.get("Message") or "").strip()
            started_flag = payload.get("Started")
            # Freeze at session end
            if msg in ("Finished", "Finalised", "Ends"):
                self._state["frozen"] = True
            # Unfreeze on new session start or green running
            elif started_flag is True or msg in ("Started", "Green", "GreenFlag"):
                self._state["frozen"] = False
                # Capture grid positions when session starts
                self._capture_grid_positions_if_needed()

    @staticmethod
    def _extract(data: dict, key: str) -> dict | None:
        if not isinstance(data, dict):
            return None
        messages = data.get("M")
        if isinstance(messages, list):
            for update in messages:
                args = update.get("A", [])
                if len(args) >= 2 and args[0] == key:
                    return args[1]
        result = data.get("R")
        if isinstance(result, dict) and key in result:
            return result.get(key)
        return None

    def _deliver(self) -> None:
        # Push deep-copied shallow dict to avoid accidental external mutation
        self.async_set_updated_data(self._state)

    def _schedule_deliver(self) -> None:
        delay = 0 if self._replay_mode else self._delay
        self._deliver_handle = _schedule_deliver_handle(
            self.hass.loop, self._deliver_handle, delay, self._deliver
        )

    def _on_driverlist(self, dl: dict) -> None:
        # Allow DriverList merges even when frozen so identity mapping remains available
        changed = self._merge_driverlist(dl)
        if changed:
            # Recompute tyre statistics to update driver names/TLAs
            self._recompute_tyre_statistics()
            self._schedule_deliver()

    def _on_timingdata(self, td: dict) -> None:
        if self._state.get("frozen") and not self._replay_mode:
            return
        if self._merge_timingdata(td):
            self._schedule_deliver()

    def _on_timingapp(self, ta: dict) -> None:
        if self._state.get("frozen") and not self._replay_mode:
            return
        if self._merge_timingapp(ta):
            self._schedule_deliver()

    def _on_tyre_stints(self, ts: dict) -> None:
        if self._state.get("frozen") and not self._replay_mode:
            return
        if self._merge_tyre_stints(ts):
            self._schedule_deliver()

    def _on_lapcount(self, lc: dict) -> None:
        if self._state.get("frozen"):
            return
        self._merge_lapcount(lc)
        self._schedule_deliver()

    def _on_sessionstatus(self, ss: dict) -> None:
        # Always process SessionStatus so we can transition out of frozen on new sessions
        self._merge_sessionstatus(ss)
        self._schedule_deliver()

    def _on_driver_race_info(self, payload: dict) -> None:
        """Handle DriverRaceInfo stream for early grid positions."""
        if not isinstance(payload, dict):
            return
        drivers = self._state["drivers"]
        changed = False
        for rn, info in payload.items():
            if not isinstance(info, dict):
                continue
            pos_raw = info.get("Position")
            if pos_raw is None:
                continue
            grid_pos = None
            try:
                grid_pos = str(pos_raw).strip()
            except (TypeError, ValueError):
                grid_pos = None
            if not grid_pos:
                continue

            entry = drivers.setdefault(rn, {})
            entry.setdefault("identity", {})
            entry.setdefault("timing", {})
            entry.setdefault("tyres", {})
            entry.setdefault("laps", {})
            entry.setdefault(
                "tyre_history", {"stints": [], "current_stint_index": None}
            )
            entry.setdefault(
                "lap_history",
                {
                    "laps": {},
                    "last_recorded_lap": 0,
                    "grid_position": None,
                    "completed_laps": 0,
                },
            )

            lap_history = entry["lap_history"]
            # Set grid_position only if not already set and no laps completed
            if (
                lap_history.get("grid_position") is None
                and (lap_history.get("completed_laps") or 0) == 0
            ):
                lap_history["grid_position"] = grid_pos
                changed = True

        if changed:
            self._schedule_deliver()

    def _on_lap_history(self, lh: dict) -> None:
        """Apply pre-built lap history from replay initial state injection."""
        if not isinstance(lh, dict):
            return
        drivers = self._state.setdefault("drivers", {})
        changed = False
        for rn, history_data in lh.items():
            if not isinstance(history_data, dict):
                continue
            # Create driver entry if it doesn't exist (LapHistory may arrive before DriverList/TimingData)
            entry = drivers.setdefault(rn, {})
            entry.setdefault("identity", {})
            entry.setdefault("timing", {})
            entry.setdefault("tyres", {})
            entry.setdefault("laps", {})
            entry.setdefault(
                "tyre_history", {"stints": [], "current_stint_index": None}
            )
            lap_history = entry.setdefault(
                "lap_history",
                {
                    "laps": {},
                    "last_recorded_lap": 0,
                    "grid_position": None,
                    "completed_laps": 0,
                },
            )
            # Only apply if our lap_history is empty (initial load)
            if lap_history.get("last_recorded_lap", 0) == 0:
                laps = history_data.get("laps", {})
                grid_pos = history_data.get("grid_position")
                last_lap = history_data.get("last_recorded_lap", 0)
                completed_laps = history_data.get("completed_laps")
                if laps or grid_pos:
                    lap_history["laps"] = dict(laps)
                    lap_history["grid_position"] = grid_pos
                    lap_history["last_recorded_lap"] = last_lap
                    if isinstance(completed_laps, int):
                        lap_history["completed_laps"] = completed_laps
                    else:
                        lap_history["completed_laps"] = last_lap
                    changed = True
        if changed:
            self._schedule_deliver()

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        # Subscribe to LiveBus streams
        try:
            bus = self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")  # type: ignore[assignment]
        except Exception:
            bus = None
        if bus is not None:
            with suppress(Exception):
                self._unsubs.append(bus.subscribe("DriverList", self._on_driverlist))
            with suppress(Exception):
                self._unsubs.append(bus.subscribe("TimingData", self._on_timingdata))
            with suppress(Exception):
                self._unsubs.append(bus.subscribe("TimingAppData", self._on_timingapp))
            with suppress(Exception):
                self._unsubs.append(
                    bus.subscribe("TyreStintSeries", self._on_tyre_stints)
                )
            with suppress(Exception):
                self._unsubs.append(bus.subscribe("LapCount", self._on_lapcount))
            with suppress(Exception):
                self._unsubs.append(
                    bus.subscribe("SessionStatus", self._on_sessionstatus)
                )
            with suppress(Exception):
                self._unsubs.append(bus.subscribe("LapHistory", self._on_lap_history))
            with suppress(Exception):
                self._unsubs.append(
                    bus.subscribe("DriverRaceInfo", self._on_driver_race_info)
                )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    # Proceed with best-effort cleanup even if unload_ok is False, but keep return value
    try:
        data_root = hass.data.get(DOMAIN)
        data = None
        if isinstance(data_root, dict):
            data = data_root.pop(entry.entry_id, None)
        if isinstance(data, dict):
            for name, obj in list(data.items()):
                if obj is None:
                    continue
                close = getattr(obj, "async_close", None)
                if callable(close):
                    try:
                        await close()
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.debug("Error during %s async_close: %s", name, err)
        # If this was the last entry, remove dev-only stats reporter.
        if isinstance(data_root, dict):
            # Keep only real entry dicts (exclude our global stats key)
            remaining_entries = [
                k
                for k in data_root.keys()
                if isinstance(k, str) and k != _JOLPICA_STATS_KEY
            ]
            if not remaining_entries:
                stats = data_root.get(_JOLPICA_STATS_KEY)
                unsub = stats.get("unsub") if isinstance(stats, dict) else None
                if callable(unsub):
                    with suppress(Exception):
                        unsub()
                data_root.pop(_JOLPICA_STATS_KEY, None)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Error during entry data cleanup: %s", err)
    return unload_ok


class F1DataCoordinator(DataUpdateCoordinator):
    """Handles updates from a given F1 endpoint."""

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        name: str,
        session=None,
        user_agent: str | None = None,
        cache=None,
        inflight=None,
        ttl_seconds: int = 30,
        persist_map=None,
        persist_save=None,
        config_entry: ConfigEntry | None = None,
    ):
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(hours=1),
            config_entry=config_entry,
        )
        self._session = session or async_get_clientsession(hass)
        self._headers = {"User-Agent": str(user_agent)} if user_agent else None
        self._url = url
        self._cache = cache
        self._inflight = inflight
        self._ttl = int(ttl_seconds or 30)
        self._persist = persist_map
        self._persist_save = persist_save
        self._last_seen_season: str | None = None

        # Initialize last-seen season from persisted current.json payload if present.
        # This makes rollover detection work immediately after a restart, even if the
        # first read is served from cache before the first network MISS.
        with suppress(Exception):
            if self._url == API_URL and isinstance(self._persist, dict):
                rec = self._persist.get(API_URL)
                payload = rec.get("data") if isinstance(rec, dict) else None
                season = self._extract_season(payload) if payload else None
                if season:
                    self._last_seen_season = season

    def _extract_season(self, payload: Any) -> str | None:
        """Best-effort extraction of season (year) from Ergast/Jolpica payloads."""
        try:
            mr = (payload or {}).get("MRData", {}) if isinstance(payload, dict) else {}
            rt = mr.get("RaceTable", {}) if isinstance(mr, dict) else {}
            season = rt.get("season")
            if season is not None:
                s = str(season).strip()
                return s if s else None
            # Fallback: infer from first race if available
            races = rt.get("Races") if isinstance(rt, dict) else None
            if isinstance(races, list) and races:
                season2 = races[0].get("season")
                if season2 is not None:
                    s2 = str(season2).strip()
                    return s2 if s2 else None
        except Exception:
            return None
        return None

    def _handle_season_rollover_if_needed(self, payload: Any) -> None:
        """If current season changed, invalidate cached /current/* endpoints and refresh dependents.

        This avoids keeping last year's 'current' data for weeks due to aggressive TTLs.
        """
        if self._url != API_URL:
            return
        season = self._extract_season(payload)
        if not season:
            return
        if self._last_seen_season is None:
            self._last_seen_season = season
            return
        if season == self._last_seen_season:
            return

        prev = self._last_seen_season
        self._last_seen_season = season
        _LOGGER.info(
            "Detected season rollover %s -> %s; invalidating Jolpica /current cache",
            prev,
            season,
        )

        # Invalidate in-memory cache entries for /current endpoints
        with suppress(Exception):
            if isinstance(self._cache, dict):
                for k in list(self._cache.keys()):
                    ks = str(k)
                    if "/ergast/f1/current" in ks:
                        self._cache.pop(k, None)
        # Invalidate persisted cache too, so restarts don't re-seed stale 'current' data
        with suppress(Exception):
            if isinstance(self._persist, dict):
                for k in list(self._persist.keys()):
                    ks = str(k)
                    if "/ergast/f1/current" in ks:
                        self._persist.pop(k, None)
                if callable(self._persist_save):
                    self._persist_save()
        # Trigger refresh of dependent coordinators for this entry (best effort)
        with suppress(Exception):
            ce = getattr(self, "config_entry", None)
            entry_id = getattr(ce, "entry_id", None) if ce is not None else None
            if not entry_id:
                return
            reg = (self.hass.data.get(DOMAIN, {}) or {}).get(entry_id, {}) or {}
            for name in (
                "driver_coordinator",
                "constructor_coordinator",
                "last_race_coordinator",
                "season_results_coordinator",
                "sprint_results_coordinator",
            ):
                coord = reg.get(name)
                if coord is None:
                    continue
                req = getattr(coord, "async_request_refresh", None)
                if callable(req):
                    self.hass.async_create_task(req())

    async def async_close(self, *_):
        """Placeholder for future cleanup."""
        return

    async def _async_update_data(self):
        """Fetch data from the F1 API."""
        try:
            async with async_timeout.timeout(10):
                data = await fetch_json(
                    self.hass,
                    self._session,
                    self._url,
                    headers=self._headers,
                    ttl_seconds=self._ttl,
                    cache=self._cache,
                    inflight=self._inflight,
                    persist_map=self._persist,
                    persist_save=self._persist_save,
                )
                # Detect season rollovers in current.json and clear stale caches if needed.
                self._handle_season_rollover_if_needed(data)
                return data
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err


class F1SeasonResultsCoordinator(DataUpdateCoordinator):
    """Fetch all season results across paginated Ergast responses."""

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        name: str,
        session=None,
        user_agent: str | None = None,
        cache=None,
        inflight=None,
        ttl_seconds: int = 6 * 3600,
        *,
        ttl_stable: int | None = None,
        ttl_recent: int | None = None,
        ttl_latest: int | None = None,
        persist_map=None,
        persist_save=None,
        config_entry: ConfigEntry | None = None,
        season_source: DataUpdateCoordinator | None = None,
    ):
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(hours=1),
            config_entry=config_entry,
        )
        self._session = session or async_get_clientsession(hass)
        self._headers = {"User-Agent": str(user_agent)} if user_agent else None
        self._base_url = url
        self._cache = cache
        self._inflight = inflight
        # ttl_seconds acts as a backward-compatible default (treated as "latest").
        default_latest = int(ttl_seconds or 6 * 3600)
        self._ttl_latest = int(ttl_latest or default_latest)
        self._ttl_recent = int(ttl_recent or max(6 * 3600, 24 * 3600))
        self._ttl_stable = int(ttl_stable or 30 * 24 * 3600)
        self._persist = persist_map
        self._persist_save = persist_save
        self._season_source = season_source

    async def async_close(self, *_):
        return

    @staticmethod
    def _extract_season(payload: Any) -> str | None:
        """Best-effort extraction of season (year) from Ergast/Jolpica payloads."""
        try:
            if not isinstance(payload, dict):
                return None
            mr = payload.get("MRData", {}) or {}
            rt = mr.get("RaceTable", {}) or {}
            season = rt.get("season")
            if season is not None:
                s = str(season).strip()
                return s if s else None
            races = rt.get("Races")
            if isinstance(races, list) and races:
                season2 = (races[0] or {}).get("season")
                if season2 is not None:
                    s2 = str(season2).strip()
                    return s2 if s2 else None
        except Exception:
            return None
        return None

    def _effective_base_url(self) -> str:
        """Prefer a season-scoped URL (/f1/<year>/...) over /f1/current/... when possible.

        This avoids stale caches across season rollovers where /current endpoints keep the
        same URL, but the "meaning" changes.
        """
        base = str(self._base_url)
        src = (
            getattr(self._season_source, "data", None)
            if self._season_source is not None
            else None
        )
        season = self._extract_season(src)
        if not season:
            return base
        # Only rewrite known /current/ Ergast paths.
        marker = "/ergast/f1/current/"
        if marker in base:
            return base.replace(marker, f"/ergast/f1/{season}/")
        return base

    def _ttl_for_offset(self, offset: int, last_offset: int, page_size: int) -> int:
        """Return TTL for a given results page offset.

        - Stable pages (older part of season): very long TTL.
        - Recent pages: daily.
        - Latest page: every few hours.
        """
        try:
            o = int(offset)
            last = int(last_offset)
            size = max(1, int(page_size))
        except Exception:
            return self._ttl_latest
        if last <= 0:
            return self._ttl_latest
        if o >= last:
            return self._ttl_latest
        if o >= max(0, last - size):
            return self._ttl_recent
        return self._ttl_stable

    async def _fetch_page(
        self, limit: int, offset: int, *, ttl_seconds: int | None = None
    ):
        from yarl import URL

        ttl = int(ttl_seconds or self._ttl_latest)

        # Primary: season-scoped URL when we can derive season from current.json.
        primary_base = self._effective_base_url()
        primary_url = str(
            URL(primary_base).with_query({"limit": str(limit), "offset": str(offset)})
        )

        async with async_timeout.timeout(10):
            try:
                return await fetch_json(
                    self.hass,
                    self._session,
                    primary_url,
                    headers=self._headers,
                    ttl_seconds=ttl,
                    cache=self._cache,
                    inflight=self._inflight,
                    persist_map=self._persist,
                    persist_save=self._persist_save,
                )
            except Exception:
                # Fallback: legacy /current/ URL (in case the API doesn't support season-scoped paths)
                fallback_url = str(
                    URL(str(self._base_url)).with_query(
                        {"limit": str(limit), "offset": str(offset)}
                    )
                )
                if fallback_url == primary_url:
                    raise
                return await fetch_json(
                    self.hass,
                    self._session,
                    fallback_url,
                    headers=self._headers,
                    ttl_seconds=ttl,
                    cache=self._cache,
                    inflight=self._inflight,
                    persist_map=self._persist,
                    persist_save=self._persist_save,
                )

    @staticmethod
    def _race_key(r: dict) -> tuple:
        season = r.get("season")
        round_ = r.get("round")
        return (
            str(season) if season is not None else "",
            str(round_) if round_ is not None else "",
        )

    async def _async_update_data(self):
        try:
            # Start with a large page size; use API-returned limit/offset/total for correctness
            request_limit = 200
            offset = 0

            races_by_key: dict[tuple, dict] = {}
            order: list[tuple] = []

            def merge_page(page_races: list[dict]):
                for race in page_races or []:
                    key = self._race_key(race)
                    existing = races_by_key.get(key)
                    if not existing:
                        copy = dict(race)
                        copy["Results"] = list(race.get("Results", []) or [])
                        races_by_key[key] = copy
                        order.append(key)
                    else:
                        seen = {
                            (res.get("Driver", {}).get("driverId"), res.get("position"))
                            for res in existing.get("Results", [])
                        }
                        for res in race.get("Results", []) or []:
                            ident = (
                                res.get("Driver", {}).get("driverId"),
                                res.get("position"),
                            )
                            if ident not in seen:
                                existing["Results"].append(res)
                                seen.add(ident)

            # Fetch first page (use recent TTL; we'll apply more specific TTLs
            # for additional pages once we know the total/last offset).
            first = await self._fetch_page(
                request_limit, offset, ttl_seconds=self._ttl_recent
            )
            mr = (first or {}).get("MRData", {})
            total = int((mr.get("total") or "0"))
            limit_used = int((mr.get("limit") or request_limit))
            offset_used = int((mr.get("offset") or offset))

            merge_page(((mr.get("RaceTable", {}) or {}).get("Races", []) or []))

            # Determine last page offset for TTL selection
            try:
                last_page_offset = (max(0, total - 1) // max(1, limit_used)) * max(
                    1, limit_used
                )
            except Exception:
                last_page_offset = offset_used

            # Defensive cap for pagination loop, based on server-reported totals.
            max_loops = 50
            if total > 0 and limit_used > 0:
                max_loops = max(1, ((total + limit_used - 1) // limit_used) + 1)

            # Iterate deterministically using server-reported paging
            next_offset = offset_used + limit_used
            # Cap loop iterations defensively
            safety = 0
            while next_offset < total and safety < max_loops:
                page_ttl = self._ttl_for_offset(
                    next_offset, last_page_offset, limit_used
                )
                page = await self._fetch_page(
                    limit_used, next_offset, ttl_seconds=page_ttl
                )
                pmr = (page or {}).get("MRData", {})
                praces = (pmr.get("RaceTable", {}) or {}).get("Races", []) or []
                merge_page(praces)
                with suppress(Exception):
                    limit_used = int(pmr.get("limit") or limit_used)
                    offset_used = int(pmr.get("offset") or next_offset)
                    total = int(pmr.get("total") or total)
                    if total > 0 and limit_used > 0:
                        max_loops = max(
                            max_loops,
                            max(1, ((total + limit_used - 1) // limit_used) + 1),
                        )
                next_offset = offset_used + limit_used
                safety += 1

            # Assemble and sort by season then numeric round
            assembled_races = [races_by_key[k] for k in order]
            assembled_races.sort(
                key=lambda r: (str(r.get("season")), int(str(r.get("round") or 0)))
            )
            if total > 0 and len(assembled_races) < total:
                _LOGGER.warning(
                    "Season results pagination incomplete: expected %s races, got %s",
                    total,
                    len(assembled_races),
                )
            return {
                "MRData": {
                    "RaceTable": {
                        "Races": assembled_races,
                    }
                }
            }
        except Exception as err:
            raise UpdateFailed(f"Error fetching season results: {err}") from err


class F1SprintResultsCoordinator(DataUpdateCoordinator):
    """Fetch sprint results for the current season (single, non-paginated endpoint)."""

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        name: str,
        session=None,
        user_agent: str | None = None,
        cache=None,
        inflight=None,
        ttl_seconds: int = 60,
        persist_map=None,
        persist_save=None,
        config_entry: ConfigEntry | None = None,
    ):
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(hours=1),
            config_entry=config_entry,
        )
        self._session = session or async_get_clientsession(hass)
        self._headers = {"User-Agent": str(user_agent)} if user_agent else None
        self._url = url
        self._cache = cache
        self._inflight = inflight
        self._ttl = int(ttl_seconds or 60)
        self._persist = persist_map
        self._persist_save = persist_save

    async def async_close(self, *_):
        return

    async def _async_update_data(self):
        try:
            async with async_timeout.timeout(10):
                return await fetch_json(
                    self.hass,
                    self._session,
                    self._url,
                    headers=self._headers,
                    ttl_seconds=self._ttl,
                    cache=self._cache,
                    inflight=self._inflight,
                    persist_map=self._persist,
                    persist_save=self._persist_save,
                )
        except Exception as err:
            raise UpdateFailed(f"Error fetching sprint results: {err}") from err


class FiaDocumentsCoordinator(DataUpdateCoordinator):
    """Coordinator that scrapes FIA decision documents for the active race weekend."""

    def __init__(
        self,
        hass: HomeAssistant,
        race_coordinator: DataUpdateCoordinator,
        *,
        session=None,
        cache=None,
        inflight=None,
        ttl_seconds: int = FIA_DOCS_POLL_INTERVAL,
        persist_map=None,
        persist_save=None,
        config_entry: ConfigEntry | None = None,
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="FIA Documents Coordinator",
            update_interval=timedelta(
                seconds=max(60, int(ttl_seconds or FIA_DOCS_POLL_INTERVAL))
            ),
            config_entry=config_entry,
        )
        self._session = session or async_get_clientsession(hass)
        self._race_coordinator = race_coordinator
        self._cache = cache
        self._inflight = inflight
        self._ttl = max(60, int(ttl_seconds or FIA_DOCS_POLL_INTERVAL))
        self._persist = persist_map
        self._persist_save = persist_save
        self._season_url_cache: dict[str, str] = {}

    async def async_close(self, *_):
        return

    async def _async_update_data(self):
        race = self._get_next_race()
        if not race:
            return {"event_key": None, "race": None, "documents": []}

        season = str(race.get("season") or datetime.utcnow().year)
        round_ = str(race.get("round") or "")
        event_key = f"{season}_{round_ or 'next'}"

        season_url = await self._get_season_url(season)

        try:
            async with async_timeout.timeout(FIA_DOCS_FETCH_TIMEOUT):
                html = await fetch_text(
                    self.hass,
                    self._session,
                    season_url,
                    ttl_seconds=self._ttl,
                    cache=self._cache,
                    inflight=self._inflight,
                    persist_map=self._persist,
                    persist_save=self._persist_save,
                )
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Error fetching FIA documents: {err}") from err

        try:
            docs = parse_fia_documents(html)
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Error parsing FIA documents: {err}") from err

        return {
            "event_key": event_key,
            "race": self._summarize_race(race),
            "documents": docs,
        }

    async def _get_season_url(self, season: str) -> str:
        cached = self._season_url_cache.get(season)
        if cached:
            return cached
        slug = None
        try:
            async with async_timeout.timeout(FIA_DOCS_FETCH_TIMEOUT):
                html = await fetch_text(
                    self.hass,
                    self._session,
                    FIA_SEASON_LIST_URL,
                    ttl_seconds=self._ttl,
                    cache=self._cache,
                    inflight=self._inflight,
                    persist_map=self._persist,
                    persist_save=self._persist_save,
                )
            slug = self._extract_season_slug(html, season)
            if not slug:
                async with async_timeout.timeout(FIA_DOCS_FETCH_TIMEOUT):
                    html = await fetch_text(
                        self.hass,
                        self._session,
                        FIA_DOCUMENTS_BASE_URL,
                        ttl_seconds=self._ttl,
                        cache=self._cache,
                        inflight=self._inflight,
                        persist_map=self._persist,
                        persist_save=self._persist_save,
                    )
                slug = self._extract_season_slug(html, season)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Failed to resolve FIA season slug for %s: %s", season, err)
        if not slug:
            _LOGGER.debug(
                "FIA season slug not found for %s; using fallback URL", season
            )
        url = (
            urljoin(FIA_DOCUMENTS_BASE_URL + "/", slug)
            if slug
            else FIA_SEASON_FALLBACK_URL
        )
        self._season_url_cache[season] = url
        return url

    @staticmethod
    def _extract_season_slug(html: str, season: str) -> str | None:
        if not isinstance(html, str) or not html:
            return None
        season_escaped = re.escape(str(season))
        pattern = re.compile(
            rf'(?:href|value)=(["\'])'
            rf'(?P<href>(?:https?://[^"\']+)?/documents[^"\']*season/season-{season_escaped}-\d+)'
            rf"\1",
            re.IGNORECASE,
        )
        match = pattern.search(html)
        if match:
            return match.group("href")
        return None

    def _summarize_race(self, race: dict | None) -> dict:
        if not isinstance(race, dict):
            return {}
        circuit = race.get("Circuit", {}) or {}
        location = circuit.get("Location", {}) or {}
        return {
            "season": race.get("season"),
            "round": race.get("round"),
            "race_name": race.get("raceName"),
            "race_date": race.get("date"),
            "race_time": race.get("time"),
            "circuit_id": circuit.get("circuitId"),
            "circuit_name": circuit.get("circuitName"),
            "circuit_url": circuit.get("url"),
            "locality": location.get("locality"),
            "country": location.get("country"),
        }

    def _get_next_race(self) -> dict | None:
        data = getattr(self._race_coordinator, "data", None) or {}
        races = (data.get("MRData") or {}).get("RaceTable", {}).get("Races", [])
        if not isinstance(races, list):
            return None
        _, race = get_next_race(
            races,
            grace=RACE_SWITCH_GRACE,
            fallback_last=True,
        )
        return race


class LiveSessionCoordinator(DataUpdateCoordinator):
    """Fetch current or next session from the LiveTiming index."""

    def __init__(
        self,
        hass: HomeAssistant,
        year: int,
        session=None,
        config_entry: ConfigEntry | None = None,
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="F1 Live Session Coordinator",
            update_interval=timedelta(hours=1),
            config_entry=config_entry,
        )
        self._session = session or async_get_clientsession(hass)
        self.year = year
        self._last_good_index: dict | None = None
        # Expose last HTTP status so the live window supervisor can distinguish
        # "index not published yet" (403/404) from other failures.
        self.last_http_status: int | None = None
        self._log_throttle: dict[str, float] = {}

    def _log_throttled(
        self,
        level: int,
        key: str,
        msg: str,
        *args,
        interval_seconds: float = 3600,
    ) -> None:
        now = time.monotonic()
        last = self._log_throttle.get(key, 0.0)
        if now - last < interval_seconds:
            return
        self._log_throttle[key] = now
        _LOGGER.log(level, msg, *args)

    async def async_close(self, *_):
        return

    async def _async_update_data(self):
        payload = await self._fetch_index()
        if payload:
            self._last_good_index = payload
            return payload
        if self._last_good_index:
            # Avoid flooding logs if callers are forcing frequent refreshes.
            self._log_throttled(
                logging.DEBUG,
                "using_cached_index",
                "Using cached LiveTiming index (server returned empty response)",
                interval_seconds=3600,
            )
            return self._last_good_index
        return payload

    async def _fetch_index(self, *, cache_bust: bool = False):
        url = LIVETIMING_INDEX_URL.format(year=self.year)
        if cache_bust:
            url = f"{url}?t={int(time.time())}"
        try:
            async with async_timeout.timeout(10):
                async with self._session.get(url) as response:
                    text = await response.text()
                    self.last_http_status = response.status
                    if response.status != 200:
                        preview = text[:200]
                        # 403/404 is common when a new season index isn't published yet.
                        if response.status in (403, 404):
                            self._log_throttled(
                                logging.INFO,
                                f"index_http_{response.status}_{self.year}",
                                "LiveTiming index not available for year %s yet (HTTP %s). Will retry later.",
                                self.year,
                                response.status,
                                interval_seconds=6 * 3600,
                            )
                            _LOGGER.debug(
                                "Index fetch failed (%s): %s", response.status, preview
                            )
                        else:
                            self._log_throttled(
                                logging.WARNING,
                                f"index_http_{response.status}_{self.year}",
                                "Index fetch failed (%s): %s",
                                response.status,
                                preview,
                                interval_seconds=3600,
                            )
                        return None
                    payload = json.loads(text.lstrip("\ufeff") or "null")
        except Exception as err:
            self._log_throttled(
                logging.WARNING,
                f"index_fetch_exception_{self.year}",
                "Error fetching index (%s): %s",
                "cache-bust" if cache_bust else "standard",
                err,
                interval_seconds=1800,
            )
            return None
        if self._has_sessions(payload):
            return payload
        if not cache_bust:
            _LOGGER.debug("Index response missing sessions; retrying with cache-buster")
            return await self._fetch_index(cache_bust=True)
        self._log_throttled(
            logging.WARNING,
            f"index_missing_sessions_{self.year}",
            "Index response still missing sessions after cache-bust",
            interval_seconds=3600,
        )
        return None

    @staticmethod
    def _has_sessions(payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        meetings = payload.get("Meetings") or payload.get("meetings")
        sessions = payload.get("Sessions") or payload.get("sessions")
        if isinstance(meetings, list) and meetings:
            return True
        if isinstance(meetings, dict) and meetings:
            return True
        if isinstance(sessions, list) and sessions:
            return True
        if isinstance(sessions, dict) and sessions:
            return True
        return False


class TrackStatusCoordinator(DataUpdateCoordinator):
    """Coordinator for TrackStatus updates using SignalR."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: LiveSessionCoordinator,
        delay_seconds: int = 0,
        bus: LiveBus | None = None,
        config_entry: ConfigEntry | None = None,
        delay_controller: LiveDelayController | None = None,
        live_state: LiveAvailabilityTracker | None = None,
    ):
        super().__init__(
            hass,
            coordinator_logger("track_status", suppress_manual=True),
            name="F1 Track Status Coordinator",
            update_interval=None,
            config_entry=config_entry,
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._last_message = None
        self.data_list: list[dict] = []
        self._deliver_handle: Optional[asyncio.Handle] = None
        self._deliver_handles: list[asyncio.Handle] = []
        self._bus = bus
        self._unsub: Optional[Callable[[], None]] = None
        self._delay_listener: Optional[Callable[[], None]] = None
        self._t0 = None
        self._startup_cutoff = None
        self._delay = max(0, int(delay_seconds or 0))
        self._replay_mode = False
        if delay_controller is not None:
            self._delay_listener = delay_controller.add_listener(self.set_delay)
        # Lightweight dedupe of untimestamped repeats
        self._last_untimestamped_fingerprint: str | None = None
        self._live_state_unsub: Optional[Callable[[], None]] = None
        if live_state is not None:
            self._live_state_unsub = live_state.add_listener(self._handle_live_state)

    async def async_close(self, *_):
        if self._unsub:
            with suppress(Exception):
                self._unsub()
            self._unsub = None
        if self._deliver_handle:
            with suppress(Exception):
                self._deliver_handle.cancel()
            self._deliver_handle = None
        # Cancel any queued delayed deliveries
        with suppress(Exception):
            _cancel_handles(self._deliver_handles)
        if self._delay_listener:
            with suppress(Exception):
                self._delay_listener()
            self._delay_listener = None
        if self._live_state_unsub:
            with suppress(Exception):
                self._live_state_unsub()
            self._live_state_unsub = None

    async def _async_update_data(self):
        return self._last_message

    def _on_bus_message(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        # Drop old messages near startup
        utc_str = (
            msg.get("Utc")
            or msg.get("utc")
            or msg.get("processedAt")
            or msg.get("timestamp")
        )
        with suppress(Exception):
            if utc_str:
                ts = datetime.fromisoformat(str(utc_str).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    from datetime import timezone as _tz

                    ts = ts.replace(tzinfo=_tz.utc)
                if self._startup_cutoff and ts < self._startup_cutoff:
                    return
        # Dedupe untimestamped exact repeats to avoid flooding when delayed
        try:
            has_ts = any(k in msg for k in ("Utc", "utc", "processedAt", "timestamp"))
        except Exception:
            has_ts = False
        if not has_ts:
            with suppress(Exception):
                fp = json.dumps(
                    {
                        "Status": msg.get("Status"),
                        "Message": msg.get("Message") or msg.get("TrackStatus"),
                    },
                    sort_keys=True,
                    default=str,
                )
                if self._last_untimestamped_fingerprint == fp:
                    return
                self._last_untimestamped_fingerprint = fp
        delay = 0 if self._replay_mode else self._delay
        if delay > 0:
            # Queue each delivery independently so intermediate states (e.g. YELLOW) survive
            try:
                handle = self.hass.loop.call_later(
                    delay, lambda m=msg: self._deliver(m)
                )
                self._deliver_handles.append(handle)
            except Exception:
                # Fallback to immediate delivery
                with suppress(Exception):
                    self._deliver(msg)
        else:
            # Immediate delivery; keep legacy single-handle for symmetry
            with suppress(Exception):
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            self._deliver_handle = self.hass.loop.call_soon(
                lambda m=msg: self._deliver(m)
            )

    @staticmethod
    def _parse_message(data):
        if not isinstance(data, dict):
            return None
        # Handle live feed entries
        messages = data.get("M")
        if isinstance(messages, list):
            for update in messages:
                args = update.get("A", [])
                if len(args) >= 2 and args[0] == "TrackStatus":
                    return args[1]
        # Handle RPC responses
        result = data.get("R")
        if isinstance(result, dict) and "TrackStatus" in result:
            return result.get("TrackStatus")
        return None

    def _deliver(self, msg: dict) -> None:
        self.available = True
        self._last_message = msg
        self.data_list = [msg]
        self.async_set_updated_data(msg)
        with suppress(Exception):
            self.hass.data[LATEST_TRACK_STATUS] = msg
        if _LOGGER.isEnabledFor(logging.DEBUG):
            with suppress(Exception):
                _LOGGER.debug(
                    "TrackStatus delivered at %s status=%s message=%s",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                    (msg or {}).get("Status"),
                    (msg or {}).get("Message"),
                )

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        # Capture connection time and startup window
        try:
            from datetime import timezone

            self._t0 = datetime.now(timezone.utc)
            self._startup_cutoff = self._t0 - timedelta(seconds=30)
        except Exception:
            self._startup_cutoff = None
        # Subscribe to LiveBus
        try:
            self._unsub = (
                self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")
            ).subscribe("TrackStatus", self._on_bus_message)  # type: ignore[attr-defined]
        except Exception:
            self._unsub = None

    def set_delay(self, seconds: int) -> None:
        _apply_delay_with_handles(self, seconds, self._deliver_handles)

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        if reason == "init":
            return
        self._replay_mode = _is_replay_delay_reason(reason)
        if self._replay_mode:
            if self._deliver_handle:
                with suppress(Exception):
                    self._deliver_handle.cancel()
                self._deliver_handle = None
            if self._deliver_handles:
                for handle in list(self._deliver_handles):
                    with suppress(Exception):
                        handle.cancel()
                self._deliver_handles.clear()
        self.available = is_live
        if not is_live:
            self._last_message = None
            self.data_list = []
            # Clear global cache so sensors don't fall back to stale data
            with suppress(Exception):
                self.hass.data[LATEST_TRACK_STATUS] = None
            # Notify entities to clear their state
            self.async_set_updated_data(self._last_message)
        # In replay mode, disable startup cutoff and clear dedup state
        if is_live and reason == "replay":
            self._startup_cutoff = None
            self._last_untimestamped_fingerprint = None
            _LOGGER.debug("TrackStatus: disabled startup cutoff for replay mode")


class SessionStatusCoordinator(DataUpdateCoordinator):
    """Coordinator for SessionStatus updates using SignalR."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: LiveSessionCoordinator,
        delay_seconds: int = 0,
        bus: LiveBus | None = None,
        config_entry: ConfigEntry | None = None,
        delay_controller: LiveDelayController | None = None,
        live_state: LiveAvailabilityTracker | None = None,
    ):
        super().__init__(
            hass,
            coordinator_logger("session_status", suppress_manual=True),
            name="F1 Session Status Coordinator",
            update_interval=None,
            config_entry=config_entry,
        )
        _init_signalr_state(
            self,
            hass,
            session_coord,
            delay_seconds,
            bus=bus,
            delay_controller=delay_controller,
            live_state=live_state,
        )

    async def async_close(self, *_):
        if self._unsub:
            with suppress(Exception):
                self._unsub()
            self._unsub = None
        if self._deliver_handle:
            with suppress(Exception):
                self._deliver_handle.cancel()
            self._deliver_handle = None
        if self._delay_listener:
            with suppress(Exception):
                self._delay_listener()
            self._delay_listener = None
        if self._live_state_unsub:
            with suppress(Exception):
                self._live_state_unsub()
            self._live_state_unsub = None

    async def _async_update_data(self):
        return self._last_message

    def _on_bus_message(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        delay = 0 if self._replay_mode else self._delay
        self._deliver_handle = _schedule_message_delivery(
            self.hass.loop, self._deliver_handle, delay, self._deliver, msg
        )

    @staticmethod
    def _parse_message(data):
        if not isinstance(data, dict):
            return None
        messages = data.get("M")
        if isinstance(messages, list):
            for update in messages:
                args = update.get("A", [])
                if len(args) >= 2 and args[0] == "SessionStatus":
                    return args[1]
        result = data.get("R")
        if isinstance(result, dict) and "SessionStatus" in result:
            return result.get("SessionStatus")
        return None

    def _deliver(self, msg: dict) -> None:
        self.available = True
        self._last_message = msg
        self.data_list = [msg]
        self.async_set_updated_data(msg)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            with suppress(Exception):
                _LOGGER.debug(
                    "SessionStatus delivered at %s status=%s started=%s",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                    (msg or {}).get("Status"),
                    (msg or {}).get("Started"),
                )

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        try:
            self._unsub = (
                self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")
            ).subscribe("SessionStatus", self._on_bus_message)  # type: ignore[attr-defined]
        except Exception:
            self._unsub = None

    def set_delay(self, seconds: int) -> None:
        _apply_delay_simple(self, seconds)

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        if reason == "init":
            return
        self._replay_mode = _is_replay_delay_reason(reason)
        if self._replay_mode:
            self._deliver_handle = _cancel_handle(self._deliver_handle)
        self.available = is_live
        if not is_live:
            self._last_message = None
            self.data_list = []
            # Notify entities to clear their state
            self.async_set_updated_data(self._last_message)


class TopThreeCoordinator(DataUpdateCoordinator):
    """Coordinator for TopThree updates using SignalR.

    Normaliserar TopThree-flödet till ett enkelt state:
        {
            "withheld": bool | None,
            "lines": [dict | None, dict | None, dict | None],
            "last_update_ts": str | None,
        }
    där varje line är direkt baserad på feedens rader (Position, Tla, DiffToLeader osv).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: LiveSessionCoordinator,
        delay_seconds: int = 0,
        bus: LiveBus | None = None,
        config_entry: ConfigEntry | None = None,
        delay_controller: LiveDelayController | None = None,
        live_state: LiveAvailabilityTracker | None = None,
    ):
        super().__init__(
            hass,
            coordinator_logger("top_three", suppress_manual=True),
            name="F1 Top Three Coordinator",
            update_interval=None,
            config_entry=config_entry,
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._state: dict[str, Any] = {
            "withheld": None,
            "lines": [None, None, None],
            "last_update_ts": None,
        }
        _init_stream_delay_state(
            self,
            delay_seconds,
            bus=bus,
            delay_controller=delay_controller,
            live_state=live_state,
        )

    async def async_close(self, *_):
        _close_stream_delay_state(self)

    async def _async_update_data(self):
        return self._state

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        if reason == "init":
            return
        self._replay_mode = _is_replay_delay_reason(reason)
        if self._replay_mode and self._deliver_handle:
            with suppress(Exception):
                self._deliver_handle.cancel()
            self._deliver_handle = None
        self.available = is_live
        # Note: For replay mode, we don't schedule deliver here.
        # The inject_message call will handle delivery with the correct initial state.
        if is_live and reason == "replay":
            _LOGGER.debug(
                "TopThree: replay mode activated, waiting for initial state injection"
            )
        if not is_live:
            with suppress(Exception):
                self._state = {
                    "withheld": None,
                    "lines": [None, None, None],
                    "last_update_ts": None,
                }
                # Notify entities to clear their state
                self.async_set_updated_data(self._state)

    def set_delay(self, seconds: int) -> None:
        _apply_delay_simple(self, seconds)

    def _schedule_deliver(self) -> None:
        delay = 0 if self._replay_mode else self._delay
        self._deliver_handle = _schedule_deliver_handle(
            self.hass.loop, self._deliver_handle, delay, self._deliver
        )

    def _merge_topthree(self, payload: dict) -> None:
        """Merge a TopThree payload (full snapshot or partial delta) into state."""
        if not isinstance(payload, dict):
            return

        state = self._state

        # Withheld flag (om F1 väljer att inte visa topp 3)
        with suppress(Exception):
            if "Withheld" in payload:
                state["withheld"] = bool(payload.get("Withheld"))
        lines = payload.get("Lines")
        cur_lines = state.get("lines") or [None, None, None]

        # Debug: Log what we received
        _LOGGER.debug(
            "TopThree _merge: Lines type=%s, Lines=%s",
            type(lines).__name__,
            str(lines)[:500] if lines else None,
        )

        # Full snapshot: Lines som lista [P1, P2, P3]
        if isinstance(lines, list):
            _LOGGER.debug("TopThree: processing as list with %d items", len(lines))
            new_lines: list[Any] = [None, None, None]
            for idx in range(3):
                try:
                    item = lines[idx]
                    _LOGGER.debug(
                        "TopThree: list[%d] type=%s, value=%s",
                        idx,
                        type(item).__name__,
                        str(item)[:200] if item else None,
                    )
                except Exception:
                    item = None
                new_lines[idx] = item if isinstance(item, dict) else None
            state["lines"] = new_lines
        # Delta: Lines som dict { "0": {...}, "1": {...}, "2": {...} }
        elif isinstance(lines, dict):
            for key, delta in lines.items():
                idx = None
                with suppress(Exception):
                    idx = int(key)
                if idx is None:
                    continue
                if idx < 0 or idx > 2:
                    continue
                if not isinstance(delta, dict):
                    continue
                base = cur_lines[idx]
                if not isinstance(base, dict):
                    base = {}
                try:
                    base.update(delta)
                except Exception:  # noqa: BLE001
                    _LOGGER.debug(
                        "TopThree: failed to merge delta for line %s",
                        key,
                        exc_info=True,
                    )
                cur_lines[idx] = base
            state["lines"] = cur_lines

        try:
            state["last_update_ts"] = dt_util.utcnow().isoformat()
        except Exception:
            state["last_update_ts"] = None

    def _on_bus_message(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        try:
            self._merge_topthree(msg)
        except Exception:
            _LOGGER.debug("TopThree: failed to merge message")
            return
        # Log what we got after merge
        lines = self._state.get("lines", [])
        line_summary = [
            (line.get("Tla") if isinstance(line, dict) else None) for line in lines
        ]
        _LOGGER.debug("TopThree: merged message, lines=%s", line_summary)
        self._schedule_deliver()

    def _deliver(self) -> None:
        # Pushar aktuellt state till sensorerna
        lines = self._state.get("lines", [])
        line_summary = [
            (line.get("Tla") if isinstance(line, dict) else None) for line in lines
        ]
        _LOGGER.debug("TopThree: delivering state, lines=%s", line_summary)
        self.async_set_updated_data(self._state)

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        # Prenumerera på TopThree från LiveBus
        try:
            bus = self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")  # type: ignore[assignment]
        except Exception:
            bus = None
        if bus is not None:
            try:
                self._unsub = bus.subscribe("TopThree", self._on_bus_message)
            except Exception:
                self._unsub = None


class SessionInfoCoordinator(DataUpdateCoordinator):
    """Coordinator for SessionInfo updates using SignalR."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: LiveSessionCoordinator,
        delay_seconds: int = 0,
        bus: LiveBus | None = None,
        config_entry: ConfigEntry | None = None,
        delay_controller: LiveDelayController | None = None,
        live_state: LiveAvailabilityTracker | None = None,
    ):
        super().__init__(
            hass,
            coordinator_logger("session_info", suppress_manual=True),
            name="F1 Session Info Coordinator",
            update_interval=None,
            config_entry=config_entry,
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._last_message = None
        self.data_list: list[dict] = []
        _init_stream_delay_state(
            self,
            delay_seconds,
            bus=bus,
            delay_controller=delay_controller,
            live_state=live_state,
        )

    async def async_close(self, *_):
        _close_stream_delay_state(self)

    async def _async_update_data(self):
        return self._last_message

    def _on_bus_message(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        delay = 0 if self._replay_mode else self._delay
        if delay > 0:
            with suppress(Exception):
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            self._deliver_handle = self.hass.loop.call_later(
                delay, lambda m=msg: self._deliver(m)
            )
        else:
            with suppress(Exception):
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            self._deliver_handle = self.hass.loop.call_soon(
                lambda m=msg: self._deliver(m)
            )

    @staticmethod
    def _parse_message(data):
        if not isinstance(data, dict):
            return None
        messages = data.get("M")
        if isinstance(messages, list):
            for update in messages:
                args = update.get("A", [])
                if len(args) >= 2 and args[0] == "SessionInfo":
                    return args[1]
        result = data.get("R")
        if isinstance(result, dict) and "SessionInfo" in result:
            return result.get("SessionInfo")
        return None

    def _deliver(self, msg: dict) -> None:
        self.available = True
        self._last_message = msg
        self.data_list = [msg]
        self.async_set_updated_data(msg)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            with suppress(Exception):
                name = (msg or {}).get("Name")
                t = (msg or {}).get("Type")
                _LOGGER.debug(
                    "SessionInfo delivered at %s type=%s name=%s",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                    t,
                    name,
                )

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        try:
            self._unsub = (
                self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")
            ).subscribe("SessionInfo", self._on_bus_message)  # type: ignore[attr-defined]
        except Exception:
            self._unsub = None

    def set_delay(self, seconds: int) -> None:
        _apply_delay_simple(self, seconds)

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        if reason == "init":
            return
        self._replay_mode = _is_replay_delay_reason(reason)
        if self._replay_mode:
            self._deliver_handle = _cancel_handle(self._deliver_handle)
        self.available = is_live
        if not is_live:
            self._last_message = None
            self.data_list = []
            # Notify entities to clear their state
            self.async_set_updated_data(self._last_message)


class SessionClockCoordinator(DataUpdateCoordinator):
    """Coordinator deriving official timer values from live timing clock streams."""

    _FINAL_STATES = frozenset({"Finalised", "Ends"})
    _ACTIVE_OR_ENDED_STATES = frozenset(
        {"Started", "Resumed", "Inactive", "Aborted", "Finished", "Finalised", "Ends"}
    )
    _QUALI_TOTALS = {1: 18 * 60, 2: 15 * 60, 3: 12 * 60}
    _SPRINT_QUALI_TOTALS = {1: 12 * 60, 2: 10 * 60, 3: 8 * 60}

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: LiveSessionCoordinator,
        delay_seconds: int = 0,
        bus: LiveBus | None = None,
        config_entry: ConfigEntry | None = None,
        delay_controller: LiveDelayController | None = None,
        live_state: LiveAvailabilityTracker | None = None,
        live_supervisor: LiveSessionSupervisor | None = None,
    ) -> None:
        super().__init__(
            hass,
            coordinator_logger("session_clock", suppress_manual=True),
            name="F1 Session Clock Coordinator",
            update_interval=None,
            config_entry=config_entry,
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._state = self._empty_state()
        self.data_list: list[dict] = [self._state]
        _init_stream_delay_state(
            self,
            delay_seconds,
            bus=bus,
            delay_controller=delay_controller,
            live_state=live_state,
        )
        self._live_supervisor = live_supervisor
        self._tick_unsub: Callable[[], None] | None = None
        self._reset_runtime()

    async def async_close(self, *_):
        self._stop_tick()
        _close_stream_delay_state(self)

    async def _async_update_data(self):
        return self._state

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "clock_remaining_s": None,
            "clock_elapsed_s": None,
            "clock_total_s": None,
            "race_start_utc": None,
            "race_three_hour_cap_utc": None,
            "race_three_hour_remaining_s": None,
            "session_part": None,
            "session_type": None,
            "session_name": None,
            "session_status": None,
            "session_start_utc": None,
            "clock_running": False,
            "clock_phase": "idle",
            "source_quality": "unavailable",
            "reference_utc": None,
            "last_server_utc": None,
        }

    def _reset_runtime(self) -> None:
        self._session_info: dict[str, Any] = {}
        self._session_status: dict[str, Any] = {}
        self._clock_anchor_utc: datetime | None = None
        self._clock_anchor_remaining_s: int | None = None
        self._clock_anchor_extrapolating = False
        self._clock_totals: dict[int, int] = {}
        self._session_part_events: list[tuple[datetime, int]] = []
        self._session_part_event_keys: set[tuple[str, int]] = set()
        self._session_status_events: list[tuple[datetime, str]] = []
        self._session_status_event_keys: set[tuple[str, str]] = set()
        self._session_start_utc: datetime | None = None
        self._race_start_utc: datetime | None = None
        self._last_heartbeat_utc: datetime | None = None
        self._last_heartbeat_mono: float | None = None

    @staticmethod
    def _parse_utc(value: Any) -> datetime | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            dt_val = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt_val.tzinfo is None:
            dt_val = dt_val.replace(tzinfo=timezone.utc)
        return dt_val.astimezone(timezone.utc)

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        if not isinstance(value, datetime):
            return None
        return value.isoformat(timespec="seconds")

    @staticmethod
    def _parse_remaining(value: Any) -> int | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        parts = text.split(":")
        if len(parts) != 3:
            return None
        try:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
        except ValueError:
            return None
        total = int(hours * 3600 + minutes * 60 + seconds)
        return max(0, total)

    @staticmethod
    def _iter_series_items(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            result: list[dict[str, Any]] = []
            try:
                keys = sorted(
                    value.keys(),
                    key=lambda k: int(k) if str(k).isdigit() else str(k),
                )
            except Exception:
                keys = list(value.keys())
            for key in keys:
                item = value.get(key)
                if isinstance(item, dict):
                    result.append(item)
            return result
        return []

    def _on_extrapolated_clock(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        remaining_s = self._parse_remaining(msg.get("Remaining"))
        anchor_utc = self._parse_utc(msg.get("Utc"))
        if remaining_s is not None:
            self._clock_anchor_remaining_s = remaining_s
        if anchor_utc is not None:
            self._clock_anchor_utc = anchor_utc
        if "Extrapolating" in msg:
            self._clock_anchor_extrapolating = bool(msg.get("Extrapolating"))
        segment_id = self._segment_id(
            self._resolve_session_part(self._server_now_utc())
        )
        self._update_clock_total(segment_id, remaining_s)
        self._schedule_deliver()

    def _on_heartbeat(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        hb_utc = self._parse_utc(
            msg.get("Utc") or msg.get("utc") or msg.get("processedAt")
        )
        if hb_utc is None:
            return
        self._last_heartbeat_utc = hb_utc
        self._last_heartbeat_mono = time.monotonic()
        self._schedule_deliver()

    def _on_session_status(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        self._session_status = msg
        self._schedule_deliver()

    def _on_session_info(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        self._session_info = msg
        self._schedule_deliver()

    def _on_session_data(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        self._ingest_session_data(msg)
        self._schedule_deliver()

    def _ingest_session_data(self, payload: dict[str, Any]) -> None:
        for item in self._iter_series_items(payload.get("Series")):
            part_raw = item.get("QualifyingPart")
            if part_raw is None:
                continue
            utc = self._parse_utc(item.get("Utc"))
            if utc is None:
                continue
            try:
                part = int(part_raw)
            except (TypeError, ValueError):
                continue
            key = (utc.isoformat(), part)
            if key in self._session_part_event_keys:
                continue
            self._session_part_event_keys.add(key)
            self._session_part_events.append((utc, part))
            self._session_part_events.sort(key=lambda x: x[0])

        for item in self._iter_series_items(payload.get("StatusSeries")):
            status = str(item.get("SessionStatus") or "").strip()
            if not status:
                continue
            utc = self._parse_utc(item.get("Utc"))
            if utc is None:
                continue
            key = (utc.isoformat(), status)
            if key in self._session_status_event_keys:
                continue
            self._session_status_event_keys.add(key)
            self._session_status_events.append((utc, status))
            self._session_status_events.sort(key=lambda x: x[0])
            if status == "Started":
                if self._session_start_utc is None or utc < self._session_start_utc:
                    self._session_start_utc = utc
                if self._race_start_utc is None or utc < self._race_start_utc:
                    self._race_start_utc = utc

    def _schedule_deliver(self) -> None:
        delay = 0 if self._replay_mode else self._delay
        self._deliver_handle = _schedule_deliver_handle(
            self.hass.loop,
            self._deliver_handle,
            delay,
            self._deliver,
        )

    def _server_now_utc(self) -> datetime:
        if (
            isinstance(self._last_heartbeat_utc, datetime)
            and self._last_heartbeat_mono is not None
        ):
            elapsed = max(0.0, time.monotonic() - self._last_heartbeat_mono)
            return self._last_heartbeat_utc + timedelta(seconds=elapsed)
        return dt_util.utcnow()

    def _current_live_window(self):
        live_supervisor = self._live_supervisor
        if live_supervisor is None:
            entry_id = getattr(getattr(self, "config_entry", None), "entry_id", None)
            reg = (
                self.hass.data.get(DOMAIN, {}).get(entry_id, {})
                if entry_id is not None
                else {}
            )
            live_supervisor = reg.get("live_supervisor")
        if live_supervisor is None:
            return None
        return getattr(live_supervisor, "current_window", None)

    def _resolve_session_type_and_name(self) -> tuple[str | None, str | None]:
        info = self._session_info if isinstance(self._session_info, dict) else {}
        session_type = str(info.get("Type") or "").strip() or None
        session_name = str(info.get("Name") or "").strip() or None
        if session_type and session_name:
            return session_type, session_name

        # Fallback: infer from current live window when SessionInfo has not arrived yet.
        try:
            window = self._current_live_window()
            inferred_name = (
                str(getattr(window, "session_name", "")).strip()
                if window is not None
                else ""
            )
            if inferred_name:
                if not session_name:
                    session_name = inferred_name
                if not session_type:
                    lower = inferred_name.lower()
                    if "qualifying" in lower or "shootout" in lower:
                        session_type = "Qualifying"
                    elif "practice" in lower:
                        session_type = "Practice"
                    elif "sprint" in lower:
                        # Sprint is usually emitted under Type "Race".
                        session_type = "Race"
                    elif "race" in lower:
                        session_type = "Race"
        except Exception:
            pass
        return session_type, session_name

    def _session_duration_from_live_window(self) -> int | None:
        window = self._current_live_window()
        if window is None:
            return None
        start = getattr(window, "start_utc", None)
        end = getattr(window, "end_utc", None)
        if not (isinstance(start, datetime) and isinstance(end, datetime)):
            return None
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        duration = int(
            (
                end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
            ).total_seconds()
        )
        if duration <= 0:
            return None
        if duration > (4 * 3600):
            return None
        return duration

    def _session_start_from_live_window(self) -> datetime | None:
        window = self._current_live_window()
        if window is None:
            return None
        start = getattr(window, "start_utc", None)
        if not isinstance(start, datetime):
            return None
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        return start.astimezone(timezone.utc)

    def _is_qualifying_like(self) -> bool:
        session_type, session_name = self._resolve_session_type_and_name()
        type_l = str(session_type or "").lower()
        name_l = str(session_name or "").lower()
        return type_l == "qualifying" or "qualifying" in name_l or "shootout" in name_l

    def _is_main_race(self) -> bool:
        session_type, session_name = self._resolve_session_type_and_name()
        type_l = str(session_type or "").lower()
        if type_l != "race":
            return False
        name_l = str(session_name or "").lower()
        return "sprint" not in name_l

    def _status_is_terminal(self, status: str | None) -> bool:
        if not status:
            return False
        if status in self._FINAL_STATES:
            return True
        if status == "Finished":
            return not self._is_qualifying_like()
        return False

    def _status_from_events(self, now_utc: datetime) -> str | None:
        latest: str | None = None
        for ts, status in self._session_status_events:
            if ts <= now_utc:
                latest = status
            else:
                break
        if latest is not None:
            return latest
        if self._session_status_events:
            return self._session_status_events[-1][1]
        return None

    def _current_status(self, now_utc: datetime) -> str | None:
        if isinstance(self._session_status, dict):
            status = str(
                self._session_status.get("Status")
                or self._session_status.get("Message")
                or ""
            ).strip()
            if status:
                return status
        return self._status_from_events(now_utc)

    def _resolve_session_part(self, now_utc: datetime) -> int | None:
        if not self._session_part_events:
            return None
        current: int | None = None
        for ts, part in self._session_part_events:
            if ts <= now_utc:
                current = part
            else:
                break
        if current is not None:
            return current
        return self._session_part_events[-1][1]

    def _segment_id(self, part: int | None) -> int:
        if self._is_qualifying_like() and isinstance(part, int) and part > 0:
            return part
        return 0

    def _session_duration_from_info(self) -> int | None:
        info = self._session_info if isinstance(self._session_info, dict) else {}
        start = self._parse_utc(info.get("StartDate"))
        end = self._parse_utc(info.get("EndDate"))
        if not (isinstance(start, datetime) and isinstance(end, datetime)):
            return None
        duration = int((end - start).total_seconds())
        if duration <= 0:
            return None
        # Keep this conservative to avoid accidentally treating weekends as one session.
        if duration > (4 * 3600):
            return None
        return duration

    def _default_clock_total(
        self, segment_id: int, remaining_s: int | None = None
    ) -> int | None:
        if self._is_main_race():
            return 2 * 3600
        if self._is_qualifying_like():
            _session_type, session_name = self._resolve_session_type_and_name()
            name_l = str(session_name or "").lower()
            table = (
                self._SPRINT_QUALI_TOTALS
                if ("sprint" in name_l or "shootout" in name_l)
                else self._QUALI_TOTALS
            )
            if segment_id in table:
                return table[segment_id]
            if isinstance(remaining_s, int) and remaining_s > 0:
                ordered = sorted(table.values())
                for candidate in ordered:
                    if remaining_s <= candidate:
                        return candidate
            return max(table.values())
        session_duration = self._session_duration_from_info()
        if isinstance(session_duration, int):
            return session_duration
        session_duration = self._session_duration_from_live_window()
        if isinstance(session_duration, int):
            return session_duration
        session_type, _session_name = self._resolve_session_type_and_name()
        if str(session_type or "").lower() == "practice":
            return 3600

        # Last-resort inference when metadata has not arrived yet.
        if isinstance(remaining_s, int) and remaining_s > 0:
            if remaining_s > 3600:
                # Only races normally run on a 2h session clock.
                return 2 * 3600
            if remaining_s > 3000:
                # Practice-like 1h clock.
                return 3600
        return None

    def _set_clock_total_floor(self, segment_id: int, total_s: int | None) -> None:
        if total_s is None or total_s <= 0:
            return
        prev = self._clock_totals.get(segment_id)
        if prev is None or total_s > prev:
            self._clock_totals[segment_id] = int(total_s)

    def _update_clock_total(self, segment_id: int, remaining_s: int | None) -> None:
        if remaining_s is None or remaining_s <= 0:
            return
        self._set_clock_total_floor(
            segment_id,
            self._default_clock_total(segment_id, remaining_s),
        )

    def _clock_remaining_seconds(self, now_utc: datetime) -> int | None:
        if self._clock_anchor_remaining_s is None:
            return None
        remaining = int(self._clock_anchor_remaining_s)
        if self._clock_anchor_extrapolating and isinstance(
            self._clock_anchor_utc, datetime
        ):
            delta = int((now_utc - self._clock_anchor_utc).total_seconds())
            remaining = remaining - max(0, delta)
        return max(0, remaining)

    def _infer_race_start_from_clock(self) -> datetime | None:
        if not self._is_main_race():
            return None
        if not self._clock_anchor_extrapolating:
            return None
        if not isinstance(self._clock_anchor_utc, datetime):
            return None
        remaining = self._clock_anchor_remaining_s
        if remaining is None:
            return None
        if not (7190 <= remaining <= 7200):
            return None
        offset = max(0, 7200 - remaining)
        return self._clock_anchor_utc - timedelta(seconds=offset)

    def _resolve_race_start(self) -> datetime | None:
        if not self._is_main_race():
            return None
        if isinstance(self._race_start_utc, datetime):
            return self._race_start_utc
        for ts, status in self._session_status_events:
            if status == "Started":
                self._race_start_utc = ts
                return ts
        inferred = self._infer_race_start_from_clock()
        if isinstance(inferred, datetime):
            self._race_start_utc = inferred
        return inferred

    def _resolve_session_start(
        self, clock_total: int | None, clock_remaining: int | None
    ) -> tuple[datetime | None, str | None]:
        if isinstance(self._session_start_utc, datetime):
            return self._session_start_utc, "sessiondata"
        for ts, status in self._session_status_events:
            if status != "Started":
                continue
            if self._session_start_utc is None or ts < self._session_start_utc:
                self._session_start_utc = ts
        if isinstance(self._session_start_utc, datetime):
            return self._session_start_utc, "sessiondata"

        if (
            isinstance(self._clock_anchor_utc, datetime)
            and isinstance(clock_total, int)
            and isinstance(clock_remaining, int)
        ):
            offset = max(0, int(clock_total) - int(clock_remaining))
            return self._clock_anchor_utc - timedelta(seconds=offset), "clock_inferred"

        info = self._session_info if isinstance(self._session_info, dict) else {}
        info_start = self._parse_utc(info.get("StartDate"))
        if isinstance(info_start, datetime):
            return info_start, "sessioninfo"

        window_start = self._session_start_from_live_window()
        if isinstance(window_start, datetime):
            return window_start, "live_window"

        return None, None

    def _source_quality(
        self, has_clock: bool, has_elapsed: bool, has_race_cap: bool
    ) -> str:
        if has_clock:
            return (
                "official"
                if self._last_heartbeat_utc is not None
                else "official_no_heartbeat"
            )
        if has_elapsed:
            return "sessiondata_fallback"
        if has_race_cap:
            return "sessiondata_fallback"
        return "unavailable"

    def _build_state(self) -> dict[str, Any]:
        now_utc = self._server_now_utc()
        session_type, session_name = self._resolve_session_type_and_name()
        status = self._current_status(now_utc)
        session_part = self._resolve_session_part(now_utc)
        segment_id = self._segment_id(session_part)

        clock_remaining = self._clock_remaining_seconds(now_utc)
        self._set_clock_total_floor(
            segment_id,
            self._default_clock_total(segment_id, clock_remaining),
        )
        self._update_clock_total(segment_id, clock_remaining)
        clock_total = self._clock_totals.get(segment_id)
        if clock_total is None and segment_id != 0:
            clock_total = self._clock_totals.get(0)
        clock_elapsed_from_clock = (
            max(0, int(clock_total) - int(clock_remaining))
            if clock_total is not None and clock_remaining is not None
            else None
        )

        session_start_utc, session_start_source = self._resolve_session_start(
            clock_total,
            clock_remaining,
        )
        clock_elapsed_from_start: int | None = None
        if isinstance(session_start_utc, datetime):
            allow_start_fallback = (
                session_start_source in {"sessiondata", "clock_inferred"}
                or clock_remaining is not None
                or status in self._ACTIVE_OR_ENDED_STATES
            )
            if allow_start_fallback and now_utc >= session_start_utc:
                clock_elapsed_from_start = max(
                    0,
                    int((now_utc - session_start_utc).total_seconds()),
                )

        clock_elapsed = clock_elapsed_from_clock
        if isinstance(clock_elapsed_from_start, int):
            if session_start_source == "sessiondata":
                clock_elapsed = (
                    clock_elapsed_from_start
                    if clock_elapsed is None
                    else max(clock_elapsed, clock_elapsed_from_start)
                )
            elif clock_elapsed is None:
                clock_elapsed = clock_elapsed_from_start

        terminal = self._status_is_terminal(status)
        clock_running = bool(
            self._clock_anchor_extrapolating
            and clock_remaining is not None
            and clock_remaining > 0
            and not terminal
        )
        if terminal or (
            clock_remaining == 0 and status in {"Finished", "Finalised", "Ends"}
        ):
            clock_phase = "finished"
        elif clock_running:
            clock_phase = "running"
        elif (
            clock_remaining is not None
            and clock_remaining > 0
            and status
            in {
                "Started",
                "Resumed",
                "Inactive",
                "Aborted",
            }
        ):
            clock_phase = "paused"
        else:
            clock_phase = "idle"

        race_start_utc = self._resolve_race_start()
        race_cap_utc = (
            race_start_utc + timedelta(hours=3)
            if isinstance(race_start_utc, datetime)
            else None
        )
        race_remaining = (
            max(0, int((race_cap_utc - now_utc).total_seconds()))
            if isinstance(race_cap_utc, datetime)
            else None
        )

        has_clock = clock_remaining is not None
        has_elapsed = clock_elapsed is not None
        has_race_cap = race_remaining is not None

        return {
            "clock_remaining_s": clock_remaining,
            "clock_elapsed_s": clock_elapsed,
            "clock_total_s": clock_total,
            "session_start_utc": self._iso(session_start_utc),
            "race_start_utc": self._iso(race_start_utc),
            "race_three_hour_cap_utc": self._iso(race_cap_utc),
            "race_three_hour_remaining_s": race_remaining,
            "session_part": session_part,
            "session_type": session_type,
            "session_name": session_name,
            "session_status": status,
            "clock_running": clock_running,
            "clock_phase": clock_phase,
            "source_quality": self._source_quality(
                has_clock, has_elapsed, has_race_cap
            ),
            "reference_utc": self._iso(self._clock_anchor_utc),
            "last_server_utc": self._iso(now_utc),
        }

    def _stop_tick(self) -> None:
        if self._tick_unsub:
            with suppress(Exception):
                self._tick_unsub()
            self._tick_unsub = None

    def _on_tick(self, _now: datetime | None = None) -> None:
        if not self.available:
            self._stop_tick()
            return
        self._deliver()

    def _should_tick(self, state: dict[str, Any]) -> bool:
        if not self.available:
            return False
        if bool(state.get("clock_running")):
            return True
        status = str(state.get("session_status") or "").strip() or None
        elapsed = state.get("clock_elapsed_s")
        if isinstance(elapsed, int) and not self._status_is_terminal(status):
            return True
        race_remaining = state.get("race_three_hour_remaining_s")
        return (
            isinstance(race_remaining, int)
            and race_remaining > 0
            and not self._status_is_terminal(status)
        )

    def _ensure_tick(self, state: dict[str, Any]) -> None:
        should_tick = self._should_tick(state)
        if should_tick and self._tick_unsub is None:
            self._tick_unsub = async_track_time_interval(
                self.hass,
                self._on_tick,
                timedelta(seconds=1),
            )
        elif not should_tick and self._tick_unsub is not None:
            self._stop_tick()

    def _deliver(self) -> None:
        self.available = True
        self._state = self._build_state()
        self.data_list = [self._state]
        self.async_set_updated_data(self._state)
        self._ensure_tick(self._state)

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        try:
            bus = self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")
        except Exception:
            bus = None
        if bus is None:
            self._unsub = None
            return
        unsubs: list[Callable[[], None]] = []
        for stream, callback in (
            ("ExtrapolatedClock", self._on_extrapolated_clock),
            ("Heartbeat", self._on_heartbeat),
            ("SessionStatus", self._on_session_status),
            ("SessionInfo", self._on_session_info),
            ("SessionData", self._on_session_data),
        ):
            with suppress(Exception):
                unsubs.append(bus.subscribe(stream, callback))
        if not unsubs:
            self._unsub = None
            return

        def _unsub_all() -> None:
            for unsub in list(unsubs):
                with suppress(Exception):
                    unsub()
            unsubs.clear()

        self._unsub = _unsub_all

    def set_delay(self, seconds: int) -> None:
        _apply_delay_simple(self, seconds)

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        if reason == "init":
            return
        self._replay_mode = _is_replay_delay_reason(reason)
        if self._replay_mode:
            self._deliver_handle = _cancel_handle(self._deliver_handle)
        self.available = is_live
        if not is_live:
            self._stop_tick()
            self._reset_runtime()
            self._state = self._empty_state()
            self.data_list = [self._state]
            self.async_set_updated_data(self._state)
