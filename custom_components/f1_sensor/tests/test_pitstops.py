from __future__ import annotations

from typing import Callable
from unittest.mock import MagicMock

import pytest

from custom_components.f1_sensor.__init__ import PitStopCoordinator


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
