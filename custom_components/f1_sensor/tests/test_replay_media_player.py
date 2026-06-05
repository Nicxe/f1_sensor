from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

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
