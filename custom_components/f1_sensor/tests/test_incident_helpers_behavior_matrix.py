"""Branch coverage for incident normalizers and detector context updates."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from custom_components.f1_sensor import incident_detection as incident
from custom_components.f1_sensor.helpers import CARDATA_MAX_ENTRIES
from custom_components.f1_sensor.incident_detection import (
    CONFIDENCE_HIGH,
    DATA_QUALITY_BOOTSTRAP,
    PHASE_CLEARED,
    PHASE_CONFIRMED,
    PHASE_UPDATED,
    TRACK_STATUS_SC,
    TRACK_STATUS_VSC,
    DriverMetadata,
    IncidentDetector,
    IncidentLocationContext,
    IncidentSignal,
    RaceControlContext,
    SessionMetadata,
    TrackStatusContext,
    _build_session_key,
    _coerce_bool,
    _coerce_float,
    _extract_car_data_entries,
    _extract_race_control_items,
    _iter_series_items,
    _location_signal_names,
    _merge_location_context,
    _merge_race_context,
    _merge_track_context,
    _normalize_session_status_value,
    _normalize_team_color,
    _normalize_track_status_value,
    _parse_utc,
    _reason_for_car_context,
    _reason_for_context,
    decode_car_data_payload,
    normalize_car_data,
    normalize_driver_list,
    normalize_session_data,
    normalize_session_info,
    normalize_session_status,
    normalize_session_type,
    normalize_stream,
    normalize_timing_data,
)

NOW = datetime(2026, 9, 1, 12, tzinfo=UTC)


def test_incident_scalar_normalizer_edges() -> None:
    assert _parse_utc(datetime(2026, 9, 1, 12)) == NOW
    assert _parse_utc(" ", default=NOW) == NOW
    assert _parse_utc("bad", default=NOW) == NOW
    assert _coerce_bool(1.0) is True
    assert _coerce_bool("n") is False
    assert _coerce_bool("bad") is None
    assert _coerce_float(None) is None
    assert _coerce_float(" ") is None
    assert _coerce_float("2.5") == 2.5
    assert _coerce_float("bad") is None
    assert _coerce_float([]) is None
    assert _normalize_track_status_value({"Message": "DOUBLE-YELLOW"}) == "YELLOW"
    assert _normalize_track_status_value({"Status": "4"}) == "SC"
    assert _normalize_track_status_value({"Message": "RED"}) == "RED"
    assert _normalize_track_status_value({}) is None
    assert _normalize_session_status_value({}) is None
    assert _normalize_session_status_value({"Started": True}) == "Started"
    assert _normalize_session_status_value({"Started": False}) == "Inactive"
    assert _normalize_session_status_value({"Status": " "}) is None
    assert _normalize_team_color(None) is None
    assert _normalize_team_color("abc") is None
    assert _normalize_team_color("zzzzzz") is None
    assert _normalize_team_color("#ff8700") == "#FF8700"
    assert _build_session_key(None, None, None) == "unknown-session"


def test_incident_collection_and_context_helper_edges() -> None:
    assert _extract_race_control_items([{"ok": 1}, "bad"]) == [{"ok": 1}]
    assert _extract_race_control_items("bad") == []
    assert _extract_race_control_items({"Messages": "bad"}) == []
    assert _extract_race_control_items(
        {"Messages": {"2": {"id": 2}, "1": {"id": 1}, "bad": {}}}
    ) == [{"id": 1}, {"id": 2}]
    assert list(_iter_series_items([{"ok": 1}, "bad"])) == [{"ok": 1}]
    assert list(_iter_series_items({"2": {"id": 2}, "1": {"id": 1}, "bad": {}})) == [
        {"id": 1},
        {"id": 2},
    ]

    empty_track = TrackStatusContext()
    track = TrackStatusContext(TRACK_STATUS_SC, "SC deployed")
    empty_race = RaceControlContext()
    race = RaceControlContext("Stopped car", "Other", None)
    assert _merge_track_context(track, empty_track) is track
    assert _merge_track_context(empty_track, track) is track
    assert _merge_race_context(race, empty_race) is race
    assert _merge_race_context(empty_race, race) is race
    empty_location = IncidentLocationContext()
    location = IncidentLocationContext(
        status="OffTrack", stale=False, sector=2, confidence=CONFIDENCE_HIGH
    )
    assert _merge_location_context(location, empty_location) is location
    assert _merge_location_context(empty_location, location) is location
    assert _location_signal_names(location) == (
        "track_map_location",
        "position_status_off_track",
        "track_map_sector_2",
    )
    assert _location_signal_names(
        IncidentLocationContext(status="PitLane", stale=False)
    ) == ("track_map_location", "position_status_pit_lane")
    assert _reason_for_context(track_context=track).endswith("safety_car_context")
    assert _reason_for_context(
        track_context=TrackStatusContext(TRACK_STATUS_VSC)
    ).endswith("vsc_context")
    assert _reason_for_context(race_context=race).endswith("race_control")
    assert _reason_for_context(track_context=TrackStatusContext("YELLOW")).endswith(
        "track_status"
    )
    assert _reason_for_car_context(track_context=track).endswith("safety_car_context")
    assert _reason_for_car_context(
        track_context=TrackStatusContext(TRACK_STATUS_VSC)
    ).endswith("vsc_context")
    assert _reason_for_car_context(track_context=TrackStatusContext("RED")).endswith(
        "red_flag_context"
    )
    assert _reason_for_car_context(race_context=race).endswith("race_control")
    assert _reason_for_car_context(track_context=TrackStatusContext("YELLOW")).endswith(
        "track_status"
    )
    assert _reason_for_car_context() == "car_low_speed"


def test_stream_normalizer_invalid_and_alternate_shapes() -> None:
    session = SessionMetadata(session_key="session")
    drivers = {"4": DriverMetadata("4", tla="NOR")}
    assert normalize_stream("Unknown", {}) == []
    assert normalize_timing_data("bad") == []
    assert normalize_timing_data({"Lines": []}) == []
    timing = normalize_timing_data(
        {
            "Lines": {
                "bad": "skip",
                "4": {
                    "RacingNumber": "4",
                    "InPit": "bad",
                    "PitOut": "yes",
                    "Retired": 0,
                    "Stopped": 1,
                },
            }
        },
        NOW,
        session=session,
        drivers=drivers,
    )
    assert [signal.kind for signal in timing] == [
        "timing_pit_out",
        "timing_retired",
        "timing_stopped",
    ]
    assert all(signal.driver == drivers["4"] for signal in timing)

    assert normalize_session_status("bad") == []
    assert normalize_session_status({}) == []
    assert normalize_session_status({"Started": False})[0].value == "Inactive"
    assert normalize_session_data("bad") == []
    session_data = normalize_session_data(
        {
            "StatusSeries": [
                {"Utc": "bad"},
                {"Utc": "2026-09-01T12:00:00Z", "Status": "Started"},
            ]
        },
        NOW,
    )
    assert len(session_data) == 1

    assert normalize_session_info("bad") == []
    metadata = normalize_session_info(
        {
            "Type": "Grand Prix",
            "Meeting": "Test GP",
            "ArchiveStatus": {"Path": "2026/test/race"},
        },
        NOW,
    )[0].session
    assert metadata.session_type == "race"
    assert metadata.session_key == "2026/test/race"

    assert normalize_driver_list("bad") == []
    driver_signals = normalize_driver_list(
        {
            "bad": "skip",
            "5": {"Line": 1},
            "4": {
                "Tla": "nor",
                "BroadcastName": "L NORRIS",
                "TeamColour": "ff8700",
            },
        },
        NOW,
        session=session,
    )
    assert len(driver_signals) == 1
    assert driver_signals[0].driver.team_color == "#FF8700"
    assert normalize_session_type("") == "unknown"
    assert normalize_session_type("not a session") == "unknown"
    assert normalize_stream("SessionData", {"StatusSeries": []}) == []
    assert normalize_stream("SessionStatus", {}) == []
    assert normalize_timing_data({"Lines": {"": {"Stopped": True}}}) == []
    assert incident.normalize_track_status({"Message": "unknown"}) == []
    generated_session = normalize_session_info({"Name": "Race", "Type": "Race"})
    assert generated_session[0].session.session_key
    assert normalize_driver_list({"": {"Tla": "BAD"}}) == []


def test_car_data_shape_limits_and_invalid_cars() -> None:
    assert _extract_car_data_entries({"Cars": {}}) == [{"Cars": {}}]
    assert _extract_car_data_entries({"Entries": "bad"}) == []
    assert _extract_car_data_entries([{"Cars": {}}, "bad"]) == [{"Cars": {}}]
    assert _extract_car_data_entries([{}] * (CARDATA_MAX_ENTRIES + 1)) == []
    assert (
        _extract_car_data_entries({"Entries": [{}] * (CARDATA_MAX_ENTRIES + 1)}) == []
    )
    assert _extract_car_data_entries("\n") == []
    assert decode_car_data_payload(b"not encoded") == []
    signals = normalize_car_data(
        {
            "Entries": [
                {"Cars": "bad"},
                {
                    "Utc": "2026-09-01T12:00:00Z",
                    "Cars": {
                        "bad": "skip",
                        "": {"Channels": {"2": 1}},
                        "4": {"Channels": {"2": "bad"}},
                        "81": {"Channels": {"2": "42.5"}},
                    },
                },
            ]
        },
        NOW,
    )
    assert len(signals) == 1
    assert signals[0].racing_number == "81"
    assert signals[0].value == 42.5


def test_incident_encoded_car_data_and_remaining_helper_edges(monkeypatch) -> None:
    monkeypatch.setattr(
        incident,
        "_decode_car_data_line",
        lambda _line: {"Entries": [{}] * (CARDATA_MAX_ENTRIES + 1)},
    )
    assert incident._extract_car_data_entries("encoded") == []
    monkeypatch.setattr(
        incident,
        "_decode_car_data_line",
        lambda _line: {"Cars": {"4": {}}},
    )
    assert incident._extract_car_data_entries("encoded") == [{"Cars": {"4": {}}}]
    assert incident._car_speed_from_payload({}) is None

    signal = IncidentSignal(
        "track_status",
        datetime(2026, 9, 1, 12),
        session_key="session",
    )
    assert incident._normalize_signal_datetime(signal).observed_at.tzinfo is UTC
    assert incident._parse_utc("2026-09-01T12:00:00").tzinfo is UTC
    assert incident._normalize_track_status_value({"Message": "CLEAR"}) == "CLEAR"
    assert incident._normalize_track_status_value({"Message": "VSC"}) == "VSC"
    assert IncidentDetector()._is_recent_pit_out(
        SimpleNamespace(pit_out=True, pit_out_at=None), NOW
    )
    assert incident._extract_race_control_items({"Category": "Other"}) == [
        {"Category": "Other"}
    ]
    assert incident._extract_racing_numbers({"Car": 4}) == ("4",)


def test_detector_uses_default_session_and_ignores_clear_track_status() -> None:
    detector = IncidentDetector()
    detector.process_signals([IncidentSignal("unknown", NOW, session_key="")])
    assert incident.DEFAULT_SESSION_KEY in detector._sessions
    assert (
        detector.process_signals(
            [
                IncidentSignal(
                    "track_status",
                    NOW,
                    session_key=incident.DEFAULT_SESSION_KEY,
                    track_status="CLEAR",
                )
            ]
        )
        == []
    )


def test_detector_track_context_update_terminal_and_guard_paths() -> None:
    detector = IncidentDetector()
    session = SessionMetadata(session_key="session", session_name="Race")
    detector.process_signals(
        [
            IncidentSignal("unknown", NOW, session_key="session", session=session),
            IncidentSignal("data_gap", NOW, session_key="session", session=session),
            IncidentSignal(
                "session_status",
                NOW,
                session_key="session",
                value="Started",
                session=session,
            ),
            IncidentSignal(
                "timing_stopped",
                NOW,
                session_key="session",
                racing_number="4",
                value=False,
                driver=DriverMetadata("4", tla="NOR"),
                session=session,
            ),
        ]
    )
    confirmed = detector.process_signals(
        [
            IncidentSignal(
                "timing_stopped",
                NOW + timedelta(seconds=1),
                session_key="session",
                racing_number="4",
                value=True,
                session=session,
            )
        ]
    )
    assert confirmed[0].phase == PHASE_CONFIRMED
    assert (
        detector.process_signals(
            [IncidentSignal("track_status", NOW, session_key="session")]
        )
        == []
    )
    updated = detector.process_signals(
        [
            IncidentSignal(
                "track_status",
                NOW + timedelta(seconds=2),
                session_key="session",
                value="YELLOW",
                track_status="YELLOW",
                message="Yellow",
                session=session,
            )
        ]
    )
    assert updated[0].phase == PHASE_UPDATED
    assert updated[0].confidence == CONFIDENCE_HIGH
    assert (
        detector.process_signals(
            [
                IncidentSignal(
                    "track_status",
                    NOW + timedelta(seconds=3),
                    session_key="session",
                    value="YELLOW",
                    track_status="YELLOW",
                    session=session,
                )
            ]
        )
        == []
    )
    cleared = detector.process_signals(
        [
            IncidentSignal(
                "session_status",
                NOW + timedelta(seconds=4),
                session_key="session",
                value="Finished",
                session=session,
            )
        ]
    )
    assert cleared[0].phase == PHASE_CLEARED
    assert detector.get_active_incident("missing", "4") is None
    assert detector.get_active_incident("session", "missing") is None


def test_detector_car_speed_ignored_quality_and_inactive_paths() -> None:
    detector = IncidentDetector()
    session = SessionMetadata(session_key="session")
    assert (
        detector.process_signals(
            [
                IncidentSignal(
                    "car_speed",
                    NOW,
                    session_key="session",
                    racing_number="4",
                    value="bad",
                    session=session,
                )
            ]
        )
        == []
    )
    assert (
        detector.process_signals(
            [
                IncidentSignal(
                    "car_speed",
                    NOW,
                    session_key="session",
                    racing_number="4",
                    value=0,
                    data_quality=DATA_QUALITY_BOOTSTRAP,
                    session=session,
                )
            ]
        )
        == []
    )
    detector.process_signals(
        [
            IncidentSignal(
                "session_status",
                NOW,
                session_key="session",
                value="Finished",
                session=session,
            )
        ]
    )
    assert (
        detector.process_signals(
            [
                IncidentSignal(
                    "car_speed",
                    NOW + timedelta(seconds=1),
                    session_key="session",
                    racing_number="4",
                    value=0,
                    session=session,
                )
            ]
        )
        == []
    )
