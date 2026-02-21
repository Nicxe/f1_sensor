from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import pytest
from yarl import URL

from custom_components.f1_sensor.__init__ import (
    F1DataCoordinator,
    F1SeasonResultsCoordinator,
)
from custom_components.f1_sensor.const import API_URL, SEASON_RESULTS_URL


@pytest.mark.asyncio
async def test_f1_data_coordinator_update(hass) -> None:
    session = MagicMock()

    def _fake_init(self, hass, logger, name, update_interval=None, **kwargs) -> None:
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval

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
    def _fake_init(self, hass, logger, name, update_interval=None, **kwargs) -> None:
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval

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
