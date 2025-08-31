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
    season_results_coordinator = F1DataCoordinator(
        hass, SEASON_RESULTS_URL, "F1 Season Results Coordinator"
    )
    year = datetime.utcnow().year
    session_coordinator = LiveSessionCoordinator(hass, year)
    enable_rc = entry.data.get("enable_race_control", False)
    live_delay = int(entry.data.get("live_delay_seconds", 0) or 0)
    track_status_coordinator = None
    session_status_coordinator = None
    hass.data[LATEST_TRACK_STATUS] = None
    if enable_rc:
        track_status_coordinator = TrackStatusCoordinator(
            hass, session_coordinator, live_delay
        )
        session_status_coordinator = SessionStatusCoordinator(
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

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "race_coordinator": race_coordinator,
        "driver_coordinator": driver_coordinator,
        "constructor_coordinator": constructor_coordinator,
        "last_race_coordinator": last_race_coordinator,
        "season_results_coordinator": season_results_coordinator,
        "session_coordinator": session_coordinator,
        "track_status_coordinator": track_status_coordinator,
        "session_status_coordinator": session_status_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


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
