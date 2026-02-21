from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from homeassistant.util import dt as dt_util

import custom_components.f1_sensor.live_window as live_window
from custom_components.f1_sensor.live_window import (
    EventTrackerScheduleSource,
    LiveSessionSupervisor,
    ScheduleFetchResult,
    SessionWindow,
)


class _DummySessionCoordinator:
    def __init__(self, data: dict | None, *, status: int | None = None) -> None:
        self.data = data
        self.last_http_status = status
        self.year = 2026

    async def async_refresh(self) -> None:
        return None

    async def async_request_refresh(self) -> None:
        return None


class _DummyBus:
    def __init__(self) -> None:
        self.started = False
        self.heartbeat_expected = False

    async def start(self) -> None:
        self.started = True

    async def async_close(self) -> None:
        self.started = False

    def set_heartbeat_expectation(self, expected: bool) -> None:
        self.heartbeat_expected = expected

    def last_heartbeat_age(self) -> float:
        return 0.0

    def last_stream_activity_age(self, *_streams: Any) -> float:
        return 0.0


class _StaticSource:
    def __init__(self, result: ScheduleFetchResult) -> None:
        self._result = result
        self.calls = 0

    async def async_fetch_windows(
        self,
        *,
        pre_window: dt.timedelta,
        post_window: dt.timedelta,
        active: bool = False,
    ) -> ScheduleFetchResult:
        del pre_window, post_window, active
        self.calls += 1
        return self._result


def _iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _mk_window(
    *,
    meeting: str = "Test Meeting",
    session: str = "Practice",
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
    meeting_key: int | None = 1304,
    session_key: int | None = 11465,
    path: str = "",
) -> SessionWindow:
    now = dt_util.utcnow()
    start_utc = start or (now + dt.timedelta(minutes=10))
    end_utc = end or (start_utc + dt.timedelta(hours=1))
    return SessionWindow(
        meeting_name=meeting,
        session_name=session,
        path=path,
        start_utc=start_utc,
        end_utc=end_utc,
        connect_at=start_utc - dt.timedelta(minutes=60),
        disconnect_at=end_utc + dt.timedelta(minutes=15),
        meeting_key=meeting_key,
        session_key=session_key,
    )


@pytest.mark.asyncio
async def test_index_has_windows_uses_primary(hass) -> None:
    now = dt_util.utcnow()
    payload = {
        "Meetings": [
            {
                "Name": "Bahrain",
                "Key": 1304,
                "Sessions": [
                    {
                        "Name": "Practice 1",
                        "Key": 11465,
                        "Path": "2026/1304/11465/",
                        "StartDate": _iso_z(now + dt.timedelta(minutes=20)),
                        "EndDate": _iso_z(now + dt.timedelta(hours=2)),
                        "GmtOffset": "+00:00",
                    }
                ],
            }
        ]
    }
    coord = _DummySessionCoordinator(payload, status=200)
    fallback = _StaticSource(
        ScheduleFetchResult(windows=[_mk_window()], source="event_tracker")
    )
    supervisor = LiveSessionSupervisor(
        hass,
        coord,
        _DummyBus(),
        http_session=object(),  # type: ignore[arg-type]
        fallback_source=fallback,
    )

    window, source = await supervisor._resolve_window()

    assert window is not None
    assert source == "index"
    assert fallback.calls == 0
    assert supervisor.schedule_source == "index"
    assert supervisor.fallback_active is False


@pytest.mark.asyncio
async def test_index_403_uses_event_tracker(hass) -> None:
    coord = _DummySessionCoordinator({}, status=403)
    fallback_window = _mk_window(session="Day 1")
    fallback = _StaticSource(
        ScheduleFetchResult(windows=[fallback_window], source="event_tracker")
    )
    supervisor = LiveSessionSupervisor(
        hass,
        coord,
        _DummyBus(),
        http_session=object(),  # type: ignore[arg-type]
        fallback_source=fallback,
    )

    window, source = await supervisor._resolve_window()

    assert window is not None
    assert source == "event_tracker"
    assert supervisor.schedule_source == "event_tracker"
    assert supervisor.index_http_status == 403
    assert supervisor.fallback_active is True


@pytest.mark.asyncio
async def test_index_healthy_past_schedule_uses_fallback(hass) -> None:
    now = dt_util.utcnow()
    payload = {
        "Meetings": [
            {
                "Name": "Abu Dhabi",
                "Key": 1299,
                "Sessions": [
                    {
                        "Name": "Race",
                        "Key": 11001,
                        "Path": "2025/1299/11001/",
                        "StartDate": _iso_z(now - dt.timedelta(days=4)),
                        "EndDate": _iso_z(
                            now - dt.timedelta(days=4) + dt.timedelta(hours=2)
                        ),
                        "GmtOffset": "+00:00",
                    }
                ],
            }
        ]
    }
    coord = _DummySessionCoordinator(payload, status=200)
    fallback = _StaticSource(
        ScheduleFetchResult(
            windows=[_mk_window(session="Fallback session")], source="event_tracker"
        )
    )
    supervisor = LiveSessionSupervisor(
        hass,
        coord,
        _DummyBus(),
        http_session=object(),  # type: ignore[arg-type]
        fallback_source=fallback,
    )

    window, source = await supervisor._resolve_window()

    assert window is not None
    assert source == "event_tracker"
    assert fallback.calls == 1
    assert supervisor.schedule_source == "event_tracker"
    assert supervisor.fallback_active is True


@pytest.mark.asyncio
async def test_index_empty_event_tracker_empty_fail_closed(hass) -> None:
    coord = _DummySessionCoordinator({}, status=403)
    fallback = _StaticSource(ScheduleFetchResult(windows=[], source="event_tracker"))
    supervisor = LiveSessionSupervisor(
        hass,
        coord,
        _DummyBus(),
        http_session=object(),  # type: ignore[arg-type]
        fallback_source=fallback,
    )

    window, source = await supervisor._resolve_window()

    assert window is None
    assert source == "none"
    assert supervisor.schedule_source == "none"
    assert supervisor.fallback_active is False


@pytest.mark.asyncio
async def test_index_200_without_windows_uses_event_tracker(hass) -> None:
    coord = _DummySessionCoordinator({}, status=200)
    fallback_window = _mk_window(session="Fallback session")
    fallback = _StaticSource(
        ScheduleFetchResult(windows=[fallback_window], source="event_tracker")
    )
    supervisor = LiveSessionSupervisor(
        hass,
        coord,
        _DummyBus(),
        http_session=object(),  # type: ignore[arg-type]
        fallback_source=fallback,
    )

    window, source = await supervisor._resolve_window()

    assert window is not None
    assert source == "event_tracker"
    assert fallback.calls == 1
    assert supervisor.schedule_source == "event_tracker"
    assert supervisor.fallback_active is True


def test_event_tracker_parses_offset_correctly() -> None:
    source = EventTrackerScheduleSource(object())  # type: ignore[arg-type]
    payload = {
        "seasonContext": {"currentOrNextMeetingKey": "1304"},
        "race": {"meetingOfficialName": "Pre-Season Testing"},
        "event": {
            "timetables": [
                {
                    "session": "p1",
                    "shortName": "FP1",
                    "description": "Day 1",
                    "startTime": "2026-02-11T10:00:00",
                    "endTime": "2026-02-11T19:00:00",
                    "gmtOffset": "+03:00",
                    "meetingSessionKey": 11465,
                }
            ]
        },
    }

    windows = source._windows_from_payload(
        payload,
        pre_window=dt.timedelta(minutes=60),
        post_window=dt.timedelta(minutes=15),
        meeting_key=1304,
    )

    assert len(windows) == 1
    assert windows[0].start_utc == dt.datetime(
        2026, 2, 11, 7, 0, tzinfo=dt.timezone.utc
    )
    assert windows[0].end_utc == dt.datetime(2026, 2, 11, 16, 0, tzinfo=dt.timezone.utc)
    assert windows[0].connect_at == dt.datetime(
        2026, 2, 11, 6, 0, tzinfo=dt.timezone.utc
    )
    assert windows[0].meeting_key == 1304
    assert windows[0].session_key == 11465


def test_event_tracker_extract_timetables_skips_empty_first_candidate() -> None:
    payload = {
        "seasonContext": {"timetables": []},
        "event": {
            "timetables": [
                {
                    "description": "Day 1",
                    "startTime": "2026-02-11T10:00:00",
                    "endTime": "2026-02-11T19:00:00",
                    "gmtOffset": "+03:00",
                    "meetingSessionKey": 11465,
                }
            ]
        },
    }

    rows = EventTrackerScheduleSource._extract_timetables(payload)

    assert len(rows) == 1
    assert rows[0]["description"] == "Day 1"


@pytest.mark.asyncio
async def test_event_tracker_updates_meeting_key_automatically(monkeypatch) -> None:
    source = EventTrackerScheduleSource(
        object(),  # type: ignore[arg-type]
        active_cache_ttl=0,
        idle_cache_ttl=0,
    )
    root_payloads = [
        {"seasonContext": {"currentOrNextMeetingKey": "1304", "timetables": []}},
        {"seasonContext": {"currentOrNextMeetingKey": "1305", "timetables": []}},
    ]
    meeting_1304 = {
        "meetingContext": {
            "meetingKey": "1304",
            "timetables": [
                {
                    "description": "Day 1",
                    "startTime": "2026-02-11T10:00:00",
                    "endTime": "2026-02-11T19:00:00",
                    "gmtOffset": "+03:00",
                    "meetingSessionKey": 11465,
                }
            ],
        },
        "race": {"meetingName": "Test 1"},
    }
    meeting_1305 = {
        "meetingContext": {
            "meetingKey": "1305",
            "timetables": [
                {
                    "description": "Day 1",
                    "startTime": "2026-02-18T10:00:00",
                    "endTime": "2026-02-18T19:00:00",
                    "gmtOffset": "+03:00",
                    "meetingSessionKey": 11468,
                }
            ],
        },
        "race": {"meetingName": "Test 2"},
    }
    calls: list[str] = []

    async def _fake_refresh(*, force: bool = False) -> None:
        del force
        return None

    async def _fake_fetch(
        endpoint: str,
        *,
        allow_retry: bool = True,
        endpoint_kind: str = "direct",
        meeting_key: int | None = None,
    ) -> dict:
        del allow_retry, endpoint_kind, meeting_key
        calls.append(endpoint)
        if endpoint == source._endpoint:
            return root_payloads.pop(0)
        if endpoint.endswith("/1304"):
            return meeting_1304
        if endpoint.endswith("/1305"):
            return meeting_1305
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(source, "_refresh_dynamic_config", _fake_refresh)
    monkeypatch.setattr(source, "_fetch_tracker_json", _fake_fetch)

    first = await source.async_fetch_windows(
        pre_window=dt.timedelta(minutes=60),
        post_window=dt.timedelta(minutes=15),
        active=False,
    )
    second = await source.async_fetch_windows(
        pre_window=dt.timedelta(minutes=60),
        post_window=dt.timedelta(minutes=15),
        active=False,
    )

    assert first.windows[0].meeting_key == 1304
    assert second.windows[0].meeting_key == 1305
    assert any(call.endswith("/1304") for call in calls)
    assert any(call.endswith("/1305") for call in calls)


@pytest.mark.asyncio
async def test_event_tracker_retry_uses_refreshed_root_endpoint(monkeypatch) -> None:
    class _FakeResponse:
        def __init__(self, status: int, body: str) -> None:
            self.status = status
            self._body = body

        async def __aenter__(self) -> "_FakeResponse":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

        async def text(self) -> str:
            return self._body

    class _FakeHttp:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get(self, url: str, headers: dict | None = None) -> _FakeResponse:
            del headers
            self.calls.append(url)
            if url.endswith("/v1/event-tracker"):
                return _FakeResponse(403, "forbidden")
            if url.endswith("/v2/event-tracker"):
                return _FakeResponse(
                    200,
                    '{"seasonContext":{"currentOrNextMeetingKey":"1304","timetables":[]}}',
                )
            raise AssertionError(f"unexpected URL: {url}")

    fake_http = _FakeHttp()
    source = EventTrackerScheduleSource(
        fake_http,  # type: ignore[arg-type]
        base_url="https://api.formula1.com",
        endpoint="/v1/event-tracker",
    )

    async def _fake_refresh(*, force: bool = False) -> None:
        del force
        source._endpoint = "/v2/event-tracker"

    monkeypatch.setattr(source, "_refresh_dynamic_config", _fake_refresh)

    payload = await source._fetch_tracker_json(
        "/v1/event-tracker",
        endpoint_kind="root",
    )

    assert payload.get("seasonContext", {}).get("currentOrNextMeetingKey") == "1304"
    assert fake_http.calls == [
        "https://api.formula1.com/v1/event-tracker",
        "https://api.formula1.com/v2/event-tracker",
    ]


@pytest.mark.asyncio
async def test_switch_back_to_index_when_recovered(monkeypatch, hass) -> None:
    coord = _DummySessionCoordinator({}, status=403)
    supervisor = LiveSessionSupervisor(
        hass,
        coord,
        _DummyBus(),
        http_session=object(),  # type: ignore[arg-type]
    )
    fallback_window = _mk_window(
        session="Day 1",
        start=dt_util.utcnow() - dt.timedelta(minutes=5),
        end=dt_util.utcnow() + dt.timedelta(hours=2),
    )
    candidate_window = _mk_window(session="Practice 1", path="2026/1304/11465/")

    async def _no_sleep(_seconds: float) -> None:
        return None

    async def _primary_window() -> SessionWindow | None:
        return candidate_window

    monkeypatch.setattr(live_window.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(
        live_window,
        "PRIMARY_RECOVERY_CHECK_INTERVAL",
        dt.timedelta(seconds=0),
    )
    monkeypatch.setattr(supervisor, "_resolve_primary_window", _primary_window)

    reason = await supervisor._monitor_window(fallback_window, source="event_tracker")

    assert reason == "primary-source-recovered"


@pytest.mark.asyncio
async def test_no_legacy_blind_fallback_when_both_down(monkeypatch, hass) -> None:
    coord = _DummySessionCoordinator({}, status=403)
    bus = _DummyBus()
    index = _StaticSource(
        ScheduleFetchResult(
            windows=[],
            source="index",
            index_http_status=403,
            last_error="index-down",
        )
    )
    fallback = _StaticSource(
        ScheduleFetchResult(
            windows=[], source="event_tracker", last_error="fallback-down"
        )
    )
    supervisor = LiveSessionSupervisor(
        hass,
        coord,
        bus,
        http_session=object(),  # type: ignore[arg-type]
        index_source=index,
        fallback_source=fallback,
    )

    async def _stop_sleep(_seconds: float) -> None:
        supervisor._stopped = True
        return None

    monkeypatch.setattr(supervisor, "_interruptible_sleep", _stop_sleep)
    await supervisor._runner()

    assert bus.started is False
