"""Timing and marker snapshots share consumed frames, not publication clocks."""

from types import SimpleNamespace

import pytest

from custom_components import f1_sensor as f1
from custom_components.f1_sensor.analysis import Phase4AnalysisStore
from custom_components.f1_sensor.history import LapAnalysisStore
from custom_components.f1_sensor.live_data_models import DriverPositionsModel
from custom_components.f1_sensor.live_delay import LiveDelayController
from custom_components.f1_sensor.signalr import LiveBus, timing_source_payload


def _emit(bus, stream, payload, time=100.0, *, snapshot=False):
    bus._dispatch(
        stream,
        timing_source_payload(
            stream,
            payload,
            source_utc=f"2025-07-06T14:{int(time) // 60:02d}:{int(time) % 60:02d}Z",
            snapshot=snapshot,
        ),
    )


def _lap(number):
    return {
        "Lines": {"4": {"NumberOfLaps": number, "LastLapTime": {"Value": "1:30.000"}}}
    }


@pytest.mark.asyncio
async def test_driver_observation_advances_only_on_consumed_timing(hass, monkeypatch):
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
    delay = LiveDelayController(hass, "entry")
    bus = LiveBus(hass, None)
    bus.configure_observations("entry", delay, lambda: None)
    driver = f1.LiveDriversCoordinator(
        hass, SimpleNamespace(data={}), bus=bus, delay_controller=delay
    )
    unsubs = [
        bus.subscribe(stream, f1._wrap_delayed_handler(driver, handler))
        for stream, handler in (
            ("SessionInfo", driver._on_sessioninfo),
            ("TimingData", driver._on_timingdata),
            ("DriverList", driver._on_driverlist),
        )
    ]
    try:
        _emit(bus, "SessionInfo", {"Key": 123, "Type": "Race"})
        _emit(bus, "TimingData", _lap(2))
        first = driver.data["race_trace_observation"]
        assert first["status"] == "ready"
        _emit(bus, "DriverList", {"4": {"RacingNumber": "4", "Tla": "NOR"}}, 110)
        assert driver.data["race_trace_observation"] == first
        _emit(bus, "TimingData", _lap(2), 120)
        assert (
            driver.data["race_trace_observation"]["timing_as_of"]["sequence"]
            > first["timing_as_of"]["sequence"]
        )
        model = DriverPositionsModel(driver, None, "entry", None)
        model.hass = hass
        model._update_from_coordinator()
        assert (
            model.extra_state_attributes["race_trace_observation"]
            == driver.data["race_trace_observation"]
        )
        await delay.async_set_delay(30)
        assert driver.data["race_trace_observation"]["status"] == "pending"
        _emit(bus, "TimingData", _lap(3), 130)
        await delay.async_set_delay(0)
        # The queued frame was received in the previous delay epoch.
        assert driver.data["race_trace_observation"]["status"] == "pending"
        _emit(bus, "TimingData", _lap(3), 140)
        assert driver.data["race_trace_observation"]["status"] == "ready"
        assert driver.data["race_trace_observation"]["context"]["delay_epoch"] == 2
        driver.reset_for_replay()
        assert driver.data["race_trace_observation"]["status"] == "pending"
    finally:
        for unsubscribe in unsubs:
            unsubscribe()
        await driver.async_close()
        await delay.async_close()


@pytest.mark.asyncio
@pytest.mark.parametrize("analysis_first", [True, False])
async def test_markers_freeze_actual_reference_lap_and_delay_never_retags(
    hass, monkeypatch, analysis_first
):
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
    delay = LiveDelayController(hass, "entry")
    bus = LiveBus(hass, None)
    bus.configure_observations("entry", delay, lambda: None)
    delayed = f1._DelayedAnalysisBus(hass, bus, 0, delay, None)
    laps = LapAnalysisStore(delayed, source_provider=lambda: "f1_live")
    analysis = Phase4AnalysisStore(delayed, laps, source_provider=lambda: "f1_live")
    driver = f1.LiveDriversCoordinator(
        hass, SimpleNamespace(data={}), bus=bus, delay_controller=delay
    )
    driver_unsub = bus.subscribe(
        "TimingData", f1._wrap_delayed_handler(driver, driver._on_timingdata)
    )
    if not analysis_first:
        bus._subs["TimingData"].reverse()
        delay._listeners.reverse()
    try:
        _emit(bus, "SessionInfo", {"Key": 123, "Type": "Race"})
        _emit(bus, "TimingData", _lap(2), 100)
        _emit(bus, "TrackStatus", {"Status": "4", "Message": "SC"}, 101)
        markers = analysis.snapshot()["race_trace_markers"]
        assert markers["context"] == driver.data["race_trace_observation"]["context"]
        event = markers["events"][0]
        assert event["reference_anchors"]["4"]["lap_number"] == 2
        assert (
            event["observation_cursor"]["sequence"]
            > driver.data["race_trace_observation"]["timing_as_of"]["sequence"]
        )
        _emit(bus, "TimingData", _lap(3), 102)
        assert analysis.snapshot()["race_trace_markers"]["events"][0] == event
        _emit(bus, "TrackStatus", {"Status": "1"}, 103)
        _emit(bus, "TrackStatus", {"Status": "4"}, 104)
        events = analysis.snapshot()["race_trace_markers"]["events"]
        assert [item["phase"] for item in events] == ["start", "end", "start"]
        assert len({item["event_id"] for item in events}) == 3
        await delay.async_set_delay(30)
        assert analysis.snapshot()["race_trace_markers"]["status"] == "pending"
        assert analysis.snapshot()["race_trace_markers"]["events"] == []
        _emit(bus, "TimingData", _lap(4), 110)
        _emit(bus, "TrackStatus", {"Status": "6"}, 111)
        await delay.async_set_delay(0)
        assert analysis.snapshot()["race_trace_markers"]["status"] == "pending"
        _emit(bus, "TrackStatus", {"Status": "1"}, 112)
        assert analysis.snapshot()["race_trace_markers"]["events"] == []
        _emit(bus, "TimingData", _lap(5), 120)
        # A backdated status cannot use the later timing anchor.
        _emit(bus, "TrackStatus", {"Status": "6"}, 119)
        assert (
            analysis.snapshot()["race_trace_markers"]["events"][-1]["reference_anchors"]
            == {}
        )
    finally:
        driver_unsub()
        await driver.async_close()
        await analysis.async_close()
        await laps.async_close()
        await delayed.async_close()
        await delay.async_close()


@pytest.fixture
async def marker_runtime(hass):
    delay = LiveDelayController(hass, "entry")
    bus = LiveBus(hass, None)
    bus.configure_observations("entry", delay, lambda: None)
    delayed = f1._DelayedAnalysisBus(hass, bus, 0, delay, None)
    laps = LapAnalysisStore(delayed, source_provider=lambda: "f1_live")
    analysis = Phase4AnalysisStore(delayed, laps, source_provider=lambda: "f1_live")
    _emit(bus, "SessionInfo", {"SessionKey": 123, "Type": "Race"})
    yield bus, analysis
    await analysis.async_close()
    await laps.async_close()
    await delayed.async_close()
    await delay.async_close()
    assert not any(bus._subs.values())
    assert delayed._delay_queue_handle is None
    assert delayed._observation_reset_listeners == []


@pytest.mark.parametrize(
    "statuses,expected",
    [
        (["6", "7", "7", "1"], [("vsc", "start"), ("vsc", "ending"), ("vsc", "end")]),
        (
            ["4", "5", "1"],
            [("sc", "start"), ("red_flag", "start"), ("red_flag", "end")],
        ),
        (["4", "6", "1"], [("sc", "start"), ("vsc", "start"), ("vsc", "end")]),
        (["4", "1", "4"], [("sc", "start"), ("sc", "end"), ("sc", "start")]),
    ],
)
async def test_global_phase_semantics_and_same_timestamp_distinct_events(
    marker_runtime, statuses, expected
):
    bus, analysis = marker_runtime
    _emit(bus, "TimingData", _lap(2))
    for status in statuses:
        _emit(bus, "TrackStatus", {"Status": status}, 101)
    events = analysis.snapshot()["race_trace_markers"]["events"]
    assert [(event["kind"], event["phase"]) for event in events] == expected
    assert len({event["event_id"] for event in events}) == len(expected)


async def test_pit_revision_replaces_lap_and_invalidates_old_anchor(marker_runtime):
    bus, analysis = marker_runtime

    def pit(lap):
        return {
            "PitTimes": {
                "4": {
                    "0": {
                        "Timestamp": "2025-07-06T14:01:40Z",
                        "PitStop": {
                            "RacingNumber": "4",
                            "Lap": lap,
                            "Duration": "20.5",
                        },
                    }
                }
            }
        }

    _emit(bus, "PitStopSeries", pit(11))
    first = analysis.snapshot()["race_trace_markers"]["events"][0]
    _emit(bus, "PitStopSeries", pit(11), 101)
    assert analysis.snapshot()["race_trace_markers"]["events"] == [first]
    _emit(bus, "PitStopSeries", pit(12), 102)
    corrected = analysis.snapshot()["race_trace_markers"]["events"][0]
    assert corrected["event_id"] == first["event_id"]
    assert corrected["revision"] == first["revision"] + 1
    assert corrected["lap_number"] == 12
    _emit(bus, "PitStopSeries", pit(None), 103)
    invalid = analysis.snapshot()["race_trace_markers"]["events"][0]
    assert invalid["event_id"] == first["event_id"]
    assert invalid["revision"] == corrected["revision"] + 1
    assert invalid["lap_number"] is None


async def test_checkpoint_laps_and_backdated_provider_utc_cannot_anchor(marker_runtime):
    bus, analysis = marker_runtime
    _emit(bus, "TimingData", _lap(20), snapshot=True)
    _emit(bus, "TrackStatus", {"Status": "4"}, 110)
    assert (
        analysis.snapshot()["race_trace_markers"]["events"][0]["reference_anchors"]
        == {}
    )
    _emit(bus, "TimingData", _lap(21), 120)
    _emit(bus, "TrackStatus", {"Status": "5", "Utc": "2025-07-06T14:01:59Z"}, 121)
    assert (
        analysis.snapshot()["race_trace_markers"]["events"][-1]["reference_anchors"]
        == {}
    )
    _emit(bus, "TrackStatus", {"Status": "1"}, 122)
    assert (
        analysis.snapshot()["race_trace_markers"]["events"][-1]["reference_anchors"][
            "4"
        ]["lap_number"]
        == 21
    )


@pytest.mark.parametrize(
    "number,value",
    [
        (True, "1:30.000"),
        (2.5, "1:30.000"),
        (501, "1:30.000"),
        (2, "garbage"),
        (2, "0:00.000"),
        (2, "NaN"),
    ],
)
async def test_invalid_lap_pair_cannot_be_a_confirmed_marker_anchor(
    marker_runtime, number, value
):
    bus, analysis = marker_runtime
    _emit(
        bus,
        "TimingData",
        {"Lines": {"4": {"NumberOfLaps": number, "LastLapTime": {"Value": value}}}},
    )
    _emit(bus, "TrackStatus", {"Status": "4"}, 101)
    assert (
        analysis.snapshot()["race_trace_markers"]["events"][0]["reference_anchors"]
        == {}
    )


@pytest.mark.parametrize(
    "inner",
    [
        {"RacingNumber": "81", "Lap": 11},
        {"RacingNumber": "4", "Lap": 0},
        {"RacingNumber": "4", "Lap": None},
    ],
)
async def test_conflicting_pit_identity_or_explicit_invalid_lap_vetoes_old_marker(
    marker_runtime, inner
):
    bus, analysis = marker_runtime
    for row in ({"RacingNumber": "4", "Lap": 11}, inner):
        _emit(
            bus,
            "PitStopSeries",
            {"PitTimes": {"4": {"0": {"Lap": 11, "PitStop": row}}}},
        )
    events = analysis.snapshot()["race_trace_markers"]["events"]
    assert len(events) == 1
    assert events[0]["lap_number"] is None
    assert events[0]["revision"] == 2


async def test_later_unrelated_analysis_input_does_not_move_marker_as_of(
    marker_runtime,
):
    bus, analysis = marker_runtime
    _emit(bus, "TimingData", _lap(2))
    _emit(bus, "TrackStatus", {"Status": "4"}, 101)
    first = analysis.snapshot()["race_trace_markers"]
    _emit(
        bus,
        "TimingAppData",
        {"Lines": {"4": {"Stints": {"0": {"Compound": "SOFT"}}}}},
        130,
    )
    assert analysis.snapshot()["race_trace_markers"]["as_of"] == first["as_of"]


async def test_snapshot_active_flag_does_not_invent_a_later_start(marker_runtime):
    bus, analysis = marker_runtime
    _emit(bus, "TrackStatus", {"Status": "4"}, snapshot=True)
    _emit(bus, "TimingData", _lap(20), 120)
    _emit(bus, "TrackStatus", {"Status": "4"}, 121)
    assert analysis.snapshot()["race_trace_markers"]["events"] == []
    _emit(bus, "TrackStatus", {"Status": "1"}, 122)
    _emit(bus, "TrackStatus", {"Status": "4"}, 123)
    events = analysis.snapshot()["race_trace_markers"]["events"]
    assert [(item["kind"], item["phase"]) for item in events] == [("sc", "start")]
    assert events[0]["reference_anchors"]["4"]["lap_number"] == 20


async def test_analysis_serialization_does_not_retag_marker_context(marker_runtime):
    from custom_components.f1_sensor.analysis_websocket import _analysis_payload

    bus, analysis = marker_runtime
    _emit(bus, "TimingData", _lap(2))
    _emit(bus, "TrackStatus", {"Status": "4"}, 101)
    expected = analysis.snapshot()["race_trace_markers"]
    clock = {"position_ms": 999999, "paused": True}
    replay = SimpleNamespace(
        get_playback_status=lambda: clock,
        get_planned_playback_details=lambda: None,
        session_manager=SimpleNamespace(
            get_loaded_index=lambda: SimpleNamespace(session_id="different-replay")
        ),
        state=SimpleNamespace(value="paused"),
    )
    runtime = SimpleNamespace(
        analysis=SimpleNamespace(store=analysis),
        live=None,
        replay=SimpleNamespace(controller=replay),
        capabilities=SimpleNamespace(requested_streams=[], active_streams=[]),
    )
    first = _analysis_payload(runtime)
    assert first["race_trace_markers"] == expected
    assert first["race_trace_markers"]["context"]["source"] == "live"
    clock["position_ms"] = 1
    assert _analysis_payload(runtime)["race_trace_markers"] == expected


async def test_cleared_driver_projection_keeps_explicit_pending_observation(hass):
    driver = f1.LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    model = DriverPositionsModel(driver, None, "entry", None)
    model._clear_state()
    assert model.extra_state_attributes["race_trace_observation"]["status"] == "pending"
    assert model.extra_state_attributes["race_trace_observation"]["context"] is None
    await driver.async_close()


@pytest.mark.asyncio
async def test_race_control_focus_provenance_belongs_to_consumed_raw_event(hass):
    delay = LiveDelayController(hass, "entry")
    bus = LiveBus(hass, None)
    bus.configure_observations("entry", delay, lambda: None)
    delayed = f1._DelayedAnalysisBus(hass, bus, 0, delay, None)
    laps = LapAnalysisStore(delayed, source_provider=lambda: "f1_live")
    analysis = Phase4AnalysisStore(delayed, laps, source_provider=lambda: "f1_live")
    try:
        _emit(bus, "SessionInfo", {"Key": 123, "Type": "Race"})
        _emit(bus, "TimingData", _lap(2), 100)
        marker_as_of = analysis.snapshot()["race_trace_markers"]["as_of"]
        _emit(
            bus,
            "RaceControlMessages",
            {"Messages": [{"Message": "CAR 18 LAP 14 DELETED"}]},
            101,
        )
        assert analysis.snapshot()["race_trace_markers"]["as_of"] == marker_as_of
        event = analysis.snapshot()["timeline"]["events"][-1]
        assert event["focus_observation"]["status"] == "ready"
        assert event["focus_observation"]["context"]["session_id"] == "123"
        assert event["focus_observation"]["timing_as_of"]["time_domain"] == "utc"
        _emit(
            bus,
            "RaceControlMessages",
            {"Messages": [{"Message": "CAR 18 LAP 14 DELETED"}]},
            102,
        )
        assert analysis.snapshot()["timeline"]["events"][-1] == event
        await delay.async_set_delay(30)
        assert event["focus_observation"]["context"]["delay_epoch"] == 0
    finally:
        await analysis.async_close()
        await laps.async_close()
        await delayed.async_close()
        await delay.async_close()


@pytest.mark.asyncio
async def test_track_marker_focus_uses_the_same_single_frame_as_its_marker(hass):
    delay = LiveDelayController(hass, "entry")
    bus = LiveBus(hass, None)
    bus.configure_observations("entry", delay, lambda: None)
    delayed = f1._DelayedAnalysisBus(hass, bus, 0, delay, None)
    laps = LapAnalysisStore(delayed, source_provider=lambda: "f1_live")
    analysis = Phase4AnalysisStore(delayed, laps, source_provider=lambda: "f1_live")
    try:
        _emit(bus, "SessionInfo", {"Key": 123, "Type": "Race"})
        _emit(bus, "TimingData", _lap(2), 100)
        _emit(bus, "TrackStatus", {"Status": "6", "Message": "VIRTUAL SAFETY CAR"}, 101)
        event = analysis.snapshot()["timeline"]["events"][-1]
        observation = event["focus_observation"]
        marker = analysis.snapshot()["race_trace_markers"]["events"][-1]
        assert observation["event_time_basis"] == "single_frame"
        assert observation["timing_as_of"] == marker["observation_cursor"]
        assert observation["context"]["token"] == marker["context_token"]
        assert event["occurred_at"] is None
    finally:
        await analysis.async_close()
        await laps.async_close()
        await delayed.async_close()
        await delay.async_close()


@pytest.mark.asyncio
async def test_pit_focus_requires_an_individual_source_utc(hass):
    delay = LiveDelayController(hass, "entry")
    bus = LiveBus(hass, None)
    bus.configure_observations("entry", delay, lambda: None)
    delayed = f1._DelayedAnalysisBus(hass, bus, 0, delay, None)
    laps = LapAnalysisStore(delayed, source_provider=lambda: "f1_live")
    analysis = Phase4AnalysisStore(delayed, laps, source_provider=lambda: "f1_live")
    try:
        _emit(bus, "SessionInfo", {"Key": 123, "Type": "Race"})
        _emit(bus, "TimingData", _lap(2), 100)
        _emit(bus, "PitStopSeries", {"PitTimes": {"4": {"0": {"Lap": 2}}}}, 101)
        event = analysis.snapshot()["timeline"]["events"][-1]
        assert event["focus_observation"] is None
        _emit(
            bus,
            "PitStopSeries",
            {"PitTimes": {"4": {"1": {"Lap": 3, "Utc": "2025-07-06T14:01:41"}}}},
            102,
        )
        event = analysis.snapshot()["timeline"]["events"][-1]
        assert event["focus_observation"]["event_time_basis"] == "utc_field"
        assert event["lap_number"] == 3
    finally:
        await analysis.async_close()
        await laps.async_close()
        await delayed.async_close()
        await delay.async_close()
