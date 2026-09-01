from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from custom_components.f1_sensor.favorite_driver import FavoriteDriverController
from custom_components.f1_sensor.select import F1FavoriteDriverSelect
from custom_components.f1_sensor.sensor import F1FavoriteDriverSensor


class _Coordinator:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.available = True
        self._listeners: list[Callable[[], None]] = []

    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def remove() -> None:
            self._listeners.remove(listener)

        return remove

    def update(self, data: dict[str, Any]) -> None:
        self.data = data
        for listener in tuple(self._listeners):
            listener()


def _driver(
    *,
    position: int,
    in_pit: bool = False,
    retired: bool = False,
) -> dict[str, Any]:
    return {
        "drivers": {
            "1": {
                "identity": {
                    "racing_number": "1",
                    "tla": "VER",
                    "name": "Max Verstappen",
                    "team": "Red Bull Racing",
                    "team_color": "3671C6",
                },
                "timing": {
                    "position": position,
                    "gap_to_leader": "LEADER" if position == 1 else "+1.234",
                    "interval": "+1.234",
                    "in_pit": in_pit,
                    "retired": retired,
                },
                "tyres": {"compound": "MEDIUM", "stint_laps": 8, "new": False},
                "lap_history": {"grid_position": 2},
            }
        }
    }


@pytest.mark.asyncio
async def test_favorite_driver_selection_is_persisted_and_projected(hass) -> None:
    coordinator = _Coordinator(_driver(position=2))
    controller = FavoriteDriverController(hass, "entry-one", coordinator)
    await controller.async_load()
    controller.start()

    await controller.async_set_driver("ver")

    assert controller.selected_tla == "VER"
    assert controller.options == ["VER"]
    assert controller.snapshot == {
        "racing_number": "1",
        "tla": "VER",
        "name": "Max Verstappen",
        "team": "Red Bull Racing",
        "team_color": "#3671C6",
        "team_color_rgb": [54, 113, 198],
        "position": 2,
        "grid_position": 2,
        "gap_to_leader": "+1.234",
        "interval_to_position_ahead": "+1.234",
        "last_lap": None,
        "best_lap": None,
        "in_pit": False,
        "pit_out": False,
        "pit_stops": None,
        "retired": False,
        "stopped": False,
        "status_code": None,
        "compound": "MEDIUM",
        "stint_laps": 8,
        "new_tyres": False,
    }

    reloaded = FavoriteDriverController(hass, "entry-one", coordinator)
    await reloaded.async_load()
    assert reloaded.selected_tla == "VER"
    assert reloaded.snapshot["position"] == 2

    await controller.async_shutdown()


@pytest.mark.asyncio
async def test_favorite_driver_emits_position_pit_and_retirement_events(hass) -> None:
    coordinator = _Coordinator(_driver(position=3))
    controller = FavoriteDriverController(hass, "entry-events", coordinator)
    await controller.async_load()
    await controller.async_set_driver("VER")
    controller.start()
    events: list[dict[str, Any]] = []

    def capture_event(
        event_type: str, previous: dict[str, Any], current: dict[str, Any]
    ) -> None:
        events.append(
            {"event_type": event_type, "previous": previous, "current": current}
        )

    controller._fire = capture_event

    coordinator.update(_driver(position=2, in_pit=True))
    await hass.async_block_till_done()
    coordinator.update(_driver(position=4, in_pit=False))
    await hass.async_block_till_done()
    coordinator.update(_driver(position=4, retired=True))
    await hass.async_block_till_done()

    assert [event["event_type"] for event in events] == [
        "position_gained",
        "entered_pits",
        "position_lost",
        "exited_pits",
        "retired",
    ]
    assert events[0]["current"]["tla"] == "VER"
    await controller.async_shutdown()


@pytest.mark.asyncio
async def test_favorite_driver_sensor_and_select_project_controller_state(hass) -> None:
    coordinator = _Coordinator(_driver(position=1))
    controller = FavoriteDriverController(hass, "entry-entities", coordinator)
    await controller.async_load()
    await controller.async_set_driver("VER")
    sensor = F1FavoriteDriverSensor(
        controller, "entry-entities_favorite_driver", "entry-entities", "F1"
    )
    select = F1FavoriteDriverSelect(
        controller, "entry-entities_favorite_driver_select", "entry-entities", "F1"
    )

    assert sensor.available is True
    assert sensor.native_value == 1
    assert sensor.extra_state_attributes["team_color_rgb"] == [54, 113, 198]
    assert select.options == ["No driver", "VER"]
    assert select.current_option == "VER"

    await select.async_select_option("No driver")

    assert select.current_option == "No driver"
    assert sensor.available is False
    assert sensor.native_value is None
