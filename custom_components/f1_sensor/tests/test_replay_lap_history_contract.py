"""Replay rebuilds preserve the association evidence of the delivered laps."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import LiveDriversCoordinator
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.live_data_models import DriverPositionsModel
from custom_components.f1_sensor.replay_mode import ReplayController, ReplayFrame
from custom_components.f1_sensor.signalr import LiveBus


def _timing(lap, value):
    return {"Lines": {"4": {"NumberOfLaps": lap, "LastLapTime": {"Value": value}}}}


def _frames():
    return [
        ReplayFrame(0, "SessionInfo", {"Key": 123, "Type": "Race", "Name": "Race"}),
        ReplayFrame(0, "DriverList", {"4": {"RacingNumber": "4", "Tla": "NOR"}}),
        ReplayFrame(0, "SessionStatus", {"Status": "Started"}),
        ReplayFrame(10_000, "TimingData", _timing(2, "1:30.000")),
        ReplayFrame(20_000, "TimingData", _timing(3, "1:30.000")),
        ReplayFrame(30_000, "TimingData", _timing(2, "1:31.000")),
        ReplayFrame(
            40_000,
            "TimingAppData",
            {
                "Lines": {
                    "4": {
                        "Stints": {
                            "0": {
                                "LapNumber": 4,
                                "LapTime": "1:29.000",
                                "Compound": "HARD",
                            }
                        }
                    }
                }
            },
        ),
    ]


@pytest.fixture
async def replay_history(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    bus = LiveBus(hass, AsyncMock())
    session = SimpleNamespace(data={}, async_add_listener=lambda _cb: lambda: None)
    coordinator = LiveDriversCoordinator(hass, session, bus=bus, config_entry=entry)
    await coordinator.async_config_entry_first_refresh()
    controller = ReplayController(hass, entry.entry_id, AsyncMock(), bus)
    model = DriverPositionsModel(coordinator, None, entry.entry_id, None)
    model.hass = hass
    yield SimpleNamespace(
        bus=bus,
        coordinator=coordinator,
        controller=controller,
        manager=controller.session_manager,
        model=model,
    )
    await coordinator.async_close()
    await controller.async_close()


async def test_rebuilt_history_retains_identical_laps_corrections_and_app_pairs(
    replay_history,
):
    state = replay_history.manager._build_initial_state(_frames(), 40_000)
    history = state["LapHistory"]["4"]
    assert history["laps"] == {"2": "1:31.000", "3": "1:30.000", "4": "1:29.000"}
    assert history["lap_metadata"] == {
        str(lap): {"association": "confirmed", "reason": None} for lap in (2, 3, 4)
    }


async def test_initial_and_checkpoint_injection_match_sequential_history(
    replay_history,
):
    harness = replay_history
    frames = _frames()
    for frame in frames:
        harness.bus.inject_message(frame.stream, frame.payload)
    live = deepcopy(harness.coordinator.data["drivers"]["4"]["lap_history"])
    assert live["laps"] == {"2": "1:31.000", "3": "1:30.000", "4": "1:29.000"}

    for through in (40_000, 20_000, 40_000):
        accumulator = harness.manager._new_seek_checkpoint_accumulator()
        for frame in frames:
            if frame.timestamp_ms <= through:
                harness.manager._accumulate_seek_checkpoint_frame(accumulator, frame)
        state = harness.manager._seek_checkpoint_state(accumulator)
        harness.coordinator.reset_for_replay()
        harness.controller._inject_initial_state(state)
        assert harness.model._update_from_coordinator(initial=False)
        attrs = harness.model._attr_extra_state_attributes
        assert attrs["lap_history_session_type"] == "Race"
        driver = attrs["drivers"][0]
        expected = (
            live["laps"] if through == 40_000 else {"2": "1:30.000", "3": "1:30.000"}
        )
        assert driver["laps"] == expected
        assert driver["completed_laps"] == (4 if through == 40_000 else 3)
        assert driver["lap_metadata"] == {
            key: {"association": "confirmed", "reason": None} for key in expected
        }


async def test_prebuilt_legacy_history_remains_unconfirmed(replay_history):
    harness = replay_history
    harness.controller._inject_initial_state(
        {
            "TimingData": _timing(3, "1:30.000"),
            "LapHistory": {
                "4": {
                    "laps": {"2": "1:31.000", "3": "1:30.000"},
                    "last_recorded_lap": 3,
                    "completed_laps": 3,
                }
            },
            "SessionInfo": {"Key": 123, "Type": "Race"},
        }
    )
    history = harness.coordinator.data["drivers"]["4"]["lap_history"]
    assert history["laps"] == {"2": "1:31.000", "3": "1:30.000"}
    assert all(
        meta["association"] != "confirmed" for meta in history["lap_metadata"].values()
    )


async def test_replay_historical_time_and_count_corrections_keep_completion(
    replay_history,
):
    manager = replay_history.manager
    history, times = {}, {}
    for payload in (
        _timing(2, "1:30.000"),
        _timing(3, "1:30.000"),
        _timing(2, "1:31.000"),
    ):
        manager._merge_lap_history_state(history, times, payload)
    assert history["4"]["completed_laps"] == 3
    manager._merge_lap_history_state(
        history, times, {"Lines": {"4": {"NumberOfLaps": 1}}}
    )
    assert history["4"]["completed_laps"] == 3


@pytest.mark.parametrize("value", [90.0, 90, True, ""])
async def test_malformed_last_lap_values_match_live_rejection(replay_history, value):
    harness = replay_history
    payload = _timing(2, value)
    harness.bus.inject_message("TimingData", payload)
    state, times = {}, {}
    harness.manager._merge_lap_history_state(state, times, payload)
    assert (
        state["4"]["laps"]
        == harness.coordinator._state["drivers"]["4"]["lap_history"]["laps"]
        == {}
    )


@pytest.mark.parametrize(
    "index", ["32", "999999999999999999999999999999999999", "bad", "-1"]
)
async def test_replay_stint_bound_matches_live(replay_history, index):
    harness = replay_history
    payload = {
        "Lines": {"4": {"Stints": {index: {"LapNumber": 2, "LapTime": "1:30.000"}}}}
    }
    harness.bus.inject_message("TimingAppData", payload)
    state = {}
    harness.manager._merge_timingapp_lap_history_state(state, payload)
    assert state == {}
    assert harness.coordinator._state["drivers"] == {}


@pytest.mark.parametrize("new_session", [False, True])
async def test_sparse_session_metadata_survives_rebuild_without_cross_session_type(
    replay_history, new_session
):
    harness = replay_history
    frames = _frames()[:4] + [
        ReplayFrame(
            15_000,
            "SessionInfo",
            {
                "Key": 124 if new_session else 123,
                "Name": "Race",
                "ArchiveStatus": {"Status": "Complete"},
            },
        )
    ]
    for frame in frames:
        harness.bus.inject_message(frame.stream, frame.payload)
    expected_type = harness.coordinator._state.get("lap_history_session_type")
    assert expected_type == (None if new_session else "Race")
    initial = harness.manager._build_initial_state(frames, 15_000)
    accumulator = harness.manager._new_seek_checkpoint_accumulator()
    for frame in frames:
        harness.manager._accumulate_seek_checkpoint_frame(accumulator, frame)
    for state in (initial, harness.manager._seek_checkpoint_state(accumulator)):
        harness.coordinator.reset_for_replay()
        harness.controller._inject_initial_state(state)
        assert (
            harness.coordinator._state.get("lap_history_session_type") == expected_type
        )
        assert state["SessionInfo"]["ArchiveStatus"] == {"Status": "Complete"}
        if new_session:
            assert not any(
                driver.get("lap_history", {}).get("lap_metadata")
                for driver in harness.coordinator._state["drivers"].values()
            )
