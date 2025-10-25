import datetime
import asyncio
from zoneinfo import ZoneInfo

import async_timeout
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.event import async_call_later
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from timezonefinder import TimezoneFinder

from .const import DOMAIN
from .entity import F1BaseEntity
from .const import LATEST_TRACK_STATUS
from .helpers import normalize_track_status
from logging import getLogger
from homeassistant.util import dt as dt_util

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
    # Normalize legacy/stale sensor keys
    allowed = {
        "next_race",
        "current_season",
        "driver_standings",
        "constructor_standings",
        "weather",
        "track_weather",
        "race_lap_count",
        "driver_list",
        # TEMP_DISABLED: race_order
        # TEMP_DISABLED: driver_favorites
        "last_race_results",
        "season_results",
        "driver_points_progression",
        "constructor_points_progression",
        "race_week",
        "track_status",
        "session_status",
        "current_session",
        "safety_car",
    }
    raw_enabled = entry.data.get("enabled_sensors", [])
    normalized = []
    seen = set()
    for key in raw_enabled:
        if key == "next_session":
            key = "next_race"
        if key in allowed and key not in seen:
            normalized.append(key)
            seen.add(key)
    enabled = normalized

    mapping = {
        "next_race": (F1NextRaceSensor, data["race_coordinator"]),
        "current_season": (F1CurrentSeasonSensor, data["race_coordinator"]),
        "driver_standings": (F1DriverStandingsSensor, data["driver_coordinator"]),
        "constructor_standings": (
            F1ConstructorStandingsSensor,
            data["constructor_coordinator"],
        ),
        "weather": (F1WeatherSensor, data["race_coordinator"]),
        "track_weather": (F1TrackWeatherSensor, data.get("weather_data_coordinator")),
        "race_lap_count": (F1RaceLapCountSensor, data.get("lap_count_coordinator")),
        "last_race_results": (F1LastRaceSensor, data["last_race_coordinator"]),
        "season_results": (F1SeasonResultsSensor, data["season_results_coordinator"]),
        "driver_points_progression": (F1DriverPointsProgressionSensor, data["season_results_coordinator"]),
        "constructor_points_progression": (F1ConstructorPointsProgressionSensor, data["season_results_coordinator"]),
        "track_status": (F1TrackStatusSensor, data.get("track_status_coordinator")),
        "session_status": (F1SessionStatusSensor, data.get("session_status_coordinator")),
        "current_session": (F1CurrentSessionSensor, data.get("session_info_coordinator")),
        # TEMP_DISABLED: "race_order": (F1RaceOrderSensor, data.get("drivers_coordinator")),
        # TEMP_DISABLED: "driver_favorites": (F1FavoriteDriverCollection, data.get("drivers_coordinator")),
        "driver_list": (F1DriverListSensor, data.get("drivers_coordinator")),
    }

    sensors = []
    for key in enabled:
        cls, coord = mapping.get(key, (None, None))
        if cls and coord:
            if cls is F1FavoriteDriverCollection:
                # Expand into multiple driver sensors from option favorite_tlas
                tlas = str(entry.data.get("favorite_tlas", "")).strip()
                tlas_list = [t.strip().upper() for t in tlas.split(",") if t.strip()]
                # Deduplicate and cap to 3
                uniq = []
                seen = set()
                for t in tlas_list:
                    if t not in seen:
                        seen.add(t)
                        uniq.append(t)
                    if len(uniq) >= 3:
                        break
                for tla in uniq:
                    sensors.append(
                        F1DriverLiveSensor(
                            coord,
                            f"{base}_driver_{tla}",
                            f"{entry.entry_id}_driver_{tla}",
                            entry.entry_id,
                            base,
                            tla,
                        )
                    )
            else:
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
        # Derive current precipitation from forecast block (instant does not include precipitation)
        current_forecast_block = (
            times[0].get("data", {}).get("next_1_hours")
            or times[0].get("data", {}).get("next_6_hours")
            or times[0].get("data", {}).get("next_12_hours")
            or {}
        )
        current_precip_details = current_forecast_block.get("details", {})
        current_precip = (
            current_precip_details.get("precipitation_amount")
            if current_precip_details.get("precipitation_amount") is not None
            else (
                current_precip_details.get("precipitation_amount_min")
                if current_precip_details.get("precipitation_amount_min") is not None
                else current_precip_details.get("precipitation_amount_max", 0)
            )
        )
        curr_with_precip = dict(curr)
        curr_with_precip["precipitation_amount"] = current_precip
        # Also expose min/max precipitation from forecast if available; fallback to amount
        _cur_min = current_precip_details.get("precipitation_amount_min")
        _cur_max = current_precip_details.get("precipitation_amount_max")
        curr_with_precip["precipitation_amount_min"] = _cur_min if _cur_min is not None else current_precip
        curr_with_precip["precipitation_amount_max"] = _cur_max if _cur_max is not None else current_precip
        self._current = self._extract(curr_with_precip)
        current_symbol = (
            current_forecast_block
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
                # Prefer 1-hour precipitation at race start, fallback to 6/12-hour blocks
                race_forecast_block = (
                    data_entry.get("next_1_hours")
                    or data_entry.get("next_6_hours")
                    or data_entry.get("next_12_hours")
                    or {}
                )
                race_precip_details = race_forecast_block.get("details", {})
                race_precip = (
                    race_precip_details.get("precipitation_amount")
                    if race_precip_details.get("precipitation_amount") is not None
                    else (
                        race_precip_details.get("precipitation_amount_min")
                        if race_precip_details.get("precipitation_amount_min") is not None
                        else race_precip_details.get("precipitation_amount_max", 0)
                    )
                )
                rd = dict(instant_details)
                rd["precipitation_amount"] = race_precip
                # Also expose min/max precipitation at race time if available; fallback to amount
                _race_min = race_precip_details.get("precipitation_amount_min")
                _race_max = race_precip_details.get("precipitation_amount_max")
                rd["precipitation_amount_min"] = _race_min if _race_min is not None else race_precip
                rd["precipitation_amount_max"] = _race_max if _race_max is not None else race_precip
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
            "precipitation_amount_min": d.get("precipitation_amount_min"),
            "precipitation_amount_max": d.get("precipitation_amount_max"),
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
        self._tf = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._tf = await self.hass.async_add_executor_job(TimezoneFinder)

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
        circuit = race.get("Circuit", {})
        loc = circuit.get("Location", {})
        timezone = self._timezone_from_location(loc.get("lat"), loc.get("long"))
        race_start = self.combine_date_time(race.get("date"), race.get("time"))
        return {
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


class F1DriverPointsProgressionSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor that exposes per-round and cumulative points per driver, including sprint points.

    - State: number of rounds included.
    - Attributes: season, rounds[], drivers{}, series{} for charting.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:chart-line"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._recompute()
        if self._attr_native_value is None:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                try:
                    self._attr_native_value = int(last.state)
                except Exception:
                    self._attr_native_value = None
                attrs = dict(getattr(last, "attributes", {}) or {})
                self._attr_extra_state_attributes = attrs
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        self._recompute()
        self.async_write_ha_state()

    def _get_sprint_results(self) -> list:
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            sprint_coord = reg.get("sprint_results_coordinator")
            if sprint_coord and isinstance(sprint_coord.data, dict):
                return (
                    sprint_coord.data.get("MRData", {})
                    .get("RaceTable", {})
                    .get("Races", [])
                )
        except Exception:
            return []
        return []

    def _get_full_schedule(self) -> list:
        """Return full season schedule (all planned rounds) from race_coordinator if available."""
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            race_coord = reg.get("race_coordinator")
            if race_coord and isinstance(race_coord.data, dict):
                return (
                    race_coord.data.get("MRData", {})
                    .get("RaceTable", {})
                    .get("Races", [])
                )
        except Exception:
            return []
        return []

    def _get_driver_standings(self) -> tuple[dict, int | None]:
        """Return (points_by_code, standings_round) from driver standings coordinator."""
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            coord = reg.get("driver_coordinator")
            points_map: dict[str, float] = {}
            round_num: int | None = None
            if coord and isinstance(coord.data, dict):
                lists = (
                    coord.data.get("MRData", {})
                    .get("StandingsTable", {})
                    .get("StandingsLists", [])
                )
                if lists:
                    try:
                        round_num = int(str(lists[0].get("round") or 0)) if str(lists[0].get("round") or "").isdigit() else None
                    except Exception:
                        round_num = None
                    for item in lists[0].get("DriverStandings", []) or []:
                        drv = item.get("Driver", {}) or {}
                        code = drv.get("code") or drv.get("driverId")
                        if not code:
                            continue
                        try:
                            points_map[code] = float(str(item.get("points") or 0))
                        except Exception:
                            points_map[code] = 0.0
            return points_map, round_num
        except Exception:
            return {}, None

    @staticmethod
    def _to_float(value):
        try:
            if value is None:
                return 0.0
            s = str(value).strip()
            return float(s) if s else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _combine_date_time(date_str, time_str):
        if not date_str:
            return None
        if not time_str:
            time_str = "00:00:00Z"
        dt_str = f"{date_str}T{time_str}".replace("Z", "+00:00")
        try:
            import datetime as _dt
            dt = _dt.datetime.fromisoformat(dt_str)
            return dt.isoformat()
        except Exception:
            return None

    def _recompute(self) -> None:
        data = self.coordinator.data or {}
        races = (
            data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        )
        season = None
        rounds_meta = []
        # Build base per-round points from race Results
        per_round_points: dict[str, list[float]] = {}
        wins_per_round: dict[str, list[int]] = {}
        name_map: dict[str, dict] = {}
        round_numbers: list[int] = []
        for race in races:
            season = season or race.get("season")
            rnd = int(str(race.get("round") or 0)) if str(race.get("round") or "").isdigit() else None
            if rnd is None:
                continue
            round_numbers.append(rnd)
            rounds_meta.append({
                "round": rnd,
                "race_name": race.get("raceName"),
                "date": self._combine_date_time(race.get("date"), race.get("time")),
            })
            # Prepare default 0 entries first
            # We'll fill driver points dynamically as we encounter drivers
            results = race.get("Results", []) or []
            # Determine winner code for wins array
            winner_code = None
            for res in results:
                drv = res.get("Driver", {}) or {}
                code = drv.get("code") or drv.get("driverId")
                if not code:
                    continue
                if res.get("position") == "1" or res.get("positionText") == "1":
                    winner_code = code
                name_map.setdefault(code, {
                    "code": drv.get("code") or None,
                    "driverId": drv.get("driverId"),
                    "name": f"{drv.get('givenName','')} {drv.get('familyName','')}".strip() or drv.get("familyName"),
                })
                # Ensure lists are sized to rnd index (append later)
            # Assign race points
            for res in results:
                drv = res.get("Driver", {}) or {}
                code = drv.get("code") or drv.get("driverId")
                if not code:
                    continue
                pts = self._to_float(res.get("points"))
                per_round_points.setdefault(code, [])
                wins_per_round.setdefault(code, [])
                per_round_points[code].append(pts)
                wins_per_round[code].append(1 if code == winner_code else 0)
            # Normalize length for drivers missing this round
            max_len = len(round_numbers)
            for code in list(per_round_points.keys()):
                while len(per_round_points[code]) < max_len:
                    per_round_points[code].append(0.0)
                while len(wins_per_round[code]) < max_len:
                    wins_per_round[code].append(0)

        # Merge sprint points (by round)
        sprints = self._get_sprint_results()
        round_index = {r: idx for idx, r in enumerate(round_numbers)}
        for sp in sprints or []:
            rnd = int(str(sp.get("round") or 0)) if str(sp.get("round") or "").isdigit() else None
            if rnd is None:
                continue
            if rnd not in round_index:
                # Lägg till sprint-rond som ännu ej har kört huvudlopp
                round_index[rnd] = len(round_numbers)
                round_numbers.append(rnd)
                rounds_meta.append({
                    "round": rnd,
                    "race_name": sp.get("raceName"),
                    "date": self._combine_date_time(sp.get("date"), sp.get("time")),
                })
                for code in list(per_round_points.keys()):
                    per_round_points[code].append(0.0)
                for code in list(wins_per_round.keys()):
                    wins_per_round[code].append(None)
            idx = round_index[rnd]
            results = sp.get("SprintResults") or sp.get("Results") or []
            for res in results:
                drv = res.get("Driver", {}) or {}
                code = drv.get("code") or drv.get("driverId")
                if not code:
                    continue
                pts = self._to_float(res.get("points"))
                per_round_points.setdefault(code, [0.0] * len(round_numbers))
                wins_per_round.setdefault(code, [None] * len(round_numbers))
                # Add sprint points to the same round
                try:
                    per_round_points[code][idx] += pts
                except Exception:
                    pass

        # Align totals with latest standings if they refer to a newer round
        try:
            standings_map, standings_round = self._get_driver_standings()
            if standings_map:
                max_round = max(round_numbers) if round_numbers else None
                # If standings reference a newer round, create it
                new_index_created = False
                if standings_round and (max_round is None or standings_round > max_round):
                    round_numbers.append(standings_round)
                    rounds_meta.append({
                        "round": standings_round,
                        "race_name": None,
                        "date": None,
                    })
                    # pad existing arrays
                    for code in list(per_round_points.keys()):
                        per_round_points[code].append(0.0)
                    for code in list(wins_per_round.keys()):
                        wins_per_round[code].append(None)
                    new_index_created = True
                # Compute and apply deltas
                for code, total_pts in standings_map.items():
                    pts_list = per_round_points.get(code)
                    if not pts_list:
                        continue
                    computed_total = 0.0
                    for v in pts_list:
                        try:
                            computed_total += float(v or 0.0)
                        except Exception:
                            pass
                    delta = round(float(total_pts - computed_total), 3)
                    if delta > 0.0:
                        # Apply delta to last available round (new one if created)
                        if new_index_created:
                            per_round_points[code][-1] = (per_round_points[code][-1] or 0.0) + delta
                        else:
                            per_round_points[code][-1] = (per_round_points[code][-1] or 0.0) + delta
        except Exception:
            pass

        # Återställ: visa endast körda ronder (som vi redan byggt från resultat)

        # Bygg cumulative och totals samt series
        drivers_attr = {}
        series = {"labels": [f"R{r}" for r in round_numbers], "series": []}
        for code, pts_list in per_round_points.items():
            cum = []
            total = 0.0
            for p in pts_list:
                if p is None:
                    cum.append(None)
                else:
                    total += float(p or 0.0)
                    cum.append(total)
            wins = wins_per_round.get(code, [0] * len(pts_list))
            # Sanitize None -> 0 for totals
            safe_wins = [int(w) if isinstance(w, int) else (1 if w is True else 0) for w in wins]
            info = name_map.get(code, {})
            drivers_attr[code] = {
                "identity": {
                    "code": info.get("code") or (code if len(code) <= 3 else None),
                    "driverId": info.get("driverId"),
                    "name": info.get("name"),
                },
                "points_per_round": pts_list,
                "cumulative_points": cum,
                "wins_per_round": wins,
                "totals": {"points": total, "wins": sum(safe_wins)},
            }
            series["series"].append({
                "key": info.get("code") or code,
                "name": info.get("name") or code,
                "data": cum,
            })

        self._attr_native_value = len(round_numbers) if round_numbers else None
        self._attr_extra_state_attributes = {
            "season": season,
            "rounds": rounds_meta,
            "drivers": drivers_attr,
            "series": series,
        }


class F1ConstructorPointsProgressionSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Constructor points per team by round, including sprint; cumulative series for charts."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:chart-line"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._recompute()
        if self._attr_native_value is None:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                try:
                    self._attr_native_value = int(last.state)
                except Exception:
                    self._attr_native_value = None
                self._attr_extra_state_attributes = dict(getattr(last, "attributes", {}) or {})
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        self._recompute()
        self.async_write_ha_state()

    def _get_sprint_results(self) -> list:
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            sprint_coord = reg.get("sprint_results_coordinator")
            if sprint_coord and isinstance(sprint_coord.data, dict):
                return (
                    sprint_coord.data.get("MRData", {})
                    .get("RaceTable", {})
                    .get("Races", [])
                )
        except Exception:
            return []
        return []

    @staticmethod
    def _to_float(value):
        try:
            if value is None:
                return 0.0
            s = str(value).strip()
            return float(s) if s else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _combine_date_time(date_str, time_str):
        if not date_str:
            return None
        if not time_str:
            time_str = "00:00:00Z"
        dt_str = f"{date_str}T{time_str}".replace("Z", "+00:00")
        try:
            import datetime as _dt
            dt = _dt.datetime.fromisoformat(dt_str)
            return dt.isoformat()
        except Exception:
            return None

    def _recompute(self) -> None:
        data = self.coordinator.data or {}
        races = (
            data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        )
        season = None
        rounds_meta = []
        round_numbers: list[int] = []

        # Per round team points and wins
        per_round_points: dict[str, list[float]] = {}
        wins_per_round: dict[str, list[int]] = {}
        team_info: dict[str, dict] = {}  # constructorId -> {name}

        for race in races:
            season = season or race.get("season")
            rnd = int(str(race.get("round") or 0)) if str(race.get("round") or "").isdigit() else None
            if rnd is None:
                continue
            round_numbers.append(rnd)
            rounds_meta.append({
                "round": rnd,
                "race_name": race.get("raceName"),
                "date": self._combine_date_time(race.get("date"), race.get("time")),
            })

            # Aggregate points by constructor this round
            results = race.get("Results", []) or []
            # Identify winning constructor (winner driver position 1)
            winning_constructor = None
            for res in results:
                if str(res.get("position") or res.get("positionText")) == "1":
                    c = (res.get("Constructor") or {}).get("constructorId")
                    winning_constructor = c
                    break
            # Sum per constructor
            per_round_sum: dict[str, float] = {}
            for res in results:
                cons = res.get("Constructor", {}) or {}
                cid = cons.get("constructorId") or cons.get("name")
                if not cid:
                    continue
                team_info.setdefault(cid, {"constructorId": cons.get("constructorId"), "name": cons.get("name")})
                per_round_sum[cid] = per_round_sum.get(cid, 0.0) + self._to_float(res.get("points"))

            # Append to arrays
            for cid, pts in per_round_sum.items():
                per_round_points.setdefault(cid, [])
                wins_per_round.setdefault(cid, [])
                per_round_points[cid].append(pts)
                wins_per_round[cid].append(1 if cid == winning_constructor else 0)
            # Normalize length for teams not present in this round
            max_len = len(round_numbers)
            for cid in list(per_round_points.keys()):
                while len(per_round_points[cid]) < max_len:
                    per_round_points[cid].append(0.0)
                while len(wins_per_round[cid]) < max_len:
                    wins_per_round[cid].append(0)

        # Merge sprint points
        sprints = self._get_sprint_results()
        round_index = {r: idx for idx, r in enumerate(round_numbers)}
        for sp in sprints or []:
            rnd = int(str(sp.get("round") or 0)) if str(sp.get("round") or "").isdigit() else None
            if rnd is None:
                continue
            if rnd not in round_index:
                # Lägg till sprint-rond även om huvudlopp saknas
                round_index[rnd] = len(round_numbers)
                round_numbers.append(rnd)
                rounds_meta.append({
                    "round": rnd,
                    "race_name": sp.get("raceName"),
                    "date": self._combine_date_time(sp.get("date"), sp.get("time")),
                })
                for cid in list(per_round_points.keys()):
                    per_round_points[cid].append(0.0)
                for cid in list(wins_per_round.keys()):
                    wins_per_round[cid].append(None)
            idx = round_index[rnd]
            results = sp.get("SprintResults") or sp.get("Results") or []
            for res in results:
                cons = res.get("Constructor", {}) or {}
                cid = cons.get("constructorId") or cons.get("name")
                if not cid:
                    continue
                team_info.setdefault(cid, {"constructorId": cons.get("constructorId"), "name": cons.get("name")})
                per_round_points.setdefault(cid, [0.0] * len(round_numbers))
                wins_per_round.setdefault(cid, [None] * len(round_numbers))
                try:
                    per_round_points[cid][idx] += self._to_float(res.get("points"))
                except Exception:
                    pass

        # Synka totals med senaste Constructor Standings
        try:
            standings_map, standings_round = self._get_constructor_standings()
            if standings_map:
                max_round = max(round_numbers) if round_numbers else None
                new_index_created = False
                if standings_round and (max_round is None or standings_round > max_round):
                    round_numbers.append(standings_round)
                    rounds_meta.append({
                        "round": standings_round,
                        "race_name": None,
                        "date": None,
                    })
                    for cid in list(per_round_points.keys()):
                        per_round_points[cid].append(0.0)
                    for cid in list(wins_per_round.keys()):
                        wins_per_round[cid].append(None)
                    new_index_created = True
                for cid, total_pts in standings_map.items():
                    pts_list = per_round_points.get(cid)
                    if not pts_list:
                        continue
                    computed_total = 0.0
                    for v in pts_list:
                        try:
                            computed_total += float(v or 0.0)
                        except Exception:
                            pass
                    delta = round(float(total_pts - computed_total), 3)
                    if delta > 0.0:
                        per_round_points[cid][-1] = (per_round_points[cid][-1] or 0.0) + delta
        except Exception:
            pass

        # Build cumulative and series
        teams_attr = {}
        series = {"labels": [f"R{r}" for r in round_numbers], "series": []}
        for cid, pts_list in per_round_points.items():
            cum = []
            total = 0.0
            for p in pts_list:
                total += float(p or 0.0)
                cum.append(total)
            wins = wins_per_round.get(cid, [0] * len(pts_list))
            safe_wins = [int(w) if isinstance(w, int) else (1 if w is True else 0) for w in wins]
            info = team_info.get(cid, {"name": cid})
            teams_attr[cid] = {
                "identity": {"constructorId": info.get("constructorId"), "name": info.get("name")},
                "points_per_round": pts_list,
                "cumulative_points": cum,
                "wins_per_round": wins,
                "totals": {"points": total, "wins": sum(safe_wins)},
            }
            series["series"].append({
                "key": info.get("constructorId") or cid,
                "name": info.get("name") or cid,
                "data": cum,
            })

        self._attr_native_value = len(round_numbers) if round_numbers else None
        self._attr_extra_state_attributes = {
            "season": season,
            "rounds": rounds_meta,
            "constructors": teams_attr,
            "series": series,
        }

    def _get_constructor_standings(self) -> tuple[dict, int | None]:
        """Return (points_by_constructorId, standings_round) from constructor standings coordinator."""
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            coord = reg.get("constructor_coordinator")
            points_map: dict[str, float] = {}
            round_num: int | None = None
            if coord and isinstance(coord.data, dict):
                lists = (
                    coord.data.get("MRData", {})
                    .get("StandingsTable", {})
                    .get("StandingsLists", [])
                )
                if lists:
                    try:
                        round_num = int(str(lists[0].get("round") or 0)) if str(lists[0].get("round") or "").isdigit() else None
                    except Exception:
                        round_num = None
                    for item in lists[0].get("ConstructorStandings", []) or []:
                        cons = item.get("Constructor", {}) or {}
                        cid = cons.get("constructorId") or cons.get("name")
                        if not cid:
                            continue
                        try:
                            points_map[cid] = float(str(item.get("points") or 0))
                        except Exception:
                            points_map[cid] = 0.0
            return points_map, round_num
        except Exception:
            return {}, None


class F1TrackWeatherSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor for live track weather via WeatherData feed.

    State: air temperature (Celsius). Attributes include track temp, humidity, pressure, rainfall,
    wind speed and direction, with units. Restores last value on restart if no live data yet.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:thermometer"
        try:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
        except Exception:
            self._attr_device_class = None
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = "°C"
        self._attr_extra_state_attributes = {}
        self._last_timestamped_dt = None
        self._last_received_utc = None
        # No stale timer: we keep last known value until a new payload arrives

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Initialize from coordinator if available, else restore
        init = self._extract_current()
        if init is not None:
            self._apply_payload(init)
            try:
                getLogger(__name__).debug("TrackWeather: Initialized from coordinator: %s", init)
            except Exception:
                pass
        else:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                # Restore last known state and attributes; do not clear due to age
                self._attr_native_value = self._to_float(last.state)
                attrs = dict(getattr(last, "attributes", {}) or {})
                for k in ("measurement_time", "measurement_age_seconds", "received_at"):
                    attrs.pop(k, None)
                self._attr_extra_state_attributes = attrs
                try:
                    getLogger(__name__).debug("TrackWeather: Restored last state: %s", last.state)
                except Exception:
                    pass
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self._safe_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        return

    def _to_float(self, value):
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        # Accept direct dict from coordinator
        if isinstance(data, dict) and any(k in data for k in ("TrackTemp", "AirTemp", "Humidity")):
            return data
        # Or wrapped inside {"data": {...}}
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            inner = data.get("data")
            if any(k in inner for k in ("TrackTemp", "AirTemp", "Humidity")):
                return inner
        # Fallback: recent history buffer if available
        history = getattr(self.coordinator, "data_list", None)
        if isinstance(history, list) and history:
            last = history[-1]
            if isinstance(last, dict) and any(k in last for k in ("TrackTemp", "AirTemp", "Humidity")):
                return last
        return None

    def _apply_payload(self, raw: dict) -> None:
        # Parse and set state and attributes
        track_temp = self._to_float(raw.get("TrackTemp"))
        air_temp = self._to_float(raw.get("AirTemp"))
        humidity = self._to_float(raw.get("Humidity"))
        pressure = self._to_float(raw.get("Pressure"))
        rainfall = self._to_float(raw.get("Rainfall"))
        wind_dir = self._to_float(raw.get("WindDirection"))
        wind_speed = self._to_float(raw.get("WindSpeed"))

        # Try to extract a timestamp from the payload; if absent, infer measurement time as now
        ts_iso = None
        age_seconds = None
        received_at_update = None
        measurement_inferred = False
        now_utc = dt_util.utcnow()
        try:
            utc_raw = (
                raw.get("Utc")
                or raw.get("utc")
                or raw.get("processedAt")
                or raw.get("timestamp")
            )
            if utc_raw:
                ts = datetime.datetime.fromisoformat(str(utc_raw).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=datetime.timezone.utc)
                ts_iso = ts.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")
                self._last_timestamped_dt = ts
                try:
                    age_seconds = (now_utc - ts).total_seconds()
                except Exception:
                    age_seconds = None
                # Only update 'received_at' when payload carries a timestamp
                received_at_update = now_utc.isoformat(timespec="seconds")
            else:
                # No explicit timestamp; do not assign measurement_time
                ts_iso = None
                measurement_inferred = True
                age_seconds = None
        except Exception:
            ts_iso = None

        try:
            getLogger(__name__).debug(
                "TrackWeather sensor state computed at %s, raw=%s -> air_temp=%s (inferred_ts=%s)",
                now_utc.isoformat(timespec="seconds"),
                raw,
                air_temp,
                measurement_inferred,
            )
        except Exception:
            pass

        self._attr_native_value = air_temp
        self._last_received_utc = now_utc
        self._attr_extra_state_attributes = {
            "air_temperature": air_temp,
            "air_temperature_unit": "celsius",
            "humidity": humidity,
            "humidity_unit": "%",
            "pressure": pressure,
            "pressure_unit": "hPa",
            "rainfall": rainfall,
            "rainfall_unit": "mm",
            "track_temperature": track_temp,
            "track_temperature_unit": "celsius",
            "wind_speed": wind_speed,
            "wind_speed_unit": "m/s",
            "wind_from_direction_degrees": wind_dir,
            "wind_from_direction_unit": "degrees",
            "measurement_inferred": measurement_inferred,
        }

        # No staleness handling: keep last known value until a new payload arrives

    # No stale scheduling required for Track Weather

    # No stale timeout handler

    # Use default attributes storage; do not force placeholders

    def _handle_coordinator_update(self) -> None:
        raw = self._extract_current()
        if raw is None:
            # Keep last known values; just log an update
            try:
                getLogger(__name__).debug(
                    "TrackWeather: No payload on update at %s; keeping previous state",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                )
            except Exception:
                pass
            self._safe_write_ha_state()
            return
        self._apply_payload(raw)
        self._safe_write_ha_state()

    def _safe_write_ha_state(self) -> None:
        try:
            in_loop = False
            try:
                running = asyncio.get_running_loop()
                in_loop = running is self.hass.loop
            except RuntimeError:
                in_loop = False
            if in_loop:
                self.async_write_ha_state()
            else:
                self.schedule_update_ha_state()
        except Exception:
            # Last resort: avoid raising in thread-safety guard
            try:
                self.schedule_update_ha_state()
            except Exception:
                pass


class F1TrackStatusSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Track status sensor independent from flag logic."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:flag-checkered"
        self._attr_native_value = None
        # Advertise as enum sensor so HA UI can suggest valid states
        try:
            self._attr_device_class = SensorDeviceClass.ENUM
        except Exception:
            self._attr_device_class = None
        # Canonical states as produced by normalize_track_status
        self._attr_options = [
            "CLEAR",
            "YELLOW",
            "VSC",
            "VSC_ENDING",
            "SC",
            "RED",
        ]

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Prefer coordinator's latest if present, otherwise restore last state
        initial = self._normalize(self._extract_current())
        if initial is not None:
            self._attr_native_value = initial
            try:
                from logging import getLogger
                getLogger(__name__).debug("TrackStatus: Initialized from coordinator: %s", initial)
            except Exception:
                pass
        else:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                self._attr_native_value = last.state
                try:
                    from logging import getLogger
                    getLogger(__name__).debug("TrackStatus: Restored last state: %s", last.state)
                except Exception:
                    pass
        # Listen for coordinator pushes
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state() 

    def _normalize(self, raw: dict | None) -> str | None:
        return normalize_track_status(raw)

    def _extract_current(self) -> dict | None:
        # Coordinator stores last payload for TrackStatus
        data = self.coordinator.data
        if not data:
            # Fallback: some ws updates may only land in data_list initially
            try:
                hist = getattr(self.coordinator, "data_list", None)
                if isinstance(hist, list) and hist:
                    last = hist[-1]
                    if isinstance(last, dict):
                        return last
            except Exception:  # noqa: BLE001
                pass
            # Final fallback: integration-level latest cache
            try:
                cache = self.hass.data.get(LATEST_TRACK_STATUS)
                if isinstance(cache, dict):
                    return cache
            except Exception:  # noqa: BLE001
                pass
            return None
        # Expect either direct dict or wrapper with 'data'
        if isinstance(data, dict) and ("Status" in data or "Message" in data):
            return data
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict):
            return inner
        return None

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def state(self):
        # Return stored value so restored/initialized state is honored until an update arrives
        return self._attr_native_value

    def _handle_coordinator_update(self) -> None:
        raw = self._extract_current()
        new_state = self._normalize(raw)
        prev = self._attr_native_value
        if prev == new_state:
            return
        try:
            from logging import getLogger
            getLogger(__name__).debug(
                "TrackStatus changed at %s: %s -> %s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                prev,
                new_state,
            )
        except Exception:  # noqa: BLE001
            pass
        self._attr_native_value = new_state
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        return {}


class F1SessionStatusSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor mapping SessionStatus to semantic states for automations."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:timer-play"
        self._attr_native_value = None
        self._started_flag = None
        # Advertise as enum sensor so HA UI can suggest valid states
        try:
            self._attr_device_class = SensorDeviceClass.ENUM
        except Exception:
            self._attr_device_class = None
        # Possible mapped states from _map_status
        self._attr_options = [
            "pre",
            "live",
            "suspended",
            "break",
            "finished",
            "finalised",
            "ended",
        ]

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Initialize from coordinator or restore
        init = self._extract_current()
        if init is not None:
            self._attr_native_value = self._map_status(init)
            try:
                getLogger(__name__).debug("SessionStatus: Initialized from coordinator: raw=%s -> %s", init, self._attr_native_value)
            except Exception:
                pass
        else:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                self._attr_native_value = last.state
                try:
                    getLogger(__name__).debug("SessionStatus: Restored last state: %s", last.state)
                except Exception:
                    pass
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        if not data:
            return None
        if isinstance(data, dict) and ("Status" in data or "Message" in data):
            return data
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict):
            return inner
        return None

    def _map_status(self, raw: dict | None) -> str | None:
        if not raw:
            return None
        # Prefer explicit string in Status, fall back to Message
        message = str(raw.get("Status") or raw.get("Message") or "").strip()
        started_hint = str(raw.get("Started") or "").strip()

        # Stateless mapping based only on this payload.
        if message == "Started":
            return "live"

        if message == "Finished":
            # A qualifying part or the session segment ended.
            # Reset internal memory defensively.
            self._started_flag = None
            return "finished"

        if message == "Finalised":
            # Session finalised without requiring a prior "Finished".
            self._started_flag = None
            return "finalised"

        if message == "Ends":
            # Session officially ends. Clear any sticky state.
            self._started_flag = None
            return "ended"

        if message == "Inactive":
            # Planned qualifying break vs. suspension vs. pre-session
            if started_hint == "Finished":
                # Planned pause between quali segments
                self._started_flag = None
                return "break"
            if started_hint == "Started":
                # Tie-break using latest TrackStatus: if not RED, treat as live
                try:
                    cache = self.hass.data.get(LATEST_TRACK_STATUS)
                    track_state = normalize_track_status(cache) if isinstance(cache, dict) else None
                except Exception:
                    track_state = None
                if track_state and track_state != "RED":
                    return "live"
                # Red flag / suspended while session is considered started
                return "suspended"
            # Not started yet
            return "pre"

        if message == "Aborted":
            # Aborted within an already started session is a suspension-like state
            if started_hint == "Started":
                # Tie-break using latest TrackStatus: if not RED, treat as live
                try:
                    cache = self.hass.data.get(LATEST_TRACK_STATUS)
                    track_state = normalize_track_status(cache) if isinstance(cache, dict) else None
                except Exception:
                    track_state = None
                if track_state and track_state != "RED":
                    return "live"
                return "suspended"
            # Otherwise treat like pre (no live running yet)
            return "pre"

        # Fallback: unknown values behave like pre-session
        return "pre"

    def _handle_coordinator_update(self) -> None:
        raw = self._extract_current()
        new_state = self._map_status(raw)
        prev = self._attr_native_value
        if prev == new_state:
            return
        try:
            getLogger(__name__).debug(
                "SessionStatus changed at %s: %s -> %s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                prev,
                new_state,
            )
        except Exception:  # noqa: BLE001
            pass
        self._attr_native_value = new_state
        self.async_write_ha_state()

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def extra_state_attributes(self):
        return {}


class F1CurrentSessionSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live sensor reporting current session label (e.g., Practice 1, Qualifying/Q1, Sprint Qualifying/SQ1, Sprint, Race).

    - State: compact label string
    - Attributes: full session metadata from SessionInfo (Type, Name, Number, Meeting, Circuit, Start/End),
                  session_part (numeric), resolved_label, and raw payloads; includes live status from SessionStatus if available.
    - Behavior: restores last state on restart; respects global live delay via coordinator.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:calendar-clock"
        try:
            self._attr_device_class = SensorDeviceClass.ENUM
        except Exception:
            self._attr_device_class = None
        self._attr_native_value = None
        # Enumerate possible labels for UI dropdowns in automations
        self._attr_options = [
            "Practice 1",
            "Practice 2",
            "Practice 3",
            "Qualifying",
            "Sprint Qualifying",
            "Sprint",
            "Race",
        ]
        self._status_coordinator = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Wire listeners first so _live_status() reflects current coordinator state
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        # Also listen to SessionStatus so we can clear state when session ends
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            self._status_coordinator = reg.get("session_status_coordinator")
            if self._status_coordinator is not None:
                rem2 = self._status_coordinator.async_add_listener(self._handle_status_update)
                self.async_on_remove(rem2)
        except Exception:
            self._status_coordinator = None

        # Restore last known state immediately; prevents unknown on restart mid-session
        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            # Restore last attributes as well for better end-detection and UI context
            attrs = dict(getattr(last, "attributes", {}) or {})
            self._attr_extra_state_attributes = attrs
            # If saved payload indicates the session ended long ago, clear state on startup
            ended_by_attrs = False
            try:
                end_iso = attrs.get("end") or attrs.get("EndDate")
                if end_iso:
                    end_dt = datetime.datetime.fromisoformat(str(end_iso).replace("Z", "+00:00"))
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=datetime.timezone.utc)
                    now_utc = datetime.datetime.now(datetime.timezone.utc)
                    if now_utc >= (end_dt + datetime.timedelta(minutes=5)):
                        # Also consider live status if available
                        st = str(self._live_status() or "").strip()
                        if st not in ("Started", "Green", "GreenFlag"):
                            ended_by_attrs = True
            except Exception:
                ended_by_attrs = False
            if ended_by_attrs:
                # Keep last label in attributes, but clear current state
                if last.state:
                    try:
                        self._attr_extra_state_attributes = dict(attrs)
                        self._attr_extra_state_attributes.setdefault("last_label", last.state)
                        self._attr_extra_state_attributes["active"] = False
                    except Exception:
                        pass
                self._attr_native_value = None
                try:
                    getLogger(__name__).debug(
                        "CurrentSession: Restored as ended (cleared) based on saved end=%s", attrs.get("end") or attrs.get("EndDate")
                    )
                except Exception:
                    pass
            else:
                self._attr_native_value = last.state
                try:
                    getLogger(__name__).debug("CurrentSession: Restored last state: %s", last.state)
                except Exception:
                    pass

        # Initialize from coordinator if available, but avoid clearing state at startup
        init = self._extract_current()
        if init is not None:
            self._apply_payload(init, allow_clear=False)
            try:
                getLogger(__name__).debug("CurrentSession: Initialized from coordinator (no clear on startup): %s", init)
            except Exception:
                pass

        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        if isinstance(data, dict) and any(k in data for k in ("Type", "Name", "Meeting")):
            return data
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict) and any(k in inner for k in ("Type", "Name", "Meeting")):
            return inner
        # No dedicated history usage; SessionInfo snapshots have no high-frequency heartbeat like others
        return None

    def _resolve_label(self, info: dict) -> tuple[str | None, dict]:
        t = str(info.get("Type") or "").strip()
        name = str(info.get("Name") or "").strip()
        num = info.get("Number")
        try:
            num_i = int(num) if num is not None else None
        except Exception:
            num_i = None

        # Try detect session part from consolidated drivers coordinator if available
        session_part = None
        try:
            drivers_data = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get("drivers_coordinator")
            if drivers_data and hasattr(drivers_data, "data"):
                sd = drivers_data.data or {}
                session = sd.get("session") or {}
                session_part = session.get("part")
        except Exception:
            session_part = None

        label = None
        if t == "Practice":
            label = f"Practice {num_i}" if num_i else (name or "Practice")
        elif t == "Qualifying":
            # Aggregate all Q1/Q2/Q3 into "Qualifying"; treat Sprint Shootout as Sprint Qualifying
            nm = name.lower()
            is_sprint_quali = nm.startswith("sprint qualifying") or nm.startswith("sprint shootout")
            label = "Sprint Qualifying" if is_sprint_quali else "Qualifying"
        elif t == "Race":
            # Some events report Sprint/Sprint Qualifying under Type "Race" via Name
            nm = name.lower()
            if nm.startswith("sprint qualifying") or nm.startswith("sprint shootout"):
                label = "Sprint Qualifying"
            elif nm.startswith("sprint"):
                label = "Sprint"
            else:
                label = name or "Race"
        else:
            # Fallback: use Name then Type
            label = name or t or None

        meta = {
            "type": t or None,
            "name": name or None,
            "number": num_i,
            "session_part": session_part,
        }
        return label, meta

    def _live_status(self) -> str | None:
        try:
            if self._status_coordinator and isinstance(self._status_coordinator.data, dict):
                d = self._status_coordinator.data
                return str(d.get("Status") or d.get("Message") or "").strip()
        except Exception:
            return None
        return None

    def _apply_payload(self, raw: dict, allow_clear: bool = True) -> None:
        label, meta = self._resolve_label(raw or {})
        status = self._live_status()
        # Treat session as ended by explicit status; only use EndDate as a soft fallback with grace
        ended = str(status or "").strip() in ("Finished", "Finalised", "Ends")
        try:
            end_iso = raw.get("EndDate")
            if end_iso and not ended:
                end_dt = datetime.datetime.fromisoformat(str(end_iso).replace("Z", "+00:00"))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=datetime.timezone.utc)
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                # Consider EndDate only if we are well past it and no active/green status is present
                if now_utc >= (end_dt + datetime.timedelta(minutes=5)):
                    st = str(status or "").strip()
                    if st not in ("Started", "Green", "GreenFlag"):
                        ended = True
        except Exception:
            pass
        active = (str(status or "").strip() == "Started")
        desired_state = None
        if label in ("Qualifying", "Sprint Qualifying"):
            desired_state = None if ended else label
        else:
            desired_state = label if active else None
        # On startup we may not yet have live status; avoid clearing to unknown
        if desired_state is None and not allow_clear:
            # Do not substitute the label on startup for ended/inactive sessions; keep prior value only
            desired_state = self._attr_native_value
        self._attr_native_value = desired_state
        attrs = dict(meta)
        # Merge common metadata
        try:
            meeting = raw.get("Meeting") or {}
            circuit = (meeting.get("Circuit") if isinstance(meeting, dict) else None) or {}
            attrs.update(
                {
                    "meeting_key": (meeting or {}).get("Key"),
                    "meeting_name": (meeting or {}).get("Name"),
                    "meeting_location": (meeting or {}).get("Location"),
                    "meeting_country": ((meeting or {}).get("Country") or {}).get("Name"),
                    "circuit_short_name": (circuit or {}).get("ShortName"),
                    "gmt_offset": raw.get("GmtOffset"),
                    "start": raw.get("StartDate"),
                    "end": raw.get("EndDate"),
                }
            )
        except Exception:
            pass
        # Include live status and activity flag
        try:
            attrs["live_status"] = status
            attrs["active"] = active
            if not active and label:
                attrs["last_label"] = label
        except Exception:
            pass
        self._attr_extra_state_attributes = attrs
        try:
            getLogger(__name__).debug(
                "CurrentSession apply: label=%s status=%s ended=%s active=%s",
                label,
                status,
                ended,
                active,
            )
        except Exception:
            pass

    def _handle_coordinator_update(self) -> None:
        raw = self._extract_current()
        if raw is None:
            try:
                getLogger(__name__).debug(
                    "CurrentSession: No payload on update at %s; keeping previous state",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                )
            except Exception:
                pass
            self.async_write_ha_state()
            return
        self._apply_payload(raw)
        self.async_write_ha_state()

    def _handle_status_update(self) -> None:
        # Re-evaluate state based on latest status (may clear on Ends/Finished/Finalised)
        raw = self._extract_current() or {}
        self._apply_payload(raw)
        try:
            getLogger(__name__).debug(
                "CurrentSession: Status update at %s -> state=%s, live_status=%s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                self._attr_native_value,
                self._live_status(),
            )
        except Exception:
            pass
        self.async_write_ha_state()

    @property
    def state(self):
        return self._attr_native_value


class F1RaceLapCountSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live race lap count based on LapCount coordinator.

    - State: current lap (int)
    - Attributes: total_laps (if present), measurement_time, measurement_age_seconds, received_at, raw
    - Restore: Remembers last value/attributes on restart and keeps them until new feed data arrives.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:counter"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_timestamped_dt = None
        self._last_received_utc = None
        self._stale_timer = None
        

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        init = self._extract_current()
        if init is not None:
            self._apply_payload(init)
            try:
                getLogger(__name__).debug("RaceLapCount: Initialized from coordinator: %s", init)
            except Exception:
                pass
        else:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                self._attr_native_value = self._to_int(last.state)
                attrs = dict(getattr(last, "attributes", {}) or {})
                for k in ("measurement_time", "measurement_age_seconds", "received_at"):
                    attrs.pop(k, None)
                self._attr_extra_state_attributes = attrs
                now_utc = dt_util.utcnow()
                try:
                    t_ref = None
                    mt = self._attr_extra_state_attributes.get("measurement_time")
                    if isinstance(mt, str) and mt:
                        t_ref = datetime.datetime.fromisoformat(mt.replace("Z", "+00:00"))
                        if t_ref.tzinfo is None:
                            t_ref = t_ref.replace(tzinfo=datetime.timezone.utc)
                        self._last_timestamped_dt = t_ref
                    if t_ref is None:
                        ra = self._attr_extra_state_attributes.get("received_at")
                        if isinstance(ra, str) and ra:
                            t_ref = datetime.datetime.fromisoformat(ra.replace("Z", "+00:00"))
                            if t_ref.tzinfo is None:
                                t_ref = t_ref.replace(tzinfo=datetime.timezone.utc)
                    if isinstance(t_ref, datetime.datetime):
                        self._last_received_utc = t_ref
                except Exception:
                    pass
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self._safe_write_ha_state()
        # No staleness timer: we keep last known value until new feed data arrives
        

    async def async_will_remove_from_hass(self) -> None:
        try:
            if self._stale_timer:
                self._stale_timer()
                self._stale_timer = None
        except Exception:
            pass
        

    def _to_int(self, value):
        try:
            if value is None:
                return None
            return int(float(value))
        except Exception:
            return None

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        if isinstance(data, dict) and ("CurrentLap" in data or "TotalLaps" in data or "LapCount" in data):
            return data
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict) and ("CurrentLap" in inner or "TotalLaps" in inner or "LapCount" in inner):
            return inner
        hist = getattr(self.coordinator, "data_list", None)
        if isinstance(hist, list) and hist:
            last = hist[-1]
            if isinstance(last, dict) and ("CurrentLap" in last or "TotalLaps" in last or "LapCount" in last):
                return last
        return None

    def _apply_payload(self, raw: dict) -> None:
        curr = self._to_int(raw.get("CurrentLap") if "CurrentLap" in raw else raw.get("LapCount"))
        total = self._to_int(raw.get("TotalLaps"))

        ts_iso = None
        age_seconds = None
        received_at_update = None
        now_utc = dt_util.utcnow()
        try:
            utc_raw = (
                raw.get("Utc")
                or raw.get("utc")
                or raw.get("processedAt")
                or raw.get("timestamp")
            )
            if utc_raw:
                ts = datetime.datetime.fromisoformat(str(utc_raw).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=datetime.timezone.utc)
                ts_iso = ts.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")
                self._last_timestamped_dt = ts
                try:
                    age_seconds = (now_utc - ts).total_seconds()
                except Exception:
                    age_seconds = None
                received_at_update = now_utc.isoformat(timespec="seconds")
        except Exception:
            ts_iso = None

        self._attr_native_value = curr
        self._last_received_utc = now_utc
        self._attr_extra_state_attributes = {
            "total_laps": total,
        }

        # No staleness handling: do not clear state; keep last value until a new payload arrives

    def _schedule_stale_check(self, t_ref: datetime.datetime | None = None, now_utc: datetime.datetime | None = None) -> None:
        try:
            if now_utc is None:
                now_utc = dt_util.utcnow()
            if t_ref is None:
                t_ref = None
                mt = (self._attr_extra_state_attributes or {}).get("measurement_time")
                if isinstance(mt, str) and mt:
                    try:
                        t_ref = datetime.datetime.fromisoformat(mt.replace("Z", "+00:00"))
                        if t_ref.tzinfo is None:
                            t_ref = t_ref.replace(tzinfo=datetime.timezone.utc)
                    except Exception:
                        t_ref = None
                if t_ref is None and isinstance(self._last_timestamped_dt, datetime.datetime):
                    t_ref = self._last_timestamped_dt
                if t_ref is None and isinstance(self._last_received_utc, datetime.datetime):
                    t_ref = self._last_received_utc
            if not isinstance(t_ref, datetime.datetime):
                return
            age = (now_utc - t_ref).total_seconds()
            threshold = 300
            delay = max(0.0, threshold - age)
            if self._stale_timer:
                try:
                    self._stale_timer()
                except Exception:
                    pass
                self._stale_timer = None
            def _cb(_now):
                self._handle_stale_timeout()
            self._stale_timer = async_call_later(self.hass, delay, _cb)
        except Exception:
            pass

    def _handle_stale_timeout(self) -> None:
        try:
            now_utc = dt_util.utcnow()
            t_ref = None
            mt = (self._attr_extra_state_attributes or {}).get("measurement_time")
            if isinstance(mt, str) and mt:
                try:
                    t_ref = datetime.datetime.fromisoformat(mt.replace("Z", "+00:00"))
                    if t_ref.tzinfo is None:
                        t_ref = t_ref.replace(tzinfo=datetime.timezone.utc)
                except Exception:
                    t_ref = None
            if t_ref is None and isinstance(self._last_timestamped_dt, datetime.datetime):
                t_ref = self._last_timestamped_dt
            if t_ref is None and isinstance(self._last_received_utc, datetime.datetime):
                t_ref = self._last_received_utc
            if isinstance(t_ref, datetime.datetime) and (now_utc - t_ref).total_seconds() >= 300:
                self._attr_native_value = None
                attrs = dict(self._attr_extra_state_attributes or {})
                attrs["stale"] = True
                attrs["stale_threshold_seconds"] = 300
                self._attr_extra_state_attributes = attrs
                self._safe_write_ha_state()
        except Exception:
            pass

    def _safe_write_ha_state(self) -> None:
        try:
            import asyncio as _asyncio
            in_loop = False
            try:
                running = _asyncio.get_running_loop()
                in_loop = running is self.hass.loop
            except RuntimeError:
                in_loop = False
            if in_loop:
                self.async_write_ha_state()
            else:
                self.schedule_update_ha_state()
        except Exception:
            try:
                self.schedule_update_ha_state()
            except Exception:
                pass

    def _handle_coordinator_update(self) -> None:
        raw = self._extract_current()
        if raw is None:
            try:
                getLogger(__name__).debug(
                    "RaceLapCount: No payload on update at %s; keeping previous state",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                )
            except Exception:
                pass
            self._safe_write_ha_state()
            return
        self._apply_payload(raw)
        self._safe_write_ha_state()
        

class _Removed:  # keeps line positions stable; no behavior
    pass


class F1RaceOrderSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live race order P1..P20 using consolidated drivers coordinator.

    State: leader TLA. Attributes: ordered list with per-position dicts {position,tla,name,team,team_color}.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:format-list-numbered"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._update_from_coordinator()
        if self._attr_native_value is None:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                self._attr_native_value = last.state
                self._attr_extra_state_attributes = dict(getattr(last, "attributes", {}) or {})
                try:
                    getLogger(__name__).debug("RaceOrder: Restored last state -> %s", last.state)
                except Exception:
                    pass
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        prev_state = self._attr_native_value
        prev_attrs = self._attr_extra_state_attributes
        self._update_from_coordinator()
        if prev_state == self._attr_native_value and prev_attrs == self._attr_extra_state_attributes:
            return
        try:
            getLogger(__name__).debug(
                "RaceOrder: Computed at %s -> leader=%s, n=%s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                self._attr_native_value,
                len((self._attr_extra_state_attributes or {}).get("order", [])),
            )
        except Exception:
            pass
        self.async_write_ha_state()

    def _update_from_coordinator(self) -> None:
        data = self.coordinator.data or {}
        drivers = data.get("drivers", {}) or {}
        leader_rn = data.get("leader_rn")
        leader = drivers.get(leader_rn, {}) if leader_rn else {}
        leader_tla = (leader.get("identity", {}) or {}).get("tla")
        if leader_tla:
            self._attr_native_value = leader_tla
        else:
            try:
                getLogger(__name__).debug("RaceOrder: No leader_tla available yet")
            except Exception:
                pass

        # Build ordered list P1..Pn based on stored 'position'
        grid = []
        for rn, info in drivers.items():
            ident = info.get("identity", {}) or {}
            timing = info.get("timing", {}) or {}
            pos_str = str(timing.get("position") or "").strip()
            try:
                pos = int(pos_str) if pos_str.isdigit() else None
            except Exception:
                pos = None
            if pos is not None:
                grid.append(
                    {
                        "position": pos,
                        "racing_number": ident.get("racing_number") or rn,
                        "tla": ident.get("tla"),
                        "name": ident.get("name"),
                        "team": ident.get("team"),
                        "team_color": ident.get("team_color"),
                    }
                )
        grid.sort(key=lambda x: x["position"])  # ascending P1..P20
        self._attr_extra_state_attributes = {"order": grid}

    @property
    def state(self):
        return self._attr_native_value

class F1FavoriteDriverCollection:
    """Placeholder class only used in mapping to signal expansion into multiple sensors."""

    pass


class F1DriverLiveSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live driver sensor for a specific favorite TLA using consolidated drivers coordinator.

    State: current position (string). Attributes: identity, timing (gap, interval, last/best), status, tyres, laps.
    Freezes on session finished/finalised and restores last known state at startup until data arrives.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name, tla: str):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:car-sports"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._tla = str(tla or "").upper()
        self._frozen = False
        # Write coalescing (min 1s between writes per entity)
        self._last_write_ts: float | None = None
        self._pending_write: bool = False

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._update_from_coordinator()
        if self._attr_native_value is None:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                self._attr_native_value = last.state
                self._attr_extra_state_attributes = dict(getattr(last, "attributes", {}) or {})
                try:
                    getLogger(__name__).debug("DriverLive[%s]: Restored last state -> %s", self._tla, last.state)
                except Exception:
                    pass
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        prev_state = self._attr_native_value
        prev_attrs = self._attr_extra_state_attributes
        self._update_from_coordinator()
        if prev_state == self._attr_native_value and prev_attrs == self._attr_extra_state_attributes:
            return
        try:
            getLogger(__name__).debug(
                "DriverLive[%s]: Computed at %s -> %s",
                self._tla,
                dt_util.utcnow().isoformat(timespec="seconds"),
                self._attr_native_value,
            )
        except Exception:
            pass
        # Coalesce writes to at most 1 Hz
        try:
            import time as _time
            now = _time.time()
            if self._last_write_ts is None or (now - self._last_write_ts) >= 1.0:
                self._last_write_ts = now
                self._safe_write_ha_state()
            else:
                if not self._pending_write:
                    self._pending_write = True
                    delay = max(0.0, 1.0 - (now - self._last_write_ts))
                    from homeassistant.helpers.event import async_call_later as _later
                    def _do_write(_):
                        try:
                            self._last_write_ts = _time.time()
                            self._safe_write_ha_state()
                        finally:
                            self._pending_write = False
                    _later(self.hass, delay, _do_write)
        except Exception:
            self._safe_write_ha_state()

    def _update_from_coordinator(self) -> None:
        data = self.coordinator.data or {}
        self._frozen = bool(data.get("frozen"))
        drivers = data.get("drivers", {})
        # Find by TLA
        selected = None
        for rn, info in drivers.items():
            try:
                if (info.get("identity", {}) or {}).get("tla", "").upper() == self._tla:
                    selected = info
                    break
            except Exception:
                continue
        if not isinstance(selected, dict):
            return
        ident = selected.get("identity", {})
        timing = selected.get("timing", {})
        tyres = selected.get("tyres", {})
        laps = selected.get("laps", {})
        pos = timing.get("position")
        if pos is not None:
            self._attr_native_value = pos
        else:
            try:
                getLogger(__name__).debug("DriverLive[%s]: No position yet", self._tla)
            except Exception:
                pass
        attrs = {
            "tla": ident.get("tla"),
            "name": ident.get("name"),
            "team": ident.get("team"),
            "team_color": ident.get("team_color"),
            # trimmed: interval, last_lap, best_lap, lap_current, lap_total
            "in_pit": timing.get("in_pit"),
            "retired": timing.get("retired"),
            "compound": tyres.get("compound"),
            "stint_laps": tyres.get("stint_laps"),
            "new": tyres.get("new"),
        }
        self._attr_extra_state_attributes = attrs

    @property
    def state(self):
        return self._attr_native_value


class F1DriverListSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live driver list sensor.

    - State: number of drivers in attributes
    - Attributes: drivers: [ { racing_number, tla, name, first_name, last_name, team, team_color, headshot_small, headshot_large, reference } ]
    - Behavior: restores last known state; logs only on change; respects consolidated drivers coordinator.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:account-multiple"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {"drivers": []}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Initialize from coordinator or restore
        self._update_from_coordinator()
        if self._attr_native_value is None:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                try:
                    self._attr_native_value = int(last.state)
                except Exception:
                    self._attr_native_value = None
                try:
                    from logging import getLogger
                    attrs = dict(getattr(last, "attributes", {}) or {})
                    # Drop legacy key 'headshot' if present (top-level or nested per-driver)
                    attrs.pop("headshot", None)
                    drivers_attr = attrs.get("drivers")
                    if isinstance(drivers_attr, list):
                        for drv in drivers_attr:
                            if isinstance(drv, dict):
                                drv.pop("headshot", None)
                    self._attr_extra_state_attributes = attrs
                    getLogger(__name__).debug("DriverList: Restored last state -> %s", last.state)
                except Exception:
                    pass
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        prev_state = self._attr_native_value
        prev_attrs = self._attr_extra_state_attributes
        self._update_from_coordinator()
        if prev_state == self._attr_native_value and prev_attrs == self._attr_extra_state_attributes:
            return
        try:
            from logging import getLogger
            getLogger(__name__).debug(
                "DriverList: Computed at %s -> count=%s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                self._attr_native_value,
            )
        except Exception:
            pass
        # Rate limit writes to once per 60s
        try:
            import time as _time
            lw = getattr(self, "_last_write_ts", None)
            now = _time.time()
            if lw is None or (now - lw) >= 60.0:
                setattr(self, "_last_write_ts", now)
                self._safe_write_ha_state()
            else:
                # Schedule a delayed write at the 60s boundary if not already pending
                pending = getattr(self, "_pending_write", False)
                if not pending:
                    setattr(self, "_pending_write", True)
                    delay = max(0.0, 60.0 - (now - lw)) if lw is not None else 60.0
                    from homeassistant.helpers.event import async_call_later as _later
                    def _do_write(_):
                        try:
                            setattr(self, "_last_write_ts", _time.time())
                            self._safe_write_ha_state()
                        finally:
                            setattr(self, "_pending_write", False)
                    _later(self.hass, delay, _do_write)
        except Exception:
            self._safe_write_ha_state()

    def _update_from_coordinator(self) -> None:
        data = self.coordinator.data or {}
        drivers = (data.get("drivers") or {}) if isinstance(data, dict) else {}
        # Build normalized list sorted by racing number (numeric if possible)
        items = []
        for rn, info in drivers.items():
            ident = (info.get("identity") or {}) if isinstance(info, dict) else {}
            try:
                team_color = ident.get("team_color")
                if isinstance(team_color, str) and team_color and not team_color.startswith("#"):
                    team_color = f"#{team_color}"
            except Exception:
                team_color = ident.get("team_color")
            items.append(
                {
                    "racing_number": ident.get("racing_number") or rn,
                    "tla": ident.get("tla"),
                    "name": ident.get("name"),
                    "first_name": ident.get("first_name"),
                    "last_name": ident.get("last_name"),
                    "team": ident.get("team"),
                    "team_color": team_color,
                    "headshot_small": ident.get("headshot_small") or ident.get("headshot"),
                    "headshot_large": ident.get("headshot_large") or ident.get("headshot"),
                    "reference": ident.get("reference"),
                }
            )
        def _rn_key(v):
            val = str(v.get("racing_number") or "")
            return (int(val) if val.isdigit() else 9999, val)
        items.sort(key=_rn_key)
        self._attr_extra_state_attributes = {"drivers": items}
        self._attr_native_value = len(items)

    @property
    def state(self):
        return self._attr_native_value

