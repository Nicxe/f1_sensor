"""Contract and pre-implementation regression tests for minisectors."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from custom_components.f1_sensor.__init__ import LiveDriversCoordinator
from custom_components.f1_sensor.models.history import normalize_lap_record

FIXTURES = Path(__file__).parent / "fixtures" / "minisectors"
CASES = json.loads((FIXTURES / "cases.json").read_text())
CONTRACT = json.loads((FIXTURES / "contract.json").read_text())
LAP_TRANSITION = json.loads((FIXTURES / "lap_transition.json").read_text())


def _indexed_items(value: object):
    if isinstance(value, list):
        return enumerate(value)
    if isinstance(value, dict):
        return ((int(key), item) for key, item in value.items() if str(key).isdigit())
    return ()


def _apply_timing_payload(
    state: dict[str, dict[str, dict[str, int]]],
    payload: dict[str, Any],
    operation: str,
) -> dict[str, dict[str, dict[str, int]]]:
    result = {} if operation == "replace" else deepcopy(state)
    for driver, driver_delta in payload.get("Lines", {}).items():
        if operation == "replace_driver":
            result.pop(driver, None)
        driver_state = result.setdefault(driver, {})
        for sector_index, sector_delta in _indexed_items(
            driver_delta.get("Sectors", {})
        ):
            if not isinstance(sector_delta, dict) or "Segments" not in sector_delta:
                continue
            segments = sector_delta["Segments"]
            sector_key = str(sector_index)
            if isinstance(segments, list):
                driver_state[sector_key] = {}
            sector_state = driver_state.setdefault(sector_key, {})
            for segment_index, segment_delta in _indexed_items(segments):
                if isinstance(segment_delta, dict) and "Status" in segment_delta:
                    sector_state[str(segment_index)] = segment_delta["Status"]
    return result


def _protocol_result(events: list[dict[str, Any]]) -> dict[str, Any]:
    result = {
        "generation": None,
        "sequence": None,
        "resync_required": False,
        "drivers": {},
    }
    for event in events:
        if event["type"] == "snapshot":
            result = {
                "generation": event["generation"],
                "sequence": event["sequence"],
                "resync_required": False,
                "drivers": deepcopy(event["drivers"]),
            }
            continue
        if event["generation"] != result["generation"]:
            continue
        if result["resync_required"]:
            continue
        if event["sequence"] != result["sequence"] + 1:
            result["resync_required"] = True
            continue
        if event["type"] == "delta":
            result["drivers"] = _apply_timing_payload(
                result["drivers"],
                {
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
                        for driver, sectors in event["drivers"].items()
                    }
                },
                "merge",
            )
        elif event["type"] == "reset":
            for driver in event["scope"]["drivers"]:
                result["drivers"].pop(driver, None)
                if driver in event["drivers"]:
                    result["drivers"][driver] = deepcopy(event["drivers"][driver])
        result["sequence"] = event["sequence"]
    return result


def _semantic_for(raw_status: object) -> dict[str, Any]:
    fallback = next(
        item for item in CONTRACT["status_semantics"] if item["raw"] == "other"
    )
    return next(
        (
            item
            for item in CONTRACT["status_semantics"]
            if item["raw"] != "other" and item["raw"] == raw_status
        ),
        fallback,
    )


def test_archive_cases_preserve_raw_indexes_and_expected_statuses() -> None:
    for case in CASES["cases"]:
        state = _apply_timing_payload(
            case["before"], case["payload"], case["operation"]
        )
        for expected in case["expected_points"]:
            raw = state[expected["driver"]][str(expected["sector"])][
                str(expected["segment"])
            ]
            assert raw == expected["raw"], case["id"]
            if "semantic" in expected:
                semantic = _semantic_for(raw)
                assert semantic["semantic"] == expected["semantic"], case["id"]
                assert semantic["color"] == expected["color"], case["id"]
        for driver, lengths in case.get("expected_lengths", {}).items():
            assert [len(state[driver][str(index)]) for index in range(3)] == lengths


def test_purple_handoff_is_one_atomic_source_frame() -> None:
    case = next(
        item for item in CASES["cases"] if item["id"] == "purple_handoff_atomic"
    )
    assert case["atomic"] is True
    assert set(case["payload"]["Lines"]) == {"31", "87"}
    state = _apply_timing_payload(case["before"], case["payload"], case["operation"])
    purple = [
        driver
        for driver, sectors in state.items()
        if sectors.get("0", {}).get("3") == 2051
    ]
    assert purple == ["87"]


def test_archive_lap_counter_precedes_atomic_segment_reset() -> None:
    counter = LAP_TRANSITION["lap_counter_frame"]
    reset = LAP_TRANSITION["segment_reset_frame"]
    driver = LAP_TRANSITION["source"]["driver"]

    assert counter["payload"] == {"Lines": {driver: {"NumberOfLaps": 1}}}
    segment_values = [
        segment["Status"]
        for sector in reset["payload"]["Lines"][driver]["Sectors"].values()
        for segment in sector["Segments"].values()
    ]
    assert len(segment_values) == 22
    assert segment_values.count(0) == 21
    assert reset["payload"]["Lines"][driver]["Sectors"]["0"]["Segments"]["0"] == {
        "Status": 2051
    }
    assert LAP_TRANSITION["observed_delay_seconds"] == 4.177


def test_unknown_statuses_retain_raw_code_and_use_neutral_fallback() -> None:
    for raw_status in (2050, 2052, 2064, 2068, 9999, "future"):
        semantic = _semantic_for(raw_status)
        if raw_status == 2064:
            assert semantic["semantic"] == "special"
        else:
            assert semantic["semantic"] == "unknown"
        assert semantic["color"] == "neutral"
        assert semantic["known"] is False


def test_protocol_generation_sequence_seek_and_resync_examples() -> None:
    for scenario in CASES["protocol_scenarios"]:
        assert _protocol_result(scenario["events"]) == scenario["expected"], scenario[
            "id"
        ]


def test_protocol_contract_has_bounded_snapshot_delta_reset_and_resync() -> None:
    protocol = CONTRACT["protocol"]
    limits = CONTRACT["limits"]
    assert protocol["version"] == 1
    assert protocol["initial_event"] == "snapshot"
    assert set(protocol["event_types"]) == {
        "snapshot",
        "delta",
        "reset",
        "unavailable",
    }
    assert protocol["event_requirements"] == {
        "snapshot": ["generation", "sequence", "drivers"],
        "delta": ["generation", "sequence", "drivers"],
        "reset": ["generation", "sequence", "reason", "scope"],
        "unavailable": ["generation", "sequence", "reason"],
    }
    assert protocol["sequence"]["snapshot"] == 0
    assert protocol["sequence"]["gap_action"] == "unsubscribe_and_resubscribe"
    assert "replay_seek_backwards" in protocol["generation_changes"]
    assert protocol["atomic_source_frame"] is True
    assert protocol["lap_boundary"] == {
        "trigger": "segment_status_reset_frame",
        "number_of_laps_role": "metadata_only",
        "retain_completed_strip_until_reset_frame": True,
        "preserve_new_lap_statuses_from_reset_frame": True,
    }
    assert limits == {
        "drivers": 32,
        "sectors_per_driver": 3,
        "segments_per_sector": 32,
        "maximum_event_bytes": 32768,
        "maximum_ui_deltas_per_second": 4,
        "maximum_rolling_bytes_per_client_per_second": 16384,
        "rolling_window_seconds": 10,
    }


def test_future_field_catalog_metadata_is_complete_and_modular() -> None:
    required = {
        "id",
        "label",
        "type",
        "unit",
        "source",
        "path",
        "capability",
        "modes",
        "sessions",
        "identity",
        "generation",
        "timestamps",
        "freshness",
        "spoiler",
        "sortable",
        "filterable",
        "mobile",
        "presentations",
        "estimated",
        "comparison",
    }
    fields = {field["id"]: field for field in CONTRACT["fields"]}
    assert set(fields) == {
        "minisector_1",
        "minisector_2",
        "minisector_3",
        "sector_1_with_minisectors",
        "sector_2_with_minisectors",
        "sector_3_with_minisectors",
    }
    assert all(required <= field.keys() for field in fields.values())
    assert all(field["spoiler"] is True for field in fields.values())
    assert all(field["modes"] == ["live", "replay"] for field in fields.values())
    assert all(field["source"] == "minisectors" for field in fields.values())
    assert all("segment" in field["identity"] for field in fields.values())


def test_availability_contract_has_no_archive_or_live_fallback_leaks() -> None:
    availability = {
        item["context"]: item["result"] for item in CONTRACT["availability"]
    }
    assert availability["locked_archive_session"] == (
        "unavailable_without_live_fallback"
    )
    assert availability["spoiler_protected"] == (
        "blocked_without_retained_segment_data"
    )
    assert availability["live_delay_changed"] == ("new_generation_from_delayed_stream")
    assert availability["all_consumers_hidden_or_removed"] == (
        "unsubscribe_and_release_resource"
    )


async def test_live_minisector_store_exposes_initial_snapshot(hass) -> None:
    case = next(item for item in CASES["cases"] if item["id"] == "initial_list_payload")
    coordinator = LiveDriversCoordinator(
        hass,
        SimpleNamespace(),
        delay_seconds=0,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
    )
    coordinator._merge_timingdata(case["payload"])

    assert "minisectors" not in coordinator._state
    assert (
        coordinator.minisector_snapshot()["drivers"]["12"]["sectors"]["2"]["segments"][
            "8"
        ]["raw_status"]
        == 0
    )


def test_history_normalizer_preserves_sparse_minisector_indexes() -> None:
    record = normalize_lap_record(
        {
            "RacingNumber": "5",
            "NumberOfLaps": 1,
            "Sectors": {"2": {"Segments": {"6": {"Status": 2048}}}},
        },
        provider="replay",
        session_type="Race",
    )

    assert [item.as_dict() for item in record.minisectors] == [
        {"sector": 3, "index": 6, "status": 2048}
    ]


def test_runtime_catalog_exposes_contracted_minisector_fields() -> None:
    catalog = (
        Path(__file__).parents[1]
        / "www"
        / "f1-sensor-live-data-card"
        / "modular"
        / "catalog.js"
    ).read_text()

    assert all(field["id"] in catalog for field in CONTRACT["fields"])
