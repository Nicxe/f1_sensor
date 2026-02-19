"""Replay mode media player entity for F1 Sensor."""

from __future__ import annotations

import datetime
import logging

from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import (
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import F1AuxEntity
from .replay_mode import ReplayController, ReplayState

_LOGGER = logging.getLogger(__name__)

_REPLAY_TICK_INTERVAL = datetime.timedelta(seconds=1)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up replay media player entity."""
    registry = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not registry:
        return

    replay_controller: ReplayController | None = registry.get("replay_controller")
    if replay_controller is None:
        return

    name = entry.data.get("sensor_name", "F1")
    async_add_entities(
        [
            F1ReplayMediaPlayer(
                replay_controller,
                f"{name} Replay Player",
                f"{entry.entry_id}_replay_player",
                entry.entry_id,
                name,
            )
        ]
    )


class F1ReplayMediaPlayer(F1AuxEntity, MediaPlayerEntity):
    """Media player entity exposing replay progress and controls."""

    _device_category = "system"
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
    )
    _attr_icon = "mdi:play-circle"
    _attr_should_poll = False

    def __init__(
        self,
        controller: ReplayController,
        sensor_name: str,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, sensor_name, unique_id, entry_id, device_name)
        MediaPlayerEntity.__init__(self)
        self._controller = controller
        self._unsub_state = None
        self._unsub_tick = None
        self._attr_state = MediaPlayerState.IDLE
        self._attr_media_position = 0
        self._attr_media_duration = 0
        self._attr_media_position_updated_at = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self) -> None:
        """Subscribe to replay state changes."""
        self._unsub_state = self._controller.session_manager.add_listener(
            self._handle_update
        )
        if self._unsub_state is not None:
            self.async_on_remove(self._unsub_state)
        self.async_on_remove(self._cancel_tick)
        self._refresh_from_controller()

    def _handle_update(self, _snapshot: dict) -> None:
        """Handle replay state updates."""
        self._refresh_from_controller()
        self._update_tick()
        self._safe_write_ha_state()

    def _handle_tick(self, _now) -> None:
        """Periodic update while playing to refresh media position."""
        if self._controller.state != ReplayState.PLAYING:
            return
        self._refresh_from_controller()
        self._safe_write_ha_state()

    def _update_tick(self) -> None:
        """Start/stop periodic updates based on playback state."""
        if self.hass is None:
            return

        if self._controller.state == ReplayState.PLAYING:
            if self._unsub_tick is None:
                self._unsub_tick = async_track_time_interval(
                    self.hass,
                    self._handle_tick,
                    _REPLAY_TICK_INTERVAL,
                )
        else:
            self._cancel_tick()

    def _cancel_tick(self) -> None:
        """Stop periodic updates."""
        if self._unsub_tick is not None:
            self._unsub_tick()
            self._unsub_tick = None

    def _refresh_from_controller(self) -> None:
        """Refresh attributes from the replay controller."""
        state = self._controller.state
        selected = self._controller.session_manager.selected_session
        playback = self._controller.get_playback_status()

        session_start_ms = int(playback.get("session_start_ms", 0) or 0)
        playback_start_ms = int(
            playback.get("playback_start_ms", session_start_ms) or 0
        )
        duration_ms = int(playback.get("duration_ms", 0) or 0)
        position_ms = int(playback.get("position_ms", 0) or 0)

        if duration_ms == 0:
            planned = self._controller.get_planned_playback_details()
            if planned:
                session_start_ms = planned.get("session_start_ms", session_start_ms)
                playback_start_ms = planned.get("playback_start_ms", playback_start_ms)
                duration_ms = planned.get("duration_ms", duration_ms)

        total_ms = max(0, duration_ms - playback_start_ms)
        position_ms = max(0, position_ms - playback_start_ms)
        total_s = int(total_ms / 1000)
        position_s = int(position_ms / 1000)
        remaining_s = max(0, total_s - position_s)

        if state == ReplayState.PLAYING:
            self._attr_state = MediaPlayerState.PLAYING
            self._attr_media_position_updated_at = dt_util.utcnow()
        elif state == ReplayState.PAUSED:
            self._attr_state = MediaPlayerState.PAUSED
            self._attr_media_position_updated_at = dt_util.utcnow()
        elif state == ReplayState.LOADING:
            self._attr_state = MediaPlayerState.BUFFERING
            self._attr_media_position_updated_at = None
        else:
            self._attr_state = MediaPlayerState.IDLE
            self._attr_media_position_updated_at = None

        if state in (ReplayState.PLAYING, ReplayState.PAUSED, ReplayState.READY):
            self._attr_media_duration = total_s
            self._attr_media_position = position_s if state != ReplayState.READY else 0
        else:
            self._attr_media_duration = 0
            self._attr_media_position = 0

        self._attr_media_title = selected.label if selected else None
        self._attr_extra_state_attributes = {
            "replay_state": state.value,
            "selected_session": selected.label if selected else None,
            "selected_session_id": selected.unique_id if selected else None,
            "playback_position_s": position_s,
            "playback_remaining_s": remaining_s,
            "playback_total_s": total_s,
            "session_start_offset_s": int(session_start_ms / 1000),
        }

    async def async_media_play(self) -> None:
        """Start or resume replay playback."""
        state = self._controller.state
        try:
            if state == ReplayState.READY:
                await self._controller.async_play()
            elif state == ReplayState.PAUSED:
                await self._controller.async_resume()
        except RuntimeError as err:
            _LOGGER.warning("Replay play failed: %s", err)

    async def async_media_pause(self) -> None:
        """Pause replay playback."""
        if self._controller.state == ReplayState.PLAYING:
            await self._controller.async_pause()

    async def async_media_stop(self) -> None:
        """Stop replay playback and reset state."""
        await self._controller.async_stop()
