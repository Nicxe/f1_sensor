"""Lifecycle coverage for the live and archive starting-grid coordinator."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from custom_components.f1_sensor import starting_grid as grid

NOW = datetime(2026, 9, 1, 12, tzinfo=UTC)


def _coordinator(hass, *, index=None, live_reason=None):
    return grid.StartingGridCoordinator(
        hass,
        SimpleNamespace(data=index or {}),
        session=Mock(),
        live_state=SimpleNamespace(reason=live_reason),
    )


def _session(name: str, session_type: str, *, status: str = "Started") -> dict:
    return {
        "Key": f"key-{name}",
        "Name": name,
        "Type": session_type,
        "Path": f"2026/test/{name}",
        "Status": status,
        "Meeting": {"Key": 10, "Name": "Test GP"},
    }


def _timing_payload() -> dict:
    return {
        "Lines": {
            "bad": "skip",
            "4": {
                "Position": "1",
                "BestLapTimes": {
                    "0": {"Value": "1:20.000", "Lap": 3},
                    "1": {"Value": "1:19.000", "Lap": 6},
                },
                "BestLapTime": {"Value": "1:19.000", "Lap": 6},
            },
            "81": {"Position": "2", "BestLapTime": {"Value": "1:19.100"}},
        }
    }


def test_starting_grid_normal_weekend_live_lifecycle(hass) -> None:
    coordinator = _coordinator(hass)
    coordinator._maybe_schedule_archive_fetch = Mock()
    coordinator._on_session_info(_session("Qualifying", "Qualifying"))
    assert coordinator._state["status"] == grid.STATUS_COLLECTING
    coordinator._on_session_status({})
    coordinator._on_timing_data("bad")
    coordinator._on_timing_data(_timing_payload())
    assert (
        coordinator._qualifying_entries[grid.CONTEXT_RACE]["4"]["qualifying_segment"]
        == "Q2"
    )

    coordinator._on_session_status({"Status": "Finished"})
    assert coordinator._state["status"] == grid.STATUS_PROVISIONAL
    assert coordinator._state["grid_count"] == 2
    coordinator._on_driver_list(
        {
            "bad": "skip",
            "4": {
                "RacingNumber": "4",
                "Tla": "NOR",
                "FullName": "Lando Norris",
                "TeamColour": "ff8700",
            },
        }
    )
    assert coordinator._state["grid"][0]["tla"] == "NOR"
    coordinator._on_driver_list({"4": {"RacingNumber": "4", "Tla": "NOR"}})

    coordinator._on_session_info(_session("Race", "Race"))
    assert coordinator._maybe_schedule_archive_fetch.called
    coordinator._on_timing_app_data("bad")
    coordinator._on_timing_app_data({"Lines": "bad"})
    coordinator._on_timing_app_data(
        {
            "Lines": {
                "bad": "skip",
                "4": {"GridPos": "2"},
                "81": {"GridPos": "1"},
                "1": {"GridPos": "bad"},
            }
        }
    )
    assert coordinator._state["status"] == grid.STATUS_CONFIRMED
    assert coordinator._state["grid"][0]["racing_number"] == "81"
    coordinator._on_session_status({"Status": "Finished"})
    assert coordinator._state["status"] == grid.STATUS_COMPLETED
    assert coordinator._state["grid"] == []


def test_starting_grid_sprint_lifecycle_and_input_guards(hass) -> None:
    coordinator = _coordinator(hass)
    coordinator._maybe_schedule_archive_fetch = Mock()
    for handler in (
        coordinator._on_session_info,
        coordinator._on_session_status,
        coordinator._on_driver_list,
        coordinator._on_timing_data,
        coordinator._on_timing_app_data,
    ):
        handler("bad")

    coordinator._on_session_info(_session("Sprint Qualifying", "Qualifying"))
    coordinator._on_timing_data(_timing_payload())
    coordinator._on_session_status({"Status": "Finished"})
    assert coordinator._state["grid_context"] == grid.CONTEXT_SPRINT
    coordinator._on_session_info(_session("Sprint", "Race"))
    coordinator._on_session_status({"Status": "Finished"})
    assert coordinator._state["status"] == grid.STATUS_WAITING_QUALIFYING
    assert coordinator._state["grid_context"] == grid.CONTEXT_RACE

    no_spoiler = _coordinator(hass)
    no_spoiler._is_no_spoiler_active = Mock(return_value=True)
    no_spoiler._on_session_info(_session("Race", "Race"))
    no_spoiler._on_session_status({"Status": "Started"})
    no_spoiler._on_driver_list({})
    no_spoiler._on_timing_data({})
    no_spoiler._on_timing_app_data({})
    assert no_spoiler._weekend_key is None


async def test_starting_grid_archive_fetch_success_guards_and_failure(hass) -> None:
    coordinator = _coordinator(hass)
    coordinator._fetch_stream = AsyncMock(
        side_effect=[
            '00:00:00 {"4":{"RacingNumber":"4","Tla":"NOR"}}',
            '00:00:01 {"Lines":{"4":{"Position":"1"}}}',
        ]
    )
    await coordinator._fetch_archive_context(grid.CONTEXT_RACE, "2026/test/q")
    assert coordinator._state["status"] == grid.STATUS_PROVISIONAL
    assert coordinator._state["source"] == grid.SOURCE_ARCHIVE

    coordinator._fetch_stream = AsyncMock(side_effect=RuntimeError("down"))
    await coordinator._fetch_archive_context(grid.CONTEXT_RACE, "bad")

    coordinator._is_replay_active = Mock(return_value=True)
    coordinator._fetch_stream.reset_mock()
    await coordinator._fetch_archive_context(grid.CONTEXT_RACE, "skip")
    coordinator._fetch_stream.assert_not_called()


def test_starting_grid_index_sync_and_schedule_guards(hass) -> None:
    coordinator = _coordinator(hass)
    coordinator._current_or_next_index_session = Mock(return_value=None)
    coordinator._sync_from_index_if_idle()
    coordinator._current_or_next_index_session = Mock(return_value={})
    coordinator._sync_from_index_if_idle()
    source = {
        "Name": "Qualifying",
        "Type": "Qualifying",
        "Path": "2026/test/q",
        "_meeting": {"Key": 10, "Name": "Test GP"},
    }
    coordinator._current_or_next_index_session = Mock(return_value=source)
    coordinator._weekend_key_from_index_session = Mock(return_value="meeting:10")
    coordinator._detect_weekend_format = Mock(return_value=grid.WEEKEND_FORMAT_NORMAL)
    coordinator._initial_status_from_index = Mock(
        return_value=(grid.STATUS_WAITING_QUALIFYING, grid.CONTEXT_RACE)
    )
    coordinator._maybe_schedule_archive_fetch = Mock()
    coordinator._sync_from_index_if_idle()
    assert coordinator._weekend_key == "meeting:10"
    assert coordinator._maybe_schedule_archive_fetch.called
    coordinator._sync_from_index_if_idle()

    guarded = _coordinator(hass)
    guarded._index_source_session = Mock(return_value=None)
    guarded._maybe_schedule_archive_fetch(grid.CONTEXT_RACE)
    guarded._index_source_session.return_value = {"Path": "2026/test/q"}
    guarded._qualifying_entries[grid.CONTEXT_RACE] = {"4": {}}
    guarded._maybe_schedule_archive_fetch(grid.CONTEXT_RACE)
    assert guarded._archive_task is None


def test_starting_grid_initial_status_time_matrix(hass, monkeypatch) -> None:
    coordinator = _coordinator(hass)

    def indexed(*sessions):
        coordinator._index_sessions_for_weekend = Mock(return_value=list(sessions))

    def item(name, session_type, start, end):
        return {
            "Name": name,
            "Type": session_type,
            "StartDate": start.isoformat(),
            "EndDate": end.isoformat(),
            "GmtOffset": "00:00:00",
        }

    monkeypatch.setattr(grid.dt_util, "utcnow", lambda: NOW)
    race = item("Race", "Race", NOW - timedelta(hours=3), NOW - timedelta(hours=1))
    indexed(race)
    assert coordinator._initial_status_from_index(
        "weekend", grid.WEEKEND_FORMAT_NORMAL
    ) == (grid.STATUS_COMPLETED, grid.CONTEXT_NONE)

    qualifying = item(
        "Qualifying",
        "Qualifying",
        NOW - timedelta(minutes=30),
        NOW + timedelta(hours=1),
    )
    race = item("Race", "Race", NOW + timedelta(hours=2), NOW + timedelta(hours=4))
    indexed(qualifying, race)
    assert coordinator._initial_status_from_index(
        "weekend", grid.WEEKEND_FORMAT_NORMAL
    ) == (grid.STATUS_COLLECTING, grid.CONTEXT_RACE)

    sprint_qualifying = item(
        "Sprint Qualifying",
        "Qualifying",
        NOW - timedelta(hours=3),
        NOW - timedelta(hours=2),
    )
    sprint = item("Sprint", "Race", NOW - timedelta(hours=1), NOW + timedelta(hours=1))
    qualifying = item(
        "Qualifying", "Qualifying", NOW + timedelta(hours=2), NOW + timedelta(hours=3)
    )
    race = item("Race", "Race", NOW + timedelta(hours=5), NOW + timedelta(hours=7))
    indexed(sprint_qualifying, sprint, qualifying, race)
    assert coordinator._initial_status_from_index(
        "weekend", grid.WEEKEND_FORMAT_SPRINT
    ) == (grid.STATUS_COLLECTING, grid.CONTEXT_SPRINT)


async def test_starting_grid_close_tolerates_unsub_and_cancels_task(hass) -> None:
    coordinator = _coordinator(hass)
    coordinator._unsubs = [Mock(side_effect=RuntimeError), Mock()]
    coordinator._archive_task = hass.async_create_task(asyncio.sleep(60))
    await coordinator.async_close()
    assert coordinator._unsubs == []
    assert coordinator._archive_task is None


async def test_starting_grid_archive_scheduler_runs_once_and_guards_context(
    hass,
) -> None:
    coordinator = _coordinator(hass)
    coordinator._weekend_key = "meeting:10"
    coordinator._index_source_session = Mock(
        return_value={"Path": "2026/test/q", "Name": "Qualifying"}
    )
    coordinator._fetch_archive_context = AsyncMock()
    coordinator._maybe_schedule_archive_fetch(grid.CONTEXT_RACE)
    assert coordinator._archive_task is not None
    await coordinator._archive_task
    coordinator._fetch_archive_context.assert_awaited_once_with(
        grid.CONTEXT_RACE, "2026/test/q"
    )
    coordinator._maybe_schedule_archive_fetch(grid.CONTEXT_RACE)
    coordinator._fetch_archive_context.assert_awaited_once()

    coordinator._maybe_schedule_archive_fetch(grid.CONTEXT_NONE)
    coordinator._index_source_session.return_value = {"Path": ""}
    coordinator._archive_fetch_keys.clear()
    coordinator._maybe_schedule_archive_fetch(grid.CONTEXT_RACE)
    assert coordinator._archive_task.done()

    fetch = _coordinator(hass)
    fetch._fetch_stream = AsyncMock(return_value=None)
    await fetch._fetch_archive_context(grid.CONTEXT_NONE, "path")
    await fetch._fetch_archive_context(grid.CONTEXT_RACE, "")
    await fetch._fetch_archive_context(grid.CONTEXT_RACE, "path")
    assert fetch._qualifying_entries[grid.CONTEXT_RACE] == {}


def test_starting_grid_current_next_and_waiting_status_matrix(
    hass, monkeypatch
) -> None:
    coordinator = _coordinator(hass)
    monkeypatch.setattr(grid.dt_util, "utcnow", lambda: NOW)

    def item(name, session_type, start=None, end=None):
        return {
            "Name": name,
            "Type": session_type,
            "StartDate": start.isoformat() if start else None,
            "EndDate": end.isoformat() if end else None,
            "GmtOffset": "00:00:00",
        }

    future = item(
        "Qualifying",
        "Qualifying",
        NOW + timedelta(hours=4),
        NOW + timedelta(hours=5),
    )
    recent = item(
        "Practice 3",
        "Practice",
        NOW - timedelta(hours=5),
        NOW - timedelta(hours=4),
    )
    invalid = item("Invalid", "Other")
    coordinator._iter_index_sessions = Mock(
        return_value=iter([invalid, recent, future])
    )
    assert coordinator._current_or_next_index_session() is future
    coordinator._iter_index_sessions = Mock(return_value=iter([recent]))
    assert coordinator._current_or_next_index_session() is recent
    coordinator._iter_index_sessions = Mock(return_value=iter([invalid]))
    assert coordinator._current_or_next_index_session() is None

    coordinator._index_sessions_for_weekend = Mock(return_value=[])
    assert coordinator._detect_weekend_format("weekend") == (
        grid.WEEKEND_FORMAT_UNKNOWN
    )
    coordinator._index_sessions_for_weekend.return_value = [
        item("Qualifying", "Qualifying", NOW, NOW + timedelta(hours=1)),
        item("Race", "Race", NOW, NOW + timedelta(hours=2)),
    ]
    assert coordinator._detect_weekend_format("weekend") == (grid.WEEKEND_FORMAT_NORMAL)
    coordinator._index_sessions_for_weekend.return_value = []
    assert coordinator._initial_status_from_index(
        "weekend", grid.WEEKEND_FORMAT_NORMAL
    ) == (grid.STATUS_WAITING_QUALIFYING, grid.CONTEXT_RACE)

    race = item("Race", "Race", NOW + timedelta(hours=5), NOW + timedelta(hours=7))
    qualifying = item(
        "Qualifying",
        "Qualifying",
        NOW + timedelta(hours=2),
        NOW + timedelta(hours=3),
    )
    coordinator._index_sessions_for_weekend.return_value = [qualifying, race]
    assert coordinator._initial_status_from_index(
        "weekend", grid.WEEKEND_FORMAT_NORMAL
    ) == (grid.STATUS_WAITING_QUALIFYING, grid.CONTEXT_RACE)

    sprint_q = item(
        "Sprint Qualifying",
        "Qualifying",
        NOW + timedelta(hours=1),
        NOW + timedelta(hours=2),
    )
    sprint = item("Sprint", "Race", NOW + timedelta(hours=3), NOW + timedelta(hours=4))
    coordinator._index_sessions_for_weekend.return_value = [
        sprint_q,
        sprint,
        qualifying,
        race,
    ]
    assert coordinator._initial_status_from_index(
        "weekend", grid.WEEKEND_FORMAT_SPRINT
    ) == (grid.STATUS_WAITING_SPRINT_QUALIFYING, grid.CONTEXT_SPRINT)

    sprint_q["StartDate"] = (NOW - timedelta(minutes=5)).isoformat()
    sprint_q["EndDate"] = (NOW + timedelta(minutes=20)).isoformat()
    assert coordinator._initial_status_from_index(
        "weekend", grid.WEEKEND_FORMAT_SPRINT
    ) == (grid.STATUS_COLLECTING, grid.CONTEXT_SPRINT)

    sprint_q["EndDate"] = (NOW - timedelta(minutes=1)).isoformat()
    assert coordinator._initial_status_from_index(
        "weekend", grid.WEEKEND_FORMAT_SPRINT
    ) == (grid.STATUS_WAITING_SPRINT_QUALIFYING, grid.CONTEXT_SPRINT)
