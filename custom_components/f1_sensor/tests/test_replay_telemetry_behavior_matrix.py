"""Behavior coverage for bounded replay telemetry extraction."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import zlib

import pytest

from custom_components.f1_sensor import replay_telemetry as telemetry


def _encoded_line(payload: dict) -> str:
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(json.dumps(payload).encode()) + compressor.flush()
    return f'"{base64.b64encode(compressed).decode()}"'


def test_replay_telemetry_scalar_time_and_merge_helpers() -> None:
    assert telemetry._mapping([]) == {}
    assert telemetry._as_int(True) is None
    assert telemetry._as_int({"Value": "4"}) == 4
    assert telemetry._as_int("bad") is None
    assert telemetry._as_float(False) is None
    assert telemetry._as_float({"Value": "3.5"}) == 3.5
    assert telemetry._as_float("nan") is None
    assert telemetry._as_float(object()) is None
    assert telemetry._parse_utc(None) is None
    assert telemetry._parse_utc("bad") is None
    assert telemetry._parse_utc("2026-09-01T12:00:00").tzinfo is UTC
    assert telemetry._frame_utc({"Timestamp": "2026-09-01T12:00:00Z"})
    assert telemetry._frame_utc({"Entries": ["bad", {"Utc": "2026-09-01T12:00:01Z"}]})
    assert telemetry._frame_utc({}) is None
    target = {"nested": {"one": 1}, "replace": 1}
    telemetry._deep_merge(target, {"nested": {"two": 2}, "replace": {"x": 1}})
    assert target == {"nested": {"one": 1, "two": 2}, "replace": {"x": 1}}


def test_replay_window_scan_decode_distance_and_downsample(tmp_path) -> None:
    frames = tmp_path / "frames.jsonl"
    frames.write_text(
        "\n".join(
            (
                "bad",
                json.dumps(
                    {
                        "t": 1000,
                        "s": "SessionInfo",
                        "p": {"Utc": "2026-09-01T12:00:00Z"},
                    }
                ),
                json.dumps(
                    {
                        "t": 2000,
                        "s": "TimingData",
                        "p": {
                            "Lines": {
                                "4": {
                                    "NumberOfLaps": 1,
                                    "LastLapTime": {"Value": "1:20"},
                                },
                                "bad": {},
                            }
                        },
                    }
                ),
                json.dumps(
                    {
                        "t": 3000,
                        "s": "TimingData",
                        "p": {
                            "Lines": {
                                "4": {
                                    "NumberOfLaps": 2,
                                    "LastLapTime": {"Value": "1:19"},
                                }
                            }
                        },
                    }
                ),
            )
        )
    )
    windows, anchor = telemetry._scan_replay_windows(frames, ((4, 2),), 0)
    assert windows == {"4:2": (2000, 3000)}
    assert anchor == (datetime(2026, 9, 1, 12, tzinfo=UTC), 1000)

    line = _encoded_line(
        {
            "Entries": [
                "bad",
                {"Utc": "bad", "Cars": {}},
                {
                    "Utc": "2026-09-01T12:00:01Z",
                    "Cars": {
                        "4": {
                            "Channels": {
                                "0": "11000",
                                "2": "300",
                                "3": "7",
                                "4": "100",
                                "5": "0",
                                "45": "12",
                            }
                        }
                    },
                },
            ]
        }
    )
    samples, max_seen = telemetry._decode_selected_batch(
        ["bad", line],
        anchor_utc=datetime(2026, 9, 1, 12, tzinfo=UTC),
        anchor_ms=1000,
        windows={"4:2": (1000, 3000)},
    )
    assert max_seen == 2000
    assert samples["4:2"][0]["speed"] == 300.0

    raw = [{"timestamp_ms": i, "time_s": float(i), "speed": 36.0} for i in range(2)]
    assert telemetry._add_distance(raw)[-1]["distance"] == 10.0
    bounded = [
        {"timestamp_ms": i} for i in range(telemetry.MAX_RAW_SELECTION_POINTS + 1)
    ]
    telemetry._bounded_extend(bounded, [])
    assert len(bounded) < telemetry.MAX_RAW_SELECTION_POINTS
    downsampled = telemetry._downsample(
        [{"timestamp_ms": i} for i in range(telemetry.MAX_TELEMETRY_POINTS + 5)]
    )
    assert len(downsampled) == telemetry.MAX_TELEMETRY_POINTS
    assert telemetry._time_at_distance([], 1) is None
    assert (
        telemetry._time_at_distance(
            [{"distance": 0, "time_s": 0}, {"distance": 10, "time_s": 2}], 5
        )
        == 1
    )
    assert (
        telemetry._time_at_distance(
            [{"distance": 2, "time_s": 1}, {"distance": 2, "time_s": 2}], 2
        )
        == 2
    )
    assert telemetry._time_at_distance([{"distance": 1, "time_s": 3}], 5) == 3

    invalid_frames = tmp_path / "invalid-frames.jsonl"
    invalid_frames.write_text(
        "\n".join(
            (
                json.dumps({"t": 1, "s": "TimingData", "p": []}),
                json.dumps({"t": 2, "s": "TimingData", "p": {"Lines": []}}),
            )
        ),
        encoding="utf-8",
    )
    assert telemetry._scan_replay_windows(invalid_frames, ((4, 99),), 0) == (
        {},
        None,
    )


class _Response:
    def __init__(self, status: int, error: Exception | None = None) -> None:
        self.status = status
        self.content = self
        self._error = error

    async def readline(self) -> bytes:
        if self._error:
            raise self._error
        return b""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _Session:
    def __init__(self, response: _Response) -> None:
        self.response = response

    def get(self, _url: str) -> _Response:
        return self.response


def _manager(tmp_path):
    index = SimpleNamespace(
        session_id="session",
        frames_file=tmp_path / "frames",
        session_started_at_ms=0,
    )
    selected = SimpleNamespace(
        path="2026/test",
        start_utc=datetime(2026, 9, 1, 12, tzinfo=UTC),
    )
    return SimpleNamespace(
        get_loaded_index=lambda: index,
        selected_session=selected,
    )


async def test_replay_compare_validation_missing_laps_and_provider_errors(
    hass, tmp_path, monkeypatch
) -> None:
    service = telemetry.ReplayTelemetryService(hass, _Session(_Response(200)), None)
    with pytest.raises(ValueError, match="valid driver_number"):
        await service.async_compare([{"driver_number": 0, "lap_number": 1}])
    with pytest.raises(ValueError, match="At least one"):
        await service.async_compare([])
    with pytest.raises(ValueError, match="At most"):
        await service.async_compare(
            [
                {"driver_number": driver, "lap_number": 1}
                for driver in range(1, telemetry.MAX_TELEMETRY_SELECTIONS + 2)
            ]
        )
    with pytest.raises(ValueError, match="Load a replay"):
        await service.async_compare([{"driver_number": 4, "lap_number": 1}])

    manager = _manager(tmp_path)
    manager.get_loaded_index = lambda: None
    service = telemetry.ReplayTelemetryService(hass, _Session(_Response(200)), manager)
    with pytest.raises(ValueError, match="Load a replay"):
        await service.async_compare([{"driver_number": 4, "lap_number": 1}])

    manager = _manager(tmp_path)
    monkeypatch.setattr(
        hass, "async_add_executor_job", AsyncMock(return_value=({}, None))
    )
    service = telemetry.ReplayTelemetryService(hass, _Session(_Response(200)), manager)
    with pytest.raises(ValueError, match="unavailable"):
        await service.async_compare([{"driver_number": 4, "lap_number": 1}])

    for status, message in ((404, "unavailable"), (503, "temporarily")):
        monkeypatch.setattr(
            hass,
            "async_add_executor_job",
            AsyncMock(return_value=({"4:1": (0, 1000)}, None)),
        )
        service = telemetry.ReplayTelemetryService(
            hass, _Session(_Response(status)), _manager(tmp_path)
        )
        with pytest.raises(ValueError, match=message):
            await service.async_compare([{"driver_number": 4, "lap_number": 1}])

    monkeypatch.setattr(
        hass,
        "async_add_executor_job",
        AsyncMock(return_value=({"4:1": (0, 1000)}, None)),
    )
    service = telemetry.ReplayTelemetryService(
        hass, _Session(_Response(200, TimeoutError())), _manager(tmp_path)
    )
    with pytest.raises(ValueError, match="timed out"):
        await service.async_compare([{"driver_number": 4, "lap_number": 1}])
    await service.async_close()
    assert service.diagnostics()["cache_entries"] == 0
