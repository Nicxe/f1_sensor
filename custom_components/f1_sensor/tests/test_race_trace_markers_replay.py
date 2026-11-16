"""Replay observations bind real-event shapes to explicit completed laps."""

from types import SimpleNamespace

import pytest

from custom_components import f1_sensor as f1
from custom_components.f1_sensor.analysis import Phase4AnalysisStore
from custom_components.f1_sensor.history import LapAnalysisStore
from custom_components.f1_sensor.live_delay import LiveDelayController
from custom_components.f1_sensor.signalr import LiveBus, timing_source_payload

SESSION_ID = "2025_1277_9947"


def _lap(driver, number, value=None):
    row = {"NumberOfLaps": number}
    if value is not None:
        row["LastLapTime"] = {"Value": value}
    return {"Lines": {driver: row}}


def _pit(driver, lap, timestamp):
    return {
        "PitTimes": {
            driver: [
                {
                    "Timestamp": timestamp,
                    "PitStop": {"RacingNumber": driver, "Lap": str(lap)},
                }
            ]
        }
    }


# Selected fields from Silverstone 2025 source observations. Millisecond offsets
# and lap-time pairs are retained; no local replay cache is required by this test.
FRAMES = (
    (0, "SessionInfo", {"Key": 9947, "Type": "Race", "Name": "Race"}),
    (3475956, "TimingData", _lap("81", 1)),
    (3477555, "TimingData", _lap("4", 1)),
    (3487014, "TrackStatus", {"Status": "6", "Message": "VSCDeployed"}),
    (3749181, "TimingData", _lap("81", 3, "2:17.795")),
    (3751365, "TimingData", _lap("4", 3, "2:17.443")),
    (3757206, "TrackStatus", {"Status": "7", "Message": "VSCEnding"}),
    (3770160, "TrackStatus", {"Status": "1", "Message": "AllClear"}),
    (3854681, "TimingData", _lap("81", 4, "1:45.828")),
    (3857081, "TimingData", _lap("4", 4, "1:45.751")),
    (3958175, "TrackStatus", {"Status": "6", "Message": "VSCDeployed"}),
    (4098769, "TimingData", _lap("81", 6, "2:19.626")),
    (4101443, "TimingData", _lap("4", 6, "2:19.233")),
    (4162963, "TrackStatus", {"Status": "7", "Message": "VSCEnding"}),
    (4176809, "TrackStatus", {"Status": "1", "Message": "AllClear"}),
    (4664436, "PitStopSeries", _pit("81", 11, "2025-07-06T14:25:25.048Z")),
    (4673122, "PitStopSeries", _pit("4", 11, "2025-07-06T14:25:33.734Z")),
    (
        8387072,
        "PitStopSeries",
        {
            "PitTimes": {
                "81": {
                    "1": {
                        "Timestamp": "2025-07-06T15:27:27.684Z",
                        "PitStop": {"RacingNumber": "81", "Lap": "43"},
                    }
                }
            }
        },
    ),
    (
        8476706,
        "PitStopSeries",
        {
            "PitTimes": {
                "4": {
                    "1": {
                        "Timestamp": "2025-07-06T15:28:57.318Z",
                        "PitStop": {"RacingNumber": "4", "Lap": "44"},
                    }
                }
            }
        },
    ),
)


@pytest.fixture
async def marker_replay(hass):
    delay = LiveDelayController(hass, "entry")
    bus = LiveBus(hass, None, transport_factory=lambda: None)
    bus.configure_observations("entry", delay, lambda: SESSION_ID)
    driver = f1.LiveDriversCoordinator(
        hass, SimpleNamespace(data={}), bus=bus, delay_controller=delay
    )
    unsubs = [
        bus.subscribe(stream, f1._wrap_delayed_handler(driver, handler))
        for stream, handler in (
            ("SessionInfo", driver._on_sessioninfo),
            ("TimingData", driver._on_timingdata),
            ("TimingAppData", driver._on_timingapp),
            ("TrackStatus", driver._on_trackstatus),
        )
    ]
    analysis_bus = f1._DelayedAnalysisBus(hass, bus, delay.current, delay, None)
    laps = LapAnalysisStore(analysis_bus, source_provider=lambda: "replay")
    analysis = Phase4AnalysisStore(analysis_bus, laps, source_provider=lambda: "replay")
    yield SimpleNamespace(bus=bus, driver=driver, analysis=analysis, delay=delay)
    await analysis.async_close()
    await laps.async_close()
    await analysis_bus.async_close()
    for unsubscribe in unsubs:
        unsubscribe()
    await driver.async_close()
    await delay.async_close()


def _feed(harness, frames=FRAMES):
    for offset, stream, payload in frames:
        harness.bus.inject_message(
            stream, timing_source_payload(stream, payload, source_time=offset / 1000)
        )


async def test_replay_vsc_events_use_observed_reference_laps_and_keep_ending_separate(
    marker_replay,
):
    harness = marker_replay
    _feed(harness)
    snapshot = harness.analysis.snapshot()["race_trace_markers"]
    events = [event for event in snapshot["events"] if event["kind"] == "vsc"]
    starts = [event for event in events if event["phase"] == "start"]
    assert len(starts) == 2
    assert not starts[0]["reference_anchors"].get("4")
    assert not starts[0]["reference_anchors"].get("81")
    second = events[events.index(starts[1]) :]
    for driver in ("4", "81"):
        assert [
            (event["phase"], event["reference_anchors"][driver]["lap_number"])
            for event in second
        ] == [("start", 4), ("ending", 6), ("end", 6)]
        assert all(
            event["reference_anchors"][driver]["basis"] == "confirmed_completed"
            for event in second
        )
    assert all("end_lap" not in event for event in events)


async def test_replay_pit_markers_keep_explicit_laps_and_source_provenance(
    marker_replay,
):
    harness = marker_replay
    _feed(harness)
    snapshot = harness.analysis.snapshot()["race_trace_markers"]
    pits = [event for event in snapshot["events"] if event["kind"] == "pit"]
    assert sorted(
        (str(event["driver_number"]), event["lap_number"]) for event in pits
    ) == [("4", 11), ("4", 44), ("81", 11), ("81", 43)]
    assert all(event["anchor_type"] == "driver_lap" for event in pits)
    context = snapshot["context"]
    timing = harness.driver.data["race_trace_observation"]
    assert context == timing["context"]
    assert context["source"] == "replay"
    assert context["session_id"] == SESSION_ID
    assert snapshot["as_of"]["sequence"] > timing["timing_as_of"]["sequence"]
    # A frontend must wait here: explicit late pits cannot advance the timing
    # barrier merely because analysis has received them.
    cursors = [event["observation_cursor"] for event in snapshot["events"]]
    assert all(cursor["time_domain"] == "replay_offset" for cursor in cursors)
    assert all(
        event["context_token"] == context["token"] for event in snapshot["events"]
    )
    assert [cursor["sequence"] for cursor in cursors] == sorted(
        cursor["sequence"] for cursor in cursors
    )
