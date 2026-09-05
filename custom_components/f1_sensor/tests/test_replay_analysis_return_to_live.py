"""Replay must not retain analysis when live data resumes for the same session."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from custom_components import f1_sensor as f1
from custom_components.f1_sensor.analysis import Phase4AnalysisStore
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.history import LapAnalysisStore
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.replay_mode import (
    ReplayController,
    ReplayIndex,
    ReplayState,
)
from custom_components.f1_sensor.signalr import LiveBus
from custom_components.f1_sensor.tests.test_phase_4_analysis import _timing_pair


@pytest.mark.asyncio
@pytest.mark.parametrize("delay", [0, 30])
@pytest.mark.parametrize("ending", ["stop", "natural"])
async def test_return_to_live_clears_replay_analysis_for_same_session(
    hass, tmp_path, delay, ending
):
    availability = LiveAvailabilityTracker()
    bus = LiveBus(hass, AsyncMock(), requested_streams={"TimingData", "Heartbeat"})
    controller = ReplayController(
        hass, "entry", AsyncMock(), bus, live_state=availability
    )
    delayed = f1._DelayedAnalysisBus(hass, bus, delay, None, availability)

    def provider():
        return "replay" if controller._replay_active else "f1_live"

    laps = LapAnalysisStore(delayed, source_provider=provider)
    analysis = Phase4AnalysisStore(delayed, laps, source_provider=provider)
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "replay_reset_callbacks": f1._build_replay_reset_callbacks(
            bus, delayed, laps, analysis
        ),
    }
    frames_file = tmp_path / "replay.jsonl"
    frames_file.write_text(
        json.dumps(
            {
                "t": 0 if ending == "natural" else 60_000,
                "s": "Heartbeat",
                "p": {"Utc": "2026-09-04T14:00:00Z"},
            }
        )
        + "\n"
    )
    session = {"Key": "same", "Type": "Race", "Name": "Race"}
    index = ReplayIndex(
        session_id="same",
        total_frames=1,
        duration_ms=60_001,
        session_started_at_ms=0,
        frames_file=frames_file,
        index_file=tmp_path / "index.json",
        initial_state={
            "SessionInfo": session,
            "SessionStatus": {"Status": "Started"},
            "TimingData": _timing_pair(
                2, first_position=1, second_position=2, first_gap="", second_gap="+0.4"
            ),
        },
    )
    controller.session_manager._loaded_index = index
    controller.session_manager._state = ReplayState.READY
    try:
        await controller.async_play()
        assert analysis.snapshot()["session_id"] == "same:Race"
        assert laps.diagnostics()["laps"] == 2
        if ending == "stop":
            await controller.async_stop()
        else:
            await asyncio.wait_for(controller._playback_task, 3)
        assert controller.state is ReplayState.IDLE
        assert analysis.snapshot()["session_id"] is None
        assert analysis.diagnostics()["timeline_events"] == 0
        assert laps.diagnostics()["laps"] == 0
        assert not delayed._delay_queue
        assert bus.get_last_payload("TimingData") is None
        assert not delayed._last_payload

        # The live source can reconnect to the SAME session at a later point.
        # Reversed positions here must establish a baseline, not an overtake.
        delayed.set_delay(0)
        availability.set_state(True, "live-Race")
        bus.inject_message("SessionInfo", session)
        bus.inject_message("SessionStatus", {"Status": "Ends"})
        bus.inject_message(
            "TimingData",
            _timing_pair(
                20,
                first_position=2,
                second_position=1,
                first_gap="+0.4",
                second_gap="",
            ),
        )
        snapshot = analysis.snapshot()
        assert snapshot["position_exchange_count"] == 0
        assert all(
            event["provider"] == "f1_live" for event in snapshot["timeline"]["events"]
        )
        assert laps.diagnostics()["laps"] == 2
    finally:
        await controller.async_close()
        await bus.async_close()
        await analysis.async_close()
        await laps.async_close()
        await delayed.async_close()
