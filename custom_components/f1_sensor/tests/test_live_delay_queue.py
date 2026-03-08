from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.f1_sensor.__init__ import (
    TopThreeCoordinator,
    _apply_delay_with_queue,
    _close_delayed_ingest_state,
    _init_delayed_ingest_state,
    _wrap_delayed_handler,
)


class _QueueProbe:
    def __init__(self, hass, delay: int) -> None:
        self.hass = hass
        self._delay = delay
        self._replay_mode = False
        self.delivered: list[str] = []
        _init_delayed_ingest_state(self)


@pytest.mark.asyncio
async def test_delayed_ingest_queue_preserves_stream_order(hass) -> None:
    probe = _QueueProbe(hass, delay=1)
    wrapped = _wrap_delayed_handler(probe, probe.delivered.append)

    try:
        wrapped("first")
        await asyncio.sleep(0.25)
        wrapped("second")
        await asyncio.sleep(0.85)
        await hass.async_block_till_done()

        assert probe.delivered == ["first"]

        await asyncio.sleep(0.3)
        await hass.async_block_till_done()

        assert probe.delivered == ["first", "second"]
    finally:
        _close_delayed_ingest_state(probe)


@pytest.mark.asyncio
async def test_delayed_ingest_queue_flushes_when_delay_becomes_zero(hass) -> None:
    probe = _QueueProbe(hass, delay=1)
    wrapped = _wrap_delayed_handler(probe, probe.delivered.append)

    try:
        wrapped("queued")
        await asyncio.sleep(0.2)

        _apply_delay_with_queue(probe, 0)
        await hass.async_block_till_done()

        assert probe.delivered == ["queued"]
        assert probe._delay == 0
    finally:
        _close_delayed_ingest_state(probe)


@pytest.mark.asyncio
async def test_top_three_continues_updating_with_live_delay(hass) -> None:
    coordinator = TopThreeCoordinator(
        hass,
        session_coord=SimpleNamespace(),
        delay_seconds=1,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
    )
    wrapped = _wrap_delayed_handler(coordinator, coordinator._on_bus_message)

    try:
        wrapped(
            {
                "Lines": [
                    {"Position": 1, "Tla": "VER"},
                    {"Position": 2, "Tla": "HAM"},
                    {"Position": 3, "Tla": "NOR"},
                ]
            }
        )
        await asyncio.sleep(0.2)
        wrapped(
            {
                "Lines": [
                    {"Position": 1, "Tla": "VER"},
                    {"Position": 2, "Tla": "LEC"},
                    {"Position": 3, "Tla": "NOR"},
                ]
            }
        )

        await asyncio.sleep(0.9)
        await hass.async_block_till_done()
        assert [line["Tla"] for line in coordinator.data["lines"]] == [
            "VER",
            "HAM",
            "NOR",
        ]

        await asyncio.sleep(0.35)
        await hass.async_block_till_done()
        assert [line["Tla"] for line in coordinator.data["lines"]] == [
            "VER",
            "LEC",
            "NOR",
        ]
    finally:
        await coordinator.async_close()
