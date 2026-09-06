"""Behavior matrix for formation-start parsing and failure handling."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.util import dt as dt_util
import pytest

from custom_components.f1_sensor.formation_start import (
    FormationStartTracker,
    _build_static_url,
    _is_race_or_sprint,
    _normalize_session_phase,
    _parse_offset,
    _parse_utc,
    _session_start_utc,
)


class _Bus:
    def __init__(self, *, fail_stream: str | None = None) -> None:
        self.fail_stream = fail_stream
        self.callbacks: dict[str, object] = {}
        self.removed: list[str] = []

    def subscribe(self, stream, callback):
        if stream == self.fail_stream:
            raise RuntimeError("subscribe failed")
        self.callbacks[stream] = callback

        def _remove() -> None:
            self.removed.append(stream)

        return _remove


class _Response:
    def __init__(self, status: int, lines: list[bytes] | None = None) -> None:
        self.status = status
        self._lines = iter(lines or [])
        self.content = self

    async def readline(self) -> bytes:
        return next(self._lines, b"")

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError("http failure")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _Http:
    def __init__(self, response: _Response | None = None, *, fail=False) -> None:
        self.response = response
        self.fail = fail

    def get(self, _url):
        if self.fail:
            raise RuntimeError("connection failed")
        return self.response


def _tracker(hass, *, bus=None, http=None, guard=None) -> FormationStartTracker:
    return FormationStartTracker(
        hass,
        bus=bus or _Bus(),
        http_session=http or _Http(_Response(200)),
        availability_guard=guard,
    )


def _arm(tracker: FormationStartTracker, target: datetime | None = None) -> None:
    tracker._session_id = "race"
    tracker._session_type = "Race"
    tracker._session_name = "Race"
    tracker._session_phase = "pre"
    tracker._path = "2026/race"
    tracker._scheduled_start_utc = target or dt_util.utcnow().replace(microsecond=0)


def test_time_session_and_phase_normalizers_cover_supported_inputs() -> None:
    assert _parse_utc(None) is None
    assert _parse_utc("bad") is None
    assert _parse_utc("2026-09-01T12:00:00").tzinfo is UTC
    assert _parse_utc("2026-09-01T12:00:00Z") == datetime(2026, 9, 1, 12, tzinfo=UTC)
    assert _parse_offset(None) == timedelta()
    assert _parse_offset("+01:30:15") == timedelta(hours=1, minutes=30, seconds=15)
    assert _parse_offset("-02:00") == -timedelta(hours=2)
    assert _parse_offset("invalid") == timedelta()

    assert _session_start_utc(None) is None
    assert _session_start_utc({}) is None
    assert _session_start_utc({"StartDate": "bad"}) is None
    assert _session_start_utc(
        {"StartDate": "2026-09-01T13:00:00", "GmtOffset": "+01:00"}
    ) == datetime(2026, 9, 1, 12, tzinfo=UTC)
    assert _session_start_utc({"StartDate": "2026-09-01T12:00:00Z"}) == datetime(
        2026, 9, 1, 12, tzinfo=UTC
    )

    assert _is_race_or_sprint("Sprint", None) is True
    assert _is_race_or_sprint("Sprint Qualifying", None) is False
    assert _is_race_or_sprint(None, "Practice 1") is False
    assert _build_static_url("/2026/race/", "CarData.z") == (
        "https://livetiming.formula1.com/static/2026/race/CarData.z"
    )
    assert _normalize_session_phase(None) is None
    assert _normalize_session_phase({"Status": "Finished"}) == "terminal"
    assert _normalize_session_phase({"Started": True}) == "live"
    assert _normalize_session_phase({"SessionStatus": "Inactive"}) == "pre"
    assert _normalize_session_phase({"Status": "Unknown"}) is None


def test_listener_bus_guards_reset_and_direct_replay_marker(hass) -> None:
    bus = _Bus(fail_stream="SessionStatus")
    tracker = _tracker(hass, bus=bus)
    bad_listener = Mock(side_effect=RuntimeError("listener failed"))
    remove_bad = tracker.add_listener(bad_listener)
    good_listener = Mock()
    remove_good = tracker.add_listener(good_listener)
    assert set(bus.callbacks) == {"SessionInfo", "CarData.z"}

    _arm(tracker)
    tracker.inject_formation_ready(tracker._scheduled_start_utc + timedelta(seconds=2))
    assert tracker.snapshot()["status"] == "ready"
    assert tracker.snapshot()["source"] == "replay_index"
    tracker.inject_formation_ready(tracker._scheduled_start_utc)
    assert tracker.snapshot()["delta_seconds"] == 2

    tracker.reset(status="cleared")
    assert tracker.snapshot()["status"] == "cleared"
    remove_bad()
    remove_bad()
    remove_good()
    assert set(bus.removed) == {"SessionInfo", "CarData.z"}

    disabled = _tracker(hass, guard=Mock(side_effect=RuntimeError("guard failed")))
    assert disabled._tracking_enabled() is False
    _arm(disabled)
    disabled.inject_formation_ready(disabled._scheduled_start_utc)
    assert disabled.formation_start_utc is None


def test_session_changes_non_race_and_cardata_helpers(hass) -> None:
    tracker = _tracker(hass)
    tracker._task = SimpleNamespace(done=lambda: False, cancel=Mock())
    tracker._handle_session_info("bad")
    tracker._handle_session_status("bad")
    tracker._handle_session_info(
        {
            "Key": "practice",
            "Type": "Practice",
            "Name": "Practice 1",
            "StartDate": "2026-09-01T12:00:00Z",
            "SessionStatus": "Inactive",
        }
    )
    assert tracker.snapshot()["status"] == "not_applicable"
    assert tracker._task is None

    assert tracker._normalize_live_cardata_line(None) is None
    assert tracker._normalize_live_cardata_line(b"  ") is None
    assert tracker._normalize_live_cardata_line(b"payload") == '"payload"'
    assert tracker._normalize_live_cardata_line('"payload"') == '"payload"'
    target = datetime(2026, 9, 1, 12, tzinfo=UTC)
    assert tracker._has_converged(None, None, None, target) is False
    assert tracker._has_converged(target, 0, target, target) is True
    assert (
        tracker._has_converged(
            target - timedelta(seconds=2),
            2,
            target + timedelta(seconds=2),
            target,
        )
        is True
    )


@pytest.mark.asyncio
async def test_live_cardata_processing_and_consumption_guards(hass) -> None:
    tracker = _tracker(hass)
    await tracker._process_live_cardata("ignored")
    _arm(tracker)
    tracker._live_cardata_window_open = Mock(return_value=False)
    await tracker._process_live_cardata("ignored")
    tracker._live_cardata_window_open = Mock(return_value=True)
    await tracker._process_live_cardata(None)
    tracker._consume_live_cardata_utcs([])

    target = tracker._scheduled_start_utc
    tracker._consume_live_cardata_utcs(
        [target - timedelta(seconds=3), target + timedelta(seconds=1)]
    )
    assert tracker.snapshot()["status"] == "ready"
    assert tracker.snapshot()["source"] == "signalr_cardata"


@pytest.mark.asyncio
async def test_probe_http_failures_empty_and_out_of_window(hass) -> None:
    tracker = _tracker(hass, http=_Http(_Response(404)))
    _arm(tracker)
    assert await tracker._probe_cardata("race") is False
    assert tracker.snapshot()["error"] == "not_found"

    tracker._http = _Http(_Response(200))
    assert await tracker._probe_cardata("race") is False
    assert tracker.snapshot()["error"] == "empty"

    tracker._http = _Http(fail=True)
    assert await tracker._probe_cardata("race") is False
    assert tracker.snapshot()["error"] == "error"

    tracker._http = _Http(_Response(200, [b"x" * 400_000, b"\n"]))
    assert await tracker._probe_cardata("race") is False
    assert tracker.snapshot()["error"] == "empty"


@pytest.mark.asyncio
async def test_probe_runner_honors_cancellation_and_phase_change(hass) -> None:
    tracker = _tracker(hass)
    _arm(tracker)
    tracker._probe_cardata = AsyncMock(return_value=True)
    await tracker._run_probe(0, "race")
    tracker._probe_cardata.assert_awaited_once()

    tracker._probe_cardata.reset_mock()
    tracker._session_id = "different"
    await tracker._run_probe(0, "race")
    tracker._probe_cardata.assert_not_awaited()


async def test_formation_exact_subscription_phase_and_probe_paths(
    hass, monkeypatch
) -> None:
    failed_session = _tracker(hass, bus=_Bus(fail_stream="SessionInfo"))
    remove = failed_session.add_listener(Mock())
    assert failed_session._session_unsub is None
    remove()

    failed_cardata = _tracker(hass, bus=_Bus(fail_stream="CarData.z"))
    remove = failed_cardata.add_listener(Mock())
    assert failed_cardata._cardata_unsub is None
    remove()

    all_good = _tracker(hass, bus=_Bus())
    remove = all_good.add_listener(Mock())
    remove()
    assert all_good._status_unsub is None

    _arm(all_good)
    all_good._session_type = "Practice"
    all_good._session_name = "Practice 1"
    all_good.inject_formation_ready(all_good._scheduled_start_utc)
    assert all_good.formation_start_utc is None
    all_good._apply_session_phase(None)
    all_good._apply_session_phase("live")
    assert all_good.snapshot()["status"] == "live"
    all_good._handle_live_cardata("ignored")

    _arm(all_good)
    all_good._scheduled_start_utc = None
    assert all_good._live_cardata_window_open() is False
    all_good._consume_live_cardata_utcs([datetime.now(UTC)])
    all_good._task = SimpleNamespace(done=lambda: False)
    all_good._schedule_probe()
    all_good._task = None
    all_good._session_id = None
    all_good._schedule_probe()

    _arm(all_good)
    with monkeypatch.context() as context:
        context.setattr(
            asyncio,
            "sleep",
            AsyncMock(side_effect=asyncio.CancelledError),
        )
        await all_good._run_probe(1, "race")

    all_good._probe_allowed = Mock(return_value=True)
    all_good._probe_cardata = AsyncMock(return_value=False)
    all_good._status = "pending"
    all_good._session_phase = "pre"
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    await all_good._run_probe(0, "race")
    assert all_good.snapshot()["status"] == "unavailable"

    all_good._probe_allowed = Mock(return_value=False)
    assert await all_good._probe_cardata("wrong") is False


async def test_formation_probe_out_of_window_batch(hass, monkeypatch) -> None:
    target = datetime(2026, 9, 1, 12, tzinfo=UTC)
    tracker = _tracker(hass, http=_Http(_Response(200, [b'"encoded"\n'])))
    _arm(tracker, target)
    monkeypatch.setattr(
        hass,
        "async_add_executor_job",
        AsyncMock(return_value=[target + timedelta(minutes=11)]),
    )
    assert await tracker._probe_cardata("race") is False
    assert tracker.snapshot()["error"] == "out_of_window"
