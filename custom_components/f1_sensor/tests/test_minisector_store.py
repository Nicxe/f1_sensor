"""Tests for the bounded live and replay minisector state store."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from custom_components.f1_sensor import LiveDriversCoordinator
from custom_components.f1_sensor.minisectors import (
    MiniSectorStateStore,
    _bounded_index,
    _driver_key,
    _raw_status,
    _stream_int,
)

FIXTURES = Path(__file__).parent / "fixtures" / "minisectors"
CASES = json.loads((FIXTURES / "cases.json").read_text())
LAP_TRANSITION = json.loads((FIXTURES / "lap_transition.json").read_text())


def _case(case_id: str) -> dict:
    return next(item for item in CASES["cases"] if item["id"] == case_id)


def _payload_from_state(state: dict) -> dict:
    return {
        "Lines": {
            driver: {
                "Sectors": {
                    sector: {
                        "Segments": {
                            segment: {"Status": status}
                            for segment, status in segments.items()
                        }
                    }
                    for sector, segments in sectors.items()
                }
            }
            for driver, sectors in state.items()
        }
    }


def _raw(snapshot: dict, driver: str, sector: int, segment: int):
    return snapshot["drivers"][driver]["sectors"][str(sector)]["segments"][
        str(segment)
    ]["raw_status"]


def test_store_applies_archive_lists_sparse_deltas_and_atomic_handoff() -> None:
    store = MiniSectorStateStore(entry_id="entry")

    initial = _case("initial_list_payload")
    assert store.merge_timing_data(initial["payload"]) is True
    snapshot = store.snapshot()
    assert _raw(snapshot, "12", 2, 8) == 0
    assert [
        len(snapshot["drivers"]["12"]["sectors"][str(index)]["segments"])
        for index in range(3)
    ] == [5, 6, 9]

    sparse = _case("sparse_object_delta")
    assert store.merge_timing_data(sparse["payload"]) is True
    assert _raw(store.snapshot(), "5", 0, 1) == 2064

    handoff = _case("purple_handoff_atomic")
    store.reset("test_seed")
    store.merge_timing_data(_payload_from_state(handoff["before"]))
    generation = store.snapshot()["generation"]
    assert store.merge_timing_data(handoff["payload"]) is True
    snapshot = store.snapshot()
    assert snapshot["generation"] == generation
    assert _raw(snapshot, "31", 0, 3) == 2049
    assert _raw(snapshot, "87", 0, 3) == 2051


def test_store_matches_reduced_archive_cases() -> None:
    for case in CASES["cases"]:
        store = MiniSectorStateStore()
        store.merge_timing_data(_payload_from_state(case["before"]))
        if case["operation"] == "replace":
            store.reset("source_restart")
        elif case["operation"] == "replace_driver":
            for driver in case["payload"].get("Lines", {}):
                store.reset_driver(driver, "new_lap")
        store.merge_timing_data(case["payload"])
        snapshot = store.snapshot()
        for expected in case["expected_points"]:
            assert (
                _raw(
                    snapshot,
                    expected["driver"],
                    expected["sector"],
                    expected["segment"],
                )
                == expected["raw"]
            ), case["id"]


def test_store_enforces_driver_sector_and_segment_bounds() -> None:
    store = MiniSectorStateStore()
    lines = {
        str(driver): {
            "Sectors": {
                "0": {"Segments": {"0": {"Status": 2048}}},
                "3": {"Segments": {"0": {"Status": 2051}}},
            }
        }
        for driver in range(1, 34)
    }
    lines["1"]["Sectors"]["0"]["Segments"]["32"] = {"Status": 2051}

    store.merge_timing_data({"Lines": lines})
    snapshot = store.snapshot()
    assert len(snapshot["drivers"]) == 32
    assert "3" not in snapshot["drivers"]["1"]["sectors"]
    assert "32" not in snapshot["drivers"]["1"]["sectors"]["0"]["segments"]


def test_store_keeps_completed_strip_until_source_reset_frame() -> None:
    store = MiniSectorStateStore()
    store.merge_timing_data(
        {
            "SessionPart": 1,
            "Lines": {"10": LAP_TRANSITION["before"]},
        }
    )
    first_generation = store.snapshot()["generation"]

    store.merge_timing_data(LAP_TRANSITION["lap_counter_frame"]["payload"])
    between_frames = store.snapshot()
    assert _raw(between_frames, "10", 0, 2) == 2051
    assert _raw(between_frames, "10", 2, 8) == 2051
    assert between_frames["drivers"]["10"]["current_lap"] == 2
    assert between_frames["generation"] == first_generation

    store.merge_timing_data(LAP_TRANSITION["segment_reset_frame"]["payload"])
    snapshot = store.snapshot()
    assert _raw(snapshot, "10", 0, 0) == 2051
    assert _raw(snapshot, "10", 0, 2) == 0
    assert _raw(snapshot, "10", 2, 8) == 0
    assert snapshot["generation"] == first_generation

    assert store.merge_timing_data({"SessionPart": 2, "Lines": {}}) is True
    snapshot = store.snapshot()
    assert snapshot["drivers"] == {}
    assert snapshot["session_part"] == 2
    assert snapshot["generation"] != first_generation


def test_store_starts_new_generation_on_replay_lap_rewind() -> None:
    store = MiniSectorStateStore()
    store.merge_timing_data(
        {
            "Lines": {
                "44": {
                    "NumberOfLaps": 20,
                    "Sectors": {"2": {"Segments": {"6": {"Status": 2051}}}},
                }
            }
        }
    )
    generation = store.snapshot()["generation"]

    store.merge_timing_data(
        {
            "Lines": {
                "44": {
                    "NumberOfLaps": 5,
                    "Sectors": {"0": {"Segments": {"0": {"Status": 2048}}}},
                }
            }
        }
    )

    snapshot = store.snapshot()
    assert snapshot["generation"] != generation
    assert snapshot["last_reset_reason"] == "replay_seek"
    assert "2" not in snapshot["drivers"]["44"]["sectors"]
    assert _raw(snapshot, "44", 0, 0) == 2048


def test_store_rejects_invalid_source_values_and_releases_listeners() -> None:
    """Malformed stream values never create state or keep a closed store active."""
    assert _bounded_index(True, 3) is None
    assert _bounded_index("3", 3) is None
    assert _bounded_index("01", 3) is None
    assert _bounded_index("1", 3) == 1
    assert _driver_key(False) is None
    assert _driver_key("000") is None
    assert _driver_key("044") == "44"
    assert _stream_int(True) is None
    assert _stream_int("1000000") is None
    assert _raw_status(" x " * 20) == (" x " * 20).strip()[:32]
    assert _raw_status({"Status": 2048}) is not None

    store = MiniSectorStateStore(entry_id="entry")
    listener = Mock()
    store.add_listener(listener)
    assert store.merge_timing_data({"SessionPart": 1}) is False
    assert store.merge_timing_data({"SessionPart": 2}) is True
    listener.assert_called_once()
    assert store.reset_driver("invalid") is False
    assert store.reset_driver("44") is False

    store.close()
    assert store.closed is True
    assert store.listener_count == 0
    assert store.merge_timing_data({"Lines": {"44": {}}}) is False
    assert store.add_listener(Mock())() is None


def test_store_clears_replaced_lists_and_recovers_from_listener_failures() -> None:
    """A complete list replaces stale values and bad callbacks cannot stop updates."""
    store = MiniSectorStateStore(entry_id="first")
    notified = Mock()
    store.add_listener(notified)
    store.add_listener(Mock(side_effect=RuntimeError("test listener failure")))
    store.merge_timing_data(
        {
            "Lines": {
                "44": {
                    "Sectors": {
                        "0": {
                            "Segments": [
                                {"Status": 2048},
                                {"Status": 2049},
                            ]
                        }
                    }
                }
            }
        }
    )
    store.merge_timing_data(
        {
            "Lines": {
                "44": {
                    "Sectors": {
                        "0": {
                            "Segments": [
                                {"Status": 2051},
                                {},
                                {"Status": {"invalid": True}},
                            ]
                        },
                        "1": {},
                    }
                }
            }
        }
    )
    snapshot = store.snapshot()
    assert _raw(snapshot, "44", 0, 0) == 2051
    assert "1" not in snapshot["drivers"]["44"]["sectors"]["0"]["segments"]
    assert notified.call_count == 2

    assert store.set_source("live") is False
    assert store.set_source("replay") is True
    assert store.reset("session_change", session_id="next", source="live") is True
    assert store.snapshot()["session_id"] == "next"
    assert store.merge_timing_data({"SessionPart": True, "Lines": {}}) is False
    assert store.merge_timing_data({"SessionPart": True, "Lines": {}}) is False

    closed = Mock()
    store.add_close_listener(closed)
    store.close()
    store.close()
    closed.assert_called_once()


async def test_coordinator_keeps_minisectors_out_of_driver_positions_updates(
    hass,
) -> None:
    coordinator = LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    deliver = Mock()
    coordinator._schedule_deliver = deliver

    coordinator._on_timingdata(_case("initial_list_payload")["payload"])

    deliver.assert_not_called()
    assert "minisectors" not in coordinator._state
    assert all(
        "minisectors" not in driver for driver in coordinator._state["drivers"].values()
    )
    assert _raw(coordinator.minisector_snapshot(), "12", 2, 8) == 0


async def test_coordinator_resets_minisectors_for_lifecycle_boundaries(hass) -> None:
    coordinator = LiveDriversCoordinator(
        hass, SimpleNamespace(data={}), delay_seconds=0
    )
    payload = _case("initial_list_payload")["payload"]
    coordinator._merge_timingdata(payload)
    initial_generation = coordinator.minisector_snapshot()["generation"]

    coordinator._on_trackstatus({"Status": "4"})
    snapshot = coordinator.minisector_snapshot()
    assert snapshot["drivers"] == {}
    assert snapshot["generation"] == initial_generation
    assert snapshot["last_reset_reason"] == "track_status_disruption"

    coordinator._merge_timingdata(payload)
    coordinator.set_delay(10)
    await hass.async_block_till_done()
    delayed = coordinator.minisector_snapshot()
    assert delayed["drivers"] == {}
    assert delayed["generation"] != initial_generation
    assert delayed["last_reset_reason"] == "live_delay_change"

    coordinator._merge_timingdata(payload)
    coordinator._handle_live_state(False, "no-spoiler")
    protected = coordinator.minisector_snapshot()
    assert protected["drivers"] == {}
    assert protected["last_reset_reason"] == "spoiler_protected"

    coordinator._merge_timingdata(payload)
    coordinator._handle_live_state(False, "outside-window")
    unavailable = coordinator.minisector_snapshot()
    assert unavailable["drivers"] == {}
    assert unavailable["last_reset_reason"] == "source_unavailable"

    coordinator._handle_live_state(True, "live")
    assert coordinator.minisector_snapshot()["drivers"] == {}

    coordinator._merge_timingdata(payload)
    coordinator._merge_sessionstatus({"Status": "Finalised"})
    coordinator._merge_sessionstatus({"Status": "Started"})
    new_session = coordinator.minisector_snapshot()
    assert new_session["drivers"] == {}
    assert new_session["last_reset_reason"] == "session_change"

    coordinator._merge_timingdata(payload)
    coordinator.reset_for_replay()
    replay_reset = coordinator.minisector_snapshot()
    assert replay_reset["drivers"] == {}
    assert replay_reset["last_reset_reason"] == "replay_reset"

    await coordinator.async_close()
    assert coordinator.minisector_snapshot()["last_reset_reason"] == "unload"


async def test_coordinator_resets_minisectors_when_session_fingerprint_changes(
    hass,
) -> None:
    session = SimpleNamespace(data={"Sessions": [{"Key": 1}]})
    coordinator = LiveDriversCoordinator(hass, session)
    coordinator._on_session_index_update()
    coordinator._merge_timingdata(_case("initial_list_payload")["payload"])

    session.data = {"Sessions": [{"Key": 2}]}
    coordinator._on_session_index_update()

    snapshot = coordinator.minisector_snapshot()
    assert snapshot["drivers"] == {}
    assert snapshot["last_reset_reason"] == "session_change"
