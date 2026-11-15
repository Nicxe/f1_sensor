"""Regression coverage for bounded, shared replay telemetry work."""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime, timedelta
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import zlib

import pytest

from custom_components.f1_sensor import replay_telemetry as telemetry


def _recording(tmp_path, *, name="frames", driver=4, session_id="session"):
    """Create three selectable laps with an explicit recorded session start."""
    start = datetime(2026, 9, 1, 12, tzinfo=UTC)
    frames = [
        {
            "t": 0,
            "s": "SessionStatus",
            "p": {"Status": "Started", "Utc": start.isoformat()},
        },
        {"t": 0, "s": "DriverList", "p": {str(driver): {"Tla": f"D{driver}"}}},
        *[
            {
                "t": lap * 1000,
                "s": "TimingData",
                "p": {"Lines": {str(driver): {"NumberOfLaps": lap}}},
            }
            for lap in range(1, 4)
        ],
    ]
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(frame) for frame in frames), encoding="utf-8")
    return SimpleNamespace(
        session_id=session_id, frames_file=path, session_started_at_ms=0
    )


def _manager(index):
    manager = SimpleNamespace(
        index=index,
        selected_session=SimpleNamespace(
            path="2026/Test/Race",
            start_utc=datetime(2026, 9, 1, 12, tzinfo=UTC),
        ),
    )
    manager.get_loaded_index = lambda: manager.index
    return manager


def _selection(lap=1, driver=4):
    return [{"driver_number": driver, "lap_number": lap}]


def _telemetry_line() -> bytes:
    start = datetime(2026, 9, 1, 12, tzinfo=UTC)
    payload = {
        "Entries": [
            {
                "Utc": (start + timedelta(milliseconds=stamp)).isoformat(),
                "Cars": {
                    str(driver): {"Channels": {"2": 300, "4": 100}}
                    for driver in (4, 16)
                },
            }
            for stamp in (200, 800, 1200, 1800, 2200, 2800)
        ]
    }
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(json.dumps(payload).encode()) + compressor.flush()
    return b'"' + base64.b64encode(compressed) + b'"\n'


class _Response:
    status = 200

    def __init__(self, release: asyncio.Event) -> None:
        self.content = self
        self.worker = None
        self.exited = False
        self._release = release
        self._lines = iter((_telemetry_line(),))

    async def readline(self) -> bytes:
        await self._release.wait()
        return next(self._lines, b"")

    async def __aenter__(self):
        self.worker = asyncio.current_task()
        return self

    async def __aexit__(self, *_args):
        self.exited = True
        return None


class _Session:
    """Give every remote request an independent stream and an optional barrier."""

    def __init__(self, *, blocked=False) -> None:
        self.release = asyncio.Event()
        if not blocked:
            self.release.set()
        self.started = asyncio.Queue()
        self.requests = 0
        self.responses = []

    def get(self, _url):
        self.requests += 1
        self.started.put_nowait(self.requests)
        response = _Response(self.release)
        self.responses.append(response)
        return response


class _ScanBarrier:
    """Hold actual file processing in the executor without mocking HA internals."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = threading.Event()
        self.calls = []
        self._loop = asyncio.get_running_loop()
        self._scan = telemetry._scan_replay_timing

    def __call__(self, *args, **kwargs):
        self.calls.append(args[0])
        self._loop.call_soon_threadsafe(self.entered.set)
        if not self.release.wait(timeout=5):
            raise TimeoutError("Test did not release the recording scan")
        return self._scan(*args, **kwargs)


async def _start_call(coroutine):
    """Run a caller until its first suspension before admitting the next one."""
    entered = asyncio.Event()

    async def invoke():
        entered.set()
        return await coroutine

    task = asyncio.create_task(invoke())
    await entered.wait()
    return task


async def _finish(service, tasks, session, scan=None) -> None:
    """Release every barrier even when an assertion fails on unfixed code."""
    if scan is not None:
        scan.release.set()
    session.release.set()
    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=5
        )
    finally:
        await service.async_close()


async def test_missing_selections_share_one_recording_scan(
    hass, tmp_path, monkeypatch
) -> None:
    """New invalid selections must not cause another full recording read."""
    scan = Mock(wraps=telemetry._scan_replay_timing)
    monkeypatch.setattr(telemetry, "_scan_replay_timing", scan)
    session = _Session()
    service = telemetry.ReplayTelemetryService(
        hass, session, _manager(_recording(tmp_path))
    )
    try:
        for lap in range(4, 20):
            for selection in (_selection(lap), _selection(1, driver=lap + 20)):
                with pytest.raises(ValueError, match="unavailable"):
                    await service.async_compare(selection)
        assert scan.call_count == 1
        assert session.requests == 0
    finally:
        await service.async_close()


async def test_concurrent_identical_comparisons_share_extraction_and_copy_results(
    hass, tmp_path
) -> None:
    session = _Session(blocked=True)
    service = telemetry.ReplayTelemetryService(
        hass, session, _manager(_recording(tmp_path))
    )
    tasks = []
    try:
        tasks.append(await _start_call(service.async_compare(_selection())))
        await asyncio.wait_for(session.started.get(), timeout=1)
        for _ in range(3):
            tasks.append(await _start_call(service.async_compare(_selection())))
        session.release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)

        assert session.requests == 1
        assert all(result == results[0] for result in results)
        assert results[0]["series"][0]["sample_count"] == 2
        results[0]["series"][0]["samples"][0]["speed"] = -1
        assert results[1]["series"][0]["samples"][0]["speed"] == 300
        cached = await service.async_compare(_selection())
        assert cached["series"][0]["samples"][0]["speed"] == 300
        assert session.requests == 1
    finally:
        await _finish(service, tasks, session)


@pytest.mark.parametrize("caller", ["catalog", "comparison"])
async def test_cancelled_caller_does_not_duplicate_recording_scan(
    hass, tmp_path, monkeypatch, caller
) -> None:
    scan = _ScanBarrier()
    monkeypatch.setattr(telemetry, "_scan_replay_timing", scan)
    session = _Session()
    service = telemetry.ReplayTelemetryService(
        hass, session, _manager(_recording(tmp_path))
    )

    def request():
        if caller == "catalog":
            return service.async_catalog(expected_session_id="session")
        return service.async_compare(_selection())

    tasks = []
    try:
        tasks.append(await _start_call(request()))
        await asyncio.wait_for(scan.entered.wait(), timeout=1)
        tasks[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[0]
        tasks.append(await _start_call(request()))
        scan.release.set()
        result = await asyncio.wait_for(tasks[1], timeout=5)

        assert result["session_id"] == "session"
        assert len(scan.calls) == 1
        assert session.requests == (0 if caller == "catalog" else 1)
    finally:
        await _finish(service, tasks, session, scan)


async def test_cancelled_caller_does_not_duplicate_remote_extraction(
    hass, tmp_path
) -> None:
    session = _Session(blocked=True)
    service = telemetry.ReplayTelemetryService(
        hass, session, _manager(_recording(tmp_path))
    )
    tasks = []
    try:
        tasks.append(await _start_call(service.async_compare(_selection())))
        await asyncio.wait_for(session.started.get(), timeout=1)
        tasks[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[0]
        tasks.append(await _start_call(service.async_compare(_selection())))
        session.release.set()
        result = await asyncio.wait_for(tasks[1], timeout=5)

        assert result["series"][0]["sample_count"] == 2
        assert session.requests == 1
    finally:
        await _finish(service, tasks, session)


async def test_distinct_comparison_capacity_rejects_excess_work_promptly(
    hass, tmp_path
) -> None:
    session = _Session(blocked=True)
    service = telemetry.ReplayTelemetryService(
        hass, session, _manager(_recording(tmp_path))
    )
    tasks = []
    try:
        for lap in (1, 2):
            tasks.append(await _start_call(service.async_compare(_selection(lap))))
            await asyncio.wait_for(session.started.get(), timeout=1)
        rejected = await _start_call(service.async_compare(_selection(3)))
        tasks.append(rejected)
        with pytest.raises(ValueError, match="busy"):
            await asyncio.wait_for(rejected, timeout=1)
        assert session.requests == 2

        session.release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks[:2]), timeout=5)
        assert [result["series"][0]["lap_number"] for result in results] == [1, 2]
        recovered = await service.async_compare(_selection(3))
        assert recovered["series"][0]["sample_count"] == 2
        assert session.requests == 3
    finally:
        await _finish(service, tasks, session)


@pytest.mark.parametrize("excess_caller", ["catalog", "comparison"])
async def test_catalog_and_duplicate_callers_share_bounded_admission(
    hass, tmp_path, monkeypatch, excess_caller
) -> None:
    scan = _ScanBarrier()
    monkeypatch.setattr(telemetry, "_scan_replay_timing", scan)
    session = _Session()
    service = telemetry.ReplayTelemetryService(
        hass, session, _manager(_recording(tmp_path))
    )
    tasks = []
    try:
        tasks.append(
            await _start_call(service.async_catalog(expected_session_id="session"))
        )
        await asyncio.wait_for(scan.entered.wait(), timeout=1)
        for position in range(7):
            request = (
                service.async_compare(_selection())
                if position % 2 == 0
                else service.async_catalog(expected_session_id="session")
            )
            tasks.append(await _start_call(request))
        assert all(not task.done() for task in tasks)

        request = (
            service.async_catalog(expected_session_id="session")
            if excess_caller == "catalog"
            else service.async_compare(_selection())
        )
        rejected = await _start_call(request)
        tasks.append(rejected)
        with pytest.raises(ValueError, match="busy"):
            await asyncio.wait_for(rejected, timeout=1)
        assert session.requests == 0

        scan.release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks[:8]), timeout=5)
        assert all(result["session_id"] == "session" for result in results)
        assert len(scan.calls) == 1
        assert session.requests == 1
        assert (await service.async_catalog(expected_session_id="session"))["drivers"]
    finally:
        await _finish(service, tasks, session, scan)


@pytest.mark.parametrize("replacement_session_id", ["session", "another-session"])
async def test_replaced_recording_invalidates_timing_catalog_and_comparisons(
    hass, tmp_path, monkeypatch, replacement_session_id
) -> None:
    scan = Mock(wraps=telemetry._scan_replay_timing)
    monkeypatch.setattr(telemetry, "_scan_replay_timing", scan)
    session = _Session()
    manager = _manager(_recording(tmp_path))
    service = telemetry.ReplayTelemetryService(hass, session, manager)
    try:
        original_catalog = await service.async_catalog(expected_session_id="session")
        original_comparison = await service.async_compare(_selection())
        assert original_catalog["drivers"][0]["driver_number"] == 4
        assert original_comparison["series"][0]["driver_number"] == 4

        manager.index = _recording(
            tmp_path,
            name="replacement",
            driver=16,
            session_id=replacement_session_id,
        )
        catalog = await service.async_catalog(
            expected_session_id=replacement_session_id
        )
        with pytest.raises(ValueError, match="unavailable"):
            await service.async_compare(_selection())
        comparison = await service.async_compare(_selection(driver=16))

        assert catalog["session_id"] == replacement_session_id
        assert catalog["drivers"][0]["driver_number"] == 16
        assert comparison["series"][0]["driver_number"] == 16
        assert comparison["series"][0]["sample_count"] == 2
        assert scan.call_count == 2
        assert session.requests == 2
    finally:
        await service.async_close()


@pytest.mark.parametrize("catalog_first", [True, False])
async def test_catalog_and_comparison_share_one_recording_scan(
    hass, tmp_path, monkeypatch, catalog_first
) -> None:
    """The local catalog and selected telemetry use the same timing index."""
    scan = Mock(wraps=telemetry._scan_replay_timing)
    monkeypatch.setattr(telemetry, "_scan_replay_timing", scan)
    session = _Session()
    service = telemetry.ReplayTelemetryService(
        hass, session, _manager(_recording(tmp_path))
    )
    try:
        if catalog_first:
            catalog = await service.async_catalog(expected_session_id="session")
            comparison = await service.async_compare(_selection())
        else:
            comparison = await service.async_compare(_selection())
            catalog = await service.async_catalog(expected_session_id="session")
        assert catalog["drivers"][0]["laps"] == [1, 2, 3]
        assert comparison["series"][0]["sample_count"] == 2
        assert scan.call_count == 1
        assert session.requests == 1
    finally:
        await service.async_close()


@pytest.mark.parametrize("replacement_session_id", ["session", "another-session"])
@pytest.mark.parametrize("original_caller", ["catalog", "comparison"])
async def test_recording_replacement_keeps_running_scan_bounded(
    hass, tmp_path, monkeypatch, replacement_session_id, original_caller
) -> None:
    """A changed recording cannot start a second scan beside the old worker."""
    scan = _ScanBarrier()
    monkeypatch.setattr(telemetry, "_scan_replay_timing", scan)
    session = _Session()
    manager = _manager(_recording(tmp_path))
    original_index = manager.index
    service = telemetry.ReplayTelemetryService(hass, session, manager)
    tasks = []
    try:
        original = (
            service.async_catalog(expected_session_id="session")
            if original_caller == "catalog"
            else service.async_compare(_selection())
        )
        tasks.append(await _start_call(original))
        await asyncio.wait_for(scan.entered.wait(), timeout=1)
        manager.index = _recording(
            tmp_path,
            name="replacement",
            driver=16,
            session_id=replacement_session_id,
        )

        rejected = await _start_call(
            service.async_catalog(expected_session_id=replacement_session_id)
        )
        tasks.append(rejected)
        with pytest.raises(ValueError, match="busy"):
            await asyncio.wait_for(rejected, timeout=1)
        rejected = await _start_call(service.async_compare(_selection(driver=16)))
        tasks.append(rejected)
        with pytest.raises(ValueError, match="busy"):
            await asyncio.wait_for(rejected, timeout=1)
        assert scan.calls == [original_index.frames_file]
        assert session.requests == 0

        scan.release.set()
        with pytest.raises(ValueError, match="changed"):
            await asyncio.wait_for(tasks[0], timeout=5)
        catalog = await service.async_catalog(
            expected_session_id=replacement_session_id
        )
        comparison = await service.async_compare(_selection(driver=16))
        assert catalog["drivers"][0]["driver_number"] == 16
        assert comparison["series"][0]["sample_count"] == 2
        assert scan.calls == [original_index.frames_file, manager.index.frames_file]
        assert session.requests == 1
    finally:
        await _finish(service, tasks, session, scan)


async def test_close_stops_remote_extraction_and_rejects_new_work(
    hass, tmp_path
) -> None:
    session = _Session(blocked=True)
    service = telemetry.ReplayTelemetryService(
        hass, session, _manager(_recording(tmp_path))
    )
    tasks = []
    try:
        tasks.append(await _start_call(service.async_compare(_selection())))
        await asyncio.wait_for(session.started.get(), timeout=1)
        response = session.responses[0]
        assert response.worker is not None
        assert not response.worker.done()

        await asyncio.wait_for(service.async_close(), timeout=1)
        with pytest.raises(ValueError, match="changed"):
            await asyncio.wait_for(tasks[0], timeout=1)
        assert response.exited
        assert response.worker.done()
        assert service.diagnostics()["cache_entries"] == 0

        with pytest.raises(ValueError, match="changed"):
            await service.async_compare(_selection())
        with pytest.raises(ValueError, match="changed"):
            await service.async_catalog(expected_session_id="session")
        assert session.requests == 1
    finally:
        await _finish(service, tasks, session)


@pytest.mark.parametrize("status", [404, 503])
async def test_provider_failure_releases_admission_and_retains_timing_index(
    hass, tmp_path, monkeypatch, status
) -> None:
    scan = Mock(wraps=telemetry._scan_replay_timing)
    monkeypatch.setattr(telemetry, "_scan_replay_timing", scan)
    session = _Session()
    get_response = session.get

    def get(url):
        response = get_response(url)
        if session.requests <= 3:
            response.status = status
        return response

    monkeypatch.setattr(session, "get", get)
    service = telemetry.ReplayTelemetryService(
        hass, session, _manager(_recording(tmp_path))
    )
    try:
        for lap in (1, 2, 3):
            with pytest.raises(ValueError, match="unavailable"):
                await service.async_compare(_selection(lap))
        assert service.diagnostics()["cache_entries"] == 0
        recovered = await service.async_compare(_selection())
        assert recovered["series"][0]["sample_count"] == 2
        assert session.requests == 4
        assert scan.call_count == 1
        assert service.diagnostics()["cache_entries"] == 1
    finally:
        await service.async_close()


async def test_failed_recording_read_can_retry_without_replacing_index(
    hass, tmp_path, monkeypatch
) -> None:
    scan = Mock(wraps=telemetry._scan_replay_timing)
    monkeypatch.setattr(telemetry, "_scan_replay_timing", scan)
    session = _Session()
    index = _recording(tmp_path)
    index.frames_file.unlink()
    service = telemetry.ReplayTelemetryService(hass, session, _manager(index))
    try:
        with pytest.raises(FileNotFoundError):
            await service.async_catalog(expected_session_id="session")
        assert session.requests == 0

        _recording(tmp_path)
        comparison = await service.async_compare(_selection())
        catalog = await service.async_catalog(expected_session_id="session")
        assert comparison["series"][0]["sample_count"] == 2
        assert catalog["drivers"][0]["laps"] == [1, 2, 3]
        assert scan.call_count == 2
        assert session.requests == 1
    finally:
        await service.async_close()
