"""Acceptance tests for Phase 3 history and new data models."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from custom_components.f1_sensor.history import HistoryService, LapAnalysisStore
from custom_components.f1_sensor.models.history import (
    LapQuality,
    _as_float,
    _as_int,
    assess_lap_quality,
    normalize_lap_record,
)
from custom_components.f1_sensor.providers import ProviderRegistry

FIXTURES = Path(__file__).parent / "fixtures"


def _service(hass) -> HistoryService:
    return HistoryService(
        hass,
        AsyncMock(),
        cache={},
        inflight={},
        persisted={},
        persist_save=lambda: None,
        registry=ProviderRegistry(),
    )


def test_lap_quality_matches_local_contract_cases() -> None:
    cases = json.loads(
        (FIXTURES / "lap_quality_cases.json").read_text(encoding="utf-8")
    )

    for case in cases:
        quality = assess_lap_quality(**case["input"])
        assert isinstance(quality, LapQuality)
        assert quality.clean is case["expected"]["clean"], case["name"]
        assert quality.confidence == case["expected"]["confidence"], case["name"]
        assert list(quality.reasons) == case["expected"]["reasons"], case["name"]


def test_history_scalar_parsers_reject_malformed_values() -> None:
    assert _as_float("bad:time") is None
    assert _as_float(object()) is None
    assert _as_int("bad") is None


@pytest.mark.asyncio
async def test_history_catalog_uses_jolpica_as_only_historical_source(
    hass, monkeypatch
) -> None:
    payload = {
        "MRData": {
            "total": "1",
            "limit": "100",
            "offset": "0",
            "RaceTable": {
                "season": "2026",
                "Races": [
                    {
                        "season": "2026",
                        "round": "1",
                        "raceName": "Bahrain Grand Prix",
                        "Circuit": {
                            "circuitId": "bahrain",
                            "circuitName": "Bahrain International Circuit",
                            "Location": {"country": "Bahrain", "locality": "Sakhir"},
                        },
                        "date": "2026-03-08",
                        "time": "15:00:00Z",
                        "FirstPractice": {
                            "date": "2026-03-06",
                            "time": "11:30:00Z",
                        },
                        "SprintQualifying": {
                            "date": "2026-03-06",
                            "time": "15:30:00Z",
                        },
                        "Sprint": {"date": "2026-03-07", "time": "11:00:00Z"},
                        "Qualifying": {
                            "date": "2026-03-07",
                            "time": "15:00:00Z",
                        },
                    }
                ],
            },
        }
    }
    fetch = AsyncMock(return_value=payload)
    monkeypatch.setattr("custom_components.f1_sensor.history.fetch_json", fetch)

    catalog = await _service(hass).async_get_catalog(2026)

    assert catalog["coverage"] == {
        "provider": "jolpica",
        "historical_source": "jolpica_only",
        "results": "session_dependent",
        "lap_times": "race_only",
        "speed_traps": "not_available_from_jolpica",
        "minisectors": "not_available_from_jolpica",
        "final": False,
    }
    sessions = catalog["meetings"][0]["sessions"]
    assert [session["kind"] for session in sessions] == [
        "practice",
        "sprint_qualifying",
        "sprint",
        "qualifying",
        "race",
    ]
    assert sessions[-1]["coverage"]["lap_times"] == "available"
    assert sessions[0]["coverage"]["results"] == "not_available_from_jolpica"
    assert fetch.await_args.kwargs["params"] == {"limit": 100, "offset": 0}


@pytest.mark.asyncio
async def test_history_results_explain_unsupported_sessions(hass) -> None:
    result = await _service(hass).async_get_session_results(
        year=2026,
        session_key="jolpica:2026:1:practice:Practice 1",
        round_number=1,
        session_type="Practice 1",
    )

    assert result["results"] == []
    assert result["coverage"]["reason"] == (
        "session_results_not_available_from_jolpica"
    )
    assert result["coverage"]["results"] == "not_available"


@pytest.mark.asyncio
async def test_history_results_normalize_jolpica_classification(
    hass, monkeypatch
) -> None:
    payload = {
        "MRData": {
            "total": "1",
            "limit": "100",
            "offset": "0",
            "RaceTable": {
                "season": "2026",
                "round": "1",
                "Races": [
                    {
                        "season": "2026",
                        "round": "1",
                        "Results": [
                            {
                                "number": "4",
                                "position": "1",
                                "grid": "2",
                                "points": "25",
                                "Driver": {
                                    "driverId": "norris",
                                    "code": "NOR",
                                    "givenName": "Lando",
                                    "familyName": "Norris",
                                },
                                "Constructor": {"name": "McLaren"},
                                "laps": "57",
                                "status": "Finished",
                                "Time": {"time": "1:31:42.123"},
                            }
                        ],
                    }
                ],
            },
        }
    }
    monkeypatch.setattr(
        "custom_components.f1_sensor.history.fetch_json",
        AsyncMock(return_value=payload),
    )

    result = await _service(hass).async_get_session_results(
        year=2026,
        session_key="jolpica:2026:1:race:Race",
        round_number=1,
        session_type="Race",
    )

    assert result["results"][0] == {
        "driver_number": 4,
        "driver_name": "Lando Norris",
        "driver_acronym": "NOR",
        "constructor_name": "McLaren",
        "position": 1,
        "grid": 2,
        "points": 25.0,
        "status": "classified",
        "status_detail": "Finished",
        "laps": 57,
        "duration": "1:31:42.123",
        "gap_to_leader": "1:31:42.123",
        "q1": None,
        "q2": None,
        "q3": None,
    }
    assert result["coverage"]["provider"] == "jolpica"
    assert result["coverage"]["results"] == "available"


@pytest.mark.asyncio
async def test_history_race_laps_are_complete_and_telemetry_limits_are_explicit(
    hass, monkeypatch
) -> None:
    probe = {
        "MRData": {
            "total": "2",
            "limit": "1",
            "offset": "0",
            "RaceTable": {
                "season": "2026",
                "round": "1",
                "Races": [
                    {
                        "season": "2026",
                        "round": "1",
                        "Laps": [
                            {
                                "number": "1",
                                "Timings": [
                                    {
                                        "driverId": "norris",
                                        "position": "1",
                                        "time": "1:36.000",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        }
    }
    full = {
        "MRData": {
            "total": "2",
            "limit": "100",
            "offset": "0",
            "RaceTable": {
                "season": "2026",
                "round": "1",
                "Races": [
                    {
                        "season": "2026",
                        "round": "1",
                        "Laps": [
                            {
                                "number": "1",
                                "Timings": [
                                    {
                                        "driverId": "norris",
                                        "position": "1",
                                        "time": "1:36.000",
                                    },
                                    {
                                        "driverId": "piastri",
                                        "position": "2",
                                        "time": "1:36.500",
                                    },
                                ],
                            }
                        ],
                    }
                ],
            },
        }
    }
    fetch = AsyncMock(side_effect=[probe, full])
    monkeypatch.setattr("custom_components.f1_sensor.history.fetch_json", fetch)

    laps = await _service(hass).async_get_laps(
        year=2026,
        round_number=1,
        session_type="Race",
    )

    assert laps["lap_summary"] == {
        "total": 2,
        "timed": 2,
        "drivers": 2,
        "first_lap": 1,
        "last_lap": 1,
    }
    assert laps["laps"][0] == {
        "provider": "jolpica",
        "driver_id": "norris",
        "lap_number": 1,
        "position": 1,
        "lap_duration": 96.0,
    }
    assert laps["coverage"] == {
        "provider": "jolpica",
        "lap_times": "available",
        "positions": "available",
        "speed_traps": "not_available_from_jolpica",
        "sectors": "not_available_from_jolpica",
        "minisectors": "not_available_from_jolpica",
        "lap_quality": "timing_only",
        "final": True,
    }
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_history_laps_do_not_query_non_race_sessions(hass, monkeypatch) -> None:
    fetch = AsyncMock()
    monkeypatch.setattr("custom_components.f1_sensor.history.fetch_json", fetch)

    laps = await _service(hass).async_get_laps(
        year=2026,
        round_number=1,
        session_type="Qualifying",
    )

    fetch.assert_not_awaited()
    assert laps["laps"] == []
    assert laps["coverage"]["lap_times"] == "not_available_for_session"


def test_speed_traps_and_minisectors_normalize_for_live_and_replay() -> None:
    live = normalize_lap_record(
        {
            "RacingNumber": "4",
            "NumberOfLaps": 12,
            "LastLapTime": {"Value": "1:29.500"},
            "Sectors": {
                "0": {"Value": "29.500", "Segments": {"0": {"Status": 2048}}},
                "1": {"Value": "30.000", "Segments": {"0": {"Status": 2049}}},
                "2": {"Value": "30.000", "Segments": {"0": {"Status": 2051}}},
            },
            "Speeds": {
                "I1": {"Value": "301"},
                "I2": {"Value": "287"},
                "FL": {"Value": "299"},
                "ST": {"Value": "318"},
            },
        },
        provider="f1_live",
        session_type="Qualifying",
    )
    replay = normalize_lap_record(
        live.source_payload,
        provider="replay",
        session_type="Qualifying",
    )

    assert live.speed_traps.as_dict() == {
        "i1": 301.0,
        "i2": 287.0,
        "finish": 299.0,
        "straight": 318.0,
    }
    assert replay.minisectors == live.minisectors
    assert {live.provider, replay.provider} == {"f1_live", "replay"}


def test_live_lap_analysis_resets_between_sessions() -> None:
    callbacks: dict[str, object] = {}

    class Bus:
        def subscribe(self, stream, callback):
            callbacks[stream] = callback
            return lambda: callbacks.pop(stream, None)

    store = LapAnalysisStore(Bus(), source_provider=lambda: "f1_live")
    assert set(callbacks) == {
        "RaceControlMessages",
        "SessionInfo",
        "TimingData",
        "TrackStatus",
    }
    callbacks["SessionInfo"]({"Key": 10, "Name": "Qualifying", "Type": "Qualifying"})
    callbacks["TimingData"](
        {
            "Lines": {
                "4": {
                    "NumberOfLaps": 1,
                    "LastLapTime": {"Value": "1:30.000"},
                    "Sectors": {
                        "0": {
                            "Value": "30.000",
                            "Segments": {"0": {"Status": 2048}},
                        },
                        "1": {"Value": "30.000"},
                        "2": {"Value": "30.000"},
                    },
                    "Speeds": {"ST": {"Value": "320"}},
                }
            }
        }
    )

    first = store.snapshot()
    assert first["session_id"] == "10:Qualifying"
    assert first["lap_quality"]["total"] == 1
    assert first["coverage"] == {
        "speed_traps": "available",
        "minisectors": "available",
    }

    callbacks["SessionInfo"]({"Key": 11, "Name": "Race", "Type": "Race"})

    second = store.snapshot()
    assert second["session_id"] == "11:Race"
    assert second["laps"] == []
    assert second["lap_quality"]["total"] == 0


def test_integration_contains_no_removed_history_provider_references() -> None:
    integration = Path(__file__).resolve().parents[1]
    source = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in integration.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix in {".py", ".js", ".json", ".md"}
    ).lower()

    for removed_name in ("open" + "f1", "fast" + "f1"):
        assert removed_name not in source
