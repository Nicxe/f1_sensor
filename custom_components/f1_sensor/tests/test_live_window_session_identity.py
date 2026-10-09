"""An earlier session must not finish the next live window."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.f1_sensor import live_window
from custom_components.f1_sensor.live_window import LiveSessionSupervisor, SessionWindow
from custom_components.f1_sensor.signalr import LiveBus


async def _monitor(
    hass,
    monkeypatch,
    initial,
    updates,
    *,
    source="index",
    key=11379,
    session_name="Sprint Qualifying",
    meeting_name="Singapore Grand Prix",
):
    """Run the real bus and supervisor with recorded-style frames and a fake clock."""
    now = datetime(2026, 10, 9, 11, 30, tzinfo=UTC)
    bus = LiveBus(hass, AsyncMock())
    for stream, payload in initial:
        bus.inject_message(stream, payload)
    supervisor = LiveSessionSupervisor(
        hass,
        SimpleNamespace(async_request_refresh=AsyncMock()),
        bus,
        http_session=AsyncMock(),
    )
    supervisor._resolve_primary_window = AsyncMock(return_value=None)
    window = SessionWindow(
        meeting_name,
        session_name,
        "",
        now + timedelta(hours=1),
        now + timedelta(hours=1, minutes=44),
        now,
        now + timedelta(hours=1, minutes=59),
        meeting_key=1296,
        session_key=key,
    )
    tick = 0

    async def advance(_seconds):
        nonlocal now, tick
        assert tick < len(updates), "Monitor did not stop after feed inactivity"
        now += timedelta(seconds=20)
        for stream, payload in updates[tick]:
            bus.inject_message(stream, payload)
        tick += 1

    monkeypatch.setattr(supervisor, "_interruptible_sleep", advance)
    monkeypatch.setattr(live_window.dt_util, "utcnow", lambda: now)
    monkeypatch.setattr(
        bus, "last_heartbeat_age", lambda: 80.0 if tick == len(updates) else 0.0
    )
    monkeypatch.setattr(bus, "last_stream_activity_age", lambda *_args: 0.0)
    reason = await supervisor._monitor_window(window, source=source)
    assert not bus._subs
    return reason, supervisor, window, tick


@pytest.mark.parametrize("source", ["index", "event_tracker"])
@pytest.mark.parametrize(
    ("info", "key"),
    [
        ({"Key": 11731, "Name": "Race", "SessionStatus": "Ends"}, 11378),
        ({"Key": 11378, "Name": "Practice 1", "SessionStatus": "Finalised"}, 11379),
        (None, 11379),
        ({"SessionStatus": "Ends"}, 11379),
        ({"Key": "invalid", "SessionStatus": "Ends"}, 11379),
        ({"Key": 11379, "SessionStatus": "Ends"}, None),
    ],
)
async def test_stale_or_unidentified_finish_keeps_window_eligible(
    hass, monkeypatch, source, info, key
):
    initial = [("SessionStatus", {"Status": "Ends", "Started": "Finished"})]
    if info is not None:
        initial.append(("SessionInfo", info))
    reason, supervisor, window, _ = await _monitor(
        hass, monkeypatch, initial, [[]] * 6, source=source, key=key
    )
    assert reason == "heartbeat-timeout-80s"
    assert await supervisor._select_window([window], source=source) is window


@pytest.mark.parametrize(
    "info", [{"Key": 11379}, {"Key": 11379, "SessionStatus": "Inactive"}]
)
async def test_current_identity_does_not_reuse_cached_previous_status(
    hass, monkeypatch, info
):
    initial = [
        ("SessionStatus", {"Status": "Ends"}),
        ("SessionInfo", info),
    ]
    reason, supervisor, window, _ = await _monitor(hass, monkeypatch, initial, [[]] * 6)
    assert reason == "heartbeat-timeout-80s"
    assert await supervisor._select_window([window], source="index") is window


@pytest.mark.parametrize("info_first", [True, False])
async def test_feed_switch_clears_previous_finish(hass, monkeypatch, info_first):
    initial = [
        ("SessionInfo", {"Key": 11378, "SessionStatus": "Finalised"}),
        ("SessionStatus", {"Status": "Ends"}),
    ]
    info = ("SessionInfo", {"Key": "11379", "SessionStatus": "Inactive"})
    status = ("SessionStatus", {"Status": "Inactive"})
    switch = [info, status] if info_first else [status, info]
    updates = [
        [],
        switch,
        [("SessionInfo", {"ArchiveStatus": {"Status": "Generating"}})],
    ]
    reason, supervisor, window, _ = await _monitor(
        hass, monkeypatch, initial, updates + [[]] * 5
    )
    assert reason == "heartbeat-timeout-80s"
    assert await supervisor._select_window([window], source="index") is window


@pytest.mark.parametrize("source", ["index", "event_tracker"])
@pytest.mark.parametrize("status", ["Finalised", "Ends"])
async def test_identified_session_finishes_after_partial_info(
    hass, monkeypatch, status, source
):
    initial = [("SessionInfo", {"Key": 11379, "SessionStatus": "Started"})]
    updates = [
        [("SessionInfo", {"ArchiveStatus": {"Status": "Generating"}})],
        [("SessionStatus", {"Status": status, "Started": "Finished"})],
    ] + [[]] * 5
    reason, supervisor, window, tick = await _monitor(
        hass, monkeypatch, initial, updates, source=source
    )
    assert reason == "session-finished"
    assert tick == 5
    assert await supervisor._select_window([window], source="index") is None


@pytest.mark.parametrize("source", ["index", "event_tracker"])
@pytest.mark.parametrize("part", [1, 2])
async def test_qualifying_segment_finish_and_break_keep_window_open(
    hass, monkeypatch, source, part
):
    initial = [("SessionInfo", {"Key": 11379, "Type": "Qualifying"})]
    updates = [
        [("SessionData", {"Series": {"1": {"QualifyingPart": part}}})],
        [("SessionStatus", {"Status": "Started", "Started": "Started"})],
        [("SessionStatus", {"Status": "Finished", "Started": "Finished"})],
        [("SessionStatus", {"Status": "Inactive", "Started": "Finished"})],
    ] + [[]] * 5
    reason, supervisor, window, _ = await _monitor(
        hass, monkeypatch, initial, updates, source=source
    )
    assert reason == "heartbeat-timeout-80s"
    assert await supervisor._select_window([window], source=source) is window


async def test_qualifying_final_segment_waits_for_finalised(hass, monkeypatch):
    initial = [("SessionInfo", {"Key": 11379, "Type": "Qualifying"})]
    updates = [
        [("SessionStatus", {"Status": "Started", "Started": "Started"})],
        [("SessionStatus", {"Status": "Finished", "Started": "Finished"})],
        [],
        [],
        [("SessionStatus", {"Status": "Finalised", "Started": "Finished"})],
    ] + [[]] * 5
    reason, supervisor, window, tick = await _monitor(
        hass, monkeypatch, initial, updates
    )
    assert reason == "session-finished"
    assert tick == 8
    assert await supervisor._select_window([window], source="index") is None


async def test_full_qualifying_progression_stays_live_through_two_breaks(
    hass, monkeypatch
):
    initial = [("SessionInfo", {"Key": 11379, "Type": "Qualifying"})]
    updates = [
        [("SessionData", {"Series": {"1": {"QualifyingPart": 1}}})],
        [("SessionStatus", {"Status": "Started", "Started": "Started"})],
        [("SessionStatus", {"Status": "Finished", "Started": "Finished"})],
        *([[]] * 4),
        [("SessionStatus", {"Status": "Inactive", "Started": "Finished"})],
        [("SessionData", {"Series": {"2": {"QualifyingPart": 2}}})],
        [("SessionStatus", {"Status": "Started", "Started": "Started"})],
        [("SessionStatus", {"Status": "Finished", "Started": "Finished"})],
        *([[]] * 4),
        [("SessionStatus", {"Status": "Inactive", "Started": "Finished"})],
        [("SessionData", {"Series": {"3": {"QualifyingPart": 3}}})],
        [("SessionStatus", {"Status": "Started", "Started": "Started"})],
        [("SessionStatus", {"Status": "Finished", "Started": "Finished"})],
        *([[]] * 4),
        [("SessionStatus", {"Status": "Finalised", "Started": "Finished"})],
        *([[]] * 4),
    ]
    reason, supervisor, window, tick = await _monitor(
        hass, monkeypatch, initial, updates
    )
    assert reason == "session-finished"
    assert tick == len(updates) - 1
    assert await supervisor._select_window([window], source="index") is None


@pytest.mark.parametrize(
    "old_info",
    [
        {"Key": 11378, "Type": "Qualifying"},
        {
            "Key": 11378,
            "Type": "Practice",
            "Meeting": {"Name": "Pre-Season Testing"},
        },
    ],
)
async def test_new_race_key_clears_previous_multi_part_context(
    hass, monkeypatch, old_info
):
    initial = [
        ("SessionInfo", old_info),
        ("SessionStatus", {"Status": "Finished"}),
    ]
    updates = [
        [("SessionInfo", {"Key": 11379, "Type": "Race"})],
        [("SessionStatus", {"Status": "Finished"})],
    ] + [[]] * 5
    reason, supervisor, window, tick = await _monitor(
        hass, monkeypatch, initial, updates, session_name="Race"
    )
    assert reason == "session-finished"
    assert tick == 5
    assert await supervisor._select_window([window], source="index") is None


@pytest.mark.parametrize("meeting_name", ["Pre-Season Testing", "F1"])
@pytest.mark.parametrize("source", ["index", "event_tracker"])
async def test_testing_day_remains_live_through_lunch_finish(
    hass, monkeypatch, meeting_name, source
):
    initial = [
        (
            "SessionInfo",
            {
                "Key": 11470,
                "Type": "Practice",
                "Meeting": {"Name": "Pre-Season Testing"},
            },
        )
    ]
    updates = [
        [("SessionStatus", {"Status": "Started", "Started": "Started"})],
        [("SessionInfo", {"Meeting": {"Name": "Updated event name"}})],
        [("SessionStatus", {"Status": "Finished", "Started": "Finished"})],
        *([[]] * 4),
        [("SessionStatus", {"Status": "Inactive", "Started": "Finished"})],
        [("SessionStatus", {"Status": "Finished", "Started": "Finished"})],
        *([[]] * 4),
        [("SessionStatus", {"Status": "Started", "Started": "Started"})],
        [("SessionStatus", {"Status": "Finalised", "Started": "Started"})],
        *([[]] * 4),
    ]
    reason, supervisor, window, tick = await _monitor(
        hass,
        monkeypatch,
        initial,
        updates,
        key=11470,
        session_name="Day 1",
        meeting_name=meeting_name,
        source=source,
    )
    assert reason == "session-finished"
    assert tick == len(updates) - 1
    assert await supervisor._select_window([window], source=source) is None


async def test_qualifying_reconnect_during_break_keeps_window_open(hass, monkeypatch):
    initial = [
        ("SessionStatus", {"Status": "Inactive", "Started": "Finished"}),
        ("SessionInfo", {"Key": 11379, "Type": "Qualifying"}),
    ]
    reason, supervisor, window, _ = await _monitor(hass, monkeypatch, initial, [[]] * 6)
    assert reason == "heartbeat-timeout-80s"
    assert await supervisor._select_window([window], source="index") is window


async def test_session_info_type_protects_renamed_qualifying_session(hass, monkeypatch):
    initial = [("SessionInfo", {"Key": 11379, "Type": "Qualifying"})]
    updates = [[("SessionStatus", {"Status": "Finished"})]] + [[]] * 5
    reason, supervisor, window, _ = await _monitor(
        hass, monkeypatch, initial, updates, session_name="Timed Segment"
    )
    assert reason == "heartbeat-timeout-80s"
    assert await supervisor._select_window([window], source="index") is window


async def test_practice_finish_remains_terminal(hass, monkeypatch):
    initial = [("SessionInfo", {"Key": 11379, "Type": "Practice"})]
    updates = [[("SessionStatus", {"Status": "Finished"})]] + [[]] * 5
    reason, supervisor, window, tick = await _monitor(
        hass, monkeypatch, initial, updates, session_name="Practice 1"
    )
    assert reason == "session-finished"
    assert tick == 4
    assert await supervisor._select_window([window], source="index") is None


async def test_matching_identity_arrives_after_unknown_terminal_status(
    hass, monkeypatch
):
    initial = [("SessionStatus", {"Status": "Ends"})]
    updates = [
        [("SessionStatus", {"Status": "Ends"})],
        [("SessionInfo", {"Key": 11379})],
        [("SessionInfo", None), ("SessionStatus", None)],
        [("SessionStatus", {"Status": "Finished"})],
    ] + [[]] * 5
    reason, supervisor, window, tick = await _monitor(
        hass, monkeypatch, initial, updates, session_name="Practice 1"
    )
    assert reason == "session-finished"
    assert tick == 7
    assert await supervisor._select_window([window], source="index") is None


async def test_reconnect_to_identified_finished_session_closes(hass, monkeypatch):
    initial = [("SessionInfo", {"Key": 11379, "SessionStatus": "Finalised"})]
    reason, supervisor, window, tick = await _monitor(
        hass, monkeypatch, initial, [[]] * 6
    )
    assert reason == "session-finished"
    assert tick == 4
    assert await supervisor._select_window([window], source="index") is None


async def test_changed_identity_cancels_pending_finish(hass, monkeypatch):
    initial = [("SessionInfo", {"Key": 11379, "SessionStatus": "Finalised"})]
    updates = [
        [],
        [("SessionInfo", {"Key": 11380})],
        [("SessionInfo", {"ArchiveStatus": {"Status": "Complete"}})],
    ] + [[]] * 5
    reason, supervisor, window, _ = await _monitor(hass, monkeypatch, initial, updates)
    assert reason == "heartbeat-timeout-80s"
    assert await supervisor._select_window([window], source="index") is window
