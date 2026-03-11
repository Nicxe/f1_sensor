from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.f1_sensor.replay_mode import (
    INDEX_STATUS_ERROR,
    ReplaySession,
    ReplaySessionManager,
    ReplayState,
)


class _TimeoutHttp:
    def __init__(self) -> None:
        self.get_calls: list[str] = []
        self.head_calls: list[str] = []

    def get(self, url: str):
        self.get_calls.append(url)
        raise TimeoutError

    def head(self, url: str):
        self.head_calls.append(url)
        raise TimeoutError


def _session() -> ReplaySession:
    start = datetime(2026, 3, 20, 5, 0, tzinfo=UTC)
    return ReplaySession(
        year=2026,
        meeting_key=1304,
        meeting_name="Australian Grand Prix",
        session_key=11465,
        session_name="Race",
        session_type="Race",
        path="2026/2026-03-20_Australian_Grand_Prix/2026-03-20_Race/",
        start_utc=start,
        end_utc=start + timedelta(hours=2),
    )


@pytest.mark.asyncio
async def test_fetch_sessions_timeout_sets_index_error(hass) -> None:
    timeout_http = _TimeoutHttp()
    manager = ReplaySessionManager(hass, "entry-test", timeout_http)  # type: ignore[arg-type]

    sessions = await manager.async_fetch_sessions(2026)

    assert sessions == []
    assert timeout_http.get_calls
    assert manager.index_status == INDEX_STATUS_ERROR
    assert manager.index_error == "timeout"
    assert manager.state == ReplayState.IDLE
    assert manager.available_sessions == []


@pytest.mark.asyncio
async def test_download_stream_timeout_returns_empty_list(hass) -> None:
    timeout_http = _TimeoutHttp()
    manager = ReplaySessionManager(hass, "entry-test", timeout_http)  # type: ignore[arg-type]

    frames = await manager._download_stream(
        "https://livetiming.formula1.com/static/test.jsonStream",
        "TimingData",
        "https://livetiming.formula1.com/static",
    )

    assert frames == []
    assert len(timeout_http.get_calls) == 1


@pytest.mark.asyncio
async def test_find_formation_start_timeout_returns_none(hass) -> None:
    timeout_http = _TimeoutHttp()
    manager = ReplaySessionManager(hass, "entry-test", timeout_http)  # type: ignore[arg-type]

    result = await manager._find_formation_start_utc(_session())

    assert result is None
    assert len(timeout_http.get_calls) == 1


@pytest.mark.asyncio
async def test_check_url_exists_timeout_marks_session_unavailable(hass) -> None:
    timeout_http = _TimeoutHttp()
    manager = ReplaySessionManager(hass, "entry-test", timeout_http)  # type: ignore[arg-type]
    session = _session()
    session.available = True

    await manager._check_url_exists(
        "https://livetiming.formula1.com/static/test", session
    )

    assert session.available is False
    assert len(timeout_http.head_calls) == 1
