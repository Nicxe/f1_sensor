from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import pytest

from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.sensor import F1StartingGridSensor
from custom_components.f1_sensor.starting_grid import (
    CONTEXT_RACE,
    CONTEXT_SPRINT,
    SOURCE_GRIDPOS,
    STATUS_COLLECTING,
    STATUS_CONFIRMED,
    STATUS_PROVISIONAL,
    STATUS_UNAVAILABLE,
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
async def test_duplicate_gridpos_falls_back_to_pre_start_line(hass) -> None:
    coordinator = _make_coordinator(hass)

    coordinator._on_session_info(_session_info("Qualifying", "Qualifying"))
    coordinator._on_driver_list(_driver_list())
    coordinator._on_timing_data(_timing_data())
    coordinator._on_session_status({"Status": "Finalised"})
    coordinator._on_session_info(
        _session_info("Race", "Race", session_key=11, status="Inactive")
    )
    # The feed can send a car the same GridPos as another car while its
    # Line still shows the real slot.
    coordinator._on_timing_app_data(
        {
            "Lines": {
                "1": {"GridPos": "1", "Line": 3},
                "2": {"GridPos": "2", "Line": 2},
                "3": {"GridPos": "1", "Line": 1},
            }
        }
    )

    grid = coordinator.data["grid"]
    assert [row["racing_number"] for row in grid] == ["3", "2", "1"]
    assert [row["grid_position"] for row in grid] == [1, 2, 3]

    # After the start Line is the running order: a GridPos-only delta and a
    # reconnect snapshot with new Lines must not move the grid.
    coordinator._on_session_status({"Status": "Started"})
    coordinator._on_timing_app_data({"Lines": {"1": {"GridPos": "1"}}})
    coordinator._on_timing_app_data(
        {
            "Lines": {
                "1": {"GridPos": "1", "Line": 1},
                "2": {"GridPos": "2", "Line": 2},
                "3": {"GridPos": "1", "Line": 3},
            }
        }
    )
    assert [row["racing_number"] for row in coordinator.data["grid"]] == [
        "3",
        "2",
        "1",
    ]


@pytest.mark.asyncio
async def test_duplicate_gridpos_uses_line_correction_without_gridpos(
    hass,
) -> None:
    coordinator = _make_coordinator(hass)

    coordinator._on_session_info(
        _session_info("Race", "Race", session_key=11, status="Inactive")
    )
    # Order seen before the 2026 Singapore Sprint: car 1 is placed on pole,
    # then moved to Line 5 by a delta without GridPos, then car 3 takes pole.
    coordinator._on_timing_app_data({"Lines": {"1": {"Line": 1, "GridPos": "1"}}})
    coordinator._on_timing_app_data({"Lines": {"1": {"Line": 5}}})
    coordinator._on_timing_app_data(
        {
            "Lines": {
                "3": {"Line": 1, "GridPos": "1"},
                "2": {"Line": 2, "GridPos": "2"},
                "4": {"Line": 3, "GridPos": "3"},
                "5": {"Line": 4, "GridPos": "4"},
            }
        }
    )

    grid = coordinator.data["grid"]
    assert [row["racing_number"] for row in grid] == ["3", "2", "4", "5", "1"]
    assert [row["grid_position"] for row in grid] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_duplicate_gridpos_ignores_line_without_pre_start_status(
    hass,
) -> None:
    coordinator = _make_coordinator(hass)

    # Cold start mid-race: SessionInfo carries no status, Line is running order.
    coordinator._on_session_info(
        _session_info("Race", "Race", session_key=11, status="")
    )
    coordinator._on_timing_app_data(
        {
            "Lines": {
                "1": {"GridPos": "1", "Line": 2},
                "2": {"GridPos": "1", "Line": 1},
                "3": {"GridPos": "3", "Line": 3},
            }
        }
    )

    assert coordinator.data["status"] == STATUS_UNAVAILABLE
    assert coordinator.data["grid"] == []


@pytest.mark.asyncio
async def test_cold_start_recovers_duplicate_from_pre_start_archive(
    hass, monkeypatch
) -> None:
    coordinator = _make_coordinator(hass)
    coordinator._on_session_info(
        _session_info("Race", "Race", session_key=11, status="Started")
    )
    archives = {
        "SessionStatus": (
            '00:00:01.000{"Status":"Inactive"}\n00:00:30.000{"Status":"Started"}\n'
        ),
        "TimingAppData": (
            '00:00:10.000{"Lines":{"1":{"Line":1,"GridPos":"1"}}}\n'
            '00:00:20.000{"Lines":{"1":{"Line":3},'
            '"2":{"Line":2,"GridPos":"2"},'
            '"3":{"Line":1,"GridPos":"1"}}}\n'
            '00:00:31.000{"Lines":{"1":{"Line":2}}}\n'
        ),
    }
    fetch = AsyncMock(side_effect=lambda _path, stream, **_kwargs: archives[stream])
    monkeypatch.setattr(coordinator, "_fetch_stream", fetch)

    coordinator._on_timing_app_data(
        {
            "Lines": {
                "1": {"GridPos": "1", "Line": 2},
                "2": {"GridPos": "2", "Line": 2},
                "3": {"GridPos": "1", "Line": 1},
            }
        }
    )
    assert coordinator.data["status"] == STATUS_UNAVAILABLE
    assert coordinator.data["grid"] == []

    await hass.async_block_till_done()
    assert [row["racing_number"] for row in coordinator.data["grid"]] == [
        "3",
        "2",
        "1",
    ]
    assert [row["grid_position"] for row in coordinator.data["grid"]] == [1, 2, 3]
    assert coordinator.data["status"] == STATUS_CONFIRMED
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_cold_start_without_archive_does_not_confirm_duplicate(
    hass, monkeypatch
) -> None:
    coordinator = _make_coordinator(hass)
    coordinator._on_session_info(
        _session_info("Race", "Race", session_key=11, status="Started")
    )
    fetch = AsyncMock(return_value=None)
    monkeypatch.setattr(coordinator, "_fetch_stream", fetch)

    coordinator._on_timing_app_data(
        {"Lines": {"1": {"GridPos": "1"}, "3": {"GridPos": "1"}}}
    )
    await hass.async_block_till_done()

    assert coordinator.data["status"] == STATUS_UNAVAILABLE
    assert coordinator.data["grid"] == []
    assert fetch.await_count == 2

    fetch.reset_mock()
    fetch.side_effect = lambda _path, stream, **_kwargs: (
        '00:00:01.000{"Lines":{"1":{"Position":"1"}}}'
        if stream == "TimingData"
        else None
    )
    await coordinator._fetch_archive_context(CONTEXT_RACE, "2026/test/qualifying/")
    assert coordinator.data["status"] == STATUS_UNAVAILABLE
    assert coordinator.data["grid"] == []

    coordinator._on_timing_app_data({"Lines": {"1": {"GridPos": "1"}}})
    await hass.async_block_till_done()
    assert fetch.await_count == 2

    coordinator._on_timing_app_data({"Lines": {"3": {"GridPos": "3"}}})
    assert coordinator.data["status"] == STATUS_CONFIRMED
    assert [row["grid_position"] for row in coordinator.data["grid"]] == [1, 3]


@pytest.mark.asyncio
async def test_cold_start_archive_cannot_update_another_weekend(
    hass, monkeypatch
) -> None:
    coordinator = _make_coordinator(hass)
    coordinator._on_session_info(
        _session_info("Race", "Race", session_key=11, status="Started")
    )
    started_fetching = asyncio.Event()
    release_fetch = asyncio.Event()

    async def delayed_fetch(_path, stream, **_kwargs):
        started_fetching.set()
        await release_fetch.wait()
        return (
            '00:00:01.000{"Status":"Inactive"}\n' if stream == "SessionStatus" else ""
        )

    monkeypatch.setattr(coordinator, "_fetch_stream", delayed_fetch)
    coordinator._on_timing_app_data(
        {"Lines": {"1": {"GridPos": "1"}, "3": {"GridPos": "1"}}}
    )
    await started_fetching.wait()

    coordinator._on_session_info(
        _session_info(
            "Practice 1", "Practice", meeting_key=2, session_key=20, status="Started"
        )
    )
    release_fetch.set()
    await hass.async_block_till_done()
    assert coordinator.data["weekend_key"] == "meeting:2"
    assert coordinator.data["grid"] == []
    assert coordinator.data["status"] == STATUS_WAITING_QUALIFYING


def test_cold_start_requires_pre_start_status_evidence() -> None:
    timing = '00:00:10.000{"Lines":{"1":{"GridPos":"1","Line":5}}}\n'
    assert (
        StartingGridCoordinator._pre_start_grid_lines(
            '00:00:30.000{"Status":"Started"}\n', timing
        )
        == {}
    )


def test_cold_start_ignores_malformed_archive_frames() -> None:
    statuses = (
        '00:00:01.000{"Status":"Inactive"}\n'
        'bad-timestamp{"Status":"Started"}\n'
        '00:00:30.000{"Status":"Started"}\n'
    )
    timing = (
        "not a frame\n"
        'bad-timestamp{"Lines":{}}\n'
        '00:00:02.000{"Lines":[]}\n'
        '00:00:03.000{"Lines":{"1":[]}}\n'
        '00:00:04.000{"Lines":{"1":{"GridPos":"1","Line":3}}}\n'
        '00:00:05.000{"Lines":broken}\n'
        '00:00:31.000{"Lines":{"1":{"Line":2}}}\n'
    )
    assert StartingGridCoordinator._pre_start_grid_lines(statuses, timing) == {
        "1": (1, 3)
    }


@pytest.mark.asyncio
async def test_cold_start_rejects_archive_with_different_grid_position(
    hass, monkeypatch
) -> None:
    coordinator = _make_coordinator(hass)
    coordinator._on_session_info(
        _session_info("Race", "Race", session_key=11, status="Started")
    )
    archives = {
        "SessionStatus": (
            '00:00:01.000{"Status":"Inactive"}\n00:00:30.000{"Status":"Started"}\n'
        ),
        "TimingAppData": (
            '00:00:20.000{"Lines":{"1":{"GridPos":"4","Line":3},'
            '"3":{"GridPos":"1","Line":1}}}\n'
        ),
    }
    monkeypatch.setattr(
        coordinator,
        "_fetch_stream",
        AsyncMock(side_effect=lambda _path, stream, **_kwargs: archives[stream]),
    )
    coordinator._on_timing_app_data(
        {"Lines": {"1": {"GridPos": "1"}, "3": {"GridPos": "1"}}}
    )
    await hass.async_block_till_done()
    assert coordinator.data["status"] == STATUS_UNAVAILABLE
    assert coordinator.data["grid"] == []


@pytest.mark.asyncio
async def test_cold_start_without_session_path_stays_unavailable(
    hass, monkeypatch
) -> None:
    coordinator = _make_coordinator(hass)
    session_info = _session_info("Race", "Race", session_key=11, status="Started")
    session_info["Path"] = ""
    coordinator._on_session_info(session_info)
    fetch = AsyncMock()
    monkeypatch.setattr(coordinator, "_fetch_stream", fetch)

    coordinator._on_timing_app_data(
        {"Lines": {"1": {"GridPos": "1"}, "3": {"GridPos": "1"}}}
    )
    await hass.async_block_till_done()
    assert coordinator.data["status"] == STATUS_UNAVAILABLE
    assert coordinator.data["grid"] == []
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_cold_start_cancels_recovery_on_close_and_reset(
    hass, monkeypatch
) -> None:
    coordinator = _make_coordinator(hass)
    coordinator._on_session_info(
        _session_info("Race", "Race", session_key=11, status="Started")
    )
    started = asyncio.Event()

    async def pending_fetch(_path, _stream, **_kwargs):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(coordinator, "_fetch_stream", pending_fetch)
    duplicate = {"Lines": {"1": {"GridPos": "1"}, "3": {"GridPos": "1"}}}
    coordinator._on_timing_app_data(duplicate)
    await started.wait()
    await coordinator.async_close()
    assert coordinator.data["status"] == STATUS_UNAVAILABLE

    coordinator.reset_runtime_state()
    coordinator._on_timing_app_data(duplicate)
    started.clear()
    await started.wait()
    coordinator.reset_runtime_state()
    await hass.async_block_till_done()
    assert coordinator.data["grid"] == []
    assert coordinator.data["cleared_reason"] == "runtime_reset"


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
async def test_no_spoiler_blocks_starting_grid_live_updates(hass) -> None:
    hass.data.setdefault(DOMAIN, {})["no_spoiler_manager"] = SimpleNamespace(
        is_active=False
    )
    coordinator = _make_coordinator(hass)

    coordinator._on_session_info(_session_info("Qualifying", "Qualifying"))
    coordinator._on_driver_list(_driver_list())
    coordinator._on_timing_data(_timing_data())
    coordinator._on_session_status({"Status": "Finalised"})
    before = dict(coordinator.data)

    hass.data[DOMAIN]["no_spoiler_manager"].is_active = True

    coordinator._on_session_info(
        _session_info(
            "Practice 1",
            "Practice",
            meeting_key=99,
            session_key=990,
            status="Started",
        )
    )
    coordinator._on_timing_data(
        {
            "Lines": {
                "1": {
                    "Position": "20",
                    "BestLapTime": {"Value": "9:59.999", "Lap": 1},
                }
            }
        }
    )
    coordinator._on_timing_app_data({"Lines": {"1": {"GridPos": 20}}})

    assert coordinator.data == before
    assert coordinator.data["weekend_key"] == "meeting:1"
    assert coordinator.data["status"] == STATUS_PROVISIONAL
    assert coordinator.data["grid_count"] == 3


@pytest.mark.asyncio
async def test_no_spoiler_does_not_block_starting_grid_replay_publish(hass) -> None:
    hass.data.setdefault(DOMAIN, {})["no_spoiler_manager"] = SimpleNamespace(
        is_active=True
    )
    live_state = _LiveState(reason="replay")
    coordinator = _make_coordinator(hass, live_state=live_state)
    coordinator._state.update(
        {
            "status": STATUS_PROVISIONAL,
            "grid_context": CONTEXT_RACE,
            "grid": [{"grid_position": 1, "racing_number": "1"}],
            "grid_count": 1,
        }
    )

    coordinator._publish()

    assert coordinator.data["status"] == STATUS_PROVISIONAL
    assert coordinator.data["grid_count"] == 1


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
