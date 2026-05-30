"""Offline maintenance workflow for the static track map geometry catalog."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .const import F1_CIRCUIT_IMAGE_SLUGS
from .helpers import get_circuit_map_url, get_circuit_outline_url
from .track_map import TrackMapBounds
from .track_map_static_geometry import (
    STATIC_TRACK_GEOMETRIES,
    STATIC_TRACK_GEOMETRY_APPROVAL_GENERATED,
    STATIC_TRACK_GEOMETRY_APPROVAL_QA_PASSED,
    STATIC_TRACK_GEOMETRY_CALIBRATOR,
    STATIC_TRACK_GEOMETRY_CATALOG_VERSION,
    STATIC_TRACK_GEOMETRY_GENERATOR,
    STATIC_TRACK_GEOMETRY_QA_ARTIFACT,
    get_static_track_geometry_provenance,
)
from .track_map_static_geometry_builder import (
    DEFAULT_STATIC_TRACK_GEOMETRY_MAX_POINTS,
    build_static_track_geometry_from_position_lines,
)
from .track_map_static_geometry_calibrator import (
    extract_track_points_from_detailed_map_bytes,
    extract_track_points_from_image_bytes,
    presentation_rotation_from_image_points,
    shape_aligned_presentation_rotation_from_image_points,
)
from .track_map_static_geometry_qa import (
    DEFAULT_QA_SEASON,
    F1_DETAILED_MAP_SOURCE,
    F1_OUTLINE_SOURCE,
    expected_2025_2026_catalog_circuit_ids,
)

ImageLoader = Callable[[str], bytes]

DEFAULT_MAINTENANCE_DUMP_ROOT = "/Volumes/Data/F1 Live Timing API - Dumps"
DEFAULT_MAINTENANCE_OUTPUT_DIR = "/tmp/f1_track_map_static_catalog_maintenance"
MAINTENANCE_STATUS_CATALOGED = "cataloged"
MAINTENANCE_STATUS_CANDIDATE_READY = "candidate_ready"
MAINTENANCE_STATUS_MISSING_POSITION_Z = "missing_position_z"
MAINTENANCE_STATUS_CANDIDATE_ERROR = "candidate_error"
MAINTENANCE_STATUS_UNEXPECTED_DUMP = "unexpected_dump"
_POSITION_STREAM_SUFFIX = "_Position.z.txt"
_SESSION_INFO_SUFFIX = "_SessionInfo.txt"
_MISSING_CIRCUIT_ALIASES: dict[str, tuple[str, ...]] = {
    "madring": ("madring", "madrid"),
}


@dataclass(frozen=True, slots=True)
class StaticTrackGeometryDumpSession:
    """One local dump session that can provide Position.z geometry."""

    root_path: str
    position_file: str
    session_info_file: str | None
    circuit_key: str | None
    circuit_short_name: str | None
    meeting_name: str | None
    session_name: str | None
    session_type: str | None
    start_date: str | None
    path: str | None
    inferred_circuit_id: str | None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable row."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StaticTrackGeometryCandidate:
    """Generated static catalog candidate for a missing circuit."""

    circuit_key: str
    circuit_id: str
    aliases: tuple[str, ...]
    approval_status: str
    rotation: float | None
    point_count: int
    driver_count: int
    sample_count: int
    bounds: dict[str, int | None]
    points: tuple[tuple[int, int], ...]
    image_source: str | None
    image_url: str | None
    source_dump_path: str
    source_position_file: str
    source_session_info_file: str | None
    provenance: dict[str, Any]
    issues: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable candidate."""
        return {
            **asdict(self),
            "aliases": list(self.aliases),
            "points": [[x, y] for x, y in self.points],
            "issues": list(self.issues),
        }


@dataclass(frozen=True, slots=True)
class StaticTrackGeometryMaintenanceEntry:
    """One maintenance report row."""

    circuit_id: str
    status: str
    catalog_present: bool
    approval_status: str | None = None
    circuit_key: str | None = None
    circuit_short_name: str | None = None
    source_dump_path: str | None = None
    position_file: str | None = None
    candidate_status: str | None = None
    candidate_point_count: int | None = None
    candidate_rotation: float | None = None
    image_source: str | None = None
    image_url: str | None = None
    issues: tuple[str, ...] = ()
    candidate: StaticTrackGeometryCandidate | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable row."""
        return {
            "circuit_id": self.circuit_id,
            "status": self.status,
            "catalog_present": self.catalog_present,
            "approval_status": self.approval_status,
            "circuit_key": self.circuit_key,
            "circuit_short_name": self.circuit_short_name,
            "source_dump_path": self.source_dump_path,
            "position_file": self.position_file,
            "candidate_status": self.candidate_status,
            "candidate_point_count": self.candidate_point_count,
            "candidate_rotation": self.candidate_rotation,
            "image_source": self.image_source,
            "image_url": self.image_url,
            "issues": list(self.issues),
            "candidate": self.candidate.as_dict() if self.candidate else None,
        }


@dataclass(frozen=True, slots=True)
class StaticTrackGeometryMaintenanceReport:
    """Maintenance summary for catalog coverage and generated candidates."""

    season: str
    dump_root: str
    expected_count: int
    catalog_count: int
    dump_session_count: int
    cataloged_count: int
    candidate_count: int
    missing_position_z_count: int
    missing_circuit_ids: tuple[str, ...]
    unexpected_dump_circuit_ids: tuple[str, ...]
    entries: tuple[StaticTrackGeometryMaintenanceEntry, ...]
    unexpected_dumps: tuple[StaticTrackGeometryDumpSession, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report."""
        return {
            "season": self.season,
            "dump_root": self.dump_root,
            "expected_count": self.expected_count,
            "catalog_count": self.catalog_count,
            "dump_session_count": self.dump_session_count,
            "cataloged_count": self.cataloged_count,
            "candidate_count": self.candidate_count,
            "missing_position_z_count": self.missing_position_z_count,
            "missing_circuit_ids": list(self.missing_circuit_ids),
            "unexpected_dump_circuit_ids": list(self.unexpected_dump_circuit_ids),
            "entries": [entry.as_dict() for entry in self.entries],
            "unexpected_dumps": [dump.as_dict() for dump in self.unexpected_dumps],
        }


def scan_position_dump_sessions(
    dump_root: str | Path,
    *,
    expected_circuit_ids: Sequence[str] | None = None,
    season: str | int = DEFAULT_QA_SEASON,
    session_name: str = "Race",
) -> tuple[StaticTrackGeometryDumpSession, ...]:
    """Find local Position.z dump sessions with SessionInfo metadata."""
    root = Path(dump_root)
    if not root.exists():
        return ()
    expected_ids = tuple(
        expected_circuit_ids or expected_2025_2026_catalog_circuit_ids()
    )
    sessions: list[StaticTrackGeometryDumpSession] = []
    for position_file in sorted(root.rglob(f"*{_POSITION_STREAM_SUFFIX}")):
        session_dir = position_file.parent
        if session_name and session_dir.name != session_name:
            continue
        session_info_file = _session_info_file_for_position_file(position_file)
        session_info = (
            _read_session_info_file(session_info_file)
            if session_info_file is not None
            else {}
        )
        circuit_key, circuit_short_name = _session_circuit_metadata(session_info)
        inferred_circuit_id = _infer_circuit_id(
            circuit_key=circuit_key,
            circuit_short_name=circuit_short_name,
            session_info=session_info,
            position_file=position_file,
            expected_circuit_ids=expected_ids,
            season=str(season),
        )
        sessions.append(
            StaticTrackGeometryDumpSession(
                root_path=str(session_dir),
                position_file=str(position_file),
                session_info_file=str(session_info_file)
                if session_info_file is not None
                else None,
                circuit_key=circuit_key,
                circuit_short_name=circuit_short_name,
                meeting_name=_text_or_none(_meeting_payload(session_info).get("Name")),
                session_name=_text_or_none(session_info.get("Name")),
                session_type=_text_or_none(session_info.get("Type")),
                start_date=_text_or_none(session_info.get("StartDate")),
                path=_text_or_none(session_info.get("Path")),
                inferred_circuit_id=inferred_circuit_id,
            )
        )
    return tuple(sessions)


def build_static_track_geometry_maintenance_report(
    *,
    dump_root: str | Path = DEFAULT_MAINTENANCE_DUMP_ROOT,
    output_dir: str | Path = DEFAULT_MAINTENANCE_OUTPUT_DIR,
    season: str | int = DEFAULT_QA_SEASON,
    expected_circuit_ids: Sequence[str] | None = None,
    build_existing: bool = False,
    image_loader: ImageLoader | None = None,
    max_points: int = DEFAULT_STATIC_TRACK_GEOMETRY_MAX_POINTS,
) -> StaticTrackGeometryMaintenanceReport:
    """Build a maintenance report and generate candidates for missing circuits."""
    season_key = str(season)
    expected_ids = tuple(
        expected_circuit_ids or expected_2025_2026_catalog_circuit_ids()
    )
    dump_sessions = scan_position_dump_sessions(
        dump_root,
        expected_circuit_ids=expected_ids,
        season=season_key,
    )
    catalog_by_circuit_id = _catalog_by_circuit_id()
    dumps_by_circuit_id = _best_dump_by_circuit_id(dump_sessions)
    candidate_output_dir = Path(output_dir) / "candidates"
    entries: list[StaticTrackGeometryMaintenanceEntry] = []

    for circuit_id in expected_ids:
        catalog_entry = catalog_by_circuit_id.get(circuit_id)
        dump_session = dumps_by_circuit_id.get(circuit_id)
        if catalog_entry is not None and not build_existing:
            provenance = get_static_track_geometry_provenance(circuit_id=circuit_id)
            source_dump_path = (
                str(provenance.get("source_dump_path"))
                if provenance and provenance.get("source_dump_path")
                else dump_session.root_path
                if dump_session is not None
                else None
            )
            entries.append(
                StaticTrackGeometryMaintenanceEntry(
                    circuit_id=circuit_id,
                    status=MAINTENANCE_STATUS_CATALOGED,
                    catalog_present=True,
                    approval_status=provenance.get("approval_status")
                    if provenance
                    else None,
                    circuit_key=catalog_entry["circuit_key"],
                    circuit_short_name=dump_session.circuit_short_name
                    if dump_session is not None
                    else None,
                    source_dump_path=source_dump_path,
                    position_file=dump_session.position_file
                    if dump_session is not None
                    else None,
                )
            )
            continue

        if dump_session is None:
            entries.append(
                StaticTrackGeometryMaintenanceEntry(
                    circuit_id=circuit_id,
                    status=MAINTENANCE_STATUS_MISSING_POSITION_Z,
                    catalog_present=catalog_entry is not None,
                    issues=("No matching Position.z Race dump found",),
                )
            )
            continue

        candidate = _build_candidate_for_dump(
            circuit_id,
            dump_session,
            season=season_key,
            image_loader=image_loader,
            max_points=max_points,
        )
        if candidate is None:
            entries.append(
                StaticTrackGeometryMaintenanceEntry(
                    circuit_id=circuit_id,
                    status=MAINTENANCE_STATUS_CANDIDATE_ERROR,
                    catalog_present=catalog_entry is not None,
                    circuit_key=dump_session.circuit_key,
                    circuit_short_name=dump_session.circuit_short_name,
                    source_dump_path=dump_session.root_path,
                    position_file=dump_session.position_file,
                    issues=("Position.z candidate generation failed",),
                )
            )
            continue

        candidate_output_dir.mkdir(parents=True, exist_ok=True)
        candidate_path = candidate_output_dir / f"{circuit_id}.json"
        candidate_path.write_text(
            json.dumps(candidate.as_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        entries.append(
            StaticTrackGeometryMaintenanceEntry(
                circuit_id=circuit_id,
                status=MAINTENANCE_STATUS_CANDIDATE_READY,
                catalog_present=catalog_entry is not None,
                approval_status=candidate.approval_status,
                circuit_key=candidate.circuit_key,
                circuit_short_name=dump_session.circuit_short_name,
                source_dump_path=dump_session.root_path,
                position_file=dump_session.position_file,
                candidate_status=candidate.approval_status,
                candidate_point_count=candidate.point_count,
                candidate_rotation=candidate.rotation,
                image_source=candidate.image_source,
                image_url=candidate.image_url,
                issues=candidate.issues,
                candidate=candidate,
            )
        )

    expected_set = set(expected_ids)
    unexpected_dumps = tuple(
        dump
        for dump in dump_sessions
        if dump.inferred_circuit_id is not None
        and dump.inferred_circuit_id not in expected_set
    )
    unexpected_ids = tuple(
        dict.fromkeys(
            dump.inferred_circuit_id
            for dump in unexpected_dumps
            if dump.inferred_circuit_id is not None
        )
    )
    missing_ids = tuple(
        entry.circuit_id
        for entry in entries
        if entry.status == MAINTENANCE_STATUS_MISSING_POSITION_Z
    )
    return StaticTrackGeometryMaintenanceReport(
        season=season_key,
        dump_root=str(dump_root),
        expected_count=len(expected_ids),
        catalog_count=len(STATIC_TRACK_GEOMETRIES),
        dump_session_count=len(dump_sessions),
        cataloged_count=sum(
            1 for entry in entries if entry.status == MAINTENANCE_STATUS_CATALOGED
        ),
        candidate_count=sum(
            1 for entry in entries if entry.status == MAINTENANCE_STATUS_CANDIDATE_READY
        ),
        missing_position_z_count=len(missing_ids),
        missing_circuit_ids=missing_ids,
        unexpected_dump_circuit_ids=unexpected_ids,
        entries=tuple(entries),
        unexpected_dumps=unexpected_dumps,
    )


def write_static_track_geometry_maintenance_artifacts(
    report: StaticTrackGeometryMaintenanceReport,
    *,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write maintenance JSON and Markdown artifacts."""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": target / "track_map_static_catalog_maintenance.json",
        "markdown": target / "track_map_static_catalog_maintenance.md",
    }
    paths["json"].write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    paths["markdown"].write_text(_markdown_report(report), encoding="utf-8")
    return paths


def _build_candidate_for_dump(
    circuit_id: str,
    dump_session: StaticTrackGeometryDumpSession,
    *,
    season: str,
    image_loader: ImageLoader | None,
    max_points: int,
) -> StaticTrackGeometryCandidate | None:
    if dump_session.circuit_key is None:
        return None
    position_file = Path(dump_session.position_file)
    try:
        with position_file.open(encoding="utf-8") as file:
            result = build_static_track_geometry_from_position_lines(
                file,
                circuit_key=dump_session.circuit_key,
                max_points=max_points,
            )
    except OSError:
        return None
    if result is None:
        return None

    issues: list[str] = []
    image_source, image_url = _image_source_for_circuit(circuit_id, season)
    rotation: float | None = None
    if image_url is None or image_source is None:
        issues.append("No F1 image source found for calibration")
    else:
        try:
            rotation = _calibrate_candidate_rotation(
                result.points,
                image_source=image_source,
                image_url=image_url,
                image_loader=image_loader or _download_image,
            )
        except Exception as err:  # noqa: BLE001 - offline tool should report issues
            issues.append(f"Image calibration failed: {err}")

    approval_status = (
        STATIC_TRACK_GEOMETRY_APPROVAL_QA_PASSED
        if rotation is not None and not issues
        else STATIC_TRACK_GEOMETRY_APPROVAL_GENERATED
    )
    provenance = _candidate_provenance(
        dump_session,
        approval_status=approval_status,
        image_source=image_source,
    )
    return StaticTrackGeometryCandidate(
        circuit_key=result.circuit_key,
        circuit_id=circuit_id,
        aliases=_candidate_aliases(circuit_id, dump_session),
        approval_status=approval_status,
        rotation=rotation,
        point_count=len(result.points),
        driver_count=result.driver_count,
        sample_count=result.sample_count,
        bounds=_bounds_payload(result.bounds),
        points=result.points,
        image_source=image_source,
        image_url=image_url,
        source_dump_path=dump_session.root_path,
        source_position_file=dump_session.position_file,
        source_session_info_file=dump_session.session_info_file,
        provenance=provenance,
        issues=tuple(issues),
    )


def _calibrate_candidate_rotation(
    points: Sequence[tuple[int, int]],
    *,
    image_source: str,
    image_url: str,
    image_loader: ImageLoader,
) -> float:
    image_bytes = image_loader(image_url)
    image_points = (
        extract_track_points_from_detailed_map_bytes(image_bytes)
        if image_source == F1_DETAILED_MAP_SOURCE
        else extract_track_points_from_image_bytes(image_bytes)
    )
    geometry_points = tuple((float(x), float(y)) for x, y in points)
    if image_source == F1_DETAILED_MAP_SOURCE:
        rotation = shape_aligned_presentation_rotation_from_image_points(
            geometry_points,
            image_points,
        )
    else:
        rotation = presentation_rotation_from_image_points(
            geometry_points,
            image_points,
        )
    return round(_normalize_degrees(rotation), 1)


def _candidate_provenance(
    dump_session: StaticTrackGeometryDumpSession,
    *,
    approval_status: str,
    image_source: str | None,
) -> dict[str, Any]:
    return {
        "approval_status": approval_status,
        "visual_approved_at": "",
        "catalog_version": STATIC_TRACK_GEOMETRY_CATALOG_VERSION,
        "geometry_source": "position_z_dump",
        "position_stream": "Position.z",
        "source_season": _source_season(dump_session),
        "source_session": dump_session.session_name or dump_session.session_type,
        "source_dump_path": dump_session.root_path,
        "source_position_file": dump_session.position_file,
        "source_session_info_file": dump_session.session_info_file,
        "generator": STATIC_TRACK_GEOMETRY_GENERATOR,
        "calibration_source": image_source,
        "calibrator": STATIC_TRACK_GEOMETRY_CALIBRATOR,
        "qa_artifact": STATIC_TRACK_GEOMETRY_QA_ARTIFACT,
    }


def _source_season(dump_session: StaticTrackGeometryDumpSession) -> int | None:
    for value in (dump_session.start_date, dump_session.path, dump_session.root_path):
        if not value:
            continue
        year = str(value).strip()[:4]
        if year.isdigit():
            return int(year)
    return None


def _candidate_aliases(
    circuit_id: str,
    dump_session: StaticTrackGeometryDumpSession,
) -> tuple[str, ...]:
    aliases: list[str] = [circuit_id]
    aliases.extend(_MISSING_CIRCUIT_ALIASES.get(circuit_id, ()))
    if dump_session.circuit_short_name:
        aliases.append(_alias_text(dump_session.circuit_short_name))
    if dump_session.meeting_name:
        aliases.append(_alias_text(dump_session.meeting_name.replace("Grand Prix", "")))
    return tuple(alias for alias in dict.fromkeys(aliases) if alias)


def _session_info_file_for_position_file(position_file: Path) -> Path | None:
    prefix = position_file.name.removesuffix(_POSITION_STREAM_SUFFIX)
    direct = position_file.with_name(f"{prefix}{_SESSION_INFO_SUFFIX}")
    if direct.exists():
        return direct
    matches = sorted(position_file.parent.glob(f"*{_SESSION_INFO_SUFFIX}"))
    return matches[0] if matches else None


def _read_session_info_file(path: Path) -> dict[str, Any]:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            payload = _json_payload_from_stream_line(line)
            if isinstance(payload, dict):
                return payload
    except OSError:
        return {}
    return {}


def _json_payload_from_stream_line(line: str) -> Any:
    stripped = line.strip()
    if not stripped or stripped.startswith("URL:"):
        return None
    start = stripped.find("{")
    if start < 0:
        return None
    try:
        return json.loads(stripped[start:])
    except json.JSONDecodeError:
        return None


def _session_circuit_metadata(
    session_info: dict[str, Any],
) -> tuple[str | None, str | None]:
    circuit = _meeting_payload(session_info).get("Circuit")
    if not isinstance(circuit, dict):
        return None, None
    return _text_or_none(circuit.get("Key")), _text_or_none(circuit.get("ShortName"))


def _meeting_payload(session_info: dict[str, Any]) -> dict[str, Any]:
    meeting = session_info.get("Meeting")
    return meeting if isinstance(meeting, dict) else {}


def _infer_circuit_id(
    *,
    circuit_key: str | None,
    circuit_short_name: str | None,
    session_info: dict[str, Any],
    position_file: Path,
    expected_circuit_ids: Sequence[str],
    season: str,
) -> str | None:
    if circuit_key is not None:
        for entry in STATIC_TRACK_GEOMETRIES.values():
            if entry["circuit_key"] == circuit_key:
                return entry["circuit_id"]
    haystack = _normalized_text(
        " ".join(
            value
            for value in (
                circuit_short_name,
                _text_or_none(_meeting_payload(session_info).get("Name")),
                _text_or_none(session_info.get("Path")),
                str(position_file.parent),
            )
            if value
        )
    )
    slug_map = F1_CIRCUIT_IMAGE_SLUGS.get(season, {})
    for circuit_id in expected_circuit_ids:
        terms = [circuit_id, slug_map.get(circuit_id, "")]
        terms.extend(_MISSING_CIRCUIT_ALIASES.get(circuit_id, ()))
        if any(_normalized_text(term) in haystack for term in terms if term):
            return circuit_id
    return None


def _best_dump_by_circuit_id(
    dump_sessions: Sequence[StaticTrackGeometryDumpSession],
) -> dict[str, StaticTrackGeometryDumpSession]:
    result: dict[str, StaticTrackGeometryDumpSession] = {}
    for dump in sorted(dump_sessions, key=_dump_sort_key, reverse=True):
        if dump.inferred_circuit_id is None:
            continue
        result.setdefault(dump.inferred_circuit_id, dump)
    return result


def _dump_sort_key(dump: StaticTrackGeometryDumpSession) -> tuple[str, str]:
    return (dump.start_date or "", dump.root_path)


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


def _markdown_report(report: StaticTrackGeometryMaintenanceReport) -> str:
    lines = [
        "# F1 Track Map Static Catalog Maintenance",
        "",
        f"Season image set: `{report.season}`",
        f"Dump root: `{report.dump_root}`",
        f"Expected 2025/2026 circuit ids: `{report.expected_count}`",
        f"Catalog entries: `{report.catalog_count}`",
        f"Dump sessions scanned: `{report.dump_session_count}`",
        f"Cataloged entries: `{report.cataloged_count}`",
        f"Generated candidates: `{report.candidate_count}`",
        f"Missing Position.z entries: `{report.missing_position_z_count}`",
        f"Missing circuit ids: `{', '.join(report.missing_circuit_ids) or 'none'}`",
        "",
        (
            "| Status | Circuit id | Approval | Key | Candidate points | Rotation | "
            "Source dump | Issues |"
        ),
        "| --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for entry in report.entries:
        lines.append(
            "| "
            f"`{entry.status}` | "
            f"`{entry.circuit_id}` | "
            f"`{entry.approval_status or ''}` | "
            f"`{entry.circuit_key or ''}` | "
            f"{entry.candidate_point_count or ''} | "
            f"{entry.candidate_rotation if entry.candidate_rotation is not None else ''} | "
            f"`{entry.source_dump_path or ''}` | "
            f"{'; '.join(entry.issues)} |"
        )
    lines.append("")
    return "\n".join(lines)


def _bounds_payload(bounds: TrackMapBounds) -> dict[str, int | None]:
    return {
        "min_x": bounds.min_x,
        "max_x": bounds.max_x,
        "min_y": bounds.min_y,
        "max_y": bounds.max_y,
        "min_z": bounds.min_z,
        "max_z": bounds.max_z,
    }


def _download_image(url: str, *, timeout: float = 30.0) -> bytes:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=timeout) as response:
        data: Any = response.read()
    return bytes(data)


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _alias_text(value: str) -> str:
    return "_".join(value.casefold().strip().split())


def _normalized_text(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _normalize_degrees(rotation: float) -> float:
    while rotation > 180:
        rotation -= 360
    while rotation <= -180:
        rotation += 360
    if abs(rotation) < 0.05:
        return 0.0
    return rotation


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan dumps and generate static track map catalog candidates",
    )
    parser.add_argument(
        "--dump-root",
        default=DEFAULT_MAINTENANCE_DUMP_ROOT,
        help="Root directory to scan for Position.z Race dumps",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_MAINTENANCE_OUTPUT_DIR,
        help="Directory for maintenance JSON, Markdown and candidate artifacts",
    )
    parser.add_argument(
        "--season",
        default=DEFAULT_QA_SEASON,
        help="F1 image season to use for calibration URLs",
    )
    parser.add_argument(
        "--build-existing",
        action="store_true",
        help="Also generate candidates for circuits already present in the catalog",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=DEFAULT_STATIC_TRACK_GEOMETRY_MAX_POINTS,
        help="Maximum points for generated candidates",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with status 1 when missing circuits remain without Position.z",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the catalog maintenance CLI."""
    args = _parse_args(argv)
    report = build_static_track_geometry_maintenance_report(
        dump_root=args.dump_root,
        output_dir=args.output_dir,
        season=args.season,
        build_existing=bool(args.build_existing),
        max_points=args.max_points,
    )
    paths = write_static_track_geometry_maintenance_artifacts(
        report,
        output_dir=args.output_dir,
    )
    for label, path in paths.items():
        print(f"{label}: {path}")
    print(
        "maintenance: "
        f"cataloged={report.cataloged_count}; "
        f"candidates={report.candidate_count}; "
        f"missing_position_z={report.missing_position_z_count}"
    )
    if args.strict and report.missing_position_z_count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
