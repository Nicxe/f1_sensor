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

from .const import (
    API_URL,
    CONSTRUCTOR_STANDINGS_URL,
    DOMAIN,
    DRIVER_STANDINGS_URL,
    LAST_RACE_RESULTS_URL,
    LIVETIMING_INDEX_URL,
    PLATFORMS,
    SEASON_RESULTS_URL,
    FLAG_MACHINE,
)
from .flag_state import FlagState

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
    enable_rc = entry.data.get("enable_race_control", True)
    race_control_coordinator = None
    hass.data[FLAG_MACHINE] = FlagState()
    if enable_rc:
        race_control_coordinator = RaceControlCoordinator(
            hass, session_coordinator
        )

    await race_coordinator.async_config_entry_first_refresh()
    await driver_coordinator.async_config_entry_first_refresh()
    await constructor_coordinator.async_config_entry_first_refresh()
    await last_race_coordinator.async_config_entry_first_refresh()
    await season_results_coordinator.async_config_entry_first_refresh()
    await session_coordinator.async_config_entry_first_refresh()
    if race_control_coordinator:
        await race_control_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "race_coordinator": race_coordinator,
        "driver_coordinator": driver_coordinator,
        "constructor_coordinator": constructor_coordinator,
        "last_race_coordinator": last_race_coordinator,
        "season_results_coordinator": season_results_coordinator,
        "session_coordinator": session_coordinator,
        "race_control_coordinator": race_control_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        for coordinator in data.values():
            await coordinator.async_close()
        hass.data.pop(FLAG_MACHINE, None)
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


class RaceControlCoordinator(DataUpdateCoordinator):
    """Coordinator for race control messages using SignalR."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: LiveSessionCoordinator,
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

        from .const import BACK_OFF_FACTOR, FAST_RETRY_SEC, MAX_RETRY_SEC

        self._client = SignalRClient(self.hass, self._session)
        delay = FAST_RETRY_SEC
        while True:
            try:
                await self._client.connect()
                delay = FAST_RETRY_SEC
                async for payload in self._client.messages():
                    msg = self._parse_message(payload)
                    if msg:
                        _LOGGER.debug("Race control message: %s", msg)
                        self.available = True
                        self._last_message = msg
                        self.data_list = [msg]
                        self.async_set_updated_data(msg)
            except Exception as err:  # pragma: no cover - network errors
                self.available = False
                _LOGGER.warning(
                    "Race control websocket error: %s. Retrying in %s s …",
                    err,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * BACK_OFF_FACTOR, MAX_RETRY_SEC)
            finally:
                if self._client:
                    await self._client.close()

    @staticmethod
    def _parse_message(data):
        messages = data.get("M") if isinstance(data, dict) else None
        if not messages:
            return None
        for update in messages:
            args = update.get("A", [])
            if len(args) < 2:
                continue
            if args[0] == "RaceControlMessages":
                content = args[1]
                if isinstance(content, list) and content:
                    msg = content[-1]
                    return msg
                if isinstance(content, dict) and content:
                    numeric_keys = [k for k in content.keys() if str(k).isdigit()]
                    if numeric_keys:
                        key = max(numeric_keys, key=lambda x: int(x))
                        msg = content[key]
                        if isinstance(msg, dict):
                            msg.setdefault("id", int(key))
                        return msg
                    try:
                        content.get("m", content.get("Category"))
                    except KeyError as exc:
                        _LOGGER.warning(
                            "Race control websocket error: %s", exc
                        )
                        return None
                    return content
        return None

    async def async_config_entry_first_refresh(self):
        await super().async_config_entry_first_refresh()
        self._task = self.hass.loop.create_task(self._listen())
