"""Cancellation and ownership regressions for the real shared Jolpica client."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components import f1_sensor
from custom_components.f1_sensor import jolpica
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.jolpica import JOLPICA_CLIENT_KEY, JolpicaClient

_USER_AGENT = "HomeAssistantF1Sensor/1.0.0 HomeAssistant/2026.9.0"


@pytest.fixture
def controlled_clients(hass, monkeypatch):
    """Use production client behavior with only its storage I/O controlled."""
    clients = []
    stores = []

    class ControlledStore:
        def __init__(self, *_args):
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.finished = asyncio.Event()
            self.on_return = None
            self.async_save = AsyncMock()
            stores.append(self)

        async def async_load(self):
            self.started.set()
            try:
                await self.release.wait()
                if self.on_return is not None:
                    self.on_return()
                return {}
            finally:
                self.finished.set()

    class RecordingClient(JolpicaClient):
        def __init__(self, *args):
            super().__init__(*args)
            clients.append(self)

    monkeypatch.setattr(jolpica, "Store", ControlledStore)
    monkeypatch.setattr(f1_sensor, "JolpicaClient", RecordingClient)
    return clients, stores


async def _start_waiter(hass):
    started = asyncio.Event()

    async def get_client():
        started.set()
        return await f1_sensor._async_get_shared_jolpica_client(
            hass, AsyncMock(), _USER_AGENT
        )

    waiter = asyncio.create_task(get_client())
    await started.wait()
    # Yield one loop turn so the separately owned initializer enters storage I/O.
    await asyncio.sleep(0)
    return waiter


async def _finish_probe(hass, waiters, stores):
    """Release background initialization even when the baseline assertion fails."""
    for store in stores:
        store.release.set()
    await asyncio.gather(*waiters, return_exceptions=True)
    await hass.async_block_till_done()
    await f1_sensor._async_close_shared_client_if_unused(hass)


@pytest.mark.asyncio
async def test_cancelled_last_waiter_cannot_publish_client_later(
    hass, controlled_clients
):
    clients, stores = controlled_clients
    waiter = await _start_waiter(hass)
    await stores[0].started.wait()
    try:
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        await f1_sensor._async_close_shared_client_if_unused(hass)
        stores[0].release.set()
        await hass.async_block_till_done()
        assert JOLPICA_CLIENT_KEY not in hass.data[DOMAIN]
        assert clients[0]._closed is True
        assert f1_sensor._JOLPICA_CLIENT_INIT_TASK_KEY not in hass.data[DOMAIN]
    finally:
        await _finish_probe(hass, [waiter], stores)


@pytest.mark.asyncio
async def test_cancelling_one_waiter_preserves_shared_initialization_for_retry(
    hass, controlled_clients
):
    clients, stores = controlled_clients
    first = await _start_waiter(hass)
    await stores[0].started.wait()
    second = await _start_waiter(hass)
    waiters = [first, second]
    try:
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        await f1_sensor._async_close_shared_client_if_unused(hass)
        retry = await _start_waiter(hass)
        waiters.append(retry)
        # A retry joins the still-owned initialization, not a second limiter.
        assert len(clients) == 1
        stores[0].release.set()
        second_client, retry_client = await asyncio.gather(second, retry)
        assert second_client is retry_client is clients[0]
        assert second_client._closed is False
        assert hass.data[DOMAIN][JOLPICA_CLIENT_KEY] is second_client
        assert f1_sensor._JOLPICA_CLIENT_INIT_TASK_KEY not in hass.data[DOMAIN]
    finally:
        await _finish_probe(hass, waiters, stores)


@pytest.mark.asyncio
async def test_cancel_after_initialization_before_waiter_resumes_closes_client(
    hass, controlled_clients
):
    clients, stores = controlled_clients
    waiter = await _start_waiter(hass)
    await stores[0].started.wait()
    stores[0].on_return = lambda: hass.loop.call_soon(waiter.cancel)
    try:
        stores[0].release.set()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        await f1_sensor._async_close_shared_client_if_unused(hass)
        assert clients[0]._closed is True
        assert JOLPICA_CLIENT_KEY not in hass.data[DOMAIN]
    finally:
        await _finish_probe(hass, [waiter], stores)


@pytest.mark.asyncio
async def test_last_entry_unload_preserves_an_initializing_waiter(
    hass, monkeypatch, controlled_clients
):
    clients, stores = controlled_clients
    waiter = await _start_waiter(hass)
    await stores[0].started.wait()
    entry = SimpleNamespace(entry_id="old-entry", runtime_data=None)
    hass.data[DOMAIN][entry.entry_id] = {}
    monkeypatch.setattr(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)
    )
    try:
        assert await f1_sensor.async_unload_entry(hass, entry)
        assert f1_sensor._JOLPICA_CLIENT_INIT_TASK_KEY in hass.data[DOMAIN]
        stores[0].release.set()
        client = await waiter
        assert client is clients[0]
        assert not client._closed
    finally:
        await _finish_probe(hass, [waiter], stores)


@pytest.mark.asyncio
async def test_failed_setup_does_not_close_client_claimed_by_another_setup(
    hass, monkeypatch, controlled_clients
):
    """A claimed client remains owned before its entry runtime is published."""
    clients, stores = controlled_clients
    acquired = {name: asyncio.Event() for name in ("failed", "pending")}
    proceed = {name: asyncio.Event() for name in ("failed", "pending")}

    async def setup_entry(_hass, entry, _transaction):
        client = await f1_sensor._async_get_shared_jolpica_client(
            hass, AsyncMock(), _USER_AGENT
        )
        acquired[entry.entry_id].set()
        await proceed[entry.entry_id].wait()
        if entry.entry_id == "failed":
            raise RuntimeError("setup failed after acquiring shared client")
        hass.data[DOMAIN][entry.entry_id] = {"jolpica_client": client}
        return True

    monkeypatch.setattr(f1_sensor, "_async_setup_entry", setup_entry)
    monkeypatch.setattr(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)
    )
    entries = {
        name: SimpleNamespace(entry_id=name, runtime_data=None) for name in acquired
    }
    tasks = {
        name: asyncio.create_task(f1_sensor.async_setup_entry(hass, entry))
        for name, entry in entries.items()
    }
    try:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await stores[0].started.wait()
        stores[0].release.set()
        await asyncio.gather(*(event.wait() for event in acquired.values()))
        proceed["failed"].set()
        with pytest.raises(RuntimeError, match="setup failed"):
            await tasks["failed"]
        assert clients[0]._closed is False
        assert hass.data[DOMAIN][JOLPICA_CLIENT_KEY] is clients[0]
        proceed["pending"].set()
        assert await tasks["pending"]
        assert await f1_sensor.async_unload_entry(hass, entries["pending"])
        assert clients[0]._closed is True
        assert f1_sensor._JOLPICA_SETUP_OWNERS_KEY not in hass.data[DOMAIN]
    finally:
        for event in proceed.values():
            event.set()
        await _finish_probe(hass, list(tasks.values()), stores)
        hass.data[DOMAIN].pop("pending", None)
        await f1_sensor._async_close_shared_client_if_unused(hass)
