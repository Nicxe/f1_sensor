"""Replay must not retain analysis when live data resumes for the same session."""

from __future__ import annotations

import asyncio
import json
import re
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import f1_sensor as f1
from custom_components.f1_sensor.analysis import Phase4AnalysisStore
from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS
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


@pytest.mark.asyncio
@pytest.mark.parametrize("delay", [0, 30])
@pytest.mark.parametrize(
    "action", ["pause", "resume", "stop", "stop_pending", "natural"]
)
async def test_existing_websocket_receives_replay_control_without_timing_frames(
    hass,
    enable_custom_integrations,
    aioclient_mock,
    hass_ws_client,
    tmp_path,
    monkeypatch,
    delay,
    action,
):
    """A retained HA socket must receive control/reset updates after entry reload."""
    pending_frame = action == "stop_pending"
    if pending_frame:
        action = "stop"
    aioclient_mock.get(
        re.compile(r"https://.*"),
        json={"Meetings": [], "MRData": {"RaceTable": {"Races": []}}},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        data={"sensor_name": "F1"},
        options={
            "operation_mode": "live",
            "enable_race_control": True,
            "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS - {"track_status"}),
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)

    async def subscribe(command_id):
        await client.send_json(
            {
                "id": command_id,
                "type": "f1_sensor/analysis/subscribe",
                "entry_id": entry.entry_id,
                "protocol_version": 1,
                "throttle_ms": 100,
            }
        )
        acknowledgment = await client.receive_json()
        assert acknowledgment["id"] == command_id and acknowledgment["success"]
        initial = await client.receive_json()
        assert initial["id"] == command_id and initial["type"] == "event"
        return initial["event"]

    try:
        retired_manager = entry.runtime_data.replay.controller.session_manager
        listeners_before_subscribe = set(retired_manager._listeners)
        await subscribe(1)
        retired_hub_listeners = (
            set(retired_manager._listeners) - listeners_before_subscribe
        )
        assert len(retired_hub_listeners) == 1
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        while (await client.receive_json())["event"]["status"] != "closed":
            pass
        assert retired_hub_listeners.isdisjoint(retired_manager._listeners)
        registry = hass.data[DOMAIN][entry.entry_id]
        controller = entry.runtime_data.replay.controller
        await registry["live_delay_controller"].async_set_delay(delay)
        frames_file = tmp_path / "control-replay.jsonl"
        frames_file.write_text(
            json.dumps({"t": 60_000, "s": "Heartbeat", "p": {"Utc": "test"}}) + "\n"
        )
        controller.session_manager._loaded_index = ReplayIndex(
            session_id="B",
            total_frames=1,
            duration_ms=60_001,
            session_started_at_ms=0,
            frames_file=frames_file,
            index_file=tmp_path / "index.json",
            initial_state={
                "SessionInfo": {"Key": "B", "Type": "Practice", "Name": "Practice 1"},
                "SessionStatus": {"Status": "Started"},
                "TimingData": _timing_pair(
                    2,
                    first_position=1,
                    second_position=2,
                    first_gap="",
                    second_gap="+0.4",
                ),
            },
        )
        controller.session_manager._state = ReplayState.READY
        await controller.async_play()
        if action != "pause":
            await controller.async_pause()
        if action == "stop":
            await controller.async_seek_to_ms(10_000)
        listener_count = len(controller.session_manager._listeners)
        initial = await subscribe(2)
        assert initial["session_id"] == "B:Practice 1"
        assert initial["replay"]["state"] == (
            "playing" if action == "pause" else "paused"
        )
        assert initial["capabilities"]["telemetry_compare"] == "ready"
        if pending_frame:
            entry.runtime_data.live.bus.inject_message(
                "TimingData", {"Lines": {"1": {"NumberOfLaps": 3}}}
            )
        else:
            # Exercise control notification when no earlier frame or throttle
            # timer is waiting to incidentally publish the new state.
            await asyncio.sleep(0.11)

        if action == "natural":
            # Advance only the actual transport's playback clock. The real disk
            # reader then delivers its final Heartbeat and reaches natural EOF.
            monkeypatch.setattr(
                controller.transport, "_get_elapsed_playback_time", lambda: 120.0
            )
            await controller.async_resume()
            await asyncio.wait_for(controller._playback_task, 3)
        else:
            await getattr(controller, f"async_{action}")()

        expected_state = {"pause": "paused", "resume": "playing"}.get(action, "idle")

        async def receive_control_update():
            while True:
                message = await client.receive_json()
                assert message["id"] == 2 and message["type"] == "event"
                payload = message["event"]
                if payload["replay"]["state"] != expected_state:
                    continue
                if expected_state == "idle" and payload["session_id"] is not None:
                    continue
                return payload

        update = await asyncio.wait_for(receive_control_update(), 1)
        if expected_state == "idle":
            assert update["provider"] == "f1_live"
            assert update["replay"]["session_id"] is None
            assert update["timing"] == []
            assert update["drivers"] == []
            assert update["timeline"]["events"] == []
            assert update["capabilities"]["telemetry_compare"] == "load_replay_first"
        else:
            assert update["session_id"] == "B:Practice 1"
            assert update["replay"]["paused"] is (expected_state == "paused")
        assert retired_hub_listeners.isdisjoint(retired_manager._listeners)
        # A pending pre-Stop snapshot must never reappear after the clear.
        try:
            async with asyncio.timeout(0.15):
                while True:
                    later = (await client.receive_json())["event"]
                    assert later["replay"]["state"] == expected_state
                    if expected_state == "idle":
                        assert later["session_id"] is None
                        assert later["replay"]["session_id"] is None
                        assert later["timing"] == []
        except TimeoutError:
            pass
        await client.send_json(
            {"id": 3, "type": "unsubscribe_events", "subscription": 2}
        )
        acknowledgment = await client.receive_json()
        assert acknowledgment["id"] == 3 and acknowledgment["success"]
        await hass.async_block_till_done()
        assert len(controller.session_manager._listeners) == listener_count
    finally:
        await client.close()
        if entry.state == ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
