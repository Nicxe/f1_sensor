"""Populated multi-client load through real Home Assistant WebSocket sockets."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import json
import logging
import math
from pathlib import Path
import re
from time import perf_counter

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor.analysis_websocket import _ANALYSIS_HUBS
from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS
from custom_components.f1_sensor.track_map import TrackMapPosition
from custom_components.f1_sensor.track_map_websocket import _TRACK_MAP_HUBS

BUDGET = json.loads(
    (Path(__file__).parent / "fixtures/release_performance_budgets.json").read_text()
)["websocket"]


def _timing(lap: int, sequence: int = 0) -> dict:
    return {
        "Lines": {
            str(number): {
                "NumberOfLaps": lap,
                "Position": str(number),
                "GapToLeader": f"+{sequence + number - 1:.3f}",
                "IntervalToPositionAhead": {"Value": "+0.7"},
                "LastLapTime": {"Value": f"{90 + number / 10:.3f}"},
                "Sectors": {
                    str(sector): {"Value": f"{30 + number / 30:.3f}"}
                    for sector in range(3)
                },
            }
            for number in range(1, BUDGET["drivers"] + 1)
        }
    }


def _positions(sequence: int) -> list[TrackMapPosition]:
    return [
        TrackMapPosition(
            racing_number=str(number),
            timestamp=datetime.now(UTC) + timedelta(milliseconds=sequence),
            x=1000 + sequence + number - 1,
            y=2000 + sequence + number,
            z=0,
            status="OnTrack",
        )
        for number in range(1, BUDGET["drivers"] + 1)
    ]


async def _subscribe(client, entry_id: str) -> int:
    size = 0
    for msg_id, command in (
        (1, "f1_sensor/analysis/subscribe"),
        (2, "f1_sensor/track_map/subscribe"),
    ):
        message = {
            "id": msg_id,
            "type": command,
            "entry_id": entry_id,
            "throttle_ms": BUDGET["throttle_ms"],
        }
        if msg_id == 2:
            message["protocol_version"] = 2
        await client.send_json(message)
        result = await client.receive_json()
        assert result["success"], result
        event = await client.receive_json()
        assert event["type"] == "event"
        assert event["id"] == msg_id
        size += len(json.dumps(event).encode())
    return size


async def _receive_latest(client, sequence: int) -> int:
    received = set()
    size = 0
    async with asyncio.timeout(10):
        while received != {1, 2}:
            message = await client.receive_json()
            assert message["type"] == "event", message
            size += len(json.dumps(message).encode())
            payload = message["event"]
            if message["id"] == 1:
                assert len(payload["drivers"]) == BUDGET["drivers"]
                assert payload["strategy"]["coverage"]["raw_laps"] >= 1000
                if payload["timing"][0]["gap_to_leader"] == f"+{sequence:.3f}":
                    received.add(1)
            elif payload.get("changes", {}).get("1", {}).get("x") == 1000 + sequence:
                received.add(2)
    return size


@pytest.mark.performance
@pytest.mark.parametrize("client_count", BUDGET["clients"])
async def test_real_websocket_clients_receive_bounded_populated_updates(
    hass,
    enable_custom_integrations,
    aioclient_mock,
    hass_ws_client,
    caplog,
    client_count: int,
) -> None:
    aioclient_mock.get(
        re.compile(r"https://.*"),
        json={"Meetings": [], "MRData": {"RaceTable": {"Races": []}}},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        data={
            "sensor_name": "F1 load",
            "enable_race_control": True,
            "operation_mode": "live",
            "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS - {"track_status"}),
        },
    )
    entry.add_to_hass(hass)
    clients = []
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry.runtime_data
    bus = runtime.live.bus
    store = runtime.track_map_store
    analysis = runtime.analysis.store
    try:
        bus._dispatch(
            "SessionInfo",
            {"Key": "release-load", "Name": "Race", "Type": "Race"},
        )
        drivers = {
            str(number): {
                "RacingNumber": str(number),
                "FullName": f"Driver {number}",
                "Tla": f"D{number:02d}",
                "TeamName": f"Team {(number - 1) // 2}",
            }
            for number in range(1, BUDGET["drivers"] + 1)
        }
        bus._dispatch("DriverList", drivers)
        bus._dispatch("TrackStatus", {"Status": "1"})
        bus._dispatch(
            "TimingAppData",
            {
                "Lines": {
                    number: {"Stints": {"0": {"Compound": "MEDIUM"}}}
                    for number in drivers
                }
            },
        )
        for lap in range(1, BUDGET["seed_laps"] + 1):
            bus._dispatch("TimingData", _timing(lap))
            if lap % 10 == 0:
                await asyncio.sleep(0)
        store.update_session_info({"Key": "release-load", "Name": "Race"})
        store.update_driver_list(drivers)
        store.update_positions(_positions(0))
        assert analysis.diagnostics()["strategy_laps"] >= 1000

        clients = list(
            await asyncio.gather(*(hass_ws_client(hass) for _ in range(client_count)))
        )
        initial_bytes = sum(
            await asyncio.gather(
                *(_subscribe(client, entry.entry_id) for client in clients)
            )
        )
        assert len(_ANALYSIS_HUBS[analysis]._subscribers) == client_count
        assert len(_TRACK_MAP_HUBS[store]._subscribers) == client_count
        dispatch_ms = []
        update_bytes = 0
        started = perf_counter()
        for burst in range(BUDGET["updates"] // BUDGET["burst_size"]):
            for offset in range(BUDGET["burst_size"]):
                sequence = burst * BUDGET["burst_size"] + offset + 1
                tick = perf_counter()
                bus._dispatch(
                    "TimingData",
                    _timing(BUDGET["seed_laps"] + sequence // 20, sequence),
                )
                store.update_positions(_positions(sequence), source="live")
                dispatch_ms.append((perf_counter() - tick) * 1000)
                await asyncio.sleep(0)
            update_bytes += sum(
                await asyncio.gather(
                    *(_receive_latest(client, sequence) for client in clients)
                )
            )
        elapsed_ms = (perf_counter() - started) * 1000
        p95_ms = sorted(dispatch_ms)[math.ceil(len(dispatch_ms) * 0.95) - 1]
        source_seconds = (
            BUDGET["updates"] / BUDGET["burst_size"] * BUDGET["throttle_ms"] / 1000
        )

        await asyncio.gather(*(client.close() for client in clients))
        await hass.async_block_till_done()
        assert analysis not in _ANALYSIS_HUBS
        assert store not in _TRACK_MAP_HUBS
        clients = list(
            await asyncio.gather(*(hass_ws_client(hass) for _ in range(client_count)))
        )
        reconnect_bytes = sum(
            await asyncio.gather(
                *(_subscribe(client, entry.entry_id) for client in clients)
            )
        )
        print(
            json.dumps(
                {
                    "profile": "real_ha_websockets",
                    "clients": client_count,
                    "initial_bytes": initial_bytes,
                    "update_bytes": update_bytes,
                    "reconnect_bytes": reconnect_bytes,
                    "source_seconds": source_seconds,
                    "elapsed_ms": elapsed_ms,
                    "p95_dispatch_ms": p95_ms,
                }
            )
        )
        assert elapsed_ms < BUDGET["total_runtime_ms"]
        assert p95_ms < BUDGET["p95_dispatch_ms"]
        assert (
            update_bytes / client_count / source_seconds
            <= BUDGET["bytes_per_client_per_source_second"]
        )
    finally:
        await asyncio.gather(*(client.close() for client in clients))
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert analysis not in _ANALYSIS_HUBS
        assert store not in _TRACK_MAP_HUBS
        assert not analysis._listeners
        assert not store._listeners
    assert not [
        record
        for record in caplog.records
        if record.levelno >= logging.ERROR
        and record.name.startswith(("aiohttp", "custom_components.f1_sensor"))
    ]
