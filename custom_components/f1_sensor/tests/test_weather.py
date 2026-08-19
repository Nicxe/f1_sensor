"""Tests for the native next-race weather entity and shared coordinator."""

from __future__ import annotations

import logging
from unittest.mock import Mock

from homeassistant.components.weather import DATA_COMPONENT, WeatherEntityFeature
from homeassistant.const import Platform, UnitOfSpeed, UnitOfTemperature
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.setup import async_setup_component
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import weather as weather_platform
from custom_components.f1_sensor.const import (
    CONF_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
)
from custom_components.f1_sensor.entity import default_object_id, set_default_entity_id
from custom_components.f1_sensor.race_weather import (
    DAILY_WEATHER_FIELDS,
    WEATHER_FIELDS,
    F1RaceWeatherCoordinator,
    wmo_condition,
)
from custom_components.f1_sensor.sensor import F1WeatherSensor
from custom_components.f1_sensor.weather import F1RaceWeatherEntity

_LOGGER = logging.getLogger(__name__)


class _Response:
    def __init__(self, payload) -> None:
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, *, params: dict):
        self.calls.append((url, params))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return _Response(response)


def _race(
    *,
    round_number: str = "1",
    race_name: str = "Australian Grand Prix",
    circuit_id: str = "albert_park",
    circuit_name: str = "Albert Park",
    date: str = "2099-03-20",
    time: str = "05:00:00Z",
    latitude: str = "-37.8497",
    longitude: str = "144.968",
) -> dict:
    return {
        "season": "2099",
        "round": round_number,
        "raceName": race_name,
        "date": date,
        "time": time,
        "Circuit": {
            "circuitId": circuit_id,
            "circuitName": circuit_name,
            "Location": {
                "lat": latitude,
                "long": longitude,
                "locality": "Melbourne",
                "country": "Australia",
            },
        },
    }


def _schedule(race: dict | None) -> dict:
    return {
        "MRData": {
            "RaceTable": {
                "Races": [race] if race is not None else [],
            }
        }
    }


def _payload(date: str = "2099-03-20", *, current_temperature: float = 23.2):
    times = [f"{date}T04:00", f"{date}T05:00", f"{date}T06:00"]
    return {
        "utc_offset_seconds": 0,
        "current": {
            "time": times[0],
            "temperature_2m": current_temperature,
            "relative_humidity_2m": 28,
            "precipitation": 0.0,
            "precipitation_probability": 2,
            "cloud_cover": 34,
            "wind_speed_10m": 3.2,
            "wind_direction_10m": 304,
            "wind_gusts_10m": 8.3,
            "visibility": 34840.0,
            "weather_code": 1,
            "is_day": 1,
        },
        "hourly": {
            "time": times,
            "temperature_2m": [20.0, 32.1, 31.4],
            "relative_humidity_2m": [30, 25, 27],
            "precipitation": [0.0, 0.4, 0.1],
            "precipitation_probability": [2, 26, 12],
            "cloud_cover": [34, 83, 70],
            "wind_speed_10m": [3.2, 4.92, 4.3],
            "wind_direction_10m": [304, 199, 205],
            "wind_gusts_10m": [8.3, 13.0, 11.2],
            "visibility": [34840.0, 41580.0, 40000.0],
            "weather_code": [1, 3, 61],
            "is_day": [0, 1, 1],
        },
        "daily": {
            "time": [date],
            "weather_code": [61],
            "temperature_2m_max": [32.1],
            "temperature_2m_min": [20.0],
            "precipitation_sum": [0.5],
            "precipitation_probability_max": [26],
            "wind_speed_10m_max": [4.92],
            "wind_gusts_10m_max": [13.0],
            "wind_direction_10m_dominant": [199],
        },
    }


def _coordinators(hass, session: _Session, race: dict | None = None):
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    entry.add_to_hass(hass)
    race_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="race schedule",
        config_entry=entry,
    )
    race_coordinator.async_set_updated_data(_schedule(race or _race()))
    weather_coordinator = F1RaceWeatherCoordinator(
        hass,
        race_coordinator,
        session=session,  # type: ignore[arg-type]
        config_entry=entry,
    )
    return entry, race_coordinator, weather_coordinator


@pytest.mark.parametrize(
    ("code", "is_daytime", "expected"),
    [
        (0, True, "sunny"),
        (0, False, "clear-night"),
        (2, True, "partlycloudy"),
        (3, True, "cloudy"),
        (45, True, "fog"),
        (61, True, "rainy"),
        (65, True, "pouring"),
        (67, True, "snowy-rainy"),
        (75, True, "snowy"),
        (95, True, "lightning"),
        (99, True, "lightning-rainy"),
        (123, True, "exceptional"),
        (None, True, None),
    ],
)
def test_wmo_condition_mapping(code, is_daytime, expected) -> None:
    assert wmo_condition(code, is_daytime) == expected


@pytest.mark.asyncio
async def test_weather_coordinator_fetches_and_normalizes_race_forecast(hass) -> None:
    session = _Session(_payload())
    _, _, coordinator = _coordinators(hass, session)

    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert len(session.calls) == 1
    _, params = session.calls[0]
    assert params["latitude"] == "-37.8497"
    assert params["longitude"] == "144.968"
    assert params["timezone"] == "auto"
    assert params["forecast_days"] == "16"
    assert set(params["current"].split(",")) == set(WEATHER_FIELDS)
    assert set(params["daily"].split(",")) == set(DAILY_WEATHER_FIELDS)
    assert coordinator.data["current"]["condition"] == "partlycloudy"
    assert coordinator.data["current"]["temperature"] == 23.2
    assert coordinator.data["daily"][0]["condition"] == "rainy"
    assert coordinator.data["daily"][0]["temperature"] == 32.1
    assert coordinator.data["daily"][0]["temperature_low"] == 20.0
    assert len(coordinator.data["twice_daily"]) == 2
    assert coordinator.data["twice_daily"][0]["is_daytime"] is False
    assert coordinator.data["twice_daily"][1]["is_daytime"] is True
    assert coordinator.data["race"]["datetime"] == "2099-03-20T05:00:00+00:00"
    assert coordinator.data["race"]["condition"] == "cloudy"
    assert coordinator.data["race"]["temperature"] == 32.1


@pytest.mark.asyncio
async def test_weather_coordinator_normalizes_circuit_local_time_to_utc(hass) -> None:
    payload = _payload()
    payload["utc_offset_seconds"] = 36000
    session = _Session(payload)
    _, _, coordinator = _coordinators(
        hass,
        session,
        _race(date="2099-03-19", time="19:00:00Z"),
    )

    await coordinator.async_refresh()

    assert coordinator.data["hourly"][1]["datetime"] == ("2099-03-19T19:00:00+00:00")
    assert coordinator.data["daily"][0]["datetime"] == ("2099-03-19T14:00:00+00:00")
    assert coordinator.data["race"]["datetime"] == "2099-03-19T19:00:00+00:00"
    assert len(coordinator.data["twice_daily"]) == 2


@pytest.mark.asyncio
async def test_weather_coordinator_does_not_label_out_of_range_hour_as_race(
    hass,
) -> None:
    session = _Session(_payload("2099-03-01"))
    _, _, coordinator = _coordinators(
        hass,
        session,
        _race(date="2099-03-20"),
    )

    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert len(coordinator.data["hourly"]) == 3
    assert coordinator.data["race"] == {}


@pytest.mark.asyncio
async def test_weather_coordinator_marks_failed_request_unavailable(hass) -> None:
    session = _Session(TimeoutError())
    _, _, coordinator = _coordinators(hass, session)

    await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert coordinator.data is None


@pytest.mark.asyncio
async def test_weather_coordinator_refreshes_when_target_race_changes(hass) -> None:
    session = _Session(
        _payload(),
        _payload("2099-04-02", current_temperature=18.5),
    )
    _, race_coordinator, coordinator = _coordinators(hass, session)
    await coordinator.async_refresh()
    coordinator.async_start()

    race_coordinator.async_set_updated_data(
        _schedule(
            _race(
                round_number="2",
                race_name="Japanese Grand Prix",
                circuit_id="suzuka",
                circuit_name="Suzuka",
                date="2099-04-02",
                latitude="34.8431",
                longitude="136.541",
            )
        )
    )
    await hass.async_block_till_done()

    assert len(session.calls) == 2
    assert coordinator.data["race_key"] == "2099:2:suzuka"
    assert coordinator.data["circuit"]["race_name"] == "Japanese Grand Prix"
    assert coordinator.data["current"]["temperature"] == 18.5
    await coordinator.async_close()

    race_coordinator.async_set_updated_data(
        _schedule(_race(round_number="3", circuit_id="silverstone"))
    )
    await hass.async_block_till_done()
    assert len(session.calls) == 2


@pytest.mark.asyncio
async def test_weather_platform_adds_entity_with_stable_identity(hass) -> None:
    session = _Session(_payload())
    entry, _, coordinator = _coordinators(hass, session)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "race_weather_coordinator": coordinator,
    }
    async_add_entities = Mock()

    await weather_platform.async_setup_entry(hass, entry, async_add_entities)

    async_add_entities.assert_called_once()
    entity = async_add_entities.call_args.args[0][0]
    assert isinstance(entity, F1RaceWeatherEntity)
    assert entity.unique_id == f"{entry.entry_id}_weather_entity"
    assert entity.entity_id == "weather.f1_weather"
    assert entity.has_entity_name is False
    assert entity.device_info is None


@pytest.mark.asyncio
async def test_weather_entity_name_uses_location_fallbacks(hass) -> None:
    session = _Session()
    entry, _, coordinator = _coordinators(hass, session)
    entity = F1RaceWeatherEntity(
        coordinator,
        f"{entry.entry_id}_weather_entity",
        entry.entry_id,
        "F1",
    )

    coordinator.async_set_updated_data(
        {
            "race_key": None,
            "race_start": None,
            "circuit": {"circuit_locality": "Melbourne"},
            "current": {},
            "hourly": [],
            "race": {},
        }
    )
    assert entity.name == "Melbourne"

    coordinator.async_set_updated_data(
        {
            "race_key": None,
            "race_start": None,
            "circuit": {
                "race_name": "Australian Grand Prix",
                "circuit_country": "Australia",
            },
            "current": {},
            "hourly": [],
            "race": {},
        }
    )
    assert entity.name == "Australian Grand Prix · Australia"

    coordinator.async_set_updated_data(
        {
            "race_key": None,
            "race_start": None,
            "circuit": {},
            "current": {},
            "hourly": [],
            "race": {},
        }
    )
    assert entity.name == "Weather"


@pytest.mark.asyncio
async def test_weather_entity_exposes_native_state_and_forecast_service(
    hass, cleanup_test_entity_components
) -> None:
    session = _Session(_payload())
    entry, _, coordinator = _coordinators(hass, session)
    await coordinator.async_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
    }

    entity = F1RaceWeatherEntity(
        coordinator,
        f"{entry.entry_id}_weather_entity",
        entry.entry_id,
        "F1",
    )
    set_default_entity_id(entity, Platform.WEATHER, default_object_id("weather"))

    assert await async_setup_component(hass, "weather", {})
    component = hass.data[DATA_COMPONENT]
    hass.data.setdefault("_f1_sensor_test_entity_components", []).append(component)
    await component.async_add_entities([entity])
    await hass.async_block_till_done()

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == "partlycloudy"
    assert state.attributes["temperature"] == 23.2
    assert state.attributes["temperature_unit"] == UnitOfTemperature.CELSIUS
    assert state.attributes["humidity"] == 28
    assert state.attributes["cloud_coverage"] == 34
    assert state.attributes["visibility"] == 34.84
    assert state.attributes["race_forecast_available"] is True
    assert state.attributes["race_name"] == "Australian Grand Prix"
    assert state.attributes["friendly_name"] == "Albert Park · Melbourne"
    assert entity.supported_features == (
        WeatherEntityFeature.FORECAST_DAILY
        | WeatherEntityFeature.FORECAST_HOURLY
        | WeatherEntityFeature.FORECAST_TWICE_DAILY
    )

    response = await hass.services.async_call(
        "weather",
        "get_forecasts",
        {"entity_id": entity.entity_id, "type": "hourly"},
        blocking=True,
        return_response=True,
    )
    forecast = response[entity.entity_id]["forecast"]
    assert len(forecast) == 3
    assert forecast[1]["datetime"] == "2099-03-20T05:00:00+00:00"
    assert forecast[1]["condition"] == "cloudy"
    assert forecast[1]["temperature"] == 32.1
    assert forecast[1]["precipitation_probability"] == 26
    assert forecast[1]["precipitation"] == 0.4

    response = await hass.services.async_call(
        "weather",
        "get_forecasts",
        {"entity_id": entity.entity_id, "type": "daily"},
        blocking=True,
        return_response=True,
    )
    forecast = response[entity.entity_id]["forecast"]
    assert len(forecast) == 1
    assert forecast[0]["datetime"] == "2099-03-20T00:00:00+00:00"
    assert forecast[0]["condition"] == "rainy"
    assert forecast[0]["temperature"] == 32.1
    assert forecast[0]["templow"] == 20.0
    assert forecast[0]["precipitation"] == 0.5

    response = await hass.services.async_call(
        "weather",
        "get_forecasts",
        {"entity_id": entity.entity_id, "type": "twice_daily"},
        blocking=True,
        return_response=True,
    )
    forecast = response[entity.entity_id]["forecast"]
    assert len(forecast) == 2
    assert forecast[0]["is_daytime"] is False
    assert forecast[0]["temperature"] == 20.0
    assert forecast[1]["is_daytime"] is True
    assert forecast[1]["condition"] == "rainy"
    assert forecast[1]["temperature"] == 32.1
    assert forecast[1]["templow"] == 31.4
    assert forecast[1]["precipitation"] == 0.5


@pytest.mark.asyncio
async def test_weather_entity_converts_native_values_to_us_units(
    hass, cleanup_test_entity_components
) -> None:
    hass.config.units = US_CUSTOMARY_SYSTEM
    session = _Session(_payload())
    entry, _, coordinator = _coordinators(hass, session)
    await coordinator.async_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
    }
    entity = F1RaceWeatherEntity(
        coordinator,
        f"{entry.entry_id}_weather_entity",
        entry.entry_id,
        "F1",
    )
    set_default_entity_id(entity, Platform.WEATHER, default_object_id("weather"))

    assert await async_setup_component(hass, "weather", {})
    component = hass.data[DATA_COMPONENT]
    hass.data.setdefault("_f1_sensor_test_entity_components", []).append(component)
    await component.async_add_entities([entity])
    await hass.async_block_till_done()

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.attributes["temperature"] == 74
    assert state.attributes["temperature_unit"] == UnitOfTemperature.FAHRENHEIT
    assert state.attributes["visibility_unit"] == "mi"
    assert state.attributes["wind_speed_unit"] == UnitOfSpeed.MILES_PER_HOUR

    response = await hass.services.async_call(
        "weather",
        "get_forecasts",
        {"entity_id": entity.entity_id, "type": "daily"},
        blocking=True,
        return_response=True,
    )
    forecast = response[entity.entity_id]["forecast"][0]
    assert forecast["temperature"] == 90
    assert forecast["templow"] == 68
    assert forecast["precipitation"] == 0.02


@pytest.mark.asyncio
async def test_sensor_and_weather_entity_share_one_coordinator_fetch(hass) -> None:
    session = _Session(_payload())
    entry, _, coordinator = _coordinators(hass, session)
    await coordinator.async_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
    }

    weather = F1RaceWeatherEntity(
        coordinator,
        f"{entry.entry_id}_weather_entity",
        entry.entry_id,
        "F1",
    )
    sensor = F1WeatherSensor(
        coordinator,
        f"{entry.entry_id}_weather",
        entry.entry_id,
        "F1",
    )

    assert weather.native_temperature == 23.2
    assert sensor.native_value == 23.2
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_race_schedule_without_future_race_does_not_call_weather_api(
    hass,
) -> None:
    session = _Session()
    _, race_coordinator, coordinator = _coordinators(hass, session)
    race_coordinator.async_set_updated_data(_schedule(None))

    await coordinator.async_refresh()

    assert coordinator.data["current"] == {}
    assert coordinator.data["daily"] == []
    assert coordinator.data["hourly"] == []
    assert coordinator.data["twice_daily"] == []
    assert session.calls == []
