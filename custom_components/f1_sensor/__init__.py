import json
import logging
import asyncio
import contextlib
from datetime import datetime, timedelta

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
    LATEST_TRACK_STATUS,
)

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
    year = datetime.utcnow().year
    session_coordinator = LiveSessionCoordinator(hass, year)
    enable_rc = entry.data.get("enable_race_control", False)
    live_delay = int(entry.data.get("live_delay_seconds", 0) or 0)
    track_status_coordinator = None
    session_status_coordinator = None
    weather_data_coordinator = None
    lap_count_coordinator = None
    race_control_coordinator = None
    hass.data[LATEST_TRACK_STATUS] = None
    if enable_rc:
        track_status_coordinator = TrackStatusCoordinator(
            hass, session_coordinator, live_delay
        )
        session_status_coordinator = SessionStatusCoordinator(
            hass, session_coordinator, live_delay
        )
        race_control_coordinator = RaceControlCoordinator(
            hass, session_coordinator, live_delay
        )
        weather_data_coordinator = WeatherDataCoordinator(
            hass, session_coordinator, live_delay
        )
        lap_count_coordinator = LapCountCoordinator(
            hass, session_coordinator, live_delay
        )

    await race_coordinator.async_config_entry_first_refresh()
    await driver_coordinator.async_config_entry_first_refresh()
    await constructor_coordinator.async_config_entry_first_refresh()
    await last_race_coordinator.async_config_entry_first_refresh()
    await season_results_coordinator.async_config_entry_first_refresh()
    await session_coordinator.async_config_entry_first_refresh()
    if track_status_coordinator:
        await track_status_coordinator.async_config_entry_first_refresh()
    if session_status_coordinator:
        await session_status_coordinator.async_config_entry_first_refresh()
    if race_control_coordinator:
        await race_control_coordinator.async_config_entry_first_refresh()
    if weather_data_coordinator:
        await weather_data_coordinator.async_config_entry_first_refresh()
    if lap_count_coordinator:
        await lap_count_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "race_coordinator": race_coordinator,
        "driver_coordinator": driver_coordinator,
        "constructor_coordinator": constructor_coordinator,
        "last_race_coordinator": last_race_coordinator,
        "season_results_coordinator": season_results_coordinator,
        "session_coordinator": session_coordinator,
        "track_status_coordinator": track_status_coordinator,
        "session_status_coordinator": session_status_coordinator,
        "race_control_coordinator": race_control_coordinator if enable_rc else None,
        "weather_data_coordinator": weather_data_coordinator if enable_rc else None,
        "lap_count_coordinator": lap_count_coordinator if enable_rc else None,
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
        self._task = None
        self._client = None
        self._delay = max(0, int(delay_seconds or 0))

    async def async_close(self, *_):
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._client:
            await self._client.close()

    async def _async_update_data(self):
        return self._last_message

    async def _listen(self):
        from .signalr import SignalRClient

        self._client = SignalRClient(self.hass, self._session)
        while True:
            try:
                await self._client._ensure_connection()
                async for payload in self._client.messages():
                    msg = self._parse_message(payload)
                    if msg:
                        # Skip duplicate snapshots without timestamp to avoid heartbeat churn
                        if self._should_skip_duplicate(msg):
                            try:
                                _LOGGER.debug(
                                    "WeatherData duplicate without timestamp ignored at %s: %s",
                                    dt_util.utcnow().isoformat(timespec="seconds"),
                                    msg,
                                )
                            except Exception:
                                pass
                            continue
                        try:
                            _LOGGER.debug(
                                "WeatherData received at %s, delay=%ss, message=%s",
                                dt_util.utcnow().isoformat(timespec="seconds"),
                                self._delay,
                                msg,
                            )
                        except Exception:
                            pass
                        if self._delay > 0:
                            try:
                                scheduled = (dt_util.utcnow() + timedelta(seconds=self._delay)).isoformat(timespec="seconds")
                                _LOGGER.debug(
                                    "WeatherData scheduled delivery at %s (+%ss)",
                                    scheduled,
                                    self._delay,
                                )
                            except Exception:
                                pass
                            self.hass.loop.call_later(
                                self._delay,
                                lambda m=msg: self._deliver(m),
                            )
                        else:
                            self._deliver(msg)
            except Exception as err:  # pragma: no cover - network errors
                self.available = False
                _LOGGER.warning("Weather data websocket error: %s", err)
            finally:
                if self._client:
                    await self._client.close()

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
        try:
            _LOGGER.debug(
                "WeatherData delivered at %s: %s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                msg,
            )
        except Exception:
            pass

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        self._task = self.hass.loop.create_task(self._listen())


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
        self._task = None
        self._client = None
        self._delay = max(0, int(delay_seconds or 0))
        # For duplicate filtering and startup replay suppression
        self._seen_ids: set[str] = set()
        self._startup_cutoff: datetime | None = None

    async def async_close(self, *_):
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._client:
            await self._client.close()

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

    async def _listen(self):
        from .signalr import SignalRClient

        self._client = SignalRClient(self.hass, self._session)
        while True:
            try:
                await self._client._ensure_connection()
                # Suppress historical replay within 30s before connect
                from datetime import timezone
                t0 = datetime.now(timezone.utc)
                self._startup_cutoff = t0 - timedelta(seconds=30)
                async for payload in self._client.messages():
                    msg = self._parse_message(payload)
                    if not msg:
                        continue
                    items = self._extract_items(msg)
                    if not items:
                        continue
                    try:
                        _LOGGER.debug(
                            "RaceControl received at %s, delay=%ss, items=%s",
                            dt_util.utcnow().isoformat(timespec="seconds"),
                            self._delay,
                            items,
                        )
                    except Exception:
                        pass

                    def schedule_delivery(item: dict):
                        if self._delay > 0:
                            try:
                                scheduled = (dt_util.utcnow() + timedelta(seconds=self._delay)).isoformat(timespec="seconds")
                                _LOGGER.debug(
                                    "RaceControl scheduled delivery at %s (+%ss) for item=%s",
                                    scheduled,
                                    self._delay,
                                    item,
                                )
                            except Exception:
                                pass
                            self.hass.loop.call_later(
                                self._delay,
                                lambda m=item: self._deliver(m),
                            )
                        else:
                            self._deliver(item)

                    # Deliver items individually with duplicate filtering and startup cutoff
                    for item in items:
                        # Parse timestamp
                        ts_raw = (
                            item.get("Utc")
                            or item.get("utc")
                            or item.get("processedAt")
                            or item.get("timestamp")
                        )
                        try:
                            if ts_raw and self._startup_cutoff:
                                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                                if ts.tzinfo is None:
                                    from datetime import timezone as _tz
                                    ts = ts.replace(tzinfo=_tz.utc)
                                if ts < self._startup_cutoff:
                                    _LOGGER.debug("RaceControl: Ignored old item at startup: %s", item)
                                    continue
                        except Exception:
                            pass

                        ident = self._message_id(item)
                        if ident in self._seen_ids:
                            _LOGGER.debug("RaceControl: Duplicate suppressed: %s", ident)
                            continue
                        self._seen_ids.add(ident)
                        schedule_delivery(item)
            except Exception as err:  # pragma: no cover - network errors
                self.available = False
                _LOGGER.warning("Race control websocket error: %s", err)
            finally:
                if self._client:
                    await self._client.close()

    def _deliver(self, item: dict) -> None:
        self.available = True
        # Maintain last message for visibility and parity with other coordinators
        self._last_message = item
        self.data_list = [item]
        self.async_set_updated_data(item)
        try:
            _LOGGER.debug(
                "RaceControl delivered at %s: %s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                item,
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
        self._task = self.hass.loop.create_task(self._listen())

class LapCountCoordinator(DataUpdateCoordinator):
    """Coordinator for LapCount updates using SignalR, mirrors other live feeds."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: 'LiveSessionCoordinator',
        delay_seconds: int = 0,
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
        self._task = None
        self._client = None
        self._delay = max(0, int(delay_seconds or 0))

    async def async_close(self, *_):
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._client:
            await self._client.close()

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

    async def _listen(self):
        from .signalr import SignalRClient

        self._client = SignalRClient(self.hass, self._session)
        while True:
            try:
                await self._client._ensure_connection()
                async for payload in self._client.messages():
                    msg = self._parse_message(payload)
                    if msg:
                        try:
                            _LOGGER.debug(
                                "LapCount received at %s, delay=%ss, message=%s",
                                dt_util.utcnow().isoformat(timespec="seconds"),
                                self._delay,
                                msg,
                            )
                        except Exception:
                            pass
                        if self._delay > 0:
                            try:
                                scheduled = (dt_util.utcnow() + timedelta(seconds=self._delay)).isoformat(timespec="seconds")
                                _LOGGER.debug(
                                    "LapCount scheduled delivery at %s (+%ss)",
                                    scheduled,
                                    self._delay,
                                )
                            except Exception:
                                pass
                            self.hass.loop.call_later(
                                self._delay,
                                lambda m=msg: self._deliver(m),
                            )
                        else:
                            self._deliver(msg)
            except Exception as err:  # pragma: no cover - network errors
                self.available = False
                _LOGGER.warning("Lap count websocket error: %s", err)
            finally:
                if self._client:
                    await self._client.close()

    def _deliver(self, msg: dict) -> None:
        self.available = True
        self._last_message = msg
        self.data_list = [msg]
        self.async_set_updated_data(msg)
        try:
            _LOGGER.debug(
                "LapCount delivered at %s: %s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                msg,
            )
        except Exception:
            pass

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        self._task = self.hass.loop.create_task(self._listen())


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        for coordinator in data.values():
            await coordinator.async_close()
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
        self._task = None
        self._client = None
        self._t0 = None
        self._startup_cutoff = None
        self._delay = max(0, int(delay_seconds or 0))

    async def async_close(self, *_):
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._client:
            await self._client.close()

    async def _async_update_data(self):
        return self._last_message

    async def _listen(self):
        from .signalr import SignalRClient

        self._client = SignalRClient(self.hass, self._session)
        while True:
            try:
                await self._client._ensure_connection()
                # Capture connection time similar to SignalRClient
                from datetime import timezone
                self._t0 = datetime.now(timezone.utc)
                self._startup_cutoff = self._t0 - timedelta(seconds=30)
                async for payload in self._client.messages():
                    msg = self._parse_message(payload)
                    if msg:
                        # Drop old messages around reconnect/heartbeat like flag sensor
                        utc_str = (
                            msg.get("Utc")
                            or msg.get("utc")
                            or msg.get("processedAt")
                            or msg.get("timestamp")
                        )
                        try:
                            if utc_str:
                                ts = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
                                if ts.tzinfo is None:
                                    from datetime import timezone as _tz
                                    ts = ts.replace(tzinfo=_tz.utc)
                                if self._startup_cutoff and ts < self._startup_cutoff:
                                    _LOGGER.debug("TrackStatus: Ignored old message: %s", msg)
                                    continue
                        except Exception:  # noqa: BLE001
                            pass

                        _LOGGER.debug(
                            "TrackStatus received at %s, status=%s, message=%s, delay=%ss",
                            dt_util.utcnow().isoformat(timespec="seconds"),
                            (msg.get("Status") if isinstance(msg, dict) else None),
                            (msg.get("Message") if isinstance(msg, dict) else None),
                            self._delay,
                        )
                        if self._delay > 0:
                            try:
                                scheduled = (dt_util.utcnow() + timedelta(seconds=self._delay)).isoformat(timespec="seconds")
                                _LOGGER.debug(
                                    "TrackStatus scheduled delivery at %s (+%ss)",
                                    scheduled,
                                    self._delay,
                                )
                            except Exception:
                                pass
                            self.hass.loop.call_later(
                                self._delay,
                                lambda m=msg: self._deliver(m),
                            )
                        else:
                            self._deliver(msg)
            except Exception as err:  # pragma: no cover - network errors
                self.available = False
                _LOGGER.warning("Track status websocket error: %s", err)
            finally:
                if self._client:
                    await self._client.close()

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
        try:
            _LOGGER.debug(
                "TrackStatus delivered at %s: %s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                msg,
            )
        except Exception:
            pass

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        self._task = self.hass.loop.create_task(self._listen())


class SessionStatusCoordinator(DataUpdateCoordinator):
    """Coordinator for SessionStatus updates using SignalR."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: LiveSessionCoordinator,
        delay_seconds: int = 0,
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
        self._task = None
        self._client = None
        self._delay = max(0, int(delay_seconds or 0))

    async def async_close(self, *_):
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._client:
            await self._client.close()

    async def _async_update_data(self):
        return self._last_message

    async def _listen(self):
        from .signalr import SignalRClient

        self._client = SignalRClient(self.hass, self._session)
        while True:
            try:
                await self._client._ensure_connection()
                async for payload in self._client.messages():
                    msg = self._parse_message(payload)
                    if msg:
                        _LOGGER.debug(
                            "SessionStatus received at %s, status=%s, started=%s, delay=%ss",
                            dt_util.utcnow().isoformat(timespec="seconds"),
                            (msg.get("Status") if isinstance(msg, dict) else None),
                            (msg.get("Started") if isinstance(msg, dict) else None),
                            self._delay,
                        )
                        if self._delay > 0:
                            try:
                                scheduled = (dt_util.utcnow() + timedelta(seconds=self._delay)).isoformat(timespec="seconds")
                                _LOGGER.debug(
                                    "SessionStatus scheduled delivery at %s (+%ss)",
                                    scheduled,
                                    self._delay,
                                )
                            except Exception:
                                pass
                            self.hass.loop.call_later(
                                self._delay,
                                lambda m=msg: self._deliver(m),
                            )
                        else:
                            self._deliver(msg)
            except Exception as err:  # pragma: no cover - network errors
                self.available = False
                _LOGGER.warning("Session status websocket error: %s", err)
            finally:
                if self._client:
                    await self._client.close()

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

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        self._task = self.hass.loop.create_task(self._listen())

    def _deliver(self, msg: dict) -> None:
        self.available = True
        self._last_message = msg
        self.data_list = [msg]
        self.async_set_updated_data(msg)
        try:
            _LOGGER.debug(
                "SessionStatus delivered at %s: %s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                msg,
            )
        except Exception:
            pass

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        self._task = self.hass.loop.create_task(self._listen())
