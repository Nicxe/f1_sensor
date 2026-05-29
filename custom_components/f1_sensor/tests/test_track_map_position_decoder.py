from __future__ import annotations

import base64
from datetime import UTC, datetime
import json
import zlib

from custom_components.f1_sensor.helpers import POSITION_Z_MAX_DECOMPRESSED_BYTES
from custom_components.f1_sensor.track_map import (
    TrackMapPosition,
    decode_position_z_payload,
    parse_position_z_line,
    parse_position_z_lines,
    track_map_positions_from_payload,
    track_map_positions_to_payload,
)


def _encoded_position_payload(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(raw) + compressor.flush()
    return base64.b64encode(compressed).decode()


def _json_stream_line(data: dict, offset: str = "00:00:04.951") -> str:
    return f'{offset}"{_encoded_position_payload(data)}"'


def _position_payload(entries: dict) -> dict:
    return {
        "Position": [
            {
                "Timestamp": "2026-05-03T16:06:45.6951105Z",
                "Entries": entries,
            }
        ]
    }


def test_parse_position_z_line_returns_positions_for_multiple_drivers() -> None:
    positions = parse_position_z_line(
        _json_stream_line(
            _position_payload(
                {
                    "1": {"Status": "OnTrack", "X": -68, "Y": 331, "Z": 0},
                    "4": {"Status": "OffTrack", "X": 180, "Y": 412, "Z": 3},
                }
            )
        )
    )

    assert positions == [
        TrackMapPosition(
            racing_number="1",
            timestamp=datetime(2026, 5, 3, 16, 6, 45, 695110, tzinfo=UTC),
            x=-68,
            y=331,
            z=0,
            status="OnTrack",
        ),
        TrackMapPosition(
            racing_number="4",
            timestamp=datetime(2026, 5, 3, 16, 6, 45, 695110, tzinfo=UTC),
            x=180,
            y=412,
            z=3,
            status="OffTrack",
        ),
    ]


def test_parse_position_z_line_preserves_zero_zero_positions() -> None:
    positions = parse_position_z_line(
        _json_stream_line(
            _position_payload(
                {
                    "10": {"Status": "OnTrack", "X": 0, "Y": 0, "Z": 0},
                }
            )
        )
    )

    assert len(positions) == 1
    assert positions[0].racing_number == "10"
    assert positions[0].x == 0
    assert positions[0].y == 0
    assert positions[0].z == 0


def test_parse_position_z_line_handles_bad_and_empty_payloads() -> None:
    assert parse_position_z_line("") == []
    assert (
        parse_position_z_line("URL: https://example.test/Position.z.jsonStream") == []
    )
    assert parse_position_z_line('00:00:01.000"not-base64"') == []
    assert parse_position_z_line(_json_stream_line({"Position": []})) == []
    assert parse_position_z_line(_json_stream_line({"Other": []})) == []


def test_parse_position_z_line_rejects_oversized_decompressed_payload() -> None:
    payload = _position_payload(
        {"1": {"Status": "OnTrack", "X": -68, "Y": 331, "Z": 0}}
    )
    payload["Pad"] = "x" * (POSITION_Z_MAX_DECOMPRESSED_BYTES + 1)

    assert parse_position_z_line(_json_stream_line(payload)) == []


def test_parse_position_z_line_skips_invalid_entries_without_failing() -> None:
    positions = parse_position_z_line(
        _json_stream_line(
            _position_payload(
                {
                    "": {"Status": "OnTrack", "X": 1, "Y": 2, "Z": 0},
                    "0": {"Status": "OnTrack", "X": 1, "Y": 2, "Z": 0},
                    "bad": {"Status": "OnTrack", "X": 1, "Y": 2, "Z": 0},
                    "11": {"Status": "OnTrack", "Y": 2, "Z": 0},
                    "22": {"Status": "OnTrack", "X": 1, "Z": 0},
                    "81": {"X": "15", "Y": "-20"},
                }
            )
        )
    )

    assert positions == [
        TrackMapPosition(
            racing_number="81",
            timestamp=datetime(2026, 5, 3, 16, 6, 45, 695110, tzinfo=UTC),
            x=15,
            y=-20,
            z=None,
            status="Unknown",
        )
    ]


def test_parse_position_z_line_skips_internal_high_number_entries() -> None:
    positions = parse_position_z_line(
        _json_stream_line(
            _position_payload(
                {
                    "99": {"Status": "OnTrack", "X": 1, "Y": 2, "Z": 0},
                    "100": {"Status": "OnTrack", "X": 3, "Y": 4, "Z": 0},
                    "242": {"Status": "OffTrack", "X": 0, "Y": 0, "Z": 0},
                    "243": {"Status": "OnTrack", "X": 5, "Y": 6, "Z": 0},
                }
            )
        )
    )

    assert [position.racing_number for position in positions] == ["99"]


def test_decode_position_z_payload_accepts_live_encoded_payload() -> None:
    payload = _position_payload(
        {
            "63": {"Status": "OnTrack", "X": 101, "Y": 202, "Z": 4},
        }
    )

    positions = decode_position_z_payload(_encoded_position_payload(payload))

    assert [(item.racing_number, item.x, item.y, item.z) for item in positions] == [
        ("63", 101, 202, 4)
    ]


def test_decode_position_z_payload_accepts_already_decoded_payload() -> None:
    positions = decode_position_z_payload(
        {
            "Timestamp": "2026-05-03T16:06:45Z",
            "Entries": {
                12: {"RacingNumber": "01", "Status": "OnTrack", "X": 7, "Y": 8},
                242: {"Status": "OnTrack", "X": 9, "Y": 10},
            },
        }
    )

    assert positions == [
        TrackMapPosition(
            racing_number="1",
            timestamp=datetime(2026, 5, 3, 16, 6, 45, tzinfo=UTC),
            x=7,
            y=8,
            z=None,
            status="OnTrack",
        )
    ]


def test_decode_position_z_payload_uses_observed_at_when_timestamp_is_missing() -> None:
    positions = decode_position_z_payload(
        _encoded_position_payload(
            {
                "Position": [
                    {
                        "Entries": {
                            "44": {
                                "Status": "OnTrack",
                                "X": 123,
                                "Y": 456,
                                "Z": 7,
                            }
                        }
                    }
                ]
            }
        ),
        observed_at="2026-05-03T16:06:46Z",
    )

    assert positions == [
        TrackMapPosition(
            racing_number="44",
            timestamp=datetime(2026, 5, 3, 16, 6, 46, tzinfo=UTC),
            x=123,
            y=456,
            z=7,
            status="OnTrack",
        )
    ]


def test_parse_position_z_lines_flattens_multiple_lines() -> None:
    lines = [
        _json_stream_line(_position_payload({"1": {"X": 1, "Y": 2}})),
        _json_stream_line(_position_payload({"2": {"X": 3, "Y": 4}})),
    ]

    positions = parse_position_z_lines(lines)

    assert [position.racing_number for position in positions] == ["1", "2"]


def test_track_map_replay_payload_roundtrips_positions() -> None:
    positions = parse_position_z_line(
        _json_stream_line(_position_payload({"23": {"X": 11, "Y": 22, "Z": 3}}))
    )

    payload = track_map_positions_to_payload(positions)
    decoded = track_map_positions_from_payload(payload)

    assert decoded == positions
