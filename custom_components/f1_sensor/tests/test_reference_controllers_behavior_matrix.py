"""Behavior coverage for persisted delay and reference controllers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

from custom_components.f1_sensor.live_delay import LiveDelayController
from custom_components.f1_sensor.reference_controller import StoredReferenceController


async def test_live_delay_controller_persistence_listeners_and_bounds(hass) -> None:
    controller = LiveDelayController(hass, "entry", min_seconds=2, max_seconds=10)
    controller._store.async_load = AsyncMock(return_value={"seconds": "8.9"})
    controller._store.async_save = AsyncMock()

    assert controller.current == 0
    assert await controller.async_initialize("bad") == 8
    await controller._save_task
    assert controller._store.async_save.await_args.args == ({"seconds": 8},)
    assert await controller.async_set_delay(8) == 8

    received = []
    remove = controller.add_listener(received.append)
    broken = Mock(side_effect=RuntimeError("listener"))
    remove_broken = controller.add_listener(broken)
    assert received == [8]
    assert await controller.async_set_delay(99, source="test") == 10
    await controller._save_task
    assert received == [8, 10]
    assert broken.call_count == 2
    remove()
    remove()
    remove_broken()

    assert controller._coerce(None) is None
    assert controller._coerce(object()) is None
    assert controller._clamp(-100) == 2
    await controller.async_close()
    assert controller._listeners == []


async def test_live_delay_commit_cancels_pending_and_handles_save_failure(hass) -> None:
    controller = LiveDelayController(hass, "entry")
    assert await controller.async_set_delay(3) == 3
    controller._loaded = True
    pending = asyncio.create_task(asyncio.sleep(60))
    controller._save_task = pending
    controller._store.async_save = AsyncMock(side_effect=RuntimeError("store"))

    await controller._async_commit()
    assert pending.cancelled() or pending.cancelling()
    await controller._save_task
    await controller.async_close()


async def test_stored_reference_controller_full_lifecycle(hass) -> None:
    controller = StoredReferenceController(
        hass,
        "entry",
        storage_key="test_reference",
        default="session",
        allowed={"session", "lap_sync"},
        log_label="Reference",
    )
    controller._store.async_load = AsyncMock(return_value={"reference": " LAP_SYNC "})
    controller._store.async_save = AsyncMock()

    assert controller.current == "session"
    assert await controller.async_initialize("invalid") == "lap_sync"
    await controller._save_task
    assert await controller.async_set_reference("lap_sync") == "lap_sync"

    received = []
    remove = controller.add_listener(received.append)
    broken = Mock(side_effect=RuntimeError("listener"))
    remove_broken = controller.add_listener(broken)
    assert await controller.async_set_reference("session", source="test") == "session"
    await controller._save_task
    assert received == ["lap_sync", "session"]
    remove()
    remove()
    remove_broken()
    assert controller._normalize(None) == "session"

    pending = asyncio.create_task(asyncio.sleep(60))
    controller._save_task = pending
    controller._store.async_save = AsyncMock(side_effect=RuntimeError("store"))
    await controller._async_commit()
    assert pending.cancelled() or pending.cancelling()
    await controller._save_task
    await controller.async_close()
    assert controller._listeners == []
