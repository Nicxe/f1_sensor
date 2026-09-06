"""Branch coverage for replay controller orchestration and safeguards."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.replay_mode import (
    REPLAY_START_REFERENCE_FORMATION,
    ReplayController,
    ReplayIndex,
    ReplayState,
)


class _Bus:
    def __init__(self) -> None:
        self._transport_factory = Mock(name="original_factory")
        self._running = False
        self.async_close = AsyncMock()
        self.swap_transport = AsyncMock()
        self.inject_message = Mock()
        self.set_heartbeat_expectation = Mock()


def _index(tmp_path: Path) -> ReplayIndex:
    frames = tmp_path / "frames.jsonl"
    frames.write_text(
        "\n".join(
            [
                "bad",
                '{"t":5,"s":"Old","p":{}}',
                '{"t":20,"s":"TrackStatus","p":{"Status":"2"}}',
                '{"t":"bad","s":"Bad","p":{}}',
                '{"t":40,"s":"SessionStatus","p":{"Status":"Started"}}',
            ]
        ),
        encoding="utf-8",
    )
    return ReplayIndex(
        session_id="session",
        total_frames=4,
        duration_ms=100,
        session_started_at_ms=20,
        frames_file=frames,
        index_file=tmp_path / "index.json",
        formation_started_at_ms=10,
        initial_state={"SessionStatus": {"Status": "Started"}},
        formation_initial_state={"SessionStatus": {"Status": "Inactive"}},
    )


def _controller(hass, *, live_state=None, start_reference="session"):
    bus = _Bus()
    ended = Mock()
    controller = ReplayController(
        hass,
        "entry",
        AsyncMock(),
        bus,
        live_state=live_state,
        start_reference_controller=SimpleNamespace(current=start_reference),
        formation_tracker=None,
        on_replay_ended=ended,
    )
    hass.data.setdefault(DOMAIN, {})["entry"] = {"replay_controller": controller}
    return controller, bus, ended


def test_replay_controller_offsets_factory_and_status_guards(hass, tmp_path) -> None:
    controller, _bus, _ended = _controller(
        hass, start_reference=REPLAY_START_REFERENCE_FORMATION
    )
    index = _index(tmp_path)
    assert controller.get_planned_playback_details() == {}
    assert controller.get_playback_status() == {
        "position_ms": 0,
        "duration_ms": 0,
        "paused": False,
        "elapsed_s": 0,
    }
    start, state = controller._resolve_playback_start(index, log=True)
    assert start == 10
    assert state == {"SessionStatus": {"Status": "Inactive"}}
    controller.session_manager._loaded_index = index
    controller._pending_start_ms = 500
    assert controller._resolve_requested_start_ms(index) == 100
    assert controller.get_planned_playback_details()["playback_start_ms"] == 10
    assert controller.get_playback_status()["position_ms"] == 100

    with pytest.raises(RuntimeError, match="not available"):
        controller._replay_transport_factory()
    controller._replay_active = True
    controller._transport = SimpleNamespace(_closed=True)
    with pytest.raises(RuntimeError, match="playback complete"):
        controller._replay_transport_factory()
    assert controller._replay_active is False


async def test_prepare_and_load_releases_failed_lock_and_keeps_ready(hass) -> None:
    live_state = SimpleNamespace(set_state=Mock())
    controller, bus, ended = _controller(hass, live_state=live_state)
    with pytest.raises(RuntimeError, match="No session selected"):
        await controller.async_prepare_and_load_session()

    controller.session_manager._state = ReplayState.SELECTED
    controller._reset_track_map_runtime = Mock()

    async def fail_load():
        controller.session_manager._state = ReplayState.SELECTED

    controller.session_manager.async_load_session = AsyncMock(side_effect=fail_load)
    await controller.async_prepare_and_load_session()
    controller._reset_track_map_runtime.assert_called_once()
    bus.async_close.assert_awaited_once()
    assert live_state.set_state.call_args_list[-1].args == (False, "replay-stopped")
    assert ended.called

    ended.reset_mock()
    live_state.set_state.reset_mock()
    controller.session_manager._state = ReplayState.SELECTED

    async def ready_load():
        controller.session_manager._state = ReplayState.READY

    controller.session_manager.async_load_session = AsyncMock(side_effect=ready_load)
    await controller.async_prepare_and_load_session()
    assert live_state.set_state.call_args_list[-1].args == (
        False,
        "replay-preparing",
    )
    ended.assert_not_called()


async def test_replay_reset_track_map_prepare_and_initial_injection(
    hass, tmp_path
) -> None:
    controller, _bus, _ended = _controller(hass)
    index = _index(tmp_path)
    sync_callback = Mock()
    async_callback = AsyncMock()
    failed_callback = Mock(side_effect=RuntimeError)
    reset = Mock()
    prepare = AsyncMock()
    hass.data[DOMAIN]["entry"].update(
        {
            "replay_reset_callbacks": [
                sync_callback,
                async_callback,
                failed_callback,
            ],
            "track_map_replay_adapter": SimpleNamespace(
                reset_for_replay=reset,
                async_prepare_replay_index=prepare,
            ),
        }
    )
    await controller._run_replay_reset_callbacks()
    assert sync_callback.called
    async_callback.assert_awaited_once()
    controller._reset_track_map_runtime()
    assert reset.called
    await controller._prepare_track_map_replay_index(index)
    prepare.assert_awaited_once_with(index)

    controller._live_bus.inject_message.reset_mock()
    controller._inject_initial_state({"TrackStatus": {"Status": "2"}, "bad": "skip"})
    controller._live_bus.inject_message.assert_called_once_with(
        "TrackStatus", {"Status": "2"}
    )
    controller._inject_initial_state(None)
    controller._inject_formation_ready_if_applicable(index)

    hass.data[DOMAIN]["entry"]["track_map_replay_adapter"] = SimpleNamespace(
        reset_for_replay=Mock(side_effect=RuntimeError),
        async_prepare_replay_index=AsyncMock(side_effect=RuntimeError),
    )
    controller._reset_track_map_runtime()
    await controller._prepare_track_map_replay_index(index)


async def test_controller_initialize_play_resume_stop_and_close_guards(
    hass, tmp_path
) -> None:
    live_state = SimpleNamespace(set_state=Mock())
    controller, bus, ended = _controller(hass, live_state=live_state)
    controller.session_manager.async_initialize = AsyncMock()
    await controller.async_initialize()
    controller.session_manager.async_initialize.assert_awaited_once()

    with pytest.raises(RuntimeError, match="not ready"):
        await controller.async_play()
    controller.session_manager._state = ReplayState.READY
    with pytest.raises(RuntimeError, match="No replay index"):
        await controller.async_play()

    transport = SimpleNamespace(resume=Mock(), close=AsyncMock(), _closed=False)
    controller._transport = transport
    controller.session_manager._state = ReplayState.PAUSED
    await controller.async_resume()
    assert transport.resume.called
    assert controller.state is ReplayState.PLAYING

    original = Mock()
    bus._transport_factory = Mock()
    controller._original_transport_factory = original
    controller._replay_active = True
    controller.session_manager.async_unload = AsyncMock()
    controller._reset_track_map_runtime = Mock()
    controller._reset_formation_tracker = Mock()
    await controller.async_stop()
    assert bus._transport_factory is original
    transport.close.assert_awaited_once()
    bus.async_close.assert_awaited_once()
    assert live_state.set_state.call_args_list[-1].args == (False, "replay-stopped")
    assert ended.called
    controller.session_manager.async_unload.assert_awaited_once()

    controller.async_stop = AsyncMock()
    controller._listeners.append(Mock())
    await controller.async_close()
    controller.async_stop.assert_awaited_once()
    assert controller._listeners == []


def test_read_frames_range_and_formation_reset_edges(hass, tmp_path) -> None:
    controller, _bus, _ended = _controller(hass)
    index = _index(tmp_path)
    frames = controller._read_frames_range_sync(
        index.frames_file,
        start_exclusive_ms=10,
        end_inclusive_ms=30,
    )
    assert [(frame.timestamp_ms, frame.stream) for frame in frames] == [
        (20, "TrackStatus")
    ]
    with pytest.raises(FileNotFoundError):
        controller._read_frames_range_sync(
            tmp_path / "missing",
            start_exclusive_ms=0,
            end_inclusive_ms=1,
        )

    tracker = SimpleNamespace(reset=Mock(side_effect=RuntimeError))
    controller._formation_tracker = tracker
    controller._reset_formation_tracker()
    assert tracker.reset.called
