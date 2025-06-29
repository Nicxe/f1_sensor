import logging
from datetime import timedelta, datetime, timezone
import async_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    PLATFORMS,
    API_URL,
    DRIVER_STANDINGS_URL,
    CONSTRUCTOR_STANDINGS_URL,
    LAST_RACE_RESULTS_URL,
    SEASON_RESULTS_URL,
    LIVETIMING_INDEX_URL,
    RACE_CONTROL_URL,
)
from .helpers import find_next_session, to_utc, parse_racecontrol

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration via config flow."""
    race_coordinator = F1DataCoordinator(hass, API_URL, "F1 Race Data Coordinator")
    driver_coordinator = F1DataCoordinator(hass, DRIVER_STANDINGS_URL, "F1 Driver Standings Coordinator")
    constructor_coordinator = F1DataCoordinator(hass, CONSTRUCTOR_STANDINGS_URL, "F1 Constructor Standings Coordinator")
    last_race_coordinator = F1DataCoordinator(hass, LAST_RACE_RESULTS_URL, "F1 Last Race Results Coordinator")
    season_results_coordinator = F1DataCoordinator(hass, SEASON_RESULTS_URL, "F1 Season Results Coordinator")
    year = datetime.utcnow().year
    session_coordinator = LiveSessionCoordinator(hass, year)
    enable_rc = entry.data.get("enable_race_control", True)
    fast_seconds = entry.data.get("fast_poll_seconds", 5)
    race_control_coordinator = None
    if enable_rc:
        race_control_coordinator = RaceControlCoordinator(hass, session_coordinator, fast_seconds)

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
                    return await response.json()
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
                    return await response.json()
        except Exception as err:
            _LOGGER.warning("Error fetching index: %s", err)
            return self.data


class RaceControlCoordinator(DataUpdateCoordinator):
    """Coordinator for race control messages."""

    def __init__(self, hass: HomeAssistant, session_coord: LiveSessionCoordinator, fast_seconds: int = 5):
        super().__init__(
            hass,
            _LOGGER,
            name="F1 Race Control Coordinator",
            update_interval=timedelta(hours=1),
        )
        self._session = async_get_clientsession(hass)
        self._session_coord = session_coord
        self._fast = timedelta(seconds=fast_seconds)
        self.available = True
        self._last_message = None

    async def async_close(self, *_):
        return

    def _adjust_interval(self, session):
        start = to_utc(session.get("StartDate"), session.get("GmtOffset"))
        end = to_utc(session.get("EndDate"), session.get("GmtOffset"))
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        if start and end and start - timedelta(hours=1) <= now <= end + timedelta(hours=2):
            if self.update_interval != self._fast:
                self.update_interval = self._fast
        elif self._last_message:
            try:
                msg_dt = to_utc(self._last_message.get("Utc"), "+00:00")
            except Exception:
                msg_dt = None
            if msg_dt and end and msg_dt > end + timedelta(hours=2):
                if self.update_interval != timedelta(hours=1):
                    self.update_interval = timedelta(hours=1)

    async def _async_update_data(self):
        if not self._session_coord.data:
            return self._last_message
        meeting, session = find_next_session(self._session_coord.data)
        if not session:
            return self._last_message

        self._adjust_interval(session)

        url = RACE_CONTROL_URL.format(path=session.get("Path"))
        try:
            async with async_timeout.timeout(10):
                async with self._session.get(url) as response:
                    if response.status in (403, 404):
                        self.available = False
                        _LOGGER.warning("Race control unavailable: %s", response.status)
                        return self._last_message
                    if response.status != 200:
                        raise UpdateFailed(f"Error fetching data: {response.status}")
                    text = await response.text()
        except Exception as err:
            _LOGGER.warning("Error fetching race control: %s", err)
            return self._last_message

        self.available = True
        msg = parse_racecontrol(text)
        if msg:
            self._last_message = msg
        return self._last_message

