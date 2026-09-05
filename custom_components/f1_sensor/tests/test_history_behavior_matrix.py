"""Behavior matrix for provider-neutral history and lap analysis guards."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.f1_sensor import history
from custom_components.f1_sensor.history import HistoryService, LapAnalysisStore
from custom_components.f1_sensor.providers import ProviderRegistry


class _Bus:
    def __init__(self) -> None:
        self.callbacks = {}
        self.removed = []

    def subscribe(self, stream, callback):
        self.callbacks[stream] = callback

        def _remove() -> None:
            self.removed.append(stream)

        return _remove


def _timing_lap(driver="4", lap=1, time="1:30.000"):
    return {
        "Lines": {
            driver: {
                "NumberOfLaps": lap,
                "LastLapTime": {"Value": time},
                "Sectors": {
                    "0": {"Value": "30.000"},
                    "1": {"Value": "30.000"},
                    "2": {"Value": "30.000"},
                },
                "Speeds": {"ST": {"Value": "320"}},
            }
        }
    }


def test_history_scalar_normalizers_and_session_kinds() -> None:
    assert history._as_int(True) is None
    assert history._as_int("bad") is None
    assert history._as_float(True) is None
    assert history._as_float(" ") is None
    assert history._as_float("1:02.500") == 62.5
    assert history._as_float("bad") is None
    assert history._text(None) is None
    assert history._text(" ") is None
    assert history._mapping("bad") == {}
    assert history._sequence("bad") == []
    assert history._sequence([{}, "bad"]) == [{}]
    assert history._parse_utc(None) is None
    assert history._parse_utc("bad") is None
    assert history._parse_utc("2026-09-01T12:00:00") == datetime(
        2026, 9, 1, 12, tzinfo=UTC
    )
    assert history._session_kind("Sprint Shootout", None) == "sprint_qualifying"
    assert history._session_kind("Practice 1", None) == "practice"
    assert history._session_kind("Sprint", None) == "sprint"
    assert history._session_kind("Qualifying", None) == "qualifying"
    assert history._session_kind("Race", None) == "race"
    assert history._session_kind("Test", None) == "other"
    assert history._combine_date_time(None, None) is None
    assert history._combine_date_time("2026-09-01", None) == ("2026-09-01T00:00:00Z")


@pytest.mark.asyncio
async def test_history_service_invalid_fetch_diagnostics_and_unsupported_sessions(
    hass, monkeypatch
) -> None:
    service = HistoryService(
        hass,
        Mock(),
        cache={},
        inflight={},
        persisted={},
        persist_save=Mock(),
        registry=ProviderRegistry(),
    )
    monkeypatch.setattr(history, "fetch_json", AsyncMock(return_value=[]))
    with pytest.raises(ValueError, match="must be an object"):
        await service._async_fetch_json(
            "url",
            year=2026,
            params={},
            force_refresh=False,
            validator=lambda _payload: None,
        )
    assert (
        await service.async_get_session_results(
            year=2026,
            session_key=1,
            round_number=1,
            session_type="Practice",
        )
    )["coverage"]["results"] == "not_available"
    assert (
        await service.async_get_laps(
            year=2026,
            round_number=1,
            session_type="Sprint",
        )
    )["coverage"]["lap_times"] == "not_available_for_session"
    assert service.diagnostics() == {
        "provider": "jolpica",
        "catalog_requests": 0,
        "result_requests": 1,
        "lap_requests": 1,
    }


def test_lap_store_ignores_invalid_stream_shapes_and_tracks_disruption() -> None:
    store = LapAnalysisStore(_Bus(), source_provider=lambda: "replay")
    store._on_session_info("bad")
    store._on_track_status("bad")
    store._on_track_status({})
    store._on_timing_data("bad")
    store._on_timing_data({"Lines": "bad"})
    store._on_timing_data({"Lines": {"bad": {}, "4": "bad", "5": {"NumberOfLaps": 0}}})
    assert store.snapshot()["laps"] == []

    store._on_timing_data(_timing_lap(lap=2))
    store._on_track_status({"Status": "7"})
    store._on_track_status({"Status": "1"})
    assert store._previous_status_for_lap(4, 2) is None
    assert store._previous_status_for_lap(4, 3) == "7"
    assert store._previous_status_for_lap(4, 4) is None


def test_lap_store_deleted_and_reinstated_race_control_messages() -> None:
    store = LapAnalysisStore(_Bus(), source_provider=lambda: "f1_live")
    store._on_timing_data(_timing_lap())
    assert store.get_lap(4, 1)["quality"]["deleted"] is None

    store._on_race_control("bad")
    store._on_race_control({"Messages": "bad"})
    store._on_race_control({"Messages": [{}, "bad"]})
    store._on_race_control(
        {
            "Messages": {
                "1": {"Message": "CAR 4 LAP TIME 1:30.000 DELETED - TRACK LIMITS"}
            }
        }
    )
    assert store.get_lap(4, 1)["quality"]["deleted"] is True
    store._on_race_control({"Message": "CAR 4 LAP TIME 1:30.000 REINSTATED"})
    assert store.get_lap(4, 1)["quality"]["deleted"] is False
    store._on_race_control({"Message": "CAR 99 LAP TIME 1:30.000 DELETED"})

    assert store._duration_seconds("bad") is None
    assert store._matching_lap(99, None) is None
    assert store._matching_lap(4, None) is not None
    assert store.diagnostics()["updates"] >= 3


@pytest.mark.asyncio
async def test_lap_store_prunes_and_closes_subscriptions() -> None:
    bus = _Bus()
    store = LapAnalysisStore(bus, source_provider=lambda: "replay", max_laps=20)
    for lap in range(1, 23):
        store._on_timing_data(_timing_lap(lap=lap))
    assert len(store.snapshot()["laps"]) == 20
    assert store.get_lap(4, 1) is None
    store.reset_for_replay()
    assert store.snapshot()["laps"] == []
    await store.async_close()
    assert set(bus.removed) == set(history.LAP_ANALYSIS_STREAMS)
