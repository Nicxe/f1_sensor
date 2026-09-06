"""Provider-neutral record envelope."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ProviderRecord:
    """One normalized record with provenance and revision metadata."""

    provider: str
    kind: str
    payload: Any
    source_session_id: str | None = None
    canonical_session_id: str | None = None
    event_timestamp: str | None = None
    received_timestamp: str | None = None
    revision: str | int | None = None
    sequence: int | None = None
    final: bool | None = None
    quality: str = "source"
    coverage_reason: str | None = None

    @classmethod
    def from_payload(
        cls,
        *,
        provider: str,
        kind: str,
        payload: Any,
        source_session_id: str | None = None,
        canonical_session_id: str | None = None,
        event_timestamp: str | None = None,
        received_timestamp: str | None = None,
        revision: str | int | None = None,
        sequence: int | None = None,
        final: bool | None = None,
        quality: str = "source",
        coverage_reason: str | None = None,
    ) -> ProviderRecord:
        """Create a record with a deterministic UTC receive timestamp."""
        return cls(
            provider=provider,
            kind=kind,
            payload=payload,
            source_session_id=source_session_id,
            canonical_session_id=canonical_session_id,
            event_timestamp=event_timestamp,
            received_timestamp=received_timestamp
            or datetime.now(UTC).isoformat(timespec="milliseconds"),
            revision=revision,
            sequence=sequence,
            final=final,
            quality=quality,
            coverage_reason=coverage_reason,
        )

    def as_dict(self, *, include_payload: bool = True) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        result: dict[str, Any] = {
            "provider": self.provider,
            "kind": self.kind,
            "source_session_id": self.source_session_id,
            "canonical_session_id": self.canonical_session_id,
            "event_timestamp": self.event_timestamp,
            "received_timestamp": self.received_timestamp,
            "revision": self.revision,
            "sequence": self.sequence,
            "final": self.final,
            "quality": self.quality,
            "coverage_reason": self.coverage_reason,
        }
        if include_payload:
            result["payload"] = self.payload
        return result
