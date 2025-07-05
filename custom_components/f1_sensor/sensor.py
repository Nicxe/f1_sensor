import datetime
from zoneinfo import ZoneInfo

import async_timeout
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from timezonefinder import TimezoneFinder

from .const import DOMAIN
from .entity import F1BaseEntity
from .helpers import find_next_session

SYMBOL_CODE_TO_MDI = {
    "clearsky_day": "mdi:weather-sunny",
    "clearsky_night": "mdi:weather-night",
    "fair_day": "mdi:weather-partly-cloudy",
    "fair_night": "mdi:weather-night-partly-cloudy",
    "partlycloudy_day": "mdi:weather-partly-cloudy",
    "partlycloudy_night": "mdi:weather-night-partly-cloudy",
    "cloudy": "mdi:weather-cloudy",
    "fog": "mdi:weather-fog",
    "rainshowers_day": "mdi:weather-rainy",
    "rainshowers_night": "mdi:weather-rainy",
    "rainshowersandthunder_day": "mdi:weather-lightning-rainy",
    "rainshowersandthunder_night": "mdi:weather-lightning-rainy",
    "heavyrainshowers_day": "mdi:weather-pouring",
    "heavyrainshowers_night": "mdi:weather-pouring",
    "sleetshowers_day": "mdi:weather-snowy-rainy",
    "sleetshowers_night": "mdi:weather-snowy-rainy",
    "snowshowers_day": "mdi:weather-snowy",
    "snowshowers_night": "mdi:weather-snowy",
    "rain": "mdi:weather-pouring",
    "heavyrain": "mdi:weather-pouring",
    "heavyrainandthunder": "mdi:weather-lightning-rainy",
    "sleet": "mdi:weather-snowy-rainy",
    "snow": "mdi:weather-snowy",
    "snowandthunder": "mdi:weather-snowy-heavy",
    "rainandthunder": "mdi:weather-lightning-rainy",
    "sleetandthunder": "mdi:weather-lightning-rainy",
    "lightrainshowers_day": "mdi:weather-rainy",
    "lightrainshowers_night": "mdi:weather-rainy",
    "lightrainshowersandthunder_day": "mdi:weather-lightning-rainy",
    "lightrainshowersandthunder_night": "mdi:weather-lightning-rainy",
    "lightsleetshowers_day": "mdi:weather-snowy-rainy",
    "lightsleetshowers_night": "mdi:weather-snowy-rainy",
    "lightsnowshowers_day": "mdi:weather-snowy",
    "lightsnowshowers_night": "mdi:weather-snowy",
    "lightsnowshowersandthunder_day": "mdi:weather-lightning-snowy",
    "lightsnowshowersandthunder_night": "mdi:weather-lightning-snowy",
    "lightssleetshowersandthunder_day": "mdi:weather-lightning-snowy-rainy",
    "lightssleetshowersandthunder_night": "mdi:weather-lightning-snowy-rainy",
    "lightssnowshowersandthunder_day": "mdi:weather-lightning-snowy",
    "lightssnowshowersandthunder_night": "mdi:weather-lightning-snowy",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Create sensors when integration is added."""
    data = hass.data[DOMAIN][entry.entry_id]
    base = entry.data.get("sensor_name", "F1")
    enabled = entry.data.get("enabled_sensors", [])

    mapping = {
        "next_race": (F1NextRaceSensor, data["race_coordinator"]),
        "current_season": (F1CurrentSeasonSensor, data["race_coordinator"]),
        "driver_standings": (F1DriverStandingsSensor, data["driver_coordinator"]),
        "constructor_standings": (
            F1ConstructorStandingsSensor,
            data["constructor_coordinator"],
        ),
        "weather": (F1WeatherSensor, data["race_coordinator"]),
        "last_race_results": (F1LastRaceSensor, data["last_race_coordinator"]),
        "season_results": (F1SeasonResultsSensor, data["season_results_coordinator"]),
        "next_session": (F1NextSessionSensor, data.get("session_coordinator")),
        "race_control": (F1RaceControlSensor, data.get("race_control_coordinator")),
        "flag": (F1FlagSensor, data.get("race_control_coordinator")),
    }

    sensors = []
    for key in enabled:
        cls, coord = mapping.get(key, (None, None))
        if cls and coord:
            sensors.append(
                cls(
                    coord,
                    f"{base}_{key}",
                    f"{entry.entry_id}_{key}",
                    entry.entry_id,
                    base,
                )
            )
    async_add_entities(sensors, True)


class F1NextRaceSensor(F1BaseEntity, SensorEntity):
    """Sensor that returns date/time (ISO8601) for the next race in 'state'."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:flag-checkered"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._tf = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._tf = await self.hass.async_add_executor_job(TimezoneFinder)

    def _get_next_race(self):
        data = self.coordinator.data
        if not data:
            return None

        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        now = datetime.datetime.now(datetime.timezone.utc)

        for race in races:
            date = race.get("date")
            time = race.get("time") or "00:00:00Z"
            dt_str = f"{date}T{time}".replace("Z", "+00:00")
            try:
                dt = datetime.datetime.fromisoformat(dt_str)
            except ValueError:
                continue
            if dt > now:
                return race
        return None

    def combine_date_time(self, date_str, time_str):
        if not date_str:
            return None
        if not time_str:
            time_str = "00:00:00Z"
        dt_str = f"{date_str}T{time_str}".replace("Z", "+00:00")
        try:
            dt = datetime.datetime.fromisoformat(dt_str)
            return dt.isoformat()
        except ValueError:
            return None

    def _timezone_from_location(self, lat, lon):
        if lat is None or lon is None or self._tf is None:
            return None
        try:
            return self._tf.timezone_at(lat=float(lat), lng=float(lon))
        except Exception:
            return None

    def _to_local(self, iso_ts, timezone):
        if not iso_ts or not timezone:
            return None
        try:
            dt = datetime.datetime.fromisoformat(iso_ts)
            return dt.astimezone(ZoneInfo(timezone)).isoformat()
        except Exception:
            return None

    @property
    def state(self):
        next_race = self._get_next_race()
        if not next_race:
            return None
        return self.combine_date_time(next_race.get("date"), next_race.get("time"))

    @property
    def extra_state_attributes(self):
        race = self._get_next_race()
        if not race:
            return {}

        circuit = race.get("Circuit", {})
        loc = circuit.get("Location", {})
        timezone = self._timezone_from_location(loc.get("lat"), loc.get("long"))

        first_practice = race.get("FirstPractice", {})
        second_practice = race.get("SecondPractice", {})
        third_practice = race.get("ThirdPractice", {})
        qualifying = race.get("Qualifying", {})
        sprint_qualifying = race.get("SprintQualifying", {})
        sprint = race.get("Sprint", {})

        race_start = self.combine_date_time(race.get("date"), race.get("time"))
        first_start = self.combine_date_time(
            first_practice.get("date"), first_practice.get("time")
        )
        second_start = self.combine_date_time(
            second_practice.get("date"), second_practice.get("time")
        )
        third_start = self.combine_date_time(
            third_practice.get("date"), third_practice.get("time")
        )
        qual_start = self.combine_date_time(
            qualifying.get("date"), qualifying.get("time")
        )
        sprint_quali_start = self.combine_date_time(
            sprint_qualifying.get("date"), sprint_qualifying.get("time")
        )
        sprint_start = self.combine_date_time(sprint.get("date"), sprint.get("time"))

        return {
            "season": race.get("season"),
            "round": race.get("round"),
            "race_name": race.get("raceName"),
            "race_url": race.get("url"),
            "circuit_id": circuit.get("circuitId"),
            "circuit_name": circuit.get("circuitName"),
            "circuit_url": circuit.get("url"),
            "circuit_lat": loc.get("lat"),
            "circuit_long": loc.get("long"),
            "circuit_locality": loc.get("locality"),
            "circuit_country": loc.get("country"),
            "circuit_timezone": timezone,
            "race_start": race_start,
            "race_start_local": self._to_local(race_start, timezone),
            "first_practice_start": first_start,
            "first_practice_start_local": self._to_local(first_start, timezone),
            "second_practice_start": second_start,
            "second_practice_start_local": self._to_local(second_start, timezone),
            "third_practice_start": third_start,
            "third_practice_start_local": self._to_local(third_start, timezone),
            "qualifying_start": qual_start,
            "qualifying_start_local": self._to_local(qual_start, timezone),
            "sprint_qualifying_start": sprint_quali_start,
            "sprint_qualifying_start_local": self._to_local(
                sprint_quali_start, timezone
            ),
            "sprint_start": sprint_start,
            "sprint_start_local": self._to_local(sprint_start, timezone),
        }


class F1CurrentSeasonSensor(F1BaseEntity, SensorEntity):
    """Sensor showing number of races this season."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:calendar-month"

    @property
    def state(self):
        data = self.coordinator.data or {}
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        return len(races)

    @property
    def extra_state_attributes(self):
        table = (self.coordinator.data or {}).get("MRData", {}).get("RaceTable", {})
        return {"season": table.get("season"), "races": table.get("Races", [])}


class F1DriverStandingsSensor(F1BaseEntity, SensorEntity):
    """Sensor for driver standings."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:account-multiple-check"

    @property
    def state(self):
        lists = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("StandingsTable", {})
            .get("StandingsLists", [])
        )
        return len(lists[0].get("DriverStandings", [])) if lists else 0

    @property
    def extra_state_attributes(self):
        lists = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("StandingsTable", {})
            .get("StandingsLists", [])
        )
        if not lists:
            return {}
        first = lists[0]
        return {
            "season": first.get("season"),
            "round": first.get("round"),
            "driver_standings": first.get("DriverStandings", []),
        }


class F1ConstructorStandingsSensor(F1BaseEntity, SensorEntity):
    """Sensor for constructor standings."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:factory"

    @property
    def state(self):
        lists = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("StandingsTable", {})
            .get("StandingsLists", [])
        )
        return len(lists[0].get("ConstructorStandings", [])) if lists else 0

    @property
    def extra_state_attributes(self):
        lists = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("StandingsTable", {})
            .get("StandingsLists", [])
        )
        if not lists:
            return {}
        first = lists[0]
        return {
            "season": first.get("season"),
            "round": first.get("round"),
            "constructor_standings": first.get("ConstructorStandings", []),
        }


class F1WeatherSensor(F1BaseEntity, SensorEntity):
    """Sensor for current and race-start weather."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:weather-partly-cloudy"
        self._current = {}
        self._race = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        removal = self.coordinator.async_add_listener(
            lambda: self.hass.async_create_task(self._update_weather())
        )
        self.async_on_remove(removal)
        await self._update_weather()

    def _get_next_race(self):
        data = self.coordinator.data
        if not data:
            return None

        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        now = datetime.datetime.now(datetime.timezone.utc)

        for race in races:
            date = race.get("date")
            time = race.get("time") or "00:00:00Z"
            dt_str = f"{date}T{time}".replace("Z", "+00:00")
            try:
                dt = datetime.datetime.fromisoformat(dt_str)
            except ValueError:
                continue
            if dt > now:
                return race
        return None

    def _combine_date_time(self, date_str, time_str):
        if not date_str:
            return None
        if not time_str:
            time_str = "00:00:00Z"
        dt_str = f"{date_str}T{time_str}".replace("Z", "+00:00")
        try:
            dt = datetime.datetime.fromisoformat(dt_str)
            return dt.isoformat()
        except ValueError:
            return None

    async def _update_weather(self):
        race = self._get_next_race()
        loc = race.get("Circuit", {}).get("Location", {}) if race else {}
        lat, lon = loc.get("lat"), loc.get("long")
        if lat is None or lon is None:
            return
        session = async_get_clientsession(self.hass)
        url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"
        headers = {"User-Agent": "homeassistant-f1_sensor"}
        try:
            async with async_timeout.timeout(10):
                resp = await session.get(url, headers=headers)
                data = await resp.json()
        except Exception:
            return
        times = data.get("properties", {}).get("timeseries", [])
        if not times:
            return
        curr = times[0].get("data", {}).get("instant", {}).get("details", {})
        self._current = self._extract(curr)
        current_symbol = (
            times[0]
            .get("data", {})
            .get("next_1_hours", {})
            .get("summary", {})
            .get("symbol_code")
        )
        current_icon = SYMBOL_CODE_TO_MDI.get(current_symbol, self._attr_icon)
        self._attr_icon = current_icon
        start_iso = (
            self._combine_date_time(race.get("date"), race.get("time"))
            if race
            else None
        )
        self._race = {k: None for k in self._current}
        if start_iso:
            start_dt = datetime.datetime.fromisoformat(start_iso)
            same_day = [
                t
                for t in times
                if datetime.datetime.fromisoformat(t["time"]).date() == start_dt.date()
            ]
            if same_day:
                closest = min(
                    same_day,
                    key=lambda t: abs(
                        datetime.datetime.fromisoformat(t["time"]) - start_dt
                    ),
                )
                data_entry = closest.get("data", {})
                instant_details = data_entry.get("instant", {}).get("details", {})
                precip_1h = (
                    data_entry.get("next_1_hours", {})
                    .get("details", {})
                    .get("precipitation_amount", 0)
                )
                rd = dict(instant_details)
                rd["precipitation_amount"] = precip_1h
                self._race = self._extract(rd)
                forecast_block = (
                    data_entry.get("next_1_hours")
                    or data_entry.get("next_6_hours")
                    or data_entry.get("next_12_hours", {})
                )
                race_symbol = forecast_block.get("summary", {}).get("symbol_code")
                race_icon = SYMBOL_CODE_TO_MDI.get(race_symbol, self._attr_icon)
                self._race["weather_icon"] = race_icon
        self.async_write_ha_state()

    def _extract(self, d):
        wd = d.get("wind_from_direction")
        return {
            "temperature": d.get("air_temperature"),
            "temperature_unit": "celsius",
            "humidity": d.get("relative_humidity"),
            "humidity_unit": "%",
            "cloud_cover": d.get("cloud_area_fraction"),
            "cloud_cover_unit": "%",
            "precipitation": d.get("precipitation_amount", 0),
            "precipitation_unit": "mm",
            "wind_speed": d.get("wind_speed"),
            "wind_speed_unit": "m/s",
            "wind_direction": self._abbr(wd),
            "wind_from_direction_degrees": wd,
            "wind_from_direction_unit": "degrees",
        }

    def _abbr(self, deg):
        if deg is None:
            return None
        dirs = [
            (i * 22.5, d)
            for i, d in enumerate(
                [
                    "N",
                    "NNE",
                    "NE",
                    "ENE",
                    "E",
                    "ESE",
                    "SE",
                    "SSE",
                    "S",
                    "SSW",
                    "SW",
                    "WSW",
                    "W",
                    "WNW",
                    "NW",
                    "NNW",
                    "N",
                ]
            )
        ]
        return min(dirs, key=lambda x: abs(deg - x[0]))[1]

    @property
    def state(self):
        return self._current.get("temperature")

    @property
    def extra_state_attributes(self):
        attrs = {f"current_{k}": v for k, v in self._current.items()}
        attrs.update({f"race_{k}": v for k, v in self._race.items()})
        return attrs


class F1LastRaceSensor(F1BaseEntity, SensorEntity):
    """Sensor for results of the latest race."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:trophy"

    @property
    def state(self):
        races = (
            self.coordinator.data.get("MRData", {})
            .get("RaceTable", {})
            .get("Races", [])
        )
        if not races:
            return None
        results = races[0].get("Results", [])
        winner = next((r for r in results if r.get("positionText") == "1"), None)
        return winner.get("Driver", {}).get("familyName") if winner else None

    @property
    def extra_state_attributes(self):
        races = (
            self.coordinator.data.get("MRData", {})
            .get("RaceTable", {})
            .get("Races", [])
        )
        if not races:
            return {}
        race = races[0]

        def _clean_result(r):
            return {
                "number": r.get("number"),
                "position": r.get("position"),
                "points": r.get("points"),
                "status": r.get("status"),
                "driver": {
                    "permanentNumber": r.get("Driver", {}).get("permanentNumber"),
                    "code": r.get("Driver", {}).get("code"),
                    "givenName": r.get("Driver", {}).get("givenName"),
                    "familyName": r.get("Driver", {}).get("familyName"),
                },
                "constructor": {
                    "constructorId": r.get("Constructor", {}).get("constructorId"),
                    "name": r.get("Constructor", {}).get("name"),
                },
            }

        results = [_clean_result(r) for r in race.get("Results", [])]
        return {
            "round": race.get("round"),
            "race_name": race.get("raceName"),
            "results": results,
        }


class F1SeasonResultsSensor(F1BaseEntity, SensorEntity):
    """Sensor for entire season's results."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:podium"

    @property
    def state(self):
        races = (
            self.coordinator.data.get("MRData", {})
            .get("RaceTable", {})
            .get("Races", [])
        )
        return len(races)

    @property
    def extra_state_attributes(self):
        races = (
            self.coordinator.data.get("MRData", {})
            .get("RaceTable", {})
            .get("Races", [])
        )

        def _clean_result(r):
            return {
                "number": r.get("number"),
                "position": r.get("position"),
                "points": r.get("points"),
                "status": r.get("status"),
                "driver": {
                    "permanentNumber": r.get("Driver", {}).get("permanentNumber"),
                    "code": r.get("Driver", {}).get("code"),
                    "givenName": r.get("Driver", {}).get("givenName"),
                    "familyName": r.get("Driver", {}).get("familyName"),
                },
                "constructor": {
                    "constructorId": r.get("Constructor", {}).get("constructorId"),
                    "name": r.get("Constructor", {}).get("name"),
                },
            }

        cleaned = []
        for race in races:
            results = [_clean_result(r) for r in race.get("Results", [])]
            cleaned.append(
                {
                    "round": race.get("round"),
                    "race_name": race.get("raceName"),
                    "results": results,
                }
            )
        return {"races": cleaned}


class F1NextSessionSensor(F1BaseEntity, SensorEntity):
    """Sensor providing information about the next session."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:clock-outline"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    def _get_session(self):
        meeting, session = find_next_session(self.coordinator.data or {})
        return meeting, session

    @property
    def unique_id(self):
        meeting, session = self._get_session()
        if meeting and session:
            return f"f1_next_session_{meeting.get('Key')}_{session.get('Key')}"
        return self._attr_unique_id

    @property
    def state(self):
        _, session = self._get_session()
        if session:
            return session.get("start_utc")
        return None

    @property
    def extra_state_attributes(self):
        meeting, session = self._get_session()
        if not session:
            return {}
        attrs = {
            "session_name": session.get("Name"),
            "session_type": session.get("Type"),
            "session_number": session.get("Number"),
            "session_start": session.get("start_utc"),
            "session_end": session.get("end_utc"),
            "path": session.get("Path"),
        }
        if meeting:
            attrs["meeting_name"] = meeting.get("Name")
            attrs["meeting_key"] = meeting.get("Key")
        attrs["session_key"] = session.get("Key")
        return attrs


class F1RaceControlSensor(F1BaseEntity, SensorEntity):
    """Sensor that shows latest race control message."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:flag"

    @property
    def available(self):
        return getattr(self.coordinator, "available", True)

    def _get_session_keys(self):
        meeting, session = find_next_session(
            self.hass.data[DOMAIN][self._entry_id]["session_coordinator"].data or {}
        )
        if meeting and session:
            return meeting.get("Key"), session.get("Key")
        return None, None

    @property
    def unique_id(self):
        mk, sk = self._get_session_keys()
        if mk and sk:
            return f"f1_race_control_{mk}_{sk}"
        return self._attr_unique_id

    @property
    def state(self):
        data = self.coordinator.data or {}
        return data.get("Message") if isinstance(data, dict) else None

    @property
    def extra_state_attributes(self):
        return self.coordinator.data or {}


class FlagStateMachine:
    """Helper class aggregating flag status messages."""

    def __init__(self) -> None:
        self.track_red: bool = False
        self.vsc_active: bool = False
        self.active_yellow_sectors: set[int] = set()
        self.state: str = "green"

    def handle_message(self, msg: dict) -> str:
        """Update state based on a race control message."""
        cat = msg.get("Category")

        if cat == "Flag" and msg.get("Flag") == "RED" and msg.get("Scope") == "Track":
            self.track_red = True
            self.vsc_active = False
            self.active_yellow_sectors.clear()
            self.state = "red"

        elif cat == "SafetyCar" and msg.get("Mode") == "VIRTUAL SAFETY CAR":
            if msg.get("Status") == "DEPLOYED":
                self.vsc_active = True
                self.state = "vsc"
            elif msg.get("Status") in ("ENDED",):
                self.vsc_active = False
                if not self.track_red and not self.active_yellow_sectors:
                    self.state = "green"

        elif (
            cat == "Flag"
            and msg.get("Flag") in ("YELLOW", "DOUBLE YELLOW")
            and msg.get("Scope") == "Sector"
        ):
            if not self.track_red and not self.vsc_active:
                sector = msg.get("Sector")
                if sector is not None:
                    self.active_yellow_sectors.add(int(sector))
                self.state = "yellow"

        elif (
            cat == "Flag"
            and msg.get("Flag") == "CLEAR"
            and msg.get("Scope") == "Sector"
        ):
            sector = msg.get("Sector")
            if sector is not None:
                self.active_yellow_sectors.discard(int(sector))
            if (
                not self.track_red
                and not self.vsc_active
                and not self.active_yellow_sectors
            ):
                self.state = "green"

        elif (
            cat == "Flag"
            and msg.get("Flag") in ("CLEAR", "GREEN")
            and msg.get("Scope") == "Track"
        ):
            self.track_red = False
            self.vsc_active = False
            self.active_yellow_sectors.clear()
            self.state = "green"

        return self.state


class F1FlagSensor(F1BaseEntity, SensorEntity):
    """Aggregated flag status for the entire track."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:flag"
        self._machine = FlagStateMachine()
        self._attr_native_value = self._machine.state

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.coordinator.async_add_listener(self._handle_coordinator_update)
        if self.coordinator.data_list:
            for msg in self.coordinator.data_list:
                if state := self._machine.handle_message(msg):
                    self._attr_native_value = state

    def _handle_coordinator_update(self) -> None:
        for msg in self.coordinator.data_list:
            if state := self._machine.handle_message(msg):
                self._attr_native_value = state
                self.async_write_ha_state()

    @property
    def state(self):
        return self._machine.state

    @property
    def extra_state_attributes(self):
        return {
            "track_red": self._machine.track_red,
            "vsc_active": self._machine.vsc_active,
            "active_yellow_sectors": sorted(self._machine.active_yellow_sectors),
        }
