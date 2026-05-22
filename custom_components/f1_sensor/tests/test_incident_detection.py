from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.f1_sensor.incident_detection import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    DATA_QUALITY_LIVE,
    PHASE_CANDIDATE,
    PHASE_CLEARED,
    PHASE_CONFIRMED,
    PHASE_UPDATED,
    DriverMetadata,
    IncidentDetector,
    IncidentSignal,
    SessionMetadata,
    normalize_driver_list,
    normalize_race_control_messages,
    normalize_session_data,
    normalize_timing_data,
    normalize_track_status,
)

BASE = datetime(2026, 5, 3, 17, 0, 0, tzinfo=UTC)
SESSION = SessionMetadata(
    session_key="2026-miami-race",
    meeting_name="Miami Grand Prix",
    session_name="Race",
    session_type="race",
)
DRIVERS = {
    "10": DriverMetadata(
        racing_number="10",
        tla="GAS",
        name="Pierre Gasly",
        team="Alpine",
    )
}


def _timing(
    at: datetime,
    racing_number: str = "10",
    *,
    stopped: bool | None = None,
    in_pit: bool | None = None,
    pit_out: bool | None = None,
    retired: bool | None = None,
) -> list[IncidentSignal]:
    payload: dict[str, dict[str, dict[str, bool]]] = {"Lines": {racing_number: {}}}
    line = payload["Lines"][racing_number]
    if in_pit is not None:
        line["InPit"] = in_pit
    if pit_out is not None:
        line["PitOut"] = pit_out
    if retired is not None:
        line["Retired"] = retired
    if stopped is not None:
        line["Stopped"] = stopped
    return normalize_timing_data(
        payload,
        at,
        session=SESSION,
        drivers=DRIVERS,
    )


def _bootstrap_clean(
    detector: IncidentDetector,
    *,
    at: datetime = BASE,
    racing_number: str = "10",
) -> None:
    changes = detector.process_signals(
        _timing(
            at,
            racing_number,
            stopped=False,
            in_pit=False,
            pit_out=False,
            retired=False,
        )
    )
    assert changes == []


def _track(at: datetime, status: str, message: str) -> list[IncidentSignal]:
    return normalize_track_status(
        {"Status": status, "Message": message},
        at,
        session=SESSION,
    )


def _race_control(
    at: datetime,
    message: str,
    *,
    category: str = "Flag",
    flag: str = "DOUBLE YELLOW",
) -> list[IncidentSignal]:
    return normalize_race_control_messages(
        {
            "Messages": [
                {
                    "Utc": at.isoformat().replace("+00:00", "Z"),
                    "Category": category,
                    "Flag": flag,
                    "Message": message,
                }
            ]
        },
        at,
        session=SESSION,
        drivers=DRIVERS,
    )


def test_normalize_timingdata_stopped_creates_timing_stopped_signal() -> None:
    signals = normalize_timing_data(
        {"Lines": {"10": {"Stopped": True, "Status": 260}}},
        BASE.isoformat(),
        session=SESSION,
        drivers=DRIVERS,
    )

    assert len(signals) == 1
    assert signals[0].kind == "timing_stopped"
    assert signals[0].value is True
    assert signals[0].racing_number == "10"
    assert signals[0].observed_at == BASE
    assert signals[0].driver == DRIVERS["10"]


def test_normalize_timingdata_in_pit_creates_pit_signal() -> None:
    signals = normalize_timing_data(
        {"Lines": {"10": {"InPit": "true"}}},
        BASE,
        session=SESSION,
    )

    assert [(signal.kind, signal.value) for signal in signals] == [
        ("timing_in_pit", True)
    ]


def test_normalize_timingdata_retired_without_stopped_is_not_stopped_signal() -> None:
    signals = normalize_timing_data(
        {"Lines": {"10": {"Retired": 1, "Stopped": False}}},
        BASE,
        session=SESSION,
    )

    assert [signal.kind for signal in signals] == [
        "timing_retired",
        "timing_stopped",
    ]
    assert signals[1].value is False


def test_normalize_track_status_accepts_code_and_message() -> None:
    by_code = normalize_track_status({"Status": "2"}, BASE, session=SESSION)
    by_message = normalize_track_status(
        {"Status": "1", "Message": "Double Yellow"},
        BASE,
        session=SESSION,
    )

    assert by_code[0].track_status == "YELLOW"
    assert by_message[0].track_status == "YELLOW"


def test_normalize_race_control_extracts_driver_number_from_message() -> None:
    signals = _race_control(BASE, "DOUBLE YELLOW FOR CAR 10")

    assert len(signals) == 1
    assert signals[0].kind == "race_control"
    assert signals[0].racing_number == "10"
    assert "race_control_yellow" in signals[0].signals
    assert "race_control_incident" in signals[0].signals


def test_normalize_race_control_ignores_pit_lane_yellow_context() -> None:
    signals = normalize_race_control_messages(
        {
            "Messages": [
                {
                    "Utc": BASE.isoformat().replace("+00:00", "Z"),
                    "Category": "Other",
                    "Message": "YELLOW IN PIT LANE",
                }
            ]
        },
        BASE,
        session=SESSION,
        drivers=DRIVERS,
    )

    assert len(signals) == 1
    assert signals[0].signals == ()


def test_normalize_race_control_ignores_lap_deletion_yellow_context() -> None:
    signals = normalize_race_control_messages(
        {
            "Messages": [
                {
                    "Utc": BASE.isoformat().replace("+00:00", "Z"),
                    "Category": "Other",
                    "Message": (
                        "CAR 87 (BEA) TIME 1:29.883 DELETED - DOUBLE YELLOW AT TURN 1"
                    ),
                }
            ]
        },
        BASE,
        session=SESSION,
        drivers=DRIVERS,
    )

    assert len(signals) == 1
    assert signals[0].racing_number == "87"
    assert signals[0].signals == ()


def test_normalize_race_control_without_driver_is_global_signal() -> None:
    signals = _race_control(BASE, "RED FLAG", flag="RED")

    assert len(signals) == 1
    assert signals[0].racing_number is None
    assert "race_control_red" in signals[0].signals


def test_normalize_driver_list_creates_driver_metadata_signal() -> None:
    signals = normalize_driver_list(
        {
            "10": {
                "Tla": "gas",
                "FullName": "Pierre Gasly",
                "TeamName": "Alpine",
                "TeamColour": "0093cc",
            }
        },
        BASE,
        session=SESSION,
    )

    assert len(signals) == 1
    assert signals[0].kind == "driver_metadata"
    assert signals[0].driver == DriverMetadata(
        racing_number="10",
        tla="GAS",
        name="Pierre Gasly",
        team="Alpine",
        team_color="#0093CC",
    )


def test_normalize_driver_list_ignores_position_only_delta() -> None:
    signals = normalize_driver_list(
        {"10": {"Line": 2}},
        BASE,
        session=SESSION,
    )

    assert signals == []


def test_driver_list_position_delta_does_not_overwrite_driver_identity() -> None:
    detector = IncidentDetector()
    detector.process_signals(
        normalize_driver_list(
            {
                "10": {
                    "Tla": "GAS",
                    "FullName": "Pierre Gasly",
                    "TeamName": "Alpine",
                }
            },
            BASE,
            session=SESSION,
        )
    )
    detector.process_signals(normalize_driver_list({"10": {"Line": 2}}, BASE))
    _bootstrap_clean(detector)

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=1), stopped=True)
    )

    assert len(changes) == 1
    assert changes[0].driver.tla == "GAS"
    assert changes[0].driver.name == "Pierre Gasly"


def test_normalize_session_data_extracts_terminal_status() -> None:
    signals = normalize_session_data(
        {
            "StatusSeries": {
                "0": {
                    "Utc": "2026-05-03T18:00:00Z",
                    "SessionStatus": "Finalised",
                }
            }
        },
        BASE,
        session=SESSION,
    )

    assert len(signals) == 1
    assert signals[0].kind == "session_status"
    assert signals[0].value == "Finalised"
    assert signals[0].observed_at == datetime(2026, 5, 3, 18, tzinfo=UTC)


def test_normalize_invalid_payload_returns_empty_list() -> None:
    assert normalize_timing_data(None, BASE) == []
    assert normalize_timing_data({"Lines": []}, BASE) == []
    assert normalize_track_status([], BASE) == []
    assert normalize_race_control_messages({"Messages": "bad"}, BASE) == []


def test_stopped_non_pit_confirms_medium_incident() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=1), stopped=True)
    )

    assert len(changes) == 1
    change = changes[0]
    assert change.phase == PHASE_CONFIRMED
    assert change.confidence == CONFIDENCE_MEDIUM
    assert change.reason == "timing_stopped"
    assert change.driver.racing_number == "10"
    assert change.incident_id == "2026-miami-race-10-2026-05-03T17:00:01Z"
    assert "timing_stopped" in change.signals
    assert change.data_quality == DATA_QUALITY_LIVE


def test_stopped_in_pit_is_suppressed() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=1), stopped=True, in_pit=True)
    )

    assert changes == []
    assert detector.get_active_incident(SESSION.session_key, "10") is None


def test_recent_pit_out_suppresses_stopped_signal() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)
    assert (
        detector.process_signals(_timing(BASE + timedelta(seconds=1), pit_out=True))
        == []
    )

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=5), stopped=True, pit_out=False)
    )

    assert changes == []
    assert detector.get_active_incident(SESSION.session_key, "10") is None


def test_pit_out_hold_expires_before_stopped_confirms_incident() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)
    detector.process_signals(_timing(BASE + timedelta(seconds=1), pit_out=True))
    detector.process_signals(_timing(BASE + timedelta(seconds=2), pit_out=False))

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=8), stopped=True)
    )

    assert len(changes) == 1
    assert changes[0].phase == PHASE_CONFIRMED
    assert changes[0].confidence == CONFIDENCE_MEDIUM


def test_track_yellow_without_driver_does_not_create_driver_incident() -> None:
    detector = IncidentDetector()

    changes = detector.process_signals(_track(BASE, "2", "Yellow"))

    assert changes == []
    assert detector.active_incidents(SESSION.session_key) == ()


def test_stopped_plus_yellow_confirms_high_incident() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)
    detector.process_signals(_track(BASE + timedelta(seconds=1), "2", "Yellow"))

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=2), stopped=True)
    )

    assert len(changes) == 1
    assert changes[0].phase == PHASE_CONFIRMED
    assert changes[0].confidence == CONFIDENCE_HIGH
    assert changes[0].reason == "timing_stopped_with_track_status"
    assert changes[0].track_status.status == "YELLOW"


def test_race_control_before_stopped_upgrades_to_high_when_stopped_arrives() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)
    candidate = detector.process_signals(
        _race_control(BASE + timedelta(seconds=10), "DOUBLE YELLOW FOR CAR 10")
    )

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=20), stopped=True)
    )

    assert len(candidate) == 1
    assert candidate[0].phase == PHASE_CANDIDATE
    assert len(changes) == 1
    assert changes[0].phase == PHASE_CONFIRMED
    assert changes[0].confidence == CONFIDENCE_HIGH
    assert changes[0].incident_id == candidate[0].incident_id
    assert changes[0].reason == "timing_stopped_with_race_control"


def test_stopped_before_race_control_updates_existing_incident_to_high() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)
    confirmed = detector.process_signals(
        _timing(BASE + timedelta(seconds=1), stopped=True)
    )[0]

    changes = detector.process_signals(
        _race_control(BASE + timedelta(seconds=30), "TURN 17 INCIDENT FOR CAR 10")
    )

    assert len(changes) == 1
    assert changes[0].phase == PHASE_UPDATED
    assert changes[0].confidence == CONFIDENCE_HIGH
    assert changes[0].incident_id == confirmed.incident_id


def test_race_control_for_other_driver_does_not_upgrade_stopped_incident() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)
    confirmed = detector.process_signals(
        _timing(BASE + timedelta(seconds=1), stopped=True)
    )[0]

    changes = detector.process_signals(
        normalize_race_control_messages(
            {
                "Messages": [
                    {
                        "Category": "Other",
                        "Message": "INCIDENT INVOLVING CAR 6",
                    }
                ]
            },
            BASE + timedelta(seconds=30),
            session=SESSION,
        )
    )

    assert changes == []
    active = detector.get_active_incident(SESSION.session_key, "10")
    assert active is not None
    assert active.incident_id == confirmed.incident_id
    assert active.confidence == CONFIDENCE_MEDIUM


def test_race_control_outside_time_window_does_not_upgrade_incident() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)
    detector.process_signals(
        _race_control(BASE + timedelta(seconds=1), "DOUBLE YELLOW FOR CAR 10")
    )

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=130), stopped=True)
    )

    assert len(changes) == 1
    assert changes[0].phase == PHASE_CONFIRMED
    assert changes[0].confidence == CONFIDENCE_MEDIUM
    assert changes[0].incident_id == "2026-miami-race-10-2026-05-03T17:02:10Z"


def test_first_snapshot_with_already_stopped_driver_bootstraps_without_alert() -> None:
    detector = IncidentDetector()

    assert detector.process_signals(_timing(BASE, stopped=True, in_pit=False)) == []
    assert (
        detector.process_signals(_timing(BASE + timedelta(seconds=1), stopped=True))
        == []
    )
    assert detector.active_incidents(SESSION.session_key) == ()


def test_stopped_after_clean_bootstrap_confirms_incident() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=1), stopped=True)
    )

    assert len(changes) == 1
    assert changes[0].phase == PHASE_CONFIRMED


def test_duplicate_stopped_signals_do_not_emit_multiple_confirmed_changes() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)

    first = detector.process_signals(_timing(BASE + timedelta(seconds=1), stopped=True))
    second = detector.process_signals(
        _timing(BASE + timedelta(seconds=2), stopped=True)
    )

    assert len(first) == 1
    assert second == []


def test_clear_when_stopped_becomes_false() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)
    confirmed = detector.process_signals(
        _timing(BASE + timedelta(seconds=1), stopped=True)
    )[0]

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=10), stopped=False)
    )

    assert len(changes) == 1
    assert changes[0].phase == PHASE_CLEARED
    assert changes[0].incident_id == confirmed.incident_id
    assert detector.get_active_incident(SESSION.session_key, "10") is None


def test_same_driver_new_stop_after_clear_and_cooldown_can_create_new_incident() -> (
    None
):
    detector = IncidentDetector(cooldown=timedelta(seconds=10))
    _bootstrap_clean(detector)
    first = detector.process_signals(
        _timing(BASE + timedelta(seconds=1), stopped=True)
    )[0]
    detector.process_signals(_timing(BASE + timedelta(seconds=2), stopped=False))

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=13), stopped=True)
    )

    assert len(changes) == 1
    assert changes[0].incident_id != first.incident_id


def test_same_driver_stop_inside_cooldown_is_deduped() -> None:
    detector = IncidentDetector(cooldown=timedelta(seconds=20))
    _bootstrap_clean(detector)
    detector.process_signals(_timing(BASE + timedelta(seconds=1), stopped=True))
    detector.process_signals(_timing(BASE + timedelta(seconds=2), stopped=False))

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=10), stopped=True)
    )

    assert changes == []


def test_session_end_clears_active_incident() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)
    confirmed = detector.process_signals(
        _timing(BASE + timedelta(seconds=1), stopped=True)
    )[0]

    changes = detector.process_signals(
        [
            IncidentSignal(
                kind="session_status",
                observed_at=BASE + timedelta(seconds=20),
                session_key=SESSION.session_key,
                value="Finalised",
                session=SESSION,
            )
        ]
    )

    assert len(changes) == 1
    assert changes[0].phase == PHASE_CLEARED
    assert changes[0].reason == "session_ended"
    assert changes[0].incident_id == confirmed.incident_id
    assert detector.get_active_incident(SESSION.session_key, "10") is None


def test_session_end_suppresses_new_stopped_until_session_active_again() -> None:
    detector = IncidentDetector(cooldown=timedelta(seconds=0))
    _bootstrap_clean(detector)
    detector.process_signals(
        [
            IncidentSignal(
                kind="session_status",
                observed_at=BASE + timedelta(seconds=1),
                session_key=SESSION.session_key,
                value="Finalised",
                session=SESSION,
            )
        ]
    )

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=2), stopped=True)
    )

    assert changes == []


def test_data_gap_does_not_create_or_clear_incident_by_itself() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)
    confirmed = detector.process_signals(
        _timing(BASE + timedelta(seconds=1), stopped=True)
    )[0]

    changes = detector.process_signals(
        [
            IncidentSignal(
                kind="data_gap",
                observed_at=BASE + timedelta(seconds=30),
                session_key=SESSION.session_key,
            )
        ]
    )

    assert changes == []
    active = detector.get_active_incident(SESSION.session_key, "10")
    assert active is not None
    assert active.incident_id == confirmed.incident_id


def test_retired_without_stopped_does_not_confirm_on_track_incident() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=1), retired=True)
    )

    assert changes == []
    assert detector.active_incidents(SESSION.session_key) == ()


def test_practice_stopped_non_pit_confirms_medium_with_session_context() -> None:
    practice = SessionMetadata(
        session_key="2026-china-practice",
        meeting_name="Chinese Grand Prix",
        session_name="Practice 1",
        session_type="practice",
    )
    detector = IncidentDetector()
    detector.process_signals(
        normalize_timing_data(
            {"Lines": {"41": {"Stopped": False, "InPit": False}}},
            BASE,
            session=practice,
        )
    )

    changes = detector.process_signals(
        normalize_timing_data(
            {"Lines": {"41": {"Stopped": True}}},
            BASE + timedelta(seconds=1),
            session=practice,
        )
    )

    assert len(changes) == 1
    assert changes[0].phase == PHASE_CONFIRMED
    assert changes[0].confidence == CONFIDENCE_MEDIUM
    assert changes[0].session.session_type == "practice"


@pytest.mark.parametrize(
    ("session_type", "session_name"),
    (
        ("sprint", "Sprint"),
        ("qualifying", "Qualifying"),
    ),
)
def test_sprint_and_qualifying_stopped_non_pit_confirm_medium(
    session_type: str, session_name: str
) -> None:
    session = SessionMetadata(
        session_key=f"2026-miami-{session_type}",
        meeting_name="Miami Grand Prix",
        session_name=session_name,
        session_type=session_type,
    )
    detector = IncidentDetector()
    detector.process_signals(
        normalize_timing_data(
            {"Lines": {"10": {"Stopped": False, "InPit": False}}},
            BASE,
            session=session,
            drivers=DRIVERS,
        )
    )

    changes = detector.process_signals(
        normalize_timing_data(
            {"Lines": {"10": {"Stopped": True}}},
            BASE + timedelta(seconds=1),
            session=session,
            drivers=DRIVERS,
        )
    )

    assert len(changes) == 1
    assert changes[0].phase == PHASE_CONFIRMED
    assert changes[0].confidence == CONFIDENCE_MEDIUM
    assert changes[0].session.session_type == session_type


def test_change_payload_is_json_serializable_and_stable() -> None:
    detector = IncidentDetector()
    _bootstrap_clean(detector)
    change = detector.process_signals(
        _timing(BASE + timedelta(seconds=1), stopped=True)
    )[0]

    payload = change.to_event_payload()

    assert payload == {
        "incident_id": "2026-miami-race-10-2026-05-03T17:00:01Z",
        "phase": "confirmed",
        "confidence": "medium",
        "reason": "timing_stopped",
        "driver": {
            "racing_number": "10",
            "tla": "GAS",
            "name": "Pierre Gasly",
            "team": "Alpine",
        },
        "session": {
            "meeting_name": "Miami Grand Prix",
            "session_name": "Race",
            "session_type": "race",
            "session_key": "2026-miami-race",
        },
        "track_status": {
            "status": None,
            "message": None,
        },
        "race_control": {
            "message": None,
            "category": None,
            "flag": None,
        },
        "signals": ["timing_stopped"],
        "started_at": "2026-05-03T17:00:01Z",
        "updated_at": "2026-05-03T17:00:01Z",
        "data_quality": "live",
    }
