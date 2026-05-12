from __future__ import annotations

import logging

from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import pytest

from custom_components.f1_sensor.sensor import F1StartingGridSensor
from custom_components.f1_sensor.starting_grid import (
    CONTEXT_RACE,
    CONTEXT_SPRINT,
    SOURCE_GRIDPOS,
    STATUS_COLLECTING,
    STATUS_CONFIRMED,
    STATUS_PROVISIONAL,
    STATUS_WAITING_QUALIFYING,
    StartingGridCoordinator,
)

_LOGGER = logging.getLogger(__name__)


class _SessionCoord:
    def __init__(self, data: dict | None = None) -> None:
        self.data = data or {}


class _LiveState:
    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason


def _session_info(
    name: str,
    session_type: str,
    *,
    meeting_key: int = 1,
    session_key: int = 10,
    status: str = "Started",
) -> dict:
    return {
        "Meeting": {"Key": meeting_key, "Name": "Test Grand Prix"},
        "SessionStatus": status,
        "Key": session_key,
        "Type": session_type,
        "Name": name,
        "Path": f"2026/2026-01-01_Test_Grand_Prix/2026-01-01_{name.replace(' ', '_')}/",
    }


def _driver_list() -> dict:
    return {
        "1": {
            "RacingNumber": "1",
            "Tla": "AAA",
            "FullName": "Driver A",
            "TeamName": "Team A",
            "TeamColour": "112233",
        },
        "2": {
            "RacingNumber": "2",
            "Tla": "BBB",
            "FullName": "Driver B",
            "TeamName": "Team B",
            "TeamColour": "#445566",
        },
        "3": {
            "RacingNumber": "3",
            "Tla": "CCC",
            "FullName": "Driver C",
            "TeamName": "Team C",
        },
    }


def _timing_data() -> dict:
    return {
        "Lines": {
            "1": {
                "Position": "1",
                "BestLapTime": {"Value": "1:10.000", "Lap": 8},
                "BestLapTimes": {
                    "0": {"Value": "1:12.000", "Lap": 3},
                    "1": {"Value": "1:11.000", "Lap": 5},
                    "2": {"Value": "1:10.000", "Lap": 8},
                },
            },
            "2": {
                "Position": "2",
                "BestLapTime": {"Value": "1:10.500", "Lap": 7},
                "BestLapTimes": {
                    "0": {"Value": "1:12.500", "Lap": 3},
                    "1": {"Value": "1:11.500", "Lap": 5},
                    "2": {"Value": "1:10.500", "Lap": 7},
                },
            },
            "3": {
                "Position": "3",
                "BestLapTime": {"Value": "1:11.000", "Lap": 4},
                "BestLapTimes": {
                    "0": {"Value": "1:11.000", "Lap": 4},
                    "1": {},
                    "2": {},
                },
            },
        }
    }


def _make_coordinator(
    hass,
    index: dict | None = None,
    *,
    live_state: _LiveState | None = None,
) -> StartingGridCoordinator:
    return StartingGridCoordinator(
        hass, _SessionCoord(index), bus=None, live_state=live_state
    )


@pytest.mark.asyncio
async def test_new_weekend_session_info_clears_previous_grid(hass) -> None:
    coordinator = _make_coordinator(hass)

    coordinator._on_session_info(_session_info("Qualifying", "Qualifying"))
    coordinator._on_driver_list(_driver_list())
    coordinator._on_timing_data(_timing_data())
    coordinator._on_session_status({"Status": "Finalised"})

    assert coordinator.data["status"] == STATUS_PROVISIONAL
    assert coordinator.data["grid_count"] == 3

    coordinator._on_session_info(
        _session_info(
            "Practice 1",
            "Practice",
            meeting_key=2,
            session_key=20,
            status="Started",
        )
    )

    assert coordinator.data["status"] == STATUS_WAITING_QUALIFYING
    assert coordinator.data["grid"] == []
    assert coordinator.data["grid_count"] == 0
    assert coordinator.data["cleared_reason"] == "new_weekend"
    assert coordinator.data["weekend_key"] == "meeting:2"


@pytest.mark.asyncio
async def test_normal_weekend_builds_and_confirms_race_grid(hass) -> None:
    coordinator = _make_coordinator(hass)

    coordinator._on_session_info(_session_info("Qualifying", "Qualifying"))
    coordinator._on_driver_list(_driver_list())
    coordinator._on_timing_data(_timing_data())
    coordinator._on_session_status({"Status": "Finalised"})

    grid = coordinator.data["grid"]
    assert coordinator.data["status"] == STATUS_PROVISIONAL
    assert coordinator.data["grid_context"] == CONTEXT_RACE
    assert grid[0]["qualifying_time"] == "1:10.000"
    assert grid[0]["qualifying_segment"] == "Q3"
    assert grid[0]["qualifying_lap"] == 8
    assert grid[0]["team_color"] == "#112233"

    coordinator._on_session_info(
        _session_info("Race", "Race", session_key=11, status="Started")
    )
    coordinator._on_timing_app_data(
        {
            "Lines": {
                "1": {"GridPos": 1},
                "2": {"GridPos": 3},
                "3": {"GridPos": 2},
            }
        }
    )

    grid = coordinator.data["grid"]
    assert coordinator.data["status"] == STATUS_CONFIRMED
    assert coordinator.data["source"] == SOURCE_GRIDPOS
    assert [row["racing_number"] for row in grid] == ["1", "3", "2"]
    moved = next(row for row in grid if row["racing_number"] == "2")
    assert moved["qualifying_position"] == 2
    assert moved["grid_position"] == 3
    assert moved["grid_delta"] == 1
    assert moved["changed_from_qualifying"] is True


@pytest.mark.asyncio
async def test_sprint_grid_clears_before_race_qualifying_grid(hass) -> None:
    coordinator = _make_coordinator(hass)

    coordinator._on_session_info(_session_info("Practice 1", "Practice"))
    coordinator._on_session_info(
        _session_info("Sprint Qualifying", "Qualifying", session_key=12)
    )
    assert coordinator.data["status"] == STATUS_COLLECTING
    assert coordinator.data["grid_context"] == CONTEXT_SPRINT

    coordinator._on_driver_list(_driver_list())
    coordinator._on_timing_data(_timing_data())
    coordinator._on_session_status({"Status": "Finalised"})

    assert coordinator.data["status"] == STATUS_PROVISIONAL
    assert coordinator.data["grid_context"] == CONTEXT_SPRINT
    assert coordinator.data["grid"][0]["qualifying_segment"] == "SQ3"

    coordinator._on_session_info(
        _session_info("Sprint", "Race", session_key=13, status="Started")
    )
    coordinator._on_timing_app_data(
        {"Lines": {"1": {"GridPos": 1}, "2": {"GridPos": 2}, "3": {"GridPos": 3}}}
    )
    assert coordinator.data["status"] == STATUS_CONFIRMED
    assert coordinator.data["grid_context"] == CONTEXT_SPRINT

    coordinator._on_session_status({"Status": "Finalised"})
    assert coordinator.data["status"] == STATUS_WAITING_QUALIFYING
    assert coordinator.data["grid_context"] == CONTEXT_RACE
    assert coordinator.data["grid"] == []

    coordinator._on_session_info(
        _session_info("Qualifying", "Qualifying", session_key=14, status="Started")
    )
    coordinator._on_timing_data(_timing_data())
    coordinator._on_session_status({"Status": "Finalised"})

    assert coordinator.data["status"] == STATUS_PROVISIONAL
    assert coordinator.data["grid_context"] == CONTEXT_RACE
    assert coordinator.data["grid"][0]["qualifying_segment"] == "Q3"


@pytest.mark.asyncio
async def test_replay_session_info_does_not_clear_current_grid(hass) -> None:
    live_state = _LiveState()
    coordinator = _make_coordinator(hass, live_state=live_state)

    coordinator._on_session_info(_session_info("Qualifying", "Qualifying"))
    coordinator._on_driver_list(_driver_list())
    coordinator._on_timing_data(_timing_data())
    coordinator._on_session_status({"Status": "Finalised"})
    before = coordinator.data

    live_state.reason = "replay"
    coordinator._on_session_info(
        _session_info(
            "Practice 1",
            "Practice",
            meeting_key=99,
            session_key=990,
            status="Started",
        )
    )

    assert coordinator.data == before
    assert coordinator.data["weekend_key"] == "meeting:1"
    assert coordinator.data["status"] == STATUS_PROVISIONAL
    assert coordinator.data["grid_count"] == 3


@pytest.mark.asyncio
async def test_replay_gridpos_does_not_replace_current_grid(hass) -> None:
    live_state = _LiveState()
    coordinator = _make_coordinator(hass, live_state=live_state)

    coordinator._on_session_info(_session_info("Qualifying", "Qualifying"))
    coordinator._on_driver_list(_driver_list())
    coordinator._on_timing_data(_timing_data())
    coordinator._on_session_status({"Status": "Finalised"})
    coordinator._on_session_info(
        _session_info("Race", "Race", session_key=11, status="Started")
    )
    coordinator._on_timing_app_data(
        {"Lines": {"1": {"GridPos": 1}, "2": {"GridPos": 2}, "3": {"GridPos": 3}}}
    )
    before = coordinator.data

    live_state.reason = "replay"
    coordinator._on_timing_app_data(
        {"Lines": {"1": {"GridPos": 3}, "2": {"GridPos": 1}, "3": {"GridPos": 2}}}
    )

    assert coordinator.data == before
    assert coordinator.data["status"] == STATUS_CONFIRMED
    assert [row["racing_number"] for row in coordinator.data["grid"]] == [
        "1",
        "2",
        "3",
    ]


@pytest.mark.asyncio
async def test_starting_grid_sensor_excludes_grid_from_recorder(hass) -> None:
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="starting-grid-test",
        update_interval=None,
    )
    coordinator.async_set_updated_data(
        {
            "status": STATUS_CONFIRMED,
            "grid_context": CONTEXT_RACE,
            "weekend_key": "meeting:1",
            "weekend_format": "normal",
            "meeting_name": "Test Grand Prix",
            "session_key": "11",
            "source_session_name": "Race",
            "target_session_name": "Race",
            "source": SOURCE_GRIDPOS,
            "source_updated_at": "2026-01-01T12:00:00+00:00",
            "cleared_at": None,
            "cleared_reason": None,
            "grid_count": 1,
            "grid": [{"grid_position": 1, "racing_number": "1"}],
        }
    )
    sensor = F1StartingGridSensor(
        coordinator,
        "entry_starting_grid",
        "entry",
        "F1",
    )

    component = EntityComponent(_LOGGER, "sensor", hass)
    await component.async_add_entities([sensor])
    await hass.async_block_till_done()

    state = hass.states.get(sensor.entity_id)
    assert state is not None
    assert state.state == STATUS_CONFIRMED
    assert "grid" in state.attributes
    assert state.state_info is not None
    assert "grid" in state.state_info["unrecorded_attributes"]
