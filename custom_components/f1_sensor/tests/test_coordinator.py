from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import pytest
from yarl import URL

from custom_components.f1_sensor.__init__ import (
    F1DataCoordinator,
    F1SeasonResultsCoordinator,
    FiaDocumentsCoordinator,
    LiveSessionCoordinator,
)
from custom_components.f1_sensor.const import (
    API_URL,
    FIA_SEASON_FALLBACK_URL,
    SEASON_RESULTS_URL,
)


class _TimeoutSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url: str):
        self.calls.append(url)
        raise TimeoutError


def _fake_init(self, hass, logger, name, update_interval=None, **kwargs) -> None:
    del kwargs
    self.hass = hass
    self.logger = logger
    self.name = name
    self.update_interval = update_interval


def _future_race_payload() -> dict:
    race_date = (datetime.now(tz=UTC) + timedelta(days=10)).date().isoformat()
    return {
        "MRData": {
            "RaceTable": {
                "Races": [
                    {
                        "season": "2026",
                        "round": "1",
                        "raceName": "Australian Grand Prix",
                        "date": race_date,
                        "time": "05:00:00Z",
                        "Circuit": {
                            "circuitId": "albert_park",
                            "circuitName": "Albert Park",
                            "Location": {
                                "locality": "Melbourne",
                                "country": "Australia",
                            },
                        },
                    }
                ]
            }
        }
    }


@pytest.mark.asyncio
async def test_f1_data_coordinator_update(hass) -> None:
    session = MagicMock()

    with patch.object(DataUpdateCoordinator, "__init__", _fake_init):
        coordinator = F1DataCoordinator(
            hass,
            API_URL,
            "Test Coordinator",
            session=session,
            user_agent="ua",
            cache={},
            inflight={},
            ttl_seconds=5,
            persist_map={},
            persist_save=MagicMock(),
        )
    payload = {"MRData": {"RaceTable": {"season": "2025", "Races": []}}}

    mock_fetch = AsyncMock(return_value=payload)
    with pytest.MonkeyPatch().context() as monkeypatch:
        monkeypatch.setattr(
            "custom_components.f1_sensor.__init__.fetch_json",
            mock_fetch,
        )
        result = await coordinator._async_update_data()

    assert result == payload
    assert mock_fetch.await_count == 1
    assert mock_fetch.await_args.kwargs["ttl_seconds"] == 5


@pytest.mark.asyncio
async def test_f1_data_coordinator_update_failure(hass) -> None:
    with patch.object(DataUpdateCoordinator, "__init__", _fake_init):
        coordinator = F1DataCoordinator(
            hass,
            API_URL,
            "Test Coordinator",
            session=MagicMock(),
            user_agent="ua",
            cache={},
            inflight={},
            ttl_seconds=5,
            persist_map={},
            persist_save=MagicMock(),
        )

    mock_fetch = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.MonkeyPatch().context() as monkeypatch:
        monkeypatch.setattr(
            "custom_components.f1_sensor.__init__.fetch_json",
            mock_fetch,
        )
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_f1_data_coordinator_timeout_maps_to_update_failed(hass) -> None:
    with patch.object(DataUpdateCoordinator, "__init__", _fake_init):
        coordinator = F1DataCoordinator(
            hass,
            API_URL,
            "Test Coordinator",
            session=MagicMock(),
            user_agent="ua",
            cache={},
            inflight={},
            ttl_seconds=5,
            persist_map={},
            persist_save=MagicMock(),
        )

    mock_fetch = AsyncMock(side_effect=TimeoutError)
    with pytest.MonkeyPatch().context() as monkeypatch:
        monkeypatch.setattr(
            "custom_components.f1_sensor.__init__.fetch_json",
            mock_fetch,
        )
        with pytest.raises(UpdateFailed, match="Error fetching data"):
            await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_season_results_coordinator_paginates_all_pages(hass) -> None:
    coordinator = F1SeasonResultsCoordinator(
        hass,
        SEASON_RESULTS_URL,
        "Test Season Results Coordinator",
        session=MagicMock(),
        user_agent="ua",
        cache={},
        inflight={},
        ttl_seconds=5,
        persist_map={},
        persist_save=MagicMock(),
        season_source=None,
    )

    def _race(round_num: int) -> dict:
        return {
            "season": "2025",
            "round": str(round_num),
            "Results": [{"position": "1"}],
        }

    async def _fake_fetch_json(_hass, _session, url, **_kwargs):
        query = URL(url).query
        offset = int(query.get("offset") or "0")
        response_limit = 2
        response_total = 4
        if offset == 0:
            races = [_race(1), _race(2)]
        elif offset == 2:
            races = [_race(3), _race(4)]
        else:
            races = []
        return {
            "MRData": {
                "total": str(response_total),
                "limit": str(response_limit),
                "offset": str(offset),
                "RaceTable": {"Races": races},
            }
        }

    mock_fetch = AsyncMock(side_effect=_fake_fetch_json)
    with pytest.MonkeyPatch().context() as monkeypatch:
        monkeypatch.setattr(
            "custom_components.f1_sensor.__init__.fetch_json",
            mock_fetch,
        )
        data = await coordinator._async_update_data()

    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    assert len(races) == 4
    assert mock_fetch.await_count == 2


@pytest.mark.asyncio
async def test_fia_documents_timeout_uses_fallback_season_url(hass) -> None:
    race_coordinator = MagicMock()
    race_coordinator.data = _future_race_payload()
    coordinator = FiaDocumentsCoordinator(
        hass,
        race_coordinator,
        session=MagicMock(),
        cache={},
        inflight={},
        persist_map={},
        persist_save=MagicMock(),
    )

    mock_fetch = AsyncMock(side_effect=TimeoutError)
    with pytest.MonkeyPatch().context() as monkeypatch:
        monkeypatch.setattr(
            "custom_components.f1_sensor.__init__.fetch_text",
            mock_fetch,
        )
        url = await coordinator._get_season_url("2026")

    assert url == FIA_SEASON_FALLBACK_URL


@pytest.mark.asyncio
async def test_fia_documents_fetch_timeout_maps_to_update_failed(hass) -> None:
    race_coordinator = MagicMock()
    race_coordinator.data = _future_race_payload()
    coordinator = FiaDocumentsCoordinator(
        hass,
        race_coordinator,
        session=MagicMock(),
        cache={},
        inflight={},
        persist_map={},
        persist_save=MagicMock(),
    )

    mock_fetch = AsyncMock(side_effect=TimeoutError)
    with pytest.MonkeyPatch().context() as monkeypatch:
        monkeypatch.setattr(
            coordinator,
            "_get_season_url",
            AsyncMock(return_value="https://fia.example/2026"),
        )
        monkeypatch.setattr(
            "custom_components.f1_sensor.__init__.fetch_text",
            mock_fetch,
        )
        with pytest.raises(UpdateFailed, match="Error fetching FIA documents"):
            await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_live_session_coordinator_fetch_index_timeout_returns_none(hass) -> None:
    timeout_session = _TimeoutSession()
    coordinator = LiveSessionCoordinator(hass, 2026, session=timeout_session)

    payload = await coordinator._fetch_index()

    assert payload is None
    assert timeout_session.calls
    assert coordinator.last_http_status is None
