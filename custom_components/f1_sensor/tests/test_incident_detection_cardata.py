from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import json
import zlib

from custom_components.f1_sensor.helpers import CARDATA_MAX_DECOMPRESSED_BYTES
from custom_components.f1_sensor.incident_detection import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    DATA_QUALITY_BOOTSTRAP,
    DATA_QUALITY_LIVE,
    PHASE_CANDIDATE,
    PHASE_CLEARED,
    PHASE_CONFIRMED,
    DriverMetadata,
    IncidentDetector,
    IncidentLocationContext,
    SessionMetadata,
    normalize_car_data,
    normalize_race_control_messages,
    normalize_session_status,
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
    ),
    "30": DriverMetadata(racing_number="30", tla="LAW"),
    "6": DriverMetadata(racing_number="6", tla="HAD"),
}


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _encoded_cardata_payload(at: datetime, speed: float, rn: str = "10") -> str:
    data = {
        "Entries": [
            {
                "Utc": _iso(at),
                "Cars": {rn: {"Channels": {"2": speed}}},
            }
        ]
    }
    raw = json.dumps(data).encode()
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(raw) + compressor.flush()
    return '"' + base64.b64encode(compressed).decode() + '"'


def _encoded_cardata_data(data: dict) -> str:
    raw = json.dumps(data).encode()
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(raw) + compressor.flush()
    return '"' + base64.b64encode(compressed).decode() + '"'


def _car_speed(
    at: datetime,
    speed: float,
    *,
    rn: str = "10",
    data_quality: str = DATA_QUALITY_LIVE,
):
    return normalize_car_data(
        {
            "Entries": [
                {
                    "Utc": _iso(at),
                    "Cars": {rn: {"Channels": {"2": speed}}},
                }
            ]
        },
        at,
        session=SESSION,
        drivers=DRIVERS,
        data_quality=data_quality,
    )


def _timing(
    at: datetime,
    *,
    rn: str = "10",
    stopped: bool | None = None,
    in_pit: bool | None = None,
    pit_out: bool | None = None,
):
    line: dict[str, bool] = {}
    if stopped is not None:
        line["Stopped"] = stopped
    if in_pit is not None:
        line["InPit"] = in_pit
    if pit_out is not None:
        line["PitOut"] = pit_out
    return normalize_timing_data(
        {"Lines": {rn: line}},
        at,
        session=SESSION,
        drivers=DRIVERS,
    )


def _track(at: datetime, status: str = "2", message: str = "Yellow"):
    return normalize_track_status(
        {"Status": status, "Message": message},
        at,
        session=SESSION,
    )


def _session_status(at: datetime, status: str):
    return normalize_session_status(
        {"Status": status},
        at,
        session=SESSION,
    )


def _race_control(at: datetime, message: str):
    return normalize_race_control_messages(
        {
            "Messages": [
                {
                    "Utc": _iso(at),
                    "Category": "Other",
                    "Message": message,
                }
            ]
        },
        at,
        session=SESSION,
        drivers=DRIVERS,
    )


def test_normalize_cardata_decodes_speed_channel_from_payload() -> None:
    signals = normalize_car_data(
        {
            "Entries": [
                {
                    "Utc": "2026-05-03T17:11:41Z",
                    "Cars": {"10": {"Channels": {"2": "0"}}},
                }
            ]
        },
        BASE,
        session=SESSION,
        drivers=DRIVERS,
    )

    assert len(signals) == 1
    assert signals[0].kind == "car_speed"
    assert signals[0].racing_number == "10"
    assert signals[0].value == 0.0
    assert signals[0].observed_at == datetime(2026, 5, 3, 17, 11, 41, tzinfo=UTC)
    assert signals[0].driver == DRIVERS["10"]


def test_normalize_cardata_decodes_compressed_live_payload() -> None:
    signals = normalize_car_data(
        _encoded_cardata_payload(BASE + timedelta(seconds=1), 4, rn="6"),
        BASE,
        session=SESSION,
        drivers=DRIVERS,
    )

    assert len(signals) == 1
    assert signals[0].racing_number == "6"
    assert signals[0].value == 4.0


def test_normalize_cardata_rejects_oversized_compressed_payload() -> None:
    signals = normalize_car_data(
        _encoded_cardata_data(
            {
                "Entries": [
                    {
                        "Utc": _iso(BASE),
                        "Cars": {"6": {"Channels": {"2": 4}}},
                    }
                ],
                "Pad": "x" * (CARDATA_MAX_DECOMPRESSED_BYTES + 1),
            }
        ),
        BASE,
        session=SESSION,
        drivers=DRIVERS,
    )

    assert signals == []


def test_normalize_cardata_ignores_malformed_or_invalid_speed() -> None:
    assert normalize_car_data(None, BASE, session=SESSION) == []
    assert normalize_car_data({"Entries": "bad"}, BASE, session=SESSION) == []
    assert (
        normalize_car_data(
            {"Entries": [{"Utc": _iso(BASE), "Cars": {"10": {"Channels": {}}}}]},
            BASE,
            session=SESSION,
        )
        == []
    )
    assert (
        normalize_car_data(
            {
                "Entries": [
                    {"Utc": _iso(BASE), "Cars": {"10": {"Channels": {"2": 999}}}}
                ]
            },
            BASE,
            session=SESSION,
        )
        == []
    )


def test_low_speed_before_yellow_creates_candidate_not_confirmed() -> None:
    detector = IncidentDetector()
    assert detector.process_signals(_car_speed(BASE, 0)) == []
    assert detector.process_signals(_car_speed(BASE + timedelta(seconds=2), 0)) == []

    changes = detector.process_signals(_track(BASE + timedelta(seconds=5)))

    assert len(changes) == 1
    change = changes[0]
    assert change.phase == PHASE_CANDIDATE
    assert change.confidence == CONFIDENCE_MEDIUM
    assert change.reason == "car_low_speed_with_track_status"
    assert change.driver.racing_number == "10"
    assert "car_low_speed" in change.signals
    assert "track_status_yellow" in change.signals


def test_miami_like_cardata_points_out_had_within_seconds_after_yellow() -> None:
    detector = IncidentDetector()
    low_start = datetime(2026, 5, 3, 17, 11, 40, 989594, tzinfo=UTC)
    detector.process_signals(_car_speed(low_start, 4, rn="6"))
    detector.process_signals(
        _car_speed(datetime(2026, 5, 3, 17, 11, 41, 229559, tzinfo=UTC), 0, rn="6")
    )
    detector.process_signals(
        _car_speed(datetime(2026, 5, 3, 17, 11, 42, 270404, tzinfo=UTC), 0, rn="6")
    )

    changes = detector.process_signals(
        _track(
            datetime(2026, 5, 3, 17, 11, 46, tzinfo=UTC),
            status="2",
            message="Yellow",
        )
    )

    assert len(changes) == 1
    assert changes[0].phase == PHASE_CANDIDATE
    assert changes[0].driver.racing_number == "6"
    assert changes[0].driver.tla == "HAD"
    assert changes[0].started_at == low_start
    assert changes[0].updated_at == datetime(2026, 5, 3, 17, 11, 46, tzinfo=UTC)


def test_yellow_before_low_speed_creates_candidate_after_duration() -> None:
    detector = IncidentDetector()
    assert detector.process_signals(_track(BASE)) == []
    assert detector.process_signals(_car_speed(BASE + timedelta(seconds=1), 0)) == []

    changes = detector.process_signals(_car_speed(BASE + timedelta(seconds=3), 0))

    assert len(changes) == 1
    assert changes[0].phase == PHASE_CANDIDATE
    assert changes[0].reason == "car_low_speed_with_track_status"


def test_cardata_candidate_promotes_with_timing_stopped() -> None:
    detector = IncidentDetector()
    detector.process_signals(_timing(BASE - timedelta(seconds=1), stopped=False))
    detector.process_signals(_car_speed(BASE, 0))
    detector.process_signals(_car_speed(BASE + timedelta(seconds=2), 0))
    candidate = detector.process_signals(_track(BASE + timedelta(seconds=5)))[0]

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=20), stopped=True)
    )

    assert len(changes) == 1
    assert changes[0].phase == PHASE_CONFIRMED
    assert changes[0].incident_id == candidate.incident_id
    assert "timing_stopped" in changes[0].signals
    assert "car_low_speed" in changes[0].signals


def test_strict_stopped_race_control_promotes_cardata_candidate() -> None:
    detector = IncidentDetector()
    detector.process_signals(_car_speed(BASE, 0))
    detector.process_signals(_car_speed(BASE + timedelta(seconds=2), 0))
    candidate = detector.process_signals(_track(BASE + timedelta(seconds=5)))[0]

    changes = detector.process_signals(
        _race_control(BASE + timedelta(seconds=6), "CAR 10 STOPPED ON TRACK")
    )

    assert len(changes) == 1
    assert changes[0].phase == PHASE_CONFIRMED
    assert changes[0].confidence == CONFIDENCE_HIGH
    assert changes[0].incident_id == candidate.incident_id
    assert changes[0].reason == "race_control_stopped_with_car_low_speed"


def test_low_speed_in_pit_is_suppressed() -> None:
    detector = IncidentDetector()
    detector.process_signals(
        _timing(BASE - timedelta(seconds=1), stopped=False, in_pit=True)
    )
    detector.process_signals(_car_speed(BASE, 0))
    detector.process_signals(_car_speed(BASE + timedelta(seconds=2), 0))

    changes = detector.process_signals(_track(BASE + timedelta(seconds=5)))

    assert changes == []
    assert detector.active_incidents(SESSION.session_key) == ()


def test_low_speed_candidate_is_suppressed_by_fresh_pit_lane_location() -> None:
    detector = IncidentDetector(
        location_resolver=lambda rn, at: IncidentLocationContext(
            status="PitLane",
            source="live",
            stale=False,
            confidence="high",
            description="pit lane",
            pit_lane=True,
            fallback_state="static_catalog",
            updated_at=at,
        )
    )
    detector.process_signals(_car_speed(BASE, 0))
    detector.process_signals(_car_speed(BASE + timedelta(seconds=2), 0))

    changes = detector.process_signals(_track(BASE + timedelta(seconds=5)))

    assert changes == []
    assert detector.active_incidents(SESSION.session_key) == ()


def test_low_speed_candidate_keeps_track_map_location_without_confirming() -> None:
    detector = IncidentDetector(
        location_resolver=lambda rn, at: IncidentLocationContext(
            status="OffTrack",
            source="live",
            stale=False,
            confidence="high",
            description="off track, sector 1",
            sector=1,
            pit_lane=False,
            track_segment=8,
            geometry_source="static_circuit_geometry",
            fallback_state="static_catalog",
            updated_at=at,
        )
    )
    detector.process_signals(_car_speed(BASE, 0))
    detector.process_signals(_car_speed(BASE + timedelta(seconds=2), 0))

    changes = detector.process_signals(_track(BASE + timedelta(seconds=5)))

    assert len(changes) == 1
    assert changes[0].phase == PHASE_CANDIDATE
    assert changes[0].confidence == CONFIDENCE_HIGH
    assert changes[0].reason == "car_low_speed_with_track_map_location"
    assert changes[0].location.status == "OffTrack"
    assert "position_status_off_track" in changes[0].signals


def test_low_speed_after_yellow_in_pit_is_suppressed() -> None:
    detector = IncidentDetector()
    detector.process_signals(_track(BASE))
    detector.process_signals(
        _timing(BASE + timedelta(seconds=1), stopped=False, in_pit=True)
    )
    detector.process_signals(_car_speed(BASE + timedelta(seconds=2), 0))

    changes = detector.process_signals(_car_speed(BASE + timedelta(seconds=4), 0))

    assert changes == []
    assert detector.active_incidents(SESSION.session_key) == ()


def test_recent_pit_out_suppresses_low_speed_candidate() -> None:
    detector = IncidentDetector()
    detector.process_signals(_timing(BASE, pit_out=True))
    detector.process_signals(_timing(BASE + timedelta(seconds=1), pit_out=False))
    detector.process_signals(_car_speed(BASE + timedelta(seconds=2), 0))
    detector.process_signals(_car_speed(BASE + timedelta(seconds=4), 0))

    changes = detector.process_signals(_track(BASE + timedelta(seconds=5)))

    assert changes == []


def test_recent_pit_out_after_yellow_suppresses_low_speed_candidate() -> None:
    detector = IncidentDetector()
    detector.process_signals(_track(BASE))
    detector.process_signals(_timing(BASE + timedelta(seconds=1), pit_out=True))
    detector.process_signals(_timing(BASE + timedelta(seconds=2), pit_out=False))
    detector.process_signals(_car_speed(BASE + timedelta(seconds=3), 0))

    changes = detector.process_signals(_car_speed(BASE + timedelta(seconds=5), 0))

    assert changes == []
    assert detector.active_incidents(SESSION.session_key) == ()


def test_bootstrap_cardata_is_not_used_for_live_context() -> None:
    detector = IncidentDetector()
    detector.process_signals(_car_speed(BASE, 0, data_quality=DATA_QUALITY_BOOTSTRAP))
    detector.process_signals(
        _car_speed(
            BASE + timedelta(seconds=2),
            0,
            data_quality=DATA_QUALITY_BOOTSTRAP,
        )
    )

    changes = detector.process_signals(_track(BASE + timedelta(seconds=5)))

    assert changes == []


def test_stale_cardata_is_not_used_for_context() -> None:
    detector = IncidentDetector()
    detector.process_signals(_car_speed(BASE, 0))
    detector.process_signals(_car_speed(BASE + timedelta(seconds=2), 0))

    changes = detector.process_signals(_track(BASE + timedelta(seconds=30)))

    assert changes == []


def test_global_red_with_too_many_low_speed_drivers_is_suppressed() -> None:
    detector = IncidentDetector(car_candidate_limit=2)
    for rn in ("6", "10", "30"):
        detector.process_signals(_car_speed(BASE, 0, rn=rn))
        detector.process_signals(_car_speed(BASE + timedelta(seconds=2), 0, rn=rn))

    changes = detector.process_signals(
        _track(BASE + timedelta(seconds=5), status="5", message="Red")
    )

    assert changes == []


def test_direct_cardata_candidates_respect_global_limit() -> None:
    detector = IncidentDetector(car_candidate_limit=2)
    detector.process_signals(_track(BASE))
    changes = []

    for rn in ("6", "10", "30"):
        detector.process_signals(_car_speed(BASE + timedelta(seconds=1), 0, rn=rn))
        changes.extend(
            detector.process_signals(_car_speed(BASE + timedelta(seconds=3), 0, rn=rn))
        )

    assert [(change.phase, change.driver.racing_number) for change in changes] == [
        (PHASE_CANDIDATE, "6"),
        (PHASE_CANDIDATE, "10"),
    ]
    assert detector.get_active_incident(SESSION.session_key, "30") is None


def test_red_flag_aborted_keeps_candidate_active_until_stopped_confirms() -> None:
    detector = IncidentDetector()
    detector.process_signals(
        _timing(BASE - timedelta(seconds=1), rn="30", stopped=False)
    )
    detector.process_signals(_car_speed(BASE, 0, rn="30"))
    detector.process_signals(_car_speed(BASE + timedelta(seconds=2), 0, rn="30"))
    candidate = detector.process_signals(_track(BASE + timedelta(seconds=5)))[0]

    assert (
        detector.process_signals(
            _session_status(BASE + timedelta(seconds=10), "Aborted")
        )
        == []
    )
    active = detector.get_active_incident(SESSION.session_key, "30")
    assert active is not None
    assert active.incident_id == candidate.incident_id

    changes = detector.process_signals(
        _timing(BASE + timedelta(seconds=20), rn="30", stopped=True)
    )

    assert len(changes) == 1
    assert changes[0].phase == PHASE_CONFIRMED
    assert changes[0].incident_id == candidate.incident_id


def test_movement_clears_unconfirmed_cardata_candidate() -> None:
    detector = IncidentDetector()
    detector.process_signals(_car_speed(BASE, 0))
    detector.process_signals(_car_speed(BASE + timedelta(seconds=2), 0))
    candidate = detector.process_signals(_track(BASE + timedelta(seconds=5)))[0]
    detector.process_signals(_car_speed(BASE + timedelta(seconds=6), 30))

    changes = detector.process_signals(_car_speed(BASE + timedelta(seconds=12), 40))

    assert len(changes) == 1
    assert changes[0].phase == PHASE_CLEARED
    assert changes[0].incident_id == candidate.incident_id
    assert changes[0].reason == "car_moving"
