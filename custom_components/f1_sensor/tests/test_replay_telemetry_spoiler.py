"""No Spoiler gates direct telemetry requests and late or cached responses."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.f1_sensor import analysis_websocket as ws
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager
from custom_components.f1_sensor.replay_telemetry import ReplayTelemetryService
from custom_components.f1_sensor.tests.test_analysis_websocket_behavior_matrix import (
    _Connection,
)
from custom_components.f1_sensor.tests.test_replay_telemetry_behavior_matrix import (
    _manager,
    _Response,
    _Session,
)


def _command(catalog):
    return (
        ws._ws_replay_telemetry_catalog if catalog else ws._ws_compare_replay_telemetry
    )


def _message():
    return {
        "id": 1,
        "expected_session_id": "session",
        "selections": [{"driver_number": 4, "lap_number": 1}],
    }


@pytest.mark.parametrize("catalog", [False, True])
@pytest.mark.parametrize("state", ["active", "missing", "unknown"])
async def test_direct_telemetry_ws_requires_known_disabled_spoiler_protection(
    hass, monkeypatch, catalog, state
):
    root = hass.data.setdefault(DOMAIN, {})
    if state != "missing":
        root["no_spoiler_manager"] = SimpleNamespace(
            is_active=True if state == "active" else None
        )
    service = SimpleNamespace(
        async_compare=AsyncMock(return_value={"secret": 1}),
        async_catalog=AsyncMock(return_value={"secret": 1}),
    )
    monkeypatch.setattr(
        ws,
        "_resolve_runtime",
        Mock(return_value=SimpleNamespace(analysis=SimpleNamespace(telemetry=service))),
    )
    connection = _Connection()
    _command(catalog)(hass, connection, _message())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert connection.results == []
    assert connection.errors[-1][1] == "spoiler_blocked"
    service.async_compare.assert_not_awaited()
    service.async_catalog.assert_not_awaited()


@pytest.mark.parametrize("catalog", [False, True])
async def test_spoiler_toggle_blocks_cached_and_inflight_telemetry_results(
    hass, tmp_path, monkeypatch, catalog
):
    protection = NoSpoilerModeManager(hass)
    monkeypatch.setattr(protection._store, "async_save", AsyncMock())
    hass.data.setdefault(DOMAIN, {})["no_spoiler_manager"] = protection
    manager = _manager(tmp_path)
    manager.get_loaded_index().frames_file.write_text(
        '{"t":0,"s":"SessionStatus","p":{"Status":"Started"}}\n'
        '{"t":1000,"s":"TimingData","p":{"Lines":{"4":{"NumberOfLaps":1}}}}\n'
    )
    service = ReplayTelemetryService(hass, _Session(_Response(200)), manager)
    monkeypatch.setattr(
        ws,
        "_resolve_runtime",
        Mock(return_value=SimpleNamespace(analysis=SimpleNamespace(telemetry=service))),
    )
    connection = _Connection()
    command = _command(catalog)
    command(hass, connection, _message())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(connection.results) == 1

    await protection.async_set_active(True)
    connection.results.clear()
    command(hass, connection, _message())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not connection.results
    assert connection.errors[-1][1] == "spoiler_blocked"
    assert service.diagnostics()["cache_hits"] == 0

    await protection.async_set_active(False)
    entered, release = asyncio.Event(), asyncio.Event()
    method = "async_catalog" if catalog else "async_compare"
    original = getattr(service, method)

    async def delayed(*args, **kwargs):
        result = await original(*args, **kwargs)
        entered.set()
        await release.wait()
        return result

    monkeypatch.setattr(service, method, delayed)
    command(hass, connection, _message())
    await entered.wait()
    await protection.async_set_active(True)
    release.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not connection.results
    assert connection.errors[-1][1] == "spoiler_blocked"
    await service.async_close()
