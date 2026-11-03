"""Preserve the event clock required by online lap inference."""

from datetime import UTC, datetime
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.f1_sensor.replay_mode import (
    ReplayController,
    ReplayIndex,
    ReplayTransport,
)
from custom_components.f1_sensor.signalr import LiveBus


@pytest.mark.asyncio
async def test_live_timing_keeps_event_time_without_mutating_source(hass):
    """A delayed consumer must receive the source clock, not delivery time."""
    bus = LiveBus(hass, MagicMock())
    received = []
    bus.subscribe("TimingData", received.append)
    source = {"Lines": {"63": {"NumberOfLaps": 5}}}
    utc = "2026-10-24T21:24:35.798Z"
    bus._process_payload({"M": [{"M": "feed", "A": ["TimingData", source, utc]}]})
    await hass.async_block_till_done()

    assert (
        received[0]["_f1_source_time"]
        == datetime(2026, 10, 24, 21, 24, 35, 798000, tzinfo=UTC).timestamp()
    )
    assert received[0]["_f1_source_utc"] == "2026-10-24T21:24:35.798000+00:00"
    assert "_f1_source_time" not in source
    await bus.async_close()


@pytest.mark.asyncio
async def test_timing_subscription_snapshot_is_not_a_new_lap(hass):
    """Cached green sectors are distinguishable from fresh crossings."""
    bus = LiveBus(hass, MagicMock())
    received = []
    bus.subscribe("TimingData", received.append)
    source = {"Lines": {"63": {"NumberOfLaps": 5}}}
    bus._process_payload({"R": {"TimingData": source}})
    await hass.async_block_till_done()

    assert received[0]["_f1_snapshot"] is True
    assert "_f1_snapshot" not in source
    await bus.async_close()


@pytest.mark.asyncio
async def test_replay_clock_survives_playback_and_seek(hass, tmp_path):
    """Playback and catch-up use identical event seconds at any replay speed."""
    frames_file = tmp_path / "frames.jsonl"
    frames_file.write_text(
        json.dumps({"t": 12345, "s": "TimingData", "p": {"Lines": {}}}) + "\n"
    )
    index = ReplayIndex(
        session_id="qualifying",
        total_frames=1,
        duration_ms=12345,
        session_started_at_ms=12345,
        frames_file=frames_file,
        index_file=tmp_path / "index.json",
    )
    transport = ReplayTransport(hass, index, speed_multiplier=10)
    messages = [message async for message in transport.messages()]
    payload = messages[0]["M"][0]["A"][1]
    assert payload["_f1_source_time"] == 12.345
    assert "_f1_source_utc" not in payload

    bus = MagicMock()
    controller = ReplayController(hass, "entry", AsyncMock(), bus)
    controller._control_is_current = lambda *_: True
    await controller._replay_frames_range(
        index, start_exclusive_ms=0, end_inclusive_ms=12345
    )
    assert bus.inject_message.call_args.args[1]["_f1_source_time"] == 12.345
