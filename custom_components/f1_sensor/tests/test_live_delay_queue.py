from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.f1_sensor.__init__ import (
    LiveDriversCoordinator,
    PitStopCoordinator,
    TeamRadioCoordinator,
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


@pytest.mark.asyncio
async def test_live_drivers_continues_updating_with_live_delay(hass) -> None:
    coordinator = LiveDriversCoordinator(
        hass,
        session_coord=SimpleNamespace(),
        delay_seconds=1,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
    )
    wrapped = _wrap_delayed_handler(coordinator, coordinator._on_timingdata)

    try:
        wrapped(
            {
                "Lines": {
                    "1": {
                        "Position": "1",
                        "LastLapTime": {"Value": "1:30.000"},
                    }
                }
            }
        )
        await asyncio.sleep(0.2)
        wrapped(
            {
                "Lines": {
                    "1": {
                        "Position": "1",
                        "LastLapTime": {"Value": "1:29.500"},
                    }
                }
            }
        )

        await asyncio.sleep(0.9)
        await hass.async_block_till_done()
        assert coordinator.data["drivers"]["1"]["timing"]["last_lap"] == "1:30.000"

        await asyncio.sleep(0.35)
        await hass.async_block_till_done()
        assert coordinator.data["drivers"]["1"]["timing"]["last_lap"] == "1:29.500"
    finally:
        await coordinator.async_close()


@pytest.mark.asyncio
async def test_pitstop_continues_updating_with_live_delay(hass) -> None:
    coordinator = PitStopCoordinator(
        hass,
        session_coord=SimpleNamespace(),
        delay_seconds=1,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
        history_limit=10,
        drivers_coordinator=None,
    )
    wrapped = _wrap_delayed_handler(coordinator, coordinator._on_bus_pitstopseries)

    try:
        wrapped(
            {
                "PitTimes": {
                    "44": [
                        {
                            "Timestamp": "2026-03-08T04:17:26.571Z",
                            "PitStop": {
                                "RacingNumber": "44",
                                "PitStopTime": "2.5",
                                "PitLaneTime": "20.0",
                                "Lap": "10",
                            },
                        }
                    ]
                }
            }
        )
        await asyncio.sleep(0.2)
        wrapped(
            {
                "PitTimes": {
                    "44": [
                        {
                            "Timestamp": "2026-03-08T04:37:26.571Z",
                            "PitStop": {
                                "RacingNumber": "44",
                                "PitStopTime": "2.6",
                                "PitLaneTime": "20.5",
                                "Lap": "20",
                            },
                        }
                    ]
                }
            }
        )

        await asyncio.sleep(0.9)
        await hass.async_block_till_done()
        assert coordinator.data["total_stops"] == 1
        assert len(coordinator.data["cars"]["44"]["stops"]) == 1

        await asyncio.sleep(0.35)
        await hass.async_block_till_done()
        assert coordinator.data["total_stops"] == 2
        assert len(coordinator.data["cars"]["44"]["stops"]) == 2
    finally:
        await coordinator.async_close()


@pytest.mark.asyncio
async def test_team_radio_continues_updating_with_live_delay(hass) -> None:
    coordinator = TeamRadioCoordinator(
        hass,
        session_coord=SimpleNamespace(),
        delay_seconds=1,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
        history_limit=10,
    )
    wrapped = _wrap_delayed_handler(coordinator, coordinator._on_bus_message)

    try:
        wrapped(
            {
                "Captures": [
                    {
                        "Utc": "2026-03-06T04:52:47.5228207Z",
                        "RacingNumber": "14",
                        "Path": "TeamRadio/ALO_14_20260306_155235.mp3",
                    }
                ]
            }
        )
        await asyncio.sleep(0.2)
        wrapped(
            {
                "Captures": [
                    {
                        "Utc": "2026-03-07T01:42:48.7125725Z",
                        "RacingNumber": "63",
                        "Path": "TeamRadio/RUS_63_20260307_124200.mp3",
                    }
                ]
            }
        )

        await asyncio.sleep(0.9)
        await hass.async_block_till_done()
        assert (
            coordinator.data["latest"]["Path"] == "TeamRadio/ALO_14_20260306_155235.mp3"
        )
        assert len(coordinator.data["history"]) == 1

        await asyncio.sleep(0.35)
        await hass.async_block_till_done()
        assert (
            coordinator.data["latest"]["Path"] == "TeamRadio/RUS_63_20260307_124200.mp3"
        )
        assert len(coordinator.data["history"]) == 2
    finally:
        await coordinator.async_close()
