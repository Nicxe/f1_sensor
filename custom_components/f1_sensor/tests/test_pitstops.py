from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.f1_sensor.__init__ import (
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
