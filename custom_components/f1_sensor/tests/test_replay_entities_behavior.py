"""Behavior tests for replay controls exposed as Home Assistant entities."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.f1_sensor.const import (
    DOMAIN,
    REPLAY_START_REFERENCE_FORMATION,
    REPLAY_START_REFERENCE_SESSION,
)
from custom_components.f1_sensor.replay_entities import (
    F1ReplayBackButton,
    F1ReplayForwardButton,
    F1ReplayLoadButton,
    F1ReplayPauseButton,
    F1ReplayPlayButton,
    F1ReplayRefreshButton,
    F1ReplaySessionSelect,
    F1ReplayStartReferenceSelect,
    F1ReplayStatusSensor,
    F1ReplayStopButton,
    F1ReplayYearSelect,
)
from custom_components.f1_sensor.replay_mode import ReplayState


class _Manager:
    def __init__(self) -> None:
        self.selected_year = 2026
        self.year_options = [2025, 2026]
        self.available_sessions = [
            SimpleNamespace(label="Test GP - Race", unique_id="race-id")
        ]
        self.selected_session = self.available_sessions[0]
        self.index_status = "ready"
        self.listeners = []
        self.async_fetch_sessions = AsyncMock()
        self.async_set_year = AsyncMock()
        self.async_select_session = AsyncMock()

    def add_listener(self, callback):
        self.listeners.append(callback)
        return Mock()


class _Controller:
    def __init__(self, state=ReplayState.SELECTED) -> None:
        self.state = state
        self.session_manager = _Manager()
        for name in (
            "async_stop",
            "async_prepare_and_load_session",
            "async_play",
            "async_resume",
            "async_pause",
            "async_seek_by",
        ):
            setattr(self, name, AsyncMock())
        self.playback = {
            "position_ms": 50_000,
            "session_start_ms": 10_000,
            "playback_start_ms": 20_000,
            "duration_ms": 100_000,
            "paused": False,
        }
        self.planned = None

    def get_playback_status(self):
        return self.playback

    def get_planned_playback_details(self):
        return self.planned


def _quiet(entity):
    entity.async_write_ha_state = Mock()
    return entity


async def test_replay_year_select_handles_year_state_and_lifecycle() -> None:
    controller = _Controller()
    entity = _quiet(F1ReplayYearSelect(controller, "uid", "entry", "F1"))
    await entity.async_added_to_hass()
    assert entity.options == ["2025", "2026"]
    entity._handle_update({"selected_year": 2025})
    assert entity.current_option == "2025"
    entity._handle_update({})
    assert entity.current_option == "2026"

    await entity.async_select_option("invalid")
    controller.state = ReplayState.LOADING
    await entity.async_select_option("2024")
    controller.session_manager.async_set_year.assert_not_awaited()

    controller.state = ReplayState.PLAYING
    await entity.async_select_option("2025")
    controller.async_stop.assert_awaited_once()
    controller.session_manager.async_set_year.assert_awaited_once_with(2025)

    controller.state = ReplayState.IDLE
    await entity.async_select_option("2026")
    controller.session_manager.async_fetch_sessions.assert_awaited_once_with(2026)
    await entity.async_will_remove_from_hass()
    assert entity._unsub is None


@pytest.mark.parametrize(
    ("status", "placeholder"),
    [
        ("no_data", "No data for 2026"),
        ("error", "Session list unavailable"),
        ("loading", "No sessions for 2026"),
    ],
)
async def test_replay_session_select_builds_options_and_placeholders(
    status, placeholder
) -> None:
    controller = _Controller()
    entity = _quiet(F1ReplaySessionSelect(controller, "uid", "entry", "F1"))
    await entity.async_added_to_hass()
    assert entity.options == ["Test GP - Race"]
    await entity.async_select_option("Test GP - Race")
    controller.session_manager.async_select_session.assert_awaited_once_with("race-id")
    await entity.async_select_option("unknown")

    controller.session_manager.available_sessions = []
    controller.session_manager.index_status = status
    entity._handle_update({})
    assert entity.options == [placeholder]
    assert entity.current_option == placeholder
    entity._handle_update({"selected_session": "Selected"})
    assert entity.current_option == "Selected"
    await entity.async_will_remove_from_hass()


async def test_replay_session_select_handles_selection_failure() -> None:
    controller = _Controller()
    controller.session_manager.async_select_session.side_effect = ValueError("gone")
    entity = _quiet(F1ReplaySessionSelect(controller, "uid", "entry", "F1"))
    entity._rebuild_options()
    await entity.async_select_option("Test GP - Race")
    controller.session_manager.available_sessions = []
    entity._placeholder_option = None
    entity._options = ["temporary"]
    entity._session_map = {}
    entity._rebuild_options = Mock()
    entity._handle_update({"selected_session": None})
    assert entity.current_option is None


async def test_replay_start_reference_select_maps_values_and_lifecycle(hass) -> None:
    controller = SimpleNamespace(
        current="unknown",
        add_listener=Mock(return_value=Mock()),
        async_set_reference=AsyncMock(),
    )
    entity = _quiet(F1ReplayStartReferenceSelect(controller, "uid", "entry", "F1"))
    assert entity.current_option == "Formation start (race/sprint)"
    assert entity.options == ["Session live", "Formation start (race/sprint)"]
    await entity.async_added_to_hass()
    await entity.async_added_to_hass()
    controller.add_listener.assert_called_once()
    await entity.async_select_option("Session live")
    controller.async_set_reference.assert_awaited_with(
        REPLAY_START_REFERENCE_SESSION, source="select_entity"
    )
    await entity.async_select_option("unknown")
    controller.async_set_reference.assert_awaited_with(
        REPLAY_START_REFERENCE_FORMATION, source="select_entity"
    )
    entity.hass = hass
    entity._handle_reference_update("unknown")
    await entity.async_will_remove_from_hass()
    assert entity._unsub is None


async def test_replay_buttons_delegate_for_supported_states() -> None:
    controller = _Controller(ReplayState.SELECTED)
    load = F1ReplayLoadButton(controller, "load", "entry", "F1")
    await load.async_press()
    controller.async_prepare_and_load_session.assert_awaited_once()
    controller.async_prepare_and_load_session.side_effect = RuntimeError("load")
    await load.async_press()

    play = F1ReplayPlayButton(controller, "play", "entry", "F1")
    controller.state = ReplayState.READY
    await play.async_press()
    controller.async_play.assert_awaited_once()
    controller.state = ReplayState.PAUSED
    await play.async_press()
    controller.async_resume.assert_awaited_once()
    controller.async_resume.side_effect = RuntimeError("resume")
    await play.async_press()

    pause = F1ReplayPauseButton(controller, "pause", "entry", "F1")
    controller.state = ReplayState.PLAYING
    await pause.async_press()
    controller.async_pause.assert_awaited_once()
    controller.state = ReplayState.IDLE
    await pause.async_press()

    stop = F1ReplayStopButton(controller, "stop", "entry", "F1")
    await stop.async_press()
    controller.async_stop.assert_awaited()

    back = F1ReplayBackButton(controller, "back", "entry", "F1")
    forward = F1ReplayForwardButton(controller, "forward", "entry", "F1")
    await back.async_press()
    await forward.async_press()
    controller.async_seek_by.assert_not_awaited()
    controller.state = ReplayState.READY
    await back.async_press()
    await forward.async_press()
    assert [call.args[0] for call in controller.async_seek_by.await_args_list] == [
        -30,
        30,
    ]

    refresh = F1ReplayRefreshButton(controller, "refresh", "entry", "F1")
    await refresh.async_press()
    controller.session_manager.async_fetch_sessions.assert_awaited()


async def test_replay_buttons_block_active_calibration(hass) -> None:
    controller = _Controller(ReplayState.SELECTED)
    manager = SimpleNamespace(
        snapshot=lambda: {"mode": "running"},
        async_blocked_by_replay=AsyncMock(),
    )
    hass.data.setdefault(DOMAIN, {})["entry"] = {"calibration_manager": manager}
    for entity, action in (
        (F1ReplayLoadButton(controller, "load", "entry", "F1"), "load"),
        (F1ReplayPlayButton(controller, "play", "entry", "F1"), "play"),
    ):
        entity.hass = hass
        await entity._block_calibration_for_replay(action)
    assert [
        call.kwargs["source"]
        for call in manager.async_blocked_by_replay.await_args_list
    ] == [
        "replay_load",
        "replay_play",
    ]

    hass.data[DOMAIN]["entry"] = {}
    load = F1ReplayLoadButton(controller, "load2", "entry", "F1")
    load.hass = hass
    await load._block_calibration_for_replay("load")
    entity = F1ReplayPlayButton(controller, "play2", "entry", "F1")
    entity.hass = hass
    await entity._block_calibration_for_replay("play")


async def test_replay_status_sensor_reports_progress_and_planned_duration() -> None:
    controller = _Controller()
    sensor = _quiet(F1ReplayStatusSensor(controller, "uid", "entry", "F1"))
    await sensor.async_added_to_hass()
    sensor._handle_update(
        {
            "state": "playing",
            "selected_session": "Test GP",
            "download_progress": 0.456,
            "sessions_count": 2,
            "selected_year": 2026,
            "index_year": 2026,
            "index_status": "ready",
        }
    )
    assert sensor.native_value == "playing"
    assert sensor.extra_state_attributes["download_progress"] == 45.6
    assert sensor.extra_state_attributes["playback_position_formatted"] == "00:00:30"

    controller.playback["duration_ms"] = 0
    controller.planned = {
        "session_start_ms": 5_000,
        "playback_start_ms": 10_000,
        "duration_ms": 70_000,
    }
    sensor._handle_update({})
    assert sensor.extra_state_attributes["playback_total_s"] == 60
    assert sensor._format_time(-1) == "00:00:00"
    assert sensor._format_time(3661) == "01:01:01"
    await sensor.async_will_remove_from_hass()
    assert sensor._unsub is None
