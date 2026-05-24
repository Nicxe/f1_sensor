"""Offline QA helpers for the static track map geometry catalog."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .const import F1_CIRCUIT_IMAGE_SLUGS
from .helpers import get_circuit_map_url, get_circuit_outline_url
from .track_map_static_geometry import (
    STATIC_TRACK_GEOMETRIES,
    get_static_track_geometry_provenance,
)
from .track_map_static_geometry_calibrator import (
    TrackPoint,
    extract_track_points_from_detailed_map_bytes,
    extract_track_points_from_image_bytes,
)

ImageLoader = Callable[[str], bytes]

STATIC_TRACK_GEOMETRY_SOURCE = "static_catalog_position_z"
F1_DETAILED_MAP_SOURCE = "f1_detailed_map"
F1_OUTLINE_SOURCE = "f1_outline"
STATUS_OK = "ok"
STATUS_MISSING_CATALOG = "missing_catalog"
STATUS_UNEXPECTED_CATALOG = "unexpected_catalog"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_IMAGE_ERROR = "image_error"
DEFAULT_QA_SEASON = "2026"


@dataclass(frozen=True, slots=True)
class StaticTrackGeometryQaEntry:
    """One catalog QA row."""

    circuit_id: str
    status: str
    circuit_key: str | None = None
    rotation: float | None = None
    point_count: int = 0
    closed: bool | None = None
    geometry_source: str | None = None
    image_source: str | None = None
    image_url: str | None = None
    image_point_count: int | None = None
    approval_status: str | None = None
    provenance: dict[str, Any] | None = None
    issues: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable row."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StaticTrackGeometryQaReport:
    """Static geometry QA summary and rows."""

    season: str
    expected_count: int
    catalog_count: int
    covered_count: int
    missing_circuit_ids: tuple[str, ...]
    unexpected_circuit_ids: tuple[str, ...]
    entries: tuple[StaticTrackGeometryQaEntry, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report."""
        return {
            "season": self.season,
            "expected_count": self.expected_count,
            "catalog_count": self.catalog_count,
            "covered_count": self.covered_count,
            "missing_circuit_ids": list(self.missing_circuit_ids),
            "unexpected_circuit_ids": list(self.unexpected_circuit_ids),
            "entries": [entry.as_dict() for entry in self.entries],
        }


def expected_2025_2026_catalog_circuit_ids() -> tuple[str, ...]:
    """Return the current 2025/2026 calendar circuit ids expected in the catalog."""
    ids = list(F1_CIRCUIT_IMAGE_SLUGS[DEFAULT_QA_SEASON])
    if "imola" not in ids:
        insert_at = ids.index("villeneuve") if "villeneuve" in ids else len(ids)
        ids.insert(insert_at, "imola")
    return tuple(dict.fromkeys(ids))


def build_static_track_geometry_qa_report(
    *,
    season: str | int = DEFAULT_QA_SEASON,
    expected_circuit_ids: Sequence[str] | None = None,
    include_image_points: bool = False,
    image_loader: ImageLoader | None = None,
) -> StaticTrackGeometryQaReport:
    """Build a catalog coverage and image-source QA report."""
    season_key = str(season)
    expected_ids = tuple(
        expected_circuit_ids or expected_2025_2026_catalog_circuit_ids()
    )
    catalog_by_circuit_id = _catalog_by_circuit_id()
    catalog_ids = tuple(catalog_by_circuit_id)
    missing_ids = tuple(
        circuit_id
        for circuit_id in expected_ids
        if circuit_id not in catalog_by_circuit_id
    )
    unexpected_ids = tuple(
        circuit_id for circuit_id in catalog_ids if circuit_id not in expected_ids
    )

    entries: list[StaticTrackGeometryQaEntry] = []
    for circuit_id in expected_ids:
        entry = catalog_by_circuit_id.get(circuit_id)
        entries.append(
            _qa_entry_for_circuit(
                circuit_id,
                entry,
                season=season_key,
                include_image_points=include_image_points,
                image_loader=image_loader,
            )
        )

    for circuit_id in unexpected_ids:
        entries.append(
            _qa_entry_for_circuit(
                circuit_id,
                catalog_by_circuit_id[circuit_id],
                season=season_key,
                status_override=STATUS_UNEXPECTED_CATALOG,
                include_image_points=include_image_points,
                image_loader=image_loader,
            )
        )

    covered_count = sum(1 for entry in entries if entry.status == STATUS_OK)
    return StaticTrackGeometryQaReport(
        season=season_key,
        expected_count=len(expected_ids),
        catalog_count=len(STATIC_TRACK_GEOMETRIES),
        covered_count=covered_count,
        missing_circuit_ids=missing_ids,
        unexpected_circuit_ids=unexpected_ids,
        entries=tuple(entries),
    )


def write_static_track_geometry_qa_artifacts(
    report: StaticTrackGeometryQaReport,
    *,
    output_dir: str | Path,
    render: bool = True,
    image_loader: ImageLoader | None = None,
) -> dict[str, Path]:
    """Write JSON, Markdown and optional overlay image QA artifacts."""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": target / "track_map_static_catalog_qa.json",
        "markdown": target / "track_map_static_catalog_qa.md",
    }
    paths["json"].write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    paths["markdown"].write_text(_markdown_report(report), encoding="utf-8")

    if render:
        image_path = target / "track_map_static_catalog_qa.png"
        render_static_track_geometry_qa_overlay(
            report,
            output_path=image_path,
            image_loader=image_loader,
        )
        paths["overlay"] = image_path
    return paths


def render_static_track_geometry_qa_overlay(
    report: StaticTrackGeometryQaReport,
    *,
    output_path: str | Path,
    image_loader: ImageLoader | None = None,
    columns: int = 4,
    cell_width: int = 360,
    cell_height: int = 250,
) -> Path:
    """Render a catalog-vs-F1-map overlay image."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as err:  # pragma: no cover - optional offline dependency
        raise RuntimeError("Pillow is required for catalog QA rendering") from err

    loader = image_loader or _download_image
    catalog_by_circuit_id = _catalog_by_circuit_id()
    rows = math.ceil(len(report.entries) / columns)
    canvas = Image.new("RGB", (columns * cell_width, rows * cell_height), (8, 10, 13))
    draw = ImageDraw.Draw(canvas)
    font = _qa_font(ImageFont)

    for index, entry in enumerate(report.entries):
        origin_x = (index % columns) * cell_width
        origin_y = (index // columns) * cell_height
        _draw_cell_frame(draw, origin_x, origin_y, cell_width, cell_height)
        _draw_label(draw, entry, origin_x, origin_y, font)

        catalog_entry = catalog_by_circuit_id.get(entry.circuit_id)
        if catalog_entry is None:
            _draw_missing_entry(
                draw, entry, origin_x, origin_y, cell_width, cell_height, font
            )
            continue

        image_points = _load_image_points_for_entry(entry, loader)
        if image_points:
            for point in _normalize_points(image_points)[::2]:
                x, y = _cell_point(point, origin_x, origin_y + 18, 220)
                draw.point((x, y), fill=(92, 98, 107))

        geometry_points = _screen_points_for_rotation(
            tuple((float(x), float(y)) for x, y in catalog_entry["points"]),
            float(catalog_entry["rotation"]),
        )
        line = [
            _cell_point(point, origin_x, origin_y + 18, 220)
            for point in _normalize_points(geometry_points)
        ]
        if line:
            draw.line(line, fill=(108, 238, 181), width=3, joint="curve")
            start_x, start_y = line[0]
            draw.ellipse(
                [start_x - 4, start_y - 4, start_x + 4, start_y + 4],
                fill=(255, 80, 80),
            )

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)
    return path


def _qa_entry_for_circuit(
    circuit_id: str,
    entry: Any,
    *,
    season: str,
    status_override: str | None = None,
    include_image_points: bool,
    image_loader: ImageLoader | None,
) -> StaticTrackGeometryQaEntry:
    image_source, image_url = _image_source_for_circuit(circuit_id, season)
    image_point_count: int | None = None
    issues: list[str] = []
    status = status_override or STATUS_OK

    if entry is None:
        return StaticTrackGeometryQaEntry(
            circuit_id=circuit_id,
            status=STATUS_MISSING_CATALOG,
            image_source=image_source,
            image_url=image_url,
            issues=("No Position.z-backed catalog geometry",),
        )

    points = entry["points"]
    closed = len(points) > 1 and points[0] == points[-1]
    if not closed:
        issues.append("Catalog polyline is not closed")
    if len(points) < 50:
        issues.append("Catalog polyline has fewer than 50 points")
    if image_url is None:
        issues.append("No F1 map or outline image URL")

    if include_image_points and image_url is not None:
        try:
            image_points = _extract_image_points(
                image_loader or _download_image,
                image_url,
                image_source,
            )
            image_point_count = len(image_points)
        except Exception as err:  # noqa: BLE001 - offline QA should report and continue
            issues.append(f"Image extraction failed: {err}")
            status = STATUS_IMAGE_ERROR

    if issues and status == STATUS_OK:
        status = STATUS_NEEDS_REVIEW
    provenance = get_static_track_geometry_provenance(circuit_id=circuit_id)
    approval_status = (
        provenance.get("approval_status") if provenance is not None else None
    )

    return StaticTrackGeometryQaEntry(
        circuit_id=circuit_id,
        status=status,
        circuit_key=entry["circuit_key"],
        rotation=float(entry["rotation"]),
        point_count=len(points),
        closed=closed,
        geometry_source=STATIC_TRACK_GEOMETRY_SOURCE,
        image_source=image_source,
        image_url=image_url,
        image_point_count=image_point_count,
        approval_status=approval_status,
        provenance=provenance,
        issues=tuple(issues),
    )


def _catalog_by_circuit_id() -> dict[str, Any]:
    return {entry["circuit_id"]: entry for entry in STATIC_TRACK_GEOMETRIES.values()}


def _image_source_for_circuit(
    circuit_id: str,
    season: str,
) -> tuple[str | None, str | None]:
    map_url = get_circuit_map_url(circuit_id, season)
    if map_url is not None:
        return F1_DETAILED_MAP_SOURCE, map_url
    outline_url = get_circuit_outline_url(circuit_id, season)
    if outline_url is not None:
        return F1_OUTLINE_SOURCE, outline_url
    return None, None


def _extract_image_points(
    image_loader: ImageLoader,
    image_url: str,
    image_source: str | None,
) -> tuple[TrackPoint, ...]:
    image_bytes = image_loader(image_url)
    if image_source == F1_DETAILED_MAP_SOURCE:
        return extract_track_points_from_detailed_map_bytes(
            image_bytes,
            max_points=7_000,
        )
    return extract_track_points_from_image_bytes(image_bytes, max_points=7_000)


def _load_image_points_for_entry(
    entry: StaticTrackGeometryQaEntry,
    image_loader: ImageLoader,
) -> tuple[TrackPoint, ...]:
    if entry.image_url is None:
        return ()
    try:
        return _extract_image_points(image_loader, entry.image_url, entry.image_source)
    except Exception:  # noqa: BLE001 - rendering should still show catalog geometry
        return ()


def _markdown_report(report: StaticTrackGeometryQaReport) -> str:
    lines = [
        "# F1 Track Map Static Catalog QA",
        "",
        f"Season image set: `{report.season}`",
        f"Expected 2025/2026 circuit ids: `{report.expected_count}`",
        f"Catalog entries: `{report.catalog_count}`",
        f"Covered entries: `{report.covered_count}`",
        f"Missing catalog entries: `{', '.join(report.missing_circuit_ids) or 'none'}`",
        f"Unexpected catalog entries: `{', '.join(report.unexpected_circuit_ids) or 'none'}`",
        "",
        (
            "| Status | Approval | Circuit id | Key | Points | Closed | Rotation | "
            "Image source | Source dump | Issues |"
        ),
        "| --- | --- | --- | --- | ---: | --- | ---: | --- | --- | --- |",
    ]
    for entry in report.entries:
        issues = "; ".join(entry.issues)
        source_dump = ""
        if entry.provenance is not None:
            source_dump = entry.provenance.get("source_dump_path", "")
        lines.append(
            "| "
            f"`{entry.status}` | "
            f"`{entry.approval_status or ''}` | "
            f"`{entry.circuit_id}` | "
            f"`{entry.circuit_key or ''}` | "
            f"{entry.point_count} | "
            f"{entry.closed if entry.closed is not None else ''} | "
            f"{entry.rotation if entry.rotation is not None else ''} | "
            f"`{entry.image_source or ''}` | "
            f"`{source_dump}` | "
            f"{issues} |"
        )
    lines.append("")
    return "\n".join(lines)


def _screen_points_for_rotation(
    points: tuple[TrackPoint, ...],
    rotation: float,
) -> tuple[TrackPoint, ...]:
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    radians = math.radians(rotation)
    cos_value = math.cos(radians)
    sin_value = math.sin(radians)
    screen_points: list[TrackPoint] = []
    for x, y in points:
        dx = x - center_x
        dy = y - center_y
        rotated_x = center_x + (dx * cos_value) - (dy * sin_value)
        rotated_y = center_y + (dx * sin_value) + (dy * cos_value)
        screen_points.append((rotated_x, -rotated_y))
    return tuple(screen_points)


def _normalize_points(points: Iterable[TrackPoint]) -> tuple[TrackPoint, ...]:
    point_list = tuple(points)
    if not point_list:
        return ()
    min_x = min(point[0] for point in point_list)
    max_x = max(point[0] for point in point_list)
    min_y = min(point[1] for point in point_list)
    max_y = max(point[1] for point in point_list)
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    scale = max(max_x - min_x, max_y - min_y) or 1.0
    return tuple(
        ((x - center_x) / scale, (y - center_y) / scale) for x, y in point_list
    )


def _cell_point(
    point: TrackPoint,
    origin_x: int,
    origin_y: int,
    size: int,
    *,
    padding: int = 30,
) -> tuple[float, float]:
    scale = size - (padding * 2)
    return (
        origin_x + padding + ((point[0] + 0.5) * scale),
        origin_y + padding + ((point[1] + 0.5) * scale),
    )


def _draw_cell_frame(
    draw: Any,
    origin_x: int,
    origin_y: int,
    cell_width: int,
    cell_height: int,
) -> None:
    draw.rectangle(
        [origin_x, origin_y, origin_x + cell_width - 1, origin_y + cell_height - 1],
        outline=(42, 45, 50),
    )


def _draw_label(
    draw: Any,
    entry: StaticTrackGeometryQaEntry,
    origin_x: int,
    origin_y: int,
    font: Any,
) -> None:
    if entry.rotation is None:
        text = f"{entry.circuit_id} {entry.status}"
    else:
        text = f"{entry.circuit_key} {entry.circuit_id} rot {entry.rotation:.1f}"
    draw.text((origin_x + 10, origin_y + 8), text, fill=(235, 239, 246), font=font)


def _draw_missing_entry(
    draw: Any,
    entry: StaticTrackGeometryQaEntry,
    origin_x: int,
    origin_y: int,
    cell_width: int,
    cell_height: int,
    font: Any,
) -> None:
    text = "Missing Position.z catalog"
    draw.text(
        (origin_x + 18, origin_y + (cell_height / 2) - 8),
        text,
        fill=(255, 170, 80),
        font=font,
    )
    if entry.image_source:
        draw.text(
            (origin_x + 18, origin_y + (cell_height / 2) + 14),
            entry.image_source,
            fill=(140, 146, 156),
            font=font,
        )


def _qa_font(image_font_module: Any) -> Any:
    try:
        return image_font_module.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            14,
        )
    except Exception:  # noqa: BLE001 - Pillow falls back to its default font
        return None


def _download_image(url: str, *, timeout: float = 30.0) -> bytes:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=timeout) as response:
        data: Any = response.read()
    return bytes(data)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render and summarize static track map catalog QA artifacts",
    )
    parser.add_argument(
        "--output-dir",
        default="/tmp/f1_track_map_static_catalog_qa",
        help="Directory for JSON, Markdown and overlay image artifacts",
    )
    parser.add_argument(
        "--season",
        default=DEFAULT_QA_SEASON,
        help="F1 image season to use for detailed map/outline URLs",
    )
    parser.add_argument(
        "--include-image-points",
        action="store_true",
        help="Include extracted F1 image point counts in JSON/Markdown",
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="Skip overlay PNG rendering",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with status 1 when missing or review entries are present",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the catalog QA CLI."""
    args = _parse_args(argv)
    report = build_static_track_geometry_qa_report(
        season=args.season,
        include_image_points=bool(args.include_image_points),
    )
    paths = write_static_track_geometry_qa_artifacts(
        report,
        output_dir=args.output_dir,
        render=not args.no_render,
    )
    for label, path in paths.items():
        print(f"{label}: {path}")
    print(
        "coverage: "
        f"{report.covered_count}/{report.expected_count}; "
        f"missing={','.join(report.missing_circuit_ids) or 'none'}"
    )
    if args.strict and (
        report.missing_circuit_ids
        or report.unexpected_circuit_ids
        or any(
            entry.status not in {STATUS_OK, STATUS_MISSING_CATALOG}
            for entry in report.entries
        )
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
