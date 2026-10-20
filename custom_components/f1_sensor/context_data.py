"""Small source, replay and protection context, independent of entity exposure."""

from __future__ import annotations

from copy import deepcopy

from .card_data_models import DataSnapshot


class ReplayStatusProjection:
    """Project controller state without constructing a diagnostic entity."""

    def __init__(self, controller):
        self._controller = controller
        self._state = "idle"
        self._attrs = {}

    def snapshot(self, snapshot):
        if self._controller is None:
            return DataSnapshot("idle", {})
        self._handle_update(snapshot)
        return DataSnapshot(self._state, deepcopy(self._attrs))

    def _handle_update(self, snapshot: dict) -> None:
        """Handle state update from controller."""
        self._state = snapshot.get("state", "idle")
        playback = self._controller.get_playback_status()
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
        relative_position_s = max(0, position_s - playback_start_s)
        self._attrs = {
            "selected_session": snapshot.get("selected_session"),
            "selected_session_id": snapshot.get("selected_session_id"),
            "selected_session_year": snapshot.get("selected_session_year"),
            "selected_meeting_key": snapshot.get("selected_meeting_key"),
            "selected_session_key": snapshot.get("selected_session_key"),
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
            "sync_points": self._controller.get_sync_points(),
        }

    @staticmethod
    def _format_time(seconds: int) -> str:
        """Format seconds as HH:MM:SS."""
        if seconds < 0:
            return "00:00:00"
        hours = seconds // 3600
        minutes = seconds % 3600 // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
