import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    PLATFORMS,
    API_URL,
    DRIVER_STANDINGS_URL,
    CONSTRUCTOR_STANDINGS_URL,
    LAST_RACE_RESULTS_URL,
    SEASON_RESULTS_URL,
)
from .api import F1ApiClient
from .coordinator import F1DataCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration via config flow."""
    session = async_get_clientsession(hass)
    client = F1ApiClient(session)

    race_coordinator = F1DataCoordinator(hass, client, API_URL, "F1 Race Data Coordinator")
    driver_coordinator = F1DataCoordinator(hass, client, DRIVER_STANDINGS_URL, "F1 Driver Standings Coordinator")
    constructor_coordinator = F1DataCoordinator(hass, client, CONSTRUCTOR_STANDINGS_URL, "F1 Constructor Standings Coordinator")
    last_race_coordinator = F1DataCoordinator(hass, client, LAST_RACE_RESULTS_URL, "F1 Last Race Results Coordinator")
    season_results_coordinator = F1DataCoordinator(hass, client, SEASON_RESULTS_URL, "F1 Season Results Coordinator", paginated=True)

    await race_coordinator.async_config_entry_first_refresh()
    await driver_coordinator.async_config_entry_first_refresh()
    await constructor_coordinator.async_config_entry_first_refresh()
    await last_race_coordinator.async_config_entry_first_refresh()
    await season_results_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "race_coordinator": race_coordinator,
        "driver_coordinator": driver_coordinator,
        "constructor_coordinator": constructor_coordinator,
        "last_race_coordinator": last_race_coordinator,
        "season_results_coordinator": season_results_coordinator,
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


