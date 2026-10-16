"""Behavior matrix for starting-grid lifecycle and parsing helpers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

from custom_components.f1_sensor import starting_grid as grid
from custom_components.f1_sensor.const import DOMAIN


def _index_data(now: datetime) -> dict:
    def session(name, session_type, start_hours, end_hours, path):
        return {
            "Name": name,
            "Type": session_type,
            "StartDate": (now + timedelta(hours=start_hours)).isoformat(),
            "EndDate": (now + timedelta(hours=end_hours)).isoformat(),
            "GmtOffset": "00:00:00",
            "Path": path,
        }

    return {
        "Meetings": [
            {
                "Key": 10,
                "Name": "Test GP",
                "Sessions": [
                    session("Sprint Qualifying", "Qualifying", -3, -2, "2026/test/sq"),
                    session("Sprint", "Race", -1, 0, "2026/test/sprint"),
                    session("Qualifying", "Qualifying", 1, 2, "2026/test/q"),
                    session("Race", "Race", 3, 5, "2026/test/race"),
                ],
            }
        ]
    }


def _coordinator(hass, *, data=None, bus=None, live_reason=None):
    session_coord = SimpleNamespace(data=data)
    return grid.StartingGridCoordinator(
        hass,
        session_coord,
        bus=bus,
        session=MagicMock(),
        live_state=SimpleNamespace(reason=live_reason),
    )


async def test_starting_grid_first_refresh_subscribes_and_closes(hass) -> None:
    callbacks = {}
    removers = []

    class Bus:
        def subscribe(self, stream, callback):
            callbacks[stream] = callback
            remove = Mock()
            removers.append(remove)
            return remove

    coordinator = _coordinator(hass, data={}, bus=Bus())
    await coordinator.async_config_entry_first_refresh()
    assert set(callbacks) == {
        "SessionInfo",
        "SessionStatus",
        "DriverList",
        "TimingData",
        "TimingAppData",
    }
    await coordinator.async_close()
    assert all(remove.called for remove in removers)

    coordinator = _coordinator(hass, data={}, bus=None)
    await coordinator.async_config_entry_first_refresh()
    assert coordinator._unsubs == []


async def test_starting_grid_reset_replay_and_no_spoiler_guards(hass) -> None:
    coordinator = _coordinator(hass, data={}, live_reason="replay")
    coordinator._weekend_format = grid.WEEKEND_FORMAT_SPRINT
    coordinator._archive_task = asyncio.create_task(asyncio.sleep(60))
    coordinator.reset_runtime_state("test")
    assert coordinator._state["status"] == grid.STATUS_WAITING_SPRINT_QUALIFYING
    assert coordinator._state["cleared_reason"] == "test"
    assert coordinator._archive_task is None
    assert coordinator._is_replay_active() is True
    assert coordinator._is_no_spoiler_active() is False
    assert await coordinator._async_update_data() is coordinator._state

    coordinator._live_state.reason = None
    hass.data.setdefault(DOMAIN, {})["no_spoiler_manager"] = SimpleNamespace(
        is_active=True
    )
    assert coordinator._is_no_spoiler_active() is True
    previous = coordinator.data
    coordinator._publish()
    assert coordinator.data is previous
    assert await coordinator._async_update_data() is coordinator._state

    class BrokenRoot:
        def get(self, _key):
            raise RuntimeError("broken state")

    hass.data[DOMAIN] = BrokenRoot()
    assert coordinator._is_no_spoiler_active() is False

    coordinator._current_or_next_index_session = lambda: {"Name": "Race"}
    coordinator._sync_from_index_if_idle()
    assert coordinator._weekend_key is None


def test_starting_grid_index_and_weekend_classification(hass, monkeypatch) -> None:
    now = datetime(2026, 9, 1, 12, tzinfo=UTC)
    monkeypatch.setattr(grid.dt_util, "utcnow", lambda: now)
    coordinator = _coordinator(hass, data=_index_data(now))
    sessions = list(coordinator._iter_index_sessions())
    assert len(sessions) == 4
    assert sessions[0]["_meeting"]["Name"] == "Test GP"
    assert coordinator._weekend_key_from_index_session(sessions[0]) == "meeting:10"
    assert (
        coordinator._weekend_key_from_session_info({"Meeting": {"Key": 10}})
        == "meeting:10"
    )
    assert coordinator._weekend_key_from_path("2026/test/race") == "path:2026/test"
    assert coordinator._weekend_key_from_path("single") == "path:single"
    assert coordinator._weekend_key_from_path(None) is None
    assert (
        coordinator._detect_weekend_format("meeting:10") == grid.WEEKEND_FORMAT_SPRINT
    )
    assert coordinator._detect_weekend_format(None) == grid.WEEKEND_FORMAT_UNKNOWN
    coordinator._weekend_key = "meeting:10"
    assert coordinator._index_source_session(grid.CONTEXT_SPRINT)["Name"] == (
        "Sprint Qualifying"
    )
    assert coordinator._index_source_session(grid.CONTEXT_RACE)["Name"] == "Qualifying"
    assert coordinator._current_or_next_index_session()["Name"] == "Sprint Qualifying"

    assert (
        coordinator._infer_weekend_format_from_session(
            {"Name": "Sprint", "Type": "Race"}
        )
        == grid.WEEKEND_FORMAT_SPRINT
    )
    coordinator._weekend_format = grid.WEEKEND_FORMAT_UNKNOWN
    assert (
        coordinator._infer_weekend_format_from_session({"Name": "Race", "Type": "Race"})
        == grid.WEEKEND_FORMAT_NORMAL
    )
    assert (
        coordinator._infer_weekend_format_from_session(
            {"Name": "Practice 1", "Type": "Practice"}
        )
        == grid.WEEKEND_FORMAT_UNKNOWN
    )

    assert coordinator._initial_status_from_index(
        "meeting:10", grid.WEEKEND_FORMAT_SPRINT
    ) == (grid.STATUS_COLLECTING, grid.CONTEXT_SPRINT)


def test_starting_grid_stream_parsing_and_static_helpers(hass) -> None:
    coordinator = _coordinator(hass, data=None)
    assert list(coordinator._iter_index_sessions()) == []
    coordinator._session_coord.data = {"Meetings": "bad"}
    assert list(coordinator._iter_index_sessions()) == []
    coordinator._session_coord.data = {
        "Meetings": {
            "1": {"Sessions": {"1": {"Name": "Race"}, "bad": "skip"}},
            "bad": "skip",
        }
    }
    assert len(list(coordinator._iter_index_sessions())) == 1

    payloads = list(
        coordinator._iter_json_stream(
            '\nplain\n00:00:01 {"ok":1}\n00:00:02 {bad\n00:00:03 [1]\n'
        )
    )
    assert payloads == [{"ok": 1}]

    kinds = {
        coordinator._session_kind_from_values("Sprint Shootout", "Qualifying"),
        coordinator._session_kind_from_values("Qualifying", "Qualifying"),
        coordinator._session_kind_from_values("Sprint", "Race"),
        coordinator._session_kind_from_values("Race", "Race"),
        coordinator._session_kind_from_values("Practice 1", "Practice"),
        coordinator._session_kind_from_values("Other", "Other"),
    }
    assert kinds == {
        grid.SESSION_KIND_SPRINT_QUALIFYING,
        grid.SESSION_KIND_QUALIFYING,
        grid.SESSION_KIND_SPRINT,
        grid.SESSION_KIND_RACE,
        grid.SESSION_KIND_PRACTICE,
        grid.SESSION_KIND_OTHER,
    }
    coordinator._current_session = {"name": "Race", "type": "Race"}
    assert coordinator._current_session_kind() == grid.SESSION_KIND_RACE
    assert coordinator._status_from_payload({"Message": " Started "}) == "Started"
    assert coordinator._status_from_payload({}) is None
    assert coordinator._session_name({"Name": 1}) == "1"
    assert coordinator._session_key({"Key": 2}) == "2"
    assert coordinator._meeting_name({"Meeting": {"OfficialName": "GP"}}) == "GP"
    assert coordinator._meeting_name({}) is None
    assert coordinator._index_meeting_name({"_meeting": {"OfficialName": "GP"}}) == "GP"
    assert coordinator._index_meeting_name({}) is None
    assert coordinator._target_session_name(grid.CONTEXT_SPRINT) == "Sprint"
    assert coordinator._target_session_name(grid.CONTEXT_RACE) == "Race"
    assert coordinator._target_session_name(grid.CONTEXT_NONE) is None
    assert coordinator._source_session_name(grid.CONTEXT_SPRINT) == "Sprint Qualifying"
    assert coordinator._source_session_name(grid.CONTEXT_RACE) == "Qualifying"
    assert coordinator._source_session_name(grid.CONTEXT_NONE) is None


def test_starting_grid_lap_segments_numbers_colors_and_dates(hass) -> None:
    coordinator = _coordinator(hass)
    segments = coordinator._extract_segment_times(
        {
            "0": {"Value": "1:20.000", "Lap": "3"},
            "1": {},
            "bad": {"Value": "1:21"},
            "4": {"Value": "1:22"},
        },
        grid.CONTEXT_RACE,
    )
    assert segments == [
        {"segment": "Q1", "time": "1:20.000", "time_secs": 80.0, "lap": 3}
    ]
    assert (
        coordinator._extract_segment_times([{"Value": "55.5"}], grid.CONTEXT_SPRINT)[0][
            "segment"
        ]
        == "SQ1"
    )
    assert coordinator._extract_segment_times("bad", grid.CONTEXT_RACE) == []
    assert coordinator._lap_payload(None) is None
    assert coordinator._lap_payload({}) is None
    assert coordinator._parse_lap_time_secs(None) is None
    assert coordinator._parse_lap_time_secs("bad") is None
    assert coordinator._parse_lap_time_secs("59.5") == 59.5
    assert coordinator._parse_int(None) is None
    assert coordinator._parse_int(2) == 2
    assert coordinator._parse_int("2.0") == 2
    assert coordinator._parse_int("bad") is None
    assert coordinator._normalize_team_color(None) is None
    assert coordinator._normalize_team_color(" ff0000 ") == "#ff0000"
    assert coordinator._normalize_team_color("#00ff00") == "#00ff00"
    assert coordinator._parse_session_datetime(None, None) is None
    assert coordinator._parse_session_datetime("bad", None) is None
    assert coordinator._parse_session_datetime(
        "2026-09-01T12:00:00", "+02:30"
    ) == datetime(2026, 9, 1, 9, 30, tzinfo=UTC)
    assert coordinator._parse_session_datetime(
        "2026-09-01T12:00:00Z", None
    ) == datetime(2026, 9, 1, 12, tzinfo=UTC)


async def test_starting_grid_archive_fetch_failure_is_nonfatal(
    hass, monkeypatch
) -> None:
    coordinator = _coordinator(hass)
    monkeypatch.setattr(grid, "fetch_text", AsyncMock(side_effect=RuntimeError("down")))
    assert await coordinator._fetch_stream("2026/test/race/", "TimingData") is None

    monkeypatch.setattr(grid, "fetch_text", AsyncMock(return_value="data"))
    assert await coordinator._fetch_stream("/2026/test/race/", "TimingData") == "data"


async def test_starting_grid_recovers_duplicate_positions_from_pre_start_archive(
    hass,
) -> None:
    """Use archived pre-start line positions when live GridPos values collide."""
    coordinator = _coordinator(hass)
    path = "2026/test/race"
    coordinator._current_session = {
        "path": path,
        "key": "race-key",
        "name": "Race",
        "type": "Race",
    }
    coordinator._current_status = "Started"
    coordinator._confirmed_grid_positions[grid.CONTEXT_RACE] = {
        "1": (1, None),
        "2": (1, None),
    }
    coordinator._fetch_stream = AsyncMock(
        side_effect=[
            "\n".join(
                [
                    '00:00:00.000 {"Status":"Inactive"}',
                    '00:01:00.000 {"Status":"Started"}',
                ]
            ),
            "\n".join(
                [
                    '00:00:30.000 {"Lines":{"1":{"GridPos":1,"Line":5},"2":{"GridPos":1,"Line":2}}}',
                    '00:01:00.000 {"Lines":{"1":{"GridPos":1,"Line":1}}}',
                ]
            ),
        ]
    )

    await coordinator._recover_grid_from_archive(grid.CONTEXT_RACE, path, "race-key")

    assert coordinator._confirmed_grid_positions[grid.CONTEXT_RACE] == {
        "1": (1, 5),
        "2": (1, 2),
    }
    assert [row["grid_position"] for row in coordinator.data["grid"]] == [2, 5]
    assert coordinator.data["status"] == grid.STATUS_CONFIRMED
    assert coordinator._fetch_stream.await_args_list[0].kwargs == {
        "force_refresh": True
    }


async def test_starting_grid_schedules_one_live_recovery_per_session(hass) -> None:
    """Avoid duplicate archive requests while a live session has the same path."""
    coordinator = _coordinator(hass)
    coordinator._current_session = {"path": "2026/test/race", "key": "race-key"}
    coordinator._recover_grid_from_archive = AsyncMock()

    coordinator._maybe_schedule_grid_recovery(grid.CONTEXT_RACE)
    coordinator._maybe_schedule_grid_recovery(grid.CONTEXT_RACE)
    await hass.async_block_till_done()

    coordinator._recover_grid_from_archive.assert_awaited_once_with(
        grid.CONTEXT_RACE, "2026/test/race", "race-key"
    )


async def test_starting_grid_cancels_recovery_tasks_when_context_changes(hass) -> None:
    """Do not retain an archive recovery after resetting the active context."""
    coordinator = _coordinator(hass)
    coordinator._grid_recovery_task = asyncio.create_task(asyncio.sleep(60))
    await coordinator.async_close()
    assert coordinator._grid_recovery_task is None

    coordinator._grid_recovery_task = asyncio.create_task(asyncio.sleep(60))
    coordinator.reset_runtime_state()
    assert coordinator._grid_recovery_task is None

    coordinator._grid_recovery_task = asyncio.create_task(asyncio.sleep(60))
    coordinator._clear_active_grid(
        "session_complete",
        next_status=grid.STATUS_COMPLETED,
        next_context=grid.CONTEXT_NONE,
        clear_context_data=grid.CONTEXT_RACE,
    )
    assert coordinator._grid_recovery_task is None

    coordinator._archive_task = asyncio.create_task(asyncio.sleep(60))
    coordinator._grid_recovery_task = asyncio.create_task(asyncio.sleep(60))
    coordinator._reset_for_new_weekend("meeting:20", {"Name": "Race", "Type": "Race"})
    assert coordinator._archive_task is None
    assert coordinator._grid_recovery_task is None
    await asyncio.sleep(0)


def test_starting_grid_rebuilds_an_unavailable_live_grid(hass) -> None:
    """A fresh live status rebuilds a grid once the duplicate data is resolved."""
    coordinator = _coordinator(hass)
    coordinator._current_status = "Started"
    coordinator._current_session = {"name": "Race", "type": "Race"}
    coordinator._state.update(
        {"status": grid.STATUS_UNAVAILABLE, "grid_context": grid.CONTEXT_RACE}
    )
    coordinator._confirmed_grid_positions[grid.CONTEXT_RACE] = {"1": (1, 1)}

    coordinator._apply_session_lifecycle()

    assert coordinator.data["status"] == grid.STATUS_CONFIRMED
    assert coordinator.data["grid_context"] == grid.CONTEXT_RACE

    coordinator._current_session = {"name": "Sprint", "type": "Race"}
    coordinator._state.update(
        {"status": grid.STATUS_UNAVAILABLE, "grid_context": grid.CONTEXT_SPRINT}
    )
    coordinator._confirmed_grid_positions[grid.CONTEXT_SPRINT] = {"2": (2, 2)}
    coordinator._apply_session_lifecycle()

    assert coordinator.data["status"] == grid.STATUS_CONFIRMED
    assert coordinator.data["grid_context"] == grid.CONTEXT_SPRINT


def test_starting_grid_ignores_non_qualifying_or_replay_live_events(hass) -> None:
    """Only live qualifying timing can update the provisional grid."""
    coordinator = _coordinator(hass)
    coordinator._reset_for_new_weekend = Mock()
    coordinator._on_session_info(
        {
            "Meeting": {"Key": 20},
            "Name": "Race",
            "Type": "Race",
            "Path": "2026/test/race",
            "Status": "Inactive",
        }
    )
    coordinator._reset_for_new_weekend.assert_called_once()

    coordinator._current_status = None
    coordinator._apply_session_lifecycle()

    replay = _coordinator(hass, live_reason="replay")
    replay._on_session_status({"Status": "Started"})
    replay._on_driver_list({"1": {}})
    replay._on_timing_data({"Lines": {}})

    coordinator._current_session = {"name": "Race", "type": "Race"}
    coordinator._current_status = "Started"
    coordinator._on_timing_data({"Lines": {}})

    coordinator._current_session = {"name": "Qualifying", "type": "Qualifying"}
    coordinator._on_timing_app_data({"Lines": {}})

    coordinator._current_session = {"name": "Qualifying", "type": "Qualifying"}
    coordinator._current_status = "Finished"
    coordinator._merge_timing_data = Mock(return_value=True)
    coordinator._build_provisional_grid = Mock()
    coordinator._on_timing_data({"Lines": {}})
    coordinator._build_provisional_grid.assert_called_once_with(
        grid.CONTEXT_RACE, source=grid.SOURCE_LIVE_QUALIFYING
    )
