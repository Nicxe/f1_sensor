import json
import logging
import asyncio
import contextlib
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from collections import deque
from urllib.parse import urljoin
from pathlib import Path
import time

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession, async_create_clientsession
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
    CONF_OPERATION_MODE,
    CONF_REPLAY_FILE,
    DEFAULT_OPERATION_MODE,
    OPERATION_MODE_DEVELOPMENT,
    OPERATION_MODE_LIVE,
)
from .signalr import LiveBus
from .replay import ReplaySignalRClient
from .live_window import LiveSessionSupervisor, LiveAvailabilityTracker
from .helpers import (
    build_user_agent,
    fetch_json,
    fetch_text,
    parse_fia_documents,
    PersistentCache,
)
from .live_delay import LiveDelayController
from .calibration import LiveDelayCalibrationManager

_LOGGER = logging.getLogger(__name__)

# Keep treating the current Grand Prix as "next" for a short period after
# lights out, so helpers and sensors do not jump to the following weekend
# immediately when a race starts.
RACE_SWITCH_GRACE = timedelta(hours=3)


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


def coordinator_logger(name: str, *, suppress_manual: bool = False) -> CoordinatorLogger:
    return CoordinatorLogger(
        logging.getLogger(f"{__name__}.{name}"),
        suppress_manual=suppress_manual,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration via config flow."""
    # Create dedicated HTTP session with custom User-Agent for Jolpica/Ergast
    ua_string = await build_user_agent(hass)
    http_session = async_create_clientsession(hass, headers={"User-Agent": ua_string})
    _LOGGER.debug("Using User-Agent for Jolpica/Ergast: %s", ua_string)

    # Per-entry shared HTTP cache and in-flight maps (for Jolpica/Ergast only)
    http_cache: dict = {}
    http_inflight: dict = {}
    # Persistent cache (across restarts) for rarely-changing endpoints
    persisted = PersistentCache(hass, entry.entry_id)
    persisted_map = await persisted.load()

    # Seed in-memory cache from persisted content with conservative startup TTLs
    try:
        from yarl import URL
        from time import monotonic as _mono
        now = _mono()
        def _startup_ttl_for_key(k: str) -> int:
            # Assign longer TTLs to low-churn pages at startup only
            # Results pagination: first pages are most stable late in season
            if "/ergast/f1/current/results.json" in k:
                q = URL(k).query
                offset = int(str(q.get("offset") or "0")) if str(q.get("offset") or "0").isdigit() else 0
                if offset == 0:
                    return 24 * 3600  # 24h
                return 3600  # 1h
            if "/ergast/f1/current/driverstandings.json" in k or "/ergast/f1/current/constructorstandings.json" in k:
                return 3600  # 1h
            if "/ergast/f1/current/last/results.json" in k or "/ergast/f1/current/sprint.json" in k:
                return 3600  # 1h
            if "/ergast/f1/current.json" in k:
                return 300  # 5m
            return 300
        for k, v in (persisted_map or {}).items():
            data = v.get("data") if isinstance(v, dict) else None
            if data is None:
                continue
            ttl = _startup_ttl_for_key(str(k))
            http_cache[k] = (now + ttl, data)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Seeded in-memory cache from persistent store with %d keys", len(http_cache))
    except Exception:
        pass

    race_coordinator = F1DataCoordinator(
        hass, API_URL, "F1 Race Data Coordinator", session=http_session, cache=http_cache, inflight=http_inflight, ttl_seconds=30, persist_map=persisted_map, persist_save=persisted.schedule_save, config_entry=entry
    )
    driver_coordinator = F1DataCoordinator(
        hass, DRIVER_STANDINGS_URL, "F1 Driver Standings Coordinator", session=http_session, cache=http_cache, inflight=http_inflight, ttl_seconds=60, persist_map=persisted_map, persist_save=persisted.schedule_save, config_entry=entry
    )
    constructor_coordinator = F1DataCoordinator(
        hass, CONSTRUCTOR_STANDINGS_URL, "F1 Constructor Standings Coordinator", session=http_session, cache=http_cache, inflight=http_inflight, ttl_seconds=60, persist_map=persisted_map, persist_save=persisted.schedule_save, config_entry=entry
    )
    last_race_coordinator = F1DataCoordinator(
        hass, LAST_RACE_RESULTS_URL, "F1 Last Race Results Coordinator", session=http_session, cache=http_cache, inflight=http_inflight, ttl_seconds=60, persist_map=persisted_map, persist_save=persisted.schedule_save, config_entry=entry
    )
    season_results_coordinator = F1SeasonResultsCoordinator(
        hass, SEASON_RESULTS_URL, "F1 Season Results Coordinator", session=http_session, cache=http_cache, inflight=http_inflight, ttl_seconds=60, persist_map=persisted_map, persist_save=persisted.schedule_save, config_entry=entry
    )
    sprint_results_coordinator = F1SprintResultsCoordinator(
        hass, SPRINT_RESULTS_URL, "F1 Sprint Results Coordinator", session=http_session, cache=http_cache, inflight=http_inflight, ttl_seconds=60, persist_map=persisted_map, persist_save=persisted.schedule_save, config_entry=entry
    )
    fia_documents_coordinator = FiaDocumentsCoordinator(
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
    year = datetime.utcnow().year
    session_coordinator = LiveSessionCoordinator(hass, year, config_entry=entry)
    enable_rc = entry.data.get("enable_race_control", False)
    configured_delay = int(entry.data.get("live_delay_seconds", 0) or 0)
    delay_controller = LiveDelayController(hass, entry.entry_id)
    live_delay = await delay_controller.async_initialize(configured_delay)
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
    weather_data_coordinator = None
    lap_count_coordinator = None
    race_control_coordinator = None
    top_three_coordinator = None
    hass.data[LATEST_TRACK_STATUS] = None
    # Create shared LiveBus (single SignalR connection). Live mode defers start to supervisor.
    session = async_get_clientsession(hass)
    live_bus = LiveBus(hass, session, transport_factory=transport_factory)
    live_supervisor: LiveSessionSupervisor | None = None
    live_state: LiveAvailabilityTracker
    if operation_mode == OPERATION_MODE_LIVE:
        live_supervisor = LiveSessionSupervisor(
            hass,
            session_coordinator,
            live_bus,
            http_session=session,
        )
        await live_supervisor.async_start()
        live_state = live_supervisor.availability
    else:
        await live_bus.start()
        live_state = LiveAvailabilityTracker()
        live_state.set_state(True, "replay-mode")

    def _reload_entry():
        hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))

    calibration_manager = LiveDelayCalibrationManager(
        hass,
        delay_controller,
        bus=live_bus,
        timeout_seconds=120,
        reload_callback=_reload_entry,
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

    await race_coordinator.async_config_entry_first_refresh()
    await driver_coordinator.async_config_entry_first_refresh()
    await constructor_coordinator.async_config_entry_first_refresh()
    await last_race_coordinator.async_config_entry_first_refresh()
    await season_results_coordinator.async_config_entry_first_refresh()
    await sprint_results_coordinator.async_config_entry_first_refresh()
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

    # Conditionally create live drivers coordinator only if any drivers-related sensors are enabled
    enabled = entry.data.get("enabled_sensors") or []
    # Only create drivers coordinator if driver_list is enabled (TEMP: race_order/driver_favorites disabled)
    need_drivers = any(k in enabled for k in ("driver_list",))
    need_top_three = any(k in enabled for k in ("top_three",))
    need_team_radio = any(k in enabled for k in ("team_radio",))
    need_pitstops = any(k in enabled for k in ("pitstops",))
    drivers_coordinator = None
    if need_drivers:
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

    # Conditionally create TopThree coordinator only if sensor is enabled
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
    if need_team_radio:
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
    if need_pitstops:
        pitstop_coordinator = PitStopCoordinator(
            hass,
            session_coordinator,
            live_delay,
            bus=live_bus,
            config_entry=entry,
            delay_controller=delay_controller,
            live_state=live_state,
            history_limit=10,
        )
        await pitstop_coordinator.async_config_entry_first_refresh()

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
        "race_control_coordinator": race_control_coordinator if enable_rc else None,
        "weather_data_coordinator": weather_data_coordinator if enable_rc else None,
        "lap_count_coordinator": lap_count_coordinator if enable_rc else None,
        "top_three_coordinator": top_three_coordinator,
        "team_radio_coordinator": team_radio_coordinator,
        "pitstop_coordinator": pitstop_coordinator,
        "drivers_coordinator": drivers_coordinator,
        "fia_documents_coordinator": fia_documents_coordinator,
        "live_bus": live_bus,
        "live_supervisor": live_supervisor,
        "live_state": live_state,
        "operation_mode": operation_mode,
        "replay_file": replay_source,
        "live_delay_controller": delay_controller,
        "calibration_manager": calibration_manager,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


class WeatherDataCoordinator(DataUpdateCoordinator):
    """Coordinator for WeatherData updates using SignalR, mirrors Track/Session behavior."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: 'LiveSessionCoordinator',
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
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._last_message = None
        self.data_list: list[dict] = []
        self._deliver_handle: Optional[asyncio.Handle] = None
        self._bus = bus
        self._unsub: Optional[Callable[[], None]] = None
        self._delay_listener: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))
        if delay_controller is not None:
            self._delay_listener = delay_controller.add_listener(self.set_delay)
        self._live_state_unsub: Optional[Callable[[], None]] = None
        if live_state is not None:
            self._live_state_unsub = live_state.add_listener(self._handle_live_state)

    async def async_close(self, *_):
        if self._unsub:
            try:
                self._unsub()
            except Exception:
                pass
            self._unsub = None
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None
        if self._delay_listener:
            try:
                self._delay_listener()
            except Exception:
                pass
            self._delay_listener = None
        if self._live_state_unsub:
            try:
                self._live_state_unsub()
            except Exception:
                pass
            self._live_state_unsub = None
        if self._delay_listener:
            try:
                self._delay_listener()
            except Exception:
                pass
            self._delay_listener = None

    async def _async_update_data(self):
        return self._last_message

    def _on_bus_message(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        # Skip duplicate snapshots without timestamp to avoid heartbeat churn
        if self._should_skip_duplicate(msg):
            return
        if self._delay > 0:
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_later(
                self._delay, lambda m=msg: self._deliver(m)
            )
        else:
            # Coalesce in same loop tick
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_soon(lambda m=msg: self._deliver(m))

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
            try:
                keys = [k for k in (msg or {}).keys()][:6]
                _LOGGER.debug(
                    "WeatherData delivered at %s keys=%s",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                    keys,
                )
            except Exception:
                pass

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        # Subscribe to shared live bus
        try:
            self._unsub = (self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")).subscribe("WeatherData", self._on_bus_message)  # type: ignore[attr-defined]
        except Exception:
            self._unsub = None

    def set_delay(self, seconds: int) -> None:
        new_delay = max(0, int(seconds or 0))
        if new_delay == self._delay:
            return
        self._delay = new_delay
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        self.available = is_live
        if not is_live:
            self._last_message = None
            self.data_list = []


class RaceControlCoordinator(DataUpdateCoordinator):
    """Coordinator for RaceControlMessages that publishes HA events for new items.

    - Mirrors logging/delay patterns from Track/Session coordinators
    - Publishes Home Assistant events only for new Race Control items (avoids replay on startup)
    """

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: 'LiveSessionCoordinator',
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
            try:
                self._unsub()
            except Exception:
                pass
            self._unsub = None
        if self._deliver_handles:
            for handle in list(self._deliver_handles):
                try:
                    handle.cancel()
                except Exception:
                    pass
            self._deliver_handles.clear()
        if self._delay_listener:
            try:
                self._delay_listener()
            except Exception:
                pass
            self._delay_listener = None
        if self._live_state_unsub:
            try:
                self._live_state_unsub()
            except Exception:
                pass
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
                except Exception:
                    # Fall through to wrapper-as-item if something unexpected happens
                    pass
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
            text = str(item.get("Message") or item.get("Text") or item.get("Flag") or "")
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
            try:
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
            except Exception:
                pass
            ident = self._message_id(item)
            if ident in self._seen_ids_set:
                continue
            # Evict if needed then add
            if len(self._seen_ids_order) == self._seen_ids_order.maxlen:
                try:
                    old = self._seen_ids_order.popleft()
                    self._seen_ids_set.discard(old)
                except Exception:
                    pass
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
                    try:
                        self._deliver_handles.remove(handle)
                    except ValueError:
                        pass
                    handle = None

        loop = self.hass.loop
        if self._delay > 0:
            handle = loop.call_later(self._delay, _callback)
        else:
            handle = loop.call_soon(_callback)
        self._deliver_handles.append(handle)

    def set_delay(self, seconds: int) -> None:
        new_delay = max(0, int(seconds or 0))
        if new_delay == self._delay:
            return
        self._delay = new_delay
        if self._deliver_handles:
            for handle in list(self._deliver_handles):
                try:
                    handle.cancel()
                except Exception:
                    pass
            self._deliver_handles.clear()

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        self.available = is_live

    def _deliver(self, item: dict) -> None:
        self.available = True
        # Maintain last message for visibility and parity with other coordinators
        self._last_message = item
        self.data_list = [item]
        self.async_set_updated_data(item)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            try:
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
            except Exception:
                pass
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
            self._unsub = (self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")).subscribe("RaceControlMessages", self._on_bus_message)  # type: ignore[attr-defined]
        except Exception:
            self._unsub = None

class LapCountCoordinator(DataUpdateCoordinator):
    """Coordinator for LapCount updates using SignalR, mirrors other live feeds."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: 'LiveSessionCoordinator',
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
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._last_message = None
        self.data_list: list[dict] = []
        self._deliver_handle: Optional[asyncio.Handle] = None
        self._bus = bus
        self._unsub: Optional[Callable[[], None]] = None
        self._delay_listener: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))
        if delay_controller is not None:
            self._delay_listener = delay_controller.add_listener(self.set_delay)
        self._live_state_unsub: Optional[Callable[[], None]] = None
        if live_state is not None:
            self._live_state_unsub = live_state.add_listener(self._handle_live_state)

    async def async_close(self, *_):
        if self._unsub:
            try:
                self._unsub()
            except Exception:
                pass
            self._unsub = None
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None
        if self._delay_listener:
            try:
                self._delay_listener()
            except Exception:
                pass
            self._delay_listener = None
        if self._live_state_unsub:
            try:
                self._live_state_unsub()
            except Exception:
                pass
            self._live_state_unsub = None

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
        if self._delay > 0:
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_later(
                self._delay, lambda m=msg: self._deliver(m)
            )
        else:
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_soon(lambda m=msg: self._deliver(m))

    def _deliver(self, msg: dict) -> None:
        self.available = True
        self._last_message = msg
        self.data_list = [msg]
        self.async_set_updated_data(msg)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            try:
                _LOGGER.debug(
                    "LapCount delivered at %s current=%s total=%s",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                    (msg or {}).get("CurrentLap") or (msg or {}).get("LapCount"),
                    (msg or {}).get("TotalLaps"),
                )
            except Exception:
                pass

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        try:
            self._unsub = (self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")).subscribe("LapCount", self._on_bus_message)  # type: ignore[attr-defined]
        except Exception:
            self._unsub = None

    def set_delay(self, seconds: int) -> None:
        new_delay = max(0, int(seconds or 0))
        if new_delay == self._delay:
            return
        self._delay = new_delay
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        self.available = is_live


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
        if self._unsub:
            try:
                self._unsub()
            except Exception:
                pass
            self._unsub = None
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None
        if self._delay_listener:
            try:
                self._delay_listener()
            except Exception:
                pass
            self._delay_listener = None
        if self._live_state_unsub:
            try:
                self._live_state_unsub()
            except Exception:
                pass
            self._live_state_unsub = None

    async def _async_update_data(self):
        return self._state

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        self.available = is_live
        if not is_live:
            self._state = {"latest": None, "history": []}

    def set_delay(self, seconds: int) -> None:
        new_delay = max(0, int(seconds or 0))
        if new_delay == self._delay:
            return
        self._delay = new_delay
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None

    def _on_bus_message(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        if self._delay > 0:
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_later(
                self._delay, lambda m=msg: self._deliver(m)
            )
        else:
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_soon(
                lambda m=msg: self._deliver(m)
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
                numeric_keys = [
                    k for k in captures.keys() if str(k).isdigit()
                ]
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
        try:
            if (
                self._dev_mode
                and self._replay_static_root
                and isinstance(msg, dict)
                and "_static_root" not in msg
            ):
                msg = dict(msg)
                msg["_static_root"] = self._replay_static_root
        except Exception:
            pass
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
            try:
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
            except Exception:
                pass

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        # Best-effort: derive static root from the replay file's URL header so sensors
        # can build full clip URLs during replay.
        if self._dev_mode and self._config_entry:
            try:
                from pathlib import Path as _Path

                replay_source = str(self._config_entry.data.get(CONF_REPLAY_FILE, "") or "").strip()
                if replay_source:
                    replay_path = _Path(replay_source).expanduser()

                    def _read_static_root() -> str | None:
                        try:
                            with replay_path.open("r", encoding="utf-8") as fh:
                                for raw in fh:
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
                                    # Only consider the header area at top
                                    return None
                        except Exception:
                            return None
                        return None

                    static_root = await self.hass.async_add_executor_job(_read_static_root)
                    if static_root:
                        self._replay_static_root = str(static_root)
            except Exception:
                pass
        try:
            self._unsub = (
                self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")
            ).subscribe("TeamRadio", self._on_bus_message)  # type: ignore[attr-defined]
        except Exception:
            self._unsub = None


class PitStopCoordinator(DataUpdateCoordinator):
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
        self._delay_listener: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))
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

        self._state: dict[str, Any] = {
            "total_stops": 0,
            "cars": {},
            "last_update": None,
        }

    async def async_close(self, *_):
        for u in list(self._unsubs):
            try:
                u()
            except Exception:
                pass
        self._unsubs.clear()
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None
        if self._delay_listener:
            try:
                self._delay_listener()
            except Exception:
                pass
            self._delay_listener = None
        if self._live_state_unsub:
            try:
                self._live_state_unsub()
            except Exception:
                pass
            self._live_state_unsub = None
        if self._session_unsub:
            try:
                self._session_unsub()
            except Exception:
                pass
            self._session_unsub = None

    async def _async_update_data(self):
        return self._state

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        self.available = is_live
        if not is_live:
            self._reset_store()

    def set_delay(self, seconds: int) -> None:
        new_delay = max(0, int(seconds or 0))
        if new_delay == self._delay:
            return
        self._delay = new_delay
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None

    def _reset_store(self) -> None:
        self._by_car = {}
        self._dedup = set()
        self._state = {"total_stops": 0, "cars": {}, "last_update": None}
        try:
            self.async_set_updated_data(self._state)
        except Exception:
            pass

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

    @staticmethod
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

    def _on_session_index_update(self) -> None:
        fp = self._compute_session_fingerprint(getattr(self._session_coord, "data", None))
        if fp is None:
            return
        if self._session_fingerprint is None:
            self._session_fingerprint = fp
            return
        if fp != self._session_fingerprint:
            self._session_fingerprint = fp
            self._reset_store()

    def _schedule_deliver(self) -> None:
        if self._delay > 0:
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_later(self._delay, self._deliver)
        else:
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_soon(self._deliver)

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
        }
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
        try:
            if not self._config_entry:
                return
            reg = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)
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
                # Do not overwrite non-null values from DriverList
                existing = self._driver_map.get(rn) if isinstance(self._driver_map, dict) else None
                if isinstance(existing, dict):
                    if existing.get("tla") or existing.get("name") or existing.get("team"):
                        continue
                self._driver_map[rn] = {"tla": code, "name": name, "team": team}
        except Exception:
            return

    def _on_bus_pitstopseries(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        self._ingest_pitstopseries(msg)
        self._schedule_deliver()

    def _deliver(self) -> None:
        self.available = True
        cars: dict[str, Any] = {}
        total = 0
        try:
            for rn, stops in sorted(
                self._by_car.items(),
                key=lambda kv: int(str(kv[0])) if str(kv[0]).isdigit() else str(kv[0]),
            ):
                lst = list(stops or [])
                ident = self._driver_map.get(str(rn), {}) if isinstance(self._driver_map, dict) else {}
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
            self._session_fingerprint = self._compute_session_fingerprint(
                getattr(self._session_coord, "data", None)
            )
            self._session_unsub = self._session_coord.async_add_listener(
                self._on_session_index_update
            )
        except Exception:
            self._session_unsub = None
        # Subscribe to shared live bus streams
        bus = self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")
        try:
            self._unsubs.append(bus.subscribe("DriverList", self._on_driverlist))  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            self._unsubs.append(
                bus.subscribe("PitStopSeries", self._on_bus_pitstopseries)  # type: ignore[attr-defined]
            )
        except Exception:
            pass

class LiveDriversCoordinator(DataUpdateCoordinator):
    """Coordinator aggregating DriverList, TimingData, TimingAppData, LapCount and SessionStatus.

    Exposes a consolidated structure suitable for sensors:
    data = {
      "drivers": {
         rn: {
            "identity": {"tla","name","team","team_color","racing_number"},
            "timing": {"position","gap_to_leader","interval","last_lap","best_lap","in_pit","retired","stopped","status_code"},
            "tyres": {"compound","stint_laps","new"},
            "laps": {"lap_current","lap_total"},
         },
      },
      "leader_rn": rn | None,
      "lap_current": int | None,
      "lap_total": int | None,
      "session_status": dict | None,
      "frozen": bool,
    }
    """

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: 'LiveSessionCoordinator',
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
        }
        self._live_state_unsub: Optional[Callable[[], None]] = None
        if live_state is not None:
            self._live_state_unsub = live_state.add_listener(self._handle_live_state)

    async def async_close(self, *_):
        for u in list(self._unsubs):
            try:
                u()
            except Exception:
                pass
        self._unsubs.clear()
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None
        if self._delay_listener:
            try:
                self._delay_listener()
            except Exception:
                pass
            self._delay_listener = None
        if self._live_state_unsub:
            try:
                self._live_state_unsub()
            except Exception:
                pass
            self._live_state_unsub = None

    async def _async_update_data(self):
        return self._state

    def _merge_driverlist(self, payload: dict) -> None:
        # payload: { rn: {Tla, FullName, TeamName, TeamColour, ...}, ... }
        drivers = self._state["drivers"]
        for rn, info in (payload or {}).items():
            if not isinstance(info, dict):
                continue
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
            ident = drivers.setdefault(rn, {})
            ident.setdefault("identity", {})
            ident.setdefault("timing", {})
            ident.setdefault("tyres", {})
            ident.setdefault("laps", {})
            ident["identity"].update(
                {
                    "racing_number": str(info.get("RacingNumber") or rn),
                    "tla": info.get("Tla"),
                    "name": info.get("FullName") or info.get("BroadcastName"),
                    "team": info.get("TeamName"),
                    "team_color": info.get("TeamColour"),
                    "first_name": info.get("FirstName"),
                    "last_name": info.get("LastName"),
                    "headshot_small": headshot_small,
                    "headshot_large": headshot_large,
                    "reference": info.get("Reference"),
                }
            )

    @staticmethod
    def _get_value(d: dict | None, *path, default: Any = None):
        cur: Any = d
        for p in path:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(p)
        return cur if cur is not None else default

    def _merge_timingdata(self, payload: dict) -> None:
        # payload: {"Lines": { rn: {...timing...} } }
        lines = (payload or {}).get("Lines", {})
        if not isinstance(lines, dict):
            return
        drivers = self._state["drivers"]
        # 1) Apply incremental updates to stored driver timing
        for rn, td in lines.items():
            if not isinstance(td, dict):
                continue
            entry = drivers.setdefault(rn, {})
            entry.setdefault("identity", {})
            entry.setdefault("timing", {})
            entry.setdefault("tyres", {})
            entry.setdefault("laps", {})
            timing = entry["timing"]
            # IMPORTANT: Only set fields that are present in this delta payload.
            if "Position" in td:
                pos_raw = td.get("Position")
                pos_str = str(pos_raw).strip() if pos_raw is not None else None
                timing["position"] = pos_str or None
            if "GapToLeader" in td:
                timing["gap_to_leader"] = td.get("GapToLeader")
            ival = self._get_value(td, "IntervalToPositionAhead", "Value")
            if ival is not None:
                timing["interval"] = ival
            last_lap = self._get_value(td, "LastLapTime", "Value")
            if last_lap is not None:
                timing["last_lap"] = last_lap
            best_lap = self._get_value(td, "BestLapTime", "Value")
            if best_lap is not None:
                timing["best_lap"] = best_lap
            if "InPit" in td:
                timing["in_pit"] = bool(td.get("InPit"))
            if "Retired" in td:
                timing["retired"] = bool(td.get("Retired"))
            if "Stopped" in td:
                timing["stopped"] = bool(td.get("Stopped"))
            if "Status" in td:
                timing["status_code"] = td.get("Status")
        # SessionPart (for Q1/Q2/Q3 detection)
        try:
            part = payload.get("SessionPart")
            if part is not None:
                self._state.setdefault("session", {})
                self._state["session"]["part"] = part
        except Exception:
            pass

    def set_delay(self, seconds: int) -> None:
        new_delay = max(0, int(seconds or 0))
        if new_delay == self._delay:
            return
        self._delay = new_delay
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        self.available = is_live
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
                pos_str = str((info.get("timing", {}) or {}).get("position") or "").strip()
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
            try:
                _LOGGER.debug("LiveDrivers: leader changed %s -> %s", prev, leader_rn)
            except Exception:
                pass
            self._state["leader_rn"] = leader_rn

    def _merge_timingapp(self, payload: dict) -> None:
        """Merge TimingAppData payloads.

        We now use the dedicated TyreStintSeries stream for tyre information, so this
        handler is only responsible for lap time fields from the embedded Stints.
        """
        # payload: {"Lines": { rn: {"Stints": { idx or list } } } }
        lines = (payload or {}).get("Lines", {})
        if not isinstance(lines, dict):
            return
        drivers = self._state["drivers"]
        for rn, app in lines.items():
            if not isinstance(app, dict):
                continue
            entry = drivers.setdefault(rn, {})
            entry.setdefault("timing", {})
            stints = app.get("Stints")
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
                    latest = stints.get("0") if isinstance(stints.get("0"), dict) else None
            if isinstance(latest, dict):
                # Lap times: map latest LapTime to timing.last_lap and update best_lap
                lap_time = latest.get("LapTime")
                if isinstance(lap_time, str) and lap_time:
                    timing = entry.setdefault("timing", {})
                    timing["last_lap"] = lap_time
                    prev_best = timing.get("best_lap")
                    try:
                        new_secs = self._parse_laptime_secs(lap_time)
                        prev_secs = self._parse_laptime_secs(prev_best) if isinstance(prev_best, str) else None
                        if new_secs is not None and (prev_secs is None or new_secs < prev_secs):
                            timing["best_lap"] = lap_time
                    except Exception:
                        # If parsing fails, at least keep last_lap updated
                        pass
        # Lap time changes sometimes coincide with leader changes
        self._recompute_leader_from_state()

    def _merge_tyre_stints(self, payload: dict) -> None:
        """Merge TyreStintSeries payloads into per-driver tyre state.

        Expected payload shape (from SignalR stream \"TyreStintSeries\"):
            {"Stints": { rn: { idx: {Compound, New, TotalLaps, ...}, ... }, ... }}
        """
        stints_root = (payload or {}).get("Stints", {})
        if not isinstance(stints_root, dict):
            return
        drivers = self._state["drivers"]
        for rn, stints in stints_root.items():
            if not isinstance(stints, (dict, list)):
                continue
            entry = drivers.setdefault(rn, {})
            entry.setdefault("tyres", {})
            tyres = entry["tyres"]
            latest: dict | None = None
            if isinstance(stints, list) and stints:
                latest = stints[-1] if isinstance(stints[-1], dict) else None
            elif isinstance(stints, dict) and stints:
                try:
                    keys = [int(k) for k in stints.keys() if str(k).isdigit()]
                    if keys:
                        latest = stints.get(str(max(keys)))
                except Exception:
                    latest = stints.get("0") if isinstance(stints.get("0"), dict) else None
            if not isinstance(latest, dict):
                continue

            # Only overwrite fields that are present in this delta to avoid losing
            # previously-known compound/new values when we receive TotalLaps-only frames.
            if "Compound" in latest:
                tyres["compound"] = latest.get("Compound")
            if "TotalLaps" in latest:
                stint_laps = latest.get("TotalLaps")
                tyres["stint_laps"] = (
                    int(stint_laps) if str(stint_laps or "").isdigit() else stint_laps
                )
            if "New" in latest:
                is_new = latest.get("New")
                s = str(is_new).lower()
                if s == "true":
                    tyres["new"] = True
                elif s == "false":
                    tyres["new"] = False
                else:
                    tyres["new"] = is_new

        # Tyre changes can also interact with leader logic (pit stops etc.)
        self._recompute_leader_from_state()

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

    def _merge_sessionstatus(self, payload: dict) -> None:
        self._state["session_status"] = payload
        try:
            msg = str(payload.get("Status") or payload.get("Message") or "").strip()
            started_flag = payload.get("Started")
            # Freeze at session end
            if msg in ("Finished", "Finalised", "Ends"):
                self._state["frozen"] = True
            # Unfreeze on new session start or green running
            elif started_flag is True or msg in ("Started", "Green", "GreenFlag"):
                self._state["frozen"] = False
        except Exception:
            pass

    def set_delay(self, seconds: int) -> None:
        new_delay = max(0, int(seconds or 0))
        if new_delay == self._delay:
            return
        self._delay = new_delay
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None

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
        if self._delay > 0:
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_later(self._delay, self._deliver)
        else:
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_soon(self._deliver)

    def _on_driverlist(self, dl: dict) -> None:
        # Allow DriverList merges even when frozen so identity mapping remains available
        self._merge_driverlist(dl)
        self._schedule_deliver()

    def _on_timingdata(self, td: dict) -> None:
        if self._state.get("frozen"):
            return
        self._merge_timingdata(td)
        self._schedule_deliver()

    def _on_timingapp(self, ta: dict) -> None:
        if self._state.get("frozen"):
            return
        self._merge_timingapp(ta)
        self._schedule_deliver()

    def _on_tyre_stints(self, ts: dict) -> None:
        if self._state.get("frozen"):
            return
        self._merge_tyre_stints(ts)
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

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        # Subscribe to LiveBus streams
        try:
            bus = (self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus"))  # type: ignore[assignment]
        except Exception:
            bus = None
        if bus is not None:
            try:
                self._unsubs.append(bus.subscribe("DriverList", self._on_driverlist))
            except Exception:
                pass
            try:
                self._unsubs.append(bus.subscribe("TimingData", self._on_timingdata))
            except Exception:
                pass
            try:
                self._unsubs.append(bus.subscribe("TimingAppData", self._on_timingapp))
            except Exception:
                pass
            try:
                self._unsubs.append(bus.subscribe("TyreStintSeries", self._on_tyre_stints))
            except Exception:
                pass
            try:
                self._unsubs.append(bus.subscribe("LapCount", self._on_lapcount))
            except Exception:
                pass
            try:
                self._unsubs.append(bus.subscribe("SessionStatus", self._on_sessionstatus))
            except Exception:
                pass

    def set_delay(self, seconds: int) -> None:
        new_delay = max(0, int(seconds or 0))
        if new_delay == self._delay:
            return
        self._delay = new_delay
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None


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
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Error during entry data cleanup: %s", err)
    return unload_ok


    


class F1DataCoordinator(DataUpdateCoordinator):
    """Handles updates from a given F1 endpoint."""

    def __init__(self, hass: HomeAssistant, url: str, name: str, session=None, cache=None, inflight=None, ttl_seconds: int = 30, persist_map=None, persist_save=None, config_entry: ConfigEntry | None = None):
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(hours=1),
            config_entry=config_entry,
        )
        self._session = session or async_get_clientsession(hass)
        self._url = url
        self._cache = cache
        self._inflight = inflight
        self._ttl = int(ttl_seconds or 30)
        self._persist = persist_map
        self._persist_save = persist_save

    async def async_close(self, *_):
        """Placeholder for future cleanup."""
        return

    async def _async_update_data(self):
        """Fetch data from the F1 API."""
        try:
            async with async_timeout.timeout(10):
                return await fetch_json(
                    self.hass,
                    self._session,
                    self._url,
                    ttl_seconds=self._ttl,
                    cache=self._cache,
                    inflight=self._inflight,
                    persist_map=self._persist,
                    persist_save=self._persist_save,
                )
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err


class F1SeasonResultsCoordinator(DataUpdateCoordinator):
    """Fetch all season results across paginated Ergast responses."""

    def __init__(self, hass: HomeAssistant, url: str, name: str, session=None, cache=None, inflight=None, ttl_seconds: int = 60, persist_map=None, persist_save=None, config_entry: ConfigEntry | None = None):
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(hours=1),
            config_entry=config_entry,
        )
        self._session = session or async_get_clientsession(hass)
        self._base_url = url
        self._cache = cache
        self._inflight = inflight
        self._ttl = int(ttl_seconds or 60)
        self._persist = persist_map
        self._persist_save = persist_save

    async def async_close(self, *_):
        return

    async def _fetch_page(self, limit: int, offset: int):
        from yarl import URL
        url = str(URL(self._base_url).with_query({"limit": str(limit), "offset": str(offset)}))
        async with async_timeout.timeout(10):
            return await fetch_json(
                self.hass,
                self._session,
                url,
                ttl_seconds=self._ttl,
                cache=self._cache,
                inflight=self._inflight,
                persist_map=self._persist,
                persist_save=self._persist_save,
            )

    @staticmethod
    def _race_key(r: dict) -> tuple:
        season = r.get("season")
        round_ = r.get("round")
        return (str(season) if season is not None else "", str(round_) if round_ is not None else "")

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
                            ident = (res.get("Driver", {}).get("driverId"), res.get("position"))
                            if ident not in seen:
                                existing["Results"].append(res)
                                seen.add(ident)

            # Fetch first page
            first = await self._fetch_page(request_limit, offset)
            mr = (first or {}).get("MRData", {})
            total = int((mr.get("total") or "0"))
            limit_used = int((mr.get("limit") or request_limit))
            offset_used = int((mr.get("offset") or offset))

            merge_page(((mr.get("RaceTable", {}) or {}).get("Races", []) or []))

            # Iterate deterministically using server-reported paging
            next_offset = offset_used + limit_used
            # Cap loop iterations defensively
            safety = 0
            while next_offset < total and safety < 50:
                page = await self._fetch_page(limit_used, next_offset)
                pmr = (page or {}).get("MRData", {})
                praces = (pmr.get("RaceTable", {}) or {}).get("Races", []) or []
                merge_page(praces)
                try:
                    limit_used = int(pmr.get("limit") or limit_used)
                    offset_used = int(pmr.get("offset") or next_offset)
                    total = int(pmr.get("total") or total)
                except Exception:
                    pass
                next_offset = offset_used + limit_used
                safety += 1

            # Assemble and sort by season then numeric round
            assembled_races = [races_by_key[k] for k in order]
            assembled_races.sort(key=lambda r: (str(r.get("season")), int(str(r.get("round") or 0))))
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

    def __init__(self, hass: HomeAssistant, url: str, name: str, session=None, cache=None, inflight=None, ttl_seconds: int = 60, persist_map=None, persist_save=None, config_entry: ConfigEntry | None = None):
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(hours=1),
            config_entry=config_entry,
        )
        self._session = session or async_get_clientsession(hass)
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
            update_interval=timedelta(seconds=max(60, int(ttl_seconds or FIA_DOCS_POLL_INTERVAL))),
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
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Failed to resolve FIA season slug for %s: %s", season, err)
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
        pattern = re.compile(
            rf'href="(?P<href>/documents[^"]*season/season-{re.escape(str(season))}-\d+)"',
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
        now = datetime.utcnow().replace(tzinfo=None)
        for race in races:
            date = race.get("date")
            time_str = race.get("time") or "00:00:00Z"
            dt_str = f"{date}T{time_str}".replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(dt_str)
            except Exception:
                continue
            # Treat a race as ongoing for a grace period after the scheduled
            # start time so that "next race" style helpers don't jump ahead
            # too early.
            end_dt = dt + RACE_SWITCH_GRACE
            if end_dt.replace(tzinfo=None) > now:
                return race
        return races[-1] if races else None
class LiveSessionCoordinator(DataUpdateCoordinator):
    """Fetch current or next session from the LiveTiming index."""

    def __init__(self, hass: HomeAssistant, year: int, session=None, config_entry: ConfigEntry | None = None):
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

    async def async_close(self, *_):
        return

    async def _async_update_data(self):
        payload = await self._fetch_index()
        if payload:
            self._last_good_index = payload
            return payload
        if self._last_good_index:
            _LOGGER.warning("Using cached LiveTiming index (server returned empty response)")
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
                    if response.status != 200:
                        _LOGGER.warning("Index fetch failed (%s): %s", response.status, text[:200])
                        return None
                    payload = json.loads(text.lstrip("\ufeff") or "null")
        except Exception as err:
            _LOGGER.warning("Error fetching index (%s): %s", "cache-bust" if cache_bust else "standard", err)
            return None
        if self._has_sessions(payload):
            return payload
        if not cache_bust:
            _LOGGER.debug("Index response missing sessions; retrying with cache-buster")
            return await self._fetch_index(cache_bust=True)
        _LOGGER.warning("Index response still missing sessions after cache-bust")
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
        if delay_controller is not None:
            self._delay_listener = delay_controller.add_listener(self.set_delay)
        # Lightweight dedupe of untimestamped repeats
        self._last_untimestamped_fingerprint: str | None = None
        self._live_state_unsub: Optional[Callable[[], None]] = None
        if live_state is not None:
            self._live_state_unsub = live_state.add_listener(self._handle_live_state)

    async def async_close(self, *_):
        if self._unsub:
            try:
                self._unsub()
            except Exception:
                pass
            self._unsub = None
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None
        # Cancel any queued delayed deliveries
        try:
            for h in list(self._deliver_handles):
                try:
                    h.cancel()
                except Exception:
                    pass
            self._deliver_handles.clear()
        except Exception:
            pass
        if self._delay_listener:
            try:
                self._delay_listener()
            except Exception:
                pass
            self._delay_listener = None
        if self._live_state_unsub:
            try:
                self._live_state_unsub()
            except Exception:
                pass
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
        try:
            if utc_str:
                ts = datetime.fromisoformat(str(utc_str).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    from datetime import timezone as _tz
                    ts = ts.replace(tzinfo=_tz.utc)
                if self._startup_cutoff and ts < self._startup_cutoff:
                    return
        except Exception:
            pass
        # Dedupe untimestamped exact repeats to avoid flooding when delayed
        try:
            has_ts = any(k in msg for k in ("Utc", "utc", "processedAt", "timestamp"))
        except Exception:
            has_ts = False
        if not has_ts:
            try:
                fp = json.dumps({
                    "Status": msg.get("Status"),
                    "Message": msg.get("Message") or msg.get("TrackStatus")
                }, sort_keys=True, default=str)
                if self._last_untimestamped_fingerprint == fp:
                    return
                self._last_untimestamped_fingerprint = fp
            except Exception:
                pass

        if self._delay > 0:
            # Queue each delivery independently so intermediate states (e.g. YELLOW) survive
            try:
                handle = self.hass.loop.call_later(self._delay, lambda m=msg: self._deliver(m))
                self._deliver_handles.append(handle)
            except Exception:
                # Fallback to immediate delivery
                try:
                    self._deliver(msg)
                except Exception:
                    pass
        else:
            # Immediate delivery; keep legacy single-handle for symmetry
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_soon(lambda m=msg: self._deliver(m))

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
        try:
            self.hass.data[LATEST_TRACK_STATUS] = msg
        except Exception:
            pass
        if _LOGGER.isEnabledFor(logging.DEBUG):
            try:
                _LOGGER.debug(
                    "TrackStatus delivered at %s status=%s message=%s",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                    (msg or {}).get("Status"),
                    (msg or {}).get("Message"),
                )
            except Exception:
                pass

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
            self._unsub = (self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")).subscribe("TrackStatus", self._on_bus_message)  # type: ignore[attr-defined]
        except Exception:
            self._unsub = None

    def set_delay(self, seconds: int) -> None:
        new_delay = max(0, int(seconds or 0))
        if new_delay == self._delay:
            return
        self._delay = new_delay
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None
        if self._deliver_handles:
            for handle in list(self._deliver_handles):
                try:
                    handle.cancel()
                except Exception:
                    pass
            self._deliver_handles.clear()

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        self.available = is_live


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
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._last_message = None
        self.data_list: list[dict] = []
        self._deliver_handle: Optional[asyncio.Handle] = None
        self._bus = bus
        self._unsub: Optional[Callable[[], None]] = None
        self._delay_listener: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))
        if delay_controller is not None:
            self._delay_listener = delay_controller.add_listener(self.set_delay)
        self._live_state_unsub: Optional[Callable[[], None]] = None
        if live_state is not None:
            self._live_state_unsub = live_state.add_listener(self._handle_live_state)

    async def async_close(self, *_):
        if self._unsub:
            try:
                self._unsub()
            except Exception:
                pass
            self._unsub = None
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None
        if self._delay_listener:
            try:
                self._delay_listener()
            except Exception:
                pass
            self._delay_listener = None
        if self._live_state_unsub:
            try:
                self._live_state_unsub()
            except Exception:
                pass
            self._live_state_unsub = None

    async def _async_update_data(self):
        return self._last_message

    def _on_bus_message(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        if self._delay > 0:
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_later(
                self._delay, lambda m=msg: self._deliver(m)
            )
        else:
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_soon(lambda m=msg: self._deliver(m))

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
            try:
                _LOGGER.debug(
                    "SessionStatus delivered at %s status=%s started=%s",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                    (msg or {}).get("Status"),
                    (msg or {}).get("Started"),
                )
            except Exception:
                pass

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        try:
            self._unsub = (self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")).subscribe("SessionStatus", self._on_bus_message)  # type: ignore[attr-defined]
        except Exception:
            self._unsub = None

    def set_delay(self, seconds: int) -> None:
        new_delay = max(0, int(seconds or 0))
        if new_delay == self._delay:
            return
        self._delay = new_delay
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        self.available = is_live


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
        self._deliver_handle: Optional[asyncio.Handle] = None
        self._bus = bus
        self._unsub: Optional[Callable[[], None]] = None
        self._delay_listener: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))
        if delay_controller is not None:
            self._delay_listener = delay_controller.add_listener(self.set_delay)
        self._live_state_unsub: Optional[Callable[[], None]] = None
        if live_state is not None:
            self._live_state_unsub = live_state.add_listener(self._handle_live_state)

    async def async_close(self, *_):
        if self._unsub:
            try:
                self._unsub()
            except Exception:
                pass
            self._unsub = None
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None
        if self._delay_listener:
            try:
                self._delay_listener()
            except Exception:
                pass
            self._delay_listener = None
        if self._live_state_unsub:
            try:
                self._live_state_unsub()
            except Exception:
                pass
            self._live_state_unsub = None

    async def _async_update_data(self):
        return self._state

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        self.available = is_live

    def set_delay(self, seconds: int) -> None:
        new_delay = max(0, int(seconds or 0))
        if new_delay == self._delay:
            return
        self._delay = new_delay
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None

    def _schedule_deliver(self) -> None:
        if self._delay > 0:
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_later(
                self._delay, self._deliver
            )
        else:
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_soon(self._deliver)

    def _merge_topthree(self, payload: dict) -> None:
        """Merge a TopThree payload (full snapshot or partial delta) into state."""
        if not isinstance(payload, dict):
            return

        state = self._state

        # Withheld flag (om F1 väljer att inte visa topp 3)
        try:
            if "Withheld" in payload:
                state["withheld"] = bool(payload.get("Withheld"))
        except Exception:
            pass

        lines = payload.get("Lines")
        cur_lines = state.get("lines") or [None, None, None]

        # Full snapshot: Lines som lista [P1, P2, P3]
        if isinstance(lines, list):
            new_lines: list[Any] = [None, None, None]
            for idx in range(3):
                try:
                    item = lines[idx]
                except Exception:
                    item = None
                new_lines[idx] = item if isinstance(item, dict) else None
            state["lines"] = new_lines
        # Delta: Lines som dict { "0": {...}, "1": {...}, "2": {...} }
        elif isinstance(lines, dict):
            for key, delta in lines.items():
                try:
                    idx = int(key)
                except Exception:
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
                except Exception:
                    # Sista försvarslinje – hellre lämna base opåverkad än krascha
                    pass
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
            return
        self._schedule_deliver()

    def _deliver(self) -> None:
        # Pushar aktuellt state till sensorerna
        self.async_set_updated_data(self._state)

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        # Prenumerera på TopThree från LiveBus
        try:
            bus = (self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus"))  # type: ignore[assignment]
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
        self._deliver_handle: Optional[asyncio.Handle] = None
        self._bus = bus
        self._unsub: Optional[Callable[[], None]] = None
        self._delay_listener: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))
        if delay_controller is not None:
            self._delay_listener = delay_controller.add_listener(self.set_delay)
        self._live_state_unsub: Optional[Callable[[], None]] = None
        if live_state is not None:
            self._live_state_unsub = live_state.add_listener(self._handle_live_state)

    async def async_close(self, *_):
        if self._unsub:
            try:
                self._unsub()
            except Exception:
                pass
            self._unsub = None
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None
        if self._delay_listener:
            try:
                self._delay_listener()
            except Exception:
                pass
            self._delay_listener = None
        if self._live_state_unsub:
            try:
                self._live_state_unsub()
            except Exception:
                pass
            self._live_state_unsub = None

    async def _async_update_data(self):
        return self._last_message

    def _on_bus_message(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        if self._delay > 0:
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_later(
                self._delay, lambda m=msg: self._deliver(m)
            )
        else:
            try:
                if self._deliver_handle:
                    self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = self.hass.loop.call_soon(lambda m=msg: self._deliver(m))

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
            try:
                name = (msg or {}).get("Name")
                t = (msg or {}).get("Type")
                _LOGGER.debug(
                    "SessionInfo delivered at %s type=%s name=%s",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                    t,
                    name,
                )
            except Exception:
                pass

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        try:
            self._unsub = (self._bus or self.hass.data.get(DOMAIN, {}).get("live_bus")).subscribe("SessionInfo", self._on_bus_message)  # type: ignore[attr-defined]
        except Exception:
            self._unsub = None

    def set_delay(self, seconds: int) -> None:
        new_delay = max(0, int(seconds or 0))
        if new_delay == self._delay:
            return
        self._delay = new_delay
        if self._deliver_handle:
            try:
                self._deliver_handle.cancel()
            except Exception:
                pass
            self._deliver_handle = None

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        self.available = is_live
