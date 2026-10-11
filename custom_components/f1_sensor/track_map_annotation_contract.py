"""Identity and validation contract for optional track map annotations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any

ANNOTATION_SCHEMA_VERSION = 1
ANNOTATION_LAYERS = frozenset(
    {"corners", "detection_zones", "sectors", "speed_traps", "start_finish"}
)
MAX_ANNOTATIONS_PER_LAYER = 64
MAX_ANNOTATION_LABEL_LENGTH = 32

# A circuit key and year only resolve to a layout after that combination has
# been reviewed. In particular, a new season never inherits last year's data.
ANNOTATION_LAYOUTS: dict[tuple[str, int], str] = {
    ("2", 2025): "silverstone_2025",
    ("61", 2022): "marina_bay_pre_2023",
    ("61", 2025): "marina_bay_post_2023",
    ("61", 2026): "marina_bay_post_2023",
}

_SESSION_YEAR = re.compile(r"^(\d{4})/")
_ITEM_ID = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
_SOURCE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ALLOWED_KINDS = {
    "corners": frozenset({"point"}),
    "detection_zones": frozenset({"point", "interval"}),
    "sectors": frozenset({"line", "interval"}),
    "speed_traps": frozenset({"point"}),
    "start_finish": frozenset({"line"}),
}


def load_annotation_catalog() -> list[dict[str, Any]]:
    """Read the bundled catalog once during entry setup, outside the event loop."""
    try:
        records = json.loads(
            Path(__file__).with_name("track_map_annotation_catalog.json").read_text()
        )
    except (OSError, ValueError):
        return []
    return records if isinstance(records, list) else []


@dataclass(frozen=True, slots=True)
class AnnotationContext:
    """The exact map generation to which annotations may be attached."""

    entry_id: str
    source: str
    session_key: str
    session_generation: int
    circuit_key: str
    season: int
    layout_key: str
    geometry_fingerprint: str


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except OverflowError:
        return None
    return result if math.isfinite(result) else None


def _pair(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    numbers = [_number(part) for part in value]
    return numbers if all(part is not None for part in numbers) else None


def geometry_fingerprint(track: Mapping[str, Any] | None) -> str | None:
    """Return a stable identity for the raw points and their projection rotation."""
    if not isinstance(track, Mapping):
        return None
    circuit_key = track.get("circuit_key")
    rotation = _number(track.get("rotation"))
    points = track.get("points")
    if (
        not isinstance(circuit_key, str)
        or not circuit_key
        or rotation is None
        or not isinstance(points, (list, tuple))
        or not 2 <= len(points) <= 50_000
    ):
        return None
    normalized_points = [_pair(point) for point in points]
    if any(point is None for point in normalized_points):
        return None
    content = json.dumps(
        [circuit_key, rotation, normalized_points], separators=(",", ":")
    ).encode()
    return f"sha256:{sha256(content).hexdigest()}"


def annotation_context(
    *,
    entry_id: str,
    session: Mapping[str, Any] | None,
    track: Mapping[str, Any] | None,
    source: str,
    session_generation: int,
    replay_year: int | None = None,
) -> AnnotationContext | None:
    """Resolve an explicitly reviewed layout from one live or replay session."""
    if (
        not isinstance(entry_id, str)
        or not entry_id
        or not isinstance(session, Mapping)
        or not isinstance(track, Mapping)
        or source not in {"live", "replay"}
        or isinstance(session_generation, bool)
        or not isinstance(session_generation, int)
        or session_generation < 0
    ):
        return None
    session_key = session.get("session_key")
    circuit_key = session.get("circuit_key")
    path = session.get("path")
    if (
        not isinstance(session_key, str)
        or not session_key
        or not isinstance(circuit_key, str)
        or not circuit_key
        or not isinstance(path, str)
        or not (match := _SESSION_YEAR.match(path))
        or track.get("circuit_key") != circuit_key
    ):
        return None
    season = int(match.group(1))
    start_date = session.get("start_date")
    if start_date is not None and (
        not isinstance(start_date, str) or not start_date.startswith(f"{season:04d}-")
    ):
        return None
    if source == "replay":
        if replay_year != season:
            return None
    elif replay_year is not None:
        return None
    layout_key = ANNOTATION_LAYOUTS.get((circuit_key, season))
    fingerprint = geometry_fingerprint(track)
    if layout_key is None or fingerprint is None:
        return None
    return AnnotationContext(
        entry_id,
        source,
        session_key,
        session_generation,
        circuit_key,
        season,
        layout_key,
        fingerprint,
    )


def _interval_position(value: Any, segment_count: int) -> float | None:
    if not isinstance(value, Mapping):
        return None
    index = value.get("segment_index")
    fraction = _number(value.get("fraction"))
    if (
        isinstance(index, bool)
        or not isinstance(index, int)
        or not 0 <= index < segment_count
        or fraction is None
        or not 0 <= fraction <= 1
    ):
        return None
    return index + fraction


def _valid_item(item: Any, layer: str, segment_count: int) -> bool:
    if not isinstance(item, Mapping):
        return False
    item_id = item.get("id")
    label = item.get("label")
    kind = item.get("kind")
    if (
        not isinstance(item_id, str)
        or not _ITEM_ID.fullmatch(item_id)
        or not isinstance(label, str)
        or not 0 < len(label) <= MAX_ANNOTATION_LABEL_LENGTH
        or not label.strip()
        or not isinstance(kind, str)
        or kind not in _ALLOWED_KINDS[layer]
    ):
        return False
    if kind == "point":
        offset = _pair(item.get("label_offset"))
        return (
            _pair(item.get("anchor")) is not None
            and offset is not None
            and all(-10 <= value <= 10 for value in offset)
        )
    if kind == "line":
        start, end = _pair(item.get("start")), _pair(item.get("end"))
        return start is not None and end is not None and start != end
    start = _interval_position(item.get("start"), segment_count)
    end = _interval_position(item.get("end"), segment_count)
    return (
        start is not None
        and end is not None
        and start != end
        and item.get("direction") == "forward"
        and type(item.get("wraps_start_finish")) is bool
        and item["wraps_start_finish"] == (end < start)
    )


def _valid_layer(record: Any, context: AnnotationContext, segment_count: int) -> bool:
    if not isinstance(record, Mapping):
        return False
    layer = record.get("layer")
    source = record.get("source")
    items = record.get("items")
    if (
        type(record.get("schema_version")) is not int
        or record["schema_version"] != ANNOTATION_SCHEMA_VERSION
        or record.get("circuit_key") != context.circuit_key
        or record.get("layout_key") != context.layout_key
        or record.get("geometry_fingerprint") != context.geometry_fingerprint
        or record.get("qa_status") != "verified"
        or record.get("rights_status") != "cleared"
        or not isinstance(layer, str)
        or layer not in ANNOTATION_LAYERS
        or type(record.get("valid_from_season")) is not int
        or type(record.get("valid_to_season")) is not int
        or not record["valid_from_season"]
        <= context.season
        <= record["valid_to_season"]
        or not isinstance(source, Mapping)
        or not isinstance(source.get("url"), str)
        or not source["url"].startswith("https://")
        or len(source["url"]) <= len("https://")
        or not isinstance(source.get("checked_on"), str)
        or not _SOURCE_DATE.fullmatch(source["checked_on"])
        or not isinstance(items, list)
        or not 0 < len(items) <= MAX_ANNOTATIONS_PER_LAYER
    ):
        return False
    try:
        date.fromisoformat(source["checked_on"])
    except ValueError:
        return False
    if not all(_valid_item(item, layer, segment_count) for item in items):
        return False
    ids = [item["id"] for item in items]
    return len(ids) == len(set(ids))


def bind_annotation_layers(
    records: Iterable[Mapping[str, Any]],
    context: AnnotationContext | None,
    *,
    segment_count: int,
) -> dict[str, Any] | None:
    """Bind only complete, approved layers to this exact map generation."""
    if context is None or type(segment_count) is not int or segment_count < 1:
        return None
    matched: dict[str, Mapping[str, Any]] = {}
    duplicate_layers: set[str] = set()
    for record in records:
        if not _valid_layer(record, context, segment_count):
            continue
        layer = record["layer"]
        if layer in matched:
            duplicate_layers.add(layer)
        else:
            matched[layer] = record
    layers = [
        dict(record)
        for layer, record in matched.items()
        if layer not in duplicate_layers
    ]
    if not layers:
        return None
    return {
        "schema_version": ANNOTATION_SCHEMA_VERSION,
        "binding": asdict(context),
        "layers": layers,
    }


def annotation_binding_matches(
    payload: Mapping[str, Any] | None, context: AnnotationContext | None
) -> bool:
    """Reject an old annotation payload after a session, entry, or seek switch."""
    return (
        context is not None
        and isinstance(payload, Mapping)
        and payload.get("schema_version") == ANNOTATION_SCHEMA_VERSION
        and payload.get("binding") == asdict(context)
    )
