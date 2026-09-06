"""Shared weather data for the circuit hosting the next Formula 1 race."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
import logging
from typing import Any, TypedDict

from aiohttp import ClientError, ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import RACE_SWITCH_GRACE
from .helpers import get_next_race

_LOGGER = logging.getLogger(__name__)

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 16
RACE_FORECAST_TOLERANCE = timedelta(minutes=60)

WEATHER_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "precipitation_probability",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "visibility",
    "weather_code",
    "is_day",
)

DAILY_WEATHER_FIELDS = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "wind_direction_10m_dominant",
)

WMO_CODE_TO_MDI = {
    0: "mdi:weather-sunny",
    1: "mdi:weather-partly-cloudy",
    2: "mdi:weather-partly-cloudy",
    3: "mdi:weather-cloudy",
    45: "mdi:weather-fog",
    48: "mdi:weather-fog",
    51: "mdi:weather-rainy",
    53: "mdi:weather-rainy",
    55: "mdi:weather-rainy",
    56: "mdi:weather-snowy-rainy",
    57: "mdi:weather-snowy-rainy",
    61: "mdi:weather-rainy",
    63: "mdi:weather-rainy",
    65: "mdi:weather-pouring",
    66: "mdi:weather-snowy-rainy",
    67: "mdi:weather-snowy-rainy",
    71: "mdi:weather-snowy",
    73: "mdi:weather-snowy",
    75: "mdi:weather-snowy",
    77: "mdi:weather-snowy",
    80: "mdi:weather-rainy",
    81: "mdi:weather-rainy",
    82: "mdi:weather-pouring",
    85: "mdi:weather-snowy",
    86: "mdi:weather-snowy",
    95: "mdi:weather-lightning",
    96: "mdi:weather-lightning-rainy",
    99: "mdi:weather-lightning-rainy",
}


class WeatherObservation(TypedDict, total=False):
    """Normalized Open-Meteo observation in native units."""

    datetime: str
    temperature: float | None
    temperature_low: float | None
    humidity: float | None
    cloud_coverage: int | None
    precipitation: float | None
    precipitation_probability: int | None
    wind_speed: float | None
    wind_bearing: float | None
    wind_gust_speed: float | None
    visibility: float | None
    weather_code: int | None
    condition: str | None
    is_daytime: bool | None


class RaceWeatherData(TypedDict):
    """Weather snapshot associated with one scheduled race."""

    race_key: str | None
    race_start: str | None
    circuit: dict[str, Any]
    current: WeatherObservation
    daily: list[WeatherObservation]
    hourly: list[WeatherObservation]
    twice_daily: list[WeatherObservation]
    race: WeatherObservation


def _as_float(value: Any) -> float | None:
    """Return a finite numeric value when possible."""
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result in (float("inf"), float("-inf")):
        return None
    return result


def _as_int(value: Any) -> int | None:
    """Return an integer value when possible."""
    number = _as_float(value)
    return round(number) if number is not None else None


def _parse_utc_datetime(value: Any, utc_offset_seconds: int = 0) -> datetime | None:
    """Parse an ISO timestamp and normalize it to UTC."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC) - timedelta(seconds=utc_offset_seconds)
    return parsed.astimezone(UTC)


def _race_start_utc(race: Mapping[str, Any] | None) -> datetime | None:
    """Return the scheduled race start as an aware UTC datetime."""
    if not race or not race.get("date"):
        return None
    time_value = race.get("time") or "00:00:00Z"
    return _parse_utc_datetime(f"{race['date']}T{time_value}")


def _next_race(schedule: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Select the next/current race from a Jolpica schedule payload."""
    if not schedule:
        return None
    races = (
        schedule.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        if isinstance(schedule, Mapping)
        else []
    )
    _, race = get_next_race(
        races,
        grace=RACE_SWITCH_GRACE,
        default_time="00:00:00Z",
    )
    return race


def race_key(race: Mapping[str, Any] | None) -> str | None:
    """Build a stable key for detecting a change of target race."""
    if not race:
        return None
    circuit = race.get("Circuit") or {}
    values = (race.get("season"), race.get("round"), circuit.get("circuitId"))
    if not any(value is not None for value in values):
        return None
    return ":".join("" if value is None else str(value) for value in values)


def wmo_condition(code: Any, is_daytime: bool | None = None) -> str | None:
    """Map a WMO weather interpretation code to a Home Assistant condition."""
    normalized = _as_int(code)
    if normalized is None:
        return None
    if normalized == 0:
        return "clear-night" if is_daytime is False else "sunny"
    if normalized in (1, 2):
        return "partlycloudy"
    if normalized == 3:
        return "cloudy"
    if normalized in (45, 48):
        return "fog"
    if normalized in (51, 53, 55, 61, 63, 80, 81):
        return "rainy"
    if normalized in (65, 82):
        return "pouring"
    if normalized in (56, 57, 66, 67):
        return "snowy-rainy"
    if normalized in (71, 73, 75, 77, 85, 86):
        return "snowy"
    if normalized == 95:
        return "lightning"
    if normalized in (96, 99):
        return "lightning-rainy"
    return "exceptional"


def weather_icon(code: Any, is_daytime: bool | None = None) -> str:
    """Return an MDI icon for a normalized WMO condition."""
    normalized = _as_int(code)
    if normalized == 0 and is_daytime is False:
        return "mdi:weather-night"
    return WMO_CODE_TO_MDI.get(normalized, "mdi:weather-partly-cloudy")


def wind_direction_abbreviation(degrees: Any) -> str | None:
    """Return a 16-point compass abbreviation."""
    value = _as_float(degrees)
    if value is None:
        return None
    directions = (
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
    )
    return directions[round((value % 360) / 22.5) % len(directions)]


def _normalize_observation(
    raw: Mapping[str, Any], timestamp: Any = None, utc_offset_seconds: int = 0
) -> WeatherObservation:
    """Normalize one Open-Meteo current or hourly record."""
    parsed_time = _parse_utc_datetime(timestamp or raw.get("time"), utc_offset_seconds)
    is_day = _as_int(raw.get("is_day"))
    is_daytime = bool(is_day) if is_day in (0, 1) else None
    code = _as_int(raw.get("weather_code"))
    observation: WeatherObservation = {
        "temperature": _as_float(raw.get("temperature_2m")),
        "humidity": _as_float(raw.get("relative_humidity_2m")),
        "cloud_coverage": _as_int(raw.get("cloud_cover")),
        "precipitation": _as_float(raw.get("precipitation")),
        "precipitation_probability": _as_int(raw.get("precipitation_probability")),
        "wind_speed": _as_float(raw.get("wind_speed_10m")),
        "wind_bearing": _as_float(raw.get("wind_direction_10m")),
        "wind_gust_speed": _as_float(raw.get("wind_gusts_10m")),
        "visibility": _as_float(raw.get("visibility")),
        "weather_code": code,
        "condition": wmo_condition(code, is_daytime),
        "is_daytime": is_daytime,
    }
    if parsed_time is not None:
        observation["datetime"] = parsed_time.isoformat()
    return observation


def _hourly_observations(
    hourly: Mapping[str, Any], utc_offset_seconds: int = 0
) -> list[WeatherObservation]:
    """Convert Open-Meteo column arrays into timestamped observations."""
    times = hourly.get("time")
    if not isinstance(times, list):
        return []
    observations: list[WeatherObservation] = []
    for index, timestamp in enumerate(times):
        raw: dict[str, Any] = {}
        for field in WEATHER_FIELDS:
            values = hourly.get(field)
            raw[field] = (
                values[index]
                if isinstance(values, list) and index < len(values)
                else None
            )
        observation = _normalize_observation(raw, timestamp, utc_offset_seconds)
        if "datetime" in observation:
            observations.append(observation)
    return observations


def _daily_observations(
    daily: Mapping[str, Any], utc_offset_seconds: int = 0
) -> list[WeatherObservation]:
    """Convert Open-Meteo daily column arrays into native forecasts."""
    times = daily.get("time")
    if not isinstance(times, list):
        return []
    observations: list[WeatherObservation] = []
    for index, timestamp in enumerate(times):
        raw = {
            field: values[index] if index < len(values) else None
            for field in DAILY_WEATHER_FIELDS
            if isinstance((values := daily.get(field)), list)
        }
        parsed_time = _parse_utc_datetime(timestamp, utc_offset_seconds)
        temperature = _as_float(raw.get("temperature_2m_max"))
        if parsed_time is None or temperature is None:
            continue
        code = _as_int(raw.get("weather_code"))
        observations.append(
            {
                "datetime": parsed_time.isoformat(),
                "temperature": temperature,
                "temperature_low": _as_float(raw.get("temperature_2m_min")),
                "precipitation": _as_float(raw.get("precipitation_sum")),
                "precipitation_probability": _as_int(
                    raw.get("precipitation_probability_max")
                ),
                "wind_speed": _as_float(raw.get("wind_speed_10m_max")),
                "wind_bearing": _as_float(raw.get("wind_direction_10m_dominant")),
                "wind_gust_speed": _as_float(raw.get("wind_gusts_10m_max")),
                "weather_code": code,
                "condition": wmo_condition(code, True),
            }
        )
    return observations


def _average(values: list[float]) -> float | None:
    """Return the arithmetic mean of available values."""
    return sum(values) / len(values) if values else None


def _aggregate_forecast_period(
    observations: list[WeatherObservation], is_daytime: bool
) -> WeatherObservation:
    """Aggregate cached hourly observations into one day or night period."""
    temperatures = [
        value
        for observation in observations
        if (value := _as_float(observation.get("temperature"))) is not None
    ]
    if not temperatures:
        return {}
    precipitation = [
        value
        for observation in observations
        if (value := _as_float(observation.get("precipitation"))) is not None
    ]
    probabilities = [
        value
        for observation in observations
        if (value := _as_int(observation.get("precipitation_probability"))) is not None
    ]
    humidities = [
        value
        for observation in observations
        if (value := _as_float(observation.get("humidity"))) is not None
    ]
    cloud_coverages = [
        value
        for observation in observations
        if (value := _as_float(observation.get("cloud_coverage"))) is not None
    ]
    weather_codes = [
        value
        for observation in observations
        if (value := _as_int(observation.get("weather_code"))) is not None
    ]
    wind_observation = max(
        observations,
        key=lambda observation: _as_float(observation.get("wind_speed")) or 0,
    )
    wind_speeds = [
        value
        for observation in observations
        if (value := _as_float(observation.get("wind_speed"))) is not None
    ]
    wind_gusts = [
        value
        for observation in observations
        if (value := _as_float(observation.get("wind_gust_speed"))) is not None
    ]
    code = max(weather_codes) if weather_codes else None
    return {
        "datetime": observations[0]["datetime"],
        "temperature": max(temperatures),
        "temperature_low": min(temperatures),
        "humidity": _average(humidities),
        "cloud_coverage": _as_int(_average(cloud_coverages)),
        "precipitation": round(sum(precipitation), 3) if precipitation else None,
        "precipitation_probability": max(probabilities) if probabilities else None,
        "wind_speed": max(wind_speeds) if wind_speeds else None,
        "wind_bearing": _as_float(wind_observation.get("wind_bearing")),
        "wind_gust_speed": max(wind_gusts) if wind_gusts else None,
        "weather_code": code,
        "condition": wmo_condition(code, is_daytime),
        "is_daytime": is_daytime,
    }


def _twice_daily_observations(
    hourly: list[WeatherObservation], utc_offset_seconds: int = 0
) -> list[WeatherObservation]:
    """Aggregate hourly data into local day and night forecast periods."""
    grouped: dict[tuple[str, bool], list[WeatherObservation]] = {}
    for observation in hourly:
        timestamp = _parse_utc_datetime(observation.get("datetime"))
        is_daytime = observation.get("is_daytime")
        if timestamp is None or not isinstance(is_daytime, bool):
            continue
        local_date = (timestamp + timedelta(seconds=utc_offset_seconds)).date()
        grouped.setdefault((local_date.isoformat(), is_daytime), []).append(observation)
    return [
        forecast
        for (_, is_daytime), observations in grouped.items()
        if (forecast := _aggregate_forecast_period(observations, is_daytime))
    ]


def _circuit_metadata(race: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build stable next-race metadata for both entity platforms."""
    if not race:
        return {}
    circuit = race.get("Circuit") or {}
    location = circuit.get("Location") or {}
    return {
        "season": race.get("season"),
        "round": race.get("round"),
        "race_name": race.get("raceName"),
        "race_url": race.get("url"),
        "circuit_id": circuit.get("circuitId"),
        "circuit_name": circuit.get("circuitName"),
        "circuit_url": circuit.get("url"),
        "circuit_lat": location.get("lat"),
        "circuit_long": location.get("long"),
        "circuit_locality": location.get("locality"),
        "circuit_country": location.get("country"),
    }


def empty_race_weather_data(
    race: Mapping[str, Any] | None = None,
) -> RaceWeatherData:
    """Return a valid empty snapshot for a missing or changing forecast."""
    race_start = _race_start_utc(race)
    return {
        "race_key": race_key(race),
        "race_start": race_start.isoformat() if race_start else None,
        "circuit": _circuit_metadata(race),
        "current": {},
        "daily": [],
        "hourly": [],
        "twice_daily": [],
        "race": {},
    }


def _closest_race_observation(
    observations: list[WeatherObservation], race_start: datetime | None
) -> WeatherObservation:
    """Return a forecast only when it genuinely covers the race start."""
    if race_start is None:
        return {}
    candidates: list[tuple[timedelta, WeatherObservation]] = []
    for observation in observations:
        timestamp = _parse_utc_datetime(observation.get("datetime"))
        if timestamp is not None:
            candidates.append((abs(timestamp - race_start), observation))
    if not candidates:
        return {}
    difference, observation = min(candidates, key=lambda item: item[0])
    return dict(observation) if difference <= RACE_FORECAST_TOLERANCE else {}


def legacy_weather_observation(
    observation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Adapt normalized data to the established weather sensor attributes."""
    observation = observation or {}
    precipitation = observation.get("precipitation")
    if observation and precipitation is None:
        precipitation = 0
    bearing = observation.get("wind_bearing")
    return {
        "temperature": observation.get("temperature"),
        "temperature_unit": "celsius",
        "humidity": observation.get("humidity"),
        "humidity_unit": "%",
        "cloud_cover": observation.get("cloud_coverage"),
        "cloud_cover_unit": "%",
        "precipitation": precipitation,
        "precipitation_amount_min": precipitation,
        "precipitation_amount_max": precipitation,
        "precipitation_probability": observation.get("precipitation_probability"),
        "precipitation_probability_unit": "%",
        "precipitation_unit": "mm",
        "wind_speed": observation.get("wind_speed"),
        "wind_speed_unit": "m/s",
        "wind_direction": wind_direction_abbreviation(bearing),
        "wind_from_direction_degrees": bearing,
        "wind_from_direction_unit": "degrees",
        "wind_gusts": observation.get("wind_gust_speed"),
        "wind_gusts_unit": "m/s",
        "visibility": observation.get("visibility"),
        "visibility_unit": "m",
        "weather_code": observation.get("weather_code"),
        "weather_source": "open-meteo" if observation else None,
    }


class F1RaceWeatherCoordinator(DataUpdateCoordinator[RaceWeatherData]):
    """Fetch and cache Open-Meteo data for the next race circuit."""

    def __init__(
        self,
        hass: HomeAssistant,
        race_coordinator: DataUpdateCoordinator[Any],
        *,
        session: ClientSession,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="F1 Next Race Weather Coordinator",
            update_interval=timedelta(hours=1),
            config_entry=config_entry,
        )
        self._race_coordinator = race_coordinator
        self._session = session
        self._race_unsub = None
        self._observed_race_key: str | None = None

    def _scheduled_race(self) -> dict[str, Any] | None:
        """Return the race currently selected by the schedule coordinator."""
        data = getattr(self._race_coordinator, "data", None)
        return _next_race(data if isinstance(data, Mapping) else None)

    @callback
    def async_start(self) -> None:
        """Listen for a target race change after initial setup."""
        if self._race_unsub is not None:
            return
        self._observed_race_key = race_key(self._scheduled_race())
        self._race_unsub = self._race_coordinator.async_add_listener(
            self._handle_schedule_update
        )

    async def async_close(self) -> None:
        """Release the schedule listener on config entry unload."""
        if self._race_unsub is not None:
            self._race_unsub()
            self._race_unsub = None
        await super().async_shutdown()

    @callback
    def _handle_schedule_update(self) -> None:
        """Clear old-circuit data immediately and fetch the new circuit."""
        race = self._scheduled_race()
        new_key = race_key(race)
        if new_key == self._observed_race_key:
            return
        self._observed_race_key = new_key
        self.async_set_updated_data(empty_race_weather_data(race))
        self.config_entry.async_create_task(
            self.hass,
            self.async_request_refresh(),
        )

    async def _async_update_data(self) -> RaceWeatherData:
        """Fetch current conditions and cached next-race forecasts."""
        race = self._scheduled_race()
        base_data = empty_race_weather_data(race)
        self._observed_race_key = base_data["race_key"]
        if race is None:
            return base_data

        location = (race.get("Circuit") or {}).get("Location") or {}
        latitude = location.get("lat")
        longitude = location.get("long")
        if latitude is None or longitude is None:
            return base_data

        fields = ",".join(WEATHER_FIELDS)
        params = {
            "latitude": str(latitude),
            "longitude": str(longitude),
            "current": fields,
            "daily": ",".join(DAILY_WEATHER_FIELDS),
            "hourly": fields,
            "wind_speed_unit": "ms",
            "timezone": "auto",
            "forecast_days": str(FORECAST_DAYS),
        }

        try:
            async with asyncio.timeout(10):
                async with self._session.get(
                    OPEN_METEO_FORECAST_URL, params=params
                ) as response:
                    response.raise_for_status()
                    payload = await response.json()
        except (TimeoutError, ClientError, ValueError, TypeError) as err:
            raise UpdateFailed(f"Error fetching race weather: {err}") from err

        if not isinstance(payload, Mapping):
            raise UpdateFailed("Error fetching race weather: invalid response payload")
        current_raw = payload.get("current")
        daily_raw = payload.get("daily")
        hourly_raw = payload.get("hourly")
        if not isinstance(current_raw, Mapping) or not isinstance(hourly_raw, Mapping):
            raise UpdateFailed("Error fetching race weather: missing weather data")

        utc_offset_seconds = _as_int(payload.get("utc_offset_seconds")) or 0
        if not -86400 < utc_offset_seconds < 86400:
            utc_offset_seconds = 0
        current = _normalize_observation(
            current_raw, utc_offset_seconds=utc_offset_seconds
        )
        if current.get("temperature") is None or current.get("condition") is None:
            raise UpdateFailed(
                "Error fetching race weather: incomplete current weather"
            )
        hourly = _hourly_observations(hourly_raw, utc_offset_seconds)
        daily = (
            _daily_observations(daily_raw, utc_offset_seconds)
            if isinstance(daily_raw, Mapping)
            else []
        )
        race_start = _race_start_utc(race)
        return {
            **base_data,
            "current": current,
            "daily": daily,
            "hourly": hourly,
            "twice_daily": _twice_daily_observations(hourly, utc_offset_seconds),
            "race": _closest_race_observation(hourly, race_start),
        }
