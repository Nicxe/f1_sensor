from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest
from custom_components.f1_sensor import LiveModeCoordinator
from custom_components.f1_sensor.binary_sensor import F1OvertakeModeBinarySensor
from custom_components.f1_sensor.const import (
    CONF_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
    OPERATION_MODE_LIVE,
    STRAIGHT_MODE_LOW,
)
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.sensor import F1StraightModeSensor
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import State
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class _LiveState:
    def __init__(self, is_live: bool = False) -> None:
        self.is_live = is_live


class _RaceControlCoordinator:
    def __init__(self) -> None:
        self.data = None

    def async_add_listener(self, _callback):
        return lambda: None


class _LiveBus:
    def __init__(self, activity_age: float | None = 0.0) -> None:
        self._activity_age = activity_age

    def last_stream_activity_age(self) -> float | None:
        return self._activity_age


def _build_coordinator(hass, data: dict | None) -> DataUpdateCoordinator:
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="live_mode_test",
        update_method=None,
    )
    coordinator.data = data
    coordinator.available = True
    return coordinator


async def _add_entity_and_get_state(hass, domain: str, entity):
    component = EntityComponent(_LOGGER, domain, hass)
    await component.async_add_entities([entity])
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert state is not None
    return state


@pytest.mark.asyncio
async def test_overtake_mode_restores_state_when_stream_active(hass) -> None:
    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
    }
    coordinator = _build_coordinator(hass, None)
    entity = F1OvertakeModeBinarySensor(
        coordinator,
        f"{entry_id}_overtake_mode",
        entry_id,
        "F1",
    )
    entity.async_get_last_state = AsyncMock(
        return_value=State(
            "binary_sensor.f1_overtake_mode",
            "on",
            {"straight_mode": STRAIGHT_MODE_LOW},
        )
    )

    state = await _add_entity_and_get_state(hass, "binary_sensor", entity)

    assert state.state == "on"
    assert state.attributes["straight_mode"] == STRAIGHT_MODE_LOW
    assert state.attributes["restored"] is True


@pytest.mark.asyncio
async def test_overtake_mode_is_unavailable_without_live_value_or_restore(hass) -> None:
    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
    }
    coordinator = _build_coordinator(hass, None)
    entity = F1OvertakeModeBinarySensor(
        coordinator,
        f"{entry_id}_overtake_mode",
        entry_id,
        "F1",
    )
    entity.async_get_last_state = AsyncMock(return_value=None)

    state = await _add_entity_and_get_state(hass, "binary_sensor", entity)

    assert state.state == STATE_UNAVAILABLE


@pytest.mark.asyncio
async def test_overtake_mode_keeps_restored_state_until_new_live_value(hass) -> None:
    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
    }
    coordinator = _build_coordinator(hass, None)
    entity = F1OvertakeModeBinarySensor(
        coordinator,
        f"{entry_id}_overtake_mode",
        entry_id,
        "F1",
    )
    entity.async_get_last_state = AsyncMock(
        return_value=State("binary_sensor.f1_overtake_mode", "on", {})
    )

    initial = await _add_entity_and_get_state(hass, "binary_sensor", entity)
    assert initial.state == "on"

    coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()

    after = hass.states.get(entity.entity_id)
    assert after is not None
    assert after.state == "on"


@pytest.mark.asyncio
async def test_overtake_mode_restores_even_before_live_state_turns_on(hass) -> None:
    entry_id = "test_entry"
    live_bus = _LiveBus(0.0)
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
        "live_state": _LiveState(False),
        "live_bus": live_bus,
    }
    coordinator = _build_coordinator(hass, None)
    entity = F1OvertakeModeBinarySensor(
        coordinator,
        f"{entry_id}_overtake_mode",
        entry_id,
        "F1",
    )
    entity.async_get_last_state = AsyncMock(
        return_value=State("binary_sensor.f1_overtake_mode", "on", {})
    )

    state = await _add_entity_and_get_state(hass, "binary_sensor", entity)

    assert state.state == STATE_UNAVAILABLE
    hass.data[DOMAIN][entry_id]["live_state"].is_live = True
    entity.async_write_ha_state()
    await hass.async_block_till_done()
    state_after_live = hass.states.get(entity.entity_id)
    assert state_after_live is not None
    assert state_after_live.state == "on"


@pytest.mark.asyncio
async def test_straight_mode_restores_state_when_stream_active(hass) -> None:
    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
    }
    coordinator = _build_coordinator(hass, None)
    entity = F1StraightModeSensor(
        coordinator,
        f"{entry_id}_straight_mode",
        entry_id,
        "F1",
    )
    entity.async_get_last_state = AsyncMock(
        return_value=State(
            "sensor.f1_straight_mode",
            STRAIGHT_MODE_LOW,
            {"overtake_enabled": True},
        )
    )

    state = await _add_entity_and_get_state(hass, "sensor", entity)

    assert state.state == STRAIGHT_MODE_LOW
    assert state.attributes["overtake_enabled"] is True
    assert state.attributes["restored"] is True


@pytest.mark.asyncio
async def test_straight_mode_is_unavailable_without_live_value_or_restore(hass) -> None:
    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
    }
    coordinator = _build_coordinator(hass, None)
    entity = F1StraightModeSensor(
        coordinator,
        f"{entry_id}_straight_mode",
        entry_id,
        "F1",
    )
    entity.async_get_last_state = AsyncMock(return_value=None)

    state = await _add_entity_and_get_state(hass, "sensor", entity)

    assert state.state == STATE_UNAVAILABLE


@pytest.mark.asyncio
async def test_straight_mode_keeps_restored_state_until_new_live_value(hass) -> None:
    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
    }
    coordinator = _build_coordinator(hass, None)
    entity = F1StraightModeSensor(
        coordinator,
        f"{entry_id}_straight_mode",
        entry_id,
        "F1",
    )
    entity.async_get_last_state = AsyncMock(
        return_value=State("sensor.f1_straight_mode", STRAIGHT_MODE_LOW, {})
    )

    initial = await _add_entity_and_get_state(hass, "sensor", entity)
    assert initial.state == STRAIGHT_MODE_LOW

    coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()

    after = hass.states.get(entity.entity_id)
    assert after is not None
    assert after.state == STRAIGHT_MODE_LOW


@pytest.mark.asyncio
async def test_straight_mode_restores_even_before_live_state_turns_on(hass) -> None:
    entry_id = "test_entry"
    live_bus = _LiveBus(0.0)
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
        "live_state": _LiveState(False),
        "live_bus": live_bus,
    }
    coordinator = _build_coordinator(hass, None)
    entity = F1StraightModeSensor(
        coordinator,
        f"{entry_id}_straight_mode",
        entry_id,
        "F1",
    )
    entity.async_get_last_state = AsyncMock(
        return_value=State("sensor.f1_straight_mode", STRAIGHT_MODE_LOW, {})
    )

    state = await _add_entity_and_get_state(hass, "sensor", entity)

    assert state.state == STATE_UNAVAILABLE
    hass.data[DOMAIN][entry_id]["live_state"].is_live = True
    entity.async_write_ha_state()
    await hass.async_block_till_done()
    state_after_live = hass.states.get(entity.entity_id)
    assert state_after_live is not None
    assert state_after_live.state == STRAIGHT_MODE_LOW


@pytest.mark.asyncio
async def test_live_mode_coordinator_notifies_when_live_window_opens(hass) -> None:
    tracker = LiveAvailabilityTracker()
    coordinator = LiveModeCoordinator(
        hass,
        _RaceControlCoordinator(),
        live_state=tracker,
    )
    observed: list[object] = []
    unsub = coordinator.async_add_listener(lambda: observed.append(coordinator.data))
    try:
        tracker.set_state(True, "live-Test")
        await hass.async_block_till_done()
    finally:
        unsub()

    assert observed
