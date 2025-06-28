import logging
from datetime import timedelta
import async_timeout

__version__ = "1.4.0"

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .race_control import resolve_racecontrol_url

from .const import (
    DOMAIN,
    PLATFORMS,
    API_URL,
    DRIVER_STANDINGS_URL,
    CONSTRUCTOR_STANDINGS_URL,
    LAST_RACE_RESULTS_URL,
    SEASON_RESULTS_URL,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration via config flow."""
    _LOGGER.debug("Setting up entry %s with data: %s", entry.entry_id, entry.data)
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

    await race_coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("Race data coordinator initial refresh done")
    await driver_coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("Driver standings coordinator initial refresh done")
    await constructor_coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("Constructor standings coordinator initial refresh done")
    await last_race_coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("Last race results coordinator initial refresh done")
    await season_results_coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("Season results coordinator initial refresh done")

    enabled = entry.data.get("enabled_sensors", [])
    race_control_coordinator = None
    if "flag_status" in enabled or "safety_car" in enabled:
        from .race_control_coordinator import RaceControlCoordinator

        race_control_coordinator = RaceControlCoordinator(
            hass, race_coordinator, entry.entry_id
        )
        await race_control_coordinator.async_setup_entry()
        await race_control_coordinator.async_config_entry_first_refresh()
        _LOGGER.debug("Race control coordinator initialized")

    from .realtime_coordinators import (
        TrackStatusWSCoordinator,
        SessionStatusCoordinator,
    )

    track_ws_coordinator = TrackStatusWSCoordinator(hass)
    session_status_coordinator = SessionStatusCoordinator(hass)
    await track_ws_coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("TrackStatus websocket coordinator ready")
    await session_status_coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("SessionStatus websocket coordinator ready")

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "race_coordinator": race_coordinator,
        "driver_coordinator": driver_coordinator,
        "constructor_coordinator": constructor_coordinator,
        "last_race_coordinator": last_race_coordinator,
        "season_results_coordinator": season_results_coordinator,
        "race_control_coordinator": race_control_coordinator,
        "track_ws_coordinator": track_ws_coordinator,
        "session_status_coordinator": session_status_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        for coordinator in data.values():
            if coordinator:
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
        _LOGGER.debug("Fetching data from %s", self._url)
        try:
            async with async_timeout.timeout(10):
                async with self._session.get(self._url) as response:
                    if response.status != 200:
                        raise UpdateFailed(f"Error fetching data: {response.status}")
                    data = await response.json()
                    _LOGGER.debug("Fetched %d bytes from %s", response.content_length or 0, self._url)
                    return data
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err
