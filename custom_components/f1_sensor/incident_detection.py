from __future__ import annotations

import base64
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
import re
from typing import Any
import zlib

DEFAULT_SESSION_KEY = "unknown-session"

CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"
CONFIDENCE_ORDER = {
    CONFIDENCE_LOW: 0,
    CONFIDENCE_MEDIUM: 1,
    CONFIDENCE_HIGH: 2,
}

PHASE_CANDIDATE = "candidate"
PHASE_CONFIRMED = "confirmed"
PHASE_UPDATED = "updated"
PHASE_CLEARED = "cleared"

DATA_QUALITY_LIVE = "live"
DATA_QUALITY_REPLAY = "replay"
DATA_QUALITY_STALE = "stale"
DATA_QUALITY_BOOTSTRAP = "bootstrap"

TRACK_STATUS_CLEAR = "CLEAR"
TRACK_STATUS_YELLOW = "YELLOW"
TRACK_STATUS_VSC = "VSC"
TRACK_STATUS_SC = "SC"
TRACK_STATUS_RED = "RED"
TRACK_STATUS_INCIDENT_CONTEXT = frozenset(
    {
        TRACK_STATUS_YELLOW,
        TRACK_STATUS_VSC,
        TRACK_STATUS_SC,
        TRACK_STATUS_RED,
    }
)

SESSION_ACTIVE_STATUSES = frozenset(
    {
        "Started",
        "Resumed",
        "Green",
        "GreenFlag",
    }
)
SESSION_TERMINAL_STATUSES = frozenset(
    {
        "Ended",
        "Ends",
        "Finalised",
        "Finished",
        "Inactive",
    }
)

_TRACK_STATUS_ALIASES = {
    "ALLCLEAR": TRACK_STATUS_CLEAR,
    "CLEAR": TRACK_STATUS_CLEAR,
    "YELLOW": TRACK_STATUS_YELLOW,
    "DOUBLE YELLOW": TRACK_STATUS_YELLOW,
    "DOUBLEYELLOW": TRACK_STATUS_YELLOW,
    "VSC": TRACK_STATUS_VSC,
    "VSCDEPLOYED": TRACK_STATUS_VSC,
    "VSC DEPLOYED": TRACK_STATUS_VSC,
    "VSC ENDING": TRACK_STATUS_VSC,
    "VSCENDING": TRACK_STATUS_VSC,
    "SAFETY CAR": TRACK_STATUS_SC,
    "SAFETYCAR": TRACK_STATUS_SC,
    "SC": TRACK_STATUS_SC,
    "SC DEPLOYED": TRACK_STATUS_SC,
    "SCDEPLOYED": TRACK_STATUS_SC,
    "SC ENDING": TRACK_STATUS_SC,
    "RED": TRACK_STATUS_RED,
    "RED FLAG": TRACK_STATUS_RED,
    "REDFLAG": TRACK_STATUS_RED,
}

_TRACK_STATUS_CODES = {
    "1": TRACK_STATUS_CLEAR,
    "2": TRACK_STATUS_YELLOW,
    "4": TRACK_STATUS_SC,
    "5": TRACK_STATUS_RED,
    "6": TRACK_STATUS_VSC,
    "7": TRACK_STATUS_VSC,
    "8": TRACK_STATUS_CLEAR,
}

_SESSION_TYPE_PATTERNS = (
    ("testing", ("test", "testing")),
    ("sprint", ("sprint",)),
    ("qualifying", ("qualifying", "sprint shootout", "shootout")),
    ("practice", ("practice", "free practice", "fp1", "fp2", "fp3")),
    ("race", ("race", "grand prix")),
)

_INCIDENT_KEYWORDS = frozenset(
    {
        "ACCIDENT",
        "CRASH",
        "DOUBLE YELLOW",
        "INCIDENT",
        "OFF TRACK",
        "RED FLAG",
        "SPUN",
        "STOP",
        "STOPPED",
        "YELLOW",
    }
)
_RACE_CONTROL_CLEAR_WORDS = frozenset({"CLEAR", "ALL CLEAR"})
_SAFETY_CAR_KEYWORDS = frozenset(
    {
        "SAFETY CAR",
        "SC DEPLOYED",
        "SCDEPLOYED",
        "VSC",
        "VSC DEPLOYED",
        "VSCDEPLOYED",
    }
)

_CAR_WORD_RE = re.compile(r"\b(?:CAR|CARS|DRIVER|DRIVERS)\s+(\d{1,3})\b", re.I)
_NUMBER_TLA_RE = re.compile(r"\b(\d{1,3})\s*\([A-Z]{2,4}\)\b", re.I)
_RACE_CONTROL_LAP_DELETION_RE = re.compile(r"\b(?:LAP\s+DELETED|TIME\b.*\bDELETED)\b")
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")

_CAR_DATA_SPEED_CHANNEL = "2"
_CAR_DATA_MAX_REASONABLE_SPEED_KPH = 450.0
_CAR_LOW_SPEED_SIGNAL = "car_low_speed"
_CAR_MOVING_SIGNAL = "car_moving"


@dataclass(frozen=True, slots=True)
class DriverMetadata:
    racing_number: str
    tla: str | None = None
    name: str | None = None
    team: str | None = None
    team_color: str | None = None

    def to_event_payload(self) -> dict[str, str | None]:
        return {
            "racing_number": self.racing_number,
            "tla": self.tla,
            "name": self.name,
            "team": self.team,
        }


@dataclass(frozen=True, slots=True)
class SessionMetadata:
    session_key: str = DEFAULT_SESSION_KEY
    meeting_name: str | None = None
    session_name: str | None = None
    session_type: str | None = None

    def to_event_payload(self) -> dict[str, str | None]:
        return {
            "meeting_name": self.meeting_name,
            "session_name": self.session_name,
            "session_type": self.session_type,
            "session_key": self.session_key,
        }


@dataclass(frozen=True, slots=True)
class TrackStatusContext:
    status: str | None = None
    message: str | None = None

    def to_event_payload(self) -> dict[str, str | None]:
        return {
            "status": self.status,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class RaceControlContext:
    message: str | None = None
    category: str | None = None
    flag: str | None = None

    def to_event_payload(self) -> dict[str, str | None]:
        return {
            "message": self.message,
            "category": self.category,
            "flag": self.flag,
        }


@dataclass(frozen=True, slots=True)
class IncidentSignal:
    kind: str
    observed_at: datetime
    session_key: str = DEFAULT_SESSION_KEY
    racing_number: str | None = None
    value: bool | str | int | None = None
    data_quality: str = DATA_QUALITY_LIVE
    confidence_hint: str | None = None
    reason: str | None = None
    message: str | None = None
    category: str | None = None
    flag: str | None = None
    track_status: str | None = None
    driver: DriverMetadata | None = None
    session: SessionMetadata | None = None
    signals: tuple[str, ...] = ()
    raw_id: str | None = None


@dataclass(frozen=True, slots=True)
class IncidentChange:
    incident_id: str
    phase: str
    confidence: str
    reason: str
    driver: DriverMetadata
    session: SessionMetadata
    track_status: TrackStatusContext
    race_control: RaceControlContext
    signals: tuple[str, ...]
    started_at: datetime
    updated_at: datetime
    data_quality: str

    def to_event_payload(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "phase": self.phase,
            "confidence": self.confidence,
            "reason": self.reason,
            "driver": self.driver.to_event_payload(),
            "session": self.session.to_event_payload(),
            "track_status": self.track_status.to_event_payload(),
            "race_control": self.race_control.to_event_payload(),
            "signals": list(self.signals),
            "started_at": _format_utc(self.started_at),
            "updated_at": _format_utc(self.updated_at),
            "data_quality": self.data_quality,
        }


@dataclass(slots=True)
class _ActiveIncident:
    incident_id: str
    phase: str
    confidence: str
    reason: str
    driver: DriverMetadata
    session: SessionMetadata
    track_status: TrackStatusContext
    race_control: RaceControlContext
    signals: list[str]
    started_at: datetime
    updated_at: datetime
    data_quality: str


@dataclass(frozen=True, slots=True)
class _CarSpeedSample:
    observed_at: datetime
    speed_kph: float
    data_quality: str


@dataclass(slots=True)
class _DriverState:
    in_pit: bool | None = None
    pit_out: bool | None = None
    pit_out_at: datetime | None = None
    retired: bool | None = None
    stopped: bool | None = None
    seen_stopped_signal: bool = False
    active_incident: _ActiveIncident | None = None
    last_cleared_at: datetime | None = None
    car_speed_samples: deque[_CarSpeedSample] = field(
        default_factory=lambda: deque(maxlen=512)
    )


@dataclass(slots=True)
class _SessionState:
    metadata: SessionMetadata = field(default_factory=SessionMetadata)
    active: bool = True
    drivers: dict[str, DriverMetadata] = field(default_factory=dict)
    driver_states: dict[str, _DriverState] = field(default_factory=dict)
    track_status_history: deque[IncidentSignal] = field(
        default_factory=lambda: deque(maxlen=256)
    )
    race_control_history: deque[IncidentSignal] = field(
        default_factory=lambda: deque(maxlen=256)
    )
    incident_history: deque[str] = field(default_factory=lambda: deque(maxlen=256))


class IncidentDetector:
    """State machine for stopped/on-track incident detection."""

    def __init__(
        self,
        *,
        correlation_window: timedelta = timedelta(seconds=120),
        pit_out_hold: timedelta = timedelta(seconds=6),
        cooldown: timedelta = timedelta(seconds=120),
        max_history: int = 256,
        car_low_speed_threshold_kph: float = 10.0,
        car_stationary_threshold_kph: float = 3.0,
        car_moving_clear_threshold_kph: float = 20.0,
        car_low_speed_duration: timedelta = timedelta(seconds=5),
        car_stationary_duration: timedelta = timedelta(seconds=2),
        car_moving_clear_duration: timedelta = timedelta(seconds=5),
        car_context_window: timedelta = timedelta(seconds=20),
        car_data_stale_after: timedelta = timedelta(seconds=10),
        car_candidate_limit: int = 3,
    ) -> None:
        self._correlation_window = correlation_window
        self._pit_out_hold = pit_out_hold
        self._cooldown = cooldown
        self._sessions: dict[str, _SessionState] = {}
        self._max_history = max(1, max_history)
        self._car_low_speed_threshold_kph = max(0.0, car_low_speed_threshold_kph)
        self._car_stationary_threshold_kph = max(0.0, car_stationary_threshold_kph)
        self._car_moving_clear_threshold_kph = max(0.0, car_moving_clear_threshold_kph)
        self._car_low_speed_duration = car_low_speed_duration
        self._car_stationary_duration = car_stationary_duration
        self._car_moving_clear_duration = car_moving_clear_duration
        self._car_context_window = car_context_window
        self._car_data_stale_after = car_data_stale_after
        self._car_candidate_limit = max(1, car_candidate_limit)

    def process_signals(
        self, signals: Iterable[IncidentSignal]
    ) -> list[IncidentChange]:
        changes: list[IncidentChange] = []
        for signal in signals:
            normalized_signal = _normalize_signal_datetime(signal)
            state = self._session_state(normalized_signal)
            changes.extend(self._process_signal(state, normalized_signal))
        return changes

    def process_stream(
        self,
        stream: str,
        payload: Any,
        observed_at: datetime | str | None = None,
        *,
        session: SessionMetadata | None = None,
        drivers: Mapping[str, DriverMetadata] | None = None,
        data_quality: str = DATA_QUALITY_LIVE,
    ) -> list[IncidentChange]:
        return self.process_signals(
            normalize_stream(
                stream,
                payload,
                observed_at,
                session=session,
                drivers=drivers,
                data_quality=data_quality,
            )
        )

    def get_active_incident(
        self, session_key: str, racing_number: str
    ) -> IncidentChange | None:
        session = self._sessions.get(session_key)
        if session is None:
            return None
        driver = session.driver_states.get(str(racing_number))
        if driver is None or driver.active_incident is None:
            return None
        return self._make_change(driver.active_incident, driver.active_incident.phase)

    def active_incidents(
        self, session_key: str | None = None
    ) -> tuple[IncidentChange, ...]:
        states: Iterable[_SessionState]
        if session_key is None:
            states = self._sessions.values()
        else:
            state = self._sessions.get(session_key)
            states = () if state is None else (state,)

        incidents: list[IncidentChange] = []
        for state in states:
            for driver_state in state.driver_states.values():
                if driver_state.active_incident is not None:
                    incidents.append(
                        self._make_change(
                            driver_state.active_incident,
                            driver_state.active_incident.phase,
                        )
                    )
        return tuple(incidents)

    def _session_state(self, signal: IncidentSignal) -> _SessionState:
        key = signal.session.session_key if signal.session else signal.session_key
        if not key:
            key = DEFAULT_SESSION_KEY
        state = self._sessions.get(key)
        if state is None:
            metadata = signal.session or SessionMetadata(session_key=key)
            state = _SessionState(
                metadata=metadata,
                track_status_history=deque(maxlen=self._max_history),
                race_control_history=deque(maxlen=self._max_history),
                incident_history=deque(maxlen=self._max_history),
            )
            self._sessions[key] = state
        elif signal.session is not None:
            state.metadata = _merge_session_metadata(state.metadata, signal.session)
        return state

    def _process_signal(
        self, state: _SessionState, signal: IncidentSignal
    ) -> list[IncidentChange]:
        if signal.driver is not None:
            state.drivers[signal.driver.racing_number] = signal.driver
        if signal.kind == "session_context" and signal.session is not None:
            state.metadata = _merge_session_metadata(state.metadata, signal.session)
            return []
        if signal.kind == "driver_metadata" and signal.driver is not None:
            state.drivers[signal.driver.racing_number] = signal.driver
            self._refresh_active_driver_metadata(state, signal.driver)
            return []
        if signal.kind == "session_status":
            return self._apply_session_status(state, signal)
        if signal.kind == "track_status":
            return self._apply_track_status(state, signal)
        if signal.kind == "race_control":
            return self._apply_race_control(state, signal)
        if signal.kind == "data_gap":
            return []
        if signal.kind == "car_speed" and signal.racing_number is not None:
            return self._apply_car_speed(state, signal)
        if signal.kind.startswith("timing_") and signal.racing_number is not None:
            return self._apply_timing(state, signal)
        return []

    def _apply_session_status(
        self, state: _SessionState, signal: IncidentSignal
    ) -> list[IncidentChange]:
        status = str(signal.value or "").strip()
        if status in SESSION_ACTIVE_STATUSES:
            state.active = True
            return []
        if status not in SESSION_TERMINAL_STATUSES:
            return []

        state.active = False
        changes: list[IncidentChange] = []
        for driver_state in state.driver_states.values():
            if driver_state.active_incident is None:
                continue
            active = driver_state.active_incident
            _append_unique(active.signals, "session_ended")
            active.reason = "session_ended"
            active.updated_at = signal.observed_at
            change = self._make_change(active, PHASE_CLEARED)
            changes.append(change)
            driver_state.last_cleared_at = signal.observed_at
            driver_state.active_incident = None
        return changes

    def _apply_track_status(
        self, state: _SessionState, signal: IncidentSignal
    ) -> list[IncidentChange]:
        if signal.track_status is None:
            return []
        state.track_status_history.append(signal)
        if signal.track_status not in TRACK_STATUS_INCIDENT_CONTEXT:
            return []

        changes: list[IncidentChange] = []
        for rn, driver_state in state.driver_states.items():
            active = driver_state.active_incident
            if active is None or active.phase != PHASE_CONFIRMED:
                continue
            if not _is_within(
                signal.observed_at, active.started_at, self._correlation_window
            ):
                continue
            if active.confidence == CONFIDENCE_HIGH:
                continue
            context = TrackStatusContext(signal.track_status, signal.message)
            active.track_status = context
            active.confidence = CONFIDENCE_HIGH
            active.reason = _reason_for_context(track_context=context)
            active.updated_at = signal.observed_at
            _append_unique(
                active.signals, "track_status_" + signal.track_status.lower()
            )
            changes.append(self._make_change(active, PHASE_UPDATED))
            self._remember_incident(state, active.incident_id)
            state.driver_states[rn] = driver_state
        changes.extend(self._start_car_candidates_from_context(state, signal))
        return changes

    def _apply_race_control(
        self, state: _SessionState, signal: IncidentSignal
    ) -> list[IncidentChange]:
        state.race_control_history.append(signal)
        if not _race_control_is_context(signal):
            return []

        changes: list[IncidentChange] = []
        if signal.racing_number is None:
            return self._start_car_candidates_from_context(state, signal)

        driver_state = self._driver_state(state, signal.racing_number)
        active = driver_state.active_incident
        if active is not None:
            if not _is_within(
                signal.observed_at, active.started_at, self._correlation_window
            ):
                return []
            rc_context = RaceControlContext(
                signal.message, signal.category, signal.flag
            )
            active.race_control = rc_context
            _extend_unique(active.signals, signal.signals or ("race_control_incident",))
            active.updated_at = signal.observed_at
            if (
                active.phase == PHASE_CANDIDATE
                and _CAR_LOW_SPEED_SIGNAL in active.signals
            ):
                previous = (
                    active.phase,
                    active.confidence,
                    active.reason,
                    tuple(active.signals),
                    active.race_control,
                )
                if "race_control_stopped" in signal.signals:
                    active.phase = PHASE_CONFIRMED
                    active.confidence = CONFIDENCE_HIGH
                    active.reason = "race_control_stopped_with_car_low_speed"
                    changes.append(self._make_change(active, PHASE_CONFIRMED))
                    self._remember_incident(state, active.incident_id)
                    return changes
                active.reason = "car_low_speed_with_race_control"
                current = (
                    active.phase,
                    active.confidence,
                    active.reason,
                    tuple(active.signals),
                    active.race_control,
                )
                if current == previous:
                    return []
                changes.append(self._make_change(active, PHASE_UPDATED))
                self._remember_incident(state, active.incident_id)
                return changes
            if _confidence_gt(CONFIDENCE_HIGH, active.confidence):
                active.confidence = CONFIDENCE_HIGH
                active.reason = "timing_stopped_with_race_control"
                changes.append(self._make_change(active, PHASE_UPDATED))
                self._remember_incident(state, active.incident_id)
            return changes

        car_candidate = self._start_car_candidate_from_context(
            state, signal.racing_number, signal
        )
        if car_candidate:
            return car_candidate

        if not driver_state.seen_stopped_signal or not state.active:
            return []
        if driver_state.stopped is True:
            return self._start_or_update_stopped_incident(
                state, signal.racing_number, signal
            )
        return self._start_candidate_incident(state, signal.racing_number, signal)

    def _apply_timing(
        self, state: _SessionState, signal: IncidentSignal
    ) -> list[IncidentChange]:
        driver_state = self._driver_state(state, signal.racing_number)

        if signal.kind == "timing_in_pit":
            driver_state.in_pit = _coerce_bool(signal.value)
            if driver_state.in_pit is True and driver_state.active_incident is not None:
                return self._clear_driver_incident(
                    driver_state,
                    signal,
                    reason="pit",
                    signal_name="pit_suppressed",
                )
            return []

        if signal.kind == "timing_pit_out":
            pit_out = _coerce_bool(signal.value)
            driver_state.pit_out = pit_out
            if pit_out is True:
                driver_state.pit_out_at = signal.observed_at
            return []

        if signal.kind == "timing_retired":
            driver_state.retired = _coerce_bool(signal.value)
            return []

        if signal.kind != "timing_stopped":
            return []

        stopped = _coerce_bool(signal.value)
        if stopped is None:
            return []

        if not driver_state.seen_stopped_signal:
            driver_state.seen_stopped_signal = True
            driver_state.stopped = stopped
            return []

        previous = driver_state.stopped
        driver_state.stopped = stopped
        if stopped is False:
            if driver_state.active_incident is None:
                return []
            return self._clear_driver_incident(
                driver_state,
                signal,
                reason="timing_moving",
                signal_name="timing_moving",
            )

        if previous is True:
            return []
        return self._start_or_update_stopped_incident(
            state, signal.racing_number, signal
        )

    def _apply_car_speed(
        self, state: _SessionState, signal: IncidentSignal
    ) -> list[IncidentChange]:
        driver_state = self._driver_state(state, signal.racing_number)
        speed = _coerce_float(signal.value)
        if speed is None:
            return []

        sample = _CarSpeedSample(
            observed_at=signal.observed_at,
            speed_kph=speed,
            data_quality=signal.data_quality,
        )
        driver_state.car_speed_samples.append(sample)
        self._prune_car_speed_samples(driver_state, signal.observed_at)

        if signal.data_quality in {DATA_QUALITY_BOOTSTRAP, DATA_QUALITY_STALE}:
            return []
        if not state.active:
            return []

        moving_change = self._clear_car_candidate_after_movement(
            driver_state, signal, speed
        )
        if moving_change:
            return moving_change

        if speed > self._car_low_speed_threshold_kph:
            return []

        track_context, race_context, context_signals = self._find_context(
            state,
            signal.racing_number,
            signal.observed_at,
            window=self._car_context_window,
        )
        if not context_signals:
            return []
        if not self._car_candidate_allowed(driver_state, signal.observed_at):
            return []
        return self._start_or_update_car_candidate(
            state,
            signal.racing_number,
            signal,
            track_context=track_context,
            race_context=race_context,
            context_signals=context_signals,
        )

    def _start_car_candidates_from_context(
        self, state: _SessionState, context_signal: IncidentSignal
    ) -> list[IncidentChange]:
        if context_signal.data_quality in {DATA_QUALITY_BOOTSTRAP, DATA_QUALITY_STALE}:
            return []
        if not state.active:
            return []

        candidates = [
            rn
            for rn, driver_state in state.driver_states.items()
            if self._car_candidate_allowed(driver_state, context_signal.observed_at)
            and self._car_low_speed_context(driver_state, context_signal.observed_at)
            is not None
        ]
        if len(candidates) > self._car_candidate_limit:
            return []

        changes: list[IncidentChange] = []
        for rn in candidates:
            changes.extend(
                self._start_car_candidate_from_context(state, rn, context_signal)
            )
        return changes

    def _start_car_candidate_from_context(
        self, state: _SessionState, racing_number: str, context_signal: IncidentSignal
    ) -> list[IncidentChange]:
        driver_state = self._driver_state(state, racing_number)
        if not self._car_candidate_allowed(driver_state, context_signal.observed_at):
            return []
        if (
            self._car_low_speed_context(driver_state, context_signal.observed_at)
            is None
        ):
            return []

        track_context, race_context, context_signals = self._context_from_signal(
            state, racing_number, context_signal
        )
        if not context_signals:
            return []

        return self._start_or_update_car_candidate(
            state,
            racing_number,
            context_signal,
            track_context=track_context,
            race_context=race_context,
            context_signals=context_signals,
        )

    def _start_or_update_car_candidate(
        self,
        state: _SessionState,
        racing_number: str,
        signal: IncidentSignal,
        *,
        track_context: TrackStatusContext,
        race_context: RaceControlContext,
        context_signals: list[str],
    ) -> list[IncidentChange]:
        driver_state = self._driver_state(state, racing_number)
        active = driver_state.active_incident
        if active is None and not self._has_car_candidate_capacity(state):
            return []
        if not self._car_candidate_allowed(driver_state, signal.observed_at):
            return []
        low_speed = self._car_low_speed_context(driver_state, signal.observed_at)
        if low_speed is None:
            return []
        low_speed_started_at, stationary = low_speed
        if self._is_in_cooldown(driver_state, signal.observed_at):
            return []

        driver = self._driver_metadata(state, racing_number, signal.driver)
        signals = [_CAR_LOW_SPEED_SIGNAL, *context_signals]
        if stationary:
            signals.insert(0, "car_stationary")
        reason = _reason_for_car_context(
            track_context=track_context,
            race_context=race_context,
        )
        confidence = CONFIDENCE_MEDIUM

        if active is None:
            active = _ActiveIncident(
                incident_id=_build_incident_id(
                    state.metadata.session_key, racing_number, low_speed_started_at
                ),
                phase=PHASE_CANDIDATE,
                confidence=confidence,
                reason=reason,
                driver=driver,
                session=state.metadata,
                track_status=track_context,
                race_control=race_context,
                signals=signals,
                started_at=low_speed_started_at,
                updated_at=signal.observed_at,
                data_quality=signal.data_quality,
            )
            driver_state.active_incident = active
            self._remember_incident(state, active.incident_id)
            return [self._make_change(active, PHASE_CANDIDATE)]

        if active.phase != PHASE_CANDIDATE:
            return []

        previous_signals = tuple(active.signals)
        previous_confidence = active.confidence
        previous_reason = active.reason
        active.driver = driver
        active.session = state.metadata
        active.track_status = _merge_track_context(active.track_status, track_context)
        active.race_control = _merge_race_context(active.race_control, race_context)
        _extend_unique(active.signals, signals)
        if _confidence_gt(confidence, active.confidence):
            active.confidence = confidence
        active.reason = reason or active.reason
        if (
            previous_signals == tuple(active.signals)
            and previous_confidence == active.confidence
            and previous_reason == active.reason
        ):
            return []
        active.updated_at = signal.observed_at
        self._remember_incident(state, active.incident_id)
        return [self._make_change(active, PHASE_UPDATED)]

    def _clear_car_candidate_after_movement(
        self, driver_state: _DriverState, signal: IncidentSignal, speed: float
    ) -> list[IncidentChange]:
        active = driver_state.active_incident
        if active is None or active.phase != PHASE_CANDIDATE:
            return []
        if _CAR_LOW_SPEED_SIGNAL not in active.signals:
            return []
        if speed <= self._car_moving_clear_threshold_kph:
            return []
        moving_since = self._car_moving_since(driver_state)
        if moving_since is None:
            return []
        if signal.observed_at - moving_since < self._car_moving_clear_duration:
            return []
        return self._clear_driver_incident(
            driver_state,
            signal,
            reason="car_moving",
            signal_name=_CAR_MOVING_SIGNAL,
        )

    def _start_candidate_incident(
        self, state: _SessionState, racing_number: str, signal: IncidentSignal
    ) -> list[IncidentChange]:
        driver_state = self._driver_state(state, racing_number)
        if self._is_in_cooldown(driver_state, signal.observed_at):
            return []
        driver = self._driver_metadata(state, racing_number, signal.driver)
        incident = _ActiveIncident(
            incident_id=_build_incident_id(
                state.metadata.session_key, racing_number, signal.observed_at
            ),
            phase=PHASE_CANDIDATE,
            confidence=signal.confidence_hint or CONFIDENCE_MEDIUM,
            reason=signal.reason or "race_control_incident",
            driver=driver,
            session=state.metadata,
            track_status=TrackStatusContext(),
            race_control=RaceControlContext(
                signal.message, signal.category, signal.flag
            ),
            signals=list(signal.signals or ("race_control_incident",)),
            started_at=signal.observed_at,
            updated_at=signal.observed_at,
            data_quality=signal.data_quality,
        )
        driver_state.active_incident = incident
        self._remember_incident(state, incident.incident_id)
        return [self._make_change(incident, PHASE_CANDIDATE)]

    def _start_or_update_stopped_incident(
        self, state: _SessionState, racing_number: str, signal: IncidentSignal
    ) -> list[IncidentChange]:
        driver_state = self._driver_state(state, racing_number)
        if not state.active:
            return []
        if driver_state.in_pit is True:
            return []
        if self._is_recent_pit_out(driver_state, signal.observed_at):
            return []
        if self._is_in_cooldown(driver_state, signal.observed_at):
            return []

        track_context, race_context, context_signals = self._find_context(
            state, racing_number, signal.observed_at
        )
        confidence = CONFIDENCE_HIGH if context_signals else CONFIDENCE_MEDIUM
        reason = _reason_for_context(
            track_context=track_context,
            race_context=race_context,
        )
        driver = self._driver_metadata(state, racing_number, signal.driver)
        active = driver_state.active_incident
        if (
            active is not None
            and active.phase == PHASE_CANDIDATE
            and not _is_within(
                active.started_at, signal.observed_at, self._correlation_window
            )
        ):
            driver_state.active_incident = None
            active = None

        if active is None:
            active = _ActiveIncident(
                incident_id=_build_incident_id(
                    state.metadata.session_key, racing_number, signal.observed_at
                ),
                phase=PHASE_CONFIRMED,
                confidence=confidence,
                reason=reason,
                driver=driver,
                session=state.metadata,
                track_status=track_context,
                race_control=race_context,
                signals=["timing_stopped", *context_signals],
                started_at=signal.observed_at,
                updated_at=signal.observed_at,
                data_quality=signal.data_quality,
            )
            driver_state.active_incident = active
            self._remember_incident(state, active.incident_id)
            return [self._make_change(active, PHASE_CONFIRMED)]

        active.driver = driver
        active.session = state.metadata
        active.updated_at = signal.observed_at
        active.track_status = track_context
        active.race_control = race_context
        _append_unique(active.signals, "timing_stopped")
        _extend_unique(active.signals, context_signals)

        if active.phase == PHASE_CANDIDATE:
            active.phase = PHASE_CONFIRMED
            active.confidence = confidence
            active.reason = reason
            self._remember_incident(state, active.incident_id)
            return [self._make_change(active, PHASE_CONFIRMED)]

        if _confidence_gt(confidence, active.confidence):
            active.confidence = confidence
            active.reason = reason
            self._remember_incident(state, active.incident_id)
            return [self._make_change(active, PHASE_UPDATED)]
        return []

    def _clear_driver_incident(
        self,
        driver_state: _DriverState,
        signal: IncidentSignal,
        *,
        reason: str,
        signal_name: str,
    ) -> list[IncidentChange]:
        active = driver_state.active_incident
        if active is None:
            return []
        active.reason = reason
        active.updated_at = signal.observed_at
        _append_unique(active.signals, signal_name)
        change = self._make_change(active, PHASE_CLEARED)
        driver_state.last_cleared_at = signal.observed_at
        driver_state.active_incident = None
        return [change]

    def _find_context(
        self,
        state: _SessionState,
        racing_number: str,
        at: datetime,
        *,
        window: timedelta | None = None,
    ) -> tuple[TrackStatusContext, RaceControlContext, list[str]]:
        correlation_window = self._correlation_window if window is None else window
        track_context = TrackStatusContext()
        race_context = RaceControlContext()
        signals: list[str] = []

        for signal in reversed(state.track_status_history):
            if signal.track_status not in TRACK_STATUS_INCIDENT_CONTEXT:
                continue
            if not _is_within(signal.observed_at, at, correlation_window):
                continue
            track_context = TrackStatusContext(signal.track_status, signal.message)
            signals.append("track_status_" + signal.track_status.lower())
            break

        for signal in reversed(state.race_control_history):
            if not _race_control_is_context(signal):
                continue
            if signal.racing_number not in (None, racing_number):
                continue
            if not _is_within(signal.observed_at, at, correlation_window):
                continue
            race_context = RaceControlContext(
                signal.message, signal.category, signal.flag
            )
            _extend_unique(signals, signal.signals or ("race_control_incident",))
            break

        return track_context, race_context, signals

    def _driver_metadata(
        self,
        state: _SessionState,
        racing_number: str,
        signal_driver: DriverMetadata | None = None,
    ) -> DriverMetadata:
        driver = signal_driver or state.drivers.get(racing_number)
        if driver is not None:
            return driver
        return DriverMetadata(racing_number=racing_number, name=racing_number)

    def _driver_state(
        self, state: _SessionState, racing_number: str | None
    ) -> _DriverState:
        rn = str(racing_number or "").strip()
        return state.driver_states.setdefault(rn, _DriverState())

    def _refresh_active_driver_metadata(
        self, state: _SessionState, driver: DriverMetadata
    ) -> None:
        driver_state = state.driver_states.get(driver.racing_number)
        if driver_state is None or driver_state.active_incident is None:
            return
        driver_state.active_incident.driver = driver

    def _is_recent_pit_out(self, state: _DriverState, at: datetime) -> bool:
        if state.pit_out is True:
            return True
        if state.pit_out_at is None:
            return False
        return timedelta(0) <= at - state.pit_out_at <= self._pit_out_hold

    def _is_in_cooldown(self, state: _DriverState, at: datetime) -> bool:
        if state.last_cleared_at is None:
            return False
        return timedelta(0) <= at - state.last_cleared_at < self._cooldown

    def _prune_car_speed_samples(self, state: _DriverState, at: datetime) -> None:
        retention = max(
            self._correlation_window,
            timedelta(seconds=90),
            key=lambda value: value.total_seconds(),
        )
        cutoff = at - retention
        while (
            state.car_speed_samples and state.car_speed_samples[0].observed_at < cutoff
        ):
            state.car_speed_samples.popleft()

    def _car_candidate_allowed(self, state: _DriverState, at: datetime) -> bool:
        if state.in_pit is True:
            return False
        if self._is_recent_pit_out(state, at):
            return False
        if self._is_in_cooldown(state, at):
            return False
        active = state.active_incident
        return active is None or active.phase == PHASE_CANDIDATE

    def _has_car_candidate_capacity(self, state: _SessionState) -> bool:
        active_car_candidates = 0
        for driver_state in state.driver_states.values():
            active = driver_state.active_incident
            if (
                active is not None
                and active.phase == PHASE_CANDIDATE
                and _CAR_LOW_SPEED_SIGNAL in active.signals
            ):
                active_car_candidates += 1
        return active_car_candidates < self._car_candidate_limit

    def _car_low_speed_context(
        self, state: _DriverState, at: datetime
    ) -> tuple[datetime, bool] | None:
        samples = self._valid_car_samples(state, at)
        if not samples:
            return None

        latest = samples[-1]
        if latest.speed_kph > self._car_low_speed_threshold_kph:
            return None

        low_speed_started_at = latest.observed_at
        stationary_started_at = (
            latest.observed_at
            if latest.speed_kph <= self._car_stationary_threshold_kph
            else None
        )
        for sample in reversed(samples[:-1]):
            if sample.speed_kph > self._car_low_speed_threshold_kph:
                break
            low_speed_started_at = sample.observed_at
            if sample.speed_kph <= self._car_stationary_threshold_kph:
                stationary_started_at = sample.observed_at
            else:
                stationary_started_at = None

        low_speed_duration = at - low_speed_started_at
        stationary = (
            stationary_started_at is not None
            and at - stationary_started_at >= self._car_stationary_duration
        )
        if low_speed_duration < self._car_low_speed_duration and not stationary:
            return None
        return low_speed_started_at, stationary

    def _car_moving_since(self, state: _DriverState) -> datetime | None:
        samples = [
            sample
            for sample in state.car_speed_samples
            if sample.data_quality not in {DATA_QUALITY_BOOTSTRAP, DATA_QUALITY_STALE}
        ]
        if not samples:
            return None
        latest = samples[-1]
        if latest.speed_kph <= self._car_moving_clear_threshold_kph:
            return None
        moving_since = latest.observed_at
        for sample in reversed(samples[:-1]):
            if sample.speed_kph <= self._car_moving_clear_threshold_kph:
                break
            moving_since = sample.observed_at
        return moving_since

    def _valid_car_samples(
        self, state: _DriverState, at: datetime
    ) -> list[_CarSpeedSample]:
        freshness_window = min(
            self._car_context_window,
            self._car_data_stale_after,
            key=lambda value: value.total_seconds(),
        )
        samples = [
            sample
            for sample in state.car_speed_samples
            if sample.data_quality not in {DATA_QUALITY_BOOTSTRAP, DATA_QUALITY_STALE}
            and timedelta(0) <= at - sample.observed_at <= freshness_window
        ]
        samples.sort(key=lambda sample: sample.observed_at)
        return samples

    def _context_from_signal(
        self,
        state: _SessionState,
        racing_number: str,
        context_signal: IncidentSignal,
    ) -> tuple[TrackStatusContext, RaceControlContext, list[str]]:
        return self._find_context(
            state,
            racing_number,
            context_signal.observed_at,
            window=self._car_context_window,
        )

    def _remember_incident(self, state: _SessionState, incident_id: str) -> None:
        if incident_id not in state.incident_history:
            state.incident_history.append(incident_id)

    @staticmethod
    def _make_change(active: _ActiveIncident, phase: str) -> IncidentChange:
        return IncidentChange(
            incident_id=active.incident_id,
            phase=phase,
            confidence=active.confidence,
            reason=active.reason,
            driver=active.driver,
            session=active.session,
            track_status=active.track_status,
            race_control=active.race_control,
            signals=tuple(active.signals),
            started_at=active.started_at,
            updated_at=active.updated_at,
            data_quality=active.data_quality,
        )


def normalize_stream(
    stream: str,
    payload: Any,
    observed_at: datetime | str | None = None,
    *,
    session: SessionMetadata | None = None,
    drivers: Mapping[str, DriverMetadata] | None = None,
    data_quality: str = DATA_QUALITY_LIVE,
) -> list[IncidentSignal]:
    if stream == "TimingData":
        return normalize_timing_data(
            payload,
            observed_at,
            session=session,
            drivers=drivers,
            data_quality=data_quality,
        )
    if stream == "TrackStatus":
        return normalize_track_status(
            payload,
            observed_at,
            session=session,
            data_quality=data_quality,
        )
    if stream == "RaceControlMessages":
        return normalize_race_control_messages(
            payload,
            observed_at,
            session=session,
            drivers=drivers,
            data_quality=data_quality,
        )
    if stream == "SessionInfo":
        return normalize_session_info(
            payload,
            observed_at,
            session=session,
            data_quality=data_quality,
        )
    if stream == "SessionData":
        return normalize_session_data(
            payload,
            observed_at,
            session=session,
            data_quality=data_quality,
        )
    if stream == "SessionStatus":
        return normalize_session_status(
            payload,
            observed_at,
            session=session,
            data_quality=data_quality,
        )
    if stream == "DriverList":
        return normalize_driver_list(
            payload,
            observed_at,
            session=session,
            data_quality=data_quality,
        )
    if stream == "CarData.z":
        return normalize_car_data(
            payload,
            observed_at,
            session=session,
            drivers=drivers,
            data_quality=data_quality,
        )
    return []


def normalize_timing_data(
    payload: Any,
    observed_at: datetime | str | None = None,
    *,
    session: SessionMetadata | None = None,
    drivers: Mapping[str, DriverMetadata] | None = None,
    data_quality: str = DATA_QUALITY_LIVE,
) -> list[IncidentSignal]:
    if not isinstance(payload, Mapping):
        return []
    lines = payload.get("Lines")
    if not isinstance(lines, Mapping):
        return []

    observed = _parse_utc(observed_at)
    session_key = _session_key(session)
    signals: list[IncidentSignal] = []
    for rn_raw, timing in lines.items():
        if not isinstance(timing, Mapping):
            continue
        rn = _normalize_racing_number(timing.get("RacingNumber") or rn_raw)
        if rn is None:
            continue
        driver = _lookup_driver(drivers, rn)
        for field_name, kind in (
            ("InPit", "timing_in_pit"),
            ("PitOut", "timing_pit_out"),
            ("Retired", "timing_retired"),
            ("Stopped", "timing_stopped"),
        ):
            if field_name not in timing:
                continue
            value = _coerce_bool(timing.get(field_name))
            if value is None:
                continue
            signals.append(
                IncidentSignal(
                    kind=kind,
                    observed_at=observed,
                    session_key=session_key,
                    racing_number=rn,
                    value=value,
                    data_quality=data_quality,
                    driver=driver,
                    session=session,
                    signals=(kind,),
                )
            )
    return signals


def normalize_track_status(
    payload: Any,
    observed_at: datetime | str | None = None,
    *,
    session: SessionMetadata | None = None,
    data_quality: str = DATA_QUALITY_LIVE,
) -> list[IncidentSignal]:
    if not isinstance(payload, Mapping):
        return []
    status = _normalize_track_status_value(payload)
    if status is None:
        return []
    message = _string_or_none(payload.get("Message") or payload.get("TrackStatus"))
    signal_name = "track_status_" + status.lower()
    return [
        IncidentSignal(
            kind="track_status",
            observed_at=_parse_utc(_timestamp_from_payload(payload) or observed_at),
            session_key=_session_key(session),
            value=status,
            data_quality=data_quality,
            message=message,
            track_status=status,
            session=session,
            signals=(signal_name,),
            raw_id=_payload_fingerprint(payload),
        )
    ]


def normalize_race_control_messages(
    payload: Any,
    observed_at: datetime | str | None = None,
    *,
    session: SessionMetadata | None = None,
    drivers: Mapping[str, DriverMetadata] | None = None,
    data_quality: str = DATA_QUALITY_LIVE,
) -> list[IncidentSignal]:
    observed = _parse_utc(observed_at)
    session_key = _session_key(session)
    signals: list[IncidentSignal] = []
    for item in _extract_race_control_items(payload):
        message = _string_or_none(item.get("Message") or item.get("Text"))
        category = _string_or_none(item.get("Category") or item.get("CategoryType"))
        flag = _string_or_none(item.get("Flag"))
        signal_names = _race_control_signal_names(item)
        confidence = (
            CONFIDENCE_HIGH
            if "race_control_stopped" in signal_names
            or "race_control_red" in signal_names
            else CONFIDENCE_MEDIUM
        )
        item_observed = _parse_utc(_timestamp_from_payload(item), default=observed)
        racing_numbers = _extract_racing_numbers(item)
        if not racing_numbers:
            signals.append(
                IncidentSignal(
                    kind="race_control",
                    observed_at=item_observed,
                    session_key=session_key,
                    data_quality=data_quality,
                    confidence_hint=confidence,
                    reason="race_control_incident",
                    message=message,
                    category=category,
                    flag=flag,
                    session=session,
                    signals=signal_names,
                    raw_id=_payload_fingerprint(item),
                )
            )
            continue
        for rn in racing_numbers:
            signals.append(
                IncidentSignal(
                    kind="race_control",
                    observed_at=item_observed,
                    session_key=session_key,
                    racing_number=rn,
                    data_quality=data_quality,
                    confidence_hint=confidence,
                    reason="race_control_incident",
                    message=message,
                    category=category,
                    flag=flag,
                    driver=_lookup_driver(drivers, rn),
                    session=session,
                    signals=signal_names,
                    raw_id=_payload_fingerprint(item),
                )
            )
    return signals


def normalize_session_info(
    payload: Any,
    observed_at: datetime | str | None = None,
    *,
    session: SessionMetadata | None = None,
    data_quality: str = DATA_QUALITY_LIVE,
) -> list[IncidentSignal]:
    if not isinstance(payload, Mapping):
        return []
    session_type = normalize_session_type(payload.get("Type") or payload.get("Name"))
    session_name = _string_or_none(
        payload.get("Name") or payload.get("SessionName") or payload.get("Type")
    )
    meeting = payload.get("Meeting")
    meeting_name = None
    if isinstance(meeting, Mapping):
        meeting_name = _string_or_none(
            meeting.get("Name") or meeting.get("OfficialName")
        )
    meeting_name = meeting_name or _string_or_none(
        payload.get("MeetingName") or payload.get("Meeting")
    )
    archive_status = payload.get("ArchiveStatus")
    archive_path = (
        archive_status.get("Path") if isinstance(archive_status, Mapping) else None
    )
    session_key = _string_or_none(
        payload.get("SessionKey")
        or payload.get("Path")
        or payload.get("LiveTimingPath")
        or archive_path
    )
    if session_key is None:
        session_key = _build_session_key(
            meeting_name, session_name, payload.get("StartDate")
        )
    metadata = _merge_session_metadata(
        session or SessionMetadata(session_key=session_key),
        SessionMetadata(
            session_key=session_key,
            meeting_name=meeting_name,
            session_name=session_name,
            session_type=session_type,
        ),
    )
    return [
        IncidentSignal(
            kind="session_context",
            observed_at=_parse_utc(_timestamp_from_payload(payload) or observed_at),
            session_key=metadata.session_key,
            data_quality=data_quality,
            session=metadata,
        )
    ]


def normalize_session_status(
    payload: Any,
    observed_at: datetime | str | None = None,
    *,
    session: SessionMetadata | None = None,
    data_quality: str = DATA_QUALITY_LIVE,
) -> list[IncidentSignal]:
    if not isinstance(payload, Mapping):
        return []
    status = _normalize_session_status_value(payload)
    if status is None:
        return []
    return [
        IncidentSignal(
            kind="session_status",
            observed_at=_parse_utc(_timestamp_from_payload(payload) or observed_at),
            session_key=_session_key(session),
            value=status,
            data_quality=data_quality,
            session=session,
            signals=("session_status",),
        )
    ]


def normalize_session_data(
    payload: Any,
    observed_at: datetime | str | None = None,
    *,
    session: SessionMetadata | None = None,
    data_quality: str = DATA_QUALITY_LIVE,
) -> list[IncidentSignal]:
    if not isinstance(payload, Mapping):
        return []
    observed = _parse_utc(observed_at)
    signals: list[IncidentSignal] = []
    for item in _iter_series_items(payload.get("StatusSeries")):
        status = _normalize_session_status_value(item)
        if status is None:
            continue
        signals.append(
            IncidentSignal(
                kind="session_status",
                observed_at=_parse_utc(item.get("Utc"), default=observed),
                session_key=_session_key(session),
                value=status,
                data_quality=data_quality,
                session=session,
                signals=("session_status",),
            )
        )
    return signals


def normalize_driver_list(
    payload: Any,
    observed_at: datetime | str | None = None,
    *,
    session: SessionMetadata | None = None,
    data_quality: str = DATA_QUALITY_LIVE,
) -> list[IncidentSignal]:
    if not isinstance(payload, Mapping):
        return []
    observed = _parse_utc(observed_at)
    signals: list[IncidentSignal] = []
    for key, raw_driver in payload.items():
        if not isinstance(raw_driver, Mapping):
            continue
        rn = _normalize_racing_number(raw_driver.get("RacingNumber") or key)
        if rn is None:
            continue
        if not any(
            field in raw_driver
            for field in (
                "Tla",
                "FullName",
                "BroadcastName",
                "TeamName",
                "TeamColour",
            )
        ):
            continue
        driver = DriverMetadata(
            racing_number=rn,
            tla=_uppercase_or_none(raw_driver.get("Tla")),
            name=_string_or_none(
                raw_driver.get("FullName") or raw_driver.get("BroadcastName") or rn
            ),
            team=_string_or_none(raw_driver.get("TeamName")),
            team_color=_normalize_team_color(raw_driver.get("TeamColour")),
        )
        signals.append(
            IncidentSignal(
                kind="driver_metadata",
                observed_at=observed,
                session_key=_session_key(session),
                racing_number=rn,
                data_quality=data_quality,
                driver=driver,
                session=session,
            )
        )
    return signals


def normalize_car_data(
    payload: Any,
    observed_at: datetime | str | None = None,
    *,
    session: SessionMetadata | None = None,
    drivers: Mapping[str, DriverMetadata] | None = None,
    data_quality: str = DATA_QUALITY_LIVE,
) -> list[IncidentSignal]:
    """Normalize CarData.z speed samples into incident detector signals."""
    observed = _parse_utc(observed_at)
    session_key = _session_key(session)
    signals: list[IncidentSignal] = []
    for entry in _extract_car_data_entries(payload):
        entry_observed = _parse_utc(_timestamp_from_payload(entry), default=observed)
        cars = entry.get("Cars")
        if not isinstance(cars, Mapping):
            continue
        for rn_raw, car in cars.items():
            if not isinstance(car, Mapping):
                continue
            rn = _normalize_racing_number(car.get("RacingNumber") or rn_raw)
            if rn is None:
                continue
            speed = _car_speed_from_payload(car)
            if speed is None:
                continue
            signals.append(
                IncidentSignal(
                    kind="car_speed",
                    observed_at=entry_observed,
                    session_key=session_key,
                    racing_number=rn,
                    value=speed,
                    data_quality=data_quality,
                    driver=_lookup_driver(drivers, rn),
                    session=session,
                    signals=("car_speed",),
                )
            )
    return signals


def decode_car_data_payload(payload: Any) -> list[Mapping[str, Any]]:
    """Decode raw or already-decoded CarData.z payloads into entry mappings."""
    return _extract_car_data_entries(payload)


def normalize_session_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unknown"
    for normalized, needles in _SESSION_TYPE_PATTERNS:
        if any(needle in text for needle in needles):
            return normalized
    return "unknown"


def _extract_car_data_entries(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        entries = payload.get("Entries")
        if isinstance(entries, list):
            return [entry for entry in entries if isinstance(entry, Mapping)]
        if isinstance(payload.get("Cars"), Mapping):
            return [payload]
        return []
    if isinstance(payload, list):
        return [entry for entry in payload if isinstance(entry, Mapping)]

    text = _decode_text_payload(payload)
    if text is None:
        return []

    entries: list[Mapping[str, Any]] = []
    for line in text.splitlines() or [text]:
        line = line.strip()
        if not line:
            continue
        decoded = _decode_car_data_line(line)
        if isinstance(decoded, Mapping):
            raw_entries = decoded.get("Entries")
            if isinstance(raw_entries, list):
                entries.extend(
                    entry for entry in raw_entries if isinstance(entry, Mapping)
                )
            elif isinstance(decoded.get("Cars"), Mapping):
                entries.append(decoded)
    return entries


def _decode_text_payload(payload: Any) -> str | None:
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="ignore")
    if isinstance(payload, str):
        return payload
    return None


def _decode_car_data_line(line: str) -> Mapping[str, Any] | None:
    if not line or line.startswith("URL:"):
        return None
    encoded = line
    if '"' in line:
        try:
            _, rest = line.split('"', 1)
            encoded = rest.split('"', 1)[0]
        except ValueError:
            return None
    encoded = encoded.strip()
    if not encoded:
        return None
    try:
        raw = base64.b64decode(encoded)
        payload = zlib.decompress(raw, wbits=-15)
        decoded = json.loads(payload)
    except Exception:  # noqa: BLE001
        return None
    return decoded if isinstance(decoded, Mapping) else None


def _car_speed_from_payload(car: Mapping[str, Any]) -> float | None:
    channels = car.get("Channels")
    if not isinstance(channels, Mapping):
        return None
    speed = _coerce_float(
        channels.get(_CAR_DATA_SPEED_CHANNEL)
        if _CAR_DATA_SPEED_CHANNEL in channels
        else channels.get(int(_CAR_DATA_SPEED_CHANNEL))
    )
    if speed is None or speed < 0 or speed > _CAR_DATA_MAX_REASONABLE_SPEED_KPH:
        return None
    return speed


def _normalize_signal_datetime(signal: IncidentSignal) -> IncidentSignal:
    observed = _parse_utc(signal.observed_at)
    if observed is signal.observed_at:
        return signal
    return IncidentSignal(
        kind=signal.kind,
        observed_at=observed,
        session_key=signal.session_key,
        racing_number=signal.racing_number,
        value=signal.value,
        data_quality=signal.data_quality,
        confidence_hint=signal.confidence_hint,
        reason=signal.reason,
        message=signal.message,
        category=signal.category,
        flag=signal.flag,
        track_status=signal.track_status,
        driver=signal.driver,
        session=signal.session,
        signals=signal.signals,
        raw_id=signal.raw_id,
    )


def _parse_utc(
    value: datetime | str | None, *, default: datetime | None = None
) -> datetime:
    if value is None:
        return default or datetime.now(UTC)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    text = str(value).strip()
    if not text:
        return default or datetime.now(UTC)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return default or datetime.now(UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _session_key(session: SessionMetadata | None) -> str:
    if session is None or not session.session_key:
        return DEFAULT_SESSION_KEY
    return session.session_key


def _merge_session_metadata(
    current: SessionMetadata, new: SessionMetadata
) -> SessionMetadata:
    return SessionMetadata(
        session_key=new.session_key or current.session_key,
        meeting_name=new.meeting_name or current.meeting_name,
        session_name=new.session_name or current.session_name,
        session_type=new.session_type or current.session_type,
    )


def _lookup_driver(
    drivers: Mapping[str, DriverMetadata] | None, racing_number: str
) -> DriverMetadata | None:
    if drivers is None:
        return None
    return drivers.get(racing_number)


def _normalize_racing_number(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, float) and value in (0.0, 1.0):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "t", "yes", "y"}:
            return True
        if text in {"0", "false", "f", "no", "n"}:
            return False
    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _normalize_track_status_value(payload: Mapping[str, Any]) -> str | None:
    message = str(payload.get("Message") or payload.get("TrackStatus") or "").upper()
    status = str(payload.get("Status") or "").strip()
    compact_message = message.replace("_", " ").replace("-", " ")

    for key, value in _TRACK_STATUS_ALIASES.items():
        if key in compact_message:
            return value
    if status in _TRACK_STATUS_CODES:
        return _TRACK_STATUS_CODES[status]
    if message in {
        TRACK_STATUS_CLEAR,
        TRACK_STATUS_YELLOW,
        TRACK_STATUS_VSC,
        TRACK_STATUS_SC,
        TRACK_STATUS_RED,
    }:
        return message
    return None


def _extract_race_control_items(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if not isinstance(payload, Mapping):
        return []
    messages = payload.get("Messages")
    if isinstance(messages, list):
        return [item for item in messages if isinstance(item, Mapping)]
    if isinstance(messages, Mapping):
        keys = sorted(
            (key for key in messages if str(key).isdigit()),
            key=lambda item: int(str(item)),
        )
        return [
            item for key in keys if isinstance((item := messages.get(key)), Mapping)
        ]
    if "Messages" in payload:
        return []
    return [payload]


def _race_control_signal_names(item: Mapping[str, Any]) -> tuple[str, ...]:
    text = _race_control_text(item)
    names: list[str] = []
    if any(word in text for word in _RACE_CONTROL_CLEAR_WORDS):
        names.append("race_control_clear")
    yellow_is_context = _race_control_yellow_is_context(text)
    if yellow_is_context:
        names.append("race_control_yellow")
    if "RED FLAG" in text or re.search(r"\bRED\b", text):
        names.append("race_control_red")
    if any(word in text for word in _SAFETY_CAR_KEYWORDS):
        names.append("race_control_safety_car")
    if "STOPPED" in text or re.search(r"\bSTOP\b", text):
        names.append("race_control_stopped")
    if any(word in text for word in _INCIDENT_KEYWORDS) and (
        "YELLOW" not in text or yellow_is_context
    ):
        names.append("race_control_incident")
    return tuple(dict.fromkeys(names))


def _race_control_yellow_is_context(text: str) -> bool:
    if "YELLOW" not in text:
        return False
    if "PIT LANE" in text:
        return False
    if "DELETED" in text and _RACE_CONTROL_LAP_DELETION_RE.search(text):
        return False
    return True


def _race_control_is_context(signal: IncidentSignal) -> bool:
    if "race_control_clear" in signal.signals and len(signal.signals) == 1:
        return False
    return any(
        name
        in {
            "race_control_incident",
            "race_control_red",
            "race_control_safety_car",
            "race_control_stopped",
            "race_control_yellow",
        }
        for name in signal.signals
    )


def _race_control_text(item: Mapping[str, Any]) -> str:
    values = (
        item.get("Message"),
        item.get("Text"),
        item.get("Flag"),
        item.get("Category"),
        item.get("CategoryType"),
        item.get("Mode"),
        item.get("Status"),
    )
    return " ".join(str(value).upper() for value in values if value is not None)


def _extract_racing_numbers(item: Mapping[str, Any]) -> tuple[str, ...]:
    direct_values = (
        item.get("RacingNumber"),
        item.get("DriverNumber"),
        item.get("Car"),
        item.get("CarNumber"),
    )
    numbers: list[str] = []
    for value in direct_values:
        rn = _normalize_racing_number(value)
        if rn is not None:
            numbers.append(rn)

    text = _race_control_text(item)
    numbers.extend(match.group(1) for match in _CAR_WORD_RE.finditer(text))
    numbers.extend(match.group(1) for match in _NUMBER_TLA_RE.finditer(text))
    return tuple(dict.fromkeys(numbers))


def _timestamp_from_payload(payload: Mapping[str, Any]) -> Any:
    return (
        payload.get("Utc")
        or payload.get("utc")
        or payload.get("processedAt")
        or payload.get("timestamp")
    )


def _normalize_session_status_value(payload: Mapping[str, Any]) -> str | None:
    raw = (
        payload.get("SessionStatus")
        or payload.get("Status")
        or payload.get("Started")
        or payload.get("Message")
    )
    if raw is None:
        return None
    if raw is True:
        return "Started"
    if raw is False:
        return "Inactive"
    text = str(raw).strip()
    return text or None


def _iter_series_items(series: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(series, list):
        for item in series:
            if isinstance(item, Mapping):
                yield item
        return
    if isinstance(series, Mapping):
        keys = sorted(
            (key for key in series if str(key).isdigit()),
            key=lambda item: int(str(item)),
        )
        for key in keys:
            item = series.get(key)
            if isinstance(item, Mapping):
                yield item


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _uppercase_or_none(value: Any) -> str | None:
    text = _string_or_none(value)
    return text.upper() if text is not None else None


def _normalize_team_color(value: Any) -> str | None:
    text = _string_or_none(value)
    if text is None:
        return None
    text = text.lstrip("#")
    if len(text) != 6:
        return None
    if not all(char in "0123456789abcdefABCDEF" for char in text):
        return None
    return "#" + text.upper()


def _payload_fingerprint(payload: Mapping[str, Any]) -> str:
    timestamp = _timestamp_from_payload(payload)
    category = payload.get("Category") or payload.get("CategoryType") or ""
    message = payload.get("Message") or payload.get("Text") or payload.get("Flag") or ""
    if timestamp or category or message:
        return f"{timestamp or ''}|{category}|{message}"
    return json.dumps(dict(payload), sort_keys=True, default=str)


def _build_session_key(
    meeting_name: str | None, session_name: str | None, start_date: Any
) -> str:
    parts = [
        str(start_date or "")[:10],
        meeting_name or "",
        session_name or "",
    ]
    slug = _NON_SLUG_RE.sub("-", "-".join(parts).lower()).strip("-")
    return slug or DEFAULT_SESSION_KEY


def _build_incident_id(
    session_key: str, racing_number: str, observed_at: datetime
) -> str:
    return f"{session_key}-{racing_number}-{_format_utc(observed_at)}"


def _confidence_gt(left: str, right: str) -> bool:
    return CONFIDENCE_ORDER.get(left, -1) > CONFIDENCE_ORDER.get(right, -1)


def _reason_for_context(
    *,
    track_context: TrackStatusContext | None = None,
    race_context: RaceControlContext | None = None,
) -> str:
    if track_context is not None and track_context.status is not None:
        if track_context.status == TRACK_STATUS_SC:
            return "timing_stopped_with_safety_car_context"
        if track_context.status == TRACK_STATUS_VSC:
            return "timing_stopped_with_vsc_context"
    if race_context is not None and race_context.message is not None:
        return "timing_stopped_with_race_control"
    if track_context is not None and track_context.status is not None:
        return "timing_stopped_with_track_status"
    return "timing_stopped"


def _reason_for_car_context(
    *,
    track_context: TrackStatusContext | None = None,
    race_context: RaceControlContext | None = None,
) -> str:
    if track_context is not None and track_context.status is not None:
        if track_context.status == TRACK_STATUS_SC:
            return "car_low_speed_with_safety_car_context"
        if track_context.status == TRACK_STATUS_VSC:
            return "car_low_speed_with_vsc_context"
        if track_context.status == TRACK_STATUS_RED:
            return "car_low_speed_with_red_flag_context"
    if race_context is not None and race_context.message is not None:
        return "car_low_speed_with_race_control"
    if track_context is not None and track_context.status is not None:
        return "car_low_speed_with_track_status"
    return "car_low_speed"


def _merge_track_context(
    current: TrackStatusContext, new: TrackStatusContext
) -> TrackStatusContext:
    if new.status is not None or new.message is not None:
        return new
    return current


def _merge_race_context(
    current: RaceControlContext, new: RaceControlContext
) -> RaceControlContext:
    if new.message is not None or new.category is not None or new.flag is not None:
        return new
    return current


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _extend_unique(values: list[str], new_values: Iterable[str]) -> None:
    for value in new_values:
        _append_unique(values, value)


def _is_within(left: datetime, right: datetime, window: timedelta) -> bool:
    return abs(left - right) <= window
