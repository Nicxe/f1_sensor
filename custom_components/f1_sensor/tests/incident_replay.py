from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from custom_components.f1_sensor.incident_detection import (
    DATA_QUALITY_BOOTSTRAP,
    DATA_QUALITY_REPLAY,
    DriverMetadata,
    IncidentChange,
    IncidentDetector,
    SessionMetadata,
    normalize_session_type,
)

FIXTURE_MANIFEST_PATH = (
    Path(__file__).parent / "fixtures" / "incident_detection" / "fixture_manifest.json"
)

PUBLIC_REPLAY_STREAMS = frozenset(
    {
        "TimingData",
        "TrackStatus",
        "RaceControlMessages",
        "SessionInfo",
        "SessionData",
        "SessionStatus",
        "DriverList",
    }
)
FORBIDDEN_FIXTURE_KEYS = frozenset(
    {
        "authorization",
        "connectiontoken",
        "cookie",
        "credential",
        "password",
        "refreshtoken",
        "secret",
        "setcookie",
        "token",
        "accesstoken",
    }
)
MAX_REPLAY_CASE_BYTES = 100_000


@dataclass(frozen=True, slots=True)
class ReplayFrameResult:
    offset: str
    observed_at: datetime
    stream: str
    changes: tuple[IncidentChange, ...]


@dataclass(frozen=True, slots=True)
class ReplayResult:
    case_id: str
    session: SessionMetadata
    frames: tuple[ReplayFrameResult, ...]

    @property
    def changes(self) -> tuple[IncidentChange, ...]:
        return tuple(change for frame in self.frames for change in frame.changes)


def load_fixture_manifest(
    path: Path = FIXTURE_MANIFEST_PATH,
) -> Mapping[str, Any]:
    with path.open(encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)
    if not isinstance(manifest, Mapping):
        raise ValueError("Incident fixture manifest must be a JSON object")
    return manifest


def extracted_cases(
    manifest: Mapping[str, Any] | None = None,
) -> tuple[Mapping[str, Any], ...]:
    source = load_fixture_manifest() if manifest is None else manifest
    cases = source.get("extracted_cases")
    if not isinstance(cases, Sequence) or isinstance(cases, str):
        raise ValueError("Incident fixture manifest must contain extracted_cases")
    return tuple(case for case in cases if isinstance(case, Mapping))


def replay_manifest_case(case: Mapping[str, Any]) -> ReplayResult:
    validate_replay_case(case)

    case_id = _required_string(case, "id")
    session = _session_metadata(case)
    drivers = _driver_metadata(case)
    start_at = _session_start_utc(case)
    detector = IncidentDetector()
    frames: list[ReplayFrameResult] = []

    detector.process_stream(
        "SessionInfo",
        _session_info_payload(case, session),
        start_at,
        data_quality=DATA_QUALITY_REPLAY,
    )
    detector.process_stream(
        "DriverList",
        _driver_list_payload(drivers),
        start_at,
        session=session,
        data_quality=DATA_QUALITY_REPLAY,
    )

    state_before = case.get("state_before_window")
    if isinstance(state_before, Mapping):
        before_at = _offset_to_datetime(
            _required_string(case.get("time_window"), "start_offset"),
            start_at,
        )
        for stream, payload in state_before.items():
            _validate_replay_stream(str(stream))
            changes = detector.process_stream(
                str(stream),
                payload,
                before_at,
                session=session,
                drivers=drivers,
                data_quality=DATA_QUALITY_BOOTSTRAP,
            )
            frames.append(
                ReplayFrameResult(
                    offset="state_before",
                    observed_at=before_at,
                    stream=str(stream),
                    changes=tuple(changes),
                )
            )

    for frame in _ordered_frames(case):
        stream = _required_string(frame, "stream")
        _validate_replay_stream(stream)
        offset = _required_string(frame, "offset")
        observed_at = _offset_to_datetime(offset, start_at)
        changes = detector.process_stream(
            stream,
            frame.get("payload"),
            observed_at,
            session=session,
            drivers=drivers,
            data_quality=DATA_QUALITY_REPLAY,
        )
        frames.append(
            ReplayFrameResult(
                offset=offset,
                observed_at=observed_at,
                stream=stream,
                changes=tuple(changes),
            )
        )

    return ReplayResult(case_id=case_id, session=session, frames=tuple(frames))


def validate_replay_case(case: Mapping[str, Any]) -> None:
    _assert_no_forbidden_keys(case)
    if replay_case_size_bytes(case) > MAX_REPLAY_CASE_BYTES:
        raise ValueError("Incident replay case is too large for a reduced fixture")
    for stream in case.get("included_streams", ()):
        _validate_replay_stream(str(stream))
    _ordered_frames(case)


def replay_case_size_bytes(case: Mapping[str, Any]) -> int:
    return len(json.dumps(case, separators=(",", ":"), default=str).encode())


def format_replay_timeline(result: ReplayResult) -> str:
    lines = [f"{result.case_id} ({result.session.session_name})"]
    for frame in result.frames:
        if not frame.changes:
            lines.append(f"{frame.offset} {frame.stream}: no incident change")
            continue
        for change in frame.changes:
            lines.append(
                " ".join(
                    (
                        f"{frame.offset} {frame.stream}:",
                        change.phase,
                        change.confidence,
                        f"car {change.driver.racing_number}",
                        change.reason,
                    )
                )
            )
    return "\n".join(lines)


def _session_metadata(case: Mapping[str, Any]) -> SessionMetadata:
    session = case.get("session")
    if not isinstance(session, Mapping):
        raise ValueError("Incident fixture case must contain session metadata")
    return SessionMetadata(
        session_key=_required_string(session, "live_timing_path"),
        meeting_name=_string_or_none(session.get("meeting")),
        session_name=_string_or_none(session.get("session_name")),
        session_type=normalize_session_type(session.get("session_type")),
    )


def _session_info_payload(
    case: Mapping[str, Any], session: SessionMetadata
) -> dict[str, Any]:
    raw_session = case.get("session")
    if not isinstance(raw_session, Mapping):
        raise ValueError("Incident fixture case must contain session metadata")
    return {
        "Name": session.session_name,
        "Type": raw_session.get("session_type"),
        "StartDate": raw_session.get("start_date"),
        "Meeting": {"Name": session.meeting_name},
        "ArchiveStatus": {"Path": session.session_key},
    }


def _driver_metadata(case: Mapping[str, Any]) -> dict[str, DriverMetadata]:
    raw_drivers = case.get("drivers")
    if not isinstance(raw_drivers, Mapping):
        raise ValueError("Incident fixture case must contain drivers")

    drivers: dict[str, DriverMetadata] = {}
    for raw_number, raw_driver in raw_drivers.items():
        if not isinstance(raw_driver, Mapping):
            continue
        racing_number = str(raw_driver.get("racing_number") or raw_number)
        drivers[racing_number] = DriverMetadata(
            racing_number=racing_number,
            tla=_string_or_none(raw_driver.get("tla")),
            name=_string_or_none(raw_driver.get("full_name")),
            team=_string_or_none(raw_driver.get("team_name")),
        )
    return drivers


def _driver_list_payload(
    drivers: Mapping[str, DriverMetadata],
) -> dict[str, dict[str, str | None]]:
    return {
        racing_number: {
            "RacingNumber": driver.racing_number,
            "Tla": driver.tla,
            "FullName": driver.name,
            "TeamName": driver.team,
        }
        for racing_number, driver in drivers.items()
    }


def _ordered_frames(case: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    frames = case.get("frames")
    if not isinstance(frames, Sequence) or isinstance(frames, str):
        raise ValueError("Incident fixture case must contain frames")
    typed_frames = tuple(frame for frame in frames if isinstance(frame, Mapping))
    previous_offset: timedelta | None = None
    for frame in typed_frames:
        offset = _parse_offset_delta(_required_string(frame, "offset"))
        if previous_offset is not None and offset < previous_offset:
            raise ValueError("Incident replay frame offsets must be monotonic")
        previous_offset = offset
    return typed_frames


def _session_start_utc(case: Mapping[str, Any]) -> datetime:
    session = case.get("session")
    if not isinstance(session, Mapping):
        raise ValueError("Incident fixture case must contain session metadata")

    start_date = _required_string(session, "start_date")
    parsed_start = datetime.fromisoformat(start_date)
    if parsed_start.tzinfo is None:
        parsed_start = parsed_start.replace(
            tzinfo=timezone(
                _parse_offset_delta(_required_string(session, "gmt_offset"))
            )
        )
    return parsed_start.astimezone(UTC)


def _offset_to_datetime(offset: str, start_at: datetime) -> datetime:
    return start_at + _parse_offset_delta(offset)


def _parse_offset_delta(value: str) -> timedelta:
    sign = -1 if value.startswith("-") else 1
    text = value[1:] if value.startswith(("-", "+")) else value
    hour_text, minute_text, second_text = text.split(":", 2)
    seconds = float(second_text)
    whole_seconds = int(seconds)
    microseconds = round((seconds - whole_seconds) * 1_000_000)
    return sign * timedelta(
        hours=int(hour_text),
        minutes=int(minute_text),
        seconds=whole_seconds,
        microseconds=microseconds,
    )


def _validate_replay_stream(stream: str) -> None:
    if stream not in PUBLIC_REPLAY_STREAMS:
        raise ValueError(f"Unsupported public incident replay stream: {stream}")


def _assert_no_forbidden_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = "".join(
                char for char in str(key).lower() if char.isalnum()
            )
            if normalized_key in FORBIDDEN_FIXTURE_KEYS:
                raise ValueError("Incident replay fixture contains secret-like keys")
            _assert_no_forbidden_keys(item)
        return
    if isinstance(value, Sequence) and not isinstance(value, str):
        for item in value:
            _assert_no_forbidden_keys(item)


def _required_string(source: Any, key: str) -> str:
    if not isinstance(source, Mapping):
        raise ValueError(f"Expected mapping while reading {key}")
    value = source.get(key)
    text = _string_or_none(value)
    if text is None:
        raise ValueError(f"Missing required incident replay field: {key}")
    return text


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


if __name__ == "__main__":
    for replay_case in extracted_cases():
        print(format_replay_timeline(replay_manifest_case(replay_case)))
        print()
