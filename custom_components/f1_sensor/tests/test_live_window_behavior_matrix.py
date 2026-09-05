"""Behavior matrix for live schedule sources and supervisor safeguards."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.f1_sensor.live_window import (
    EventTrackerScheduleSource,
    IndexScheduleSource,
    LiveAvailabilityTracker,
    LiveSessionSupervisor,
    ScheduleFetchResult,
    SessionWindow,
    _as_int,
    _build_static_url,
    _clean_text,
    _clock_finished,
    _debug_payload_preview,
    _ensure_sequence,
    _find_matching_window,
    _keys_match,
    _names_match,
    _normalize_path,
    _normalize_session_match_text,
    _parse_offset,
    _session_status_running,
    _to_utc,
    _window_times_differ,
    build_session_windows,
)


class _Context:
    def __init__(self, value) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return None


class _Http:
    def __init__(self, responses=None, *, error=None) -> None:
        self.responses = list(responses or [])
        self.error = error
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error is not None:
            raise self.error
        return _Context(self.responses.pop(0))


def _response(status=200, text="{}"):
    return SimpleNamespace(
        status=status,
        text=AsyncMock(return_value=text),
        raise_for_status=Mock(
            side_effect=RuntimeError("http failure") if status >= 400 else None
        ),
    )


def _window(
    *,
    now: datetime | None = None,
    meeting="Australian Grand Prix",
    session="Race",
    path="2026/race/",
    meeting_key=1,
    session_key=2,
) -> SessionWindow:
    now = now or datetime.now(UTC)
    start = now - timedelta(minutes=10)
    end = now + timedelta(minutes=30)
    return SessionWindow(
        meeting,
        session,
        path,
        start,
        end,
        start - timedelta(hours=1),
        end + timedelta(minutes=15),
        meeting_key,
        session_key,
    )


def _supervisor(hass, *, http=None, index=None, fallback=None):
    bus = SimpleNamespace(
        start=AsyncMock(),
        async_close=AsyncMock(),
        set_heartbeat_expectation=Mock(),
        last_heartbeat_age=Mock(return_value=None),
        last_stream_activity_age=Mock(return_value=None),
    )
    coord = SimpleNamespace(async_request_refresh=AsyncMock())
    source = index or SimpleNamespace(async_fetch_windows=AsyncMock())
    return LiveSessionSupervisor(
        hass,
        coord,
        bus,
        http_session=http or _Http(),
        index_source=source,
        fallback_source=fallback,
    )


def test_live_window_parsing_matching_and_status_helpers() -> None:
    assert _parse_offset(None) == timedelta()
    assert _parse_offset("1") == timedelta(hours=1)
    assert _parse_offset("+01:30") == timedelta(hours=1, minutes=30)
    assert _parse_offset("-01:02:03") == -timedelta(hours=1, minutes=2, seconds=3)
    assert _parse_offset("") == timedelta()
    assert _parse_offset("bad") == timedelta()
    assert _to_utc(None, None) is None
    assert _to_utc("bad", None) is None
    assert _to_utc("2026-09-01T13:00:00", "+01:00") == datetime(
        2026, 9, 1, 12, tzinfo=UTC
    )
    assert _normalize_path(None) is None
    assert _normalize_path(" / ") is None
    assert _normalize_path("race") == "race/"
    assert _ensure_sequence([1]) == [1]
    assert _ensure_sequence({"a": 1}) == [1]
    assert _ensure_sequence("bad") == []
    assert _debug_payload_preview({"a": 1}).startswith('{"type"')
    assert _debug_payload_preview([1]) == "type=list"
    assert _as_int(None) is None
    assert _as_int(" ") is None
    assert _as_int("bad") is None
    assert _as_int("2") == 2
    assert _clean_text(None, " ", "value") == "value"
    assert _clean_text(None, default="fallback") == "fallback"
    assert _normalize_session_match_text("FP1") == "practice 1"
    assert _normalize_session_match_text("Sprint Shootout") == "sprint qualifying"
    assert _build_static_url("/race/", "Status") == (
        "https://livetiming.formula1.com/static/race/Status"
    )
    assert _clock_finished(None) is False
    assert _clock_finished({"Remaining": "00:00:00"}) is True
    assert _clock_finished({"Remaining": "00:00:00", "Extrapolating": True}) is False
    assert _session_status_running(None) is False
    assert _session_status_running({"Status": "Started"}) is True
    assert _session_status_running({"Started": "Finished"}) is False

    primary = _window()
    same_key = _window(meeting="Different", session="Practice")
    assert _keys_match(primary, same_key) is True
    assert _names_match(primary, same_key) is False
    same_name = _window(meeting_key=None, session_key=None)
    assert _names_match(primary, same_name) is True
    assert _find_matching_window(primary, [same_name]) is same_name
    shifted = _window()
    shifted.start_utc += timedelta(minutes=10)
    assert _window_times_differ(primary, shifted) is True


def test_build_session_windows_root_fallback_and_default_duration() -> None:
    payload = {
        "Sessions": [
            {
                "Meeting": {"OfficialName": " Grand Prix ", "Key": 1},
                "Type": "Race",
                "Key": 2,
                "StartDate": "2026-09-01T12:00:00Z",
                "EndDate": "2026-09-01T11:00:00Z",
            },
            {"Name": "Invalid"},
        ]
    }
    windows = build_session_windows(payload)
    assert len(windows) == 1
    assert windows[0].meeting_name == "Grand Prix"
    assert windows[0].end_utc - windows[0].start_utc == timedelta(hours=2)


def test_availability_replay_lock_listener_failures_and_removal() -> None:
    tracker = LiveAvailabilityTracker()
    failing = Mock(side_effect=RuntimeError("listener"))
    remove = tracker.add_listener(failing)
    tracker.set_state(True, "replay")
    tracker.set_state(False, "supervisor")
    assert tracker.is_live is True
    assert tracker.replay_locked is True
    tracker.set_state(False, "replay-completed")
    assert tracker.is_live is False
    assert tracker.replay_locked is False
    remove()
    remove()


@pytest.mark.asyncio
async def test_index_source_refresh_success_and_failure() -> None:
    coord = SimpleNamespace(data=None, last_http_status=503, async_refresh=AsyncMock())
    source = IndexScheduleSource(coord)
    failed = await source.async_fetch_windows(
        pre_window=timedelta(), post_window=timedelta()
    )
    assert failed.windows == []
    assert failed.index_http_status == 503

    coord.async_refresh = AsyncMock(side_effect=RuntimeError("index failed"))
    failed = await source.async_fetch_windows(
        pre_window=timedelta(), post_window=timedelta()
    )
    assert failed.last_error == "index failed"


@pytest.mark.asyncio
async def test_event_tracker_dynamic_config_cache_and_disabled_paths() -> None:
    text = (
        'PUBLIC_GLOBAL_APIGEE_BASEURL":"https://api.formula1.com" '
        'PUBLIC_GLOBAL_EVENTTRACKER_ENDPOINT":"events" '
        'PUBLIC_GLOBAL_EVENTTRACKER_MEETINGENDPOINT":"meeting/{meeting_key}" '
        'PUBLIC_GLOBAL_EVENTTRACKER_APIKEY":"key"'
    )
    source = EventTrackerScheduleSource(
        _Http([_response(text=text)]), env_refresh_ttl=60
    )
    await source._refresh_dynamic_config(force=True)
    assert source._endpoint == "/events"
    assert source._meeting_endpoint(7) == "/meeting/7"
    assert source._api_key == "key"
    await source._refresh_dynamic_config()

    source._meeting_endpoint_prefix = "/meeting"
    assert source._meeting_endpoint(8) == "/meeting/8"

    no_env = EventTrackerScheduleSource(_Http(), endpoint="", env_source_url="")
    await no_env._refresh_dynamic_config(force=True)
    assert no_env._endpoint == "/"

    unavailable_env = EventTrackerScheduleSource(
        _Http([_response(503)]), env_source_url="https://example.test/env"
    )
    await unavailable_env._refresh_dynamic_config(force=True)

    failed_env = EventTrackerScheduleSource(
        _Http(error=RuntimeError("offline")),
        env_source_url="https://example.test/env",
    )
    await failed_env._refresh_dynamic_config(force=True)

    disabled = EventTrackerScheduleSource(_Http(), fallback_enabled=False)
    result = await disabled.async_fetch_windows(
        pre_window=timedelta(), post_window=timedelta()
    )
    assert result.last_error == "fallback-disabled"

    cached = ScheduleFetchResult([], "event_tracker", last_error="cached")
    source._cache_result = cached
    source._cache_expires_at = float("inf")
    result = await source.async_fetch_windows(
        pre_window=timedelta(), post_window=timedelta()
    )
    assert result is cached


@pytest.mark.asyncio
async def test_event_tracker_fetch_errors_retry_and_payload_validation() -> None:
    source = EventTrackerScheduleSource(
        _Http([_response(403, "denied"), _response(200, "[]")]),
        env_source_url="",
    )
    source._refresh_dynamic_config = AsyncMock()
    with pytest.raises(RuntimeError, match="not a dict"):
        await source._fetch_tracker_json("/events", endpoint_kind="root")
    source._refresh_dynamic_config.assert_awaited_once_with(force=True)

    source = EventTrackerScheduleSource(_Http([_response(500, "broken")]))
    with pytest.raises(RuntimeError, match="HTTP 500"):
        await source._fetch_tracker_json("/events", allow_retry=False)

    assert source._extract_meeting_key(None) is None
    assert source._extract_meeting_key({"fomRaceId": "4"}) == 4
    assert source._extract_timetables(None) == []
    assert source._extract_timetables(
        {"event": {"timetables": ["bad", {"description": "Race"}]}}
    ) == [{"description": "Race"}]
    assert source._extract_meeting_name(None) == "F1"
    assert (
        source._windows_from_payload(
            {"event": {"timetables": [{"description": "bad"}]}},
            pre_window=timedelta(),
            post_window=timedelta(),
        )
        == []
    )


@pytest.mark.asyncio
async def test_supervisor_state_selection_and_session_activity(
    hass, monkeypatch
) -> None:
    supervisor = _supervisor(hass)
    assert supervisor._should_log("key", interval_seconds=0) is True
    assert supervisor._should_log("key", interval_seconds=999999) is False
    supervisor._set_schedule_state(source="index", fallback_active=False)
    supervisor._set_schedule_state(
        source="event_tracker", fallback_active=True, log_context="test"
    )
    supervisor._set_schedule_state(source="none", fallback_active=False)
    assert supervisor.schedule_source == "none"
    assert supervisor.fallback_active is False
    assert supervisor.current_window is None

    assert await supervisor._select_window([], source="index") is None
    now = datetime.now(UTC)
    finished = _window(now=now - timedelta(hours=4), path="")
    assert await supervisor._select_window([finished], source="index") is None

    ended_but_active = _window(now=now - timedelta(hours=4))
    extension_supervisor = _supervisor(hass)
    extension_supervisor._session_active = AsyncMock(return_value=True)
    extended = await extension_supervisor._select_window(
        [ended_but_active], source="index"
    )
    assert extended is not None
    assert extended.disconnect_at > now
    assert extended.connect_at <= now - timedelta(minutes=5)

    active = _window(now=now)
    supervisor._fetch_json = AsyncMock(side_effect=RuntimeError("temporary"))
    assert await supervisor._session_active(active) is True
    expired = _window(now=now - timedelta(hours=5))
    assert await supervisor._session_active(expired) is False
    assert await supervisor._session_active(_window(path="")) is False
    supervisor._fetch_json = AsyncMock(return_value="bad")
    assert await supervisor._session_active(active) is False
    supervisor._fetch_json = AsyncMock(return_value={"Status": "Finished"})
    assert await supervisor._session_active(active) is False
    supervisor._fetch_json = AsyncMock(return_value={"Started": "Ends"})
    assert await supervisor._session_active(active) is False
    supervisor._fetch_json = AsyncMock(return_value={"Status": "Started"})
    assert await supervisor._session_active(active) is True


@pytest.mark.asyncio
async def test_supervisor_session_finished_and_json_stream_decoder(hass) -> None:
    supervisor = _supervisor(hass)
    window = _window()
    supervisor._fetch_json = AsyncMock(side_effect=RuntimeError("offline"))
    assert await supervisor._session_finished(window) is False
    supervisor._fetch_json = AsyncMock(return_value="bad")
    assert await supervisor._session_finished(window) is False
    supervisor._fetch_json = AsyncMock(return_value={"Status": "Finished"})
    assert await supervisor._session_finished(window) is True
    supervisor._fetch_json = AsyncMock(return_value={"Status": "Started"})
    assert await supervisor._session_finished(window) is False

    decoder = _supervisor(hass, http=_Http([_response(404, "missing")]))
    assert await decoder._fetch_json("url") is None
    decoder._http = _Http([_response(200, "\ufeff  ")])
    assert await decoder._fetch_json("url") is None
    decoder._http = _Http([_response(200, '{"a":1}')])
    assert await decoder._fetch_json("url") == {"a": 1}
    decoder._http = _Http([_response(200, 'noise {"a":1} [2,3]')])
    assert await decoder._fetch_json("url") == [2, 3]
    decoder._http = _Http([_response(200, "not-json")])
    with pytest.raises(ValueError):
        await decoder._fetch_json("url")


@pytest.mark.asyncio
async def test_supervisor_activate_cleanup_and_no_spoiler_monitor(hass) -> None:
    supervisor = _supervisor(hass)
    window = _window()
    supervisor._monitor_window = AsyncMock(return_value="disconnect-window-expired")
    await supervisor._activate_window(window, source="index")
    supervisor._bus.start.assert_awaited_once()
    supervisor._bus.async_close.assert_awaited_once()
    assert supervisor.current_window is None

    monitor = _supervisor(hass)
    monitor._stopped = False
    monitor._interruptible_sleep = AsyncMock()
    hass.data.setdefault("f1_sensor", {})["no_spoiler_manager"] = SimpleNamespace(
        is_active=True
    )
    reason = await monitor._monitor_window(_window(), source="index")
    assert reason == "no-spoiler-activated"


@pytest.mark.parametrize("error", [asyncio.CancelledError, RuntimeError])
async def test_supervisor_interrupted_window_preserves_error_and_cleans_up(hass, error):
    """Cancellation/errors cannot leave an active window or mask the cause."""
    supervisor = _supervisor(hass)
    supervisor._monitor_window = AsyncMock(side_effect=error)
    with pytest.raises(error):
        await supervisor._activate_window(_window(), source="index")
    supervisor._bus.async_close.assert_awaited_once()
    supervisor._bus.set_heartbeat_expectation.assert_called_with(False)
    assert supervisor.availability.is_live is False
    assert supervisor.current_window is None
    assert supervisor._current_window_source == "none"


async def test_supervisor_close_failure_still_clears_availability(hass):
    supervisor = _supervisor(hass)
    supervisor._monitor_window = AsyncMock(return_value="disconnect-window-expired")
    supervisor._bus.async_close = AsyncMock(side_effect=RuntimeError("close failed"))
    with pytest.raises(RuntimeError, match="close failed"):
        await supervisor._activate_window(_window(), source="index")
    assert supervisor.availability.is_live is False
    assert supervisor.current_window is None
    assert supervisor._current_window_source == "none"


@pytest.mark.asyncio
async def test_supervisor_properties_wake_start_close_and_runner_gates(
    hass, monkeypatch
) -> None:
    supervisor = _supervisor(hass)
    assert supervisor.availability is supervisor._availability
    assert supervisor.current_window_source == "none"
    assert supervisor.last_schedule_error is None
    assert supervisor.fallback_source is None
    supervisor.wake()
    await supervisor._interruptible_sleep(1)
    assert supervisor._wake_event.is_set() is False

    ran = AsyncMock()
    monkeypatch.setattr(supervisor, "_runner", ran)
    await supervisor.async_start()
    await hass.async_block_till_done()
    ran.assert_awaited_once()
    await supervisor.async_start()
    await supervisor.async_close()
    assert supervisor._task is None

    async def _run_once(test_supervisor, result):
        test_supervisor._resolve_window = AsyncMock(return_value=result)

        async def _stop_after_sleep(_seconds):
            test_supervisor._stopped = True

        test_supervisor._interruptible_sleep = AsyncMock(side_effect=_stop_after_sleep)
        await test_supervisor._runner()

    idle = _supervisor(hass)
    await _run_once(idle, (None, "none"))
    assert idle.availability.reason == "no-session-found"

    future = _supervisor(hass)
    future_window = _window(now=datetime.now(UTC) + timedelta(hours=4))
    await _run_once(future, (future_window, "index"))
    assert future.availability.reason.startswith("waiting-")

    replay = _supervisor(hass)
    replay.availability.set_state(True, "replay")
    await _run_once(replay, (_window(), "index"))
    replay._bus.start.assert_not_awaited()

    spoiler = _supervisor(hass)
    hass.data.setdefault("f1_sensor", {})["no_spoiler_manager"] = SimpleNamespace(
        is_active=True
    )
    await _run_once(spoiler, (_window(), "index"))
    assert spoiler.availability.reason == "no-spoiler"


@pytest.mark.asyncio
async def test_supervisor_resolve_window_fallback_reconcile_and_recovery(hass) -> None:
    now = datetime.now(UTC)
    primary_window = _window(now=now)
    shifted = _window(now=now)
    shifted.start_utc += timedelta(minutes=30)
    shifted.end_utc += timedelta(minutes=30)
    shifted.connect_at += timedelta(minutes=30)
    shifted.disconnect_at += timedelta(minutes=30)

    primary = SimpleNamespace(
        async_fetch_windows=AsyncMock(
            return_value=ScheduleFetchResult(
                [primary_window], "index", index_http_status=200
            )
        )
    )
    fallback = SimpleNamespace(
        async_fetch_windows=AsyncMock(
            return_value=ScheduleFetchResult([shifted], "event_tracker")
        )
    )
    supervisor = _supervisor(hass, index=primary, fallback=fallback)
    selected, source = await supervisor._resolve_window()
    assert source == "event_tracker"
    assert selected is not None and selected.start_utc == shifted.start_utc
    assert supervisor.fallback_active is True

    primary.async_fetch_windows.return_value = ScheduleFetchResult(
        [], "index", index_http_status=503, last_error="index down"
    )
    selected, source = await supervisor._resolve_window()
    assert source == "event_tracker" and selected is not None
    assert supervisor.index_http_status == 503

    fallback.async_fetch_windows.return_value = ScheduleFetchResult(
        [], "event_tracker", last_error="fallback down"
    )
    selected, source = await supervisor._resolve_window()
    assert selected is None and source == "none"
    assert supervisor.last_schedule_error == "fallback down"

    supervisor._fallback_source = None
    selected, source = await supervisor._resolve_window()
    assert selected is None and source == "none"
    assert (
        supervisor._fallback_context(ScheduleFetchResult([], "index", last_error="bad"))
        == "index-error"
    )
    assert (
        supervisor._fallback_context(
            ScheduleFetchResult([], "index", index_http_status=404)
        )
        == "index-unavailable-http-404"
    )
    assert supervisor._fallback_context(ScheduleFetchResult([], "index")) == (
        "index-empty"
    )

    primary.async_fetch_windows.return_value = ScheduleFetchResult(
        [primary_window], "index", index_http_status=200
    )
    assert await supervisor._resolve_primary_window() is primary_window
    assert await supervisor._resolve_primary_window(active_window=shifted) is None


@pytest.mark.asyncio
async def test_supervisor_monitor_disconnect_extension_and_primary_recovery(
    hass, monkeypatch
) -> None:
    supervisor = _supervisor(hass)
    supervisor._stopped = False
    supervisor._interruptible_sleep = AsyncMock()
    now = datetime.now(UTC)
    window = _window(now=now - timedelta(hours=1))
    window.disconnect_at = now - timedelta(seconds=1)
    supervisor._bus.last_heartbeat_age.return_value = 1
    supervisor._bus.last_stream_activity_age.return_value = None
    calls = 0

    def _now():
        nonlocal calls
        calls += 1
        if calls > 1:
            supervisor._bus.last_heartbeat_age.return_value = None
            return now + timedelta(hours=2)
        return now

    monkeypatch.setattr("custom_components.f1_sensor.live_window.dt_util.utcnow", _now)
    reason = await supervisor._monitor_window(window, source="index")
    assert reason == "disconnect-window-expired"
    assert window.disconnect_at > now

    monkeypatch.setattr(
        "custom_components.f1_sensor.live_window.dt_util.utcnow", lambda: now
    )
    recovery = _supervisor(hass)
    recovery._stopped = False
    recovery._interruptible_sleep = AsyncMock()
    recovery._resolve_primary_window = AsyncMock(return_value=_window(now=now))
    recovery._last_primary_recovery_check = 0
    recovery._bus.last_heartbeat_age.return_value = None
    recovery._bus.last_stream_activity_age.return_value = None
    reason = await recovery._monitor_window(_window(now=now), source="event_tracker")
    assert reason == "primary-source-recovered"
