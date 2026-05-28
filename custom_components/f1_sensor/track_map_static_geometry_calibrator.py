"""Offline calibration helpers for static track map presentation rotation."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
import math
from typing import Any
from urllib.request import Request, urlopen

from .helpers import get_circuit_map_url, get_circuit_outline_url
from .track_map_static_geometry import STATIC_TRACK_GEOMETRIES

TrackPoint = tuple[float, float]


@dataclass(frozen=True, slots=True)
class StaticTrackImageCalibration:
    """Result from comparing catalog geometry against an official F1 image."""

    circuit_key: str
    circuit_id: str
    image_url: str
    geometry_angle: float
    image_angle: float
    rotation: float
    geometry_point_count: int
    image_point_count: int


def principal_axis_degrees(points: Iterable[TrackPoint]) -> float:
    """Return the dominant 2D axis angle in degrees for a point cloud."""
    point_list = tuple(points)
    if len(point_list) > 2 and point_list[0] == point_list[-1]:
        point_list = point_list[:-1]
    if len(point_list) < 2:
        raise ValueError("At least two points are required")

    mean_x = sum(point[0] for point in point_list) / len(point_list)
    mean_y = sum(point[1] for point in point_list) / len(point_list)
    variance_x = sum((point[0] - mean_x) ** 2 for point in point_list) / len(point_list)
    variance_y = sum((point[1] - mean_y) ** 2 for point in point_list) / len(point_list)
    covariance = sum(
        (point[0] - mean_x) * (point[1] - mean_y) for point in point_list
    ) / len(point_list)
    return math.degrees(0.5 * math.atan2(2 * covariance, variance_x - variance_y))


def presentation_rotation_from_image_points(
    geometry_points: Iterable[TrackPoint],
    image_points: Iterable[TrackPoint],
    *,
    reference_rotation: float | None = None,
) -> float:
    """Return catalog rotation needed to match an image's screen orientation."""
    geometry_angle = principal_axis_degrees(geometry_points)
    image_angle = principal_axis_degrees(image_points)
    return _normalize_equivalent_rotation(
        -image_angle - geometry_angle,
        reference_rotation=reference_rotation,
    )


def calibrate_static_track_geometry_from_image_points(
    circuit_key: str,
    image_points: Iterable[TrackPoint],
    *,
    image_url: str = "",
    shape_align: bool = False,
) -> StaticTrackImageCalibration:
    """Calibrate one static catalog entry from already extracted image points."""
    entry = STATIC_TRACK_GEOMETRIES[circuit_key]
    geometry_points = tuple((float(x), float(y)) for x, y in entry["points"])
    image_point_list = tuple(image_points)
    geometry_angle = principal_axis_degrees(geometry_points)
    image_angle = principal_axis_degrees(image_point_list)
    if shape_align:
        rotation = shape_aligned_presentation_rotation_from_image_points(
            geometry_points,
            image_point_list,
            reference_rotation=float(entry["rotation"]),
        )
    else:
        rotation = _normalize_equivalent_rotation(
            -image_angle - geometry_angle,
            reference_rotation=float(entry["rotation"]),
        )
    rotation = round(rotation, 1)
    return StaticTrackImageCalibration(
        circuit_key=circuit_key,
        circuit_id=entry["circuit_id"],
        image_url=image_url,
        geometry_angle=geometry_angle,
        image_angle=image_angle,
        rotation=rotation,
        geometry_point_count=len(geometry_points),
        image_point_count=len(image_point_list),
    )


def calibrate_static_track_geometry_from_f1_image(
    circuit_key: str,
    *,
    season: str | int = "2026",
    timeout: float = 30.0,
) -> StaticTrackImageCalibration:
    """Download the official F1 map image and calibrate one catalog entry."""
    entry = STATIC_TRACK_GEOMETRIES[circuit_key]
    circuit_id = entry["circuit_id"]
    image_url = get_circuit_map_url(circuit_id, season)
    shape_align = image_url is not None
    if image_url is None:
        image_url = get_circuit_outline_url(circuit_id, season)
        shape_align = False
    if image_url is None:
        raise ValueError(f"No F1 circuit image URL for circuit_id={circuit_id}")
    image_bytes = _download_image(image_url, timeout=timeout)
    image_points = (
        extract_track_points_from_detailed_map_bytes(image_bytes)
        if shape_align
        else extract_track_points_from_image_bytes(image_bytes)
    )
    return calibrate_static_track_geometry_from_image_points(
        circuit_key,
        image_points,
        image_url=image_url,
        shape_align=shape_align,
    )


def extract_track_points_from_image_bytes(
    image_bytes: bytes,
    *,
    alpha_threshold: int = 20,
    brightness_threshold: int = 80,
    max_points: int = 20_000,
) -> tuple[TrackPoint, ...]:
    """Extract bright visible pixels from an official F1 outline image."""
    try:
        from PIL import Image
    except ImportError as err:  # pragma: no cover - optional offline dependency
        raise RuntimeError("Pillow is required for image calibration") from err

    with Image.open(BytesIO(image_bytes)) as image:
        rgba = image.convert("RGBA")
        points: list[TrackPoint] = []
        for y in range(rgba.height):
            for x in range(rgba.width):
                red, green, blue, alpha = rgba.getpixel((x, y))
                brightness = (red + green + blue) / 3
                if alpha > alpha_threshold and brightness >= brightness_threshold:
                    points.append((float(x), float(y)))

    if len(points) < 2:
        raise ValueError("Image did not contain enough visible track pixels")
    if max_points > 0 and len(points) > max_points:
        step = math.ceil(len(points) / max_points)
        points = points[::step]
    return tuple(points)


def extract_track_points_from_detailed_map_bytes(
    image_bytes: bytes,
    *,
    alpha_threshold: int = 20,
    dark_brightness_threshold: int = 205,
    saturated_brightness_threshold: int = 245,
    saturation_threshold: int = 50,
    max_dimension: int = 900,
    max_points: int = 20_000,
) -> tuple[TrackPoint, ...]:
    """Extract the main circuit component from an official F1 detailed map."""
    try:
        from PIL import Image
    except ImportError as err:  # pragma: no cover - optional offline dependency
        raise RuntimeError("Pillow is required for image calibration") from err

    with Image.open(BytesIO(image_bytes)) as image:
        rgba = image.convert("RGBA")
        if max_dimension > 0 and max(rgba.size) > max_dimension:
            scale = max_dimension / max(rgba.size)
            rgba = rgba.resize((round(rgba.width * scale), round(rgba.height * scale)))

        width, height = rgba.size
        mask = bytearray(width * height)
        pixels = rgba.load()
        for y in range(height):
            for x in range(width):
                red, green, blue, alpha = pixels[x, y]
                if alpha <= alpha_threshold:
                    continue
                brightness = (red + green + blue) / 3
                saturation = max(red, green, blue) - min(red, green, blue)
                if brightness < dark_brightness_threshold or (
                    saturation > saturation_threshold
                    and brightness < saturated_brightness_threshold
                ):
                    mask[(y * width) + x] = 1

    component = _largest_mask_component(mask, width, height)
    if len(component) < 2:
        raise ValueError("Image did not contain enough circuit map pixels")

    points = tuple((float(index % width), float(index // width)) for index in component)
    return _downsample_track_points(points, max_points=max_points)


def shape_aligned_presentation_rotation_from_image_points(
    geometry_points: Iterable[TrackPoint],
    image_points: Iterable[TrackPoint],
    *,
    reference_rotation: float | None = None,
    grid_size: int = 96,
    coarse_step_degrees: float = 1.0,
    refine_window_degrees: float = 15.0,
    refine_step_degrees: float = 0.25,
) -> float:
    """Return presentation rotation by matching the full outline shape."""
    geometry_point_list = tuple(geometry_points)
    image_point_list = tuple(image_points)
    if len(geometry_point_list) < 3 or len(image_point_list) < 3:
        return presentation_rotation_from_image_points(
            geometry_point_list,
            image_point_list,
            reference_rotation=reference_rotation,
        )

    principal_rotation = presentation_rotation_from_image_points(
        geometry_point_list,
        image_point_list,
        reference_rotation=None,
    )
    image_distances = _occupancy_distance_grid(
        _normalize_match_points(image_point_list),
        grid_size=grid_size,
    )
    candidates = _shape_rotation_candidates(
        principal_rotation,
        coarse_step_degrees=coarse_step_degrees,
        refine_window_degrees=refine_window_degrees,
        refine_step_degrees=refine_step_degrees,
    )
    best_rotation = min(
        candidates,
        key=lambda rotation: _shape_match_score(
            _normalize_match_points(
                _screen_points_for_presentation_rotation(
                    geometry_point_list,
                    rotation,
                )
            ),
            image_distances,
        ),
    )
    return _normalize_shape_rotation(
        best_rotation,
        reference_rotation=reference_rotation,
    )


def _downsample_track_points(
    points: tuple[TrackPoint, ...],
    *,
    max_points: int,
) -> tuple[TrackPoint, ...]:
    if max_points <= 0 or len(points) <= max_points:
        return points
    step = math.ceil(len(points) / max_points)
    return points[::step]


def _largest_mask_component(
    mask: bytearray,
    width: int,
    height: int,
) -> tuple[int, ...]:
    seen = bytearray(width * height)
    best: list[int] = []
    for index, value in enumerate(mask):
        if not value or seen[index]:
            continue
        component: list[int] = []
        queue: deque[int] = deque([index])
        seen[index] = 1
        while queue:
            current = queue.popleft()
            component.append(current)
            x = current % width
            y = current // width
            for ny in range(y - 1, y + 2):
                for nx in range(x - 1, x + 2):
                    if nx == x and ny == y:
                        continue
                    if nx < 0 or ny < 0 or nx >= width or ny >= height:
                        continue
                    neighbor = (ny * width) + nx
                    if mask[neighbor] and not seen[neighbor]:
                        seen[neighbor] = 1
                        queue.append(neighbor)
        if len(component) > len(best):
            best = component
    return tuple(best)


def _shape_rotation_candidates(
    principal_rotation: float,
    *,
    coarse_step_degrees: float,
    refine_window_degrees: float,
    refine_step_degrees: float,
) -> tuple[float, ...]:
    candidates: set[float] = set()
    coarse_steps = max(1, round(360 / coarse_step_degrees))
    for index in range(coarse_steps + 1):
        candidates.add(_normalize_degrees(-180 + (index * coarse_step_degrees)))

    refine_steps = max(1, round((refine_window_degrees * 2) / refine_step_degrees))
    for center in (
        principal_rotation,
        principal_rotation - 180,
        principal_rotation + 180,
    ):
        for index in range(refine_steps + 1):
            offset = -refine_window_degrees + (index * refine_step_degrees)
            candidates.add(_normalize_degrees(center + offset))
    return tuple(sorted(candidates))


def _screen_points_for_presentation_rotation(
    points: Iterable[TrackPoint],
    rotation: float,
) -> tuple[TrackPoint, ...]:
    point_list = tuple(points)
    min_x = min(point[0] for point in point_list)
    max_x = max(point[0] for point in point_list)
    min_y = min(point[1] for point in point_list)
    max_y = max(point[1] for point in point_list)
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    radians = math.radians(rotation)
    cos_value = math.cos(radians)
    sin_value = math.sin(radians)
    transformed: list[TrackPoint] = []
    for x, y in point_list:
        dx = x - center_x
        dy = y - center_y
        rotated_x = center_x + (dx * cos_value) - (dy * sin_value)
        rotated_y = center_y + (dx * sin_value) + (dy * cos_value)
        transformed.append((rotated_x, -rotated_y))
    return tuple(transformed)


def _normalize_match_points(points: Iterable[TrackPoint]) -> tuple[TrackPoint, ...]:
    point_list = tuple(points)
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


def _occupancy_distance_grid(
    points: Iterable[TrackPoint],
    *,
    grid_size: int,
) -> tuple[tuple[int, ...], ...]:
    occupied = {_match_grid_cell(point, grid_size=grid_size) for point in points}
    distances = [[10_000] * grid_size for _ in range(grid_size)]
    queue: deque[tuple[int, int]] = deque()
    for x, y in occupied:
        distances[y][x] = 0
        queue.append((x, y))

    while queue:
        x, y = queue.popleft()
        distance = distances[y][x] + 1
        for ny in range(y - 1, y + 2):
            for nx in range(x - 1, x + 2):
                if nx == x and ny == y:
                    continue
                if nx < 0 or ny < 0 or nx >= grid_size or ny >= grid_size:
                    continue
                if distance < distances[ny][nx]:
                    distances[ny][nx] = distance
                    queue.append((nx, ny))
    return tuple(tuple(row) for row in distances)


def _shape_match_score(
    points: Iterable[TrackPoint],
    distances: tuple[tuple[int, ...], ...],
) -> float:
    grid_size = len(distances)
    total = 0.0
    count = 0
    for point in points:
        x, y = _match_grid_cell(point, grid_size=grid_size)
        total += distances[y][x]
        count += 1
    return total / max(1, count)


def _match_grid_cell(point: TrackPoint, *, grid_size: int) -> tuple[int, int]:
    return (
        max(0, min(grid_size - 1, round((point[0] + 0.5) * (grid_size - 1)))),
        max(0, min(grid_size - 1, round((point[1] + 0.5) * (grid_size - 1)))),
    )


def _normalize_degrees(rotation: float) -> float:
    while rotation > 180:
        rotation -= 360
    while rotation <= -180:
        rotation += 360
    return rotation


def _normalize_shape_rotation(
    rotation: float,
    *,
    reference_rotation: float | None,
) -> float:
    if reference_rotation is not None and math.isfinite(reference_rotation):
        candidates = [rotation + (360 * offset) for offset in range(-2, 3)]
        rotation = min(candidates, key=lambda value: abs(value - reference_rotation))
    return _normalize_degrees(rotation)


def _download_image(url: str, *, timeout: float) -> bytes:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=timeout) as response:
        data: Any = response.read()
    return bytes(data)


def _normalize_equivalent_rotation(
    rotation: float,
    *,
    reference_rotation: float | None,
) -> float:
    if reference_rotation is not None and math.isfinite(reference_rotation):
        candidates = [rotation + (180 * offset) for offset in range(-3, 4)]
        rotation = min(candidates, key=lambda value: abs(value - reference_rotation))
    else:
        while rotation > 90:
            rotation -= 180
        while rotation <= -90:
            rotation += 180

    while rotation > 180:
        rotation -= 360
    while rotation <= -180:
        rotation += 360
    if abs(rotation) < 0.05:
        return 0.0
    return rotation
