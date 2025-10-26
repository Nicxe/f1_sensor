import json
import logging
import asyncio
import contextlib
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from collections import deque

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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
)
from .signalr import LiveBus

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration via config flow."""
    race_coordinator = F1DataCoordinator(hass, API_URL, "F1 Race Data Coordinator")
    driver_coordinator = F1DataCoordinator(
        hass, DRIVER_STANDINGS_URL, "F1 Driver Standings Coordinator"
    )
    constructor_coordinator = F1DataCoordinator(
        hass, CONSTRUCTOR_STANDINGS_URL, "F1 Constructor Standings Coordinator"
    )
    last_race_coordinator = F1DataCoordinator(
        hass, LAST_RACE_RESULTS_URL, "F1 Last Race Results Coordinator"
    )
    season_results_coordinator = F1SeasonResultsCoordinator(
        hass, SEASON_RESULTS_URL, "F1 Season Results Coordinator"
    )
    sprint_results_coordinator = F1SprintResultsCoordinator(
        hass, SPRINT_RESULTS_URL, "F1 Sprint Results Coordinator"
    )
    year = datetime.utcnow().year
    session_coordinator = LiveSessionCoordinator(hass, year)
    enable_rc = entry.data.get("enable_race_control", False)
    live_delay = int(entry.data.get("live_delay_seconds", 0) or 0)
    track_status_coordinator = None
    session_status_coordinator = None
    session_info_coordinator = None
    weather_data_coordinator = None
    lap_count_coordinator = None
    race_control_coordinator = None
    hass.data[LATEST_TRACK_STATUS] = None
    # Create and start a shared LiveBus (single SignalR connection)
    session = async_get_clientsession(hass)
    live_bus = LiveBus(hass, session)
    await live_bus.start()

    if enable_rc:
        track_status_coordinator = TrackStatusCoordinator(
            hass, session_coordinator, live_delay, bus=live_bus
        )
        session_status_coordinator = SessionStatusCoordinator(
            hass, session_coordinator, live_delay, bus=live_bus
        )
        session_info_coordinator = SessionInfoCoordinator(
            hass, session_coordinator, live_delay, bus=live_bus
        )
        race_control_coordinator = RaceControlCoordinator(
            hass, session_coordinator, live_delay, bus=live_bus
        )
        weather_data_coordinator = WeatherDataCoordinator(
            hass, session_coordinator, live_delay, bus=live_bus
        )
        lap_count_coordinator = LapCountCoordinator(
            hass, session_coordinator, live_delay, bus=live_bus
        )

    await race_coordinator.async_config_entry_first_refresh()
    await driver_coordinator.async_config_entry_first_refresh()
    await constructor_coordinator.async_config_entry_first_refresh()
    await last_race_coordinator.async_config_entry_first_refresh()
    await season_results_coordinator.async_config_entry_first_refresh()
    await sprint_results_coordinator.async_config_entry_first_refresh()
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
    drivers_coordinator = None
    if need_drivers:
        drivers_coordinator = LiveDriversCoordinator(
            hass,
            session_coordinator,
            delay_seconds=int(entry.data.get("live_delay_seconds", 0) or 0),
            bus=live_bus,
        )
        await drivers_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
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
        "drivers_coordinator": drivers_coordinator,
        "live_bus": live_bus,
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
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="F1 Weather Data Coordinator",
            update_interval=None,
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._last_message = None
        self.data_list: list[dict] = []
        self._deliver_handle: Optional[asyncio.Handle] = None
        self._bus = bus
        self._unsub: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))

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
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="F1 Race Control Coordinator",
            update_interval=None,
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._last_message = None
        self.data_list: list[dict] = []
        self._deliver_handle: Optional[asyncio.Handle] = None
        self._bus = bus
        self._unsub: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))
        # For duplicate filtering and startup replay suppression
        self._seen_ids_set: set[str] = set()
        self._seen_ids_order = deque(maxlen=1024)
        self._startup_cutoff: datetime | None = None

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
            if isinstance(msg.get("Messages"), list):
                return [m for m in msg.get("Messages") if isinstance(m, dict)]
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
            if self._delay > 0:
                try:
                    if self._deliver_handle:
                        self._deliver_handle.cancel()
                except Exception:
                    pass
                self._deliver_handle = self.hass.loop.call_later(
                    self._delay, lambda m=item: self._deliver(m)
                )
            else:
                try:
                    if self._deliver_handle:
                        self._deliver_handle.cancel()
                except Exception:
                    pass
                self._deliver_handle = self.hass.loop.call_soon(lambda m=item: self._deliver(m))

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
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="F1 Lap Count Coordinator",
            update_interval=None,
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._last_message = None
        self.data_list: list[dict] = []
        self._deliver_handle: Optional[asyncio.Handle] = None
        self._bus = bus
        self._unsub: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))

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
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="F1 Live Drivers Coordinator",
            update_interval=None,
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self._deliver_handle: Optional[asyncio.Handle] = None
        self._bus = bus
        self._unsubs: list[Callable[[], None]] = []
        self._delay = max(0, int(delay_seconds or 0))
        self._state: dict[str, Any] = {
            "drivers": {},
            "leader_rn": None,
            "lap_current": None,
            "lap_total": None,
            "session_status": None,
            "frozen": False,
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
        # payload: {"Lines": { rn: {"Stints": { idx or list } } } }
        lines = (payload or {}).get("Lines", {})
        if not isinstance(lines, dict):
            return
        drivers = self._state["drivers"]
        for rn, app in lines.items():
            if not isinstance(app, dict):
                continue
            entry = drivers.setdefault(rn, {})
            entry.setdefault("tyres", {})
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
                # Tyres info
                comp = latest.get("Compound")
                stint_laps = latest.get("TotalLaps")
                is_new = latest.get("New")
                entry["tyres"].update(
                    {
                        "compound": comp,
                        "stint_laps": int(stint_laps) if str(stint_laps or "").isdigit() else stint_laps,
                        "new": True if str(is_new).lower() == "true" else (False if str(is_new).lower() == "false" else is_new),
                    }
                )
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
        # Tyre or lap time changes sometimes coincide with leader changes
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
                self._unsubs.append(bus.subscribe("LapCount", self._on_lapcount))
            except Exception:
                pass
            try:
                self._unsubs.append(bus.subscribe("SessionStatus", self._on_sessionstatus))
            except Exception:
                pass


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

    def __init__(self, hass: HomeAssistant, url: str, name: str):
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(hours=1),
        )
        self._session = async_get_clientsession(hass)
        self._url = url

    async def async_close(self, *_):
        """Placeholder for future cleanup."""
        return

    async def _async_update_data(self):
        """Fetch data from the F1 API."""
        try:
            async with async_timeout.timeout(10):
                async with self._session.get(self._url) as response:
                    if response.status != 200:
                        raise UpdateFailed(f"Error fetching data: {response.status}")
                    text = await response.text()
                    return json.loads(text.lstrip("\ufeff"))
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err


class F1SeasonResultsCoordinator(DataUpdateCoordinator):
    """Fetch all season results across paginated Ergast responses."""

    def __init__(self, hass: HomeAssistant, url: str, name: str):
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(hours=1),
        )
        self._session = async_get_clientsession(hass)
        self._base_url = url

    async def async_close(self, *_):
        return

    async def _fetch_page(self, limit: int, offset: int):
        from yarl import URL

        url = str(URL(self._base_url).with_query({"limit": str(limit), "offset": str(offset)}))
        async with async_timeout.timeout(10):
            async with self._session.get(url) as response:
                if response.status != 200:
                    raise UpdateFailed(f"Error fetching data: {response.status}")
                text = await response.text()
                return json.loads(text.lstrip("\ufeff"))

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

    def __init__(self, hass: HomeAssistant, url: str, name: str):
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(hours=1),
        )
        self._session = async_get_clientsession(hass)
        self._url = url

    async def async_close(self, *_):
        return

    async def _async_update_data(self):
        try:
            async with async_timeout.timeout(10):
                async with self._session.get(self._url) as response:
                    if response.status != 200:
                        raise UpdateFailed(f"Error fetching data: {response.status}")
                    text = await response.text()
                    return json.loads(text.lstrip("\ufeff"))
        except Exception as err:
            raise UpdateFailed(f"Error fetching sprint results: {err}") from err

class LiveSessionCoordinator(DataUpdateCoordinator):
    """Fetch current or next session from the LiveTiming index."""

    def __init__(self, hass: HomeAssistant, year: int):
        super().__init__(
            hass,
            _LOGGER,
            name="F1 Live Session Coordinator",
            update_interval=timedelta(hours=1),
        )
        self._session = async_get_clientsession(hass)
        self.year = year

    async def async_close(self, *_):
        return

    async def _async_update_data(self):
        url = LIVETIMING_INDEX_URL.format(year=self.year)
        try:
            async with async_timeout.timeout(10):
                async with self._session.get(url) as response:
                    if response.status in (403, 404):
                        _LOGGER.warning("Index unavailable: %s", response.status)
                        return self.data
                    if response.status != 200:
                        raise UpdateFailed(f"Error fetching data: {response.status}")
                    text = await response.text()
                    return json.loads(text.lstrip("\ufeff"))
        except Exception as err:
            _LOGGER.warning("Error fetching index: %s", err)
            return self.data



class TrackStatusCoordinator(DataUpdateCoordinator):
    """Coordinator for TrackStatus updates using SignalR."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: LiveSessionCoordinator,
        delay_seconds: int = 0,
        bus: LiveBus | None = None,
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="F1 Track Status Coordinator",
            update_interval=None,
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
        self._t0 = None
        self._startup_cutoff = None
        self._delay = max(0, int(delay_seconds or 0))
        # Lightweight dedupe of untimestamped repeats
        self._last_untimestamped_fingerprint: str | None = None

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


class SessionStatusCoordinator(DataUpdateCoordinator):
    """Coordinator for SessionStatus updates using SignalR."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: LiveSessionCoordinator,
        delay_seconds: int = 0,
        bus: LiveBus | None = None,
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="F1 Session Status Coordinator",
            update_interval=None,
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._last_message = None
        self.data_list: list[dict] = []
        self._deliver_handle: Optional[asyncio.Handle] = None
        self._bus = bus
        self._unsub: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))

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


class SessionInfoCoordinator(DataUpdateCoordinator):
    """Coordinator for SessionInfo updates using SignalR."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: LiveSessionCoordinator,
        delay_seconds: int = 0,
        bus: LiveBus | None = None,
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="F1 Session Info Coordinator",
            update_interval=None,
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self.available = True
        self._last_message = None
        self.data_list: list[dict] = []
        self._deliver_handle: Optional[asyncio.Handle] = None
        self._bus = bus
        self._unsub: Optional[Callable[[], None]] = None
        self._delay = max(0, int(delay_seconds or 0))

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
