"""Rebuild reviewed 2025 and Singapore 2026 track annotations.

The corner coordinates below are rounded positions from the season-specific
MultiViewer circuit API. FIA event maps supply the feature locations and
distances. The generated coordinates are snapped to our static centreline;
this script is an offline QA tool and is never used by Home Assistant.
"""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
GEOMETRIES = runpy.run_path(
    str(ROOT / "custom_components/f1_sensor/track_map_static_geometry.py")
)["STATIC_TRACK_GEOMETRIES"]
FINGERPRINT = runpy.run_path(
    str(ROOT / "custom_components/f1_sensor/track_map_annotation_contract.py")
)["geometry_fingerprint"]
PILOT_CATALOG = runpy.run_path(
    str(ROOT / "quality/track_map_annotation_calibration.py")
)["build_catalog"]
CATALOG = ROOT / "custom_components/f1_sensor/track_map_annotation_catalog.json"

SOURCES = {
    "2": {
        "layout": "silverstone_2025",
        "length_m": 5891,
        "map": "https://www.fia.com/system/files/decision-document/2025_british_grand_prix_-_event_notes_-_circuit_map_v2.pdf",
        "coordinates": "https://api.multiviewer.app/api/v1/circuits/2/2025",
        "corners": (
            (1, 1193, 4504),
            (2, 2770, 4463),
            (3, 4845, 5895),
            (4, 5803, 4734),
            (5, 6232, 6459),
            (6, 631, 10910),
            (7, -566, 9540),
            (8, 761, 12362),
            (9, 5894, 12947),
            (10, 7296, 7780),
            (11, 7535, 6906),
            (12, 7337, 5475),
            (13, 7776, 4164),
            (14, 6807, 3147),
            (15, 2399, -4099),
            (16, -620, -994),
            (17, -1438, -1147),
            (18, -2309, -106),
        ),
        # The FIA start arrow is at M18.7, upstream of the separate control
        # line at M18.1. It intersects the static segment from index 7 to 8.
        "start_position": (7, 0.38),
        "sectors": (("s1", "S1", 6, -110), ("s2", "S2", 14, 50)),
        "speed_traps": (("speed_trap", "Speed trap", 15, -140),),
        "detection_zones": (
            ("drs_d1", "DRS D1", 3, -25),
            ("drs_d2", "DRS D2", 11, 0),
            ("drs_a1", "DRS A1", 5, 30),
            ("drs_a2", "DRS A2", 14, 0),
        ),
    },
    "61": {
        "layout": "marina_bay_post_2023",
        "length_m": 4927,
        "map": "https://www.fia.com/system/files/decision-document/2025_singapore_grand_prix_-_event_notes_-_circuit_map_pit_lane_emergency_exits_map_and_quarantine_zone.pdf",
        "coordinates": "https://api.multiviewer.app/api/v1/circuits/61/2025",
        "corners": (
            (1, 431, 3477),
            (2, -195, 3722),
            (3, -780, 4086),
            (4, -1000, 2763),
            (5, -704, 290),
            (6, -4914, 446),
            (7, -8210, 2142),
            (8, -9608, 545),
            (9, -11035, 1643),
            (10, -13198, -1884),
            (11, -12225, -3009),
            (12, -11973, -3759),
            (13, -10795, -4904),
            (14, -9087, 76),
            (15, -7370, -1290),
            (16, -2544, -1748),
            (17, -2205, -2401),
            (18, 387, -2658),
            (19, 1137, -1840),
        ),
        "sectors": (("s1", "S1", 7, -150), ("s2", "S2", 14, -140)),
        "speed_traps": (("speed_trap", "Speed trap", 1, -150),),
        "detection_zones": (
            ("drs_d1", "DRS D1", 4, 0),
            ("drs_d2", "DRS D2", 13, -102),
            ("drs_d3", "DRS D3", 17, 105),
            ("drs_a1", "DRS A1", 5, 48),
            ("drs_a2", "DRS A2", 13, 78),
            ("drs_a3", "DRS A3", 14, 100),
            # The map says only "Exit T19" for A4, so there is no exact
            # distance to place it on the simplified static geometry.
        ),
    },
}

SINGAPORE_2026_MAP = (
    "https://www.fia.com/system/files/decision-document/"
    "2026_singapore_grand_prix_-_competition_notes_-_circuit_map_"
    "pit_lane_drawing_and_emergency_exits_map.pdf"
)

# FIA Singapore 2026 circuit map V2, issued 7 October 2026. The published
# overtake detection location is only "Entry T17"; it has no measurable offset
# on our simplified centreline, so that point is deliberately omitted.
# Straight Mode normal- and low-grip activation points are kept distinct.
SINGAPORE_2026_AERO_POINTS = (
    ("ot_a", "OT A", 17, 30),
    ("sm_a1_n", "SM A1 N", 19, 30),
    ("sm_a1_l", "SM A1 L", 19, 90),
    ("sm_a2_n", "SM A2 N", 5, 50),
    ("sm_a3_n", "SM A3 N", 9, 70),
    ("sm_a3_l", "SM A3 L", 9, 120),
    ("sm_a4_n", "SM A4 N", 13, 115),
    ("sm_a4_l", "SM A4 L", 13, 165),
    ("sm_a5_n", "SM A5 N", 15, 70),
    ("sm_a5_l", "SM A5 L", 15, 90),
)


def _segments(points):
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:], strict=False)]
    cumulative = [0.0]
    for length in lengths:
        cumulative.append(cumulative[-1] + length)
    return lengths, cumulative


def _nearest(points, target, lengths, cumulative):
    best = None
    for index, (a, b) in enumerate(zip(points, points[1:], strict=False)):
        dx, dy = b[0] - a[0], b[1] - a[1]
        fraction = max(
            0.0,
            min(
                1.0,
                ((target[0] - a[0]) * dx + (target[1] - a[1]) * dy)
                / (lengths[index] ** 2),
            ),
        )
        position = (a[0] + fraction * dx, a[1] + fraction * dy)
        distance = math.dist(position, target)
        if best is None or distance < best[0]:
            best = (distance, cumulative[index] + fraction * lengths[index], position)
    return best


def _at(points, lengths, cumulative, distance):
    distance %= cumulative[-1]
    for index, length in enumerate(lengths):
        if distance <= cumulative[index + 1]:
            fraction = (distance - cumulative[index]) / length
            a, b = points[index : index + 2]
            center = (a[0] + fraction * (b[0] - a[0]), a[1] + fraction * (b[1] - a[1]))
            normal = (-(b[1] - a[1]) / length, (b[0] - a[0]) / length)
            return center, normal
    raise AssertionError("unreachable distance")


def _line(points, lengths, cumulative, distance, label, item_id):
    center, normal = _at(points, lengths, cumulative, distance)
    half_width = 220
    return {
        "id": item_id,
        "kind": "line",
        "start": [round(center[i] - half_width * normal[i]) for i in range(2)],
        "end": [round(center[i] + half_width * normal[i]) for i in range(2)],
        "label": label,
    }


def _point(points, lengths, cumulative, distance, label, item_id):
    center, _ = _at(points, lengths, cumulative, distance)
    return {
        "id": item_id,
        "kind": "point",
        "anchor": [round(value) for value in center],
        "label": label,
        "label_offset": [3, -4],
    }


def _singapore_2026_records(records):
    """Bind FIA 2026 markings to the reviewed, unchanged Marina Bay geometry."""
    source = {
        "url": SINGAPORE_2026_MAP,
        "coordinate_url": "https://api.multiviewer.app/api/v1/circuits/61/2026",
        "checked_on": "2026-10-10",
    }
    reviewed = [
        deepcopy(record)
        for record in records
        if record["circuit_key"] == "61" and record["valid_from_season"] == 2025
    ]
    for record in reviewed:
        record["valid_from_season"] = 2026
        record["valid_to_season"] = 2026
        record["source"] = source

    track = GEOMETRIES["61"]
    points = track["points"]
    lengths, cumulative = _segments(points)
    scale = cumulative[-1] / 4927
    corner_arcs = {
        number: _nearest(points, (x, y), lengths, cumulative)[1]
        for number, x, y in SOURCES["61"]["corners"]
    }
    corners = next(record for record in reviewed if record["layer"] == "corners")
    previous_offsets = {
        int(item["label"]): item["label_offset"] for item in corners["items"]
    }
    corners["items"] = [
        {
            **_point(
                points,
                lengths,
                cumulative,
                corner_arcs[number],
                str(number),
                f"turn_{number:02d}",
            ),
            "label_offset": previous_offsets[number],
        }
        for number, _, _ in SOURCES["61"]["corners"]
    ]
    aero = next(record for record in reviewed if record["layer"] == "detection_zones")
    aero["items"] = [
        _point(
            points,
            lengths,
            cumulative,
            corner_arcs[corner] + offset_m * scale,
            label,
            item_id,
        )
        for item_id, label, corner, offset_m in SINGAPORE_2026_AERO_POINTS
    ]
    return reviewed


def build_catalog():
    """Return the reviewed season-specific layers for both 2025 and 2026."""
    pilot = PILOT_CATALOG(qa_status="verified", rights_status="cleared")
    records = list(pilot)
    for circuit_key, source in SOURCES.items():
        track = GEOMETRIES[circuit_key]
        points = track["points"]
        lengths, cumulative = _segments(points)
        scale = cumulative[-1] / source["length_m"]
        corner_arcs = {}
        for number, x, y in source["corners"]:
            gap, arc, _ = _nearest(points, (x, y), lengths, cumulative)
            if gap > 500:
                raise ValueError(
                    f"{circuit_key} T{number} is too far from geometry: {gap:.0f}"
                )
            corner_arcs[number] = arc
        common = {
            "schema_version": 1,
            "circuit_key": circuit_key,
            "layout_key": source["layout"],
            "valid_from_season": 2025,
            "valid_to_season": 2025,
            "geometry_fingerprint": FINGERPRINT(track),
            "qa_status": "verified",
            "rights_status": "cleared",
            "source": {
                "url": source["map"],
                "coordinate_url": source["coordinates"],
                "checked_on": "2026-10-10",
            },
        }
        if circuit_key == "2":
            index, fraction = source["start_position"]
            start_arc = cumulative[index] + fraction * lengths[index]
            records.extend(
                [
                    {
                        **common,
                        "layer": "start_finish",
                        "items": [
                            _line(
                                points,
                                lengths,
                                cumulative,
                                start_arc,
                                "Start/finish",
                                "start_finish",
                            )
                        ],
                    },
                    {
                        **common,
                        "layer": "corners",
                        "items": [
                            _point(
                                points,
                                lengths,
                                cumulative,
                                corner_arcs[number],
                                str(number),
                                f"turn_{number:02d}",
                            )
                            for number in range(1, 19)
                        ],
                    },
                ]
            )
        for layer in ("sectors", "speed_traps", "detection_zones"):
            items = []
            for item_id, label, corner, offset_m in source[layer]:
                arc = corner_arcs[corner] + offset_m * scale
                if layer == "sectors":
                    items.append(
                        _line(points, lengths, cumulative, arc, label, item_id)
                    )
                else:
                    items.append(
                        _point(points, lengths, cumulative, arc, label, item_id)
                    )
            records.append({**common, "layer": layer, "items": items})
    return records + _singapore_2026_records(records)


if __name__ == "__main__":
    CATALOG.write_text(json.dumps(build_catalog(), indent=2) + "\n", encoding="utf-8")
