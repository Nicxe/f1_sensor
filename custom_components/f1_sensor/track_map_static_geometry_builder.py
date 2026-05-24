"""Offline helpers for building static track map geometry from dumps."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .track_map import (
    DEFAULT_TRACK_MAP_GEOMETRY_MIN_DRIVER_POINTS,
    TrackMapBounds,
    TrackMapPosition,
    build_track_geometry_from_position_groups,
    parse_position_z_line,
)

STATIC_TRACK_GEOMETRY_CANDIDATE_SOURCE = "static_catalog_candidate"
DEFAULT_STATIC_TRACK_GEOMETRY_MAX_POINTS = 90
DEFAULT_STATIC_TRACK_GEOMETRY_MAX_CLOSURE_GAP = 1000.0
DEFAULT_STATIC_TRACK_GEOMETRY_MAX_CLOSURE_RATIO = 0.05


@dataclass(frozen=True, slots=True)
class StaticTrackGeometryBuildResult:
    """Candidate static geometry and provenance metrics from a dump."""

    circuit_key: str
    points: tuple[tuple[int, int], ...]
    bounds: TrackMapBounds
    driver_count: int
    sample_count: int


def build_static_track_geometry_from_position_lines(
    lines: Iterable[str],
    *,
    circuit_key: str,
    max_points: int = DEFAULT_STATIC_TRACK_GEOMETRY_MAX_POINTS,
    min_points: int = DEFAULT_TRACK_MAP_GEOMETRY_MIN_DRIVER_POINTS,
) -> StaticTrackGeometryBuildResult | None:
    """Build a closed catalog candidate from Position.z jsonStream lines."""
    positions_by_driver: dict[str, list[TrackMapPosition]] = defaultdict(list)
    sample_count = 0
    for line in lines:
        for position in parse_position_z_line(line):
            if position.status.strip().lower() != "ontrack":
                continue
            if position.x == 0 and position.y == 0:
                continue
            positions_by_driver[position.racing_number].append(position)
            sample_count += 1

    geometry = build_track_geometry_from_position_groups(
        positions_by_driver,
        circuit_key=circuit_key,
        source=STATIC_TRACK_GEOMETRY_CANDIDATE_SOURCE,
        max_points=max_points,
        min_points=min_points,
    )
    if geometry is None:
        return None

    points = _close_static_track_points(geometry.points)
    if points is None:
        return None

    bounds = _bounds_from_points(points)
    if bounds is None:
        return None

    return StaticTrackGeometryBuildResult(
        circuit_key=circuit_key,
        points=points,
        bounds=bounds,
        driver_count=len(positions_by_driver),
        sample_count=sample_count,
    )


def _close_static_track_points(
    points: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int], ...] | None:
    if len(points) < 2:
        return None
    if points[0] == points[-1]:
        return points

    bounds = _bounds_from_points(points)
    if bounds is None:
        return None

    closure_gap = _point_distance(points[0], points[-1])
    max_gap = max(
        DEFAULT_STATIC_TRACK_GEOMETRY_MAX_CLOSURE_GAP,
        _bounds_diagonal(bounds) * DEFAULT_STATIC_TRACK_GEOMETRY_MAX_CLOSURE_RATIO,
    )
    if closure_gap > max_gap:
        return None
    return (*points, points[0])


def _bounds_from_points(points: Iterable[tuple[int, int]]) -> TrackMapBounds | None:
    point_list = list(points)
    if not point_list:
        return None
    xs = [point[0] for point in point_list]
    ys = [point[1] for point in point_list]
    return TrackMapBounds(
        min_x=min(xs),
        max_x=max(xs),
        min_y=min(ys),
        max_y=max(ys),
    )


def _point_distance(start: tuple[int, int], end: tuple[int, int]) -> float:
    return ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5


def _bounds_diagonal(bounds: TrackMapBounds) -> float:
    return (
        (bounds.max_x - bounds.min_x) ** 2 + (bounds.max_y - bounds.min_y) ** 2
    ) ** 0.5
