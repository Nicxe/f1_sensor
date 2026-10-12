"""Rebuild the reviewed 2025 pilot and 2026 track annotations.

The 2025 pilot corner coordinates below are manually reviewed. Most 2026 corner
coordinates come from the checked-in circuit API snapshot. Sepang and Madring
use checked-in anchors aligned from their published centrelines. FIA event maps
supply feature locations and distances. Generated coordinates are snapped to
our static centreline. This offline QA tool is never used by Home Assistant.
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
COORDINATE_SNAPSHOT = ROOT / "quality/track_map_2026_coordinate_snapshot.json"
BASELINE_COORDINATE_SNAPSHOT = (
    ROOT / "quality/track_map_2025_coordinate_baseline_snapshot.json"
)

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

# Feature positions are measured from the 2026 FIA circuit data tables. Each
# tuple is (id, label, corner number, metres from the corner). FIA points that
# are specified only as entry/apex/exit are omitted because this centreline is
# simplified and cannot represent those positions precisely.
SEASON_2026 = {
    "10": {
        "layout": "albert_park_2026",
        "length_m": 5278,
        "map": "https://www.fia.com/system/files/decision-document/2026_australian_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_quarantine_zone.pdf",
        "sectors": (("s1", "S1", 6, -120), ("s2", "S2", 9, -140)),
        "speed": (1, -120),
        "zones": (
            ("ot_d1", "OT D", 13, 15),
            ("ot_a1", "OT A", 14, 50),
            ("sm_a1_n", "SM A1 N", 14, 50),
            ("sm_a1_l", "SM A1 L", 14, 100),
            ("sm_a2_n", "SM A2 N", 2, 45),
            ("sm_a3_n", "SM A3 N", 5, 85),
            ("sm_a3_l", "SM A3 L", 5, 125),
            ("sm_a4_n", "SM A4 N", 8, 35),
            ("sm_a5_n", "SM A5 N", 10, 60),
        ),
    },
    "49": {
        "layout": "shanghai_2026",
        "length_m": 5451,
        "map": "https://www.fia.com/system/files/decision-document/2026_chinese_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_battery_containment_area_and_red_zone.pdf",
        "sectors": (("s1", "S1", 6, -150), ("s2", "S2", 11, -145)),
        "speed": (14, -240),
        "zones": (
            ("ot_a1", "OT A", 16, 100),
            ("sm_a1_n", "SM A1 N", 16, 100),
            ("sm_a1_l", "SM A1 L", 16, 150),
            ("sm_a2_n", "SM A2 N", 4, 60),
            ("sm_a2_l", "SM A2 L", 4, 100),
            ("sm_a3_n", "SM A3 N", 10, 100),
            ("sm_a3_l", "SM A3 L", 10, 140),
            ("sm_a4_n", "SM A4 N", 13, 60),
            ("sm_a4_l", "SM A4 L", 13, 130),
        ),
    },
    "46": {
        "layout": "suzuka_2026",
        "length_m": 5807,
        "map": "https://www.fia.com/system/files/decision-document/2026_japanese_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_battery_containment_area_and_red_zone.pdf",
        "sectors": (("s1", "S1", 8, -110), ("s2", "S2", 15, -270)),
        "speed": (15, 70),
        "zones": (("sm_a1_l", "SM A1 L", 18, 100), ("sm_a2_n", "SM A2 N", 14, 70)),
    },
    "151": {
        "layout": "miami_2026",
        "length_m": 5412,
        "map": "https://www.fia.com/system/files/decision-document/2026_miami_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_red_zone.pdf",
        "sectors": (("s1", "S1", 8, 110), ("s2", "S2", 16, 70)),
        "speed": (17, -150),
        "zones": (
            ("ot_d1", "OT D", 17, 20),
            ("ot_a1", "OT A", 18, 10),
            ("sm_a1_n", "SM A1 N", 8, 165),
            ("sm_a3_n", "SM A3 N", 16, 90),
            ("sm_a3_l", "SM A3 L", 16, 150),
        ),
    },
    "23": {
        "layout": "montreal_2026",
        "length_m": 4361,
        "map": "https://www.fia.com/system/files/decision-document/2026_canadian_grand_prix_-_competition_notes_-_circuit_map_v2.pdf",
        "sectors": (("s1", "S1", 6, -150), ("s2", "S2", 10, -190)),
        "speed": (13, -250),
        "zones": (
            ("ot_a1", "OT A", 13, 70),
            ("sm_a1_n", "SM A1 N", 14, 100),
            ("sm_a1_l", "SM A1 L", 14, 160),
            ("sm_a2_n", "SM A2 N", 7, 50),
            ("sm_a2_l", "SM A2 L", 7, 110),
            ("sm_a3_n", "SM A3 N", 9, 60),
            ("sm_a4_n", "SM A4 N", 11, 30),
            ("sm_a4_l", "SM A4 L", 11, 120),
        ),
    },
    "22": {
        "layout": "monaco_2026",
        "length_m": 3337,
        "map": "https://www.fia.com/system/files/decision-document/2026_monaco_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_red_zone.pdf",
        "sectors": (("s1", "S1", 5, -60), ("s2", "S2", 13, -70)),
        "speed": (10, -190),
        "zones": (("ot_d1", "OT D", 16, 80), ("ot_a1", "OT A", 18, 40)),
    },
    "15": {
        "layout": "barcelona_catalunya_2026",
        "length_m": 4657,
        "map": "https://www.fia.com/system/files/decision-document/2026_barcelona-catalunya_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_and_emergency_exits_map.pdf",
        "sectors": (("s1", "S1", 4, -50), ("s2", "S2", 10, -90)),
        "speed": (1, -220),
        "zones": (
            ("sm_a1_n", "SM A1 N", 14, 45),
            ("sm_a1_l", "SM A1 L", 14, 85),
            ("sm_a3_n", "SM A3 N", 5, 90),
            ("sm_a3_l", "SM A3 L", 5, 90),
            ("sm_a4_n", "SM A4 N", 9, 40),
            ("sm_a4_l", "SM A4 L", 9, 90),
        ),
    },
    "19": {
        "layout": "spielberg_2026",
        "length_m": 4326,
        "map": "https://www.fia.com/system/files/decision-document/2026_austrian_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_red_zone.pdf",
        "sectors": (("s1", "S1", 3, -170), ("s2", "S2", 7, -60)),
        "speed": (4, -170),
        "zones": (
            ("ot_d1", "OT D", 10, -50),
            ("ot_a1", "OT A", 10, 110),
            ("sm_a1_n", "SM A1 N", 10, 110),
            ("sm_a1_l", "SM A1 L", 10, 160),
            ("sm_a2_n", "SM A2 N", 1, 110),
            ("sm_a2_l", "SM A2 L", 1, 170),
            ("sm_a3_n", "SM A3 N", 3, 90),
            ("sm_a3_l", "SM A3 L", 3, 160),
            ("sm_a4_n", "SM A4 N", 8, 10),
            ("sm_a4_l", "SM A4 L", 8, 60),
        ),
    },
    "2": {
        "layout": "silverstone_2026",
        "length_m": 5891,
        "map": "https://www.fia.com/system/files/decision-document/2026_british_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_red_zone.pdf",
        "sectors": (("s1", "S1", 6, -110), ("s2", "S2", 14, 50)),
        "speed": (15, -140),
        "zones": (
            ("ot_a1", "OT A", 17, 95),
            ("sm_a1_n", "SM A1 N", 18, 65),
            ("sm_a1_l", "SM A1 L", 18, 115),
            ("sm_a2_n", "SM A2 N", 5, 55),
            ("sm_a2_l", "SM A2 L", 5, 115),
            ("sm_a3_n", "SM A3 N", 7, 155),
            ("sm_a4_n", "SM A4 N", 14, 65),
            ("sm_a4_l", "SM A4 L", 14, 125),
        ),
    },
    "7": {
        "layout": "spa_2026",
        "length_m": 7004,
        "map": "https://www.fia.com/system/files/decision-document/2026_belgian_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_red_zone.pdf",
        "sectors": (("s1", "S1", 5, -150), ("s2", "S2", 15, -50)),
        "speed": (4, 30),
        "zones": (
            ("ot_a1", "OT A", 19, 130),
            ("sm_a1_n", "SM A1 N", 19, 190),
            ("sm_a1_l", "SM A1 L", 19, 240),
            ("sm_a2_n", "SM A2 N", 1, 140),
            ("sm_a2_l", "SM A2 L", 1, 195),
            ("sm_a3_n", "SM A3 N", 4, 60),
            ("sm_a3_l", "SM A3 L", 4, 360),
            ("sm_a4_n", "SM A4 N", 15, 140),
            ("sm_a4_l", "SM A4 L", 15, 190),
            ("sm_a5_n", "SM A5 N", 17, 80),
            ("sm_a5_l", "SM A5 L", 17, 110),
        ),
    },
    "4": {
        "layout": "hungaroring_2026",
        "length_m": 4381,
        "map": "https://www.fia.com/system/files/decision-document/2026_hungarian_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_red_zone.pdf",
        "sectors": (("s1", "S1", 4, -85), ("s2", "S2", 11, 100)),
        "speed": (1, -310),
        "zones": (
            ("sm_a1_n", "SM A1 N", 14, 40),
            ("sm_a1_l", "SM A1 L", 14, 100),
            ("sm_a3_n", "SM A3 N", 3, 50),
            ("sm_a3_l", "SM A3 L", 3, 80),
            ("sm_a4_n", "SM A4 N", 11, 60),
            ("sm_a4_l", "SM A4 L", 11, 90),
        ),
    },
    "55": {
        "layout": "zandvoort_2026",
        "length_m": 4259,
        "map": "https://www.fia.com/system/files/decision-document/2026_dutch_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_and_emergency_exits_map.pdf",
        "sectors": (("s1", "S1", 7, -110), ("s2", "S2", 11, -150)),
        "speed": (1, -95),
        "zones": (
            ("ot_d1", "OT D", 13, -10),
            ("sm_a1_n", "SM A1 N", 14, 20),
            ("sm_a1_l", "SM A1 L", 14, 80),
            ("sm_a2_n", "SM A2 N", 10, 50),
            ("sm_a2_l", "SM A2 L", 10, 120),
        ),
    },
    "39": {
        "layout": "monza_2026",
        "length_m": 5793,
        "map": "https://www.fia.com/system/files/decision-document/2026_italian_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_red_zone.pdf",
        "sectors": (("s1", "S1", 4, -230), ("s2", "S2", 8, -210)),
        "speed": (1, -190),
        "zones": (
            ("sm_a2_n", "SM A2 N", 3, 70),
            ("sm_a2_l", "SM A2 L", 3, 110),
            ("sm_a3_n", "SM A3 N", 7, 170),
            ("sm_a3_l", "SM A3 L", 7, 230),
            ("sm_a4_n", "SM A4 N", 10, 130),
            ("sm_a4_l", "SM A4 L", 10, 180),
        ),
    },
    "144": {
        "layout": "baku_2026",
        "length_m": 6003,
        "map": "https://www.fia.com/system/files/decision-document/2026_azerbaijan_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_red_zone.pdf",
        "sectors": (("s1", "S1", 5, -45), ("s2", "S2", 16, -55)),
        "speed": (20, 210),
        "zones": (
            ("ot_d1", "OT D", 16, 90),
            ("ot_a1", "OT A", 17, -20),
            ("sm_a1_n", "SM A1 N", 19, 45),
            ("sm_a1_l", "SM A1 L", 20, 45),
            ("sm_a2_n", "SM A2 N", 2, 110),
            ("sm_a2_l", "SM A2 L", 2, 160),
        ),
    },
    "61": {
        "layout": "marina_bay_post_2023",
        "length_m": 4927,
        "map": "https://www.fia.com/system/files/decision-document/2026_singapore_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_and_emergency_exits_map.pdf",
        "sectors": (("s1", "S1", 7, -150), ("s2", "S2", 14, -140)),
        "speed": (1, -150),
        "zones": SINGAPORE_2026_AERO_POINTS,
    },
    "12": {
        "layout": "sepang_2026",
        "length_m": 5543,
        "map": "https://cdn.jsdelivr.net/gh/TracingInsights/DDocs@0ac6569aba0e2fbccfd1995988ac6a7bd7ba751d/documents/2026/bahrain-grand-prix/competition-notes-circuit-map-pit-lane-drawing-emergency-exits-map-and-red-zone.pdf",
        "coordinates": "https://github.com/TUMFTM/racetrack-database/blob/master/tracks/Sepang.csv",
        "sectors": (("s1", "S1", 4, -145), ("s2", "S2", 10, 0)),
        "speed": (15, -205),
        "zones": (
            ("ot_d1", "OT D", 15, -45),
            ("ot_a1", "OT A", 15, 0),
            ("sm_a1_n", "SM A1 N", 15, 65),
            ("sm_a1_l", "SM A1 L", 15, 85),
            ("sm_a2_n", "SM A2 N", 3, 10),
            ("sm_a2_l", "SM A2 L", 3, 50),
            ("sm_a3_n", "SM A3 N", 8, 65),
            ("sm_a3_l", "SM A3 L", 8, 95),
            ("sm_a4_n", "SM A4 N", 14, 65),
            ("sm_a4_l", "SM A4 L", 14, 80),
        ),
    },
    "153": {
        "layout": "madring_2026",
        "length_m": 5414,
        "map": "https://www.fia.com/system/files/decision-document/2026_spanish_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_and_emergency_exits_map.pdf",
        "coordinates": "https://geoportal.madrid.es/fsdescargas/IDEAM_WBGEOPORTAL/CIRCUITO_F1/CIRCUITO_F1_MADRING.zip",
        "sectors": (("s1", "S1", 7, -85), ("s2", "S2", 16, -40)),
        "speed": (5, -160),
        "zones": (
            ("ot_a1", "OT A", 22, 20),
            ("sm_a1_n", "SM A1 N", 22, 100),
            ("sm_a1_l", "SM A1 L", 22, 130),
            ("sm_a2_n", "SM A2 N", 3, 40),
            ("sm_a2_l", "SM A2 L", 3, 90),
        ),
    },
}

# The final six 2026 venues do not yet have event-specific 2026 FIA maps or
# position dumps. Prepare the stable map layers from 2025 event maps and the
# matching 2025 Position.z geometry. Detection/activation marks are omitted:
# 2025 DRS positions do not establish 2026 Overtake or Straight Mode points.
SEASON_2026_BASELINES = {
    "9": {
        "layout": "americas_2026_baseline",
        "length_m": 5513,
        "map": "https://www.fia.com/system/files/decision-document/2025_united_states_grand_prix_-_event_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_quarantine_zone_map_red_zones_map.pdf",
        "sectors": (("s1", "S1", 7, -55), ("s2", "S2", 13, -65)),
        "speed": (12, -180),
    },
    "65": {
        "layout": "rodriguez_2026_baseline",
        "length_m": 4304,
        "map": "https://www.fia.com/system/files/decision-document/2025_mexico_city_grand_prix_-_event_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_quarantine_zone_area.pdf",
        "sectors": (("s1", "S1", 4, -136), ("s2", "S2", 12, -242)),
        "speed": (1, -234),
    },
    "14": {
        "layout": "interlagos_2026_baseline",
        "length_m": 4309,
        "map": "https://www.fia.com/system/files/decision-document/2025_sao_paulo_grand_prix_-_event_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_quarantine_zone_and_red_zones_map.pdf",
        "sectors": (("s1", "S1", 4, -168), ("s2", "S2", 12, -85)),
        "speed": (1, -90),
    },
    "150": {
        "layout": "losail_2026_baseline",
        "length_m": 5419,
        "map": "https://www.fia.com/system/files/decision-document/2025_qatar_grand_prix_-_event_notes_-_circuit_map._pit_lane_drawing_emergency_exits_map_ers_battery_containment_area_red_zones_map.pdf",
        "sectors": (("s1", "S1", 6, -80), ("s2", "S2", 12, -75)),
        "speed": (1, -205),
    },
    "70": {
        "layout": "yas_marina_2026_baseline",
        "length_m": 5281,
        "map": "https://www.fia.com/system/files/decision-document/2025_abu_dhabi_grand_prix_-_event_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_quarantine_zone_and_red_zones.pdf",
        "sectors": (("s1", "S1", 5, -205), ("s2", "S2", 9, -100)),
        "speed": (6, -150),
    },
}


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


def _feature_arc(corner_arcs, scale, circuit_key, corner, offset_m):
    if corner not in corner_arcs:
        raise ValueError(f"{circuit_key} has no source coordinate for T{corner}")
    return corner_arcs[corner] + offset_m * scale


def _singapore_2026_records(records):
    """Bind FIA 2026 markings to the reviewed, unchanged Marina Bay geometry."""
    source = {
        "url": SINGAPORE_2026_MAP,
        "coordinate_url": "https://api.multiviewer.app/api/v1/circuits/61/2026",
        "checked_on": "2026-10-11",
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


def _season_2026_records():
    """Build verified 2026 layers from the frozen circuit and FIA sources."""
    snapshot = json.loads(COORDINATE_SNAPSHOT.read_text(encoding="utf-8"))
    if snapshot.get("checked_on") != "2026-10-11":
        raise ValueError("Unexpected 2026 coordinate snapshot date")
    records = []
    for circuit_key, source in SEASON_2026.items():
        # Singapore reuses the reviewed 2025 geometry and has a dedicated
        # 2026 binding below; its coordinates must not be regenerated here.
        if circuit_key == "61":
            continue
        api = snapshot["circuits"][circuit_key]
        track = GEOMETRIES[circuit_key]
        points = track["points"]
        lengths, cumulative = _segments(points)
        scale = cumulative[-1] / source["length_m"]
        corners = {
            int(item["number"]): (float(item["x"]), float(item["y"]))
            for item in api["corners"]
        }
        corner_arcs = {}
        for number, coordinate in corners.items():
            gap, arc, _ = _nearest(points, coordinate, lengths, cumulative)
            if gap > 500:
                raise ValueError(
                    f"{circuit_key} T{number} is too far from geometry: {gap:.0f}"
                )
            corner_arcs[number] = arc

        common = {
            "schema_version": 1,
            "circuit_key": circuit_key,
            "layout_key": source["layout"],
            "valid_from_season": 2026,
            "valid_to_season": 2026,
            "geometry_fingerprint": FINGERPRINT(track),
            "qa_status": "verified",
            "rights_status": "cleared",
            "source": {
                "url": source["map"],
                "coordinate_url": source.get(
                    "coordinates",
                    f"https://api.multiviewer.app/api/v1/circuits/{circuit_key}/2026",
                ),
                "checked_on": "2026-10-11",
            },
        }
        start = api.get("start")
        if start is None:
            start = {"x": api["x"][0], "y": api["y"][0]}
        start_gap, start_arc, _ = _nearest(
            points, (float(start["x"]), float(start["y"])), lengths, cumulative
        )
        if start_gap > 500:
            raise ValueError(f"{circuit_key} start line is too far from geometry")
        records.extend(
            (
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
                        for number in sorted(corner_arcs)
                    ],
                },
                {
                    **common,
                    "layer": "sectors",
                    "items": [
                        _line(
                            points,
                            lengths,
                            cumulative,
                            _feature_arc(
                                corner_arcs, scale, circuit_key, corner, offset
                            ),
                            label,
                            item_id,
                        )
                        for item_id, label, corner, offset in source["sectors"]
                    ],
                },
                {
                    **common,
                    "layer": "speed_traps",
                    "items": [
                        _point(
                            points,
                            lengths,
                            cumulative,
                            _feature_arc(
                                corner_arcs, scale, circuit_key, *source["speed"]
                            ),
                            "Speed trap",
                            "speed_trap",
                        )
                    ],
                },
                {
                    **common,
                    "layer": "detection_zones",
                    "items": [
                        _point(
                            points,
                            lengths,
                            cumulative,
                            _feature_arc(
                                corner_arcs, scale, circuit_key, corner, offset
                            ),
                            label,
                            item_id,
                        )
                        for item_id, label, corner, offset in source["zones"]
                    ],
                },
            )
        )
    return records


def _season_2026_baseline_records():
    """Build clearly labelled 2026 baseline layers from reviewed 2025 maps."""
    snapshot = json.loads(BASELINE_COORDINATE_SNAPSHOT.read_text(encoding="utf-8"))
    if snapshot.get("checked_on") != "2026-10-11":
        raise ValueError("Unexpected 2025 baseline coordinate snapshot date")
    records = []
    for circuit_key, source in SEASON_2026_BASELINES.items():
        api = snapshot["circuits"][circuit_key]
        track = GEOMETRIES[circuit_key]
        points = track["points"]
        lengths, cumulative = _segments(points)
        scale = cumulative[-1] / source["length_m"]
        corner_arcs = {}
        for item in api["corners"]:
            number = int(item["number"])
            gap, arc, _ = _nearest(
                points, (float(item["x"]), float(item["y"])), lengths, cumulative
            )
            if gap > 500:
                raise ValueError(
                    f"{circuit_key} T{number} is too far from 2025 geometry: {gap:.0f}"
                )
            corner_arcs[number] = arc

        common = {
            "schema_version": 1,
            "circuit_key": circuit_key,
            "layout_key": source["layout"],
            "valid_from_season": 2026,
            "valid_to_season": 2026,
            "geometry_fingerprint": FINGERPRINT(track),
            "qa_status": "verified",
            "rights_status": "cleared",
            "source": {
                "url": source["map"],
                "coordinate_url": api["coordinate_url"],
                "coordinate_reference_year": api["provider_data_year"],
                "baseline_season": 2025,
                "checked_on": "2026-10-11",
            },
        }
        start = api["start"]
        start_gap, start_arc, _ = _nearest(
            points, (float(start["x"]), float(start["y"])), lengths, cumulative
        )
        if start_gap > 500:
            raise ValueError(f"{circuit_key} start line is too far from 2025 geometry")
        records.extend(
            (
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
                        for number in sorted(corner_arcs)
                    ],
                },
                {
                    **common,
                    "layer": "sectors",
                    "items": [
                        _line(
                            points,
                            lengths,
                            cumulative,
                            _feature_arc(
                                corner_arcs, scale, circuit_key, corner, offset
                            ),
                            label,
                            item_id,
                        )
                        for item_id, label, corner, offset in source["sectors"]
                    ],
                },
                {
                    **common,
                    "layer": "speed_traps",
                    "items": [
                        _point(
                            points,
                            lengths,
                            cumulative,
                            _feature_arc(
                                corner_arcs, scale, circuit_key, *source["speed"]
                            ),
                            "Speed trap",
                            "speed_trap",
                        )
                    ],
                },
            )
        )
    return records


def build_catalog():
    """Return the existing pilot records plus reviewed 2026 circuits."""
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
    records.extend(_singapore_2026_records(records))
    records.extend(_season_2026_records())
    records.extend(_season_2026_baseline_records())
    return records


if __name__ == "__main__":
    CATALOG.write_text(json.dumps(build_catalog(), indent=2) + "\n", encoding="utf-8")
