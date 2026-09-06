"""A finishing close cannot release a newer LiveBus transport generation."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from unittest.mock import AsyncMock

import pytest

from custom_components.f1_sensor.signalr import LiveBus, LiveConnectionState


class _ControlledTransport:
    """Control external connection and shutdown I/O without mocking the bus."""

    def __init__(
        self, name: str, *, hold_close: bool = False, hold_connection: bool = False
    ) -> None:
        self.name = name
        self.connecting = asyncio.Event()
        self.may_connect = asyncio.Event()
        self.closing = asyncio.Event()
        self.may_close = asyncio.Event()
        self.closed = asyncio.Event()
        self.close_count = 0
        if not hold_connection:
            self.may_connect.set()
        if not hold_close:
            self.may_close.set()

    async def ensure_connection(self) -> None:
        self.connecting.set()
        await self.may_connect.wait()

    async def messages(self):
        yield {"R": {"TrackStatus": {"Status": "1", "Message": self.name}}}
        await self.closed.wait()

    async def close(self) -> None:
        self.close_count += 1
        self.closing.set()
        await self.may_close.wait()
        self.closed.set()


@pytest.mark.parametrize("new_connected", [False, True], ids=["connecting", "live"])
async def test_old_close_preserves_new_transport_task_and_connection_state(
    hass, new_connected: bool
) -> None:
    """A real swap may start while old transport cleanup is awaiting I/O."""
    old = _ControlledTransport("old", hold_close=True)
    new = _ControlledTransport("new", hold_connection=not new_connected)
    bus = LiveBus(hass, AsyncMock(), transport_factory=lambda: old)
    new_frame = asyncio.Event()
    unsubscribe = bus.subscribe(
        "TrackStatus",
        lambda payload: new_frame.set() if payload.get("Message") == "new" else None,
    )
    shutdown = None
    new_task = None
    try:
        async with asyncio.timeout(5):
            await bus.start()
            await old.connecting.wait()
            old_task = bus._task
            old_heartbeat_guard = bus._heartbeat_guard
            shutdown = asyncio.create_task(bus.async_close())
            await old.closing.wait()

            # The old guard must stop before a newer client becomes visible.
            assert old_heartbeat_guard is not None
            assert old_heartbeat_guard.done() or old_heartbeat_guard.cancelling()

            await bus.swap_transport(lambda: new)
            await new.connecting.wait()
            new_task = bus._task
            assert new_task is not old_task
            if new_connected:
                await new_frame.wait()

            old.may_close.set()
            await shutdown
            assert not new.closed.is_set()
            assert new.close_count == 0
            assert bus._task is new_task
            assert bus._client is new
            assert not new_task.done()
            assert bus.connection_state is (
                LiveConnectionState.LIVE
                if new_connected
                else LiveConnectionState.CONNECTING
            )

            new.may_connect.set()
            await new_frame.wait()
            assert bus.connection_state is LiveConnectionState.LIVE
            assert bus._last_payload["TrackStatus"]["Message"] == "new"
    finally:
        old.may_close.set()
        new.may_connect.set()
        if shutdown is not None:
            with suppress(asyncio.CancelledError):
                await shutdown
        unsubscribe()
        await bus.async_close()
        # Also clean the captured task if a regression detached it prematurely.
        if new_task is not None and not new_task.done():
            new_task.cancel()
            with suppress(asyncio.CancelledError):
                await new_task
