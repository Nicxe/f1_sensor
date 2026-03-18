from __future__ import annotations

import asyncio
import base64
from datetime import UTC, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import zlib

from homeassistant.util import dt as dt_util
import pytest

from custom_components.f1_sensor.formation_start import FormationStartTracker
from custom_components.f1_sensor.replay_mode import (
    ReplayController,
    ReplayFrame,
    ReplayIndex,
    ReplaySession,
    ReplaySessionManager,
)
from custom_components.f1_sensor.signalr import LiveBus


def _make_cardata_line(utc_iso: str) -> bytes:
    """Build a single CarData.z.jsonStream line with one entry at the given UTC."""
    data = {"Entries": [{"Utc": utc_iso}]}
    raw = json.dumps(data).encode()
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(raw) + compressor.flush()
    encoded = base64.b64encode(compressed).decode()
    return f'"{encoded}"\n'.encode()


def _make_cardata_payload(utc_iso: str) -> str:
    return _make_cardata_line(utc_iso).decode().strip()


def _iso_utc(value) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class _AsyncLineContent:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = iter(lines)

    async def readline(self) -> bytes:
        return next(self._lines, b"")


class _LineResponse:
    def __init__(self, lines: list[bytes]) -> None:
        self.status = 200
        self.content = _AsyncLineContent(lines)

    def raise_for_status(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


class _LineHttpSession:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    def get(self, *_args, **_kwargs):
        return _LineResponse(list(self._lines))


class _ObservedLineContent:
    def __init__(
        self,
        lines: list[bytes],
        *,
        after_read=None,
        max_reads: int | None = None,
    ) -> None:
        self._lines = list(lines)
        self._after_read = after_read
        self._max_reads = max_reads
        self.reads = 0

    async def readline(self) -> bytes:
        self.reads += 1
        if self._max_reads is not None and self.reads > self._max_reads:
            raise RuntimeError("Read past expected convergence point")
        if self._after_read is not None:
            self._after_read(self.reads)
        if self.reads - 1 >= len(self._lines):
            return b""
        return self._lines[self.reads - 1]


class _ObservedLineResponse:
    def __init__(self, content) -> None:
        self.status = 200
        self.content = content

    def raise_for_status(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


class _ObservedLineHttpSession:
    def __init__(self, content) -> None:
        self._content = content

    def get(self, *_args, **_kwargs):
        return _ObservedLineResponse(self._content)


class _TimeoutAfterLinesContent:
    """Returns lines then raises TimeoutError to simulate a mid-stream timeout."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = iter(lines)

    async def readline(self) -> bytes:
        line = next(self._lines, None)
        if line is None:
            raise TimeoutError
        return line


class _TimeoutAfterLinesResponse:
    def __init__(self, lines: list[bytes]) -> None:
        self.status = 200
        self.content = _TimeoutAfterLinesContent(lines)

    def raise_for_status(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


class _TimeoutAfterLinesHttp:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    def get(self, *_args, **_kwargs):
        return _TimeoutAfterLinesResponse(list(self._lines))


class _CachingBus:
    def __init__(self, cached: dict[str, dict] | None = None) -> None:
        self._cached = cached or {}
        self.subscriptions: list[str] = []
        self._callbacks: dict[str, list] = {}

    def subscribe(self, stream: str, callback):
        self.subscriptions.append(stream)
        self._callbacks.setdefault(stream, []).append(callback)
        payload = self._cached.get(stream)
        if isinstance(payload, dict):
            callback(dict(payload))

        def _remove() -> None:
            callbacks = self._callbacks.get(stream)
            if callbacks and callback in callbacks:
                callbacks.remove(callback)

        return _remove

    def emit(self, stream: str, payload) -> None:
        for callback in list(self._callbacks.get(stream, [])):
            callback(payload)


class _TimeoutHttp:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, *_args, **_kwargs):
        self.calls += 1
        raise TimeoutError


class _ReplayBus:
    def __init__(self) -> None:
        self.injected: list[tuple[str, dict]] = []

    def subscribe(self, *_args, **_kwargs):
        return lambda: None

    def inject_message(self, stream: str, payload: dict) -> None:
        self.injected.append((stream, payload))

    async def swap_transport(self, _transport_factory) -> None:
        return None

    async def async_close(self) -> None:
        return None


class _InjectedFormationTracker:
    def __init__(self) -> None:
        self.injected: list = []

    def inject_formation_ready(self, formation_utc) -> None:
        self.injected.append(formation_utc)


def _session_info_payload(
    *,
    session_status: str = "Inactive",
    start_utc=None,
) -> dict[str, str]:
    start = start_utc or dt_util.utcnow().replace(microsecond=0)
    return {
        "Path": "2026/2026-03-08_Australian_Grand_Prix/2026-03-08_Race/",
        "Type": "Race",
        "Name": "Race",
        "StartDate": start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "GmtOffset": "+00:00",
        "SessionStatus": session_status,
    }


def _make_replay_session(
    *,
    session_name: str = "Race",
    session_type: str = "Race",
    path: str = "2026/2026-03-08_Australian_Grand_Prix/2026-03-08_Race",
) -> ReplaySession:
    start_utc = dt_util.utcnow().replace(microsecond=0)
    return ReplaySession(
        year=2026,
        meeting_key=100,
        meeting_name="Australian Grand Prix",
        session_key=200,
        session_name=session_name,
        session_type=session_type,
        path=path,
        start_utc=start_utc,
        end_utc=start_utc + timedelta(hours=1),
        available=True,
    )


def _make_replay_index(
    tmp_path: Path,
    *,
    formation_start_utc=None,
    initial_state: dict[str, dict] | None = None,
) -> ReplayIndex:
    frames_file = tmp_path / "frames.jsonl"
    frames_file.write_text("", encoding="utf-8")
    return ReplayIndex(
        session_id="test_session",
        total_frames=1,
        duration_ms=0,
        session_started_at_ms=0,
        frames_file=frames_file,
        index_file=tmp_path / "index.json",
        formation_started_at_ms=None,
        formation_start_utc=formation_start_utc,
        initial_state=initial_state,
        formation_initial_state=None,
    )


@pytest.mark.asyncio
async def test_late_session_info_does_not_rearm_after_session_goes_live(hass) -> None:
    tracker = FormationStartTracker(
        hass,
        bus=_CachingBus(),
        http_session=object(),  # type: ignore[arg-type]
    )
    probe_calls: list[tuple[float, str | None]] = []

    async def _fake_run_probe(delay: float, session_id: str | None) -> None:
        probe_calls.append((delay, session_id))

    tracker._run_probe = _fake_run_probe

    tracker._handle_session_info(_session_info_payload())
    await hass.async_block_till_done()

    assert len(probe_calls) == 1
    assert tracker.snapshot()["status"] == "pending"

    tracker._handle_session_status({"Status": "Started", "Started": "Started"})
    tracker._handle_session_info(_session_info_payload(session_status="Started"))
    await hass.async_block_till_done()

    assert len(probe_calls) == 1
    assert tracker.snapshot()["status"] == "live"

    tracker._handle_session_info(_session_info_payload(session_status="Finalised"))
    await hass.async_block_till_done()

    assert len(probe_calls) == 1
    assert tracker.snapshot()["status"] == "terminal"


@pytest.mark.asyncio
async def test_started_status_cancels_pending_probe(hass) -> None:
    tracker = FormationStartTracker(
        hass,
        bus=_CachingBus(),
        http_session=object(),  # type: ignore[arg-type]
    )
    start_utc = dt_util.utcnow() + timedelta(minutes=5)

    tracker._handle_session_info(_session_info_payload(start_utc=start_utc))

    assert tracker._task is not None

    tracker._handle_session_status({"Status": "Started", "Started": "Started"})

    assert tracker._task is None
    assert tracker.snapshot()["status"] == "live"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session_info_status", "session_status_payload", "expected_status"),
    [
        (
            "Started",
            {"Status": "Started", "Started": "Started"},
            "live",
        ),
        (
            "Finalised",
            {"Status": "Finalised", "Started": "Finished"},
            "terminal",
        ),
    ],
)
async def test_cached_late_payloads_do_not_schedule_probe(
    hass,
    session_info_status: str,
    session_status_payload: dict[str, str],
    expected_status: str,
) -> None:
    probe_calls: list[tuple[float, str | None]] = []
    tracker = FormationStartTracker(
        hass,
        bus=_CachingBus(
            {
                "SessionInfo": _session_info_payload(
                    session_status=session_info_status
                ),
                "SessionStatus": session_status_payload,
            }
        ),
        http_session=object(),  # type: ignore[arg-type]
    )

    async def _fake_run_probe(delay: float, session_id: str | None) -> None:
        probe_calls.append((delay, session_id))

    tracker._run_probe = _fake_run_probe

    snapshots: list[dict[str, str | None]] = []
    tracker.add_listener(lambda snapshot: snapshots.append(snapshot))
    await hass.async_block_till_done()

    assert probe_calls == []
    assert tracker.snapshot()["status"] == expected_status
    assert tracker.formation_start_utc is None
    assert snapshots[-1]["formation_start"] is None


@pytest.mark.asyncio
async def test_probe_cardata_timeout_sets_timeout_error(hass) -> None:
    timeout_http = _TimeoutHttp()
    tracker = FormationStartTracker(
        hass,
        bus=_CachingBus(),
        http_session=timeout_http,  # type: ignore[arg-type]
    )
    tracker._session_id = "session-1"
    tracker._session_phase = "pre"
    tracker._path = "2026/2026-03-20_Australian_Grand_Prix/2026-03-20_Race/"
    tracker._scheduled_start_utc = dt_util.utcnow()

    result = await tracker._probe_cardata("session-1")

    assert result is False
    assert timeout_http.calls == 1
    assert tracker.snapshot()["error"] == "timeout"


@pytest.mark.asyncio
async def test_successful_probe_sets_ready_status(hass) -> None:
    target = dt_util.utcnow().replace(microsecond=0)
    line = _make_cardata_line(_iso_utc(target))
    tracker = FormationStartTracker(
        hass,
        bus=_CachingBus(),
        http_session=_LineHttpSession([line]),  # type: ignore[arg-type]
    )
    tracker._session_id = "session-1"
    tracker._session_phase = "pre"
    tracker._path = "2026/2026-03-08_Australian_Grand_Prix/2026-03-08_Race/"
    tracker._scheduled_start_utc = target

    result = await tracker._probe_cardata("session-1")

    assert result is True
    assert tracker.snapshot()["status"] == "ready"
    assert tracker.snapshot()["source"] == "cardata"
    assert tracker.formation_start_utc is not None


@pytest.mark.asyncio
async def test_live_cardata_signalr_sets_ready_before_session_live(hass) -> None:
    bus = _CachingBus()
    tracker = FormationStartTracker(
        hass,
        bus=bus,  # type: ignore[arg-type]
        http_session=object(),  # type: ignore[arg-type]
    )
    tracker._schedule_probe = Mock()  # type: ignore[method-assign]
    snapshots: list[dict[str, str | float | None]] = []
    tracker.add_listener(lambda snapshot: snapshots.append(snapshot))

    target = dt_util.utcnow().replace(microsecond=0)
    tracker._handle_session_info(_session_info_payload(start_utc=target))

    bus.emit(
        "CarData.z",
        _make_cardata_payload(_iso_utc(target + timedelta(milliseconds=80))),
    )
    await hass.async_block_till_done()

    assert tracker.snapshot()["status"] == "ready"
    assert tracker.snapshot()["source"] == "signalr_cardata"
    assert tracker.snapshot()["delta_seconds"] == pytest.approx(0.08)
    assert tracker.formation_start_utc == target + timedelta(milliseconds=80)
    assert snapshots[-1]["status"] == "ready"


@pytest.mark.asyncio
async def test_live_cardata_after_session_live_does_not_emit_ready(hass) -> None:
    bus = _CachingBus()
    tracker = FormationStartTracker(
        hass,
        bus=bus,  # type: ignore[arg-type]
        http_session=object(),  # type: ignore[arg-type]
    )
    tracker._schedule_probe = Mock()  # type: ignore[method-assign]
    target = dt_util.utcnow().replace(microsecond=0)

    tracker.add_listener(lambda _snapshot: None)
    tracker._handle_session_info(_session_info_payload(start_utc=target))
    tracker._handle_session_status({"Status": "Started", "Started": "Started"})

    bus.emit(
        "CarData.z",
        _make_cardata_payload(_iso_utc(target + timedelta(milliseconds=80))),
    )
    await hass.async_block_till_done()

    assert tracker.snapshot()["status"] == "live"
    assert tracker.snapshot()["source"] is None
    assert tracker.formation_start_utc is None


@pytest.mark.asyncio
async def test_timeout_with_valid_partial_result_succeeds(hass) -> None:
    target = dt_util.utcnow().replace(microsecond=0)
    lines = [_make_cardata_line(_iso_utc(target - timedelta(milliseconds=500)))]
    tracker = FormationStartTracker(
        hass,
        bus=_CachingBus(),
        http_session=_TimeoutAfterLinesHttp(lines),  # type: ignore[arg-type]
    )
    tracker._session_id = "session-1"
    tracker._session_phase = "pre"
    tracker._path = "2026/2026-03-08_Australian_Grand_Prix/2026-03-08_Race/"
    tracker._scheduled_start_utc = target

    result = await tracker._probe_cardata("session-1")

    assert result is True
    assert tracker.snapshot()["status"] == "ready"
    assert tracker.snapshot()["error"] is None
    assert tracker.snapshot()["delta_seconds"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_probe_returns_not_reached_when_stream_ends_too_early(hass) -> None:
    target = dt_util.utcnow().replace(microsecond=0)
    tracker = FormationStartTracker(
        hass,
        bus=_CachingBus(),
        http_session=_LineHttpSession(
            [
                _make_cardata_line(_iso_utc(target - timedelta(seconds=5))),
                _make_cardata_line(_iso_utc(target - timedelta(seconds=2))),
            ]
        ),  # type: ignore[arg-type]
    )
    tracker._session_id = "session-1"
    tracker._session_phase = "pre"
    tracker._path = "2026/2026-03-08_Australian_Grand_Prix/2026-03-08_Race/"
    tracker._scheduled_start_utc = target

    result = await tracker._probe_cardata("session-1")

    assert result is False
    assert tracker.snapshot()["error"] == "not_reached"


@pytest.mark.asyncio
async def test_probe_resolves_nearest_timestamp_as_soon_as_it_converges(
    hass,
) -> None:
    target = dt_util.utcnow().replace(microsecond=0)
    content = _ObservedLineContent(
        [
            _make_cardata_line(_iso_utc(target - timedelta(milliseconds=200))),
            _make_cardata_line(_iso_utc(target + timedelta(milliseconds=90))),
            _make_cardata_line(_iso_utc(target + timedelta(milliseconds=500))),
            _make_cardata_line(_iso_utc(target + timedelta(seconds=10))),
        ],
        max_reads=2,
    )
    tracker = FormationStartTracker(
        hass,
        bus=_CachingBus(),
        http_session=_ObservedLineHttpSession(content),  # type: ignore[arg-type]
    )
    tracker._session_id = "session-1"
    tracker._session_phase = "pre"
    tracker._path = "2026/2026-03-08_Australian_Grand_Prix/2026-03-08_Race/"
    tracker._scheduled_start_utc = target

    result = await tracker._probe_cardata("session-1")

    assert result is True
    assert tracker.formation_start_utc == target + timedelta(milliseconds=90)
    assert tracker.snapshot()["delta_seconds"] == pytest.approx(0.09)
    assert content.reads == 2


@pytest.mark.asyncio
async def test_probe_does_not_emit_ready_after_session_goes_live(hass) -> None:
    target = dt_util.utcnow().replace(microsecond=0)
    tracker = FormationStartTracker(
        hass,
        bus=_CachingBus(),
        http_session=None,  # type: ignore[arg-type]
    )
    tracker._session_id = "session-1"
    tracker._session_phase = "pre"
    tracker._path = "2026/2026-03-08_Australian_Grand_Prix/2026-03-08_Race/"
    tracker._scheduled_start_utc = target

    def _mark_live(reads: int) -> None:
        if reads == 2:
            tracker._handle_session_status({"Status": "Started", "Started": "Started"})

    content = _ObservedLineContent(
        [
            _make_cardata_line(_iso_utc(target - timedelta(milliseconds=300))),
            _make_cardata_line(_iso_utc(target + timedelta(milliseconds=80))),
        ],
        after_read=_mark_live,
    )
    tracker._http = _ObservedLineHttpSession(content)  # type: ignore[assignment]

    result = await tracker._probe_cardata("session-1")

    assert result is False
    assert tracker.formation_start_utc is None
    assert tracker.snapshot()["status"] == "live"


@pytest.mark.asyncio
async def test_exhausted_probes_set_unavailable(hass) -> None:
    tracker = FormationStartTracker(
        hass,
        bus=_CachingBus(),
        http_session=object(),  # type: ignore[arg-type]
    )
    tracker._session_id = "session-1"
    tracker._session_phase = "pre"
    tracker._path = "2026/2026-03-08_Australian_Grand_Prix/2026-03-08_Race/"
    tracker._scheduled_start_utc = dt_util.utcnow()
    tracker._status = "pending"

    with patch.object(asyncio, "sleep", new_callable=AsyncMock):
        tracker._probe_cardata = AsyncMock(return_value=False)
        await tracker._run_probe(0.0, "session-1")

    assert tracker.snapshot()["status"] == "unavailable"


@pytest.mark.asyncio
async def test_probe_watch_is_armed_before_scheduled_start(hass) -> None:
    tracker = FormationStartTracker(
        hass,
        bus=_CachingBus(),
        http_session=object(),  # type: ignore[arg-type]
    )
    probe_calls: list[tuple[float, str | None]] = []

    async def _fake_run_probe(delay: float, session_id: str | None) -> None:
        probe_calls.append((delay, session_id))

    tracker._run_probe = _fake_run_probe

    fixed_now = dt_util.utcnow().replace(microsecond=0)
    start_utc = fixed_now + timedelta(minutes=5)

    with patch(
        "custom_components.f1_sensor.formation_start.dt_util.utcnow",
        return_value=fixed_now,
    ):
        tracker._handle_session_info(_session_info_payload(start_utc=start_utc))
        await hass.async_block_till_done()

    assert len(probe_calls) == 1
    assert probe_calls[0] == (295.0, tracker._session_id)


@pytest.mark.asyncio
async def test_live_bus_dispatches_non_dict_cardata_without_breaking_dict_streams(
    hass,
) -> None:
    bus = LiveBus(hass, Mock())
    received: list[str] = []

    bus.subscribe("CarData.z", lambda payload: received.append(payload))
    bus.inject_message("CarData.z", _make_cardata_payload(_iso_utc(dt_util.utcnow())))
    bus.inject_message("SessionStatus", {"Status": "Started"})

    diagnostics = bus.stream_diagnostics(["CarData.z", "SessionStatus"])

    assert len(received) == 1
    assert isinstance(received[0], str)
    assert diagnostics["CarData.z"] == {
        "frame_count": 1,
        "last_seen_age_s": 0.0,
        "last_payload_keys": None,
    }
    assert diagnostics["SessionStatus"]["last_payload_keys"] == ["Status"]


@pytest.mark.asyncio
async def test_replay_controller_injects_cached_formation_marker(
    hass, tmp_path
) -> None:
    http_session = SimpleNamespace(get=Mock())
    bus = _ReplayBus()
    tracker = _InjectedFormationTracker()
    controller = ReplayController(
        hass,
        "entry-test",
        http_session,  # type: ignore[arg-type]
        bus,
        formation_tracker=tracker,  # type: ignore[arg-type]
        start_reference_controller=SimpleNamespace(current="session"),
    )
    formation_start = dt_util.utcnow().replace(microsecond=0)
    index = _make_replay_index(
        tmp_path,
        formation_start_utc=formation_start,
        initial_state={
            "SessionInfo": {"Type": "Race", "Name": "Race"},
            "SessionStatus": {"Status": "Inactive", "Started": "Inactive"},
        },
    )

    controller.session_manager._loaded_index = index
    controller._inject_initial_state(index.initial_state)
    controller._inject_formation_ready_if_applicable(index)

    assert bus.injected == list(index.initial_state.items())
    assert tracker.injected == [formation_start]
    assert not http_session.get.called


@pytest.mark.asyncio
async def test_replay_manager_rebuilds_old_cache_with_formation_marker(
    hass, tmp_path
) -> None:
    manager = ReplaySessionManager(hass, "entry-test", AsyncMock())  # type: ignore[arg-type]
    manager._cache_dir = tmp_path
    session = _make_replay_session()
    session_dir = tmp_path / session.unique_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "frames.jsonl").write_text('{"cached":true}\n', encoding="utf-8")
    (session_dir / "index.json").write_text(
        json.dumps(
            {
                "cache_version": 6,
                "session_id": session.unique_id,
                "total_frames": 1,
                "duration_ms": 0,
                "session_started_at_ms": 0,
                "initial_state": {},
                "formation_initial_state": None,
            }
        ),
        encoding="utf-8",
    )
    formation_start = session.start_utc + timedelta(milliseconds=120)
    manager._download_stream = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            ReplayFrame(
                timestamp_ms=0,
                stream="TimingData",
                payload={"Utc": _iso_utc(session.start_utc)},
            )
        ]
    )
    manager._find_formation_start_utc = AsyncMock(  # type: ignore[method-assign]
        return_value=formation_start
    )
    manager._find_closest_frame_ms = Mock(return_value=0)  # type: ignore[method-assign]

    index = await manager._download_and_index_session(session)

    assert manager._download_stream.await_count > 0
    saved = json.loads((session_dir / "index.json").read_text(encoding="utf-8"))
    assert saved["cache_version"] == 8
    assert saved["formation_start_utc"] == formation_start.isoformat()
    assert index.formation_start_utc == formation_start


@pytest.mark.asyncio
async def test_replay_manager_handles_non_race_sessions_without_marker(
    hass, tmp_path
) -> None:
    manager = ReplaySessionManager(hass, "entry-test", AsyncMock())  # type: ignore[arg-type]
    manager._cache_dir = tmp_path
    session = _make_replay_session(
        session_name="Practice 1",
        session_type="Practice",
        path="2026/2026-03-08_Australian_Grand_Prix/2026-03-08_Practice_1",
    )
    manager._download_stream = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            ReplayFrame(
                timestamp_ms=0,
                stream="TimingData",
                payload={"Utc": _iso_utc(session.start_utc)},
            )
        ]
    )
    manager._find_formation_start_utc = AsyncMock()  # type: ignore[method-assign]

    index = await manager._download_and_index_session(session)

    assert index.formation_start_utc is None
    manager._find_formation_start_utc.assert_not_awaited()
