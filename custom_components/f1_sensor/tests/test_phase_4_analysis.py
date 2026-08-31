"""Acceptance tests for Phase 4 analysis and main-experience contracts."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import zlib

import pytest

from custom_components.f1_sensor.analysis import (
    PHASE4_ANALYSIS_STREAMS,
    Phase4AnalysisStore,
    analyze_strategy,
    historical_timeline,
)
from custom_components.f1_sensor.history import LapAnalysisStore
from custom_components.f1_sensor.replay_telemetry import ReplayTelemetryService

FIXTURES = Path(__file__).parent / "fixtures"


class _Bus:
    def __init__(self) -> None:
        self.callbacks: dict[str, list] = {}

    def subscribe(self, stream, callback):
        self.callbacks.setdefault(stream, []).append(callback)

        def _unsubscribe():
            self.callbacks[stream].remove(callback)

        return _unsubscribe

    def emit(self, stream: str, payload: dict) -> None:
        for callback in tuple(self.callbacks.get(stream, [])):
            callback(payload)


def _timing_lap(
    driver: str,
    lap: int,
    seconds: float,
    position: int,
    gap: str,
    *,
    gap_to_leader: str | None = None,
) -> dict:
    sector = seconds / 3
    return {
        "Lines": {
            driver: {
                "NumberOfLaps": lap,
                "Position": str(position),
                "IntervalToPositionAhead": {"Value": gap},
                "GapToLeader": gap_to_leader,
                "LastLapTime": {"Value": f"{seconds:.3f}"},
                "Sectors": {
                    "0": {"Value": f"{sector:.3f}"},
                    "1": {"Value": f"{sector:.3f}"},
                    "2": {"Value": f"{sector:.3f}"},
                },
            }
        }
    }


def _timing_pair(
    lap: int,
    *,
    first_position: int,
    second_position: int,
    first_gap: str,
    second_gap: str,
) -> dict:
    first = _timing_lap(
        "1",
        lap,
        90.0,
        first_position,
        first_gap,
        gap_to_leader="" if first_position == 1 else first_gap,
    )
    second = _timing_lap(
        "4",
        lap,
        90.2,
        second_position,
        second_gap,
        gap_to_leader="" if second_position == 1 else second_gap,
    )
    return {"Lines": {**first["Lines"], **second["Lines"]}}


def test_strategy_analyzer_matches_provider_neutral_golden_output() -> None:
    case = json.loads(
        (FIXTURES / "phase4_strategy_case.json").read_text(encoding="utf-8")
    )

    result = analyze_strategy(case["laps"], case["drivers"])
    driver_4 = next(item for item in result["stints"] if item["driver_number"] == 4)
    compound = result["compound_comparison"][0]
    teammate = result["teammate_comparisons"][0]

    assert result["analysis_type"] == "local_estimate"
    assert driver_4["adjusted_median_clean_pace"] == case["expected"]["driver_4_median"]
    assert driver_4["degradation_seconds_per_lap"] == case["expected"]["driver_4_slope"]
    assert driver_4["confidence"] == case["expected"]["driver_4_confidence"]
    assert compound["median_clean_pace"] == case["expected"]["compound_median"]
    assert compound["sample_count"] == case["expected"]["compound_samples"]
    assert teammate["delta_seconds"] == case["expected"]["teammate_delta"]
    assert teammate["faster_driver"] == case["expected"]["faster_driver"]
    assert "not official strategy" in result["assumptions"][1]


def test_strategy_analyzer_reports_evidence_backed_undercut_outcome() -> None:
    laps = []
    for lap_number in range(1, 9):
        laps.extend(
            [
                {
                    "driver_number": 4,
                    "lap_number": lap_number,
                    "lap_duration": 90.0,
                    "stint_index": 1 if lap_number >= 4 else 0,
                    "compound": "MEDIUM" if lap_number >= 4 else "HARD",
                    "position": 1 if lap_number >= 7 else 2,
                    "quality": {"clean": True, "confidence": 1.0},
                },
                {
                    "driver_number": 81,
                    "lap_number": lap_number,
                    "lap_duration": 90.2,
                    "stint_index": 1 if lap_number >= 6 else 0,
                    "compound": "MEDIUM" if lap_number >= 6 else "HARD",
                    "position": 2 if lap_number >= 7 else 1,
                    "quality": {"clean": True, "confidence": 1.0},
                },
            ]
        )

    result = analyze_strategy(
        laps,
        {
            "4": {"name": "Lando Norris", "team": "McLaren"},
            "81": {"name": "Oscar Piastri", "team": "McLaren"},
        },
    )

    outcome = result["undercut_overcut_outcomes"][0]
    assert outcome["result"] == "undercut_succeeded"
    assert outcome["successful_driver"] == 4
    assert outcome["supporting_signals"] == [
        "stint_transition",
        "lap_position_before",
        "lap_position_after",
    ]


def test_strategy_waits_for_clean_laps_and_reports_observed_coverage() -> None:
    result = analyze_strategy(
        [
            {
                "driver_number": 30,
                "lap_number": lap_number,
                "lap_duration": duration,
                "stint_index": 1,
                "compound": "HARD",
                "quality": {
                    "clean": False,
                    "confidence": 1.0,
                    "reasons": ["first_lap_after_safety_car"],
                },
            }
            for lap_number, duration in ((34, 111.787), (35, 111.503))
        ]
    )

    assert result["status"] == "waiting_for_clean_laps"
    assert result["coverage"] == {
        "raw_laps": 2,
        "clean_laps": 0,
        "excluded_laps": 2,
        "observed_compounds": ["HARD"],
        "excluded_reason_counts": {"first_lap_after_safety_car": 2},
    }
    assert result["stints"][0]["excluded_reason_counts"] == {
        "first_lap_after_safety_car": 2
    }
    assert result["compound_comparison"] == []


def test_lap_analysis_excludes_only_one_post_safety_car_lap_per_driver() -> None:
    bus = _Bus()
    store = LapAnalysisStore(bus, source_provider=lambda: "replay")

    bus.emit("TrackStatus", {"Status": "1"})
    bus.emit(
        "TimingData",
        _timing_pair(
            1, first_position=1, second_position=2, first_gap="", second_gap="+0.4"
        ),
    )
    bus.emit("TrackStatus", {"Status": "7"})
    bus.emit(
        "TimingData",
        _timing_pair(
            2, first_position=1, second_position=2, first_gap="", second_gap="+0.5"
        ),
    )
    bus.emit("TrackStatus", {"Status": "1"})
    bus.emit(
        "TimingData",
        _timing_pair(
            3, first_position=1, second_position=2, first_gap="", second_gap="+0.6"
        ),
    )
    bus.emit(
        "TimingData",
        _timing_pair(
            4, first_position=1, second_position=2, first_gap="", second_gap="+0.7"
        ),
    )

    laps = {
        (item["driver_number"], item["lap_number"]): item
        for item in store.snapshot()["laps"]
    }
    for driver in (1, 4):
        assert "safety_car_or_red_flag" in laps[(driver, 2)]["quality"]["reasons"]
        assert "first_lap_after_safety_car" in laps[(driver, 3)]["quality"]["reasons"]
        assert laps[(driver, 4)]["quality"]["clean"] is True
        assert (
            "first_lap_after_safety_car" not in laps[(driver, 4)]["quality"]["reasons"]
        )


def test_lap_analysis_keeps_completed_sectors_after_next_lap_resets_them() -> None:
    bus = _Bus()
    store = LapAnalysisStore(bus, source_provider=lambda: "replay")

    bus.emit("TrackStatus", {"Status": "1"})
    bus.emit("TimingData", _timing_lap("30", 34, 111.787, 7, "+0.698"))
    bus.emit(
        "TimingData",
        {
            "Lines": {
                "30": {
                    "Sectors": {
                        "0": {"Value": ""},
                        "1": {"Value": ""},
                        "2": {"Value": ""},
                    }
                }
            }
        },
    )

    lap = store.snapshot()["laps"][0]
    assert lap["quality"]["clean"] is True
    assert all(value is not None for value in lap["sector_durations"])


def test_driver_list_sparse_delta_preserves_identity() -> None:
    bus = _Bus()
    lap_store = LapAnalysisStore(bus, source_provider=lambda: "replay")
    store = Phase4AnalysisStore(bus, lap_store, source_provider=lambda: "replay")

    bus.emit(
        "DriverList",
        {
            "Lines": {
                "30": {
                    "RacingNumber": "30",
                    "FullName": "Liam Lawson",
                    "Tla": "LAW",
                    "TeamName": "Racing Bulls",
                    "TeamColour": "6692FF",
                }
            }
        },
    )
    bus.emit("DriverList", {"Lines": {"30": {"Line": 6}}})

    assert store.snapshot()["drivers"] == [
        {
            "driver_number": 30,
            "name": "Liam Lawson",
            "tla": "LAW",
            "team": "Racing Bulls",
            "team_color": "6692FF",
        }
    ]


def test_timing_delta_does_not_rescan_every_stored_lap() -> None:
    bus = _Bus()
    lap_store = LapAnalysisStore(bus, source_provider=lambda: "replay")
    Phase4AnalysisStore(bus, lap_store, source_provider=lambda: "replay")

    bus.emit(
        "TimingData",
        _timing_pair(
            1,
            first_position=1,
            second_position=2,
            first_gap="",
            second_gap="+0.4",
        ),
    )
    with patch.object(
        lap_store,
        "snapshot",
        side_effect=AssertionError("TimingData must not rescan the full lap store"),
    ):
        bus.emit(
            "TimingData",
            {"Lines": {"4": {"IntervalToPositionAhead": {"Value": "+0.3"}}}},
        )


def test_strategy_preserves_the_position_recorded_at_each_completed_lap() -> None:
    bus = _Bus()
    lap_store = LapAnalysisStore(bus, source_provider=lambda: "replay")
    store = Phase4AnalysisStore(bus, lap_store, source_provider=lambda: "replay")

    bus.emit(
        "TimingData",
        _timing_pair(
            1,
            first_position=1,
            second_position=2,
            first_gap="",
            second_gap="+0.4",
        ),
    )
    bus.emit(
        "TimingData",
        _timing_pair(
            2,
            first_position=2,
            second_position=1,
            first_gap="+0.2",
            second_gap="",
        ),
    )

    assert store._strategy_laps[(1, 1)]["position"] == 1
    assert store._strategy_laps[(4, 1)]["position"] == 2
    assert store._strategy_laps[(1, 2)]["position"] == 2
    assert store._strategy_laps[(4, 2)]["position"] == 1


def test_phase4_store_unifies_timeline_strategy_exchanges_and_battles() -> None:
    bus = _Bus()
    lap_store = LapAnalysisStore(bus, source_provider=lambda: "replay")
    store = Phase4AnalysisStore(bus, lap_store, source_provider=lambda: "replay")

    assert PHASE4_ANALYSIS_STREAMS <= set(bus.callbacks)
    bus.emit(
        "SessionInfo",
        {"Key": 10, "Name": "Race", "Type": "Race", "Meeting": {"Key": 2}},
    )
    bus.emit("SessionStatus", {"Status": "Started", "Started": True})
    bus.emit(
        "DriverList",
        {
            "1": {
                "RacingNumber": "1",
                "FullName": "Max Verstappen",
                "TeamName": "Red Bull Racing",
            },
            "4": {
                "RacingNumber": "4",
                "FullName": "Lando Norris",
                "TeamName": "McLaren",
            },
        },
    )
    bus.emit(
        "TimingAppData",
        {
            "Lines": {
                "1": {"Stints": {"0": {"Compound": "HARD", "StartLaps": 0}}},
                "4": {"Stints": {"0": {"Compound": "MEDIUM", "StartLaps": 0}}},
            }
        },
    )
    for lap, first_time, second_time in (
        (1, 90.0, 90.3),
        (2, 90.2, 90.5),
        (3, 90.4, 90.7),
    ):
        bus.emit("TimingData", _timing_lap("1", lap, first_time, 1, "0"))
        bus.emit("TimingData", _timing_lap("4", lap, second_time, 2, "+0.7"))

    snapshot = store.snapshot()

    assert snapshot["phase"] == "live"
    assert snapshot["strategy"]["status"] == "ready"
    assert any(
        event["kind"] == "lap_completed" for event in snapshot["timeline"]["events"]
    )
    assert snapshot["battles"]["active"][0]["kind"] == "battle_started"
    assert snapshot["capabilities"]["strategy"] == "ready"

    switched = _timing_pair(
        4,
        first_position=2,
        second_position=1,
        first_gap="+0.3",
        second_gap="",
    )
    bus.emit("TimingData", switched)
    assert store.snapshot()["position_exchanges"] == []
    bus.emit("TimingData", switched)
    exchange = store.snapshot()["position_exchanges"][-1]

    assert exchange["kind"] == "likely_on_track_overtake"
    assert exchange["confidence"] == 0.85
    assert exchange["supporting_signals"] == ["TimingData", "close_gap"]
    assert store.snapshot()["position_exchange_count"] == 1

    timing = {item["driver_number"]: item for item in store.snapshot()["timing"]}
    assert timing[1]["position"] == 2
    assert timing[1]["gap_to_leader"] == "+0.3"
    assert timing[4]["position"] == 1
    assert timing[4]["interval_to_ahead"] is None


def test_position_exchange_remains_neutral_with_pit_context() -> None:
    bus = _Bus()
    lap_store = LapAnalysisStore(bus, source_provider=lambda: "f1_live")
    store = Phase4AnalysisStore(bus, lap_store, source_provider=lambda: "f1_live")
    bus.emit("TimingData", _timing_lap("1", 5, 90.0, 1, "0"))
    bus.emit("TimingData", _timing_lap("4", 5, 90.1, 2, "+0.4"))
    bus.emit(
        "PitStopSeries",
        {"PitTimes": {"1": {"0": {"PitStop": {"Lap": 6, "Duration": "2.3"}}}}},
    )
    switched = _timing_pair(
        6,
        first_position=2,
        second_position=1,
        first_gap="+0.2",
        second_gap="",
    )
    bus.emit("TimingData", switched)
    bus.emit("TimingData", switched)

    exchange = store.snapshot()["position_exchanges"][-1]

    assert exchange["kind"] == "position_exchange"
    assert exchange["confidence"] == 0.55
    assert "pit_context" in exchange["supporting_signals"]


def test_position_exchange_remains_neutral_while_a_driver_is_in_the_pit() -> None:
    bus = _Bus()
    lap_store = LapAnalysisStore(bus, source_provider=lambda: "replay")
    store = Phase4AnalysisStore(bus, lap_store, source_provider=lambda: "replay")
    bus.emit(
        "TimingData",
        _timing_pair(
            10,
            first_position=1,
            second_position=2,
            first_gap="",
            second_gap="+0.4",
        ),
    )
    switched = _timing_pair(
        11,
        first_position=2,
        second_position=1,
        first_gap="+0.2",
        second_gap="",
    )
    switched["Lines"]["1"]["InPit"] = True
    bus.emit("TimingData", switched)
    bus.emit("TimingData", switched)

    exchange = store.snapshot()["position_exchanges"][-1]
    assert exchange["kind"] == "position_exchange"
    assert exchange["confidence"] == 0.55
    assert "pit_state" in exchange["supporting_signals"]


def test_pre_race_positions_do_not_create_exchanges_or_battles() -> None:
    bus = _Bus()
    lap_store = LapAnalysisStore(bus, source_provider=lambda: "replay")
    store = Phase4AnalysisStore(bus, lap_store, source_provider=lambda: "replay")
    initial = {
        "Lines": {
            "1": {
                "Position": "1",
                "IntervalToPositionAhead": {"Value": ""},
            },
            "4": {
                "Position": "2",
                "IntervalToPositionAhead": {"Value": "+0.4"},
            },
        }
    }
    switched = {
        "Lines": {
            "1": {
                "Position": "2",
                "IntervalToPositionAhead": {"Value": "+0.2"},
            },
            "4": {
                "Position": "1",
                "IntervalToPositionAhead": {"Value": ""},
            },
        }
    }

    for _ in range(3):
        bus.emit("TimingData", initial)
    for _ in range(3):
        bus.emit("TimingData", switched)

    snapshot = store.snapshot()
    assert snapshot["position_exchanges"] == []
    assert snapshot["position_exchange_count"] == 0
    assert snapshot["battles"]["active"] == []
    assert snapshot["battles"]["history"] == []


def test_finished_session_closes_active_battles() -> None:
    bus = _Bus()
    lap_store = LapAnalysisStore(bus, source_provider=lambda: "replay")
    store = Phase4AnalysisStore(bus, lap_store, source_provider=lambda: "replay")
    close_pair = _timing_pair(
        4,
        first_position=1,
        second_position=2,
        first_gap="",
        second_gap="+0.4",
    )
    for _ in range(3):
        bus.emit("TimingData", close_pair)
    assert len(store.snapshot()["battles"]["active"]) == 1

    bus.emit("SessionStatus", {"Status": "Finished"})

    snapshot = store.snapshot()
    assert snapshot["phase"] == "after"
    assert snapshot["battles"]["active"] == []
    assert snapshot["battles"]["history"][-1]["kind"] == "battle_ended"
    assert snapshot["battles"]["history"][-1]["supporting_signals"] == [
        "SessionStatus",
        "session_finished",
    ]


def test_restarting_the_same_replay_session_resets_previous_analysis() -> None:
    bus = _Bus()
    lap_store = LapAnalysisStore(bus, source_provider=lambda: "replay")
    store = Phase4AnalysisStore(bus, lap_store, source_provider=lambda: "replay")
    session = {
        "Key": 11334,
        "Name": "Race",
        "Type": "Race",
        "Meeting": {"Key": 1290},
    }
    bus.emit("SessionInfo", session)
    bus.emit("SessionStatus", {"Status": "Started"})
    close_pair = _timing_pair(
        4,
        first_position=1,
        second_position=2,
        first_gap="",
        second_gap="+0.4",
    )
    for _ in range(3):
        bus.emit("TimingData", close_pair)
    bus.emit("SessionStatus", {"Status": "Finished"})
    assert store.snapshot()["strategy"]["stints"]
    assert lap_store.snapshot()["laps"]

    bus.emit("SessionInfo", {**session, "SessionStatus": "Inactive"})

    snapshot = store.snapshot()
    assert snapshot["session_id"] == "1290:11334:Race"
    assert snapshot["phase"] == "before"
    assert snapshot["strategy"]["stints"] == []
    assert snapshot["position_exchange_count"] == 0
    assert snapshot["battles"]["active"] == []
    assert snapshot["battles"]["history"] == []
    assert lap_store.snapshot()["laps"] == []


def test_replay_reset_clears_session_identity_and_accumulated_analysis() -> None:
    bus = _Bus()
    lap_store = LapAnalysisStore(bus, source_provider=lambda: "replay")
    store = Phase4AnalysisStore(bus, lap_store, source_provider=lambda: "replay")
    bus.emit(
        "SessionInfo",
        {
            "Key": 11334,
            "Name": "Race",
            "Type": "Race",
            "Meeting": {"Key": 1290},
        },
    )
    bus.emit("SessionStatus", {"Status": "Started"})
    close_pair = _timing_pair(
        4,
        first_position=1,
        second_position=2,
        first_gap="",
        second_gap="+0.4",
    )
    for _ in range(3):
        bus.emit("TimingData", close_pair)

    assert store.snapshot()["session_id"] == "1290:11334:Race"
    assert lap_store.snapshot()["laps"]

    lap_store.reset_for_replay()
    store.reset_for_replay()

    snapshot = store.snapshot()
    assert snapshot["session_id"] is None
    assert snapshot["session_name"] is None
    assert snapshot["phase"] == "before"
    assert snapshot["strategy"]["stints"] == []
    assert snapshot["position_exchange_count"] == 0
    assert snapshot["battles"]["active"] == []
    assert snapshot["battles"]["history"] == []
    assert lap_store.snapshot()["session_id"] is None
    assert lap_store.snapshot()["laps"] == []


def test_historical_timeline_uses_same_contract_without_inventing_overtakes() -> None:
    result = historical_timeline(
        year=2025,
        round_number=24,
        session_type="Race",
        results=[
            {"driver_number": 4, "driver_name": "Lando Norris", "position": 1},
            {"driver_number": 81, "driver_name": "Oscar Piastri", "position": 2},
        ],
    )

    assert result["provider"] == "jolpica"
    assert {event["kind"] for event in result["events"]} == {
        "session_finalised",
        "final_classification",
    }
    assert result["coverage"]["position_exchanges"] == "not_inferred_from_results"
    assert all(
        set(event) >= {"event_id", "revision", "sequence", "provider", "confidence"}
        for event in result["events"]
    )


def _cardata_line(utc_value: datetime, speed: int) -> bytes:
    payload = {
        "Entries": [
            {
                "Utc": utc_value.isoformat().replace("+00:00", "Z"),
                "Cars": {
                    "4": {
                        "Channels": {
                            "0": 11000,
                            "2": speed,
                            "3": 7,
                            "4": 100,
                            "5": 0,
                            "45": 12,
                        }
                    }
                },
            }
        ]
    }
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(json.dumps(payload).encode()) + compressor.flush()
    return f'"{base64.b64encode(compressed).decode()}"\n'.encode()


class _Content:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = iter(lines)

    async def readline(self) -> bytes:
        return next(self._lines, b"")


class _Response:
    status = 200

    def __init__(self, lines: list[bytes]) -> None:
        self.content = _Content(lines)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _Session:
    def __init__(self, lines: list[bytes]) -> None:
        self.lines = lines
        self.requests = 0

    def get(self, _url: str) -> _Response:
        self.requests += 1
        return _Response(list(self.lines))


@pytest.mark.asyncio
async def test_replay_telemetry_reads_only_selected_lap_and_uses_bounded_cache(
    hass, tmp_path
) -> None:
    start = datetime(2026, 8, 23, 13, 0, tzinfo=UTC)
    frames = tmp_path / "frames.jsonl"
    frames.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "t": 0,
                        "s": "SessionStatus",
                        "p": {"Status": "Started", "Utc": start.isoformat()},
                    }
                ),
                json.dumps(
                    {
                        "t": 1000,
                        "s": "TimingData",
                        "p": _timing_lap("4", 1, 90.0, 1, "0"),
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    index = SimpleNamespace(
        session_id="2026_2_10", frames_file=frames, session_started_at_ms=0
    )
    manager = SimpleNamespace(
        selected_session=SimpleNamespace(path="2026/Test/Race", start_utc=start),
        get_loaded_index=lambda: index,
    )
    session = _Session(
        [
            _cardata_line(start + timedelta(milliseconds=200), 300),
            _cardata_line(start + timedelta(milliseconds=800), 320),
        ]
    )
    service = ReplayTelemetryService(hass, session, manager)

    first = await service.async_compare([{"driver_number": 4, "lap_number": 1}])
    second = await service.async_compare([{"driver_number": 4, "lap_number": 1}])

    assert first == second
    assert session.requests == 1
    assert first["series"][0]["sample_count"] == 2
    assert first["series"][0]["summary"]["top_speed"] == 320.0
    assert all(
        "distance" in sample and "delta_s" in sample
        for sample in first["series"][0]["samples"]
    )
    assert first["coverage"]["raw_home_assistant_states"] == "not_exposed"
    assert first["limits"]["max_points_per_lap"] == 500
    assert service.diagnostics()["cache_entries"] == 1
