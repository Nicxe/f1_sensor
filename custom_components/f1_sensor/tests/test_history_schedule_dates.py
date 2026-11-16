"""Published calendar dates do not assert an unpublished session start."""

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.f1_sensor.history import HistoryService
from custom_components.f1_sensor.providers import ProviderRegistry


@pytest.mark.parametrize(
    ("date", "time", "precision", "start"),
    [
        ("2026-09-01", None, "date", None),
        ("2026-09-01", "", "date", None),
        ("2026-09-01", "bad", "date", None),
        ("2026-09-01", "12:00:00", "date", None),
        ("2026-09-01", "00:00:00Z", "datetime", "2026-09-01T00:00:00Z"),
        ("2026-09-01", "14:00:00+02:00", "datetime", "2026-09-01T14:00:00+02:00"),
        ("2026-02-30", "12:00:00Z", "unknown", None),
        (None, "12:00:00Z", "unknown", None),
    ],
)
def test_catalog_preserves_date_precision_without_changing_session_identity(
    hass, date, time, precision, start
) -> None:
    service = HistoryService(
        hass,
        AsyncMock(),
        cache={},
        inflight={},
        persisted={},
        persist_save=Mock(),
        registry=ProviderRegistry(),
    )
    payload = {
        "MRData": {
            "RaceTable": {
                "Races": [
                    {
                        "round": "3",
                        "raceName": "Published event",
                        "date": date,
                        "time": time,
                        "Circuit": {"circuitId": "monza"},
                    }
                ]
            }
        }
    }
    meeting = service._normalize_catalog(2026, payload)["meetings"][0]
    session = meeting["sessions"][0]
    assert meeting["circuit_timezone"] == "Europe/Rome"
    assert session["session_key"] == "jolpica:2026:3:race:Race"
    assert session["date"] == (date if precision != "unknown" else None)
    assert session["start_precision"] == precision
    assert session["start"] == start


def test_catalog_date_only_sessions_sort_with_their_published_day(hass) -> None:
    service = HistoryService(
        hass,
        AsyncMock(),
        cache={},
        inflight={},
        persisted={},
        persist_save=Mock(),
        registry=ProviderRegistry(),
    )
    payload = {
        "MRData": {
            "RaceTable": {
                "Races": [
                    {
                        "round": "3",
                        "date": "2026-09-06",
                        "FirstPractice": {"date": "2026-09-04", "time": "12:00:00Z"},
                        "Qualifying": {"date": "2026-09-05"},
                    }
                ]
            }
        }
    }
    meeting = service._normalize_catalog(2026, payload)["meetings"][0]
    assert meeting["circuit_timezone"] is None
    assert [session["name"] for session in meeting["sessions"]] == [
        "Practice 1",
        "Qualifying",
        "Race",
    ]
