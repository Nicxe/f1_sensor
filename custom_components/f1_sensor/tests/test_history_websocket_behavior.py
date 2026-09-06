"""Behavior coverage for the versioned history WebSocket API."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.f1_sensor import history_websocket as ws
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.jolpica import JolpicaError
from custom_components.f1_sensor.jolpica_pagination import JolpicaPaginationError


class _Connection:
    def __init__(self) -> None:
        self.results = []
        self.errors = []

    def send_result(self, msg_id, result=None):
        self.results.append((msg_id, result))

    def send_error(self, msg_id, code, message):
        self.errors.append((msg_id, code, message))


def _runtime(*, lap_analysis=None):
    service = SimpleNamespace(
        async_get_catalog=AsyncMock(return_value={"catalog": True}),
        async_get_session_results=AsyncMock(return_value={"results": True}),
        async_get_laps=AsyncMock(return_value={"laps": True}),
    )
    return SimpleNamespace(
        history=SimpleNamespace(service=service, lap_analysis=lap_analysis)
    )


def test_history_websocket_registration_is_idempotent(hass, monkeypatch) -> None:
    registered = []
    monkeypatch.setattr(
        ws.websocket_api, "async_register_command", lambda _, fn: registered.append(fn)
    )
    ws.async_register_history_websocket(hass)
    ws.async_register_history_websocket(hass)
    assert registered == [
        ws._ws_get_history_catalog,
        ws._ws_get_history_results,
        ws._ws_get_history_laps,
        ws._ws_get_live_laps,
    ]


async def test_history_commands_return_catalog_results_and_laps(
    hass, monkeypatch
) -> None:
    runtime = _runtime()
    monkeypatch.setattr(
        ws,
        "runtime_from_hass",
        lambda _hass, entry_id: runtime if entry_id == "entry" else None,
    )
    connection = _Connection()

    ws._ws_get_history_catalog(
        hass,
        connection,
        {"id": 1, "entry_id": "entry", "year": 2026, "force_refresh": True},
    )
    ws._ws_get_history_results(
        hass,
        connection,
        {
            "id": 2,
            "entry_id": "entry",
            "year": 2026,
            "session_key": "race",
            "round": 1,
            "session_type": "Race",
            "force_refresh": False,
        },
    )
    ws._ws_get_history_laps(
        hass,
        connection,
        {
            "id": 3,
            "entry_id": "entry",
            "year": 2026,
            "round": 1,
            "session_type": "Race",
            "force_refresh": False,
        },
    )
    await hass.async_block_till_done()
    assert connection.results == [
        (1, {"catalog": True}),
        (2, {"results": True}),
        (3, {"laps": True}),
    ]
    runtime.history.service.async_get_catalog.assert_awaited_once_with(
        2026, force_refresh=True
    )
    runtime.history.service.async_get_session_results.assert_awaited_once()
    runtime.history.service.async_get_laps.assert_awaited_once()


async def test_history_commands_report_not_loaded(hass, monkeypatch) -> None:
    monkeypatch.setattr(ws, "runtime_from_hass", lambda *_: None)
    connection = _Connection()
    common = {"entry_id": "missing", "year": 2026, "force_refresh": False}
    ws._ws_get_history_catalog(hass, connection, {"id": 1, **common})
    ws._ws_get_history_results(
        hass,
        connection,
        {
            "id": 2,
            **common,
            "session_key": 1,
            "round": 1,
            "session_type": "Race",
        },
    )
    ws._ws_get_history_laps(
        hass,
        connection,
        {"id": 3, **common, "round": 1, "session_type": "Race"},
    )
    ws._ws_get_live_laps(hass, connection, {"id": 4, "entry_id": "missing"})
    await hass.async_block_till_done()
    assert [error[1] for error in connection.errors] == ["not_loaded"] * 4


def test_live_laps_returns_empty_or_store_snapshot(hass, monkeypatch) -> None:
    connection = _Connection()
    runtime = _runtime()
    monkeypatch.setattr(ws, "runtime_from_hass", lambda *_: runtime)
    ws._ws_get_live_laps(hass, connection, {"id": 1, "entry_id": "entry"})
    assert connection.results[0][1]["lap_quality"]["total"] == 0
    assert connection.results[0][1]["coverage"]["speed_traps"] == (
        "live_or_replay_not_active"
    )

    runtime.history.lap_analysis = SimpleNamespace(snapshot=lambda: {"laps": [1]})
    ws._ws_get_live_laps(hass, connection, {"id": 2, "entry_id": "entry"})
    assert connection.results[-1] == (2, {"laps": [1]})


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (JolpicaError("down"), "provider_unavailable"),
        (JolpicaPaginationError("bad page"), "provider_unavailable"),
        (ValueError("bad request"), "invalid_request"),
        (RuntimeError("unexpected"), "provider_unavailable"),
    ],
)
async def test_async_result_maps_provider_and_request_failures(error, code) -> None:
    connection = _Connection()

    async def fail():
        raise error

    await ws._send_async_result(connection, {"id": 9}, fail())
    assert connection.errors[0][1] == code


def test_resolve_runtime_requires_explicit_or_single_loaded_entry(
    hass, monkeypatch
) -> None:
    runtime = _runtime()
    entries = [SimpleNamespace(entry_id="one"), SimpleNamespace(entry_id="two")]
    original_entries = hass.config_entries.async_entries
    monkeypatch.setattr(
        hass.config_entries,
        "async_entries",
        lambda domain=None: entries if domain == DOMAIN else original_entries(domain),
    )
    monkeypatch.setattr(
        ws,
        "runtime_from_hass",
        lambda _hass, entry_id: runtime if entry_id == "one" else None,
    )
    assert ws._resolve_runtime(hass, "one") is runtime
    assert ws._resolve_runtime(hass, None) is runtime

    monkeypatch.setattr(ws, "runtime_from_hass", lambda *_: runtime)
    assert ws._resolve_runtime(hass, None) is None
    hass.data.setdefault(DOMAIN, {})
