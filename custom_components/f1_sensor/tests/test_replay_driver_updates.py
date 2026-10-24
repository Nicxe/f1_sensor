"""Catch-up retains every driver input while limiting dashboard publications."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import LiveDriversCoordinator
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.replay_mode import (
    ReplayController,
    ReplayIndex,
    ReplayState,
)
from custom_components.f1_sensor.signalr import LiveBus


class _OfflineBus(LiveBus):
    """Use real subscriptions and injection without opening a transport."""

    async def swap_transport(self, factory) -> None:
        self._transport_factory = factory
        self._running = True

    async def async_close(self) -> None:
        self._running = False


def _lap_time(lap: int) -> str:
    return f"1:{lap % 60:02}.{lap:03}"


def _timing(lap: int) -> dict:
    return {
        "Lines": {
            "16": {
                "NumberOfLaps": lap,
                "LastLapTime": {"Value": _lap_time(lap)},
            }
        }
    }


@pytest.fixture
async def replay_drivers(hass, tmp_path):
    """Bind an actual controller and drivers coordinator to the same entry."""
    total_laps = 251  # Leave a final batch shorter than the catch-up limit.
    frames_file = tmp_path / "frames.jsonl"
    frames_file.write_text(
        "".join(
            json.dumps({"t": lap * 1000, "s": "TimingData", "p": _timing(lap)}) + "\n"
            for lap in range(1, total_laps + 1)
        ),
        encoding="utf-8",
    )
    index = ReplayIndex(
        session_id="driver-catch-up",
        total_frames=total_laps,
        duration_ms=total_laps * 1000,
        session_started_at_ms=0,
        frames_file=frames_file,
        index_file=tmp_path / "index.json",
        initial_state={
            "SessionInfo": {"Key": 123, "Type": "Practice", "Name": "Practice 2"},
            "DriverList": {"16": {"Tla": "LEC", "RacingNumber": "16"}},
            "SessionStatus": {"Status": "Started"},
            "TimingAppData": {
                "Lines": {
                    "16": {
                        "Stints": [
                            {
                                "Compound": "SOFT",
                                "New": "true",
                                "TyresNotChanged": "0",
                                "TotalLaps": 0,
                            }
                        ]
                    }
                }
            },
        },
    )
    bus = _OfflineBus(hass, SimpleNamespace())
    live_state = LiveAvailabilityTracker()
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    session = SimpleNamespace(data={}, async_add_listener=lambda _cb: lambda: None)
    coordinator = LiveDriversCoordinator(
        hass, session, bus=bus, config_entry=entry, live_state=live_state
    )
    await coordinator.async_config_entry_first_refresh()
    controller = ReplayController(
        hass,
        entry.entry_id,
        AsyncMock(),
        bus,
        live_state=live_state,
        start_reference_controller=SimpleNamespace(current="session"),
    )
    controller.session_manager._loaded_index = index
    controller.session_manager._state = ReplayState.READY
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "replay_controller": controller,
        "replay_reset_callbacks": [coordinator.reset_for_replay],
    }
    updates = []
    remove_listener = coordinator.async_add_listener(
        lambda: updates.append(deepcopy(coordinator.data))
    )
    yield SimpleNamespace(
        coordinator=coordinator,
        controller=controller,
        bus=bus,
        live_state=live_state,
        total_laps=total_laps,
        updates=updates,
    )
    remove_listener()
    await controller.async_close()
    await coordinator.async_close()


async def test_ready_catch_up_retains_all_laps_and_flushes_final_publication(
    replay_drivers,
) -> None:
    """The API returns with full history visible after fewer listener updates."""
    harness = replay_drivers
    await harness.controller.async_seek_to_position(harness.total_laps)
    await harness.controller.async_play()

    history = harness.coordinator.data["drivers"]["16"]["lap_history"]
    assert history["laps"] == {
        str(lap): _lap_time(lap) for lap in range(1, harness.total_laps + 1)
    }
    assert history["last_recorded_lap"] == harness.total_laps
    assert history["completed_laps"] == harness.total_laps
    assert 2 <= len(harness.updates) < harness.total_laps // 2
    assert harness.updates[-1]["drivers"]["16"]["lap_history"] == history
    assert harness.coordinator._deliver_handle is None
    assert harness.controller.state is ReplayState.PLAYING


@pytest.mark.parametrize("replay", [False, True])
async def test_live_and_normal_replay_publish_each_update_immediately(
    replay_drivers, replay
) -> None:
    """Batching applies only to a controller's accelerated catch-up state."""
    harness = replay_drivers
    if replay:
        harness.controller._ensure_replay_active()
    else:
        harness.live_state.set_state(True, "live-Practice 2")
    harness.controller._set_state(ReplayState.PLAYING)
    harness.updates.clear()

    for lap in range(1, 4):
        harness.bus.inject_message("TimingData", _timing(lap))
        assert len(harness.updates) == lap
        published = harness.updates[-1]["drivers"]["16"]["lap_history"]
        assert published["last_recorded_lap"] == lap
    assert harness.coordinator._deliver_handle is None


@pytest.mark.parametrize("action", ["reset", "stop", "unload"])
async def test_reset_stop_or_unload_discards_pending_catch_up_publication(
    replay_drivers, action
) -> None:
    """A queued callback cannot republish an abandoned replay generation."""
    harness = replay_drivers
    harness.controller._ensure_replay_active()
    harness.controller._set_state(ReplayState.SEEKING)
    harness.updates.clear()
    harness.bus.inject_message("TimingData", _timing(1))
    assert harness.updates == []
    assert harness.coordinator._deliver_handle is not None

    if action == "reset":
        harness.coordinator.reset_for_replay()
    elif action == "stop":
        await harness.controller.async_stop()
    else:
        await harness.coordinator.async_close()
    after_cleanup = deepcopy(harness.updates)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert harness.updates == after_cleanup
    assert harness.coordinator._deliver_handle is None
    assert all(not update["drivers"] for update in harness.updates)
