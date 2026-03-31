from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
import time
from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import STATE_UNAVAILABLE, UnitOfTemperature
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.json import json_bytes
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.json import json_loads
import pytest

from custom_components.f1_sensor import F1NextRaceHistoryCoordinator
from custom_components.f1_sensor.const import (
    CONF_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
)
from custom_components.f1_sensor.helpers import get_circuit_map_url
from custom_components.f1_sensor.sensor import (
    F1ConstructorPointsProgressionSensor,
    F1ConstructorStandingsSensor,
    F1CurrentSeasonSensor,
    F1DriverListSensor,
    F1DriverPointsProgressionSensor,
    F1DriverPositionsSensor,
    F1DriverStandingsSensor,
    F1LiveTimingModeSensor,
    F1NextRaceSensor,
    F1PitStopsSensor,
    F1SeasonResultsSensor,
    F1SprintResultsSensor,
    F1TopThreePositionSensor,
    F1WeatherSensor,
)
from custom_components.f1_sensor.signalr import LiveBus

_LOGGER = logging.getLogger(__name__)
MAX_STATE_ATTRS_BYTES = 16384


class _LiveState:
    def __init__(self, is_live: bool = False) -> None:
        self.is_live = is_live


class _TimeoutSession:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, *_args, **_kwargs):
        self.calls += 1
        raise TimeoutError


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


def _build_top_three_data(*, p1: str, p2: str, p3: str, ts: str) -> dict:
    return {
        "withheld": False,
        "lines": [
            {"Position": "1", "Tla": p1, "RacingNumber": "1"},
            {"Position": "2", "Tla": p2, "RacingNumber": "2"},
            {"Position": "3", "Tla": p3, "RacingNumber": "3"},
        ],
        "last_update_ts": ts,
    }


def _build_race(
    *,
    season: str = "2026",
    round_: str = "1",
    race_name: str = "Australian Grand Prix",
    circuit_id: str = "albert_park",
    circuit_name: str = "Albert Park Grand Prix Circuit",
    locality: str = "Melbourne",
    country: str = "Australia",
    date: str = "2026-03-08",
    time: str = "04:00:00Z",
) -> dict:
    return {
        "season": season,
        "round": round_,
        "raceName": race_name,
        "url": f"https://example.com/races/{round_}",
        "date": date,
        "time": time,
        "Circuit": {
            "circuitId": circuit_id,
            "url": f"https://example.com/circuits/{circuit_id}",
            "circuitName": circuit_name,
            "Location": {
                "lat": "-37.8497",
                "long": "144.968",
                "locality": locality,
                "country": country,
            },
        },
        "FirstPractice": {"date": "2026-03-06", "time": "01:30:00Z"},
        "SecondPractice": {"date": "2026-03-06", "time": "05:00:00Z"},
        "ThirdPractice": {"date": "2026-03-07", "time": "01:30:00Z"},
        "Qualifying": {"date": "2026-03-07", "time": "05:00:00Z"},
    }


def _history_driver(
    driver_id: str,
    code: str,
    given_name: str,
    family_name: str,
) -> dict:
    return {
        "driverId": driver_id,
        "code": code,
        "givenName": given_name,
        "familyName": family_name,
    }


def _history_constructor(constructor_id: str, name: str) -> dict:
    return {
        "constructorId": constructor_id,
        "name": name,
    }


def _history_result(
    *,
    position: int,
    driver: dict,
    constructor: dict,
    grid: int,
    status: str = "Finished",
) -> dict:
    return {
        "position": str(position),
        "Driver": driver,
        "Constructor": constructor,
        "grid": str(grid),
        "status": status,
    }


def _history_qualifying(
    *,
    position: int,
    driver: dict,
    constructor: dict,
    q1: str,
    q2: str | None = None,
    q3: str | None = None,
) -> dict:
    result = {
        "position": str(position),
        "Driver": driver,
        "Constructor": constructor,
        "Q1": q1,
    }
    if q2 is not None:
        result["Q2"] = q2
    if q3 is not None:
        result["Q3"] = q3
    return result


def _history_race_entry(
    *,
    season: str,
    round_: str,
    race_name: str,
    date: str,
    circuit_id: str = "red_bull_ring",
    circuit_name: str = "Red Bull Ring",
    locality: str = "Spielberg",
    country: str = "Austria",
    time: str = "13:00:00Z",
) -> dict:
    return {
        "season": season,
        "round": round_,
        "raceName": race_name,
        "url": f"https://example.com/{season}/{round_}",
        "date": date,
        "time": time,
        "Circuit": {
            "circuitId": circuit_id,
            "url": f"https://example.com/circuits/{circuit_id}",
            "circuitName": circuit_name,
            "Location": {
                "lat": "47.2197",
                "long": "14.7647",
                "locality": locality,
                "country": country,
            },
        },
    }


def _build_next_race_history_fixture(
    *, include_previous_season: bool = True
) -> tuple[dict, dict[str, dict]]:
    norris = _history_driver("norris", "NOR", "Lando", "Norris")
    verstappen = _history_driver("max_verstappen", "VER", "Max", "Verstappen")
    piastri = _history_driver("piastri", "PIA", "Oscar", "Piastri")
    leclerc = _history_driver("leclerc", "LEC", "Charles", "Leclerc")
    hamilton = _history_driver("hamilton", "HAM", "Lewis", "Hamilton")
    bottas = _history_driver("bottas", "BOT", "Valtteri", "Bottas")
    sainz = _history_driver("sainz", "SAI", "Carlos", "Sainz")
    perez = _history_driver("perez", "PER", "Sergio", "Perez")

    mclaren = _history_constructor("mclaren", "McLaren")
    red_bull = _history_constructor("red_bull", "Red Bull")
    ferrari = _history_constructor("ferrari", "Ferrari")
    mercedes = _history_constructor("mercedes", "Mercedes")

    historical_races = [
        {
            "race": _history_race_entry(
                season="2025",
                round_="11",
                race_name="Austrian GP",
                date="2025-06-29",
            ),
            "results": [
                _history_result(position=1, driver=norris, constructor=mclaren, grid=2),
                _history_result(
                    position=2, driver=verstappen, constructor=red_bull, grid=1
                ),
                _history_result(
                    position=3, driver=piastri, constructor=mclaren, grid=3
                ),
                _history_result(
                    position=4, driver=leclerc, constructor=ferrari, grid=4
                ),
                _history_result(
                    position=5,
                    driver=hamilton,
                    constructor=mercedes,
                    grid=5,
                    status="Engine",
                ),
            ],
            "qualifying": [
                _history_qualifying(
                    position=1,
                    driver=piastri,
                    constructor=mclaren,
                    q1="1:05.000",
                    q2="1:04.800",
                    q3="1:04.500",
                ),
                _history_qualifying(
                    position=2,
                    driver=verstappen,
                    constructor=red_bull,
                    q1="1:05.100",
                    q2="1:04.900",
                    q3="1:04.600",
                ),
            ],
        },
        {
            "race": _history_race_entry(
                season="2024",
                round_="10",
                race_name="Styrian Grand Prix",
                date="2024-06-30",
            ),
            "results": [
                _history_result(
                    position=1, driver=verstappen, constructor=red_bull, grid=1
                ),
                _history_result(position=2, driver=norris, constructor=mclaren, grid=2),
                _history_result(
                    position=3, driver=leclerc, constructor=ferrari, grid=4
                ),
                _history_result(
                    position=4, driver=hamilton, constructor=mercedes, grid=5
                ),
                _history_result(
                    position=5,
                    driver=perez,
                    constructor=red_bull,
                    grid=3,
                    status="Disqualified",
                ),
            ],
            "qualifying": [
                _history_qualifying(
                    position=1,
                    driver=norris,
                    constructor=mclaren,
                    q1="1:05.200",
                    q2="1:05.000",
                    q3="1:04.700",
                ),
            ],
        },
        {
            "race": _history_race_entry(
                season="2023",
                round_="9",
                race_name="Austrian Grand Prix",
                date="2023-07-02",
            ),
            "results": [
                _history_result(
                    position=1, driver=verstappen, constructor=red_bull, grid=1
                ),
                _history_result(
                    position=2,
                    driver=hamilton,
                    constructor=mercedes,
                    grid=2,
                    status="+1 Lap",
                ),
                _history_result(
                    position=3,
                    driver=norris,
                    constructor=mclaren,
                    grid=4,
                    status="+2 Laps",
                ),
                _history_result(
                    position=4, driver=leclerc, constructor=ferrari, grid=3
                ),
                _history_result(
                    position=5,
                    driver=sainz,
                    constructor=ferrari,
                    grid=5,
                    status="Engine",
                ),
            ],
            "qualifying": [
                _history_qualifying(
                    position=1,
                    driver=verstappen,
                    constructor=red_bull,
                    q1="1:05.300",
                    q2="1:05.100",
                    q3="1:04.800",
                ),
            ],
        },
        {
            "race": _history_race_entry(
                season="2022",
                round_="11",
                race_name="Austrian GP",
                date="2022-07-10",
            ),
            "results": [
                _history_result(
                    position=1, driver=leclerc, constructor=ferrari, grid=1
                ),
                _history_result(
                    position=2,
                    driver=verstappen,
                    constructor=red_bull,
                    grid=2,
                    status="Accident",
                ),
                _history_result(
                    position=3, driver=hamilton, constructor=mercedes, grid=4
                ),
                _history_result(
                    position=4,
                    driver=norris,
                    constructor=mclaren,
                    grid=5,
                    status="+1 Lap",
                ),
                _history_result(position=5, driver=sainz, constructor=ferrari, grid=3),
            ],
            "qualifying": [
                _history_qualifying(
                    position=1,
                    driver=leclerc,
                    constructor=ferrari,
                    q1="1:05.400",
                    q2="1:05.200",
                    q3="1:04.900",
                ),
            ],
        },
        {
            "race": _history_race_entry(
                season="2021",
                round_="9",
                race_name="Styria Grand Prix",
                date="2021-06-27",
            ),
            "results": [
                _history_result(
                    position=1, driver=hamilton, constructor=mercedes, grid=4
                ),
                _history_result(
                    position=2, driver=verstappen, constructor=red_bull, grid=1
                ),
                _history_result(
                    position=3, driver=bottas, constructor=mercedes, grid=2
                ),
                _history_result(
                    position=4,
                    driver=leclerc,
                    constructor=ferrari,
                    grid=3,
                    status="+1 Lap",
                ),
                _history_result(
                    position=5,
                    driver=norris,
                    constructor=mclaren,
                    grid=5,
                    status="Collision",
                ),
            ],
            "qualifying": [
                _history_qualifying(
                    position=1,
                    driver=hamilton,
                    constructor=mercedes,
                    q1="1:05.500",
                    q2="1:05.300",
                    q3="1:05.000",
                ),
            ],
        },
        {
            "race": _history_race_entry(
                season="2020",
                round_="1",
                race_name="Austrian Grand Prix",
                date="2020-07-05",
            ),
            "results": [
                _history_result(
                    position=1, driver=bottas, constructor=mercedes, grid=1
                ),
                _history_result(
                    position=2, driver=verstappen, constructor=red_bull, grid=2
                ),
                _history_result(
                    position=3, driver=hamilton, constructor=mercedes, grid=3
                ),
                _history_result(
                    position=4, driver=leclerc, constructor=ferrari, grid=4
                ),
                _history_result(position=5, driver=norris, constructor=mclaren, grid=5),
            ],
            "qualifying": [
                _history_qualifying(
                    position=1,
                    driver=bottas,
                    constructor=mercedes,
                    q1="1:05.600",
                    q2="1:05.400",
                    q3="1:05.100",
                ),
            ],
        },
        {
            "race": _history_race_entry(
                season="2019",
                round_="9",
                race_name="Austrian Grand Prix",
                date="2019-06-30",
            ),
            "results": [
                _history_result(
                    position=1, driver=leclerc, constructor=ferrari, grid=1
                ),
            ],
            "qualifying": [
                _history_qualifying(
                    position=1,
                    driver=leclerc,
                    constructor=ferrari,
                    q1="1:05.700",
                    q2="1:05.500",
                    q3="1:05.200",
                ),
            ],
        },
    ]
    if not include_previous_season:
        historical_races = [
            entry for entry in historical_races if entry["race"]["season"] != "2025"
        ]

    upcoming_race = _build_race(
        season="2026",
        round_="11",
        race_name="Austrian Grand Prix",
        circuit_id="red_bull_ring",
        circuit_name="Red Bull Ring",
        locality="Spielberg",
        country="Austria",
        date="2026-06-28",
        time="13:00:00Z",
    )
    upcoming_circuit_entry = _history_race_entry(
        season="2026",
        round_="11",
        race_name="Austrian Grand Prix",
        date="2026-06-28",
    )

    base_url = "https://api.jolpi.ca/ergast/f1"
    payloads: dict[str, dict] = {
        f"{base_url}/circuits/red_bull_ring/races.json?limit=100": {
            "MRData": {
                "RaceTable": {
                    "Races": [entry["race"] for entry in historical_races]
                    + [upcoming_circuit_entry]
                }
            }
        },
        f"{base_url}/circuits/red_bull_ring/results/1.json?limit=100": {
            "MRData": {
                "RaceTable": {
                    "Races": [
                        {
                            **entry["race"],
                            "Results": [entry["results"][0]],
                        }
                        for entry in historical_races
                    ]
                }
            }
        },
    }

    latest_five = [
        entry
        for entry in historical_races
        if entry["race"]["season"] in {"2025", "2024", "2023", "2022", "2021"}
    ]
    if not include_previous_season:
        latest_five = [
            entry
            for entry in historical_races
            if entry["race"]["season"] in {"2024", "2023", "2022", "2021", "2020"}
        ]

    for entry in latest_five:
        season = entry["race"]["season"]
        round_ = entry["race"]["round"]
        payloads[f"{base_url}/{season}/{round_}/results.json"] = {
            "MRData": {
                "RaceTable": {"Races": [{**entry["race"], "Results": entry["results"]}]}
            }
        }
        payloads[f"{base_url}/{season}/{round_}/qualifying.json"] = {
            "MRData": {
                "RaceTable": {
                    "Races": [
                        {
                            **entry["race"],
                            "QualifyingResults": entry["qualifying"],
                        }
                    ]
                }
            }
        }

    return upcoming_race, payloads


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


def test_get_circuit_map_url_prefers_2026_detailed_maps() -> None:
    assert (
        get_circuit_map_url("albert_park", "2026")
        == "https://media.formula1.com/image/upload/f_auto,q_auto/common/f1/2026/track/2026trackmelbournedetailed.webp"
    )
    assert (
        get_circuit_map_url("madring", "2026")
        == "https://media.formula1.com/image/upload/f_auto,q_auto/common/f1/2026/track/2026trackmadringdetailed.webp"
    )
    assert (
        get_circuit_map_url("imola", "2026")
        == "https://media.formula1.com/image/upload/f_auto,q_auto/content/dam/fom-website/2018-redesign-assets/Circuit%20maps%2016x9/Emilia_Romagna_Circuit.webp"
    )


@pytest.mark.asyncio
async def test_next_race_sensor_uses_2026_detailed_circuit_map(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.helpers.dt_util.utcnow",
        lambda: datetime(2026, 3, 10, tzinfo=UTC),
    )
    coordinator = _build_coordinator(
        hass,
        {"MRData": {"RaceTable": {"Races": [_build_race(date="2026-03-15")]}}},
    )
    entry_id = "test_entry_next_race"
    _set_entry_context(hass, entry_id)

    sensor = F1NextRaceSensor(
        coordinator,
        f"{entry_id}_next_race",
        entry_id,
        "F1",
    )
    state = await _add_sensor_and_get_state(hass, sensor)

    assert (
        state.attributes["circuit_map_url"]
        == "https://media.formula1.com/image/upload/f_auto,q_auto/common/f1/2026/track/2026trackmelbournedetailed.webp"
    )


@pytest.mark.asyncio
async def test_next_race_sensor_exposes_circuit_history_attrs(
    hass, monkeypatch
) -> None:
    next_race, payloads = _build_next_race_history_fixture()
    race_coordinator = _build_coordinator(
        hass,
        {"MRData": {"RaceTable": {"Races": [next_race]}}},
    )
    entry_id = "test_entry_next_race_history"
    _set_entry_context(hass, entry_id)

    async def _fake_fetch_url(_self, url):
        if url not in payloads:
            raise AssertionError(f"Unexpected URL: {url}")
        return payloads[url]

    monkeypatch.setattr(
        F1NextRaceHistoryCoordinator,
        "_fetch_url",
        _fake_fetch_url,
    )

    history_coordinator = F1NextRaceHistoryCoordinator(
        hass,
        race_coordinator,
        "Test Next Race History Coordinator",
        session=MagicMock(),
        user_agent="ua",
        cache={},
        inflight={},
        ttl_seconds=3600,
        persist_map={},
        persist_save=MagicMock(),
    )
    history_coordinator.data = await history_coordinator._async_update_data()
    history_coordinator.available = True
    hass.data[DOMAIN][entry_id]["next_race_history_coordinator"] = history_coordinator

    sensor = F1NextRaceSensor(
        race_coordinator,
        f"{entry_id}_next_race",
        entry_id,
        "F1",
    )
    state = await _add_sensor_and_get_state(hass, sensor)

    assert state.attributes["defending_winner"]["driver_name"] == "Lando Norris"
    assert state.attributes["defending_winner"]["season"] == "2025"
    assert state.attributes["defending_pole_sitter"]["driver_name"] == "Oscar Piastri"
    assert [item["season"] for item in state.attributes["last_5_winners"]] == [
        "2025",
        "2024",
        "2023",
        "2022",
        "2021",
    ]
    assert [item["race_name"] for item in state.attributes["last_5_winners"][:2]] == [
        "Austrian GP",
        "Styrian Grand Prix",
    ]
    assert [item["driver_name"] for item in state.attributes["last_5_poles"][:3]] == [
        "Oscar Piastri",
        "Lando Norris",
        "Max Verstappen",
    ]
    assert [
        item["driver_name"] for item in state.attributes["top_5_driver_wins_here"]
    ] == [
        "Max Verstappen",
        "Charles Leclerc",
        "Lando Norris",
        "Lewis Hamilton",
        "Valtteri Bottas",
    ]
    assert [
        item["constructor_name"]
        for item in state.attributes["top_5_constructor_wins_here"]
    ] == ["Red Bull", "Ferrari", "Mercedes", "McLaren"]
    assert state.attributes["first_f1_race_here"] == {
        "season": "2019",
        "round": "9",
        "race_name": "Austrian Grand Prix",
        "date": "2019-06-30",
        "url": "https://example.com/2019/9",
    }
    assert state.attributes["races_held_here"] == 7
    assert state.attributes["last_year_podium"]["season"] == "2025"
    assert [
        item["driver_name"] for item in state.attributes["last_year_podium"]["podium"]
    ] == ["Lando Norris", "Max Verstappen", "Oscar Piastri"]
    assert state.attributes["dnf_rate_last_5"] == 20.0
    assert state.attributes["dnf_rate_last_5_stats"]["starter_count"] == 25
    assert state.attributes["dnf_rate_last_5_stats"]["finisher_count"] == 20
    assert state.attributes["dnf_rate_last_5_stats"]["dnf_count"] == 5
    assert state.attributes["pole_to_win_conversion_last_5"] == 60.0
    assert (
        state.attributes["pole_to_win_conversion_last_5_stats"]["pole_to_win_count"]
        == 3
    )
    assert state.attributes["pole_to_win_conversion_last_5_stats"]["per_race"][0] == {
        "season": "2025",
        "round": "11",
        "race_name": "Austrian GP",
        "winner_name": "Lando Norris",
        "winner_grid": "2",
        "converted": False,
    }
    assert state.state_info is not None
    assert "last_5_winners" in state.state_info["unrecorded_attributes"]
    assert "last_5_poles" in state.state_info["unrecorded_attributes"]
    assert "top_5_driver_wins_here" in state.state_info["unrecorded_attributes"]
    assert "top_5_constructor_wins_here" in state.state_info["unrecorded_attributes"]
    assert "dnf_rate_last_5_stats" in state.state_info["unrecorded_attributes"]
    assert (
        "pole_to_win_conversion_last_5_stats"
        in state.state_info["unrecorded_attributes"]
    )

    shared_attrs, shared_attrs_size = _recorder_shared_attrs(state)
    assert shared_attrs_size <= MAX_STATE_ATTRS_BYTES
    assert "last_5_winners" not in shared_attrs
    assert "last_5_poles" not in shared_attrs
    assert shared_attrs["defending_winner"]["season"] == "2025"


@pytest.mark.asyncio
async def test_next_race_history_last_year_podium_missing_returns_none(
    hass, monkeypatch
) -> None:
    next_race, payloads = _build_next_race_history_fixture(
        include_previous_season=False
    )
    race_coordinator = _build_coordinator(
        hass,
        {"MRData": {"RaceTable": {"Races": [next_race]}}},
    )

    async def _fake_fetch_url(_self, url):
        if url not in payloads:
            raise AssertionError(f"Unexpected URL: {url}")
        return payloads[url]

    monkeypatch.setattr(
        F1NextRaceHistoryCoordinator,
        "_fetch_url",
        _fake_fetch_url,
    )

    history_coordinator = F1NextRaceHistoryCoordinator(
        hass,
        race_coordinator,
        "Test Next Race History Coordinator",
        session=MagicMock(),
        user_agent="ua",
        cache={},
        inflight={},
        ttl_seconds=3600,
        persist_map={},
        persist_save=MagicMock(),
    )
    history = await history_coordinator._async_update_data()

    assert history["last_year_podium"] is None
    assert [item["season"] for item in history["last_5_winners"]] == [
        "2024",
        "2023",
        "2022",
        "2021",
        "2020",
    ]
    assert history["races_held_here"] == 6


@pytest.mark.asyncio
async def test_current_season_sensor_enriches_races_with_detailed_maps(hass) -> None:
    coordinator = _build_coordinator(
        hass,
        {
            "MRData": {
                "RaceTable": {
                    "season": "2026",
                    "Races": [
                        _build_race(round_="1"),
                        _build_race(
                            round_="16",
                            race_name="Spanish Grand Prix",
                            circuit_id="madring",
                            circuit_name="Madring",
                            locality="Madrid",
                            country="Spain",
                            date="2026-09-13",
                            time="13:00:00Z",
                        ),
                    ],
                }
            }
        },
    )
    entry_id = "test_entry_current_season_maps"
    _set_entry_context(hass, entry_id)

    sensor = F1CurrentSeasonSensor(
        coordinator,
        f"{entry_id}_current_season",
        entry_id,
        "F1",
    )
    state = await _add_sensor_and_get_state(hass, sensor)

    races = state.attributes["races"]
    assert races[0]["circuit_map_url"].endswith("2026trackmelbournedetailed.webp")
    assert races[1]["circuit_map_url"].endswith("2026trackmadringdetailed.webp")


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
async def test_live_bus_stream_diagnostics_track_frames_and_keys(
    hass, monkeypatch, caplog
) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(
        "custom_components.f1_sensor.signalr.time.time",
        lambda: clock["now"],
    )
    bus = LiveBus(hass, MagicMock())

    caplog.set_level(logging.DEBUG, logger="custom_components.f1_sensor.signalr")

    bus.inject_message("SessionStatus", {"Status": "Started"})
    clock["now"] = 112.5
    bus.inject_message("TrackStatus", {"Status": "1", "Message": "AllClear"})

    diagnostics = bus.stream_diagnostics(
        ["ChampionshipPrediction", "SessionStatus", "TrackStatus"]
    )

    assert diagnostics["ChampionshipPrediction"] == {
        "frame_count": 0,
        "last_seen_age_s": None,
        "last_payload_keys": None,
    }
    assert diagnostics["SessionStatus"] == {
        "frame_count": 1,
        "last_seen_age_s": 12.5,
        "last_payload_keys": ["Status"],
    }
    assert diagnostics["TrackStatus"] == {
        "frame_count": 1,
        "last_seen_age_s": 0.0,
        "last_payload_keys": ["Status", "Message"],
    }
    assert "LiveBus first frame for SessionStatus with keys=['Status']" in caplog.text
    assert (
        "LiveBus first frame for TrackStatus with keys=['Status', 'Message']"
        in caplog.text
    )
    # ChampionshipPrediction removed from DEBUG_SUMMARY_STREAMS (replay-only)
    assert "TopThree:0/0 (none)" in caplog.text


@pytest.mark.asyncio
async def test_live_timing_mode_sensor_exposes_stream_diagnostics(hass) -> None:
    entry_id = "test_entry_live_diagnostics"
    _set_entry_context(hass, entry_id, stream_active=True)

    bus = MagicMock()
    bus.last_heartbeat_age.return_value = 5.0
    bus.last_stream_activity_age.return_value = 2.0
    bus.stream_diagnostics.return_value = {
        "SessionStatus": {
            "frame_count": 3,
            "last_seen_age_s": 1.0,
            "last_payload_keys": ["Status"],
        },
        "TrackStatus": {
            "frame_count": 8,
            "last_seen_age_s": 0.5,
            "last_payload_keys": ["Status", "Message"],
        },
    }
    hass.data[DOMAIN][entry_id]["live_bus"] = bus

    sensor = F1LiveTimingModeSensor(hass, entry_id, "F1")
    state = await _add_sensor_and_get_state(hass, sensor)

    assert state.attributes["heartbeat_age_s"] == 5.0
    assert state.attributes["activity_age_s"] == 2.0
    assert state.attributes["streams"]["SessionStatus"] == {
        "frame_count": 3,
        "last_seen_age_s": 1.0,
        "last_payload_keys": ["Status"],
    }
    assert state.attributes["streams"]["TrackStatus"] == {
        "frame_count": 8,
        "last_seen_age_s": 0.5,
        "last_payload_keys": ["Status", "Message"],
    }
    assert state.attributes["streams"]["ChampionshipPrediction"] == {
        "frame_count": 0,
        "last_seen_age_s": None,
        "last_payload_keys": None,
    }
    assert "TyreStintSeries" not in state.attributes["streams"]


@pytest.mark.asyncio
async def test_top_three_sensor_rate_limits_to_one_second(hass) -> None:
    coordinator = _build_coordinator(
        hass,
        _build_top_three_data(
            p1="VER",
            p2="HAM",
            p3="NOR",
            ts="2026-03-08T04:00:00+00:00",
        ),
    )
    entry_id = "test_entry_top_three"
    _set_entry_context(hass, entry_id, stream_active=True)

    sensor = F1TopThreePositionSensor(
        coordinator,
        f"{entry_id}_top_three_p2",
        entry_id,
        "F1",
        position_index=1,
    )
    await _add_sensor_and_get_state(hass, sensor)

    writes: list[float] = []
    sensor._safe_write_ha_state = lambda *_args: writes.append(time.monotonic())

    coordinator.async_set_updated_data(
        _build_top_three_data(
            p1="VER",
            p2="LEC",
            p3="NOR",
            ts="2026-03-08T04:00:01+00:00",
        )
    )
    await hass.async_block_till_done()
    assert len(writes) == 1

    coordinator.async_set_updated_data(
        _build_top_three_data(
            p1="VER",
            p2="RUS",
            p3="NOR",
            ts="2026-03-08T04:00:02+00:00",
        )
    )
    await hass.async_block_till_done()
    assert len(writes) == 1

    await asyncio.sleep(1.2)
    await hass.async_block_till_done()

    assert len(writes) == 2
    assert sensor.native_value == "RUS"


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
async def test_weather_sensor_timeout_clears_stale_state(hass, monkeypatch) -> None:
    coordinator = _build_coordinator(
        hass,
        {
            "MRData": {
                "RaceTable": {
                    "Races": [
                        {
                            "season": "2026",
                            "round": "1",
                            "raceName": "Australian Grand Prix",
                            "date": "2099-03-20",
                            "time": "05:00:00Z",
                            "Circuit": {
                                "circuitId": "albert_park",
                                "circuitName": "Albert Park",
                                "Location": {"lat": "-37.8497", "long": "144.968"},
                            },
                        }
                    ]
                }
            }
        },
    )
    entry_id = "test_entry"
    _set_entry_context(hass, entry_id)

    sensor = F1WeatherSensor(
        coordinator,
        f"{entry_id}_weather",
        entry_id,
        "F1",
    )
    sensor._current = {"temperature": 31.2, "weather_source": "stale"}
    sensor._race = {"temperature": 27.5, "weather_source": "stale"}
    sensor._attr_icon = "mdi:weather-sunny"
    timeout_session = _TimeoutSession()

    monkeypatch.setattr(
        "custom_components.f1_sensor.sensor.async_get_clientsession",
        lambda _hass: timeout_session,
    )
    sensor._hass = hass
    sensor.async_write_ha_state = MagicMock()

    await sensor._update_weather()

    assert timeout_session.calls == 1
    assert sensor._current == {}
    assert sensor._race == {}
    assert sensor._attr_icon == "mdi:weather-partly-cloudy"
    sensor.async_write_ha_state.assert_called_once()


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
