from __future__ import annotations

import asyncio
import base64
from datetime import UTC, timedelta
import json
from unittest.mock import AsyncMock, patch
import zlib

from homeassistant.util import dt as dt_util
import pytest

from custom_components.f1_sensor.formation_start import FormationStartTracker


def _make_cardata_line(utc_iso: str) -> bytes:
    """Build a single CarData.z.jsonStream line with one entry at the given UTC."""
    data = {"Entries": [{"Utc": utc_iso}]}
    raw = json.dumps(data).encode()
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(raw) + compressor.flush()
    encoded = base64.b64encode(compressed).decode()
    return f'"{encoded}"\n'.encode()


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

    def subscribe(self, stream: str, callback):
        self.subscriptions.append(stream)
        payload = self._cached.get(stream)
        if isinstance(payload, dict):
            callback(dict(payload))
        return lambda: None


class _TimeoutHttp:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, *_args, **_kwargs):
        self.calls += 1
        raise TimeoutError


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
    line = _make_cardata_line(target.isoformat().replace("+00:00", "Z"))
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
    assert tracker.formation_start_utc is not None


@pytest.mark.asyncio
async def test_timeout_with_valid_partial_result_succeeds(hass) -> None:
    # The probe batches 50 lines before flushing. Provide exactly 50 lines so the
    # batch is processed (best_utc found), then TimeoutError fires on line 51.
    # With the fix, a valid partial result is preserved rather than discarded.
    target = dt_util.utcnow().replace(microsecond=0)
    utc_str = target.isoformat().replace("+00:00", "Z")
    lines = [_make_cardata_line(utc_str)] * 50
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
async def test_probe_fires_after_scheduled_start(hass) -> None:
    """Probe delay must be > T-now, confirming the probe fires after T, not before."""
    tracker = FormationStartTracker(
        hass,
        bus=_CachingBus(),
        http_session=object(),  # type: ignore[arg-type]
    )
    probe_calls: list[tuple[float, str | None]] = []

    async def _fake_run_probe(delay: float, session_id: str | None) -> None:
        probe_calls.append((delay, session_id))

    tracker._run_probe = _fake_run_probe

    start_utc = dt_util.utcnow() + timedelta(minutes=5)
    tracker._handle_session_info(_session_info_payload(start_utc=start_utc))
    await hass.async_block_till_done()

    assert len(probe_calls) == 1
    delay = probe_calls[0][0]
    # With _CARDATA_PRE_WINDOW = timedelta(seconds=-10): delay = T-now+10 ≈ 310s.
    # The probe fires 10s AFTER T, not 60s before it (old bug: delay ≈ 240s).
    assert delay > 300, (
        f"Probe delay {delay:.1f}s — expected > 300s (fires after scheduled start)"
    )
