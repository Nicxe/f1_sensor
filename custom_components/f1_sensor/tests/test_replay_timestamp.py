"""Archive duration parsing must distinguish bad input from the zero point."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.f1_sensor import replay, replay_mode
from custom_components.f1_sensor.replay import ReplaySignalRClient
from custom_components.f1_sensor.replay_mode import ReplaySessionManager


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        ("00:00:00", 0),
        ("00:00:00.1", 100),
        ("00:00:00.10", 100),
        ("00:00:00.100", 100),
        ("00:00:00.123456", 123),
        ("00:00:00.000999", 0),
        ("25:02:03.004", 90_123_004),
        ("123:00:00", 442_800_000),
        ("bad", None),
        ("", None),
        ("-01:00:00", None),
        ("00:60:00", None),
        ("00:00:60", None),
        ("00::00", None),
        ("00:00:00.", None),
        ("00:00:00.1234567", None),
        ("00:00:00.1.2", None),
        ("garbage00:00:00", None),
        ("00:00:00garbage", None),
        ("００:００:００", None),
    ],
)
def test_replay_duration_contract_is_shared(timestamp, expected) -> None:
    assert ReplaySessionManager._parse_timestamp_to_ms(timestamp) == expected
    assert ReplaySignalRClient._parse_timestamp(timestamp) == (
        expected / 1000 if expected is not None else None
    )


@pytest.mark.parametrize("stream", ["TrackStatus", "Position.z"])
def test_replay_normalizer_rejects_invalid_time_and_keeps_zero(
    hass, stream, monkeypatch
) -> None:
    manager = ReplaySessionManager(hass, "entry", AsyncMock())
    monkeypatch.setattr(replay_mode, "parse_position_z_line", lambda _: {"1": {}})
    monkeypatch.setattr(replay_mode, "track_map_positions_to_payload", lambda p: p)
    payload = '"encoded"' if stream == "Position.z" else '{"Status":"1"}'
    for prefix in ("bad", "00:60:00", "", "junk00:00:01"):
        assert (
            manager._normalize_replay_stream_line(
                (prefix + payload).encode(), stream, "url"
            )
            is None
        )
    normalized = manager._normalize_replay_stream_line(
        ("00:00:00.000999" + payload).encode(), stream, "url"
    )
    assert json.loads(normalized)["t"] == 0


@pytest.mark.parametrize("stream", ["TrackStatus", "Position.z"])
async def test_local_replay_skips_bad_time_without_resetting_delay(
    hass, tmp_path, stream, monkeypatch
) -> None:
    monkeypatch.setattr(replay, "parse_position_z_line", lambda _: {"1": {}})
    monkeypatch.setattr(replay, "track_map_positions_to_payload", lambda p: p)
    payload = '"encoded"' if stream == "Position.z" else '{"Status":"1"}'
    source = tmp_path / "replay.txt"
    source.write_text(
        "\n".join(
            prefix + payload
            for prefix in ("00:00:00", "invalid", "00:00:00.123456", "25:00:00")
        ),
        encoding="utf-8",
    )
    client = ReplaySignalRClient(hass, source, stream_hint=stream)
    await client.ensure_connection()
    assert [frame.delay for frame in client._frames] == [0, 0.123, 89_999.877]
    assert client.invalid_timestamp_count == 1


@pytest.mark.parametrize("stream", ["TrackStatus", "Position.z"])
async def test_stream_download_paths_share_timestamp_filtering(
    hass, tmp_path, stream, monkeypatch
):
    monkeypatch.setattr(replay_mode, "parse_position_z_line", lambda _: {"1": {}})
    monkeypatch.setattr(replay_mode, "track_map_positions_to_payload", lambda p: p)
    payload = '"encoded"' if stream == "Position.z" else '{"Status":"1"}'
    lines = [
        (prefix + payload + "\n").encode()
        for prefix in (
            "00:00:00",
            "invalid",
            "00:00:00.1",
            "00:00:00.123456",
            "00:00:00.123999",
        )
    ]
    response = MagicMock(status=200)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    response.content.readline = AsyncMock(side_effect=[*lines, b""])
    response.text = AsyncMock(return_value=b"".join(lines).decode())
    http = MagicMock()
    http.get.return_value = response
    manager = ReplaySessionManager(hass, "entry", http)
    destination = tmp_path / "stream.jsonl"
    assert await manager._download_stream_to_file("url", stream, destination) == 4
    timestamps = [
        json.loads(line)["t"] for line in destination.read_text().splitlines()
    ]
    assert timestamps == [0, 100, 123, 123]
    assert manager._get_snapshot()["stream_parse_counts"][stream] == {
        "accepted": 4,
        "invalid": 1,
    }
    legacy = await manager._download_stream("url", stream)
    assert [frame.timestamp_ms for frame in legacy] == timestamps
