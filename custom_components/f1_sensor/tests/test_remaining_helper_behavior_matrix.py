"""Behavior matrix for remaining pure normalization and lifecycle helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from custom_components.f1_sensor import binary_sensor, config_flow, formation_start
from custom_components.f1_sensor.live_window import (
    LiveAvailabilityTracker,
    _as_int,
    _debug_payload_preview,
    _ensure_sequence,
    _iter_meeting_sessions,
    _normalize_path,
    _parse_offset,
    _to_utc,
    build_session_windows,
)


def test_live_window_normalization_and_root_session_fallback() -> None:
    assert _parse_offset(None) == timedelta()
    assert _parse_offset("2") == timedelta(hours=2)
    assert _parse_offset("+02:30") == timedelta(hours=2, minutes=30)
    assert _parse_offset("-01:02:03") == -timedelta(hours=1, minutes=2, seconds=3)
    assert _parse_offset("bad") == timedelta()
    assert _to_utc(None, None) is None
    assert _to_utc("bad", None) is None
    assert _to_utc("2026-09-01T12:00:00Z", None) == datetime(2026, 9, 1, 12, tzinfo=UTC)
    assert _to_utc("2026-09-01T12:00:00", "+02:00") == datetime(
        2026, 9, 1, 10, tzinfo=UTC
    )
    assert _normalize_path(None) is None
    assert _normalize_path(" / ") is None
    assert _normalize_path(" /2026/test/race ") == "2026/test/race/"
    assert _ensure_sequence([1]) == [1]
    assert _ensure_sequence({"a": 1}) == [1]
    assert _ensure_sequence("bad") == []
    assert _as_int(None) is None
    assert _as_int(" ") is None
    assert _as_int("4") == 4
    assert _as_int("bad") is None
    assert "keys" in _debug_payload_preview({"a": 1})
    assert _debug_payload_preview([1]) == "type=list"

    root = {
        "Sessions": [
            {
                "Name": "Race",
                "Type": "Race",
                "Path": "2026/test/race",
                "StartDate": "2026-09-01T12:00:00Z",
                "EndDate": "2026-09-01T11:00:00Z",
                "Meeting": {"OfficialName": "Test GP", "Key": 1},
                "Key": 2,
            },
            {
                "Name": "Invalid",
                "StartDate": "bad",
                "Meeting": {},
            },
        ]
    }
    sessions = list(_iter_meeting_sessions(root))
    assert sessions[0][0]["OfficialName"] == "Test GP"
    windows = build_session_windows(root)
    assert len(windows) == 1
    assert windows[0].end_utc == windows[0].start_utc + timedelta(hours=2)


def test_live_availability_listener_replay_lock_and_failure_isolation() -> None:
    tracker = LiveAvailabilityTracker()
    events = []
    remove = tracker.add_listener(lambda state, reason: events.append((state, reason)))
    tracker.add_listener(Mock(side_effect=RuntimeError("listener")))
    tracker.set_state(True, "replay")
    assert tracker.replay_locked is True
    tracker.set_state(False, "window-ended")
    assert tracker.is_live is True
    tracker.set_state(False, "replay-completed")
    assert tracker.replay_locked is False
    assert tracker.is_live is False
    remove()
    remove()
    assert events[0] == (False, "init")


async def test_config_flow_normalizers_and_async_replay_path(hass, tmp_path) -> None:
    assert config_flow._normalize_race_week_start_value({}) == (
        config_flow.DEFAULT_RACE_WEEK_START_DAY
    )
    assert (
        config_flow._normalize_race_week_start_value(
            {config_flow.CONF_RACE_WEEK_SUNDAY_START: True}
        )
        == config_flow.RACE_WEEK_START_SUNDAY
    )
    assert (
        config_flow._normalize_race_week_start_value(
            {config_flow.CONF_RACE_WEEK_SUNDAY_START: False}
        )
        == config_flow.RACE_WEEK_START_MONDAY
    )
    assert (
        config_flow._normalize_race_week_start_value(
            {
                config_flow.CONF_RACE_WEEK_SUNDAY_START: config_flow.RACE_WEEK_START_SATURDAY
            }
        )
        == config_flow.RACE_WEEK_START_SATURDAY
    )
    replay_file = tmp_path / "replay.json"
    replay_file.write_text("{}", encoding="utf-8")
    assert await config_flow._async_validate_replay_file(hass, str(replay_file)) is True
    assert await config_flow._async_validate_replay_file(hass, str(tmp_path)) is False


def test_formation_and_binary_sensor_normalizers() -> None:
    assert formation_start._parse_utc(None) is None
    assert formation_start._parse_utc("bad") is None
    assert formation_start._parse_utc("2026-09-01T12:00:00") == datetime(
        2026, 9, 1, 12, tzinfo=UTC
    )
    assert formation_start._parse_offset(None) == timedelta()
    assert formation_start._parse_offset("-01:30") == -timedelta(hours=1, minutes=30)
    assert formation_start._parse_offset("bad") == timedelta()
    assert formation_start._session_start_utc(None) is None
    assert formation_start._session_start_utc({}) is None
    assert formation_start._session_start_utc({"StartDate": "bad"}) is None
    assert formation_start._session_start_utc(
        {"StartDate": "2026-09-01T12:00:00", "GmtOffset": "02:00"}
    ) == datetime(2026, 9, 1, 10, tzinfo=UTC)
    assert formation_start._normalize_session_phase(None) is None
    assert formation_start._normalize_session_phase({"Status": "Finished"}) == (
        "terminal"
    )
    assert formation_start._normalize_session_phase({"Started": True}) == "live"
    assert formation_start._normalize_session_phase({"Started": False}) == "pre"
    assert formation_start._normalize_session_phase({"Status": "unknown"}) is None

    assert binary_sensor._session_status_mapping_context(
        SimpleNamespace(is_qualifying_like_session=True, qualifying_part="bad")
    ) == (True, None)
    assert binary_sensor._session_status_mapping_context(
        SimpleNamespace(is_qualifying_like_session=True, qualifying_part="2")
    ) == (True, 2)
    assert binary_sensor._normalize_race_week_start({}) == (
        binary_sensor.DEFAULT_RACE_WEEK_START_DAY
    )
    assert (
        binary_sensor._normalize_race_week_start(
            {binary_sensor.CONF_RACE_WEEK_SUNDAY_START: True}
        )
        == binary_sensor.RACE_WEEK_START_SUNDAY
    )
    assert (
        binary_sensor._normalize_race_week_start(
            {binary_sensor.CONF_RACE_WEEK_SUNDAY_START: False}
        )
        == binary_sensor.RACE_WEEK_START_MONDAY
    )
