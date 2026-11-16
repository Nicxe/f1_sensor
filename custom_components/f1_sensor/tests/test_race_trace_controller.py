"""Race Trace provenance survives the actual replay catch-up/transport lifecycle."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import re
from unittest.mock import AsyncMock, Mock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor.analysis_websocket import (
    _analysis_hub,
    _AnalysisSubscription,
)
from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS
from custom_components.f1_sensor.live_window import LiveSessionSupervisor
from custom_components.f1_sensor.replay_mode import (
    ReplayIndex,
    ReplaySession,
    ReplayState,
)
from custom_components.f1_sensor.signalr import timing_source_payload


def _timing(lap):
    return {"Lines": {"4": {"NumberOfLaps": lap, "LastLapTime": {"Value": "1:30.000"}}}}


@pytest.mark.asyncio
@pytest.mark.parametrize("selection_change", ["session", "year"])
async def test_real_entry_first_play_rewind_and_live_keep_frame_bound_context(
    hass,
    enable_custom_integrations,
    aioclient_mock,
    monkeypatch,
    tmp_path,
    selection_change,
):
    # The test explicitly starts each transport to verify replay handoff ownership.
    monkeypatch.setattr(
        LiveSessionSupervisor, "_discover_live_window", AsyncMock(return_value=None)
    )
    aioclient_mock.get(
        re.compile(r"https://.*"),
        json={"Meetings": [], "MRData": {"RaceTable": {"Races": []}}},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        data={"sensor_name": "F1", "data_choice_version": 1},
        options={
            "operation_mode": "live",
            "enable_race_control": True,
            "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS - {"track_status"}),
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry.runtime_data
    registry = hass.data[DOMAIN][entry.entry_id]
    controller, bus = runtime.replay.controller, runtime.live.bus
    drivers, analysis = registry["drivers_coordinator"], runtime.analysis.store

    # Exercise the real start/reset/close methods without network or a file reader.
    starts = []
    native_stopped = asyncio.Event()

    async def offline_run():
        native = bus._transport_factory is None
        starts.append("native" if native else "replay")
        if bus._transport_factory is not None:
            bus._client = bus._create_client()
        try:
            await asyncio.Event().wait()
        finally:
            if native:
                native_stopped.set()

    monkeypatch.setattr(bus, "_run", offline_run)
    now = datetime(2025, 7, 6, tzinfo=UTC)
    selected = ReplaySession(
        2025,
        1277,
        "British Grand Prix",
        9947,
        "Race",
        "Race",
        "test/",
        now,
        now + timedelta(hours=2),
    )
    frames = [
        (1000, "TimingData", _timing(2)),
        (1500, "TrackStatus", {"Status": "4"}),
        (2000, "TimingData", _timing(3)),
        (2500, "TrackStatus", {"Status": "1"}),
        (3000, "TimingData", _timing(4)),
        (86000, "TimingData", _timing(21)),
        (87000, "TrackStatus", {"Status": "4"}),
        (88000, "TrackStatus", {"Status": "1"}),
        (89000, "TrackStatus", {"Status": "4"}),
        (90000, "TimingData", _timing(22)),
    ]
    path = tmp_path / "frames.jsonl"
    path.write_text(
        "".join(
            json.dumps({"t": t, "s": stream, "p": payload}) + "\n"
            for t, stream, payload in frames
        )
    )
    index = ReplayIndex(
        session_id=selected.unique_id,
        total_frames=len(frames),
        duration_ms=120000,
        session_started_at_ms=0,
        frames_file=path,
        index_file=tmp_path / "index.json",
        initial_state={
            "SessionInfo": {"Key": 9947, "Type": "Race", "Name": "Race"},
            "SessionStatus": {"Status": "Started"},
        },
    )
    controller.session_manager._selected_session = selected
    controller.session_manager._loaded_index = index
    controller.session_manager._state = ReplayState.READY
    observed = []
    unsubscribe = bus.subscribe("TimingData", observed.append)
    replay_range = controller._replay_frames_range
    demand_checked = False

    async def flush_demand():
        for _ in range(5):
            await asyncio.sleep(0)

    async def replay_range_with_new_dashboard(*args, **kwargs):
        nonlocal demand_checked
        if not demand_checked:
            demand_checked = True
            assert controller.state is ReplayState.SEEKING
            assert controller.transport is None
            runtime.capabilities.requested_streams = frozenset()
            runtime.capabilities.stream_reasons.clear()
            subscription = _AnalysisSubscription(
                hass, Mock(), 1, _analysis_hub(hass, runtime, analysis), 0.1
            )
            await flush_demand()
            assert starts == (["native"] if selection_change == "session" else [])
            if selection_change == "session":
                assert native_stopped.is_set()
            subscription.unsubscribe()
            await flush_demand()
        # Other live owners may also request start during an initial rebuild
        # or a seek that still retains the previous replay factory.
        previous_starts = list(starts)
        await bus.start()
        await flush_demand()
        assert starts == previous_starts
        assert bus._running is False
        await replay_range(*args, **kwargs)

    monkeypatch.setattr(
        controller, "_replay_frames_range", replay_range_with_new_dashboard
    )
    try:
        if selection_change == "session":
            await bus.start()
            await flush_demand()
        await controller.async_seek_to_position(3)
        assert controller.state is ReplayState.READY
        await controller.async_play()
        observation = drivers.data["race_trace_observation"]
        assert observation["status"] == "ready"
        assert observation["context"]["entry_id"] == entry.entry_id
        assert observation["context"]["source"] == "replay"
        assert observation["context"]["session_id"] == selected.unique_id
        markers = analysis.snapshot()["race_trace_markers"]
        assert len(markers["events"]) == 2
        assert markers["context"] == observation["context"]
        assert bus.consumed_observation(observed[-1], 0)["status"] == "ready"
        for state in (ReplayState.PLAYING, ReplayState.PAUSED):
            if state is ReplayState.PAUSED:
                await controller.async_pause()
            transport = controller.transport
            subscription = _AnalysisSubscription(
                hass, Mock(), 2, _analysis_hub(hass, runtime, analysis), 0.1
            )
            await flush_demand()
            subscription.unsubscribe()
            await flush_demand()
            assert controller.transport is transport
            assert transport._closed is False
            assert bus._running is True
            assert controller.state is state
        close_transport = transport.close

        async def close_with_pending_start():
            await close_transport()
            if controller.state is ReplayState.SEEKING:
                previous_starts = list(starts)
                await bus.start()
                await flush_demand()
                assert starts == previous_starts

        monkeypatch.setattr(transport, "close", close_with_pending_start)
        await controller.async_seek_to_position(3.1)
        assert controller.state is ReplayState.PAUSED
        assert (
            drivers.data["race_trace_observation"]["context"] == observation["context"]
        )
        assert analysis.snapshot()["race_trace_markers"]["events"] == markers["events"]
        old_frame = timing_source_payload("TimingData", _timing(5), source_time=4)
        bus.inject_message("TimingData", old_frame)
        replay_frame = bus.get_last_payload("TimingData")
        assert (
            drivers.data["race_trace_observation"]["context"] == observation["context"]
        )
        assert analysis.snapshot()["race_trace_markers"]["events"] == markers["events"]
        await controller.async_seek_to_position(2)
        rewound = drivers.data["race_trace_observation"]
        assert rewound["status"] == "ready"
        assert (
            rewound["context"]["source_epoch"] != observation["context"]["source_epoch"]
        )
        assert len(analysis.snapshot()["race_trace_markers"]["events"]) == 1
        assert bus.consumed_observation(replay_frame, 0)["status"] == "pending"
        bus.inject_message(
            "TimingData", timing_source_payload("TimingData", _timing(4), source_time=3)
        )
        assert drivers.data["race_trace_observation"]["context"] == rewound["context"]
        assert len(analysis.snapshot()["race_trace_markers"]["events"]) == 1
        rewound_frame = bus.get_last_payload("TimingData")
        index.seek_checkpoints = [
            {
                "t": 85000,
                "state": {
                    **index.initial_state,
                    "TimingData": _timing(20),
                    "TrackStatus": {"Status": "4"},
                },
            }
        ]
        await controller.async_seek_to_position(90)
        rebuilt = drivers.data["race_trace_observation"]
        assert rebuilt["status"] == "ready"
        assert rebuilt["context"]["source_epoch"] != rewound["context"]["source_epoch"]
        checkpoint_events = analysis.snapshot()["race_trace_markers"]["events"]
        assert [(item["kind"], item["phase"]) for item in checkpoint_events] == [
            ("sc", "start")
        ]
        assert checkpoint_events[0]["reference_anchors"]["4"]["lap_number"] == 21
        assert (
            checkpoint_events[0]["reference_anchors"]["4"]["observation_cursor"][
                "source_time_ms"
            ]
            == 86000
        )
        assert bus.consumed_observation(rewound_frame, 0)["status"] == "pending"
        if selection_change == "session":
            other = replace(selected, session_key=9948, session_name="Sprint")
            controller.session_manager._available_sessions = [selected, other]
            await controller.session_manager.async_select_session(other.unique_id)
        else:
            await controller.session_manager.async_set_year(2024)
        # Selecting another archive does not stop A's existing transport yet.
        # A late A frame must not be attributed to the new dropdown selection.
        bus.inject_message(
            "TimingData", timing_source_payload("TimingData", _timing(5), source_time=4)
        )
        bus.inject_message(
            "TrackStatus",
            timing_source_payload("TrackStatus", {"Status": "6"}, source_time=4.1),
        )
        assert drivers.data["race_trace_observation"]["status"] == "ready"
        assert (
            drivers.data["race_trace_observation"]["context"]["session_id"]
            == selected.unique_id
        )
        assert (
            analysis.snapshot()["race_trace_markers"]["context"]["session_id"]
            == selected.unique_id
        )
        assert controller.replay_active is True
        assert controller.active_session_id == selected.unique_id
        if selection_change == "session":

            async def load_other_session():
                assert controller.transport is None
                assert controller.replay_active is False
                controller.session_manager._loaded_index = replace(
                    index,
                    session_id=other.unique_id,
                    seek_checkpoints=None,
                    initial_state={
                        "SessionInfo": {
                            "Key": other.session_key,
                            "Type": "Race",
                            "Name": "Race",
                        },
                        "SessionStatus": {"Status": "Started"},
                    },
                )
                controller.session_manager._state = ReplayState.READY

            monkeypatch.setattr(
                controller.session_manager, "async_load_session", load_other_session
            )
            await controller.async_prepare_and_load_session()
            await controller.async_seek_to_position(3)
            await controller.async_play()
            assert (
                drivers.data["race_trace_observation"]["context"]["session_id"]
                == other.unique_id
            )
            assert (
                analysis.snapshot()["race_trace_markers"]["context"]["session_id"]
                == other.unique_id
            )
            assert bus.consumed_observation(replay_frame, 0)["status"] == "pending"
        await controller.async_stop()
        assert controller.replay_active is False
        assert controller.active_session_id is None
        registry["live_state"].set_state(True, "live-Race")
        bus.inject_message("SessionInfo", {"Key": 9999, "Type": "Race", "Name": "Race"})
        bus.inject_message(
            "TimingData",
            timing_source_payload(
                "TimingData", _timing(2), source_utc="2025-07-06T14:00:00Z"
            ),
        )
        live = drivers.data["race_trace_observation"]
        assert live["status"] == "ready"
        assert live["context"]["source"] == "live"
        assert live["context"]["session_id"] == "9999"
        assert live["context"]["source_epoch"] != rewound["context"]["source_epoch"]
        assert bus.consumed_observation(replay_frame, 0)["status"] == "pending"
    finally:
        unsubscribe()
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
