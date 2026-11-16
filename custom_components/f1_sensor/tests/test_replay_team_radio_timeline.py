"""Radio archives can use an elapsed clock inherited from another session.

The radio fixture preserves the official archive response retrieved 2026-11-16:
https://livetiming.formula1.com/static/2026/2026-11-01_Mexico_City_Grand_Prix/2026-11-01_Race/TeamRadio.jsonStream
No request credentials are included.
"""

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from custom_components.f1_sensor import replay_mode
from custom_components.f1_sensor.replay_mode import ReplaySession, ReplaySessionManager


class _Response:
    def __init__(self, text):
        self.status = 200 if text else 404
        self.content = self
        self._lines = iter([line.encode() + b"\n" for line in text.splitlines()])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def readline(self):
        return next(self._lines, b"")


class _Archive:
    def __init__(self, streams):
        self.streams = streams

    def get(self, url):
        return _Response(self.streams.get(url.rsplit("/", 1)[-1], ""))


def _lines(*rows):
    return "\n".join(prefix + json.dumps(payload) for prefix, payload in rows)


def _session():
    return ReplaySession(
        year=2026,
        meeting_key=1298,
        meeting_name="Mexico City Grand Prix",
        session_key=11404,
        session_name="Race",
        session_type="Race",
        path="2026/2026-11-01_Mexico_City_Grand_Prix/2026-11-01_Race",
        start_utc=datetime(2026, 11, 1, 20, tzinfo=UTC),
        end_utc=datetime(2026, 11, 1, 23, tzinfo=UTC),
    )


async def _load(hass, tmp_path, monkeypatch, radio, *, anchors=True, overrides=None):
    streams = {
        "SessionInfo.jsonStream": _lines(
            ("00:00:00.000", {"Key": 11404, "Meeting": {"Key": 1298}})
        ),
        "SessionStatus.jsonStream": _lines(
            ("00:13:22.499", {"Status": "Started"}),
            ("02:46:40.000", {"Status": "Finished"}),
        ),
        "TeamRadio.jsonStream": radio,
        # Heartbeat is generated when this archive is rebuilt, not at race UTC.
        "Heartbeat.jsonStream": _lines(
            ("00:00:15.001", {"Utc": "2026-11-03T04:50:31.3457232Z"})
        ),
    }
    if anchors:
        streams["SessionData.jsonStream"] = _lines(
            ("00:00:00.000", {"StatusSeries": [{"Utc": "2026-11-01T19:04:05.444Z"}]}),
            (
                "00:13:22.499",
                {
                    "StatusSeries": {
                        "1": {
                            "Utc": "2026-11-01T20:03:25.510Z",
                            "SessionStatus": "Started",
                        }
                    }
                },
            ),
            (
                "00:14:15.587",
                {"StatusSeries": {"2": {"Utc": "2026-11-01T20:04:18.598Z"}}},
            ),
        )
        streams["ExtrapolatedClock.jsonStream"] = _lines(
            ("00:00:00.984", {"Utc": "2026-11-01T19:50:03.995Z"}),
            ("00:13:23.000", {"Utc": "2026-11-01T20:03:26.011Z"}),
            ("02:11:56.997", {"Utc": "2026-10-31T17:20:00.009Z"}),
        )
    streams.update(overrides or {})
    manager = ReplaySessionManager(hass, "radio-test", _Archive(streams))
    manager._cache_dir = tmp_path
    monkeypatch.setattr(
        manager, "_find_formation_start_utc", AsyncMock(return_value=None)
    )
    index = await manager._download_and_index_session(_session())
    frames = [json.loads(line) for line in index.frames_file.read_text().splitlines()]
    return manager, index, frames


async def test_mexico_radio_archive_uses_session_clock_and_individual_capture_utc(
    hass, tmp_path, monkeypatch
):
    """Keep all 28 clips without stretching a race to the radio's old clock."""
    radio = (
        Path(__file__).parent / "fixtures/replay/team_radio_mexico_2026.jsonStream"
    ).read_text(encoding="utf-8-sig")
    manager, index, frames = await _load(hass, tmp_path, monkeypatch, radio)
    captures = [
        (frame["t"], capture)
        for frame in frames
        if frame["s"] == "TeamRadio"
        for capture in frame["p"]["Captures"]
    ]
    assert len(captures) == 28
    assert [t for t, _ in captures] == sorted(t for t, _ in captures)
    assert [t for t, _ in captures[:3]] == [321_555, 564_996, 930_568]
    assert [(t, capture["Utc"]) for t, capture in captures[12:14]] == [
        (3_917_991, "2026-11-01T20:55:21.002Z"),
        (3_918_223, "2026-11-01T20:55:21.234Z"),
    ]
    assert all(
        frame["p"]["_static_root"].endswith(_session().path)
        for frame in frames
        if frame["s"] == "TeamRadio"
    )
    assert index.duration_ms == 10_000_000
    assert index.session_started_at_ms == 802_499
    assert manager._stream_parse_counts["TeamRadio"] == {"accepted": 26, "invalid": 0}
    assert json.loads(index.index_file.read_text())["normalization_version"] > 1


@pytest.mark.parametrize(
    ("prefix", "expected"), [("00:00:10.000", [10_000]), ("1.02:32:50.914", [])]
)
async def test_radio_without_session_clock_preserves_normal_prefix_only(
    hass, tmp_path, monkeypatch, prefix, expected
):
    radio = _lines(
        (
            prefix,
            {
                "Captures": [
                    {
                        "Utc": "2026-11-01T19:55:24.566Z",
                        "RacingNumber": "50",
                        "Path": "TeamRadio/BEA.mp3",
                    }
                ]
            },
        )
    )
    manager, index, frames = await _load(
        hass, tmp_path, monkeypatch, radio, anchors=False
    )
    assert [frame["t"] for frame in frames if frame["s"] == "TeamRadio"] == expected
    assert index.duration_ms == 10_000_000
    assert manager._stream_parse_counts["TeamRadio"] == {
        "accepted": len(expected),
        "invalid": 1 - len(expected),
    }


@pytest.mark.parametrize("captures", [None, 1, "bad", {"0": None}, [None, "bad"]])
async def test_malformed_radio_capture_does_not_block_valid_replay(
    hass, tmp_path, monkeypatch, captures
):
    valid = {"Utc": "2026-11-01T20:05:33.579Z", "Path": "TeamRadio/HAM.mp3"}
    radio = _lines(
        ("1.02:32:50.914", {"Captures": captures}),
        ("1.02:42:59.406", {"Captures": [valid]}),
    )
    manager, index, frames = await _load(hass, tmp_path, monkeypatch, radio)
    assert [
        frame["p"]["Captures"] for frame in frames if frame["s"] == "TeamRadio"
    ] == [[valid]]
    assert index.duration_ms == 10_000_000
    assert manager._stream_parse_counts["TeamRadio"] == {"accepted": 1, "invalid": 1}


@pytest.mark.parametrize("entries", [None, 1, "bad", {"0": None}, [None, "bad"]])
async def test_malformed_session_clock_keeps_ordinary_radio_fallback(
    hass, tmp_path, monkeypatch, entries
):
    radio = _lines(
        ("00:00:10.000", {"Captures": [{"Utc": "bad", "Path": "TeamRadio/HAM.mp3"}]})
    )
    _, _, frames = await _load(
        hass,
        tmp_path,
        monkeypatch,
        radio,
        overrides={
            "SessionData.jsonStream": _lines(
                ("00:00:01.000", {"StatusSeries": entries})
            ),
            "ExtrapolatedClock.jsonStream": _lines(("00:00:01.000", {"Utc": entries})),
        },
    )
    assert [frame["t"] for frame in frames if frame["s"] == "TeamRadio"] == [10_000]


async def test_conflicting_session_clocks_do_not_guess_radio_time(
    hass, tmp_path, monkeypatch
):
    radio = _lines(
        (
            "1.02:32:50.914",
            {
                "Captures": [
                    {"Utc": "2026-11-01T19:55:24.566Z", "Path": "TeamRadio/BEA.mp3"}
                ]
            },
        )
    )
    manager, index, frames = await _load(
        hass,
        tmp_path,
        monkeypatch,
        radio,
        overrides={
            "ExtrapolatedClock.jsonStream": _lines(
                ("00:00:00.984", {"Utc": "2026-11-01T18:50:03.995Z"}),
                ("00:13:23.000", {"Utc": "2026-11-01T19:03:26.011Z"}),
            ),
        },
    )
    assert not [frame for frame in frames if frame["s"] == "TeamRadio"]
    assert index.duration_ms == 10_000_000
    assert manager._stream_parse_counts["TeamRadio"] == {"accepted": 0, "invalid": 1}


async def test_session_clock_consensus_tolerates_millisecond_truncation(
    hass, tmp_path, monkeypatch
):
    radio = _lines(
        (
            "1.02:32:50.914",
            {
                "Captures": [
                    {"Utc": "2026-11-01T19:55:24.566Z", "Path": "TeamRadio/BEA.mp3"}
                ]
            },
        )
    )
    _, _, frames = await _load(
        hass,
        tmp_path,
        monkeypatch,
        radio,
        overrides={
            "SessionData.jsonStream": _lines(
                (
                    "00:13:22.500",
                    {"StatusSeries": {"1": {"Utc": "2026-11-01T20:03:25.510Z"}}},
                )
            ),
            "ExtrapolatedClock.jsonStream": _lines(
                ("00:13:23.000", {"Utc": "2026-11-01T20:03:26.011901Z"})
            ),
        },
    )
    assert [frame["t"] for frame in frames if frame["s"] == "TeamRadio"] == [321_555]


async def test_radio_sorting_across_bounded_runs_preserves_equal_time_order(
    hass, tmp_path, monkeypatch
):
    monkeypatch.setattr(replay_mode, "REPLAY_STREAM_BATCH_LINES", 2)
    origin = datetime(2026, 11, 1, 19, 50, 3, 11000, tzinfo=UTC)
    rows = [
        (
            "1.00:00:00.000",
            {
                "Captures": [
                    {
                        "Utc": (origin + timedelta(seconds=second)).isoformat(),
                        "Path": f"TeamRadio/{index}.mp3",
                    }
                ]
            },
        )
        for index, second in enumerate([10, 1, 5, 5, 9, 8, 3, 7, 2, 4, 6])
    ]
    _, _, frames = await _load(hass, tmp_path, monkeypatch, _lines(*rows))
    radio = [frame for frame in frames if frame["s"] == "TeamRadio"]
    assert [frame["t"] for frame in radio] == [
        1000,
        2000,
        3000,
        4000,
        5000,
        5000,
        6000,
        7000,
        8000,
        9000,
        10000,
    ]
    assert [
        frame["p"]["Captures"][0]["Path"] for frame in radio if frame["t"] == 5000
    ] == ["TeamRadio/2.mp3", "TeamRadio/3.mp3"]
    assert not list(tmp_path.rglob("*.part"))


@pytest.mark.parametrize("shape", ["direct", "list", "single", "indexed"])
async def test_radio_without_capture_utc_preserves_supported_payload_shapes(
    hass, tmp_path, monkeypatch, shape
):
    capture = {"Path": "TeamRadio/HAM.mp3", "RacingNumber": "44"}
    payload = {
        "direct": capture,
        "list": {"Captures": [capture]},
        "single": {"Captures": capture},
        "indexed": {"Captures": {"7": capture}},
    }[shape]
    manager, _, frames = await _load(
        hass, tmp_path, monkeypatch, _lines(("00:00:10.000", payload))
    )
    radio = [frame for frame in frames if frame["s"] == "TeamRadio"]
    assert len(radio) == 1
    assert radio[0]["t"] == 10_000
    restored = radio[0]["p"]["Captures"]
    assert len(restored) == 1
    assert {key: restored[0][key] for key in capture} == capture
    assert manager._stream_parse_counts["TeamRadio"] == {"accepted": 1, "invalid": 0}
