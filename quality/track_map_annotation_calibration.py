"""Build and review Singapore 2025 annotation candidates without network access.

Run with Python 3.14 from the repository root. The FIA map is a linked review
source only; its pixels are never copied into generated artifacts.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import runpy
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
GEOMETRY = ROOT / "custom_components/f1_sensor/track_map_static_geometry.py"
CONTRACT = ROOT / "custom_components/f1_sensor/track_map_annotation_contract.py"
FIA_MAP = (
    "https://www.fia.com/system/files/decision-document/"
    "2025_singapore_grand_prix_-_event_notes_-_circuit_map_pit_lane_"
    "emergency_exits_map_and_quarantine_zone.pdf"
)

# Manual matches against the FIA 2025 circuit map, in lap order. These indexes
# are review data, not evidence that source-image pixels equal raw coordinates.
CORNER_POINTS = (
    (1, 50, (3, -4)),
    (2, 52, (6, -8)),
    (3, 54, (-4, -4)),
    (4, 60, (-4, 0)),
    (5, 63, (4, 2)),
    (6, 68, (0, 5)),
    (7, 74, (0, -5)),
    (8, 79, (-6, 4)),
    (9, 84, (-4, -1)),
    (10, 0, (0, -10)),
    (11, 3, (6, -6)),
    (12, 6, (-6, 10)),
    (13, 10, (5, 4)),
    (14, 21, (8, -4)),
    (15, 27, (0, 5)),
    (16, 33, (-2, -5)),
    (17, 36, (1, 5)),
    (18, 41, (-4, 8)),
    (19, 43, (-8, -2)),
)
# FIA marks the start line at M0.0 above the checkered control line; index 45
# would incorrectly place the annotation near that separate control line.
START_LINE_POINT_INDEX = 47
START_LINE_HALF_WIDTH = 220


def _geometry() -> dict:
    return runpy.run_path(str(GEOMETRY))["STATIC_TRACK_GEOMETRIES"]["61"]


def _fingerprint(track: dict) -> str:
    return runpy.run_path(str(CONTRACT))["geometry_fingerprint"](track)


def _start_line(points: tuple[tuple[int, int], ...]) -> tuple[list[int], list[int]]:
    before = points[START_LINE_POINT_INDEX - 1]
    after = points[START_LINE_POINT_INDEX + 1]
    dx, dy = after[0] - before[0], after[1] - before[1]
    length = math.hypot(dx, dy)
    nx, ny = -dy / length, dx / length
    center = points[START_LINE_POINT_INDEX]
    return (
        [
            round(center[0] - nx * START_LINE_HALF_WIDTH),
            round(center[1] - ny * START_LINE_HALF_WIDTH),
        ],
        [
            round(center[0] + nx * START_LINE_HALF_WIDTH),
            round(center[1] + ny * START_LINE_HALF_WIDTH),
        ],
    )


def build_catalog(
    *, qa_status: str = "candidate", rights_status: str = "pending"
) -> list[dict]:
    """Generate two geometry-bound records from reviewed point indexes."""
    track = _geometry()
    points = track["points"]
    common = {
        "schema_version": 1,
        "circuit_key": "61",
        "layout_key": "marina_bay_post_2023",
        "valid_from_season": 2025,
        "valid_to_season": 2025,
        "geometry_fingerprint": _fingerprint(track),
        "qa_status": qa_status,
        "rights_status": rights_status,
        "source": {"url": FIA_MAP, "checked_on": "2026-10-09"},
    }
    start, end = _start_line(points)
    return [
        {
            **common,
            "layer": "start_finish",
            "items": [
                {
                    "id": "start_finish",
                    "kind": "line",
                    "start": start,
                    "end": end,
                    "label": "Start/finish",
                }
            ],
        },
        {
            **common,
            "layer": "corners",
            "items": [
                {
                    "id": f"turn_{number:02d}",
                    "kind": "point",
                    "anchor": list(points[index]),
                    "label": str(number),
                    "label_offset": list(offset),
                }
                for number, index, offset in CORNER_POINTS
            ],
        },
    ]


def project(track: dict, *, orientation: str, vertical: str):
    """Mirror the card's raw-to-SVG transform for review images."""
    points = track["points"]
    min_x, max_x = min(x for x, _ in points), max(x for x, _ in points)
    min_y, max_y = min(y for _, y in points), max(y for _, y in points)
    cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
    angle = math.radians(track["rotation"] if orientation == "source" else 0)

    def rotate(x: float, y: float) -> tuple[float, float]:
        a, b = x - cx, y - cy
        return a * math.cos(angle) - b * math.sin(angle), a * math.sin(
            angle
        ) + b * math.cos(angle)

    rotated = [rotate(*point) for point in points]
    left, right = min(x for x, _ in rotated), max(x for x, _ in rotated)
    bottom, top = min(y for _, y in rotated), max(y for _, y in rotated)
    rcx, rcy = (left + right) / 2, (bottom + top) / 2
    scale = 90 / max(right - left, top - bottom, 1)
    y_sign = -1 if vertical == "flipped" else 1

    def transform(x: float, y: float) -> tuple[float, float]:
        a, b = rotate(x, y)
        return 50 + (a - rcx) * scale, 50 + (b - rcy) * scale * y_sign

    return transform


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _panel(
    draw: ImageDraw.ImageDraw,
    track: dict,
    catalog: list[dict],
    *,
    left: int,
    top: int,
    title: str,
    orientation: str,
    vertical: str,
    cars: list[tuple[float, float, str]] | None = None,
) -> None:
    scale = 7.4
    transform = project(track, orientation=orientation, vertical=vertical)

    def px(point: tuple[float, float] | list[float]) -> tuple[float, float]:
        return left + point[0] * scale, top + 32 + point[1] * scale

    draw.text((left + 10, top + 5), title, fill="#13243a", font=_font(22))
    path = [px(transform(*point)) for point in track["points"]]
    draw.line(path, fill="#64748b", width=8, joint="curve")
    line = catalog[0]["items"][0]
    draw.line(
        [px(transform(*line["start"])), px(transform(*line["end"]))],
        fill="#d91920",
        width=7,
    )
    for item in catalog[1]["items"]:
        x, y = transform(*item["anchor"])
        cx, cy = px((x, y))
        draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill="#1346a3")
        dx, dy = item["label_offset"]
        if vertical == "normal":
            dy = -dy
        lx, ly = px((x + dx, y + dy))
        draw.line([(cx, cy), (lx, ly)], fill="#9aaccb", width=2)
        draw.text(
            (lx, ly),
            item["label"],
            fill="#102d78",
            font=_font(25),
            anchor="mm",
            stroke_width=2,
            stroke_fill="white",
        )
    if cars:
        for x, y, driver in cars:
            cx, cy = px(transform(x, y))
            draw.ellipse(
                (cx - 12, cy - 12, cx + 12, cy + 12),
                fill="#f4a100",
                outline="#462d00",
                width=2,
            )
            draw.text(
                (cx + 14, cy), driver, fill="#473000", font=_font(16), anchor="lm"
            )


def render_review(
    catalog: list[dict], output: Path, *, replay_dump: Path | None = None
) -> None:
    """Render four orientation variants or four real replay frames."""
    track = _geometry()
    image = Image.new("RGB", (1660, 1660), "white")
    draw = ImageDraw.Draw(image)
    if replay_dump is None:
        panels = [
            ("source", "flipped"),
            ("source", "normal"),
            ("raw", "flipped"),
            ("raw", "normal"),
        ]
        for i, (orientation, vertical) in enumerate(panels):
            _panel(
                draw,
                track,
                catalog,
                left=(i % 2) * 830,
                top=(i // 2) * 830,
                title=f"{orientation} / {vertical}",
                orientation=orientation,
                vertical=vertical,
            )
    else:
        sys.path.insert(0, str(ROOT))
        from custom_components.f1_sensor.track_map import parse_position_z_line

        frames: list[list[tuple[float, float, str]]] = []
        target_lines = {2500, 4500, 6500, 8500}
        with replay_dump.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if line_number in target_lines:
                    latest = {}
                    for item in parse_position_z_line(line):
                        if item.status.lower() == "ontrack" and (item.x or item.y):
                            latest[item.racing_number] = (
                                item.x,
                                item.y,
                                item.racing_number,
                            )
                    frames.append(list(latest.values()))
                if line_number >= max(target_lines):
                    break
        if len(frames) != 4 or any(len(frame) < 10 for frame in frames):
            raise ValueError(
                "Replay dump did not yield four frames with at least 10 cars"
            )
        for i, cars in enumerate(frames):
            _panel(
                draw,
                track,
                catalog,
                left=(i % 2) * 830,
                top=(i // 2) * 830,
                title=f"Position.z line {sorted(target_lines)[i]} ({len(cars)} cars)",
                orientation="source",
                vertical="flipped",
                cars=cars,
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-out", type=Path)
    parser.add_argument("--review-out", type=Path)
    parser.add_argument("--replay-dump", type=Path)
    parser.add_argument(
        "--qa-status", default="candidate", choices=["candidate", "verified"]
    )
    parser.add_argument(
        "--rights-status", default="pending", choices=["pending", "cleared"]
    )
    args = parser.parse_args()
    if not args.catalog_out and not args.review_out:
        parser.error("Specify --catalog-out or --review-out")
    catalog = build_catalog(qa_status=args.qa_status, rights_status=args.rights_status)
    if args.catalog_out:
        args.catalog_out.parent.mkdir(parents=True, exist_ok=True)
        args.catalog_out.write_text(
            json.dumps(catalog, indent=2) + "\n", encoding="utf-8"
        )
    if args.review_out:
        render_review(catalog, args.review_out, replay_dump=args.replay_dump)


if __name__ == "__main__":
    main()
