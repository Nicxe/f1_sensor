"""Static QA for reviewed season-specific track annotation catalog entries."""

from copy import deepcopy
import json
from math import dist
from pathlib import Path

from custom_components.f1_sensor.track_map_annotation_contract import (
    annotation_context,
    bind_annotation_layers,
    geometry_fingerprint,
)
from custom_components.f1_sensor.track_map_static_geometry import (
    STATIC_TRACK_GEOMETRIES,
)

CATALOG_PATH = Path(__file__).resolve().parents[1] / "track_map_annotation_catalog.json"


def _catalog() -> list[dict]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _records(circuit_key: str, season: int = 2025) -> list[dict]:
    return [
        record
        for record in _catalog()
        if record["circuit_key"] == circuit_key
        and record["valid_from_season"] == season
    ]


def _track() -> dict:
    return STATIC_TRACK_GEOMETRIES["61"]


def _context(track: dict | None = None):
    return annotation_context(
        entry_id="test-entry",
        session={
            "session_key": "9896",
            "circuit_key": "61",
            "path": "2025/2025-10-05_Singapore_Grand_Prix/2025-10-05_Race/",
            "start_date": "2025-10-05T20:00:00",
        },
        track=track or _track(),
        source="replay",
        session_generation=1,
        replay_year=2025,
    )


def test_catalog_has_five_geometry_bound_layers_per_reviewed_2025_layout() -> None:
    catalog = _catalog()
    assert len(catalog) == 15
    for circuit_key, season, layout in (
        ("61", 2025, "marina_bay_post_2023"),
        ("2", 2025, "silverstone_2025"),
        ("61", 2026, "marina_bay_post_2023"),
    ):
        records = _records(circuit_key, season)
        track = STATIC_TRACK_GEOMETRIES[circuit_key]
        expected_fingerprint = geometry_fingerprint(track)
        assert {record["layer"] for record in records} == {
            "start_finish",
            "corners",
            "sectors",
            "speed_traps",
            "detection_zones",
        }
        assert all(record["layout_key"] == layout for record in records)
        assert all(record["valid_from_season"] == season for record in records)
        assert all(record["valid_to_season"] == season for record in records)
        assert all(
            record["geometry_fingerprint"] == expected_fingerprint for record in records
        )
        assert all(
            record["source"]["url"].startswith("https://www.fia.com/")
            for record in records
        )
        assert all(record["qa_status"] == "verified" for record in records)
        assert all(record["rights_status"] == "cleared" for record in records)
    assert len(json.dumps(catalog, separators=(",", ":")).encode()) <= 18_000


def test_singapore_2026_binds_only_to_its_verified_year_and_geometry() -> None:
    track = _track()
    records = _records("61", 2026)
    assert len(records) == 5
    assert {record["source"]["checked_on"] for record in records} == {"2026-10-10"}
    assert all(
        "2026_singapore_grand_prix" in record["source"]["url"] for record in records
    )
    assert all(
        record["source"]["coordinate_url"].endswith("/61/2026") for record in records
    )
    for year in (2025, 2026, 2027):
        context = annotation_context(
            entry_id="test-entry",
            session={
                "session_key": f"singapore-{year}",
                "circuit_key": "61",
                "path": f"{year}/{year}-10-10_Singapore_Grand_Prix/Sprint/",
                "start_date": f"{year}-10-10T20:00:00",
            },
            track=track,
            source="replay",
            session_generation=year,
            replay_year=year,
        )
        bound = bind_annotation_layers(records, context, segment_count=90)
        if year == 2026:
            assert bound is not None
            assert {layer["layer"] for layer in bound["layers"]} == {
                "start_finish",
                "corners",
                "sectors",
                "speed_traps",
                "detection_zones",
            }
        else:
            assert bound is None
    changed = {**track, "rotation": track["rotation"] + 1}
    context = annotation_context(
        entry_id="test-entry",
        session={
            "session_key": "singapore-2026",
            "circuit_key": "61",
            "path": "2026/2026-10-10_Singapore_Grand_Prix/Sprint/",
            "start_date": "2026-10-10T20:00:00",
        },
        track=changed,
        source="replay",
        session_generation=1,
        replay_year=2026,
    )
    assert bind_annotation_layers(records, context, segment_count=90) is None


def test_singapore_pilot_corners_remain_stable() -> None:
    records = _records("61")
    track = _track()
    assert len(records) == 5
    assert all(
        record["geometry_fingerprint"] == geometry_fingerprint(track)
        for record in records
    )


def test_corners_are_unique_ordered_and_on_the_calibrated_raw_geometry() -> None:
    corners = next(record for record in _records("61") if record["layer"] == "corners")
    items = corners["items"]
    points = list(_track()["points"][:-1])
    assert [item["label"] for item in items] == [str(number) for number in range(1, 20)]
    assert [item["id"] for item in items] == [
        f"turn_{number:02d}" for number in range(1, 20)
    ]
    assert all(item["kind"] == "point" for item in items)
    indexes = [points.index(tuple(item["anchor"])) for item in items]
    assert len(indexes) == len(set(indexes))
    unwrapped = [indexes[0]]
    for index in indexes[1:]:
        while index <= unwrapped[-1]:
            index += len(points)
        unwrapped.append(index)
    assert unwrapped[-1] - unwrapped[0] < len(points)
    assert all(
        all(-10 <= value <= 10 for value in item["label_offset"]) for item in items
    )


def test_start_line_is_perpendicular_to_forward_travel_at_m_zero() -> None:
    record = next(
        record for record in _records("61") if record["layer"] == "start_finish"
    )
    item = record["items"][0]
    points = _track()["points"]
    before, center, after = points[46:49]
    start, end = item["start"], item["end"]
    midpoint = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2]
    assert item["kind"] == "line"
    assert dist(midpoint, center) <= 1
    assert 400 <= dist(start, end) <= 500
    tangent = (after[0] - before[0], after[1] - before[1])
    line = (end[0] - start[0], end[1] - start[1])
    assert abs(tangent[0] * line[0] + tangent[1] * line[1]) < 500
    assert midpoint != list(points[45])  # The FIA map shows a separate control line.


def test_captured_replay_samples_cross_start_line_in_forward_order() -> None:
    """Two local Race replay positions straddle the reviewed start line."""
    item = next(
        record for record in _records("61") if record["layer"] == "start_finish"
    )["items"][0]
    start, end = item["start"], item["end"]
    before, after = (661, 1112), (551, 1893)

    def side(point: tuple[int, int]) -> int:
        return (end[0] - start[0]) * (point[1] - start[1]) - (end[1] - start[1]) * (
            point[0] - start[0]
        )

    points = _track()["points"][:-1]

    def nearest(position: tuple[int, int]) -> int:
        return min(range(len(points)), key=lambda index: dist(position, points[index]))

    assert side(before) > 0 > side(after)
    assert (nearest(before), nearest(after)) == (47, 48)


def test_source_qa_and_rights_gate_allow_approved_layers() -> None:
    records = _records("61")
    context = _context()
    assert context is not None
    assert all(record["qa_status"] == "verified" for record in records)
    assert all(record["rights_status"] == "cleared" for record in records)
    assert all(
        record["source"]["url"].startswith("https://www.fia.com/") for record in records
    )
    assert {record["source"]["checked_on"] for record in records} == {
        "2026-10-09",
        "2026-10-10",
    }
    bound = bind_annotation_layers(records, context, segment_count=90)
    assert bound is not None
    assert {record["layer"] for record in bound["layers"]} == {
        "corners",
        "start_finish",
        "sectors",
        "speed_traps",
        "detection_zones",
    }
    pending = deepcopy(records)
    for record in pending:
        record["rights_status"] = "pending"
    assert bind_annotation_layers(pending, context, segment_count=90) is None


def test_pilot_catalog_cannot_bind_to_changed_geometry_or_layout_year() -> None:
    cleared = _catalog()
    changed = dict(_track())
    changed["rotation"] = changed["rotation"] + 1
    assert bind_annotation_layers(cleared, _context(changed), segment_count=90) is None
    old_session = {
        "session_key": "old",
        "circuit_key": "61",
        "path": "2022/2022-10-02_Singapore_Grand_Prix/2022-10-02_Race/",
        "start_date": "2022-10-02T20:00:00",
    }
    old_context = annotation_context(
        entry_id="test-entry",
        session=old_session,
        track=_track(),
        source="replay",
        session_generation=2,
        replay_year=2022,
    )
    assert bind_annotation_layers(cleared, old_context, segment_count=90) is None


def _arc_at(track: dict, target: tuple[float, float]) -> tuple[float, float]:
    points = track["points"]
    traversed = 0.0
    best = (float("inf"), 0.0)
    for start, end in zip(points, points[1:], strict=False):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = dist(start, end)
        fraction = max(
            0.0,
            min(
                1.0,
                ((target[0] - start[0]) * dx + (target[1] - start[1]) * dy) / length**2,
            ),
        )
        projected = (start[0] + fraction * dx, start[1] + fraction * dy)
        best = min(best, (dist(target, projected), traversed + fraction * length))
        traversed += length
    return best[1], traversed


def _mark_position(item: dict) -> tuple[float, float]:
    if item["kind"] == "line":
        return tuple(
            (start + end) / 2
            for start, end in zip(item["start"], item["end"], strict=True)
        )
    return tuple(item["anchor"])


def test_verified_sector_and_trap_marks_follow_fia_distances_in_lap_order() -> None:
    source_corners = {
        "2": {6: (631, 10910), 14: (6807, 3147), 15: (2399, -4099)},
        "61": {1: (431, 3477), 7: (-8210, 2142), 14: (-9087, 76)},
    }
    expected = {
        "2": (
            ("sectors", "S1", 6, -110),
            ("sectors", "S2", 14, 50),
            ("speed_traps", "Speed trap", 15, -140),
        ),
        "61": (
            ("sectors", "S1", 7, -150),
            ("sectors", "S2", 14, -140),
            ("speed_traps", "Speed trap", 1, -150),
        ),
    }
    for circuit_key, marks in expected.items():
        track = STATIC_TRACK_GEOMETRIES[circuit_key]
        records = {record["layer"]: record for record in _records(circuit_key)}
        official_length = 5891 if circuit_key == "2" else 4927
        for layer, label, corner, offset_m in marks:
            item = next(
                item for item in records[layer]["items"] if item["label"] == label
            )
            position, total = _arc_at(track, _mark_position(item))
            corner_position, _ = _arc_at(track, source_corners[circuit_key][corner])
            measured = (position - corner_position + total / 2) % total - total / 2
            assert abs(measured / total * official_length - offset_m) < 2


def test_silverstone_corners_are_ordered_and_match_only_the_2025_layout() -> None:
    records = _records("2")
    corners = next(record for record in records if record["layer"] == "corners")
    assert [item["label"] for item in corners["items"]] == [
        str(number) for number in range(1, 19)
    ]
    track = STATIC_TRACK_GEOMETRIES["2"]
    arcs = [_arc_at(track, tuple(item["anchor"]))[0] for item in corners["items"]]
    total = _arc_at(track, (0, 0))[1]
    assert all(
        0 < (right - left) % total < total / 3
        for left, right in zip(arcs, arcs[1:], strict=False)
    )
    session = {
        "session_key": "british-race",
        "circuit_key": "2",
        "path": "2025/2025-07-06_British_Grand_Prix/2025-07-06_Race/",
        "start_date": "2025-07-06T15:00:00",
    }
    context = annotation_context(
        entry_id="test-entry",
        session=session,
        track=track,
        source="replay",
        session_generation=4,
        replay_year=2025,
    )
    bound = bind_annotation_layers(_catalog(), context, segment_count=90)
    assert bound is not None
    assert len(bound["layers"]) == 5
    for mismatched in (
        {
            **session,
            "path": "2024/2024-07-07_British_Grand_Prix/2024-07-07_Race/",
            "start_date": "2024-07-07",
        },
        {**session, "circuit_key": "61"},
    ):
        bad = annotation_context(
            entry_id="test-entry",
            session=mismatched,
            track=track,
            source="replay",
            session_generation=4,
            replay_year=int(mismatched["path"][:4]),
        )
        assert bind_annotation_layers(_catalog(), bad, segment_count=90) is None


def test_speed_traps_are_locations_and_singapore_drs_coverage_is_partial() -> None:
    for circuit_key in ("2", "61"):
        speed = next(
            record
            for record in _records(circuit_key)
            if record["layer"] == "speed_traps"
        )
        assert len(speed["items"]) == 1
        assert set(speed["items"][0]) == {
            "id",
            "kind",
            "anchor",
            "label",
            "label_offset",
        }
    drs = next(
        record for record in _records("61") if record["layer"] == "detection_zones"
    )
    assert [item["label"] for item in drs["items"]] == [
        "DRS D1",
        "DRS D2",
        "DRS D3",
        "DRS A1",
        "DRS A2",
        "DRS A3",
    ]


def test_singapore_2026_uses_fia_overtake_and_straight_mode_positions() -> None:
    reviewed_2025 = {record["layer"]: record for record in _records("61")}
    reviewed_2026 = {record["layer"]: record for record in _records("61", 2026)}
    for layer in ("start_finish", "sectors", "speed_traps"):
        assert reviewed_2026[layer]["items"] == reviewed_2025[layer]["items"]
    corners = reviewed_2026["corners"]["items"]
    assert [item["label"] for item in corners] == [
        str(number) for number in range(1, 20)
    ]
    for number, coordinate in ((4, (-1000, 2763)), (6, (-4914, 446))):
        assert dist(corners[number - 1]["anchor"], coordinate) < 50

    # FIA 2026 map V2 lists the distances from the named turns. "Entry T17"
    # has no numeric offset, and A2 low-grip is N/A, so neither is invented.
    expected = (
        ("OT A", 17, 30, (-2205, -2401)),
        ("SM A1 N", 19, 30, (1137, -1840)),
        ("SM A1 L", 19, 90, (1137, -1840)),
        ("SM A2 N", 5, 50, (-704, 290)),
        ("SM A3 N", 9, 70, (-11035, 1643)),
        ("SM A3 L", 9, 120, (-11035, 1643)),
        ("SM A4 N", 13, 115, (-10795, -4904)),
        ("SM A4 L", 13, 165, (-10795, -4904)),
        ("SM A5 N", 15, 70, (-7370, -1290)),
        ("SM A5 L", 15, 90, (-7370, -1290)),
    )
    items = reviewed_2026["detection_zones"]["items"]
    assert [item["label"] for item in items] == [entry[0] for entry in expected]
    assert all("DRS" not in item["label"] for item in items)
    track = _track()
    for item, (_, corner, metres, coordinate) in zip(items, expected, strict=True):
        position, total = _arc_at(track, _mark_position(item))
        corner_position, _ = _arc_at(track, coordinate)
        measured = (position - corner_position + total / 2) % total - total / 2
        assert abs(measured / total * 4927 - metres) < 2, (item["label"], corner)
