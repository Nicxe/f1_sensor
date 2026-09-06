"""Remaining cache, HTTP, and rollover behavior for core coordinators."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest

from custom_components.f1_sensor import (
    API_URL,
    F1DataCoordinator,
    FiaDocumentsCoordinator,
    LiveSessionCoordinator,
)


class _Response:
    def __init__(self, status: int, payload) -> None:
        self.status = status
        self._text = payload if isinstance(payload, str) else json.dumps(payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def text(self) -> str:
        return self._text


class _Session:
    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.urls = []

    def get(self, url):
        self.urls.append(str(url))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


async def test_live_session_http_cache_bust_and_last_good_matrix(
    hass, monkeypatch
) -> None:
    coordinator = LiveSessionCoordinator(
        hass,
        2026,
        session=_Session(
            _Response(403, "not published"),
            _Response(500, "server error"),
            _Response(200, {}),
            _Response(200, {}),
            _Response(200, {"Meetings": [{"Name": "Dutch GP"}]}),
            RuntimeError("network"),
        ),
    )
    monkeypatch.setattr("custom_components.f1_sensor.time.monotonic", lambda: 5000)
    coordinator._log_throttled(20, "once", "message")
    coordinator._log_throttled(20, "once", "message")

    assert await coordinator._fetch_index() is None
    assert coordinator.last_http_status == 403
    assert await coordinator._fetch_index() is None
    assert coordinator.last_http_status == 500
    assert await coordinator._fetch_index() is None
    assert "?t=" in coordinator._session.urls[-1]
    payload = await coordinator._fetch_index()
    assert payload["Meetings"][0]["Name"] == "Dutch GP"
    coordinator._last_good_index = payload
    assert await coordinator._async_update_data() == payload
    assert await coordinator.async_close() is None

    assert coordinator._has_sessions(None) is False
    assert coordinator._has_sessions({"meetings": {"1": {}}}) is True
    assert coordinator._has_sessions({"Sessions": [{}]}) is True
    assert coordinator._has_sessions({"sessions": {"1": {}}}) is True
    assert coordinator._has_sessions({}) is False


def _race_payload():
    return {
        "season": "2026",
        "round": "16",
        "raceName": "Italian Grand Prix",
        "date": "2026-09-06",
        "time": "13:00:00Z",
        "Circuit": {
            "circuitId": "monza",
            "circuitName": "Monza",
            "url": "https://example.test/monza",
            "Location": {"locality": "Monza", "country": "Italy"},
        },
    }


async def test_fia_documents_resolution_result_and_failure_matrix(
    hass, monkeypatch
) -> None:
    race = _race_payload()
    race_coordinator = SimpleNamespace(
        data={"MRData": {"RaceTable": {"Races": [race]}}}
    )
    coordinator = FiaDocumentsCoordinator(hass, race_coordinator, session=Mock())
    assert coordinator._extract_season_slug("", "2026") is None
    slug_html = '<a href="/documents/season/season-2026-2043">season</a>'
    assert coordinator._extract_season_slug(slug_html, "2026").endswith("2043")
    assert coordinator._summarize_race(None) == {}
    assert coordinator._summarize_race(race)["circuit_id"] == "monza"
    assert coordinator._build_result(None, []) == {
        "event_key": None,
        "race": None,
        "documents": [],
    }

    fetch = AsyncMock(side_effect=["missing", slug_html])
    monkeypatch.setattr("custom_components.f1_sensor.fetch_text", fetch)
    season_url = await coordinator._get_season_url("2026")
    assert season_url.endswith("season-2026-2043")
    assert await coordinator._get_season_url("2026") == season_url

    monkeypatch.setattr(
        "custom_components.f1_sensor.fetch_text", AsyncMock(return_value="<html />")
    )
    with pytest.raises(UpdateFailed, match="unavailable"):
        await FiaDocumentsCoordinator(
            hass, race_coordinator, session=Mock()
        )._get_season_url("2030")

    coordinator._season_url_cache["2026"] = season_url
    monkeypatch.setattr(
        "custom_components.f1_sensor.fetch_text", AsyncMock(return_value="documents")
    )
    monkeypatch.setattr(
        "custom_components.f1_sensor.parse_fia_documents",
        lambda _html: [{"title": "Decision 1"}],
    )
    result = await coordinator._async_update_data()
    assert result["documents"][0]["title"] == "Decision 1"
    assert coordinator.build_empty_result()["race"]["race_name"] == "Italian Grand Prix"
    assert await coordinator.async_close() is None

    empty = FiaDocumentsCoordinator(hass, SimpleNamespace(data={}), session=Mock())
    assert (await empty._async_update_data())["documents"] == []
    empty._season_url_cache["2026"] = season_url
    empty._get_next_race = Mock(return_value=race)
    monkeypatch.setattr(
        "custom_components.f1_sensor.fetch_text",
        AsyncMock(side_effect=RuntimeError("network")),
    )
    with pytest.raises(UpdateFailed, match="fetching FIA"):
        await empty._async_update_data()

    monkeypatch.setattr(
        "custom_components.f1_sensor.fetch_text", AsyncMock(return_value="bad")
    )
    monkeypatch.setattr(
        "custom_components.f1_sensor.parse_fia_documents",
        Mock(side_effect=ValueError("invalid html")),
    )
    with pytest.raises(UpdateFailed, match="parsing FIA"):
        await empty._async_update_data()


async def test_f1_data_validation_provider_rollover_and_failure_matrix(
    hass, monkeypatch
) -> None:
    current_cache = {
        API_URL: {"data": {"MRData": {"RaceTable": {"season": "2025"}}}},
        "https://api.jolpi.ca/ergast/f1/current/results": {},
        "keep": {},
    }
    persisted = dict(current_cache)
    persist_save = Mock()
    coordinator = F1DataCoordinator(
        hass,
        API_URL,
        "Current",
        session=Mock(),
        cache=current_cache,
        persist_map=persisted,
        persist_save=persist_save,
    )
    assert coordinator._last_seen_season == "2025"
    assert coordinator._extract_season(None) is None
    assert (
        coordinator._extract_season(
            {"MRData": {"RaceTable": {"Races": [{"season": "2026"}]}}}
        )
        == "2026"
    )

    refresh = AsyncMock()
    coordinator.config_entry = SimpleNamespace(entry_id="entry")
    hass.data.setdefault("f1_sensor", {})["entry"] = {
        "driver_coordinator": SimpleNamespace(async_request_refresh=refresh),
        "constructor_coordinator": None,
    }
    coordinator._handle_season_rollover_if_needed(
        {"MRData": {"RaceTable": {"season": "2026"}}}
    )
    await hass.async_block_till_done()
    assert coordinator._last_seen_season == "2026"
    assert "keep" in current_cache
    assert not any("/ergast/f1/current" in key for key in current_cache)
    persist_save.assert_called_once()
    refresh.assert_awaited_once()

    validator_calls = []

    async def fake_fetch(*_args, validator=None, **_kwargs):
        validator({})
        validator_calls.append(True)
        return {"MRData": {"RaceTable": {"season": "2026"}}}

    monkeypatch.setattr("custom_components.f1_sensor.fetch_json", fake_fetch)
    monkeypatch.setattr(
        "custom_components.f1_sensor.validate_single_page_jolpica",
        lambda payload, leaf: leaf(payload),
    )
    monkeypatch.setattr(
        "custom_components.f1_sensor.standings_leaf_keys", lambda *_args: []
    )
    monkeypatch.setattr(
        "custom_components.f1_sensor.result_leaf_keys", lambda *_args: []
    )
    monkeypatch.setattr("custom_components.f1_sensor.race_leaf_keys", lambda *_args: [])

    for suffix in (
        "driverstandings.json",
        "constructorstandings.json",
        "results.json",
        "current.json",
    ):
        item = F1DataCoordinator(
            hass,
            f"https://api.jolpi.ca/ergast/f1/{suffix}",
            suffix,
            session=Mock(),
        )
        assert await item._async_update_data()
    assert len(validator_calls) == 4

    provider = SimpleNamespace(
        normalize=Mock(return_value=SimpleNamespace(payload={"normalized": True}))
    )
    normalized = F1DataCoordinator(
        hass,
        "https://api.jolpi.ca/ergast/f1/current.json",
        "Provider",
        session=Mock(),
        provider_registry=provider,
    )
    assert await normalized._async_update_data() == {"normalized": True}
    provider.normalize.assert_called_once()

    monkeypatch.setattr(
        "custom_components.f1_sensor.fetch_json",
        AsyncMock(side_effect=RuntimeError("offline")),
    )
    with pytest.raises(UpdateFailed, match="Error fetching data"):
        await normalized._async_update_data()
    assert await normalized.async_close() is None
