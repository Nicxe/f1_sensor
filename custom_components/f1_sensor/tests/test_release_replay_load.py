"""Race-length disk replay through real parsing and bounded analysis stores."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import gc
import json
from pathlib import Path
from time import perf_counter
import tracemalloc
from unittest.mock import AsyncMock

import pytest

from custom_components.f1_sensor.analysis import (
    MAX_STRATEGY_LAPS,
    MAX_TIMELINE_EVENTS,
    Phase4AnalysisStore,
)
from custom_components.f1_sensor.history import LapAnalysisStore
from custom_components.f1_sensor.replay_mode import ReplayIndex, ReplayTransport
from custom_components.f1_sensor.signalr import LiveBus

BUDGET = json.loads(
    (Path(__file__).parent / "fixtures/release_performance_budgets.json").read_text()
)["replay"]
MIB = 1024 * 1024


def _write_session(directory: Path, session_id: str) -> ReplayIndex:
    directory.mkdir()
    frames = directory / "frames.jsonl"
    duration = BUDGET["duration_seconds"]
    drivers = {
        str(number): {
            "RacingNumber": str(number),
            "FullName": f"Driver {number}",
            "Tla": f"D{number:02d}",
            "TeamName": f"Team {(number - 1) // 2}",
        }
        for number in range(1, BUDGET["drivers"] + 1)
    }
    initial = {
        "SessionInfo": {"Key": session_id, "Name": "Race", "Type": "Race"},
        "DriverList": drivers,
        "TrackStatus": {"Status": "1"},
        "SessionStatus": {"Status": "Started"},
        "TimingAppData": {
            "Lines": {
                number: {"Stints": {"0": {"Compound": "MEDIUM"}}} for number in drivers
            }
        },
    }
    seek_index = [{"t": 0, "offset": 0}]
    total = 0
    with frames.open("wb") as output:

        def write(t, stream, payload):
            nonlocal total
            output.write(
                (
                    json.dumps(
                        {"t": t, "s": stream, "p": payload}, separators=(",", ":")
                    )
                    + "\n"
                ).encode()
            )
            total += 1

        for stream, payload in initial.items():
            write(0, stream, payload)
        for second in range(0, duration, BUDGET["timing_interval_seconds"]):
            if second and second % 60 == 0:
                seek_index.append({"t": second * 1000, "offset": output.tell()})
            lap = second // BUDGET["lap_seconds"] + 1
            payload = {
                "Lines": {
                    number: {
                        "NumberOfLaps": lap,
                        "Position": number,
                        "GapToLeader": f"+{int(number) - 1:.3f}",
                        "IntervalToPositionAhead": {"Value": "+0.7"},
                        "LastLapTime": {"Value": f"{90 + int(number) / 10:.3f}"},
                        "Sectors": {
                            str(sector): {"Value": f"{30 + int(number) / 30:.3f}"}
                            for sector in range(3)
                        },
                    }
                    for number in drivers
                }
            }
            write(second * 1000, "TimingData", payload)
        write(duration * 1000, "SessionStatus", {"Status": "Finished"})
    index = directory / "index.json"
    index.write_text(json.dumps({"session_id": session_id, "seek_index": seek_index}))
    return ReplayIndex(
        session_id=session_id,
        total_frames=total,
        duration_ms=duration * 1000,
        session_started_at_ms=0,
        frames_file=frames,
        index_file=index,
        initial_state=initial,
        seek_index=seek_index,
    )


@pytest.mark.performance
async def test_two_race_length_disk_replays_seek_pause_and_release_memory(
    hass, tmp_path, monkeypatch
) -> None:
    indexes = []
    for number in range(BUDGET["sessions"]):
        indexes.append(
            await hass.async_add_executor_job(
                _write_session, tmp_path / str(number), f"session-{number}"
            )
        )
    disk_bytes = sum(
        path.stat().st_size for path in tmp_path.rglob("*") if path.is_file()
    )
    assert disk_bytes <= BUDGET["fixture_disk_mib"] * MIB
    bus = LiveBus(hass, AsyncMock())
    laps = LapAnalysisStore(bus, source_provider=lambda: "replay")
    analysis = Phase4AnalysisStore(bus, laps, source_provider=lambda: "replay")
    transports = []
    retained = []
    timings = []
    tracemalloc.start()
    try:
        for session_number, index in enumerate(indexes):
            transport = ReplayTransport(hass, index)
            transports.append(transport)
            # Advance only the playback wait, retaining disk, queue, JSON and store work.
            monkeypatch.setattr(
                transport,
                "_get_elapsed_playback_time",
                lambda: BUDGET["duration_seconds"] + 1,
            )
            iterator = transport.messages()
            count = 0
            started = perf_counter()
            async with asyncio.timeout(BUDGET["runtime_seconds_per_session"]):
                async for message in iterator:
                    bus._process_payload(message)
                    count += 1
                    if count == index.total_frames // 2:
                        transport.pause()
                        waiting = asyncio.create_task(anext(iterator))
                        await asyncio.sleep(0)
                        assert not waiting.done()
                        transport.resume()
                        bus._process_payload(await waiting)
                        count += 1
            timings.append(perf_counter() - started)
            assert count == index.total_frames
            assert transport.get_playback_position_ms() == index.duration_ms
            assert transport._closed
            snapshot = analysis.snapshot()
            assert f"session-{session_number}" in snapshot["session_id"]
            assert snapshot["session_status"] == "Finished"
            assert len(snapshot["drivers"]) == BUDGET["drivers"]
            assert snapshot["strategy"]["coverage"]["raw_laps"] >= 1500
            assert analysis.diagnostics()["strategy_laps"] <= MAX_STRATEGY_LAPS
            assert analysis.diagnostics()["timeline_events"] <= MAX_TIMELINE_EVENTS
            assert laps.diagnostics()["laps"] <= laps.diagnostics()["max_laps"]
            del snapshot, message
            await iterator.aclose()
            await transport.close()

            seek = ReplayTransport(hass, index, start_from_ms=index.duration_ms // 2)
            transports.append(seek)
            monkeypatch.setattr(
                seek,
                "_get_elapsed_playback_time",
                lambda: BUDGET["duration_seconds"] + 1,
            )
            seek_iterator = seek.messages()
            seek_started = perf_counter()
            async with asyncio.timeout(5):
                for _ in range(100):
                    await anext(seek_iterator)
            assert seek.get_playback_position_ms() >= index.duration_ms // 2
            seek_latency = perf_counter() - seek_started
            await seek.close()
            await seek_iterator.aclose()
            laps.reset_for_replay()
            analysis.reset_for_replay()
            gc.collect()
            current, peak = tracemalloc.get_traced_memory()
            retained.append(current)
            print(
                json.dumps(
                    {
                        "profile": "race_length_replay",
                        "session": session_number,
                        "source_seconds": BUDGET["duration_seconds"],
                        "frames": count,
                        "wall_seconds": timings[-1],
                        "seek_100_frames_seconds": seek_latency,
                        "retained_python_bytes": current,
                        "peak_python_bytes": peak,
                        "fixture_disk_bytes": disk_bytes,
                    }
                )
            )
            assert peak <= BUDGET["peak_python_allocation_mib"] * MIB
        await analysis.async_close()
        await laps.async_close()
        await bus.async_close()
        assert not analysis._unsubs
        assert not laps._unsubs
        gc.collect()
        after_unload = tracemalloc.get_traced_memory()[0]
        assert retained[-1] - retained[0] <= BUDGET["retained_growth_mib"] * MIB
        assert after_unload <= BUDGET["retained_after_unload_mib"] * MIB
    finally:
        for transport in transports:
            with suppress(Exception):
                await transport.close()
        await analysis.async_close()
        await laps.async_close()
        await bus.async_close()
        tracemalloc.stop()
