from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import STATE_UNAVAILABLE, UnitOfTemperature
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.json import json_bytes
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.json import json_loads
import pytest

from custom_components.f1_sensor.const import (
    CONF_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
)
from custom_components.f1_sensor.sensor import (
    F1ConstructorPointsProgressionSensor,
    F1ConstructorStandingsSensor,
    F1CurrentSeasonSensor,
    F1DriverListSensor,
    F1DriverPointsProgressionSensor,
    F1DriverPositionsSensor,
    F1DriverStandingsSensor,
    F1PitStopsSensor,
    F1SeasonResultsSensor,
    F1SprintResultsSensor,
    F1WeatherSensor,
)

_LOGGER = logging.getLogger(__name__)
MAX_STATE_ATTRS_BYTES = 16384


class _LiveState:
    def __init__(self, is_live: bool = False) -> None:
        self.is_live = is_live


def _build_coordinator(hass, data: dict) -> DataUpdateCoordinator:
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="test",
        update_method=None,
    )
    coordinator.data = data
    coordinator.available = True
    return coordinator


def _set_entry_context(hass, entry_id: str, *, stream_active: bool = False) -> None:
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(stream_active),
    }


async def _add_sensor_and_get_state(hass, sensor):
    component = EntityComponent(_LOGGER, "sensor", hass)
    await component.async_add_entities([sensor])
    await hass.async_block_till_done()
    state = hass.states.get(sensor.entity_id)
    assert state is not None
    return state


def _recorder_shared_attrs(state) -> tuple[dict, int]:
    unrecorded_attributes = frozenset()
    if state.state_info is not None:
        unrecorded_attributes = state.state_info.get(
            "unrecorded_attributes", frozenset()
        )

    recorded = {
        key: value
        for key, value in state.attributes.items()
        if key not in unrecorded_attributes
    }
    shared_attrs_bytes = json_bytes(recorded)
    return json_loads(shared_attrs_bytes), len(shared_attrs_bytes)


def _build_result_entry(idx: int) -> dict:
    return {
        "number": str(idx),
        "position": str(idx),
        "points": str(max(0, 26 - idx)),
        "status": "Finished",
        "Driver": {
            "driverId": f"driver{idx}",
            "code": f"D{idx:02d}",
            "givenName": f"Driver{idx}",
            "familyName": "Test",
            "permanentNumber": str(idx),
        },
        "Constructor": {
            "constructorId": f"team{((idx - 1) % 10) + 1}",
            "name": f"Team {((idx - 1) % 10) + 1}",
        },
    }


def _build_season_results_data(
    *, season: str = "2026", race_count: int = 3, results_per_race: int = 20
) -> dict:
    races = []
    for race_idx in range(1, race_count + 1):
        races.append(
            {
                "season": season,
                "round": str(race_idx),
                "raceName": f"Race {race_idx}",
                "date": "2026-03-01",
                "time": "14:00:00Z",
                "Results": [
                    _build_result_entry(driver_idx)
                    for driver_idx in range(1, results_per_race + 1)
                ],
            }
        )
    return {"MRData": {"RaceTable": {"season": season, "Races": races}}}


def _build_sprint_results_data(
    *, season: str = "2026", race_count: int = 3, results_per_race: int = 20
) -> dict:
    races = []
    for race_idx in range(1, race_count + 1):
        races.append(
            {
                "season": season,
                "round": str(race_idx),
                "raceName": f"Sprint {race_idx}",
                "SprintResults": [
                    _build_result_entry(driver_idx)
                    for driver_idx in range(1, results_per_race + 1)
                ],
            }
        )
    return {"MRData": {"RaceTable": {"season": season, "Races": races}}}


def _build_driver_positions_data(*, drivers: int = 20, laps: int = 60) -> dict:
    payload = {}
    for idx in range(1, drivers + 1):
        rn = str(idx)
        lap_history = {
            str(lap): f"1:{20 + (lap % 30):02d}.{(idx * lap) % 1000:03d}"
            for lap in range(1, laps + 1)
        }
        payload[rn] = {
            "identity": {
                "racing_number": rn,
                "tla": f"D{idx:02d}",
                "name": f"Driver {idx}",
                "team": f"Team {((idx - 1) % 10) + 1}",
                "team_color": "FF0000",
            },
            "lap_history": {
                "grid_position": str(idx),
                "laps": lap_history,
                "completed_laps": laps,
                "last_recorded_lap": laps,
            },
            "timing": {
                "position": str(idx),
                "in_pit": False,
                "pit_out": False,
                "retired": False,
                "stopped": False,
            },
        }
    return {"drivers": payload, "lap_current": laps, "lap_total": laps}


def _build_pitstops_data(*, cars: int = 20, stops_per_car: int = 8) -> dict:
    payload = {}
    for idx in range(1, cars + 1):
        stops = []
        for stop_idx in range(1, stops_per_car + 1):
            stops.append(
                {
                    "lap": stop_idx * 5,
                    "timestamp": f"2026-03-01T14:{stop_idx:02d}:00Z",
                    "pit_stop_time": f"2.{stop_idx}45",
                    "pit_lane_time": f"21.{stop_idx}2",
                }
            )
        payload[str(idx)] = {
            "count": len(stops),
            "stops": stops,
            "tla": f"D{idx:02d}",
            "name": f"Driver {idx}",
            "team": f"Team {((idx - 1) % 10) + 1}",
        }
    return {
        "total_stops": cars * stops_per_car,
        "cars": payload,
        "last_update": "2026-03-01T14:59:00Z",
    }


@pytest.mark.asyncio
async def test_current_season_sensor_state_attributes_and_availability(hass) -> None:
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="test",
        update_method=None,
    )
    coordinator.data = {
        "MRData": {
            "RaceTable": {
                "season": "2025",
                "Races": [{"round": "1"}, {"round": "2"}],
            }
        }
    }
    coordinator.available = True

    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": None,
    }

    sensor = F1CurrentSeasonSensor(
        coordinator,
        f"{entry_id}_current_season",
        entry_id,
        "F1",
    )

    component = EntityComponent(_LOGGER, "sensor", hass)
    await component.async_add_entities([sensor])
    await hass.async_block_till_done()

    state = hass.states.get(sensor.entity_id)
    assert state is not None
    assert state.state == "2"
    assert state.attributes["season"] == "2025"
    assert len(state.attributes["races"]) == 2
    assert state.state != STATE_UNAVAILABLE

    registry = er.async_get(hass)
    entry = registry.async_get(sensor.entity_id)
    assert entry is not None
    assert entry.unique_id == f"{entry_id}_current_season"

    coordinator.available = False
    sensor.async_write_ha_state()
    await hass.async_block_till_done()

    state = hass.states.get(sensor.entity_id)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


@pytest.mark.asyncio
async def test_current_season_sensor_excludes_races_from_recorder(hass) -> None:
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="test",
        update_method=None,
    )
    coordinator.data = {
        "MRData": {
            "RaceTable": {
                "season": "2026",
                "Races": [{"round": "1"}, {"round": "2"}, {"round": "3"}],
            }
        }
    }
    coordinator.available = True

    entry_id = "test_entry_recorder"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": None,
    }

    sensor = F1CurrentSeasonSensor(
        coordinator,
        f"{entry_id}_current_season",
        entry_id,
        "F1",
    )

    component = EntityComponent(_LOGGER, "sensor", hass)
    await component.async_add_entities([sensor])
    await hass.async_block_till_done()

    state = hass.states.get(sensor.entity_id)
    assert state is not None
    assert "races" in state.attributes
    assert state.state_info is not None
    assert "races" in state.state_info["unrecorded_attributes"]

    shared_attrs, _ = _recorder_shared_attrs(state)

    assert "season" in shared_attrs
    assert "races" not in shared_attrs


@pytest.mark.asyncio
async def test_season_results_sensor_excludes_races_from_recorder(hass) -> None:
    coordinator = _build_coordinator(hass, _build_season_results_data(race_count=2))
    entry_id = "test_entry_season_results"
    _set_entry_context(hass, entry_id)

    sensor = F1SeasonResultsSensor(
        coordinator,
        f"{entry_id}_season_results",
        entry_id,
        "F1",
    )
    state = await _add_sensor_and_get_state(hass, sensor)

    assert "races" in state.attributes
    assert state.state_info is not None
    assert "races" in state.state_info["unrecorded_attributes"]

    shared_attrs, _ = _recorder_shared_attrs(state)
    assert "races" not in shared_attrs


@pytest.mark.asyncio
async def test_sprint_results_sensor_excludes_races_from_recorder(hass) -> None:
    coordinator = _build_coordinator(hass, _build_sprint_results_data(race_count=2))
    entry_id = "test_entry_sprint_results"
    _set_entry_context(hass, entry_id)

    sensor = F1SprintResultsSensor(
        coordinator,
        f"{entry_id}_sprint_results",
        entry_id,
        "F1",
    )
    state = await _add_sensor_and_get_state(hass, sensor)

    assert "races" in state.attributes
    assert state.state_info is not None
    assert "races" in state.state_info["unrecorded_attributes"]

    shared_attrs, _ = _recorder_shared_attrs(state)
    assert "races" not in shared_attrs


@pytest.mark.asyncio
async def test_driver_points_progression_excludes_heavy_attrs_from_recorder(
    hass,
) -> None:
    coordinator = _build_coordinator(hass, _build_season_results_data(race_count=3))
    entry_id = "test_entry_driver_points"
    _set_entry_context(hass, entry_id)

    sensor = F1DriverPointsProgressionSensor(
        coordinator,
        f"{entry_id}_driver_points_progression",
        entry_id,
        "F1",
    )
    state = await _add_sensor_and_get_state(hass, sensor)

    assert "drivers" in state.attributes
    assert "series" in state.attributes
    assert "rounds" in state.attributes
    assert state.state_info is not None
    assert "drivers" in state.state_info["unrecorded_attributes"]
    assert "series" in state.state_info["unrecorded_attributes"]

    shared_attrs, _ = _recorder_shared_attrs(state)
    assert "drivers" not in shared_attrs
    assert "series" not in shared_attrs
    assert "rounds" in shared_attrs


@pytest.mark.asyncio
async def test_constructor_points_progression_excludes_heavy_attrs_from_recorder(
    hass,
) -> None:
    coordinator = _build_coordinator(hass, _build_season_results_data(race_count=3))
    entry_id = "test_entry_constructor_points"
    _set_entry_context(hass, entry_id)

    sensor = F1ConstructorPointsProgressionSensor(
        coordinator,
        f"{entry_id}_constructor_points_progression",
        entry_id,
        "F1",
    )
    state = await _add_sensor_and_get_state(hass, sensor)

    assert "constructors" in state.attributes
    assert "series" in state.attributes
    assert "rounds" in state.attributes
    assert state.state_info is not None
    assert "constructors" in state.state_info["unrecorded_attributes"]
    assert "series" in state.state_info["unrecorded_attributes"]

    shared_attrs, _ = _recorder_shared_attrs(state)
    assert "constructors" not in shared_attrs
    assert "series" not in shared_attrs
    assert "rounds" in shared_attrs


@pytest.mark.asyncio
async def test_pitstops_sensor_excludes_cars_from_recorder(hass) -> None:
    coordinator = _build_coordinator(hass, _build_pitstops_data(stops_per_car=8))
    entry_id = "test_entry_pitstops"
    _set_entry_context(hass, entry_id, stream_active=True)

    sensor = F1PitStopsSensor(
        coordinator,
        f"{entry_id}_pitstops",
        entry_id,
        "F1",
    )
    state = await _add_sensor_and_get_state(hass, sensor)

    assert "cars" in state.attributes
    assert "last_update" in state.attributes
    assert state.state_info is not None
    assert "cars" in state.state_info["unrecorded_attributes"]

    shared_attrs, _ = _recorder_shared_attrs(state)
    assert "cars" not in shared_attrs
    assert "last_update" in shared_attrs


@pytest.mark.asyncio
async def test_driver_positions_sensor_excludes_drivers_from_recorder(hass) -> None:
    coordinator = _build_coordinator(hass, _build_driver_positions_data(laps=20))
    entry_id = "test_entry_driver_positions"
    _set_entry_context(hass, entry_id, stream_active=True)

    sensor = F1DriverPositionsSensor(
        coordinator,
        f"{entry_id}_driver_positions",
        entry_id,
        "F1",
    )
    state = await _add_sensor_and_get_state(hass, sensor)

    assert "drivers" in state.attributes
    assert "total_laps" in state.attributes
    assert state.state_info is not None
    assert "drivers" in state.state_info["unrecorded_attributes"]

    shared_attrs, _ = _recorder_shared_attrs(state)
    assert "drivers" not in shared_attrs
    assert "total_laps" in shared_attrs


@pytest.mark.asyncio
async def test_recorder_payload_size_stays_below_limit_for_large_season_results(
    hass,
) -> None:
    coordinator = _build_coordinator(
        hass, _build_season_results_data(race_count=16, results_per_race=20)
    )
    entry_id = "test_entry_season_results_size"
    _set_entry_context(hass, entry_id)

    sensor = F1SeasonResultsSensor(
        coordinator,
        f"{entry_id}_season_results",
        entry_id,
        "F1",
    )
    state = await _add_sensor_and_get_state(hass, sensor)
    _, shared_attrs_size = _recorder_shared_attrs(state)

    assert shared_attrs_size <= MAX_STATE_ATTRS_BYTES


@pytest.mark.asyncio
async def test_recorder_payload_size_stays_below_limit_for_large_driver_positions(
    hass,
) -> None:
    coordinator = _build_coordinator(hass, _build_driver_positions_data(laps=60))
    entry_id = "test_entry_driver_positions_size"
    _set_entry_context(hass, entry_id, stream_active=True)

    sensor = F1DriverPositionsSensor(
        coordinator,
        f"{entry_id}_driver_positions",
        entry_id,
        "F1",
    )
    state = await _add_sensor_and_get_state(hass, sensor)
    _, shared_attrs_size = _recorder_shared_attrs(state)

    assert shared_attrs_size <= MAX_STATE_ATTRS_BYTES


@pytest.mark.asyncio
async def test_standings_sensor_counts_expandable(hass) -> None:
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="test",
        update_method=None,
    )
    driver_standings = [
        {"position": str(idx), "Driver": {"driverId": f"driver{idx}"}}
        for idx in range(1, 23)
    ]
    constructor_standings = [
        {"position": str(idx), "Constructor": {"constructorId": f"team{idx}"}}
        for idx in range(1, 12)
    ]
    coordinator.data = {
        "MRData": {
            "StandingsTable": {
                "StandingsLists": [
                    {
                        "season": "2026",
                        "round": "1",
                        "DriverStandings": driver_standings,
                        "ConstructorStandings": constructor_standings,
                    }
                ]
            }
        }
    }
    coordinator.available = True

    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": None,
    }

    driver_sensor = F1DriverStandingsSensor(
        coordinator,
        f"{entry_id}_driver_standings",
        entry_id,
        "F1",
    )
    constructor_sensor = F1ConstructorStandingsSensor(
        coordinator,
        f"{entry_id}_constructor_standings",
        entry_id,
        "F1",
    )

    component = EntityComponent(_LOGGER, "sensor", hass)
    await component.async_add_entities([driver_sensor, constructor_sensor])
    await hass.async_block_till_done()

    state = hass.states.get(driver_sensor.entity_id)
    assert state is not None
    assert state.state == "22"
    assert len(state.attributes["driver_standings"]) == 22

    state = hass.states.get(constructor_sensor.entity_id)
    assert state is not None
    assert state.state == "11"
    assert len(state.attributes["constructor_standings"]) == 11


def test_weather_sensor_uses_celsius_unit(hass) -> None:
    coordinator = _build_coordinator(hass, {"MRData": {"RaceTable": {"Races": []}}})
    entry_id = "test_entry"
    _set_entry_context(hass, entry_id)

    sensor = F1WeatherSensor(
        coordinator,
        f"{entry_id}_weather",
        entry_id,
        "F1",
    )

    assert sensor.device_class == SensorDeviceClass.TEMPERATURE
    assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS


@pytest.mark.asyncio
async def test_driver_list_sensor_handles_22_drivers(hass) -> None:
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="test",
        update_method=None,
    )
    drivers = {}
    for idx in range(1, 23):
        rn = str(idx)
        drivers[rn] = {
            "identity": {
                "racing_number": rn,
                "tla": f"D{idx:02d}",
                "name": f"Driver {idx}",
                "team": f"Team {((idx - 1) % 11) + 1}",
                "team_color": "FF0000",
            }
        }
    coordinator.data = {"drivers": drivers}
    coordinator.available = True

    entry_id = "test_entry_drivers"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": None,
    }

    sensor = F1DriverListSensor(
        coordinator,
        f"{entry_id}_driver_list",
        entry_id,
        "F1",
    )

    component = EntityComponent(_LOGGER, "sensor", hass)
    await component.async_add_entities([sensor])
    await hass.async_block_till_done()

    state = hass.states.get(sensor.entity_id)
    assert state is not None
    assert state.state == "22"
    assert len(state.attributes["drivers"]) == 22
