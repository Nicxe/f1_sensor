"""Behavior coverage for the legacy local replay file client."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from custom_components.f1_sensor import replay
from custom_components.f1_sensor.replay import ReplaySignalRClient
from custom_components.f1_sensor.track_map import TRACK_MAP_POSITION_STREAM


async def test_replay_client_loads_supported_json_shapes(hass, tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text(
        "\ufeffURL: https://livetiming.formula1.com/static/2026/race/TeamRadio.jsonStream\n"
        '00:00:01.000{"payload":{"Captures":{"1":{}}}}\n'
        '00:00:02{"stream":"TrackStatus","payload":{"Status":"2"}}\n'
        '00:00:03{"payload":{"_stream":"SessionStatus","Status":"Started"}}\n'
        '00:00:04{"_stream":"WeatherData","AirTemp":"20"}\n'
        '00:00:05{"AirTemp":"21"}\n'
        "not-json\n"
        "00:00:06{broken\n",
        encoding="utf-8",
    )
    client = ReplaySignalRClient(
        hass,
        source,
        loop_forever=False,
        speed_multiplier=1_000_000,
    )

    await client.ensure_connection()
    await client.ensure_connection()
    messages = [message async for message in client.messages()]

    assert [message["M"][0]["A"][0] for message in messages] == [
        "TeamRadio",
        "TrackStatus",
        "SessionStatus",
        "WeatherData",
        "TeamRadio",
    ]
    first_payload = messages[0]["M"][0]["A"][1]
    assert first_payload["_static_root"].endswith("/static/2026/race")
    assert messages[1]["M"][0]["A"][1] == {"Status": "2"}
    assert client._frames[0].delay == 1.0
    assert client._frames[1].delay == 1.0


async def test_replay_client_position_stream_and_close(
    hass, tmp_path, monkeypatch
) -> None:
    source = tmp_path / "Position.z.txt"
    source.write_text(
        "URL: https://livetiming.formula1.com/static/2026/race/Position.z.jsonStream\n"
        '00:00:01.500"encoded"\n'
        '00:00:02.000"empty"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        replay,
        "parse_position_z_line",
        lambda value: {"44": {"X": 1}} if value == '"encoded"' else {},
    )
    monkeypatch.setattr(
        replay,
        "track_map_positions_to_payload",
        lambda positions: {"Positions": positions},
    )
    client = ReplaySignalRClient(
        hass,
        source,
        loop_forever=True,
        speed_multiplier=1_000_000,
    )

    iterator = client.messages()
    message = await anext(iterator)
    assert message["M"][0]["A"] == [
        TRACK_MAP_POSITION_STREAM,
        {"Positions": {"44": {"X": 1}}},
    ]
    await client.close()
    with pytest.raises(StopAsyncIteration):
        await anext(iterator)


async def test_replay_client_reports_missing_empty_and_invalid_sources(
    hass, tmp_path
) -> None:
    missing = ReplaySignalRClient(hass, tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError, match="Replay dump not found"):
        await missing.ensure_connection()

    empty_path = tmp_path / "empty.json"
    empty_path.write_text("\nURL:\n{}\n", encoding="utf-8")
    empty = ReplaySignalRClient(hass, empty_path)
    with pytest.raises(RuntimeError, match="did not contain any valid frames"):
        await empty.ensure_connection()

    directory = ReplaySignalRClient(hass, tmp_path)
    with pytest.raises(RuntimeError, match="Failed to parse replay dump"):
        await directory.ensure_connection()


def test_replay_client_parsing_helpers_cover_edge_cases(tmp_path: Path) -> None:
    assert ReplaySignalRClient._parse_timestamp("01:02:03.500") == 3723.5
    assert ReplaySignalRClient._parse_timestamp("01:02:03") == 3723.0
    assert ReplaySignalRClient._parse_timestamp("invalid") is None
    assert ReplaySignalRClient._split_line("prefix") == ("prefix", "")
    assert ReplaySignalRClient._split_line('1 {"x":1}') == ("1", '{"x":1}')
    assert ReplaySignalRClient._split_position_z_line("payload") == ("", "payload")
    assert ReplaySignalRClient._split_position_z_line('1 "payload"') == (
        "1",
        '"payload"',
    )
    assert ReplaySignalRClient._parse_json("{") is None
    assert (
        ReplaySignalRClient._guess_stream_from_name(
            tmp_path / "recording_TrackStatus.txt"
        )
        == "TrackStatus"
    )
    assert ReplaySignalRClient._guess_stream_from_name(tmp_path / "unknown.txt") is None
    assert ReplaySignalRClient._extract_stream_from_url("invalid") is None
    assert ReplaySignalRClient._extract_stream_from_url("URL:") is None
    assert (
        ReplaySignalRClient._extract_stream_from_url(
            "URL: https://host/TrackStatus.jsonStream/"
        )
        == "TrackStatus"
    )
    assert (
        ReplaySignalRClient._extract_stream_from_url("URL: https://host/Unknown")
        is None
    )
    assert ReplaySignalRClient._extract_static_root_from_url("invalid") is None
    assert ReplaySignalRClient._extract_static_root_from_url("URL:") is None
    assert ReplaySignalRClient._extract_static_root_from_url("URL: one") is None
    assert ReplaySignalRClient._extract_static_root_from_url(
        "URL: https://host/file"
    ) == ("https://host")
    assert ReplaySignalRClient._extract_stream([]) == (None, None)
    assert ReplaySignalRClient._extract_stream({"payload": {"value": 1}}) == (
        None,
        {"value": 1},
    )
    assert ReplaySignalRClient._extract_stream({"value": 1}) == (
        None,
        {"value": 1},
    )

    client = ReplaySignalRClient(None, tmp_path / "x", speed_multiplier=0)  # type: ignore[arg-type]
    assert client._speed == 1.0
    assert client._compute_delay(None, 2.0) == 0.0
    assert client._compute_delay(1.0, None) == 1.0
    assert client._compute_delay(1.0, 2.0) == 0.0


async def test_replay_messages_returns_when_preloaded_frames_are_empty(
    hass, tmp_path
) -> None:
    client = ReplaySignalRClient(hass, tmp_path / "unused")
    client._loaded = True
    assert [message async for message in client.messages()] == []

    client._frames = [replay.ReplayFrame(10, "TrackStatus", {"Status": "1"})]
    task = asyncio.create_task(anext(client.messages()))
    await asyncio.sleep(0)
    await client.close()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
