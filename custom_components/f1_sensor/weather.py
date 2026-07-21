"""Weather platform for the circuit hosting the next Formula 1 race."""

from __future__ import annotations

from typing import Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    Platform,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .entity import F1BaseEntity, default_object_id, set_default_entity_id
from .race_weather import (
    F1RaceWeatherCoordinator,
    RaceWeatherData,
    WeatherObservation,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the next-race weather entity."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data.get("race_weather_coordinator")
    if not isinstance(coordinator, F1RaceWeatherCoordinator):
        return

    entity = F1RaceWeatherEntity(
        coordinator,
        f"{entry.entry_id}_weather_entity",
        entry.entry_id,
        entry.data.get("sensor_name", "F1"),
    )
    set_default_entity_id(entity, Platform.WEATHER, default_object_id("weather"))
    async_add_entities([entity])


class F1RaceWeatherEntity(F1BaseEntity, WeatherEntity):
    """Represent current weather and forecasts at the next race circuit."""

    _device_category = "race"
    _attr_has_entity_name = False
    _attr_translation_key = "weather"
    _attr_attribution = "Weather data by Open-Meteo.com"
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY
        | WeatherEntityFeature.FORECAST_HOURLY
        | WeatherEntityFeature.FORECAST_TWICE_DAILY
    )
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS

    def __init__(
        self,
        coordinator: F1RaceWeatherCoordinator,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._apply_coordinator_data()

    @property
    def available(self) -> bool:
        """Return whether current conditions are valid for the target race."""
        data = self._coordinator_data
        current = data.get("current", {})
        return (
            super().available
            and current.get("temperature") is not None
            and current.get("condition") is not None
        )

    @property
    def device_info(self) -> None:
        """Keep the destination weather independent of the race device name."""
        return None

    @property
    def name(self) -> str | None:
        """Return a recognizable destination for the next race."""
        circuit = self._coordinator_data.get("circuit", {})
        circuit_name = str(circuit.get("circuit_name") or "").strip()
        race_name = str(circuit.get("race_name") or "").strip()
        locality = str(circuit.get("circuit_locality") or "").strip()
        country = str(circuit.get("circuit_country") or "").strip()

        destination_name = circuit_name or race_name
        destination_place = locality or country
        if destination_name and destination_place:
            if destination_name.casefold() == destination_place.casefold():
                return destination_name
            return f"{destination_name} · {destination_place}"
        return destination_name or destination_place or super().name

    @property
    def _coordinator_data(self) -> RaceWeatherData:
        """Return a shape-safe coordinator snapshot."""
        data = self.coordinator.data
        if isinstance(data, dict):
            return data
        return {
            "race_key": None,
            "race_start": None,
            "circuit": {},
            "current": {},
            "daily": [],
            "hourly": [],
            "twice_daily": [],
            "race": {},
        }

    def _apply_coordinator_data(self) -> None:
        """Copy current native observations into WeatherEntity properties."""
        data = self._coordinator_data
        current = data.get("current", {})
        self._attr_condition = current.get("condition")
        self._attr_native_temperature = current.get("temperature")
        self._attr_humidity = current.get("humidity")
        self._attr_cloud_coverage = current.get("cloud_coverage")
        self._attr_native_wind_speed = current.get("wind_speed")
        self._attr_native_wind_gust_speed = current.get("wind_gust_speed")
        self._attr_wind_bearing = current.get("wind_bearing")
        visibility_m = current.get("visibility")
        self._attr_native_visibility = (
            float(visibility_m) / 1000 if visibility_m is not None else None
        )

        race_forecast = data.get("race", {})
        circuit = data.get("circuit", {})
        self._attr_extra_state_attributes = {
            "race_start": data.get("race_start"),
            "race_forecast_available": bool(race_forecast),
            "season": circuit.get("season"),
            "round": circuit.get("round"),
            "race_name": circuit.get("race_name"),
            "circuit_id": circuit.get("circuit_id"),
            "circuit_name": circuit.get("circuit_name"),
            "circuit_locality": circuit.get("circuit_locality"),
            "circuit_country": circuit.get("circuit_country"),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Write current conditions and push updated forecast subscriptions."""
        self._apply_coordinator_data()
        super()._handle_coordinator_update()
        self.hass.async_create_task(
            self.async_update_listeners(("daily", "hourly", "twice_daily"))
        )

    @staticmethod
    def _native_forecast(
        observation: WeatherObservation,
        *,
        include_temperature_low: bool = False,
        include_is_daytime: bool = False,
    ) -> Forecast | None:
        """Convert one cached observation to Home Assistant forecast data."""
        timestamp = observation.get("datetime")
        if not timestamp or observation.get("temperature") is None:
            return None
        forecast: Forecast = {
            "datetime": timestamp,
            "condition": observation.get("condition"),
            "native_temperature": observation.get("temperature"),
            "humidity": observation.get("humidity"),
            "cloud_coverage": observation.get("cloud_coverage"),
            "native_precipitation": observation.get("precipitation"),
            "precipitation_probability": observation.get("precipitation_probability"),
            "native_wind_speed": observation.get("wind_speed"),
            "native_wind_gust_speed": observation.get("wind_gust_speed"),
            "wind_bearing": observation.get("wind_bearing"),
        }
        if include_temperature_low:
            forecast["native_templow"] = observation.get("temperature_low")
        if include_is_daytime:
            is_daytime = observation.get("is_daytime")
            if not isinstance(is_daytime, bool):
                return None
            forecast["is_daytime"] = is_daytime
        return forecast

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Return the cached daily forecast in native units."""
        return [
            forecast
            for observation in self._coordinator_data.get("daily", [])
            if (
                forecast := self._native_forecast(
                    observation, include_temperature_low=True
                )
            )
        ]

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the cached hourly forecast in native units."""
        return [
            forecast
            for observation in self._coordinator_data.get("hourly", [])
            if (forecast := self._native_forecast(observation))
        ]

    async def async_forecast_twice_daily(self) -> list[Forecast] | None:
        """Return the cached local day and night forecast in native units."""
        return [
            forecast
            for observation in self._coordinator_data.get("twice_daily", [])
            if (
                forecast := self._native_forecast(
                    observation,
                    include_temperature_low=True,
                    include_is_daytime=True,
                )
            )
        ]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose stable race context alongside native weather attributes."""
        return self._attr_extra_state_attributes
