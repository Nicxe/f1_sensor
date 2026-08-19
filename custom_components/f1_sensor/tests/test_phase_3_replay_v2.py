"""Acceptance tests for the Phase 3 Replay v2 pipeline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from unittest.mock import AsyncMock

from homeassistant.util import dt as dt_util
import pytest

from custom_components.f1_sensor.history import LAP_ANALYSIS_STREAMS
from custom_components.f1_sensor.replay_mode import (
    REPLAY_EARLIEST_YEAR,
    ReplaySession,
    ReplaySessionManager,
)


class _NoNetworkHttp:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, _url: str):
        self.calls += 1
        raise AssertionError("Replay discovery must stay lazy during initialization")


class _StreamingContent:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = iter(lines)
        self.readline_calls = 0

    async def readline(self) -> bytes:
        self.readline_calls += 1
        return next(self._lines, b"")


class _StreamingResponse:
    def __init__(self, lines: list[bytes]) -> None:
        self.status = 200
        self.content = _StreamingContent(lines)
        self.text_called = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    async def text(self) -> str:
        self.text_called = True
        raise AssertionError("Replay v2 must not buffer the whole response body")


class _StreamingHttp:
    def __init__(self, response: _StreamingResponse) -> None:
        self.response = response

    def get(self, _url: str) -> _StreamingResponse:
        return self.response


def _session() -> ReplaySession:
    start = datetime(2026, 3, 20, 5, 0, tzinfo=UTC)
    return ReplaySession(
        year=2026,
        meeting_key=1304,
        meeting_name="Australian Grand Prix",
        session_key=11465,
        session_name="Race",
        session_type="Race",
        path="2026/australia/race",
        start_utc=start,
        end_utc=start + timedelta(hours=2),
    )


@pytest.mark.asyncio
async def test_replay_initialization_is_lazy_and_supports_full_archive(
    hass, tmp_path
) -> None:
    http = _NoNetworkHttp()
    manager = ReplaySessionManager(hass, "entry-test", http)  # type: ignore[arg-type]
    manager._cache_dir = tmp_path

    await manager.async_initialize()

    assert http.calls == 0
    assert manager.available_sessions == []
    assert manager.year_options[0] == dt_util.utcnow().year
    assert manager.year_options[-1] == REPLAY_EARLIEST_YEAR


def test_replay_download_plan_only_contains_requested_feature_streams(hass) -> None:
    manager = ReplaySessionManager(
        hass,
        "entry-test",
        _NoNetworkHttp(),  # type: ignore[arg-type]
        requested_streams={"TimingData", "RaceControlMessages"},
    )

    assert {"SessionInfo", "SessionStatus", "TimingData", "RaceControlMessages"} <= set(
        manager.download_streams
    )
    assert "TeamRadio" not in manager.download_streams
    assert "ChampionshipPrediction" not in manager.download_streams


def test_replay_lap_analysis_streams_are_provider_neutral() -> None:
    assert LAP_ANALYSIS_STREAMS == {
        "RaceControlMessages",
        "SessionInfo",
        "TimingData",
        "TrackStatus",
    }


@pytest.mark.asyncio
async def test_replay_stream_download_parses_incrementally(hass, tmp_path) -> None:
    response = _StreamingResponse(
        [
            b'00:00:01.000{"Status":"Started"}\n',
            b'00:00:02.000{"Status":"Finished"}\n',
        ]
    )
    manager = ReplaySessionManager(
        hass,
        "entry-test",
        _StreamingHttp(response),  # type: ignore[arg-type]
        requested_streams={"SessionStatus"},
    )
    destination = tmp_path / "SessionStatus.jsonl"

    count = await manager._download_stream_to_file(
        "https://livetiming.formula1.com/static/test/SessionStatus.jsonStream",
        "SessionStatus",
        destination,
    )

    assert count == 2
    assert response.content.readline_calls == 3
    assert response.text_called is False
    assert destination.read_text(encoding="utf-8").splitlines() == [
        '{"t":1000,"s":"SessionStatus","p":{"Status":"Started"}}',
        '{"t":2000,"s":"SessionStatus","p":{"Status":"Finished"}}',
    ]


@pytest.mark.asyncio
async def test_replay_cache_is_bounded_lru_and_preserved_on_unload(
    hass, tmp_path
) -> None:
    manager = ReplaySessionManager(
        hass,
        "entry-test",
        _NoNetworkHttp(),  # type: ignore[arg-type]
        cache_max_bytes=900,
        cache_max_sessions=2,
    )
    manager._cache_dir = tmp_path
    now = datetime.now(UTC).timestamp()
    for index, name in enumerate(("old", "middle", "new")):
        session_dir = tmp_path / name
        session_dir.mkdir()
        index_file = session_dir / "index.json"
        index_file.write_text("{}", encoding="utf-8")
        (session_dir / "frames.jsonl").write_bytes(b"x" * 350)
        timestamp = now - (30 - index * 10)
        os.utime(index_file, (timestamp, timestamp))

    removed = await manager._prune_cache()

    assert removed >= 1
    assert not (tmp_path / "old").exists()
    assert (tmp_path / "new").exists()
    before = sorted(path.name for path in tmp_path.iterdir())
    manager._loaded_index = None
    await manager.async_unload()
    assert sorted(path.name for path in tmp_path.iterdir()) == before
    diagnostics = manager.cache_diagnostics
    assert diagnostics["max_bytes"] == 900
    assert diagnostics["max_sessions"] == 2
    assert diagnostics["sessions"] <= 2
    assert diagnostics["bytes"] <= 900


def test_replay_cache_does_not_prune_active_session(hass, tmp_path) -> None:
    manager = ReplaySessionManager(
        hass,
        "entry-test",
        _NoNetworkHttp(),  # type: ignore[arg-type]
        cache_max_bytes=1,
        cache_max_sessions=1,
    )
    manager._cache_dir = tmp_path
    active = tmp_path / _session().unique_id
    active.mkdir()
    (active / "index.json").write_text("{}", encoding="utf-8")
    (active / "frames.jsonl").write_bytes(b"active-data")

    removed, diagnostics = manager._prune_cache_sync(_session().unique_id)

    assert removed == 0
    assert active.exists()
    assert diagnostics["over_budget"] is True


@pytest.mark.asyncio
async def test_replay_failed_download_removes_partial_stream_files(
    hass, tmp_path, monkeypatch
) -> None:
    manager = ReplaySessionManager(
        hass,
        "entry-test",
        _NoNetworkHttp(),  # type: ignore[arg-type]
        requested_streams={"TimingData"},
    )
    manager._cache_dir = tmp_path
    monkeypatch.setattr(manager, "_download_stream_to_file", AsyncMock(return_value=0))

    with pytest.raises(RuntimeError, match="No frames downloaded"):
        await manager._download_and_index_session(_session())

    assert not (tmp_path / _session().unique_id / "streams").exists()
    assert await manager._prune_cache() == 1
    assert not (tmp_path / _session().unique_id).exists()
