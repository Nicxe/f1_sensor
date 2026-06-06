from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.f1_sensor.__init__ import (
    PITSTOP_MAX_CARS,
    PITSTOP_MAX_ENTRIES_PER_PAYLOAD,
    PITSTOP_MAX_HISTORY_PER_CAR,
    PITSTOP_MAX_TEXT_CHARS,
    LiveDriversCoordinator,
    PitStopCoordinator,
)


class DummyDriversCoordinator:
    def __init__(self, data) -> None:
        self.data = data
        self._listeners: list[Callable[[], None]] = []

    def async_add_listener(self, callback):
        self._listeners.append(callback)

        def _remove():
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _remove

    def fire(self) -> None:
        for callback in list(self._listeners):
            callback()


def _make_live_drivers_coord(hass) -> LiveDriversCoordinator:
    return LiveDriversCoordinator(
        hass,
        SimpleNamespace(),
        delay_seconds=0,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
    )


@pytest.mark.asyncio
async def test_pit_delta_computed_when_lap_time_available(hass) -> None:
    drivers_coord = DummyDriversCoordinator(
        {
            "drivers": {
                "44": {
                    "lap_history": {
                        "laps": {
                            "9": "1:30.000",
                            "10": "1:45.000",
                            "11": "1:30.000",
                        }
                    }
                }
            }
        }
    )
    coordinator = PitStopCoordinator(
        hass,
        session_coord=MagicMock(),
        delay_seconds=0,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
        history_limit=10,
        drivers_coordinator=drivers_coord,
    )

    coordinator._add_stop(
        "44",
        {"lap": 10, "pit_stop_time": 2.5, "pit_lane_time": 20.0},
    )

    stop = coordinator._by_car["44"][0]
    assert stop["pit_delta"] == 15.0

    coordinator._deliver()
    state = coordinator.data
    assert state["cars"]["44"]["stops"][0]["pit_delta"] == 15.0


@pytest.mark.asyncio
async def test_pit_delta_updates_after_lap_time_arrives(hass) -> None:
    drivers_coord = DummyDriversCoordinator(
        {
            "drivers": {
                "44": {
                    "lap_history": {
                        "laps": {"9": "1:30.000"},
                    }
                }
            }
        }
    )
    coordinator = PitStopCoordinator(
        hass,
        session_coord=MagicMock(),
        delay_seconds=0,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
        history_limit=10,
        drivers_coordinator=drivers_coord,
    )

    coordinator._add_stop(
        "44",
        {"lap": 10, "pit_stop_time": 2.5, "pit_lane_time": 20.0},
    )
    stop = coordinator._by_car["44"][0]
    assert stop["pit_delta"] is None

    drivers_coord.data["drivers"]["44"]["lap_history"]["laps"]["10"] = "1:45.000"
    assert coordinator._refresh_pit_deltas() is False
    assert stop["pit_delta"] is None

    drivers_coord.data["drivers"]["44"]["lap_history"]["laps"]["11"] = "1:30.000"
    assert coordinator._refresh_pit_deltas() is True
    assert stop["pit_delta"] == 15.0


@pytest.mark.asyncio
async def test_pitstops_identity_from_drivers_coordinator(hass) -> None:
    drivers_coord = DummyDriversCoordinator(
        {
            "drivers": {
                "1": {
                    "identity": {
                        "tla": "VER",
                        "name": "Max Verstappen",
                        "team": "Red Bull Racing",
                    }
                }
            }
        }
    )
    coordinator = PitStopCoordinator(
        hass,
        session_coord=MagicMock(),
        delay_seconds=0,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
        history_limit=10,
        drivers_coordinator=drivers_coord,
    )

    coordinator._add_stop(
        "1",
        {"lap": 10, "pit_stop_time": 2.5, "pit_lane_time": 20.0},
    )

    coordinator._deliver()
    state = coordinator.data
    car = state["cars"]["1"]
    assert car["tla"] == "VER"
    assert car["name"] == "Max Verstappen"
    assert car["team"] == "Red Bull Racing"


@pytest.mark.asyncio
async def test_live_drivers_store_pitstops_from_timingdata(hass) -> None:
    coordinator = _make_live_drivers_coord(hass)

    changed = coordinator._merge_timingdata(
        {"Lines": {"44": {"NumberOfLaps": 10, "NumberOfPitStops": 2}}}
    )

    assert changed is True
    assert coordinator._state["drivers"]["44"]["timing"]["pit_stops"] == 2


@pytest.mark.asyncio
async def test_live_drivers_store_pitstops_from_driver_race_info_without_position(
    hass,
) -> None:
    coordinator = _make_live_drivers_coord(hass)

    coordinator._on_driver_race_info({"44": {"PitStops": 1}})

    assert coordinator._state["drivers"]["44"]["timing"]["pit_stops"] == 1


@pytest.mark.asyncio
async def test_pitstops_seed_from_driver_counts_when_series_missing(hass) -> None:
    drivers_coord = DummyDriversCoordinator(
        {
            "drivers": {
                "44": {
                    "identity": {
                        "tla": "HAM",
                        "name": "Lewis Hamilton",
                        "team": "Ferrari",
                    },
                    "timing": {"pit_stops": 2},
                }
            }
        }
    )
    coordinator = PitStopCoordinator(
        hass,
        session_coord=MagicMock(),
        delay_seconds=0,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
        history_limit=10,
        drivers_coordinator=drivers_coord,
    )

    assert coordinator._refresh_pit_counts_from_coordinator() is True
    assert coordinator._refresh_driver_map_from_coordinator() is True
    coordinator._deliver()

    state = coordinator.data
    assert state["total_stops"] == 2
    assert state["cars"]["44"]["count"] == 2
    assert state["cars"]["44"]["stops"] == []
    assert state["cars"]["44"]["tla"] == "HAM"


@pytest.mark.asyncio
async def test_pitstops_count_prefers_driver_total_over_partial_series(hass) -> None:
    drivers_coord = DummyDriversCoordinator(
        {
            "drivers": {
                "44": {
                    "timing": {"pit_stops": 2},
                }
            }
        }
    )
    coordinator = PitStopCoordinator(
        hass,
        session_coord=MagicMock(),
        delay_seconds=0,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
        history_limit=10,
        drivers_coordinator=drivers_coord,
    )

    coordinator._add_stop(
        "44",
        {"lap": 10, "pit_stop_time": 2.5, "pit_lane_time": 20.0},
    )
    coordinator._on_drivers_update()

    state = coordinator.data
    assert state["total_stops"] == 2
    assert state["cars"]["44"]["count"] == 2
    assert len(state["cars"]["44"]["stops"]) == 1


@pytest.mark.asyncio
async def test_pitstopseries_bounds_cars_entries_and_dedup(hass) -> None:
    coordinator = PitStopCoordinator(
        hass,
        session_coord=MagicMock(),
        delay_seconds=0,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
        history_limit=50,
    )
    payload = {
        "PitTimes": {
            str(idx + 1): [
                {
                    "Timestamp": f"T{idx}",
                    "PitStop": {
                        "RacingNumber": str(idx + 1),
                        "Lap": 10,
                        "PitStopTime": 2.5,
                        "PitLaneTime": 20.0,
                    },
                }
            ]
            for idx in range(PITSTOP_MAX_CARS + 20)
        }
    }

    coordinator._ingest_pitstopseries(payload)
    coordinator._deliver()

    assert len(coordinator._by_car) == PITSTOP_MAX_CARS
    assert len(coordinator._dedup) == PITSTOP_MAX_CARS
    assert len(coordinator.data["cars"]) == PITSTOP_MAX_CARS


@pytest.mark.asyncio
async def test_pitstopseries_evicts_dedup_with_history_limit(hass) -> None:
    coordinator = PitStopCoordinator(
        hass,
        session_coord=MagicMock(),
        delay_seconds=0,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
        history_limit=PITSTOP_MAX_HISTORY_PER_CAR + 10,
    )

    for idx in range(PITSTOP_MAX_HISTORY_PER_CAR + 25):
        coordinator._add_stop(
            "44",
            {
                "lap": idx + 1,
                "timestamp": f"T{idx}",
                "pit_stop_time": 2.5,
                "pit_lane_time": 20.0,
            },
        )

    assert len(coordinator._by_car["44"]) == PITSTOP_MAX_HISTORY_PER_CAR
    assert len(coordinator._dedup) == PITSTOP_MAX_HISTORY_PER_CAR
    assert coordinator._by_car["44"][0]["timestamp"] == "T25"


@pytest.mark.asyncio
async def test_pitstopseries_rejects_invalid_racing_numbers_and_bounds_text(
    hass,
) -> None:
    coordinator = PitStopCoordinator(
        hass,
        session_coord=MagicMock(),
        delay_seconds=0,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
        history_limit=10,
    )

    coordinator._ingest_pitstopseries(
        {
            "PitTimes": {
                "../44": [
                    {
                        "Timestamp": "bad",
                        "PitStop": {"RacingNumber": "../44", "Lap": 1},
                    }
                ],
                "44": [
                    {
                        "Timestamp": "x" * (PITSTOP_MAX_TEXT_CHARS + 10),
                        "PitStop": {
                            "RacingNumber": "44",
                            "Lap": 2,
                            "PitStopTime": 2.5,
                            "PitLaneTime": 20.0,
                        },
                    }
                ],
            }
        }
    )

    assert set(coordinator._by_car) == {"44"}
    assert len(coordinator._by_car["44"][0]["timestamp"]) == PITSTOP_MAX_TEXT_CHARS


@pytest.mark.asyncio
async def test_pitstopseries_limits_entries_per_payload(hass) -> None:
    coordinator = PitStopCoordinator(
        hass,
        session_coord=MagicMock(),
        delay_seconds=0,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
        history_limit=PITSTOP_MAX_ENTRIES_PER_PAYLOAD,
    )
    coordinator._ingest_pitstopseries(
        {
            "PitTimes": {
                str(car): [
                    {
                        "Timestamp": f"T{car}-{idx}",
                        "PitStop": {
                            "RacingNumber": str(car),
                            "Lap": idx,
                            "PitStopTime": 2.5,
                            "PitLaneTime": 20.0,
                        },
                    }
                    for idx in range(PITSTOP_MAX_HISTORY_PER_CAR)
                ]
                for car in range(1, PITSTOP_MAX_CARS + 1)
            }
        }
    )

    retained = sum(len(stops) for stops in coordinator._by_car.values())
    assert retained == PITSTOP_MAX_ENTRIES_PER_PAYLOAD
    assert len(coordinator._dedup) == PITSTOP_MAX_ENTRIES_PER_PAYLOAD


@pytest.mark.asyncio
async def test_pitstop_last_reset_is_stable_until_store_reset(
    hass, monkeypatch
) -> None:
    reset_times = iter(
        (
            "2026-06-06T10:30:00+00:00",
            "2026-06-06T10:45:00+00:00",
            "2026-06-06T11:30:00+00:00",
        )
    )
    monkeypatch.setattr(
        "custom_components.f1_sensor.__init__.dt_util.utcnow",
        lambda: datetime.fromisoformat(next(reset_times)),
    )
    coordinator = PitStopCoordinator(
        hass,
        session_coord=MagicMock(),
        delay_seconds=0,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
    )

    initial_reset = coordinator._state["last_reset"]
    coordinator._add_stop("44", {"lap": 10, "timestamp": "10:45:00"})
    coordinator._deliver()

    assert coordinator.data["last_reset"] == initial_reset

    coordinator._reset_store()

    assert coordinator.data["last_reset"] == "2026-06-06T11:30:00+00:00"
