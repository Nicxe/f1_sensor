from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.components.media_player import (
    DATA_COMPONENT,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
)
from homeassistant.components.media_player.const import (
    ATTR_MEDIA_SEEK_POSITION,
    MediaPlayerEntityFeature,
)
from homeassistant.const import SERVICE_MEDIA_SEEK
from homeassistant.setup import async_setup_component
import pytest

from custom_components.f1_sensor import media_player as media_player_platform
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.media_player import F1ReplayMediaPlayer
from custom_components.f1_sensor.replay_mode import ReplayState


class _SessionManager:
    selected_session = SimpleNamespace(label="Test GP - Race", unique_id="test_race")

    def __init__(self) -> None:
        self._listeners = []

    def add_listener(self, callback):
        self._listeners.append(callback)

        def _unsub() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _unsub


class _Controller:
    def __init__(self, state: ReplayState = ReplayState.PAUSED) -> None:
        self.state = state
        self.session_manager = _SessionManager()
        self.async_seek_to_position = AsyncMock()
        self.async_play = AsyncMock()
        self.async_pause = AsyncMock()
        self.async_resume = AsyncMock()
        self.async_stop = AsyncMock()

    def get_playback_status(self) -> dict:
        return {
            "session_start_ms": 0,
            "playback_start_ms": 0,
            "position_ms": 10_000,
            "duration_ms": 90_000,
            "paused": self.state == ReplayState.PAUSED,
            "elapsed_s": 0,
        }

    def get_planned_playback_details(self) -> dict | None:
        return None


def _player(controller: _Controller) -> F1ReplayMediaPlayer:
    player = F1ReplayMediaPlayer(controller, "entry_replay_player", "entry", "F1")
    player._refresh_from_controller()
    return player


def test_replay_media_player_exposes_seek_feature() -> None:
    player = _player(_Controller())

    assert player.supported_features & MediaPlayerEntityFeature.SEEK


@pytest.mark.asyncio
async def test_replay_media_player_media_seek_delegates_to_controller() -> None:
    controller = _Controller()
    player = _player(controller)

    await player.async_media_seek(30)

    controller.async_seek_to_position.assert_awaited_once_with(30)


@pytest.mark.asyncio
async def test_replay_media_player_media_seek_clamps_to_duration() -> None:
    controller = _Controller()
    player = _player(controller)

    await player.async_media_seek(120)

    controller.async_seek_to_position.assert_awaited_once_with(90)


@pytest.mark.asyncio
async def test_replay_media_player_ignores_seek_when_not_loaded() -> None:
    controller = _Controller(ReplayState.IDLE)
    player = _player(controller)

    await player.async_media_seek(30)

    controller.async_seek_to_position.assert_not_awaited()


@pytest.mark.asyncio
async def test_media_player_media_seek_service_calls_entity(hass) -> None:
    assert await async_setup_component(hass, MEDIA_PLAYER_DOMAIN, {})
    component = hass.data[DATA_COMPONENT]
    controller = _Controller()
    player = _player(controller)

    await component.async_add_entities([player])
    await hass.async_block_till_done()

    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_MEDIA_SEEK,
        {
            "entity_id": player.entity_id,
            ATTR_MEDIA_SEEK_POSITION: 42,
        },
        blocking=True,
    )

    controller.async_seek_to_position.assert_awaited_once_with(42)


async def test_media_player_setup_requires_runtime_and_controller(hass) -> None:
    entry = SimpleNamespace(
        entry_id="entry",
        data={"sensor_name": "F1"},
        options={},
        runtime_data=None,
    )
    add_entities = Mock()
    await media_player_platform.async_setup_entry(hass, entry, add_entities)
    add_entities.assert_not_called()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"other": True}
    await media_player_platform.async_setup_entry(hass, entry, add_entities)
    add_entities.assert_not_called()

    controller = _Controller()
    hass.data[DOMAIN][entry.entry_id]["replay_controller"] = controller
    await media_player_platform.async_setup_entry(hass, entry, add_entities)
    added = add_entities.call_args.args[0]
    assert len(added) == 1
    assert added[0].entity_id == "media_player.f1_replay_player"


async def test_media_player_lifecycle_ticks_and_planned_timing(
    hass, monkeypatch
) -> None:
    controller = _Controller(ReplayState.PLAYING)
    controller.get_playback_status = Mock(
        return_value={
            "session_start_ms": 5_000,
            "playback_start_ms": 10_000,
            "position_ms": 20_000,
            "duration_ms": 0,
        }
    )
    controller.get_planned_playback_details = Mock(
        return_value={
            "session_start_ms": 5_000,
            "playback_start_ms": 10_000,
            "duration_ms": 70_000,
        }
    )
    cancel_tick = Mock()
    monkeypatch.setattr(
        media_player_platform,
        "async_track_time_interval",
        Mock(return_value=cancel_tick),
    )
    player = F1ReplayMediaPlayer(controller, "uid", "entry", "F1")
    player._update_tick()
    player.hass = hass
    player.entity_id = "media_player.test"
    player._safe_write_ha_state = Mock()

    await player.async_added_to_hass()
    assert player.state == "playing"
    assert player.media_duration == 60
    assert player.media_position == 10
    player._handle_update({})
    assert player._unsub_tick is cancel_tick
    player._handle_tick(None)
    player._safe_write_ha_state.assert_called()

    controller.state = ReplayState.IDLE
    player._handle_tick(None)
    player._update_tick()
    cancel_tick.assert_called_once()
    player._cancel_tick()


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (ReplayState.PAUSED, "paused"),
        (ReplayState.LOADING, "buffering"),
        (ReplayState.SEEKING, "buffering"),
        (ReplayState.IDLE, "idle"),
        (ReplayState.READY, "idle"),
    ],
)
def test_media_player_maps_replay_states(state, expected) -> None:
    player = _player(_Controller(state))
    assert player.state == expected
    if state in {ReplayState.PAUSED, ReplayState.READY}:
        assert player.media_duration == 90
    else:
        assert player.media_duration == 0


async def test_media_player_play_pause_seek_error_and_stop_paths() -> None:
    controller = _Controller(ReplayState.READY)
    player = _player(controller)
    player._safe_write_ha_state = Mock()
    await player.async_media_play()
    controller.async_play.assert_awaited_once()

    controller.state = ReplayState.PAUSED
    await player.async_media_play()
    controller.async_resume.assert_awaited_once()
    controller.async_resume.side_effect = RuntimeError("resume")
    await player.async_media_play()

    controller.state = ReplayState.PLAYING
    await player.async_media_pause()
    controller.async_pause.assert_awaited_once()
    controller.state = ReplayState.IDLE
    await player.async_media_pause()

    controller.state = ReplayState.PAUSED
    await player.async_media_seek(float("nan"))
    controller.async_seek_to_position.assert_awaited_with(0)
    controller.async_seek_to_position.side_effect = RuntimeError("seek")
    await player.async_media_seek(1)

    await player.async_media_stop()
    controller.async_stop.assert_awaited_once()
