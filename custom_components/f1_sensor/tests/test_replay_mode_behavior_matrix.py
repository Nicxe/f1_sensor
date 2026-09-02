"""Behavior matrix for replay parsing, merge, and seek helpers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.f1_sensor import replay_mode
from custom_components.f1_sensor.replay_mode import (
    ReplayController,
    ReplayFrame,
    ReplayIndex,
    ReplaySession,
    ReplaySessionManager,
    ReplayState,
    ReplayTransport,
    _parse_optional_utc,
    _parse_replay_int,
    _seek_offset_for_ms,
    _seek_state_checkpoint_for_ms,
)
from custom_components.f1_sensor.track_map import TRACK_MAP_POSITION_STREAM


def _session(**overrides) -> ReplaySession:
    values = {
        "year": 2026,
        "meeting_key": 1,
        "meeting_name": "Test GP",
        "session_key": 2,
        "session_name": "Race",
        "session_type": "Race",
        "path": "2026/test/race/",
        "start_utc": datetime(2026, 9, 1, tzinfo=UTC),
        "end_utc": datetime(2026, 9, 1, 2, tzinfo=UTC),
    }
    values.update(overrides)
    return ReplaySession(**values)


def _manager(hass, tmp_path: Path) -> ReplaySessionManager:
    manager = ReplaySessionManager(
        hass,
        "entry",
        AsyncMock(),
        requested_streams={"TrackStatus"},
        cache_max_bytes=0,
        cache_max_sessions=0,
    )
    manager._cache_dir = tmp_path
    return manager


def test_replay_identifiers_sessions_and_seek_helpers() -> None:
    assert _parse_replay_int(True) is None
    assert _parse_replay_int(-1) is None
    assert _parse_replay_int(" 42 ") == 42
    assert _parse_replay_int("bad") is None
    with pytest.raises(ValueError, match="identifiers"):
        _session(year=0)
    session = _session(year="2026", meeting_key="1", session_key="2")
    assert session.label == "Test GP - Race"
    assert session.unique_id == "2026_1_2"
    assert _parse_optional_utc(None) is None
    assert _parse_optional_utc("bad") is None
    assert _parse_optional_utc("2026-09-01T12:00:00").tzinfo is UTC

    assert _seek_offset_for_ms(None, 10) == 0
    assert (
        _seek_offset_for_ms(
            [
                {"t": "bad", "offset": 1},
                {"t": 0, "offset": -2},
                {"t": 10, "offset": 20},
                {"t": 30, "offset": 40},
            ],
            20,
        )
        == 20
    )
    assert _seek_state_checkpoint_for_ms(None, after_ms=0, target_ms=10) is None
    checkpoint = _seek_state_checkpoint_for_ms(
        [
            {"t": "bad"},
            {"t": 0, "state": {}},
            {"t": 10, "state": "bad"},
            {"t": 20, "state": {"ok": True}},
            {"t": 30, "state": {"later": True}},
        ],
        after_ms=0,
        target_ms=25,
    )
    assert checkpoint == {"t": 20, "state": {"ok": True}}


async def test_manager_properties_initialize_and_listener_snapshot(
    hass, tmp_path
) -> None:
    manager = _manager(hass, tmp_path)
    manager._selected_year = 1900
    assert 1900 in manager.year_options
    assert manager.download_streams
    assert manager.cache_diagnostics["max_sessions"] == 1
    assert manager.selected_session is None
    assert manager.available_sessions == []
    assert manager.index_status is None
    assert manager.index_year is None
    assert manager.index_error is None
    assert manager.download_progress == 0
    assert manager.download_error is None
    await manager.async_initialize()
    assert tmp_path.exists()

    snapshots = []
    remove = manager.add_listener(snapshots.append)
    manager._notify_listeners()
    assert snapshots[-1]["state"] == "idle"
    remove()
    remove()

    manager.add_listener(Mock(side_effect=RuntimeError("listener")))
    manager._notify_listeners()


def test_stream_normalization_position_and_file_merge(
    hass, tmp_path, monkeypatch
) -> None:
    manager = _manager(hass, tmp_path)
    assert manager._normalize_replay_stream_line(b"", "TrackStatus", "url") is None
    assert manager._normalize_replay_stream_line(b"\xff", "TrackStatus", "url") is None
    assert manager._normalize_replay_stream_line(b"plain", "TrackStatus", "url") is None
    normalized = manager._normalize_replay_stream_line(
        b'00:00:01.000{"Status":"2"}', "TrackStatus", "https://host/file"
    )
    assert json.loads(normalized) == {
        "t": 1000,
        "s": "TrackStatus",
        "p": {"Status": "2"},
    }
    radio = manager._normalize_replay_stream_line(
        b'00:00:01.000{"Captures":{}}', "TeamRadio", "https://host/path/file"
    )
    assert json.loads(radio)["p"]["_static_root"] == "https://host/path"

    monkeypatch.setattr(
        replay_mode, "parse_position_z_line", lambda line: {"1": {"X": 1}}
    )
    monkeypatch.setattr(
        replay_mode, "track_map_positions_to_payload", lambda value: {"P": value}
    )
    position = manager._normalize_replay_stream_line(
        b'00:00:02.000"encoded"', TRACK_MAP_POSITION_STREAM, "url"
    )
    assert json.loads(position)["t"] == 2000
    assert manager._split_position_z_line("plain") == ("", "plain")

    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    output = tmp_path / "merged.jsonl"
    first.write_text('{"t":1}\ninvalid\n', encoding="utf-8")
    second.write_text('{"t":0}\n{"t":2}\n', encoding="utf-8")
    assert manager._merge_stream_files_sync([first, second], output) == 3
    assert [json.loads(line)["t"] for line in output.read_text().splitlines()] == [
        0,
        1,
        2,
    ]
    manager._append_lines_file(output, ['{"t":3}'])
    assert output.read_text().splitlines()[-1] == '{"t":3}'
    manager._unlink_if_exists(tmp_path / "missing")
    manager._unlink_if_exists(output)
    assert not output.exists()


def test_replay_merge_helpers_accumulate_realistic_deltas(hass, tmp_path) -> None:
    manager = _manager(hass, tmp_path)
    top = {"lines": [None, None, None], "withheld": False}
    manager._merge_topthree_state(
        top, {"Withheld": True, "Lines": [{"RacingNumber": "1"}, None]}
    )
    manager._merge_topthree_state(
        top,
        {"Lines": {"0": {"BestLapTime": "1:20"}, "bad": {}, "4": {}, "1": "bad"}},
    )
    assert top["withheld"] is True
    assert top["lines"][0]["BestLapTime"] == "1:20"

    timing_app = {}
    manager._merge_timingapp_state(
        timing_app,
        {
            "Withheld": False,
            "Lines": {
                "1": {
                    "GridPos": "1",
                    "Stints": [{"Compound": "SOFT"}, None],
                },
                "bad": "value",
            },
        },
    )
    manager._merge_timingapp_state(
        timing_app, {"Lines": {"1": {"Stints": {"0": {"TotalLaps": 5}}}}}
    )
    assert timing_app["Lines"]["1"]["Stints"]["0"] == {
        "Compound": "SOFT",
        "TotalLaps": 5,
    }
    assert manager._has_timingapp_state(timing_app) is True

    timing_data = {}
    manager._merge_timingdata_state(
        timing_data,
        {"Lines": {"1": {"Sectors": [{"Value": "30"}]}, "bad": "skip"}},
    )
    manager._merge_timingdata_state(
        timing_data, {"Lines": {"1": {"Sectors": {"0": {"Stopped": True}}}}}
    )
    assert timing_data["Lines"]["1"]["Sectors"][0]["Stopped"] is True
    assert manager._deep_merge_replay_state([], {"2": {"x": 1}})[2] == {"x": 1}
    assert manager._deep_merge_replay_state(None, [1]) == [1]
    assert manager._has_timingdata_state(timing_data) is True

    laps = {}
    last_times = {}
    manager._merge_lap_history_state(
        laps,
        last_times,
        {
            "Lines": {
                "1": {
                    "NumberOfLaps": "1",
                    "Position": "2",
                    "LastLapTime": {"Value": "1:20"},
                },
                "bad": "skip",
            }
        },
    )
    manager._merge_lap_history_state(
        laps,
        last_times,
        {"Lines": {"1": {"NumberOfLaps": "2", "LastLapTime": "1:21"}}},
    )
    manager._merge_lap_history_state(
        laps, last_times, {"Lines": {"1": {"NumberOfLaps": "bad"}}}
    )
    assert laps["1"]["laps"] == {"1": "1:20", "2": "1:21"}
    assert manager._has_lap_history_state(laps) is True

    manager._extract_grid_from_driver_race_info(
        laps, {"2": {"Position": 3}, "bad": "skip", "none": {}}
    )
    manager._extract_grid_from_driverlist(
        laps, {"3": {"Line": "4"}, "bad": "skip", "none": {"Line": "bad"}}
    )
    assert laps["2"]["grid_position"] == "3"
    assert laps["3"]["grid_position"] == "4"


def test_checkpoint_merges_repair_malformed_targets_and_dict_payloads(
    hass, tmp_path
) -> None:
    manager = _manager(hass, tmp_path)
    state = {"RaceControlMessages": {"Messages": []}}
    manager._merge_race_control_checkpoint_state(
        state,
        {"Messages": {"7": {"Message": "Yellow"}, "bad": "ignored"}},
    )
    assert state["RaceControlMessages"]["Messages"]["7"]["id"] == 7
    manager._merge_race_control_checkpoint_state(
        state, {"Utc": "now", "Message": "Clear"}
    )
    assert state["RaceControlMessages"]["Messages"]["now"]["Message"] == "Clear"

    state = {"PitStopSeries": {"PitTimes": []}}
    manager._merge_pitstop_checkpoint_state(
        state,
        {
            "PitTimes": {
                "4": {"first": {"PitStop": {"Lap": 1}}, "bad": "ignored"},
                "81": "bad",
            }
        },
    )
    assert state["PitStopSeries"]["PitTimes"]["4"]["first"]["PitStop"]["Lap"] == 1
    manager._merge_pitstop_checkpoint_state(state, {"PitTimes": []})


def test_checkpoint_accumulation_and_datetime_matching(hass, tmp_path) -> None:
    manager = _manager(hass, tmp_path)
    accumulator = manager._new_seek_checkpoint_accumulator()
    frames = [
        ReplayFrame(
            0, "RaceControlMessages", {"Messages": [{"Utc": "2026-09-01T00:00:00Z"}]}
        ),
        ReplayFrame(
            1,
            "PitStopSeries",
            {"PitTimes": {"1": [{"Timestamp": "t", "PitStop": {"Lap": 1}}]}},
        ),
        ReplayFrame(2, "DriverList", {"1": {"Line": 1}}),
        ReplayFrame(3, "DriverRaceInfo", {"2": {"Position": 2}}),
        ReplayFrame(4, "TrackStatus", {"Status": "2"}),
        ReplayFrame(5, "bad", "not-dict"),  # type: ignore[arg-type]
    ]
    for frame in frames:
        manager._accumulate_seek_checkpoint_frame(accumulator, frame)
    state = manager._seek_checkpoint_state(accumulator)
    assert state["RaceControlMessages"]["Messages"]
    assert state["PitStopSeries"]["PitTimes"]["1"]["t"]
    assert state["TrackStatus"] == {"Status": "2"}

    assert manager._checkpoint_message_key({}, 4) == "4"
    assert manager._pitstop_checkpoint_key({"PitStop": {"Lap": 5}}, 1) == "5"
    assert manager._pitstop_checkpoint_key({}, 2) == "2"
    assert manager._is_race_or_sprint_session(_session(session_type="Sprint")) is True
    assert (
        manager._is_race_or_sprint_session(
            _session(session_type="Sprint Qualifying", session_name="Sprint Qualifying")
        )
        is False
    )
    assert manager._parse_utc(None) is None
    assert manager._parse_utc("bad") is None
    assert manager._parse_utc("2026-09-01T00:00:00") == datetime(2026, 9, 1, tzinfo=UTC)
    assert manager._extract_frame_utc(None) is None
    assert manager._extract_frame_utc(
        {"Entries": [{"Utc": "2026-09-01T00:00:00Z"}]}
    ) == (datetime(2026, 9, 1, tzinfo=UTC))
    assert (
        manager._find_closest_frame_ms(
            [ReplayFrame(10, "x", {"Utc": "2026-09-01T00:00:01Z"})],
            datetime(2026, 9, 1, 0, 0, 1, tzinfo=UTC),
        )
        == 10
    )
    assert manager._find_closest_frame_ms([], datetime.now(UTC)) is None
    assert (
        manager._find_closest_frame_ms(
            [ReplayFrame(10, "x", {"Utc": "2020-01-01T00:00:00Z"})],
            datetime(2026, 9, 1, tzinfo=UTC),
        )
        is None
    )


def test_build_seek_checkpoints_and_scan_merged_file(hass, tmp_path) -> None:
    manager = _manager(hass, tmp_path)
    frames = [
        ReplayFrame(
            0, "SessionStatus", {"Status": "Started", "Utc": "2026-09-01T00:00:00Z"}
        ),
        ReplayFrame(
            30_000, "TrackStatus", {"Status": "2", "Utc": "2026-09-01T00:00:30Z"}
        ),
        ReplayFrame(
            60_000, "TrackStatus", {"Status": "1", "Utc": "2026-09-01T00:01:00Z"}
        ),
    ]
    checkpoints = manager._build_seek_state_checkpoints(frames)
    assert [checkpoint["t"] for checkpoint in checkpoints] == [30_000, 60_000]

    frames_file = tmp_path / "frames.jsonl"
    with frames_file.open("w", encoding="utf-8") as handle:
        handle.write("invalid\n")
        for frame in frames:
            handle.write(
                json.dumps(
                    {"t": frame.timestamp_ms, "s": frame.stream, "p": frame.payload}
                )
                + "\n"
            )
    scan = manager._scan_merged_frames_sync(
        frames_file, datetime(2026, 9, 1, 0, 0, 30, tzinfo=UTC)
    )
    assert scan["total_frames"] == 3
    assert scan["duration_ms"] == 60_000
    assert scan["session_started_at_ms"] == 0
    assert scan["formation_started_at_ms"] == 30_000


def test_initial_state_fills_topthree_and_timingapp_after_start(hass, tmp_path) -> None:
    manager = _manager(hass, tmp_path)
    frames = [
        ReplayFrame(0, "PitStopSeries", {"PitTimes": {}}),
        ReplayFrame(1, "DriverRaceInfo", {"4": {"Position": 1}}),
        ReplayFrame(1, "DriverList", {"4": {"Line": 1}}),
        ReplayFrame(2, "SessionStatus", {"Status": "Started"}),
        ReplayFrame(10, "TopThree", {"Lines": {"0": {"Tla": "NOR"}}}),
        ReplayFrame(11, "TopThree", {"Lines": {"1": {"Tla": "PIA"}}}),
        ReplayFrame(12, "TopThree", {"Lines": {"2": {"Tla": "VER"}}}),
        ReplayFrame(
            13,
            "TimingAppData",
            {"Lines": {"4": {"Stints": {"0": {"Compound": "SOFT"}}}}},
        ),
    ]
    state = manager._build_initial_state(frames, 2)
    assert [line["Tla"] for line in state["TopThree"]["Lines"]] == [
        "NOR",
        "PIA",
        "VER",
    ]
    assert state["TimingAppData"]["Lines"]["4"]["Stints"]["0"]["Compound"] == "SOFT"
    assert "PitStopSeries" not in state


async def test_replay_transport_streams_valid_frames_and_tracks_control_state(
    hass, tmp_path, monkeypatch
) -> None:
    frames_file = tmp_path / "frames.jsonl"
    frames_file.write_bytes(
        b"\xff\n"
        b"not-json\n"
        b'{"t":99,"s":"Old","p":{}}\n'
        b'{"t":100,"s":"Boundary","p":{}}\n'
        b'{"t":101,"s":"TrackStatus","p":{"Status":"2"}}\n'
        b'{"t":102,"s":"MissingPayload"}\n'
        b'{"t":103,"s":"SessionStatus","p":{"Status":"Started"}}\n'
    )
    index = ReplayIndex(
        session_id="session",
        total_frames=7,
        duration_ms=103,
        session_started_at_ms=50,
        frames_file=frames_file,
        index_file=tmp_path / "index.json",
    )
    transport = ReplayTransport(
        hass,
        index,
        start_from_ms=100,
        include_start_frame=False,
        speed_multiplier=100,
    )
    monkeypatch.setattr(transport, "_get_elapsed_playback_time", lambda: 1000.0)
    positions = []
    remove = transport.add_listener(
        lambda status: positions.append(status["position_ms"])
    )
    messages = [message async for message in transport.messages()]
    assert [message["M"][0]["A"][0] for message in messages] == [
        "TrackStatus",
        "SessionStatus",
    ]
    assert transport.get_playback_position_ms() == 103
    assert transport.get_session_start_offset_ms() == 50
    assert transport.get_playback_start_offset_ms() == 100
    assert positions[-1] == 103
    remove()
    remove()
    transport.pause()
    assert transport.is_paused() is True
    transport.resume()
    assert transport.is_paused() is False
    assert transport.get_total_duration_ms() == 103
    await transport.ensure_connection()
    await transport.close()
    assert transport._closed is True


class _ReplayResponse:
    def __init__(self, status: int, payload: str = "") -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def text(self) -> str:
        return self._payload


class _ReplayHttp:
    def __init__(self, responses) -> None:
        self.responses = list(responses)

    def get(self, _url):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


async def test_replay_session_discovery_http_states_and_selection(
    hass, tmp_path
) -> None:
    manager = ReplaySessionManager(hass, "entry", _ReplayHttp([_ReplayResponse(404)]))
    manager._cache_dir = tmp_path
    assert await manager.async_fetch_sessions(2025) == []
    assert manager.index_status == replay_mode.INDEX_STATUS_NO_DATA

    manager._http = _ReplayHttp([_ReplayResponse(500)])
    assert await manager.async_fetch_sessions(2024) == []
    assert manager.index_error == "HTTP 500"

    payload = {
        "Meetings": {
            "0": {
                "Key": 1,
                "OfficialName": "Past GP",
                "Sessions": {
                    "0": {
                        "Key": 2,
                        "Name": "Race",
                        "Type": "Race",
                        "Path": "/2026/past/race/",
                        "StartDate": "2026-01-01T12:00:00",
                        "EndDate": "2026-01-01T14:00:00",
                        "GmtOffset": "01:00:00",
                    },
                    "1": {
                        "Key": None,
                        "Path": "/invalid/",
                        "StartDate": "2026-01-01T12:00:00Z",
                    },
                    "2": "ignored",
                },
            },
            "bad": "ignored",
        }
    }
    manager._http = _ReplayHttp([_ReplayResponse(200, json.dumps(payload))])
    sessions = await manager.async_fetch_sessions(2026)
    assert len(sessions) == 1
    assert sessions[0].available is True
    await manager.async_select_session(sessions[0].unique_id)
    assert manager.selected_session is sessions[0]
    with pytest.raises(ValueError, match="not found"):
        await manager.async_select_session("missing")

    manager._http = _ReplayHttp([RuntimeError("network")])
    assert await manager.async_fetch_sessions(2023) == []
    assert manager.index_error == "network"


async def test_replay_manager_selection_load_unload_and_cache_helpers(
    hass, tmp_path, monkeypatch
) -> None:
    manager = _manager(hass, tmp_path)
    fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(manager, "async_fetch_sessions", fetch)
    await manager.async_set_year(manager.selected_year)
    fetch.assert_awaited_once_with(manager.selected_year)
    await manager.async_set_year(2025)
    assert manager.selected_year == 2025
    assert manager.state is replay_mode.ReplayState.IDLE

    with pytest.raises(RuntimeError, match="No session selected"):
        await manager.async_load_session()
    session = _session()
    manager._selected_session = session
    loaded = ReplayIndex(
        session_id=session.unique_id,
        total_frames=1,
        duration_ms=1,
        session_started_at_ms=0,
        frames_file=tmp_path / "frames.jsonl",
        index_file=tmp_path / "index.json",
    )
    monkeypatch.setattr(
        manager, "_download_and_index_session", AsyncMock(return_value=loaded)
    )
    await manager.async_load_session()
    assert manager.state is replay_mode.ReplayState.READY
    assert manager.get_loaded_index() is loaded

    monkeypatch.setattr(
        manager,
        "_download_and_index_session",
        AsyncMock(side_effect=RuntimeError("download failed")),
    )
    await manager.async_load_session()
    assert manager.download_error == "download failed"
    assert manager.state is replay_mode.ReplayState.SELECTED
    monkeypatch.setattr(manager, "_prune_cache", AsyncMock(return_value=0))
    await manager.async_unload()
    assert manager.selected_session is None

    await manager._delete_session_cache("../escape")
    cache_dir = tmp_path / "valid"
    cache_dir.mkdir()
    (cache_dir / "file").write_text("x", encoding="utf-8")
    await manager._delete_session_cache("valid")
    assert not cache_dir.exists()

    frames = tmp_path / "read.jsonl"
    frames.write_bytes(
        b"invalid\n"
        b'{"t":1,"s":"TrackStatus","p":{"Status":"1"}}\n'
        b'{"t":"bad","s":"x","p":{}}\n'
    )
    assert manager._read_frames_file_sync(frames) == [
        ReplayFrame(1, "TrackStatus", {"Status": "1"})
    ]
    lines = [
        "bad",
        json.dumps({"t": replay_mode.SEEK_INDEX_INTERVAL_MS, "s": "x", "p": {}}),
        json.dumps({"t": replay_mode.SEEK_INDEX_INTERVAL_MS * 3, "s": "x", "p": {}}),
    ]
    seek = manager._build_seek_index(lines)
    assert len(seek) == 3
    output = tmp_path / "lines.txt"
    manager._write_lines_file(output, ["a", "b"])
    assert output.read_text(encoding="utf-8") == "a\nb\n"
    assert manager._parse_timestamp_to_ms("bad") == 0
    assert manager._parse_timestamp_to_ms("01:02:03") == 3_723_000
    assert manager._parse_timestamp_to_ms("01:02:bad") == 0
    assert manager._parse_datetime(None, None) is None
    assert manager._parse_datetime("bad", None) is None
    assert manager._parse_datetime("2026-09-01T12:00:00Z", None) == datetime(
        2026, 9, 1, 12, tzinfo=UTC
    )
    assert manager._parse_datetime("2026-09-01T12:00:00", "bad") == datetime(
        2026, 9, 1, 12, tzinfo=UTC
    )


async def test_replay_availability_head_success_and_failure(hass, tmp_path) -> None:
    session_ok = _session(session_key=1)
    session_missing = _session(session_key=2)

    class HeadHttp:
        def head(self, url):
            if "race" in url:
                return _ReplayResponse(200)
            raise RuntimeError("network")

    manager = ReplaySessionManager(hass, "entry", HeadHttp())
    manager._cache_dir = tmp_path
    await manager._check_url_exists("race", session_ok)
    await manager._check_url_exists("other", session_missing)
    assert session_ok.available is True
    assert session_missing.available is False


class _LineContent:
    def __init__(self, lines) -> None:
        self.lines = iter(lines)

    async def readline(self):
        return next(self.lines, b"")


class _StreamResponse(_ReplayResponse):
    def __init__(self, status: int, lines=None, payload: str = "") -> None:
        super().__init__(status, payload)
        self.content = _LineContent(lines or [])


async def test_replay_stream_download_streaming_http_and_cleanup_paths(
    hass, tmp_path
) -> None:
    destination = tmp_path / "stream.jsonl"
    manager = _manager(hass, tmp_path)
    manager._http = _ReplayHttp([_StreamResponse(404)])
    assert (
        await manager._download_stream_to_file("url", "TrackStatus", destination) == 0
    )
    manager._http = _ReplayHttp([_StreamResponse(500)])
    assert (
        await manager._download_stream_to_file("url", "TrackStatus", destination) == 0
    )

    manager._http = _ReplayHttp(
        [
            _StreamResponse(
                200,
                [
                    b"\n",
                    b"plain\n",
                    b'00:00:01.000{"Status":"2"}\n',
                    b'00:00:02.000{"Status":"1"}\n',
                ],
            )
        ]
    )
    assert (
        await manager._download_stream_to_file("url", "TrackStatus", destination) == 2
    )
    assert destination.exists()
    assert len(destination.read_text(encoding="utf-8").splitlines()) == 2

    manager._http = _ReplayHttp([RuntimeError("network")])
    assert (
        await manager._download_stream_to_file("url", "TrackStatus", destination) == 0
    )


async def test_replay_stream_download_small_mock_text_fallback(hass, tmp_path) -> None:
    destination = tmp_path / "text.jsonl"
    manager = _manager(hass, tmp_path)
    manager._http = _ReplayHttp(
        [
            _ReplayResponse(
                200,
                '00:00:01.000{"Status":"2"}\ninvalid\n00:00:02.000{"Status":"1"}',
            )
        ]
    )
    assert (
        await manager._download_stream_to_file("url", "TrackStatus", destination) == 2
    )


async def test_cached_replay_index_is_reused_without_downloading(
    hass, tmp_path, monkeypatch
) -> None:
    manager = _manager(hass, tmp_path)
    session = _session()
    cache = tmp_path / session.unique_id
    cache.mkdir()
    frames = cache / "frames.jsonl"
    frames.write_text("", encoding="utf-8")
    index = cache / "index.json"
    index.write_text(
        json.dumps(
            {
                "cache_version": replay_mode.CACHE_VERSION,
                "total_frames": 3,
                "duration_ms": 20,
                "session_started_at_ms": 1,
                "formation_started_at_ms": 2,
                "formation_start_utc": "2026-09-01T00:00:00Z",
                "initial_state": {"TrackStatus": {"Status": "1"}},
                "formation_initial_state": {},
                "seek_index": [{"t": 0, "offset": 0}],
                "seek_checkpoints": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(manager, "_prune_cache", AsyncMock(return_value=0))
    loaded = await manager._download_and_index_session(session)
    assert loaded.total_frames == 3
    assert loaded.formation_start_utc == datetime(2026, 9, 1, tzinfo=UTC)
    manager._prune_cache.assert_awaited_once_with(session.unique_id)


def test_build_initial_state_merges_checkpoint_streams_and_first_payloads(
    hass, tmp_path
) -> None:
    manager = _manager(hass, tmp_path)
    frames = [
        ReplayFrame(0, "TopThree", {"Lines": [{"RacingNumber": "1"}]}),
        ReplayFrame(1, "TimingAppData", {"Lines": {"1": {"GridPos": "1"}}}),
        ReplayFrame(
            2,
            "TimingData",
            {
                "Lines": {
                    "1": {
                        "NumberOfLaps": 1,
                        "Position": "1",
                        "LastLapTime": {"Value": "1:20.000"},
                    }
                }
            },
        ),
        ReplayFrame(3, "DriverRaceInfo", {"1": {"Position": "1"}}),
        ReplayFrame(4, "DriverList", {"1": {"Line": 1}}),
        ReplayFrame(5, "PitStopSeries", {"PitTimes": {}}),
        ReplayFrame(100, "TrackStatus", {"Status": "2"}),
    ]
    state = manager._build_initial_state(frames, 5)
    assert state["TopThree"]["Lines"][0]["RacingNumber"] == "1"
    assert state["TimingAppData"]["Lines"]["1"]["GridPos"] == "1"
    assert state["TimingData"]["Lines"]["1"]["NumberOfLaps"] == 1
    assert state["LapHistory"]["1"]["grid_position"] == "1"
    assert state["TrackStatus"] == {"Status": "2"}
    assert "PitStopSeries" not in state


async def test_formation_marker_http_status_empty_success_and_outside_window(
    hass, tmp_path, monkeypatch
) -> None:
    manager = _manager(hass, tmp_path)
    session = _session()
    manager._http = _ReplayHttp([_StreamResponse(404)])
    assert await manager._find_formation_start_utc(session) is None
    manager._http = _ReplayHttp([_StreamResponse(500)])
    assert await manager._find_formation_start_utc(session) is None
    manager._http = _ReplayHttp([RuntimeError("network")])
    assert await manager._find_formation_start_utc(session) is None

    target = session.start_utc
    manager._http = _ReplayHttp([_StreamResponse(200, [b'"encoded"\n'])])
    monkeypatch.setattr(
        replay_mode,
        "parse_cardata_lines",
        lambda _lines, _parser: [target],
    )
    assert await manager._find_formation_start_utc(session) == target

    manager._http = _ReplayHttp([_StreamResponse(200, [b'"encoded"\n'])])
    monkeypatch.setattr(
        replay_mode,
        "parse_cardata_lines",
        lambda _lines, _parser: [target.replace(year=2020)],
    )
    assert await manager._find_formation_start_utc(session) is None


def test_replay_cache_pruning_missing_invalid_and_over_budget_entries(
    hass, tmp_path
) -> None:
    manager = _manager(hass, tmp_path)
    manager._cache_max_sessions = 1
    manager._cache_max_bytes = 1
    missing_index = tmp_path / "missing-index"
    missing_index.mkdir()
    old = tmp_path / "old"
    old.mkdir()
    (old / "index.json").write_text("{}", encoding="utf-8")
    (old / "data").write_text("large", encoding="utf-8")
    newer = tmp_path / "newer"
    newer.mkdir()
    (newer / "index.json").write_text("{}", encoding="utf-8")
    (newer / "data").write_text("large", encoding="utf-8")
    cleaned, diagnostics = manager._prune_cache_sync("newer")
    assert cleaned >= 2
    assert diagnostics["max_sessions"] == 1
    assert newer.exists()


async def test_replay_background_unload_delete_and_compatibility_wrappers(
    hass, tmp_path, monkeypatch
) -> None:
    manager = _manager(hass, tmp_path)
    monkeypatch.setattr(replay_mode.asyncio, "sleep", AsyncMock())
    manager.async_fetch_sessions = AsyncMock(return_value=[])
    await manager._fetch_sessions_background()
    manager.async_fetch_sessions.assert_awaited_once_with()
    manager.async_fetch_sessions = AsyncMock(side_effect=RuntimeError("index"))
    await manager._fetch_sessions_background()

    pending = asyncio.create_task(asyncio.Event().wait())
    manager._fetch_task = pending
    manager._prune_cache = AsyncMock(return_value=0)
    await manager.async_unload()
    assert pending.cancelled()

    valid = tmp_path / "valid"
    valid.mkdir()
    monkeypatch.setattr(
        hass,
        "async_add_executor_job",
        AsyncMock(side_effect=RuntimeError("filesystem")),
    )
    await manager._delete_session_cache("valid")

    manager._prune_cache = AsyncMock(return_value=2)
    await manager._cleanup_old_cache()
    manager._prune_cache.assert_awaited_once_with()
    monkeypatch.setattr(manager, "_prune_cache_sync", lambda _active: (3, {}))
    assert manager._cleanup_old_cache_sync() == 3
    assert manager._safe_session_cache_dir("../escape") is None


async def test_legacy_stream_download_and_normalization_error_matrix(
    hass, tmp_path, monkeypatch
) -> None:
    manager = _manager(hass, tmp_path)
    manager._http = _ReplayHttp([_ReplayResponse(404)])
    assert await manager._download_stream("url", "TrackStatus") == []
    manager._http = _ReplayHttp([_ReplayResponse(503)])
    assert await manager._download_stream("url", "TrackStatus") == []
    manager._http = _ReplayHttp([RuntimeError("network")])
    assert await manager._download_stream("url", "TrackStatus") == []

    manager._http = _ReplayHttp(
        [
            _ReplayResponse(
                200,
                '\nplain\n00:00:bad{bad}\n00:00:01.000{"Captures": {}}',
            )
        ]
    )
    radio = await manager._download_stream("https://host/path/file", "TeamRadio")
    assert radio[0].payload["_static_root"] == "https://host/path"

    monkeypatch.setattr(replay_mode, "parse_position_z_line", lambda _line: {})
    manager._http = _ReplayHttp(
        [_ReplayResponse(200, '\ninvalid\n00:00:01.000"encoded"')]
    )
    assert await manager._download_stream("url", TRACK_MAP_POSITION_STREAM) == []
    assert (
        manager._normalize_replay_stream_line(
            b"x" * (16 * 1024 * 1024 + 1), "TrackStatus", "url"
        )
        is None
    )
    assert (
        manager._normalize_replay_stream_line(
            b'00:00:01.000{"bad": NaN}', "TrackStatus", "url"
        )
        is not None
    )
    monkeypatch.setattr(
        replay_mode,
        "parse_position_z_line",
        Mock(side_effect=ValueError("position")),
    )
    assert (
        manager._parse_position_z_stream_text(
            '\n00:00:01.000"bad"', TRACK_MAP_POSITION_STREAM
        )
        == []
    )


def test_replay_merge_checkpoint_and_grid_defensive_matrix(hass, tmp_path) -> None:
    manager = _manager(hass, tmp_path)
    top = {"lines": [None, None, None], "withheld": False}
    manager._merge_topthree_state(top, "bad")
    timing_app = {}
    manager._merge_timingapp_state(timing_app, "bad")
    manager._merge_timingapp_state(timing_app, {"Lines": "bad"})
    manager._merge_timingapp_state(
        timing_app,
        {"Lines": {"4": {"Stints": {"bad": "skip", "0": {"Laps": 2}}}}},
    )
    timing_data = {"Lines": {"4": {"Sectors": {}}}}
    manager._merge_timingdata_state(timing_data, "bad")
    manager._merge_timingdata_state(
        timing_data, {"Lines": {"4": {"Sectors": {"0": {"Value": "20"}}}}}
    )
    target = []
    manager._merge_replay_list_state(target, {"bad": {}, "-1": {}, "2": {"x": 1}})
    assert target[2] == {"x": 1}

    state = {}
    manager._extract_grid_from_driver_race_info(state, "bad")
    manager._extract_grid_from_driver_race_info(
        state, {"4": {"Position": ""}, "81": {"Position": "2"}}
    )
    manager._extract_grid_from_driverlist(state, "bad")
    manager._extract_grid_from_driverlist(state, {"4": {}, "81": {"Line": "2"}})
    assert state["81"]["grid_position"] == "2"

    accumulator = manager._new_seek_checkpoint_accumulator()
    manager._accumulate_seek_checkpoint_frame(
        accumulator, ReplayFrame(1, "TopThree", {"Lines": [{"Tla": "NOR"}]})
    )
    manager._accumulate_seek_checkpoint_frame(
        accumulator,
        ReplayFrame(2, "TimingAppData", {"Lines": {"4": {"GridPos": "1"}}}),
    )
    manager._accumulate_seek_checkpoint_frame(
        accumulator, ReplayFrame(3, "TrackStatus", {"Status": "2"})
    )
    checkpoint = manager._seek_checkpoint_state(accumulator)
    assert checkpoint["TopThree"]["Lines"][0]["Tla"] == "NOR"
    assert checkpoint["TimingAppData"]["Lines"]["4"]["GridPos"] == "1"


class _BadReplayText:
    def __str__(self):
        raise ValueError("text")


async def test_replay_exact_manager_and_checkpoint_fallbacks(
    hass, tmp_path, monkeypatch
) -> None:
    manager = _manager(hass, tmp_path)
    manager._http = _ReplayHttp([_ReplayResponse(404)])
    assert await manager.async_fetch_sessions() == []
    monkeypatch.setattr(manager, "_safe_session_cache_dir", Mock(return_value=None))
    with pytest.raises(RuntimeError, match="Invalid replay session"):
        await manager._download_and_index_session(_session())

    laps = {
        "4": {
            "laps": {},
            "last_recorded_lap": 2,
            "grid_position": None,
            "completed_laps": "bad",
        }
    }
    manager._merge_lap_history_state(
        laps,
        {},
        {"Lines": {"4": {"Position": "3", "LastLapTime": "1:20"}}},
    )
    assert laps["4"]["laps"]["3"] == "1:20"
    assert laps["4"]["grid_position"] is None
    manager._merge_lap_history_state(
        laps,
        {},
        {"Lines": {"6": {"Position": "4", "NumberOfLaps": 0}}},
    )
    assert laps["6"]["grid_position"] == "4"
    manager._extract_grid_from_driver_race_info(
        laps, {"5": {"Position": _BadReplayText()}}
    )

    state = {"PitStopSeries": {"PitTimes": {"4": "bad"}}}
    manager._merge_pitstop_checkpoint_state(
        state,
        {"PitTimes": {"4": ["bad", {"Timestamp": "t", "PitStop": {}}]}},
    )
    assert state["PitStopSeries"]["PitTimes"]["4"]["t"]

    accumulator = manager._new_seek_checkpoint_accumulator()
    accumulator["state"]["DriverList"] = "bad"
    manager._accumulate_seek_checkpoint_frame(
        accumulator,
        ReplayFrame(1, "DriverList", {"4": {"Line": 1}}),
    )
    manager._accumulate_seek_checkpoint_frame(
        accumulator,
        ReplayFrame(2, "TimingData", {"Lines": {"4": {"Position": "1"}}}),
    )
    checkpoint = manager._seek_checkpoint_state(accumulator)
    assert checkpoint["DriverList"]["4"]["Line"] == 1
    assert checkpoint["TimingData"]["Lines"]["4"]["Position"] == "1"


async def test_replay_controller_exact_guards_and_pending_start(hass, tmp_path) -> None:
    bus = SimpleNamespace(
        _transport_factory=None,
        _running=False,
        inject_message=Mock(),
        swap_transport=AsyncMock(),
        async_close=AsyncMock(),
    )
    controller = ReplayController(hass, "entry", AsyncMock(), bus)
    assert (
        controller._get_start_reference() == replay_mode.DEFAULT_REPLAY_START_REFERENCE
    )
    with pytest.raises(RuntimeError, match="No replay index"):
        await controller.async_seek_by(1)
    with pytest.raises(RuntimeError, match="No replay index"):
        await controller.async_seek_to_position(1)
    with pytest.raises(RuntimeError, match="loaded before seeking"):
        await controller.async_seek_to_ms(1)

    index = ReplayIndex(
        session_id="session",
        total_frames=0,
        duration_ms=100,
        session_started_at_ms=0,
        frames_file=tmp_path / "frames.jsonl",
        index_file=tmp_path / "index.json",
        initial_state={},
    )
    controller.session_manager._loaded_index = index
    controller.session_manager._state = ReplayState.PLAYING
    controller._transport = SimpleNamespace(
        _closed=False,
        get_playback_position_ms=lambda: 10,
    )
    controller._replay_active = True
    assert controller._replay_transport_factory() is controller._transport
    await controller.async_seek_to_ms(10)

    controller.session_manager._state = ReplayState.READY
    controller._transport = None
    controller._pending_start_ms = 50
    controller._run_replay_reset_callbacks = AsyncMock()
    controller._prepare_track_map_replay_index = AsyncMock()
    controller._replay_frames_range = AsyncMock()
    controller._start_transport = AsyncMock()
    controller._inject_initial_state = Mock()
    controller._inject_formation_ready_if_applicable = Mock()
    await controller.async_play()
    controller._replay_frames_range.assert_awaited_once()
    assert controller.session_manager.state is ReplayState.PLAYING

    class BrokenTransport:
        @property
        def _closed(self):
            raise RuntimeError("closed")

    controller._transport = BrokenTransport()
    controller.session_manager._state = ReplayState.IDLE
    await controller._run_playback()


def test_replay_read_range_skips_unicode_and_empty_lines(tmp_path) -> None:
    path = tmp_path / "range.jsonl"
    path.write_bytes(
        b'\xff\n\n{"t":1,"s":"TrackStatus","p":{}}\n{"t":3,"s":"TrackStatus","p":{}}\n'
    )
    frames = ReplayController._read_frames_range_sync(
        path,
        start_exclusive_ms=0,
        end_inclusive_ms=2,
    )
    assert [frame.timestamp_ms for frame in frames] == [1]


async def test_replay_transport_disk_messages_pause_and_elapsed_time(
    hass, tmp_path, monkeypatch
) -> None:
    frames = tmp_path / "transport.jsonl"
    frames.write_bytes(
        b"\xff\n"
        b"bad\n"
        b'{"t":0,"s":"TrackStatus","p":{"Status":"1"}}\n'
        b'{"t":20,"s":"TrackStatus","p":{"Status":"2"}}\n'
    )
    index = ReplayIndex(
        session_id="2026_1_2",
        total_frames=2,
        duration_ms=20,
        session_started_at_ms=0,
        frames_file=frames,
        index_file=tmp_path / "index.json",
        seek_index=[{"t": 0, "offset": 0}],
    )
    transport = ReplayTransport(
        hass,
        index,
        start_from_session_start=False,
        speed_multiplier=10,
    )
    assert transport._resolve_start_ms() == 0
    assert transport._get_elapsed_playback_time() == 0.0
    now = time.monotonic()
    transport._playback_started_at = now - 10
    transport._paused = True
    transport._pause_started_at = now - 2
    transport._total_paused_duration = 1
    assert 6.5 < transport._get_elapsed_playback_time() < 7.5
    transport._paused = False
    transport._pause_event.set()
    messages = [message async for message in transport.messages()]
    assert len(messages) == 2
    assert transport.get_playback_position_ms() == 20
    assert transport._closed is True
