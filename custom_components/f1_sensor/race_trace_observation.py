"""Frame-bound provenance shared by Race Trace timing and analysis consumers."""

from copy import deepcopy
import hashlib
import json
import math
from typing import Any
from uuid import uuid4

from .history import merge_analysis_session_info

RACE_TRACE_OBSERVATION_VERSION = 1
OBSERVATION_STREAMS = frozenset(
    {
        "SessionInfo",
        "TimingData",
        "TimingAppData",
        "TrackStatus",
        "PitStopSeries",
        "RaceControlMessages",
    }
)


def pending_observation(reason: str = "waiting_for_timing") -> dict[str, Any]:
    """Return stable keys without borrowing the current publication context."""
    return {
        "version": RACE_TRACE_OBSERVATION_VERSION,
        "status": "pending",
        "reason": reason,
        "context": None,
        "timing_as_of": None,
    }


class RaceTraceObservationSource:
    """Stamp a shared raw observation once, before existing subscriber fanout."""

    def __init__(self, entry_id: str) -> None:
        self.entry_id = entry_id
        self.reset()

    def reset(self) -> None:
        """Retire the previous source/rebuild epoch, even for the same session."""
        self.epoch = uuid4().hex
        self.sequence = 0
        self._session_info: dict[str, Any] = {}
        self._source: str | None = None
        self._replay_session_id: str | None = None

    def stamp(
        self,
        stream: str,
        payload: Any,
        *,
        source: str,
        replay_session_id: str | None,
        delay_epoch: int,
        delay_seconds: int,
    ) -> Any:
        """Never modify provider data or mint a cursor for merged snapshots."""
        if stream not in OBSERVATION_STREAMS or not isinstance(payload, dict):
            return payload
        if self._source is not None and (
            source != self._source
            or (source == "replay" and replay_session_id != self._replay_session_id)
        ):
            self.reset()
        self._source = source
        self._replay_session_id = replay_session_id
        if stream == "SessionInfo":
            merged, changed = merge_analysis_session_info(self._session_info, payload)
            if changed:
                self.epoch = uuid4().hex
                self.sequence = 0
            self._session_info = merged
        self.sequence += 1
        session_id = (
            replay_session_id
            if source == "replay"
            else self._session_info.get("Key") or self._session_info.get("Path")
        )
        context = {
            "entry_id": self.entry_id,
            "source": source,
            "session_id": str(session_id) if session_id is not None else None,
            "source_epoch": self.epoch,
            "delay_epoch": delay_epoch,
            "delay_seconds": delay_seconds,
        }
        context["token"] = hashlib.sha256(
            json.dumps(context, sort_keys=True).encode()
        ).hexdigest()[:32]
        cursor = None
        seconds = payload.get("_f1_source_time")
        domain = payload.get("_f1_source_domain")
        if (
            not payload.get("_f1_snapshot")
            and isinstance(seconds, (int, float))
            and not isinstance(seconds, bool)
            and math.isfinite(seconds)
            and 0 <= seconds < 9007199254740
            and domain == ("replay_offset" if source == "replay" else "utc")
        ):
            cursor = {
                "sequence": self.sequence,
                "source_time_ms": round(seconds * 1000),
                "time_domain": domain,
            }
        return {**payload, "_f1_observation": {"context": context, "cursor": cursor}}


def consumed_observation(
    payload: Any, *, delay_epoch: int, delay_seconds: int
) -> dict[str, Any]:
    """Validate the received epoch after the actual delayed callback runs."""
    raw = payload.get("_f1_observation") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        return pending_observation("missing_observation")
    context = raw.get("context")
    if not isinstance(context, dict) or not context.get("session_id"):
        return pending_observation("missing_session")
    if (
        context.get("delay_epoch") != delay_epoch
        or context.get("delay_seconds") != delay_seconds
    ):
        return pending_observation("delay_changed")
    cursor = raw.get("cursor")
    if not isinstance(cursor, dict):
        return pending_observation("unverified_snapshot_or_time")
    return {
        "version": RACE_TRACE_OBSERVATION_VERSION,
        "status": "ready",
        "reason": None,
        "context": deepcopy(context),
        "timing_as_of": deepcopy(cursor),
    }
