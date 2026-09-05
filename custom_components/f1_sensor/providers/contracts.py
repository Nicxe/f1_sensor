"""Shared normalization contract for static, live, and replay providers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..models import ProviderRecord


def _first_text(*values: object) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _jolpica_context(payload: Any) -> tuple[str | None, str | None]:
    root = _mapping(payload)
    mr_data = _mapping(root.get("MRData"))
    table = _mapping(
        mr_data.get("RaceTable")
        or mr_data.get("StandingsTable")
        or mr_data.get("SeasonTable")
    )
    season = _first_text(table.get("season"))
    round_number = _first_text(table.get("round"))
    source_id = ":".join(part for part in (season, round_number) if part) or None
    return source_id, source_id


def _live_context(payload: Any) -> tuple[str | None, str | None, str | None]:
    root = _mapping(payload)
    meeting = _mapping(root.get("Meeting"))
    session_id = _first_text(
        root.get("Key"),
        root.get("SessionKey"),
        root.get("Path"),
    )
    meeting_id = _first_text(meeting.get("Key"), meeting.get("Name"))
    canonical = ":".join(part for part in (meeting_id, session_id) if part) or None
    event_timestamp = _first_text(
        root.get("Utc"),
        root.get("Timestamp"),
        root.get("timestamp"),
    )
    return session_id, canonical, event_timestamp


@dataclass(slots=True)
class ProviderRegistry:
    """Normalize every provider through one record contract."""

    latest: dict[tuple[str, str], ProviderRecord] = field(default_factory=dict)
    sequence: int = 0

    def normalize(
        self,
        provider: str,
        kind: str,
        payload: Any,
        *,
        revision: str | int | None = None,
        final: bool | None = None,
        quality: str = "source",
        coverage_reason: str | None = None,
    ) -> ProviderRecord:
        """Return and retain one provider-neutral record."""
        self.sequence += 1
        if provider == "jolpica":
            source_session_id, canonical_session_id = _jolpica_context(payload)
            event_timestamp = None
        else:
            source_session_id, canonical_session_id, event_timestamp = _live_context(
                payload
            )
        record = ProviderRecord.from_payload(
            provider=provider,
            kind=kind,
            payload=payload,
            source_session_id=source_session_id,
            canonical_session_id=canonical_session_id,
            event_timestamp=event_timestamp,
            revision=revision,
            sequence=self.sequence,
            final=final,
            quality=quality,
            coverage_reason=coverage_reason,
        )
        self.latest[(provider, kind)] = record
        return record

    def diagnostics(self) -> dict[str, Any]:
        """Return compact metadata without provider payloads."""
        return {
            "record_count": len(self.latest),
            "sequence": self.sequence,
            "latest": {
                f"{provider}:{kind}": record.as_dict(include_payload=False)
                for (provider, kind), record in sorted(self.latest.items())
            },
        }
