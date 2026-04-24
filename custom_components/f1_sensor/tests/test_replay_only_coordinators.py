from __future__ import annotations

import pytest

from custom_components.f1_sensor import (
    ChampionshipPredictionCoordinator,
    PitStopCoordinator,
    TeamRadioCoordinator,
)
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker


class _StubBus:
    def subscribe(self, _stream, _callback):
        return lambda: None


@pytest.mark.parametrize(
    ("coordinator_cls", "extra_kwargs"),
    [
        (TeamRadioCoordinator, {}),
        (PitStopCoordinator, {}),
    ],
)
@pytest.mark.asyncio
async def test_replay_only_coordinators_are_available_only_during_replay(
    hass, coordinator_cls, extra_kwargs
) -> None:
    live_state = LiveAvailabilityTracker()
    coordinator = coordinator_cls(
        hass,
        session_coord=object(),
        bus=_StubBus(),
        live_state=live_state,
        **extra_kwargs,
    )
    await hass.async_block_till_done()

    assert coordinator.available is False

    live_state.set_state(True, "live-Race")
    await hass.async_block_till_done()
    assert coordinator.available is False

    live_state.set_state(True, "replay")
    await hass.async_block_till_done()
    assert coordinator.available is True

    live_state.set_state(False, "replay-stopped")
    await hass.async_block_till_done()
    assert coordinator.available is False


@pytest.mark.asyncio
async def test_championship_prediction_coordinator_is_available_for_auth_live_or_replay(
    hass,
) -> None:
    live_state = LiveAvailabilityTracker()
    bus = _StubBus()
    bus.auth_enabled = False
    coordinator = ChampionshipPredictionCoordinator(
        hass,
        session_coord=object(),
        bus=bus,
        live_state=live_state,
    )
    await hass.async_block_till_done()

    assert coordinator.available is False

    live_state.set_state(True, "live-Race")
    await hass.async_block_till_done()
    assert coordinator.available is False

    bus.auth_enabled = True
    live_state.set_state(False, "idle")
    await hass.async_block_till_done()
    live_state.set_state(True, "live-Race")
    await hass.async_block_till_done()
    assert coordinator.available is True

    bus.auth_enabled = False
    live_state.set_state(True, "replay")
    await hass.async_block_till_done()
    assert coordinator.available is True

    live_state.set_state(False, "replay-stopped")
    await hass.async_block_till_done()
    assert coordinator.available is False
