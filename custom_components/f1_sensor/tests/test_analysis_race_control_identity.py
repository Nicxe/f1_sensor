"""Republished Race Control messages remain one revisioned analysis event."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import f1_sensor as f1
from custom_components.f1_sensor import _RC_LOG_EVENT
from custom_components.f1_sensor.analysis import (
    MAX_TIMELINE_EVENTS,
    Phase4AnalysisStore,
)
from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS
from custom_components.f1_sensor.history import LapAnalysisStore
from custom_components.f1_sensor.live_delay import LiveDelayController
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager
from custom_components.f1_sensor.replay_mode import (
    ReplayIndex,
    ReplaySession,
    ReplaySessionManager,
    ReplayState,
)
from custom_components.f1_sensor.signalr import LiveBus

FIXTURE = Path(__file__).parent / "fixtures/race_control_fp3_republished.json"
MESSAGE = {
    "Utc": "2026-11-07T14:15:06",
    "Category": "Flag",
    "Flag": "YELLOW",
    "Scope": "Sector",
    "Sector": 1,
    "Message": "YELLOW FLAG",
}


def _race_control_events(store):
    return [
        event
        for event in store.snapshot()["timeline"]["events"]
        if "RaceControlMessages" in event["supporting_signals"]
    ]


@pytest.fixture
async def pipeline(hass, monkeypatch):
    """Use actual transport decoding, delay and stores without opening a socket."""
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
    state = LiveAvailabilityTracker()
    state.set_state(True, "live")
    manager = NoSpoilerModeManager(hass)
    monkeypatch.setattr(manager._store, "async_save", AsyncMock())
    hass.data.setdefault(DOMAIN, {})["no_spoiler_manager"] = manager
    delay = LiveDelayController(hass, "entry")
    raw = LiveBus(hass, None, monotonic=lambda: clock.value)
    raw.configure_observations("entry", delay, lambda: None)
    delayed = f1._DelayedAnalysisBus(hass, raw, 0, delay, state)
    laps = LapAnalysisStore(delayed, source_provider=lambda: "f1_live")
    analysis = Phase4AnalysisStore(delayed, laps, source_provider=lambda: "f1_live")

    def emit(payload, source_time=None):
        args = ["RaceControlMessages", deepcopy(payload)]
        if source_time:
            args.append(source_time)
        raw._process_payload({"M": [{"M": "feed", "A": args}]})

    def snapshot(payload):
        raw._process_payload({"R": {"RaceControlMessages": deepcopy(payload)}})

    raw._dispatch("SessionInfo", {"Key": "fp3", "Name": "Practice 3"})
    yield SimpleNamespace(
        raw=raw,
        delayed=delayed,
        laps=laps,
        analysis=analysis,
        delay=delay,
        manager=manager,
        state=state,
        clock=clock,
        emit=emit,
        snapshot=snapshot,
    )
    await analysis.async_close()
    await laps.async_close()
    await delayed.async_close()
    await delay.async_close()
    await raw.async_close()


@pytest.fixture
async def loaded_entry(hass, enable_custom_integrations, aioclient_mock, freezer):
    """Set up and unload the real integration with external HTTP mocked."""
    freezer.move_to("2026-11-07T14:15:00+00:00")
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
            "live_delay_seconds": 0,
            "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS - {"race_control"}),
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    try:
        yield entry
    finally:
        if entry.state is ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)


async def test_recorded_fp3_republication_matches_sensor_and_log(hass, loaded_entry):
    """Exercise real config-entry wiring with unmodified recorded FP3 payloads."""
    case = json.loads(FIXTURE.read_text())
    entry = loaded_entry
    delivered = []

    @callback
    def record_event(event):
        delivered.append(event.data)

    unsubscribe = hass.bus.async_listen(_RC_LOG_EVENT, record_event)
    try:
        registry = hass.data[DOMAIN][entry.entry_id]
        registry["live_state"].set_state(True, "live")
        bus = registry["live_bus"]
        analysis = registry["phase4_analysis_store"]
        bus._dispatch("SessionInfo", case["session"])
        for frame in case["frames"][:2]:
            bus._dispatch("RaceControlMessages", deepcopy(frame))
        await hass.async_block_till_done()
        originals = _race_control_events(analysis)
        assert len(originals) == 2
        for frame in case["frames"][2:]:
            bus._dispatch("RaceControlMessages", deepcopy(frame))
        await hass.async_block_till_done()
        assert len(delivered) == 2
        assert len(registry["race_control_log_store"].get_items()) == 2
        assert _race_control_events(analysis) == originals
        assert {event["occurred_at"] for event in originals} == {
            "2026-11-07T14:15:06Z",
            "2026-11-07T14:15:20Z",
        }
    finally:
        unsubscribe()


@pytest.mark.parametrize(
    "payload",
    [
        {"Messages": [MESSAGE]},
        {"Messages": {"99": MESSAGE}},
        {"Messages": {"99": {**MESSAGE, "Id": "new-source-id"}}},
        {"Messages": {"99": {**MESSAGE, "id": 99}}},
        {"Messages": {MESSAGE["Utc"]: MESSAGE}},
        {"Messages": {"99": {**MESSAGE, "Utc": MESSAGE["Utc"] + "Z"}}},
    ],
    ids=["list", "new-index", "Id", "id", "checkpoint-key", "explicit-utc-zone"],
)
async def test_republication_ignores_transport_identity(pipeline, payload):
    pipeline.emit({"Messages": {"1": MESSAGE}})
    original = _race_control_events(pipeline.analysis)
    pipeline.emit(payload)
    assert _race_control_events(pipeline.analysis) == original


@pytest.mark.parametrize(
    "changed",
    [
        {"Utc": "2026-11-07T14:15:07"},
        {"Category": "Other"},
        {"Flag": "CLEAR"},
        {"Scope": "Track"},
        {"Sector": 2},
        {"RacingNumber": 4},
        {"CarNumber": 4},
        {"Status": "ENDING"},
        {"Mode": "VIRTUAL SAFETY CAR"},
        {"Message": "DOUBLE YELLOW FLAG"},
    ],
)
@pytest.mark.parametrize("source_key", ["1", "2"])
async def test_distinct_incidents_are_not_collapsed(pipeline, changed, source_key):
    pipeline.emit({"Messages": {"1": MESSAGE}})
    pipeline.emit({"Messages": {source_key: {**MESSAGE, **changed}}})
    events = _race_control_events(pipeline.analysis)
    assert len(events) == 2
    assert events[0]["event_id"] != events[1]["event_id"]


async def test_submicrosecond_event_times_remain_distinct(pipeline):
    for key, fraction in enumerate(("1234561", "1234562")):
        pipeline.emit(
            {
                "Messages": {
                    str(key): {**MESSAGE, "Utc": f"2026-11-07T14:15:06.{fraction}"}
                }
            }
        )
    events = _race_control_events(pipeline.analysis)
    assert len(events) == 2
    assert {event["occurred_at"] for event in events} == {
        "2026-11-07T14:15:06.1234561Z",
        "2026-11-07T14:15:06.1234562Z",
    }


@pytest.mark.parametrize("utc", [None, "", "invalid", "2026-11-07"])
async def test_unverifiable_time_does_not_merge_new_source_indices(pipeline, utc):
    message = {**MESSAGE, "Utc": utc}
    pipeline.emit({"Messages": {"1": message}})
    first = _race_control_events(pipeline.analysis)
    pipeline.emit({"Messages": {"1": message}})
    assert _race_control_events(pipeline.analysis) == first
    pipeline.emit({"Messages": {"2": message}})
    events = _race_control_events(pipeline.analysis)
    assert len(events) == 2
    assert all(event["occurred_at"] is None for event in events)


@pytest.mark.parametrize("delivery", ["snapshot", "new-alias"])
async def test_old_original_cannot_undo_a_lap_correction(pipeline, delivery):
    original = {**MESSAGE, "Lap": 2}
    corrected = {**MESSAGE, "Lap": 3}
    pipeline.emit({"Messages": {"1": original}})
    first = _race_control_events(pipeline.analysis)[0]
    pipeline.emit({"Messages": {"1": corrected}})
    events = _race_control_events(pipeline.analysis)
    assert len(events) == 1
    assert events[0]["event_id"] == first["event_id"]
    assert events[0]["sequence"] == first["sequence"]
    assert events[0]["revision"] == first["revision"] + 1
    assert events[0]["lap_number"] == 3
    pipeline.emit({"Messages": {"1": corrected}})
    assert _race_control_events(pipeline.analysis) == events
    if delivery == "snapshot":
        pipeline.snapshot({"Messages": {"1": original}})
    else:
        pipeline.emit({"Messages": {"99": original}})
    assert _race_control_events(pipeline.analysis) == events
    # A fresh correction from the established source is still a real revision.
    pipeline.emit({"Messages": {"1": {**MESSAGE, "Lap": 4}}})
    latest = _race_control_events(pipeline.analysis)
    assert len(latest) == 1
    assert latest[0]["event_id"] == first["event_id"]
    assert latest[0]["revision"] == events[0]["revision"] + 1
    assert latest[0]["lap_number"] == 4


@pytest.mark.parametrize("snapshot_key", ["1", MESSAGE["Utc"]])
async def test_snapshot_first_does_not_grant_stale_alias_correction_ownership(
    pipeline, snapshot_key
):
    corrected = {**MESSAGE, "Lap": 3}
    pipeline.snapshot({"Messages": {snapshot_key: corrected}})
    original = _race_control_events(pipeline.analysis)
    assert len(original) == 1
    assert original[0]["lap_number"] == 3
    assert original[0]["focus_observation"] is None
    pipeline.emit({"Messages": {"99": {**MESSAGE, "Lap": 2}}})
    assert _race_control_events(pipeline.analysis) == original
    # A timestamp checkpoint has no transport owner. Matching metadata allows
    # the real stream row to establish ownership before a fresh correction.
    pipeline.emit({"Messages": {"1": corrected}})
    assert _race_control_events(pipeline.analysis) == original
    pipeline.emit({"Messages": {"1": {**MESSAGE, "Lap": 4}}})
    events = _race_control_events(pipeline.analysis)
    assert len(events) == 1
    assert events[0]["event_id"] == original[0]["event_id"]
    assert events[0]["sequence"] == original[0]["sequence"]
    assert events[0]["revision"] == original[0]["revision"] + 1
    assert events[0]["lap_number"] == 4
    assert events[0]["focus_observation"] is None


async def test_republished_message_keeps_original_focus_anchor(pipeline):
    pipeline.emit({"Messages": {"1": MESSAGE}}, "2026-11-07T14:15:10Z")
    original = _race_control_events(pipeline.analysis)[0]
    assert original["focus_observation"]["status"] == "ready"
    pipeline.emit({"Messages": {"2": MESSAGE}}, "2026-11-07T14:18:10Z")
    assert _race_control_events(pipeline.analysis) == [original]
    pipeline.snapshot({"Messages": {"1": MESSAGE, "2": MESSAGE}})
    assert _race_control_events(pipeline.analysis) == [original]


@pytest.mark.parametrize("boundary", ["delay", "source"])
async def test_republication_does_not_rebind_focus_after_context_change(
    pipeline, boundary
):
    pipeline.emit({"Messages": {"1": MESSAGE}}, "2026-11-07T14:15:10Z")
    original = _race_control_events(pipeline.analysis)[0]
    old_context = original["focus_observation"]["context"]
    if boundary == "delay":
        await pipeline.delay.async_set_delay(50)
        await pipeline.delay.async_set_delay(0)
    else:
        pipeline.raw.reset_for_replay()
        pipeline.raw._dispatch("SessionInfo", {"Key": "fp3", "Name": "Practice 3"})
    pipeline.emit({"Messages": {"2": MESSAGE}}, "2026-11-07T14:18:10Z")
    events = _race_control_events(pipeline.analysis)
    assert len(events) == 1
    assert events[0]["event_id"] == original["event_id"]
    focus = events[0]["focus_observation"]
    assert focus is None or focus["context"] == old_context
    pipeline.emit(
        {"Messages": {"3": {**MESSAGE, "Utc": "2026-11-07T14:18:11"}}},
        "2026-11-07T14:18:12Z",
    )
    latest = _race_control_events(pipeline.analysis)[-1]
    assert latest["focus_observation"]["status"] == "ready"
    assert latest["focus_observation"]["context"] != old_context


@pytest.mark.parametrize("delay_transition", ["unchanged", "flush", "increase"])
async def test_duplicate_reception_respects_delay_without_adding_events(
    pipeline, delay_transition
):
    pipeline.emit({"Messages": {"1": MESSAGE}})
    original = _race_control_events(pipeline.analysis)
    await pipeline.delay.async_set_delay(50)
    pipeline.emit({"Messages": {"2": MESSAGE}})
    assert _race_control_events(pipeline.analysis) == original
    if delay_transition == "flush":
        await pipeline.delay.async_set_delay(0)
    else:
        if delay_transition == "increase":
            await pipeline.delay.async_set_delay(100)
        pipeline.clock.value += pipeline.delay.current
        f1._drain_delayed_ingest_queue(pipeline.delayed)
    assert not pipeline.delayed._delay_queue
    assert _race_control_events(pipeline.analysis) == original


async def test_no_spoiler_snapshot_resumption_deduplicates_republished_history(
    pipeline,
):
    pipeline.emit({"Messages": {"1": MESSAGE}})
    original = _race_control_events(pipeline.analysis)
    await pipeline.manager.async_set_active(True)
    pipeline.state.set_state(False, "no-spoiler")
    pipeline.emit({"Messages": {"2": MESSAGE}})
    assert _race_control_events(pipeline.analysis) == original
    await pipeline.manager.async_set_active(False)
    pipeline.state.set_state(True, "live")
    for _ in range(2):
        pipeline.snapshot({"Messages": {"1": MESSAGE, "2": MESSAGE}})
        assert _race_control_events(pipeline.analysis) == original


async def test_no_spoiler_clears_old_focus_even_when_observation_context_is_reused(
    pipeline,
):
    pipeline.emit({"Messages": {"1": MESSAGE}}, "2026-11-07T14:15:10Z")
    original = _race_control_events(pipeline.analysis)[0]
    original_context = original["focus_observation"]["context"]
    assert original["focus_observation"]["status"] == "ready"
    epoch = pipeline.raw.observation_epoch
    await pipeline.manager.async_set_active(True)
    pipeline.state.set_state(False, "no-spoiler")
    protected = _race_control_events(pipeline.analysis)
    assert len(protected) == 1
    assert protected[0]["event_id"] == original["event_id"]
    assert protected[0]["focus_observation"] is None
    assert protected[0]["revision"] > original["revision"]
    await pipeline.manager.async_set_active(False)
    pipeline.state.set_state(True, "live")
    pipeline.snapshot({"Messages": {"1": MESSAGE, "2": MESSAGE}})
    assert _race_control_events(pipeline.analysis) == protected

    # A reconnect can reuse the bus epoch: context matching alone cannot protect
    # an old selected event once fresh timing/events make that context ready again.
    assert pipeline.raw.observation_epoch == epoch
    pipeline.raw._process_payload(
        {
            "M": [
                {
                    "M": "feed",
                    "A": [
                        "TimingData",
                        {"Lines": {"4": {"NumberOfLaps": 1, "Position": "1"}}},
                        "2026-11-07T14:18:10Z",
                    ],
                }
            ]
        }
    )
    markers = pipeline.analysis.snapshot()["race_trace_markers"]
    assert markers["status"] == "ready"
    assert markers["context"] == original_context
    assert _race_control_events(pipeline.analysis) == protected
    pipeline.emit(
        {"Messages": {"3": {**MESSAGE, "Utc": "2026-11-07T14:18:11"}}},
        "2026-11-07T14:18:12Z",
    )
    events = _race_control_events(pipeline.analysis)
    assert len(events) == 2
    assert events[1]["focus_observation"]["status"] == "ready"
    assert events[1]["focus_observation"]["context"] == original_context
    pipeline.emit({"Messages": {"2": MESSAGE}}, "2026-11-07T14:18:13Z")
    by_id = {
        event["event_id"]: event for event in _race_control_events(pipeline.analysis)
    }
    assert by_id[original["event_id"]] == protected[0]


async def test_replay_checkpoint_and_later_delta_share_semantic_identity(
    pipeline, hass
):
    case = json.loads(FIXTURE.read_text())
    manager = ReplaySessionManager(hass, "entry", async_get_clientsession(hass))
    checkpoint = {}
    for frame in case["frames"]:
        manager._merge_race_control_checkpoint_state(checkpoint, frame)
    # Real checkpoint merging changes list positions to timestamp-based keys.
    pipeline.snapshot(checkpoint["RaceControlMessages"])
    events = _race_control_events(pipeline.analysis)
    assert len(events) == 2
    for frame in case["frames"]:
        pipeline.emit(frame)
    assert _race_control_events(pipeline.analysis) == events


async def test_session_and_playback_resets_clear_deduplication_ownership(pipeline):
    pipeline.emit({"Messages": {"1": MESSAGE}})
    first = _race_control_events(pipeline.analysis)[0]
    pipeline.raw._dispatch("SessionInfo", {"Key": "q", "Name": "Qualifying"})
    assert not _race_control_events(pipeline.analysis)
    pipeline.emit({"Messages": {"2": MESSAGE}})
    second = _race_control_events(pipeline.analysis)[0]
    assert second["session_id"] != first["session_id"]
    assert second["event_id"] != first["event_id"]
    pipeline.delayed.reset_for_replay()
    pipeline.laps.reset_for_replay()
    pipeline.analysis.reset_for_replay()
    pipeline.raw.reset_for_replay()
    pipeline.raw._dispatch("SessionInfo", {"Key": "fp3", "Name": "Practice 3"})
    pipeline.emit({"Messages": {"2": MESSAGE}})
    rebuilt = _race_control_events(pipeline.analysis)
    assert len(rebuilt) == 1
    assert rebuilt[0]["revision"] == 1
    assert rebuilt[0]["session_id"] == first["session_id"]


async def test_evicted_message_can_be_observed_again_without_unbounded_history(
    pipeline,
):
    pipeline.emit({"Messages": {"1": MESSAGE}})
    first = _race_control_events(pipeline.analysis)[0]
    start = datetime.fromisoformat(MESSAGE["Utc"])
    for number in range(1, MAX_TIMELINE_EVENTS + 1):
        pipeline.emit(
            {
                "Messages": {
                    str(number + 1): {
                        **MESSAGE,
                        "Utc": (start + timedelta(seconds=number)).isoformat(),
                    }
                }
            }
        )
    retained = _race_control_events(pipeline.analysis)
    assert len(retained) == MAX_TIMELINE_EVENTS
    assert first["event_id"] not in {event["event_id"] for event in retained}
    pipeline.emit({"Messages": {"reloaded-old-event": MESSAGE}})
    restored = _race_control_events(pipeline.analysis)
    assert len(restored) == MAX_TIMELINE_EVENTS
    original_time = [
        event for event in restored if event["occurred_at"] == first["occurred_at"]
    ]
    assert len(original_time) == 1
    assert original_time[0]["revision"] == 1
    assert original_time[0]["sequence"] > max(event["sequence"] for event in retained)


async def test_real_replay_seek_checkpoint_and_rewind_keep_one_event_per_message(
    hass, loaded_entry, monkeypatch, tmp_path
):
    """Drive actual controller reset/catch-up paths with recorded RC frames."""
    case = json.loads(FIXTURE.read_text())
    runtime = loaded_entry.runtime_data
    bus, controller = runtime.live.bus, runtime.replay.controller
    analysis = runtime.analysis.store

    async def offline_run():
        if bus._transport_factory is not None:
            bus._client = bus._create_client()
        await asyncio.Event().wait()

    monkeypatch.setattr(bus, "_run", offline_run)
    now = datetime(2026, 11, 7, 14, 15, tzinfo=UTC)
    session = ReplaySession(
        2026,
        1299,
        "Sao Paulo Grand Prix",
        11407,
        "Practice 3",
        "Practice",
        "test/",
        now,
        now + timedelta(hours=2),
    )
    frames = [
        {"t": offset, "s": "RaceControlMessages", "p": frame}
        for offset, frame in zip(
            (5040, 19094, 184281, 184286), case["frames"], strict=True
        )
    ]
    path = tmp_path / "frames.jsonl"
    path.write_text("".join(json.dumps(frame) + "\n" for frame in frames))
    initial = {"SessionInfo": case["session"], "SessionStatus": {"Status": "Inactive"}}
    checkpoint = deepcopy(initial)
    for frame in case["frames"][:2]:
        controller.session_manager._merge_race_control_checkpoint_state(
            checkpoint, frame
        )
    index = ReplayIndex(
        session_id=session.unique_id,
        total_frames=len(frames),
        duration_ms=240000,
        session_started_at_ms=0,
        frames_file=path,
        index_file=tmp_path / "index.json",
        initial_state=initial,
        seek_checkpoints=[{"t": 20000, "state": checkpoint}],
    )
    manager = controller.session_manager
    manager._selected_session = session
    manager._loaded_index = index
    manager._state = ReplayState.READY
    try:
        await controller.async_seek_to_position(185)
        await controller.async_play()
        await controller.async_pause()
        events = _race_control_events(analysis)
        assert len(events) == 2
        assert all(event["provider"] == "replay" for event in events)
        assert {event["title"] for event in events} == {
            case["frames"][0]["Messages"][0]["Message"],
            case["frames"][1]["Messages"]["1"]["Message"],
        }

        # Rewind through a real checkpoint whose first message has a timestamp key.
        await controller.async_seek_to_position(30)
        rewound = _race_control_events(analysis)
        assert len(rewound) == 2
        assert all(event["revision"] == 1 for event in rewound)
        await controller.async_seek_to_position(185)
        assert _race_control_events(analysis) == rewound

        # A rewind before any message must drop the previous generation entirely.
        await controller.async_seek_to_position(1)
        assert not _race_control_events(analysis)
        await controller.async_seek_to_position(185)
        assert len(_race_control_events(analysis)) == 2
    finally:
        await controller.async_stop()
