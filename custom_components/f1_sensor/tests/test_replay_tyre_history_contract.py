"""Recorded race boundaries survive replay bootstrap, checkpoints and seeks."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import LiveDriversCoordinator
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.live_data_models import CurrentTyresModel
from custom_components.f1_sensor.replay_mode import ReplayController, ReplayFrame
from custom_components.f1_sensor.signalr import LiveBus


@pytest.fixture
async def tyre_replay(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    bus = LiveBus(hass, AsyncMock())
    session = SimpleNamespace(data={}, async_add_listener=lambda _cb: lambda: None)
    coordinator = LiveDriversCoordinator(hass, session, bus=bus, config_entry=entry)
    await coordinator.async_config_entry_first_refresh()
    controller = ReplayController(hass, entry.entry_id, AsyncMock(), bus)
    model = CurrentTyresModel(coordinator, None, entry.entry_id, None)
    model.hass = hass
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/mexico_2026_tyre_seek.json").read_text()
    )
    frames = [
        ReplayFrame(0, "SessionInfo", {"Key": 11404, "Type": "Race", "Name": "Race"})
    ]
    frames.extend(
        ReplayFrame(item["t"], item["s"], item["p"]) for item in fixture["frames"]
    )
    yield SimpleNamespace(
        bus=bus,
        coordinator=coordinator,
        controller=controller,
        manager=controller.session_manager,
        model=model,
        frames=frames,
    )
    await coordinator.async_close()
    await controller.async_close()


def snapshot(harness):
    assert harness.model._update_from_coordinator()
    return deepcopy(harness.model._attr_extra_state_attributes)


def play_through(harness, target):
    for frame in harness.frames:
        if frame.timestamp_ms <= target:
            harness.bus.inject_message(frame.stream, frame.payload)


async def test_recorded_start_and_delayed_confirmation_have_real_lap_ranges(
    tyre_replay,
):
    harness = tyre_replay
    play_through(harness, 1_932_499)
    attrs = snapshot(harness)
    old, current = attrs["drivers"][0]["stints"]
    assert (old["first_lap"], old["last_lap"], old["stint_laps"]) == (1, 11, 11)
    assert (
        current["first_lap"],
        current["last_lap"],
        current["stint_laps"],
        current["tyre_age_at_start"],
        current["total_laps"],
    ) == (12, 12, 1, 3, 4)
    assert attrs["lap_total"] == 71


@pytest.mark.parametrize("builder", ["initial", "checkpoint", "scan"])
@pytest.mark.parametrize("lap_as_string", [False, True])
async def test_rebuild_before_after_and_backwards_never_uses_future_sets(
    tyre_replay, builder, lap_as_string, tmp_path
):
    harness = tyre_replay
    if lap_as_string:
        for frame in harness.frames:
            if frame.stream == "LapCount":
                frame.payload["CurrentLap"] = str(frame.payload["CurrentLap"])
    for target in (1_932_499, 1_772_499, 1_932_499):
        if builder == "initial":
            state = harness.manager._build_initial_state(harness.frames, target)
        elif builder == "checkpoint":
            accumulator = harness.manager._new_seek_checkpoint_accumulator()
            for frame in harness.frames:
                if frame.timestamp_ms <= target:
                    harness.manager._accumulate_seek_checkpoint_frame(
                        accumulator, frame
                    )
            state = harness.manager._seek_checkpoint_state(accumulator)
        else:
            path = tmp_path / "frames.jsonl"
            path.write_text(
                "".join(
                    json.dumps({"t": f.timestamp_ms, "s": f.stream, "p": f.payload})
                    + "\n"
                    for f in harness.frames
                )
            )
            index = harness.manager._scan_merged_frames_sync(path, None)
            checkpoint = next(
                cp for cp in reversed(index["seek_checkpoints"]) if cp["t"] <= target
            )
            state = checkpoint["state"]
        harness.coordinator.reset_for_replay()
        harness.controller._inject_initial_state(state)
        if builder == "scan":
            for frame in harness.frames:
                if checkpoint["t"] < frame.timestamp_ms <= target:
                    harness.bus.inject_message(frame.stream, frame.payload)
        attrs = snapshot(harness)
        stints = attrs["drivers"][0]["stints"]
        assert attrs["lap_total"] == 71
        assert stints[0]["first_lap"] == 1
        if target == 1_932_499:
            assert len(stints) == 2
            assert (
                stints[0]["last_lap"],
                stints[1]["first_lap"],
                stints[1]["last_lap"],
            ) == (11, 12, 12)
            assert stints[1]["tyre_age_at_start"] == 3
        else:
            assert len(stints) == 1
            assert stints[0]["compound"] == "MEDIUM"
            assert stints[0]["last_lap"] == 10


@pytest.mark.parametrize("next_set", [False, True])
async def test_observed_continuation_counter_correction_survives_checkpoint(
    tyre_replay, next_set
):
    harness = tyre_replay
    frames = [
        ReplayFrame(0, "SessionInfo", {"Key": 1, "Type": "Race"}),
        ReplayFrame(0, "LapCount", {"CurrentLap": 1, "TotalLaps": 56}),
        ReplayFrame(
            1000,
            "TimingAppData",
            {
                "Lines": {
                    "30": {
                        "Stints": {
                            "0": {
                                "Compound": "SOFT",
                                "TyresNotChanged": "0",
                                "StartLaps": 0,
                                "TotalLaps": 3,
                            }
                        }
                    }
                }
            },
        ),
        ReplayFrame(
            2000,
            "TimingAppData",
            {
                "Lines": {
                    "30": {
                        "Stints": {
                            "1": {
                                "Compound": "SOFT",
                                "TyresNotChanged": "1",
                                "StartLaps": 3,
                                "TotalLaps": 5,
                            }
                        }
                    }
                }
            },
        ),
        ReplayFrame(
            3000,
            "TimingAppData",
            {"Lines": {"30": {"Stints": {"1": {"TotalLaps": 2}}}}},
        ),
    ]
    if next_set:
        frames.append(
            ReplayFrame(
                4000,
                "TimingAppData",
                {
                    "Lines": {
                        "30": {
                            "Stints": {
                                "2": {
                                    "Compound": "HARD",
                                    "TyresNotChanged": "0",
                                    "StartLaps": 0,
                                    "TotalLaps": 1,
                                }
                            }
                        }
                    }
                },
            )
        )
    accumulator = harness.manager._new_seek_checkpoint_accumulator()
    for frame in frames:
        harness.bus.inject_message(frame.stream, frame.payload)
        harness.manager._accumulate_seek_checkpoint_frame(accumulator, frame)
    before = snapshot(harness)
    assert before["drivers"][0]["stints"][0]["total_laps"] == 2
    state = harness.manager._seek_checkpoint_state(accumulator)
    harness.coordinator.reset_for_replay()
    harness.controller._inject_initial_state(state)
    after = snapshot(harness)
    assert after == before


@pytest.mark.parametrize("explicit_null", [False, True])
async def test_lap_distance_delta_matches_checkpoint_and_live(
    tyre_replay, explicit_null
):
    harness = tyre_replay
    accumulator = harness.manager._new_seek_checkpoint_accumulator()
    for payload in (
        {"CurrentLap": 1, "TotalLaps": 71},
        {"CurrentLap": 2, **({"TotalLaps": None} if explicit_null else {})},
    ):
        frame = ReplayFrame(0, "LapCount", payload)
        harness.bus.inject_message(frame.stream, frame.payload)
        harness.manager._accumulate_seek_checkpoint_frame(accumulator, frame)
    expected = None if explicit_null else 71
    assert harness.coordinator.data["lap_total"] == expected
    assert (
        harness.manager._seek_checkpoint_state(accumulator)["LapCount"]["TotalLaps"]
        == expected
    )
