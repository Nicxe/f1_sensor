"""Replay mode UI entities for F1 Sensor."""

from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.button import ButtonEntity
from homeassistant.components.select import SelectEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory
from .const import (
    DOMAIN,
    REPLAY_START_REFERENCE_FORMATION,
    REPLAY_START_REFERENCE_SESSION,
)
from .entity import F1AuxEntity
from .replay_mode import ReplayController, ReplayState
from .replay_start import ReplayStartReferenceController
from .calibration import LiveDelayCalibrationManager

_LOGGER = logging.getLogger(__name__)


class F1ReplayYearSelect(F1AuxEntity, SelectEntity):
    """Select entity for choosing replay year."""

    _device_category = "system"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False
    _attr_translation_key = "replay_year"

    def __init__(
        self,
        controller: ReplayController,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
        SelectEntity.__init__(self)
        self._controller = controller
        self._unsub: Callable[[], None] | None = None
        self._current_option: str | None = None
        self._options: list[str] = []
        self._attr_icon = "mdi:calendar"

    async def async_added_to_hass(self) -> None:
        """Subscribe to state changes when added to hass."""
        self._unsub = self._controller.session_manager.add_listener(self._handle_update)
        self._rebuild_options()

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe when removed."""
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def options(self) -> list[str]:
        """Return list of available options."""
        return self._options

    @property
    def current_option(self) -> str | None:
        """Return current selected option."""
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        try:
            year = int(option)
        except ValueError:
            return

        if self._controller.state == ReplayState.LOADING:
            _LOGGER.warning("Replay year change ignored while loading")
            return

        if self._controller.state in (
            ReplayState.PLAYING,
            ReplayState.PAUSED,
            ReplayState.READY,
        ):
            await self._controller.async_stop()

        manager = self._controller.session_manager
        if year == manager.selected_year:
            await manager.async_fetch_sessions(year)
            return
        await manager.async_set_year(year)

    def _handle_update(self, snapshot: dict) -> None:
        """Handle state update from controller."""
        self._rebuild_options()
        selected_year = snapshot.get("selected_year")
        if selected_year is None:
            selected_year = self._controller.session_manager.selected_year
        self._current_option = str(selected_year) if selected_year is not None else None
        self.async_write_ha_state()

    def _rebuild_options(self) -> None:
        """Rebuild options list from available years."""
        years = self._controller.session_manager.year_options
        self._options = [str(y) for y in years]


class F1ReplaySessionSelect(F1AuxEntity, SelectEntity):
    """Select entity for choosing replay session."""

    _device_category = "system"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False
    _attr_translation_key = "replay_session"

    def __init__(
        self,
        controller: ReplayController,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
        SelectEntity.__init__(self)
        self._controller = controller
        self._unsub: Callable[[], None] | None = None
        self._current_option: str | None = None
        self._options: list[str] = []
        self._session_map: dict[str, str] = {}  # label -> session_id
        self._placeholder_option: str | None = None
        self._attr_icon = "mdi:calendar-clock"

    async def async_added_to_hass(self) -> None:
        """Subscribe to state changes when added to hass."""
        self._unsub = self._controller.session_manager.add_listener(self._handle_update)
        # Build initial options
        self._rebuild_options()

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe when removed."""
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def options(self) -> list[str]:
        """Return list of available options."""
        return self._options

    @property
    def current_option(self) -> str | None:
        """Return current selected option."""
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        session_id = self._session_map.get(option)
        if session_id:
            try:
                await self._controller.session_manager.async_select_session(session_id)
            except ValueError as err:
                _LOGGER.warning("Failed to select session: %s", err)

    def _handle_update(self, snapshot: dict) -> None:
        """Handle state update from controller."""
        self._rebuild_options()
        selected = snapshot.get("selected_session")
        if selected is not None:
            self._current_option = selected
        elif self._placeholder_option:
            self._current_option = self._placeholder_option
        else:
            self._current_option = None
        self.async_write_ha_state()

    def _rebuild_options(self) -> None:
        """Rebuild options list from available sessions."""
        manager = self._controller.session_manager
        sessions = manager.available_sessions
        self._options = [s.label for s in sessions]
        self._session_map = {s.label: s.unique_id for s in sessions}
        self._placeholder_option = None
        if not self._options:
            year = manager.selected_year
            status = manager.index_status
            if status == "no_data":
                self._placeholder_option = f"No data for {year}"
            elif status == "error":
                self._placeholder_option = "Session list unavailable"
            else:
                self._placeholder_option = f"No sessions for {year}"
            self._options = [self._placeholder_option]


class F1ReplayStartReferenceSelect(F1AuxEntity, SelectEntity):
    """Select entity for choosing replay playback start reference."""

    _device_category = "system"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False
    _attr_translation_key = "replay_start_reference"

    def __init__(
        self,
        controller: ReplayStartReferenceController,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
        SelectEntity.__init__(self)
        self._controller = controller
        self._option_to_value = {
            "Session live": REPLAY_START_REFERENCE_SESSION,
            "Formation start (race/sprint)": REPLAY_START_REFERENCE_FORMATION,
        }
        self._value_to_option = {v: k for k, v in self._option_to_value.items()}
        self._current_option = self._value_to_option.get(
            controller.current, "Formation start (race/sprint)"
        )
        self._unsub: Callable[[], None] | None = None
        self._attr_icon = "mdi:flag-checkered"

    async def async_added_to_hass(self) -> None:
        """Subscribe to reference changes when added to hass."""
        if not self._unsub:
            self._unsub = self._controller.add_listener(self._handle_reference_update)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe when removed."""
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def options(self) -> list[str]:
        """Return list of available options."""
        return list(self._option_to_value.keys())

    @property
    def current_option(self) -> str | None:
        """Return current selected option."""
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        value = self._option_to_value.get(option, REPLAY_START_REFERENCE_FORMATION)
        await self._controller.async_set_reference(value, source="select_entity")

    def _handle_reference_update(self, value: str) -> None:
        self._current_option = self._value_to_option.get(
            value, "Formation start (race/sprint)"
        )
        if self.hass:
            self.async_write_ha_state()


class F1ReplayLoadButton(F1AuxEntity, ButtonEntity):
    """Button to load selected session."""

    _device_category = "system"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "replay_load"

    def __init__(
        self,
        controller: ReplayController,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
        ButtonEntity.__init__(self)
        self._controller = controller
        self._attr_icon = "mdi:download"

    async def async_press(self) -> None:
        """Handle button press - load selected session."""
        await self._block_calibration_for_replay("load")
        if self._controller.state == ReplayState.SELECTED:
            try:
                await self._controller.async_prepare_and_load_session()
            except RuntimeError as err:
                _LOGGER.warning("Failed to load session: %s", err)

    async def _block_calibration_for_replay(self, action: str) -> None:
        if not self.hass:
            return
        reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}) or {}
        manager: LiveDelayCalibrationManager | None = reg.get("calibration_manager")
        if manager is None:
            return
        mode = str(manager.snapshot().get("mode") or "idle")
        if mode in {"waiting", "running"}:
            await manager.async_blocked_by_replay(source=f"replay_{action}")


class F1ReplayPlayButton(F1AuxEntity, ButtonEntity):
    """Button to start or resume playback."""

    _device_category = "system"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "replay_play"

    def __init__(
        self,
        controller: ReplayController,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
        ButtonEntity.__init__(self)
        self._controller = controller
        self._attr_icon = "mdi:play"

    async def async_press(self) -> None:
        """Handle button press - start or resume playback."""
        await self._block_calibration_for_replay("play")
        state = self._controller.state
        try:
            if state == ReplayState.READY:
                await self._controller.async_play()
            elif state == ReplayState.PAUSED:
                await self._controller.async_resume()
        except RuntimeError as err:
            _LOGGER.warning("Failed to start/resume playback: %s", err)

    async def _block_calibration_for_replay(self, action: str) -> None:
        if not self.hass:
            return
        reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}) or {}
        manager: LiveDelayCalibrationManager | None = reg.get("calibration_manager")
        if manager is None:
            return
        mode = str(manager.snapshot().get("mode") or "idle")
        if mode in {"waiting", "running"}:
            await manager.async_blocked_by_replay(source=f"replay_{action}")


class F1ReplayPauseButton(F1AuxEntity, ButtonEntity):
    """Button to pause playback."""

    _device_category = "system"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "replay_pause"

    def __init__(
        self,
        controller: ReplayController,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
        ButtonEntity.__init__(self)
        self._controller = controller
        self._attr_icon = "mdi:pause"

    async def async_press(self) -> None:
        """Handle button press - pause playback."""
        if self._controller.state == ReplayState.PLAYING:
            await self._controller.async_pause()


class F1ReplayStopButton(F1AuxEntity, ButtonEntity):
    """Button to stop replay and return to idle mode."""

    _device_category = "system"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "replay_stop"

    def __init__(
        self,
        controller: ReplayController,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
        ButtonEntity.__init__(self)
        self._controller = controller
        self._attr_icon = "mdi:stop"

    async def async_press(self) -> None:
        """Handle button press - stop replay."""
        await self._controller.async_stop()


class F1ReplayStatusSensor(F1AuxEntity, SensorEntity):
    """Sensor showing replay status and progress."""

    _device_category = "system"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False
    _attr_translation_key = "replay_status"

    def __init__(
        self,
        controller: ReplayController,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
        SensorEntity.__init__(self)
        self._controller = controller
        self._unsub: Callable[[], None] | None = None
        self._state: str = "idle"
        self._attrs: dict[str, Any] = {}
        self._attr_icon = "mdi:replay"

    async def async_added_to_hass(self) -> None:
        """Subscribe to state changes when added to hass."""
        self._unsub = self._controller.session_manager.add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe when removed."""
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def native_value(self) -> str:
        """Return current state."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return self._attrs

    def _handle_update(self, snapshot: dict) -> None:
        """Handle state update from controller."""
        self._state = snapshot.get("state", "idle")

        playback = self._controller.get_playback_status()

        # Calculate human-readable position
        position_ms = int(playback.get("position_ms", 0) or 0)
        session_start_ms = int(playback.get("session_start_ms", 0) or 0)
        playback_start_ms = int(playback.get("playback_start_ms", 0) or 0)
        duration_ms = int(playback.get("duration_ms", 0) or 0)

        if duration_ms == 0:
            planned = self._controller.get_planned_playback_details()
            if planned:
                session_start_ms = planned.get("session_start_ms", session_start_ms)
                playback_start_ms = planned.get("playback_start_ms", playback_start_ms)
                duration_ms = planned.get("duration_ms", duration_ms)

        position_s = position_ms // 1000
        session_start_s = session_start_ms // 1000
        playback_start_s = playback_start_ms // 1000
        duration_s = duration_ms // 1000

        # Position relative to session start
        relative_position_s = max(0, position_s - playback_start_s)

        self._attrs = {
            "selected_session": snapshot.get("selected_session"),
            "download_progress": round(snapshot.get("download_progress", 0) * 100, 1),
            "download_error": snapshot.get("download_error"),
            "playback_position_s": relative_position_s,
            "playback_position_formatted": self._format_time(relative_position_s),
            "playback_total_s": duration_s - playback_start_s,
            "playback_total_formatted": self._format_time(
                duration_s - playback_start_s
            ),
            "session_start_offset_s": session_start_s,
            "paused": playback.get("paused", False),
            "sessions_available": snapshot.get("sessions_count", 0),
            "selected_year": snapshot.get("selected_year"),
            "index_year": snapshot.get("index_year"),
            "index_status": snapshot.get("index_status"),
            "index_error": snapshot.get("index_error"),
        }
        self.async_write_ha_state()

    @staticmethod
    def _format_time(seconds: int) -> str:
        """Format seconds as HH:MM:SS."""
        if seconds < 0:
            return "00:00:00"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class F1ReplayRefreshButton(F1AuxEntity, ButtonEntity):
    """Button to refresh the session list."""

    _device_category = "system"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "replay_refresh"

    def __init__(
        self,
        controller: ReplayController,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
        ButtonEntity.__init__(self)
        self._controller = controller
        self._attr_icon = "mdi:refresh"

    async def async_press(self) -> None:
        """Handle button press - refresh session list."""
        await self._controller.session_manager.async_fetch_sessions()
