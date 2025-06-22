import logging
from datetime import timedelta, datetime, timezone
import json
import urllib.parse
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
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration via config flow."""
    race_coordinator = F1DataCoordinator(hass, API_URL, "F1 Race Data Coordinator")
    driver_coordinator = F1DataCoordinator(hass, DRIVER_STANDINGS_URL, "F1 Driver Standings Coordinator")
    constructor_coordinator = F1DataCoordinator(hass, CONSTRUCTOR_STANDINGS_URL, "F1 Constructor Standings Coordinator")
    last_race_coordinator = F1DataCoordinator(hass, LAST_RACE_RESULTS_URL, "F1 Last Race Results Coordinator")
    season_results_coordinator = F1DataCoordinator(hass, SEASON_RESULTS_URL, "F1 Season Results Coordinator")

    await race_coordinator.async_config_entry_first_refresh()
    await driver_coordinator.async_config_entry_first_refresh()
    await constructor_coordinator.async_config_entry_first_refresh()
    await last_race_coordinator.async_config_entry_first_refresh()
    await season_results_coordinator.async_config_entry_first_refresh()

    enabled = entry.data.get("enabled_sensors", [])
    race_control_coordinator = None
    if "flag_status" in enabled or "safety_car" in enabled:
        race_control_coordinator = RaceControlCoordinator(hass, race_coordinator)
        await race_control_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "race_coordinator": race_coordinator,
        "driver_coordinator": driver_coordinator,
        "constructor_coordinator": constructor_coordinator,
        "last_race_coordinator": last_race_coordinator,
        "season_results_coordinator": season_results_coordinator,
        "race_control_coordinator": race_control_coordinator,
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
        try:
            async with async_timeout.timeout(10):
                async with self._session.get(self._url) as response:
                    if response.status != 200:
                        raise UpdateFailed(f"Error fetching data: {response.status}")
                    return await response.json()
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err


class RaceControlCoordinator(DataUpdateCoordinator):
    """Coordinator for F1 race control messages."""

    def __init__(self, hass: HomeAssistant, race_coordinator: F1DataCoordinator):
        super().__init__(
            hass,
            _LOGGER,
            name="F1 Race Control Coordinator",
            update_interval=timedelta(seconds=5),
        )
        self._session = async_get_clientsession(hass)
        self._race_coordinator = race_coordinator
        self._yellow_sectors: set[str] = set()
        self._sc_active = False
        self._vsc_active = False
        self._red_flag = False
        self._finished = False
        self._last = {"flag_status": None, "sc_active": False}

    async def async_close(self, *_):
        return

    def _combine_dt(self, date: str | None, time: str | None) -> datetime | None:
        if not date:
            return None
        if not time:
            time = "00:00:00Z"
        try:
            return datetime.fromisoformat(f"{date}T{time}".replace("Z", "+00:00"))
        except ValueError:
            return None

    def _current_session(self):
        data = self._race_coordinator.data or {}
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        now = datetime.now(timezone.utc)
        for race in races:
            race_dt = self._combine_dt(race.get("date"), race.get("time"))
            qual = race.get("Qualifying", {})
            qual_dt = self._combine_dt(qual.get("date"), qual.get("time"))
            if race_dt and race_dt - timedelta(minutes=30) <= now <= race_dt + timedelta(hours=3):
                return race, "Race", race_dt
            if qual_dt and qual_dt - timedelta(minutes=30) <= now <= qual_dt + timedelta(hours=2):
                return race, "Qualifying", qual_dt
        return None, None, None

    def _build_url(self, race: dict, session_name: str) -> str:
        year = race.get("season")
        event = urllib.parse.quote(race.get("raceName", "").replace(" ", "_"))
        event_path = f"{race.get('date')}_{event}"
        if session_name == "Race":
            session_date = race.get("date")
        else:
            session_date = race.get("Qualifying", {}).get("date")
        session_path = f"{session_date}_{session_name}"
        return (
            f"https://livetiming.formula1.com/static/{year}/{event_path}/{session_path}/RaceControlMessages.jsonStream"
        )

    def _handle_message(self, msg: dict):
        flag = str(msg.get("Flag", "")).upper()
        status = str(msg.get("Status", "")).upper()
        text = str(msg.get("Message", "")).upper()
        scope = msg.get("Scope")
        sector = msg.get("Sector")

        if flag in ("YELLOW", "DOUBLE YELLOW"):
            if scope == "Sector" and sector is not None:
                self._yellow_sectors.add(str(sector))
            else:
                self._yellow_sectors.add("track")
        elif flag in ("GREEN", "CLEAR"):
            if scope == "Sector" and sector is not None:
                self._yellow_sectors.discard(str(sector))
            else:
                self._yellow_sectors.clear()
                self._red_flag = False
        if flag == "RED":
            self._red_flag = True

        if "VIRTUAL SAFETY CAR" in text or status.startswith("VSC"):
            if "END" in text or "ENDING" in text or status.endswith("ENDING") or status.endswith("WITHDRAWN"):
                self._vsc_active = False
            elif "DEPLOYED" in text or "DEPLOYED" in status:
                self._vsc_active = True

        if "SAFETY CAR" in text and "VIRTUAL" not in text:
            if "END" in text or "IN THIS LAP" in text or "ENDING" in text or status.endswith("ENDING"):
                self._sc_active = False
            elif "DEPLOYED" in text or status.endswith("DEPLOYED"):
                self._sc_active = True

        if "CHEQUERED" in text or "SESSION FINISHED" in text:
            self._finished = True

    def _derive(self):
        if self._red_flag:
            return "RED"
        if self._sc_active:
            return "SC"
        if self._vsc_active:
            return "VSC"
        if self._yellow_sectors:
            return "YELLOW"
        return "GREEN"

    async def _async_update_data(self):
        race, session_name, _ = self._current_session()
        if not race or not session_name or self._finished:
            return self._last

        url = self._build_url(race, session_name)
        try:
            async with async_timeout.timeout(10):
                resp = await self._session.get(url)
                if resp.status == 404:
                    return self._last
                if resp.status != 200:
                    raise UpdateFailed(f"Race control fetch failed: {resp.status}")
                text = await resp.text()
        except Exception as err:
            raise UpdateFailed(f"Error fetching race control data: {err}") from err

        for line in text.splitlines():
            if not line:
                continue
            line = line.lstrip("\ufeff")
            json_start = line.find("{")
            if json_start == -1:
                continue
            try:
                data = json.loads(line[json_start:])
            except Exception:
                continue
            msgs = data.get("Messages")
            if isinstance(msgs, dict):
                iterable = msgs.values()
            else:
                iterable = msgs or []
            for msg in iterable:
                self._handle_message(msg)

        self._last = {
            "flag_status": self._derive(),
            "sc_active": self._sc_active or self._vsc_active,
        }
        return self._last


