"""Branch coverage for the provider-neutral Phase 4 analysis store."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from custom_components.f1_sensor.analysis import (
    Phase4AnalysisStore,
    TimelineEvent,
    UnifiedTimelineStore,
    _as_float,
    _as_int,
    _compound_crossover_indications,
    _items,
    _linear_fit,
    _linear_slope,
    _utc_text,
)


class _Bus:
    def __init__(self) -> None:
        self.callbacks = {}

    def subscribe(self, stream, callback):
        self.callbacks[stream] = callback
        return Mock()


def _store():
    lap_analysis = SimpleNamespace(
        snapshot=Mock(return_value={"laps": []}),
        get_lap=Mock(return_value=None),
        reset_session=Mock(),
    )
    return (
        Phase4AnalysisStore(_Bus(), lap_analysis, source_provider=lambda: "replay"),
        lap_analysis,
    )


def _event(event_id: str, title: str = "Event") -> TimelineEvent:
    return TimelineEvent(
        event_id=event_id,
        revision=0,
        sequence=0,
        provider="replay",
        session_id="session",
        occurred_at=None,
        offset_ms=None,
        category="test",
        kind="test",
        title=title,
    )


def test_analysis_scalar_helpers_and_regression_edges() -> None:
    assert _items([{"ok": 1}, "bad"]) == [("0", {"ok": 1})]
    assert _as_int({"Value": "4"}) == 4
    assert _as_int("bad") is None
    assert _as_float(None) is None
    assert _as_float("") is None
    assert _as_float("+1:30.5") == 90.5
    assert _as_float("3.2s") == 3.2
    assert _as_float("nan") is None
    assert _as_float("bad") is None
    assert _utc_text({"Date": "2026-09-01"}) == "2026-09-01"
    assert _linear_slope([(1, 1.0), (1, 2.0), (1, 3.0)]) is None
    assert _linear_fit([]) is None
    assert _linear_fit([(1, 1.0), (1, 2.0), (1, 3.0)]) is None
    assert _compound_crossover_indications({"SOFT": [(1, 90.0)]}) == []


def test_timeline_dedup_revision_and_bounded_retention() -> None:
    store = UnifiedTimelineStore(max_events=1)
    first = store.upsert(_event("same"))
    assert store.upsert(_event("same")) is first
    revised = store.upsert(_event("same", "Updated"))
    assert revised.revision == 2
    assert revised.sequence == first.sequence
    for index in range(25):
        store.upsert(_event(f"event-{index}"))
    snapshot = store.snapshot()
    assert len(snapshot) == 20
    assert snapshot[-1]["event_id"] == "event-24"


def test_analysis_stream_handler_matrix_and_session_reset() -> None:
    store, lap_analysis = _store()
    for handler in (
        store._on_session_info,
        store._on_session_status,
        store._on_track_status,
        store._on_driver_list,
        store._on_timing_app,
        store._on_timing_data,
        store._on_pit_stops,
        store._on_race_control,
        store._on_weather,
        store._on_team_radio,
    ):
        handler("bad")

    session = {
        "Key": 10,
        "Name": "Race",
        "SessionStatus": "Inactive",
        "Meeting": {"Key": 2, "Name": "Test GP"},
    }
    store._on_session_info(session)
    store._on_session_status({"Status": "Started"})
    store._on_session_info(session)
    assert lap_analysis.reset_session.called
    store._on_session_info({"Key": 11, "Name": "Sprint", "Meeting": {"Key": 2}})
    assert store._session_name == "Sprint"

    store._on_session_status({})
    store._on_session_status({"Status": "Started"})
    store._on_track_status({})
    store._on_track_status({"Status": "2", "Utc": "t", "Message": "Yellow"})
    store._on_track_status({"Status": "2"})
    store._on_track_status({"Status": "1", "Message": "Clear"})

    store._on_driver_list(
        {
            "Lines": {
                "bad": {"RacingNumber": "bad"},
                "4": {
                    "RacingNumber": 4,
                    "BroadcastName": "L NORRIS",
                    "Tla": "NOR",
                    "TeamName": "McLaren",
                },
            }
        }
    )
    store._on_timing_app({"Lines": {"4": {"Stints": {"1": {"Compound": "MEDIUM"}}}}})
    store._on_timing_data({"Lines": {"bad": {}, "4": {"Position": "1"}}})

    store._on_pit_stops(
        {
            "PitTimes": {
                "bad": {"0": {"Lap": 1}},
                "4": {"0": {"PitStop": {"Lap": 8, "Duration": "2.2"}}},
            }
        }
    )
    assert store._pit_context[4] == {8}

    store._on_race_control(
        {
            "Messages": [
                {},
                {"Id": 1, "Message": "LAP 8 DELETED FOR CAR 4", "Lap": 8},
                {"Id": 2, "Message": "LAP 8 REINSTATED FOR CAR 4", "Lap": 8},
                {"Id": 3, "Message": "5 SECOND PENALTY FOR CAR 4", "Lap": 8},
                {"Id": 4, "Message": "MESSAGE FOR CAR 4"},
            ]
        }
    )
    assert store._penalty_context[4] == {8}
    store._on_race_control({"Message": "CAR 81 NOTED", "Lap": 3})

    store._on_weather({})
    store._on_weather({"Rainfall": "1"})
    store._on_weather({"Rainfall": "0"})
    store._on_team_radio(
        {
            "Captures": [
                {"RacingNumber": "4", "Utc": "t"},
                {"Path": "unknown.mp3"},
            ]
        }
    )
    kinds = {event["kind"] for event in store.snapshot()["timeline"]["events"]}
    assert {"lap_deleted", "lap_reinstated", "penalty"} <= kinds
    assert store.diagnostics()["provider"] == "replay"


def test_strategy_capture_duplicate_invalid_and_trim_paths() -> None:
    store, lap_analysis = _store()
    store._timing["4"] = {"NumberOfLaps": 8, "Position": "2"}
    store._timing_app["4"] = {"Stints": {"1": {"Compound": "MEDIUM", "StartLaps": 3}}}
    valid_lap = {
        "driver_number": 4,
        "lap_number": 8,
        "lap_duration": 90.0,
        "quality": {"confidence": 0.9},
        "source_payload": {"large": True},
    }
    lap_analysis.snapshot.return_value = {"laps": ["bad", {}, valid_lap]}
    store._capture_strategy_laps()
    assert store._strategy_laps[(4, 8)]["compound"] == "MEDIUM"
    assert "source_payload" not in store._strategy_laps[(4, 8)]

    store._timing_app["4"] = {}
    store._timing["4"]["Position"] = "1"
    lap_analysis.snapshot.return_value = {"laps": [valid_lap]}
    store._capture_strategy_laps()
    assert store._strategy_laps[(4, 8)]["position"] == 2

    store._previous_positions = {1: 1, 4: 2}
    store._timing = {"1": {"Position": "1"}, "4": {"Position": "1"}}
    store._detect_position_exchanges()
    assert store._previous_positions == {1: 1, 4: 2}
    assert store._has_lap_context({}, 4, None) is False
    store._timing["bad"] = {"Position": "bad"}
    assert all(item["driver_number"] != "bad" for item in store._timing_snapshot())
