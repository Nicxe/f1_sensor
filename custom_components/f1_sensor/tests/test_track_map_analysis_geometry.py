from __future__ import annotations

import base64
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
import json
import math
from math import isfinite
from types import SimpleNamespace
import zlib

import pytest

from custom_components.f1_sensor import (
    track_map_static_geometry_calibrator as calibrator,
    track_map_static_geometry_maintenance as maintenance,
    track_map_static_geometry_qa as geometry_qa,
)
from custom_components.f1_sensor.helpers import (
    get_circuit_map_url,
    get_circuit_outline_url,
)
from custom_components.f1_sensor.track_map import (
    TRACK_MAP_STATIC_GEOMETRY_SOURCE,
    TrackMapBounds,
    TrackMapPosition,
    analyze_position_z_lines,
    build_track_geometry_from_position_groups,
    build_track_geometry_from_positions,
    get_static_track_geometry,
)
from custom_components.f1_sensor.track_map_static_geometry import (
    STATIC_TRACK_GEOMETRIES,
    STATIC_TRACK_GEOMETRY_APPROVAL_QA_PASSED,
    STATIC_TRACK_GEOMETRY_APPROVAL_VISUAL_APPROVED,
    STATIC_TRACK_GEOMETRY_CATALOG_VERSION,
    STATIC_TRACK_GEOMETRY_QA_ARTIFACT,
    get_static_track_geometry_provenance,
)
from custom_components.f1_sensor.track_map_static_geometry_builder import (
    build_static_track_geometry_from_position_lines,
)
from custom_components.f1_sensor.track_map_static_geometry_calibrator import (
    calibrate_static_track_geometry_from_image_points,
    extract_track_points_from_detailed_map_bytes,
    presentation_rotation_from_image_points,
    shape_aligned_presentation_rotation_from_image_points,
)
from custom_components.f1_sensor.track_map_static_geometry_maintenance import (
    MAINTENANCE_STATUS_CANDIDATE_READY,
    MAINTENANCE_STATUS_CATALOGED,
    MAINTENANCE_STATUS_MISSING_POSITION_Z,
    build_static_track_geometry_maintenance_report,
    scan_position_dump_sessions,
    write_static_track_geometry_maintenance_artifacts,
)
from custom_components.f1_sensor.track_map_static_geometry_qa import (
    STATUS_MISSING_CATALOG,
    STATUS_OK,
    build_static_track_geometry_qa_report,
    expected_2025_2026_catalog_circuit_ids,
    render_static_track_geometry_qa_overlay,
    write_static_track_geometry_qa_artifacts,
)

BASE = datetime(2026, 5, 3, 16, 6, 45, tzinfo=UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _encoded_position_payload(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(raw) + compressor.flush()
    return base64.b64encode(compressed).decode()


def _json_stream_line(data: dict, offset: str = "00:00:04.951") -> str:
    return f'{offset}"{_encoded_position_payload(data)}"'


def _position_payload(entries: dict, at: datetime = BASE) -> dict:
    return {
        "Position": [
            {
                "Timestamp": _iso(at),
                "Entries": entries,
            }
        ]
    }


def _position(
    racing_number: str,
    x: int,
    y: int,
    *,
    z: int | None = 0,
    status: str = "OnTrack",
    seconds: int = 0,
) -> TrackMapPosition:
    return TrackMapPosition(
        racing_number=racing_number,
        timestamp=BASE + timedelta(seconds=seconds),
        x=x,
        y=y,
        z=z,
        status=status,
    )


def _positions_from_points(
    racing_number: str,
    points: list[tuple[int, int]],
    *,
    z: int | None = 0,
    start_seconds: int = 0,
) -> list[TrackMapPosition]:
    return [
        _position(
            racing_number,
            x,
            y,
            z=z,
            seconds=start_seconds + index,
        )
        for index, (x, y) in enumerate(points)
    ]


def _representative_loop(offset: int = 0) -> list[tuple[int, int]]:
    return [
        (100 + offset, 100 + offset),
        (600 + offset, 100 + offset),
        (1100 + offset, 100 + offset),
        (1100 + offset, 600 + offset),
        (1100 + offset, 1100 + offset),
        (600 + offset, 1100 + offset),
        (100 + offset, 1100 + offset),
        (-400 + offset, 1100 + offset),
        (-400 + offset, 600 + offset),
        (-400 + offset, 100 + offset),
        (100 + offset, 100 + offset),
    ]


def _screen_points_for_rotation(
    points: tuple[tuple[float, float], ...],
    rotation: float,
) -> tuple[tuple[float, float], ...]:
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    radians = math.radians(rotation)
    cos_value = math.cos(radians)
    sin_value = math.sin(radians)
    screen_points: list[tuple[float, float]] = []
    for x, y in points:
        dx = x - center_x
        dy = y - center_y
        rotated_x = center_x + (dx * cos_value) - (dy * sin_value)
        rotated_y = center_y + (dx * sin_value) + (dy * cos_value)
        screen_points.append((rotated_x, -rotated_y))
    return tuple(screen_points)


def _qa_test_image_bytes() -> bytes:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (160, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.line(
        [(15, 70), (48, 18), (112, 20), (140, 58), (78, 82), (15, 70)],
        fill="black",
        width=8,
        joint="curve",
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _outline_test_image_bytes() -> bytes:
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (40, 30), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.line([(2, 20), (20, 2), (37, 20)], fill="white", width=3)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _write_dump_session(
    root,
    *,
    event_dir: str,
    circuit_key: str,
    circuit_short_name: str,
    meeting_name: str,
    circuit_id: str | None = None,
) -> None:
    race_dir = root / "2026" / "GrandPrix" / event_dir / "Race"
    race_dir.mkdir(parents=True)
    prefix = f"2026_{event_dir}_Race"
    session_info = {
        "Meeting": {
            "Name": meeting_name,
            "Circuit": {"Key": circuit_key, "ShortName": circuit_short_name},
        },
        "Key": 9999,
        "Type": "Race",
        "Name": "Race",
        "StartDate": "2026-09-13T13:00:00",
        "Path": f"2026/{event_dir}/Race/",
    }
    (race_dir / f"{prefix}_SessionInfo.txt").write_text(
        "URL: https://example.test/SessionInfo.jsonStream\n\n"
        f"00:00:00.000{json.dumps(session_info)}\n",
        encoding="utf-8",
    )
    points = _representative_loop()
    lines = [
        _json_stream_line(
            _position_payload(
                {"1": {"Status": "OnTrack", "X": x, "Y": y, "Z": 0}},
                BASE + timedelta(seconds=index),
            ),
            f"00:00:{index:02}.000",
        )
        for index, (x, y) in enumerate(points)
    ]
    filename_circuit = circuit_id or circuit_short_name
    (race_dir / f"{prefix}_{filename_circuit}_Position.z.txt").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def test_analyze_position_z_lines_returns_compact_metrics() -> None:
    lines = [
        "URL: https://example.test/Position.z.jsonStream",
        _json_stream_line(
            _position_payload(
                {
                    "1": {"Status": "OnTrack", "X": -10, "Y": 20, "Z": 0},
                    "4": {"Status": "OffTrack", "X": 30, "Y": 40, "Z": 3},
                },
                BASE,
            )
        ),
        _json_stream_line(
            _position_payload(
                {
                    "1": {"Status": "OnTrack", "X": 0, "Y": 0, "Z": 0},
                    "63": {"Status": "OnTrack", "X": 100, "Y": -50, "Z": 5},
                    "bad": {"Status": "OnTrack", "X": 9, "Y": 9, "Z": 0},
                },
                BASE + timedelta(seconds=1),
            ),
            "00:00:05.951",
        ),
        '00:00:06.000"not-base64"',
    ]

    metrics = analyze_position_z_lines(lines)

    assert metrics.frame_count == 2
    assert metrics.sample_count == 2
    assert metrics.decoded_positions == 4
    assert metrics.driver_count == 3
    assert metrics.average_drivers_per_sample == 2.5
    assert metrics.on_track_count == 3
    assert metrics.off_track_count == 1
    assert metrics.zero_zero_count == 1
    assert metrics.invalid_line_count == 1
    assert metrics.first_timestamp == BASE
    assert metrics.last_timestamp == BASE + timedelta(seconds=1)
    assert metrics.bounds == TrackMapBounds(
        min_x=-10,
        max_x=100,
        min_y=-50,
        max_y=40,
        min_z=0,
        max_z=5,
    )


def test_static_geometry_image_extractors_calibration_and_rotation_helpers(
    monkeypatch,
) -> None:
    outline = _outline_test_image_bytes()
    points = calibrator.extract_track_points_from_image_bytes(outline, max_points=5)
    assert 2 <= len(points) <= 5
    detailed = extract_track_points_from_detailed_map_bytes(
        _qa_test_image_bytes(), max_dimension=50, max_points=10
    )
    assert 2 <= len(detailed) <= 10

    from PIL import Image

    empty = BytesIO()
    Image.new("RGBA", (5, 5), (0, 0, 0, 0)).save(empty, format="PNG")
    with pytest.raises(ValueError, match="enough visible"):
        calibrator.extract_track_points_from_image_bytes(empty.getvalue())
    with pytest.raises(ValueError, match="enough circuit"):
        extract_track_points_from_detailed_map_bytes(empty.getvalue())

    monkeypatch.setattr(calibrator, "get_circuit_map_url", lambda *_: "map-url")
    monkeypatch.setattr(
        calibrator, "_download_image", lambda *_args, **_kwargs: _qa_test_image_bytes()
    )
    result = calibrator.calibrate_static_track_geometry_from_f1_image("151")
    assert result.image_url == "map-url"

    monkeypatch.setattr(calibrator, "get_circuit_map_url", lambda *_: None)
    monkeypatch.setattr(calibrator, "get_circuit_outline_url", lambda *_: "outline-url")
    monkeypatch.setattr(
        calibrator, "_download_image", lambda *_args, **_kwargs: outline
    )
    result = calibrator.calibrate_static_track_geometry_from_f1_image("151")
    assert result.image_url == "outline-url"
    monkeypatch.setattr(calibrator, "get_circuit_outline_url", lambda *_: None)
    with pytest.raises(ValueError, match="No F1 circuit image"):
        calibrator.calibrate_static_track_geometry_from_f1_image("151")

    assert calibrator._normalize_shape_rotation(370, reference_rotation=5) == 10
    assert calibrator._normalize_equivalent_rotation(180, reference_rotation=None) == 0
    assert calibrator._normalize_equivalent_rotation(0.01, reference_rotation=0) == 0


def test_static_geometry_maintenance_and_qa_cli_paths(tmp_path, monkeypatch) -> None:
    maintenance_report = SimpleNamespace(
        cataloged_count=20,
        candidate_count=1,
        missing_position_z_count=1,
    )
    monkeypatch.setattr(
        maintenance,
        "build_static_track_geometry_maintenance_report",
        lambda **_kwargs: maintenance_report,
    )
    monkeypatch.setattr(
        maintenance,
        "write_static_track_geometry_maintenance_artifacts",
        lambda *_args, **_kwargs: {"json": tmp_path / "maintenance.json"},
    )
    assert maintenance.main(["--output-dir", str(tmp_path)]) == 0
    assert maintenance.main(["--output-dir", str(tmp_path), "--strict"]) == 1
    assert maintenance._normalize_degrees(360) == 0
    assert maintenance._normalize_degrees(-360) == 0
    assert maintenance._text_or_none(" ") is None
    assert maintenance._json_payload_from_stream_line("URL: ignored") is None
    assert maintenance._json_payload_from_stream_line("prefix {bad") is None
    info = tmp_path / "SessionInfo.txt"
    info.write_text('00:00:00.000{"Meeting":{"Name":"Test"}}')
    assert maintenance._read_session_info_file(info)["Meeting"]["Name"] == "Test"
    assert maintenance._read_session_info_file(tmp_path / "missing") == {}

    qa_report = SimpleNamespace(
        covered_count=20,
        expected_count=21,
        missing_circuit_ids=("madring",),
        unexpected_circuit_ids=(),
        entries=(),
    )
    monkeypatch.setattr(
        geometry_qa,
        "build_static_track_geometry_qa_report",
        lambda **_kwargs: qa_report,
    )
    monkeypatch.setattr(
        geometry_qa,
        "write_static_track_geometry_qa_artifacts",
        lambda *_args, **_kwargs: {"json": tmp_path / "qa.json"},
    )
    assert geometry_qa.main(["--output-dir", str(tmp_path), "--no-render"]) == 0
    assert (
        geometry_qa.main(["--output-dir", str(tmp_path), "--no-render", "--strict"])
        == 1
    )
    assert geometry_qa._normalize_points(()) == ()
    assert (
        geometry_qa._qa_font(
            SimpleNamespace(truetype=lambda *_: (_ for _ in ()).throw(RuntimeError()))
        )
        is None
    )


def test_analyze_position_z_lines_handles_empty_input() -> None:
    metrics = analyze_position_z_lines(["", "URL: ignored"])

    assert metrics.frame_count == 0
    assert metrics.sample_count == 0
    assert metrics.decoded_positions == 0
    assert metrics.driver_count == 0
    assert metrics.average_drivers_per_sample == 0
    assert metrics.bounds is None


def test_build_track_geometry_from_positions_filters_zero_and_non_ontrack() -> None:
    geometry = build_track_geometry_from_positions(
        [
            _position("1", 0, 0),
            _position("1", 10, 20),
            _position("1", 30, 40, status="OffTrack"),
            _position("1", 50, 60),
        ],
        circuit_key="miami",
        max_points=100,
    )

    assert geometry is not None
    assert geometry.circuit_key == "miami"
    assert geometry.source == "derived_position_z"
    assert geometry.points == ((10, 20), (50, 60))
    assert geometry.bounds == TrackMapBounds(
        min_x=10,
        max_x=50,
        min_y=20,
        max_y=60,
    )


def test_build_track_geometry_from_positions_removes_obvious_outlier() -> None:
    positions = [
        _position("1", 100 + index, 200 + index, seconds=index) for index in range(10)
    ]
    positions.append(_position("1", 50000, -50000, seconds=11))

    geometry = build_track_geometry_from_positions(positions)

    assert geometry is not None
    assert (50000, -50000) not in geometry.points
    assert geometry.bounds == TrackMapBounds(
        min_x=100,
        max_x=109,
        min_y=200,
        max_y=209,
    )


def test_build_track_geometry_from_positions_downsamples_and_keeps_ends() -> None:
    geometry = build_track_geometry_from_positions(
        [_position("1", index, index * 2, seconds=index) for index in range(1, 11)],
        max_points=4,
    )

    assert geometry is not None
    assert len(geometry.points) == 4
    assert geometry.points[0] == (1, 2)
    assert geometry.points[-1] == (10, 20)


def test_build_track_geometry_from_positions_uses_representative_loop() -> None:
    positions = _positions_from_points("1", _representative_loop())
    positions.extend(
        _positions_from_points(
            "1",
            _representative_loop(offset=30),
            start_seconds=len(positions),
        )
    )

    geometry = build_track_geometry_from_positions(positions)

    assert geometry is not None
    assert geometry.points == tuple(_representative_loop())
    assert (130, 130) not in geometry.points


def test_build_track_geometry_from_positions_does_not_force_close_near_loop() -> None:
    points = _representative_loop()
    points[-1] = (120, 100)

    geometry = build_track_geometry_from_positions(_positions_from_points("1", points))

    assert geometry is not None
    assert geometry.points[-1] == (120, 100)
    assert geometry.points[-1] != geometry.points[0]


def test_build_track_geometry_from_position_groups_prefers_closed_clean_segment() -> (
    None
):
    incomplete_long_run = _positions_from_points(
        "1",
        [(3000 + index * 100, 250) for index in range(20)],
    )
    clean_loop = _positions_from_points("4", _representative_loop())

    geometry = build_track_geometry_from_position_groups(
        {
            "1": incomplete_long_run,
            "4": clean_loop,
        }
    )

    assert geometry is not None
    assert geometry.points == tuple(_representative_loop())
    assert geometry.bounds.max_x == 4900


def test_build_track_geometry_from_positions_handles_missing_z() -> None:
    geometry = build_track_geometry_from_positions(
        _positions_from_points("1", _representative_loop(), z=None)
    )

    assert geometry is not None
    assert geometry.points[0] == (100, 100)


def test_build_track_geometry_from_positions_returns_none_for_no_track_points() -> None:
    assert (
        build_track_geometry_from_positions(
            [
                _position("1", 0, 0),
                _position("1", 10, 20, status="OffTrack"),
            ]
        )
        is None
    )


def test_static_track_geometry_catalog_returns_miami_by_key() -> None:
    geometry = get_static_track_geometry(circuit_key="151")

    assert geometry is not None
    assert geometry.source == TRACK_MAP_STATIC_GEOMETRY_SOURCE
    assert geometry.circuit_key == "151"
    assert len(geometry.points) > 40
    assert geometry.points[0] == geometry.points[-1]


def test_static_track_geometry_catalog_returns_suzuka_by_alias() -> None:
    geometry = get_static_track_geometry(circuit_short_name="Suzuka")

    assert geometry is not None
    assert geometry.source == TRACK_MAP_STATIC_GEOMETRY_SOURCE
    assert geometry.circuit_key == "46"
    assert len(geometry.points) > 50
    assert geometry.points[0] == geometry.points[-1]


def test_static_track_geometry_catalog_uses_full_silverstone_loop() -> None:
    geometry = get_static_track_geometry(circuit_key="2")

    assert geometry is not None
    assert geometry.circuit_key == "2"
    assert geometry.points[0] == geometry.points[-1]
    assert geometry.bounds.min_x <= -2280
    assert geometry.bounds.max_x >= 7780
    assert geometry.bounds.min_y <= -4080
    assert geometry.bounds.max_y >= 13090
    assert any(x <= -2200 and -400 <= y <= 600 for x, y in geometry.points)


def test_static_track_geometry_catalog_contains_2025_calendar_tracks() -> None:
    expected = {
        "2": "Silverstone",
        "4": "Hungaroring",
        "6": "Imola",
        "7": "Spa-Francorchamps",
        "9": "Austin",
        "10": "Melbourne",
        "14": "Interlagos",
        "15": "Catalunya",
        "19": "Spielberg",
        "22": "Monte Carlo",
        "23": "Montreal",
        "39": "Monza",
        "46": "Suzuka",
        "49": "Shanghai",
        "55": "Zandvoort",
        "61": "Singapore",
        "63": "Sakhir",
        "65": "Mexico City",
        "70": "Yas Marina Circuit",
        "144": "Baku",
        "149": "Jeddah",
        "150": "Lusail",
        "151": "Miami",
        "152": "Las Vegas",
    }

    assert set(STATIC_TRACK_GEOMETRIES) == set(expected)
    for circuit_key, alias in expected.items():
        geometry = get_static_track_geometry(circuit_key=circuit_key)
        alias_geometry = get_static_track_geometry(circuit_short_name=alias)

        assert geometry is not None
        assert alias_geometry is not None
        assert geometry.circuit_key == circuit_key
        assert alias_geometry.circuit_key == circuit_key
        assert len(geometry.points) >= 50
        assert geometry.points[0] == geometry.points[-1]


def test_static_track_geometry_catalog_exposes_presentation_rotation() -> None:
    expected_rotations = {
        "2": -89.0,
        "4": 99.0,
        "6": -1.6,
        "7": 96.3,
        "9": -7.4,
        "10": 48.0,
        "14": -87.2,
        "15": -54.8,
        "19": 25.0,
        "22": -48.0,
        "23": 58.3,
        "39": 101.0,
        "46": -0.8,
        "49": -119.8,
        "55": 177.0,
        "61": 0.2,
        "63": 94.8,
        "65": 6.7,
        "70": -100.0,
        "144": -50.6,
        "149": 111.0,
        "150": 61.0,
        "151": 11.2,
        "152": 87.8,
    }

    for circuit_key, rotation in expected_rotations.items():
        geometry = get_static_track_geometry(circuit_key=circuit_key)

        assert geometry is not None
        assert geometry.rotation == rotation


def test_static_track_geometry_calibrator_matches_image_axis() -> None:
    geometry_points = ((0.0, 0.0), (100.0, 0.0))
    image_points = ((0.0, 0.0), (100.0, 100.0))

    assert (
        presentation_rotation_from_image_points(
            geometry_points,
            image_points,
        )
        == -45.0
    )


def test_static_track_geometry_calibrator_matches_detailed_map_shape() -> None:
    geometry_points = (
        (0.0, 0.0),
        (100.0, 0.0),
        (100.0, 50.0),
        (30.0, 50.0),
        (30.0, 100.0),
        (0.0, 100.0),
        (0.0, 0.0),
    )
    image_points = _screen_points_for_rotation(geometry_points, 37.0)

    rotation = shape_aligned_presentation_rotation_from_image_points(
        geometry_points,
        image_points,
        grid_size=64,
    )

    assert abs(rotation - 37.0) <= 1.0


def test_static_track_geometry_calibrator_extracts_detailed_map_component() -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return

    image = Image.new("RGB", (140, 90), "white")
    draw = ImageDraw.Draw(image)
    draw.line(
        [(15, 65), (45, 20), (95, 18), (120, 50), (72, 72), (15, 65)],
        fill="black",
        width=8,
        joint="curve",
    )
    draw.rectangle((5, 5, 18, 12), fill="black")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    points = extract_track_points_from_detailed_map_bytes(buffer.getvalue())

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    assert len(points) > 600
    assert max(xs) - min(xs) > 90
    assert max(ys) - min(ys) > 45


def test_static_track_geometry_calibrator_uses_catalog_metadata() -> None:
    image_points = ((0.0, 0.0), (100.0, 100.0))

    result = calibrate_static_track_geometry_from_image_points(
        "151",
        image_points,
        image_url="https://example.test/miami.webp",
    )

    assert result.circuit_key == "151"
    assert result.circuit_id == "miami"
    assert result.image_url == "https://example.test/miami.webp"
    assert result.geometry_point_count == len(STATIC_TRACK_GEOMETRIES["151"]["points"])
    assert result.image_point_count == 2


def test_static_track_geometry_catalog_entries_have_valid_shapes() -> None:
    seen_aliases: set[str] = set()
    seen_circuit_ids: set[str] = set()

    for circuit_key, entry in STATIC_TRACK_GEOMETRIES.items():
        assert entry["circuit_key"] == circuit_key
        assert entry["circuit_id"]
        assert entry["circuit_id"] == entry["circuit_id"].lower()
        assert entry["circuit_id"] not in seen_circuit_ids
        assert (
            get_circuit_map_url(entry["circuit_id"], "2026")
            or get_circuit_outline_url(entry["circuit_id"], "2026")
        ) is not None
        seen_circuit_ids.add(entry["circuit_id"])
        assert entry["aliases"]
        assert isfinite(entry["rotation"])
        assert -180 <= entry["rotation"] <= 180
        assert len(entry["points"]) >= 50
        assert entry["points"][0] == entry["points"][-1]
        assert (0, 0) not in entry["points"]
        provenance = entry["provenance"]
        assert provenance["approval_status"] == (
            STATIC_TRACK_GEOMETRY_APPROVAL_VISUAL_APPROVED
        )
        assert provenance["catalog_version"] == STATIC_TRACK_GEOMETRY_CATALOG_VERSION
        assert provenance["geometry_source"] == "position_z_dump"
        assert provenance["position_stream"] == "Position.z"
        assert provenance["source_session"] == "Race"
        assert provenance["source_dump_path"].endswith("/Race")
        assert provenance["qa_artifact"] == STATIC_TRACK_GEOMETRY_QA_ARTIFACT
        for alias in entry["aliases"]:
            assert alias == alias.lower()
            assert alias not in seen_aliases
            seen_aliases.add(alias)


def test_static_track_geometry_provenance_can_be_looked_up() -> None:
    provenance = get_static_track_geometry_provenance(circuit_key="151")

    assert provenance is not None
    assert (
        provenance["approval_status"] == STATIC_TRACK_GEOMETRY_APPROVAL_VISUAL_APPROVED
    )
    assert provenance["source_dump_path"].endswith("/2025-05-02_Miami_Grand_Prix/Race")
    assert get_static_track_geometry_provenance(circuit_id="madring") is None


def test_static_track_geometry_qa_reports_calendar_coverage_gap() -> None:
    report = build_static_track_geometry_qa_report()

    assert "madring" in expected_2025_2026_catalog_circuit_ids()
    assert report.expected_count == 25
    assert report.catalog_count == 24
    assert report.missing_circuit_ids == ("madring",)
    assert report.unexpected_circuit_ids == ()

    miami = next(entry for entry in report.entries if entry.circuit_id == "miami")
    assert miami.status == STATUS_OK
    assert miami.circuit_key == "151"
    assert miami.point_count == len(STATIC_TRACK_GEOMETRIES["151"]["points"])
    assert miami.rotation == 11.2
    assert miami.image_source == "f1_detailed_map"
    assert miami.approval_status == STATIC_TRACK_GEOMETRY_APPROVAL_VISUAL_APPROVED
    assert miami.provenance is not None
    assert miami.provenance["catalog_version"] == STATIC_TRACK_GEOMETRY_CATALOG_VERSION

    madring = next(entry for entry in report.entries if entry.circuit_id == "madring")
    assert madring.status == STATUS_MISSING_CATALOG
    assert madring.point_count == 0
    assert madring.image_source == "f1_detailed_map"
    assert madring.approval_status is None
    assert madring.provenance is None


def test_static_track_geometry_qa_writes_artifacts(
    tmp_path,
) -> None:
    report = build_static_track_geometry_qa_report(
        expected_circuit_ids=("miami", "madring"),
        include_image_points=True,
        image_loader=lambda _: _qa_test_image_bytes(),
    )

    paths = write_static_track_geometry_qa_artifacts(
        report,
        output_dir=tmp_path,
        render=True,
        image_loader=lambda _: _qa_test_image_bytes(),
    )

    assert paths["json"].exists()
    assert paths["markdown"].exists()
    assert paths["overlay"].exists()
    assert "madring" in paths["markdown"].read_text(encoding="utf-8")
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["missing_circuit_ids"] == ["madring"]
    miami = next(
        entry for entry in payload["entries"] if entry["circuit_id"] == "miami"
    )
    assert miami["image_point_count"] > 0
    assert miami["approval_status"] == STATIC_TRACK_GEOMETRY_APPROVAL_VISUAL_APPROVED
    assert miami["provenance"]["source_dump_path"].endswith(
        "/2025-05-02_Miami_Grand_Prix/Race"
    )


def test_static_track_geometry_qa_overlay_can_render_subset(tmp_path) -> None:
    report = build_static_track_geometry_qa_report(
        expected_circuit_ids=("miami", "madring"),
    )
    output_path = tmp_path / "qa.png"

    rendered = render_static_track_geometry_qa_overlay(
        report,
        output_path=output_path,
        image_loader=lambda _: _qa_test_image_bytes(),
        columns=2,
        cell_width=220,
        cell_height=160,
    )

    assert rendered == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_static_track_geometry_maintenance_generates_missing_candidate(
    tmp_path,
) -> None:
    _write_dump_session(
        tmp_path,
        event_dir="2026-09-13_Madrid_Grand_Prix",
        circuit_key="999",
        circuit_short_name="Madrid",
        meeting_name="Madrid Grand Prix",
        circuit_id="madring",
    )

    sessions = scan_position_dump_sessions(
        tmp_path,
        expected_circuit_ids=("madring",),
    )

    assert len(sessions) == 1
    assert sessions[0].inferred_circuit_id == "madring"

    report = build_static_track_geometry_maintenance_report(
        dump_root=tmp_path,
        output_dir=tmp_path / "out",
        expected_circuit_ids=("madring",),
        image_loader=lambda _: _qa_test_image_bytes(),
        max_points=100,
    )

    assert report.expected_count == 1
    assert report.cataloged_count == 0
    assert report.candidate_count == 1
    assert report.missing_position_z_count == 0
    entry = report.entries[0]
    assert entry.status == MAINTENANCE_STATUS_CANDIDATE_READY
    assert entry.approval_status == STATIC_TRACK_GEOMETRY_APPROVAL_QA_PASSED
    assert entry.candidate is not None
    assert entry.candidate.circuit_key == "999"
    assert entry.candidate.circuit_id == "madring"
    assert entry.candidate.point_count == len(entry.candidate.points)
    assert entry.candidate.rotation is not None
    assert entry.candidate.provenance["visual_approved_at"] == ""
    assert entry.candidate.provenance["source_dump_path"].endswith("/Race")


def test_static_track_geometry_maintenance_writes_artifacts(tmp_path) -> None:
    _write_dump_session(
        tmp_path,
        event_dir="2026-09-13_Madrid_Grand_Prix",
        circuit_key="999",
        circuit_short_name="Madrid",
        meeting_name="Madrid Grand Prix",
        circuit_id="madring",
    )
    output_dir = tmp_path / "maintenance"
    report = build_static_track_geometry_maintenance_report(
        dump_root=tmp_path,
        output_dir=output_dir,
        expected_circuit_ids=("miami", "madring"),
        image_loader=lambda _: _qa_test_image_bytes(),
        max_points=100,
    )

    paths = write_static_track_geometry_maintenance_artifacts(
        report,
        output_dir=output_dir,
    )

    assert paths["json"].exists()
    assert paths["markdown"].exists()
    assert (output_dir / "candidates" / "madring.json").exists()
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["candidate_count"] == 1
    assert payload["missing_position_z_count"] == 0
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "madring" in markdown
    assert "candidate_ready" in markdown


def test_static_track_geometry_maintenance_reports_cataloged_and_missing(
    tmp_path,
) -> None:
    _write_dump_session(
        tmp_path,
        event_dir="2026-05-03_Miami_Grand_Prix",
        circuit_key="151",
        circuit_short_name="Miami",
        meeting_name="Miami Grand Prix",
    )

    report = build_static_track_geometry_maintenance_report(
        dump_root=tmp_path,
        expected_circuit_ids=("miami", "madring"),
    )

    by_id = {entry.circuit_id: entry for entry in report.entries}
    assert by_id["miami"].status == MAINTENANCE_STATUS_CATALOGED
    assert by_id["miami"].approval_status == (
        STATIC_TRACK_GEOMETRY_APPROVAL_VISUAL_APPROVED
    )
    assert by_id["madring"].status == MAINTENANCE_STATUS_MISSING_POSITION_Z
    assert report.missing_circuit_ids == ("madring",)


def test_static_track_geometry_builder_closes_near_loop_candidate() -> None:
    points = _representative_loop()
    points[-1] = (120, 100)
    lines = [
        _json_stream_line(
            _position_payload(
                {"1": {"Status": "OnTrack", "X": x, "Y": y, "Z": 0}},
                BASE + timedelta(seconds=index),
            ),
            f"00:00:{index:02}.000",
        )
        for index, (x, y) in enumerate(points)
    ]

    result = build_static_track_geometry_from_position_lines(
        lines,
        circuit_key="test",
        max_points=100,
    )

    assert result is not None
    assert result.circuit_key == "test"
    assert result.driver_count == 1
    assert result.sample_count == len(points)
    assert result.points[0] == result.points[-1]


def test_static_geometry_maintenance_edge_helpers(tmp_path, monkeypatch) -> None:
    """Offline catalog maintenance handles incomplete dumps without crashing."""
    dump = maintenance.StaticTrackGeometryDumpSession(
        root_path=str(tmp_path),
        position_file=str(tmp_path / "missing_Position.z.txt"),
        session_info_file=None,
        circuit_key=None,
        circuit_short_name=None,
        meeting_name=None,
        session_name=None,
        session_type=None,
        start_date=None,
        path=None,
        inferred_circuit_id=None,
    )
    assert dump.as_dict()["root_path"] == str(tmp_path)
    assert scan_position_dump_sessions(tmp_path / "absent") == ()

    practice = tmp_path / "Practice"
    practice.mkdir()
    (practice / "sample_Position.z.txt").write_text("", encoding="utf-8")
    assert (
        scan_position_dump_sessions(tmp_path, expected_circuit_ids=("madring",)) == ()
    )

    assert (
        maintenance._build_candidate_for_dump(
            "madring", dump, season="2026", image_loader=None, max_points=10
        )
        is None
    )
    keyed_dump = replace(dump, circuit_key="999")
    assert (
        maintenance._build_candidate_for_dump(
            "madring", keyed_dump, season="2026", image_loader=None, max_points=10
        )
        is None
    )

    empty_position = tmp_path / "empty_Position.z.txt"
    empty_position.write_text("invalid", encoding="utf-8")
    empty_dump = replace(keyed_dump, position_file=str(empty_position))
    assert (
        maintenance._build_candidate_for_dump(
            "madring", empty_dump, season="2026", image_loader=None, max_points=10
        )
        is None
    )

    assert maintenance._source_season(dump) is None
    direct = tmp_path / "sample_Position.z.txt"
    direct.write_text("", encoding="utf-8")
    session_info = tmp_path / "sample_SessionInfo.txt"
    session_info.write_text("URL: ignored\ninvalid\n", encoding="utf-8")
    assert maintenance._session_info_file_for_position_file(direct) == session_info
    assert maintenance._read_session_info_file(session_info) == {}
    assert maintenance._json_payload_from_stream_line("text without json") is None
    assert maintenance._session_circuit_metadata({"Meeting": {"Circuit": "bad"}}) == (
        None,
        None,
    )
    assert (
        maintenance._infer_circuit_id(
            circuit_key=None,
            circuit_short_name="Unknown",
            session_info={},
            position_file=direct,
            expected_circuit_ids=("madring",),
            season="2026",
        )
        is None
    )
    assert maintenance._best_dump_by_circuit_id((dump,)) == {}
    assert maintenance._text_or_none(None) is None

    monkeypatch.setattr(maintenance, "get_circuit_map_url", lambda *_: None)
    monkeypatch.setattr(
        maintenance,
        "get_circuit_outline_url",
        lambda *_: "https://outline.test/map.png",
    )
    assert maintenance._image_source_for_circuit("madring", "2026") == (
        maintenance.F1_OUTLINE_SOURCE,
        "https://outline.test/map.png",
    )
    monkeypatch.setattr(maintenance, "get_circuit_outline_url", lambda *_: None)
    assert maintenance._image_source_for_circuit("madring", "2026") == (None, None)

    monkeypatch.setattr(
        maintenance,
        "extract_track_points_from_image_bytes",
        lambda _data: ((0.0, 0.0), (1.0, 1.0)),
    )
    monkeypatch.setattr(
        maintenance,
        "presentation_rotation_from_image_points",
        lambda *_args: 12.34,
    )
    assert (
        maintenance._calibrate_candidate_rotation(
            ((0, 0), (1, 1)),
            image_source=maintenance.F1_OUTLINE_SOURCE,
            image_url="https://outline.test/map.png",
            image_loader=lambda _url: b"image",
        )
        == 12.3
    )

    class _DownloadResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return bytearray(b"image")

    monkeypatch.setattr(
        maintenance, "urlopen", lambda *_args, **_kwargs: _DownloadResponse()
    )
    assert maintenance._download_image("https://example.test/map.png") == b"image"


def test_static_geometry_maintenance_candidate_failure_report(
    tmp_path, monkeypatch
) -> None:
    dump = maintenance.StaticTrackGeometryDumpSession(
        root_path=str(tmp_path),
        position_file=str(tmp_path / "sample_Position.z.txt"),
        session_info_file=None,
        circuit_key="999",
        circuit_short_name="Madrid",
        meeting_name="Madrid Grand Prix",
        session_name="Race",
        session_type="Race",
        start_date="2026-09-13T13:00:00",
        path="2026/Madrid/Race",
        inferred_circuit_id="madring",
    )
    monkeypatch.setattr(
        maintenance, "scan_position_dump_sessions", lambda *_args, **_kwargs: (dump,)
    )
    monkeypatch.setattr(maintenance, "_catalog_by_circuit_id", lambda: {})
    monkeypatch.setattr(
        maintenance, "_build_candidate_for_dump", lambda *_args, **_kwargs: None
    )

    report = build_static_track_geometry_maintenance_report(
        dump_root=tmp_path,
        output_dir=tmp_path / "out",
        expected_circuit_ids=("madring",),
    )

    assert report.entries[0].status == maintenance.MAINTENANCE_STATUS_CANDIDATE_ERROR


def test_static_geometry_qa_review_and_image_edge_paths(monkeypatch) -> None:
    entry = {"circuit_key": "test", "rotation": 0, "points": ((0, 0), (1, 1))}
    image_source_for_circuit = geometry_qa._image_source_for_circuit
    monkeypatch.setattr(
        geometry_qa, "_image_source_for_circuit", lambda *_args: (None, None)
    )
    review = geometry_qa._qa_entry_for_circuit(
        "unknown",
        entry,
        season="2026",
        include_image_points=False,
        image_loader=None,
    )
    assert review.status == geometry_qa.STATUS_NEEDS_REVIEW
    assert len(review.issues) == 3

    monkeypatch.setattr(
        geometry_qa,
        "_image_source_for_circuit",
        lambda *_args: (geometry_qa.F1_OUTLINE_SOURCE, "https://example.test/map.png"),
    )
    image_error = geometry_qa._qa_entry_for_circuit(
        "unknown",
        entry,
        season="2026",
        include_image_points=True,
        image_loader=lambda _url: (_ for _ in ()).throw(RuntimeError("bad image")),
    )
    assert image_error.status == geometry_qa.STATUS_IMAGE_ERROR

    monkeypatch.setattr(
        geometry_qa, "_image_source_for_circuit", image_source_for_circuit
    )
    monkeypatch.setattr(geometry_qa, "get_circuit_map_url", lambda *_args: None)
    monkeypatch.setattr(
        geometry_qa,
        "get_circuit_outline_url",
        lambda *_args: "https://example.test/outline.png",
    )
    assert geometry_qa._image_source_for_circuit("unknown", "2026") == (
        geometry_qa.F1_OUTLINE_SOURCE,
        "https://example.test/outline.png",
    )
    monkeypatch.setattr(geometry_qa, "get_circuit_outline_url", lambda *_args: None)
    assert geometry_qa._image_source_for_circuit("unknown", "2026") == (None, None)

    monkeypatch.setattr(
        geometry_qa,
        "extract_track_points_from_image_bytes",
        lambda _data, **_kwargs: ((1.0, 2.0),),
    )
    assert geometry_qa._extract_image_points(
        lambda _url: b"image",
        "https://example.test/outline.png",
        geometry_qa.F1_OUTLINE_SOURCE,
    ) == ((1.0, 2.0),)
    assert (
        geometry_qa._load_image_points_for_entry(
            geometry_qa.StaticTrackGeometryQaEntry("unknown", geometry_qa.STATUS_OK),
            lambda _url: b"image",
        )
        == ()
    )
    broken_entry = geometry_qa.StaticTrackGeometryQaEntry(
        "unknown",
        geometry_qa.STATUS_OK,
        image_source=geometry_qa.F1_OUTLINE_SOURCE,
        image_url="https://example.test/outline.png",
    )
    assert (
        geometry_qa._load_image_points_for_entry(
            broken_entry,
            lambda _url: (_ for _ in ()).throw(RuntimeError("bad image")),
        )
        == ()
    )

    class _DownloadResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return bytearray(b"image")

    monkeypatch.setattr(
        geometry_qa, "urlopen", lambda *_args, **_kwargs: _DownloadResponse()
    )
    assert geometry_qa._download_image("https://example.test/map.png") == b"image"


def test_static_geometry_builder_rejects_empty_and_unbounded_points(
    monkeypatch,
) -> None:
    from custom_components.f1_sensor import track_map_static_geometry_builder as builder

    assert builder._close_static_track_points(()) is None
    assert builder._bounds_from_points(()) is None
    monkeypatch.setattr(builder, "_bounds_from_points", lambda _points: None)
    assert builder._close_static_track_points(((0, 0), (1, 1))) is None


def test_static_track_geometry_builder_rejects_open_candidate() -> None:
    lines = [
        _json_stream_line(
            _position_payload(
                {
                    "1": {
                        "Status": "OnTrack",
                        "X": 100 + (index * 1000),
                        "Y": 100,
                        "Z": 0,
                    }
                },
                BASE + timedelta(seconds=index),
            ),
            f"00:00:{index:02}.000",
        )
        for index in range(12)
    ]

    assert (
        build_static_track_geometry_from_position_lines(
            lines,
            circuit_key="test",
            max_points=100,
        )
        is None
    )
