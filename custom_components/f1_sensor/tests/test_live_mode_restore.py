from __future__ import annotations

import logging
from unittest.mock import AsyncMock

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import State
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import pytest

from custom_components.f1_sensor import LiveModeCoordinator
from custom_components.f1_sensor.binary_sensor import (
    F1FormationStartBinarySensor,
    F1OvertakeModeBinarySensor,
    F1SafetyCarBinarySensor,
)
from custom_components.f1_sensor.const import (
    CONF_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
    OPERATION_MODE_LIVE,
    STRAIGHT_MODE_LOW,
)
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.sensor import F1StraightModeSensor, F1TrackStatusSensor

_LOGGER = logging.getLogger(__name__)


class _LiveState:
    def __init__(self, is_live: bool = False) -> None:
        self.is_live = is_live
        self._listeners = []

    def add_listener(self, callback):
        self._listeners.append(callback)
        callback(self.is_live, "init")

        def _remove():
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _remove

    def set_live(self, is_live: bool, reason: str | None = None) -> None:
        self.is_live = is_live
        for callback in list(self._listeners):
            callback(is_live, reason)


class _ListenerCoordinator:
    def __init__(self, data=None) -> None:
        self.data = data
        self._listeners = []

    def async_add_listener(self, callback):
        self._listeners.append(callback)

        def _remove():
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _remove

    def push(self, data) -> None:
        self.data = data
        for callback in list(self._listeners):
            callback()


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


def _set_status_context(
    coordinator: DataUpdateCoordinator,
    *,
    is_qualifying_like: bool = False,
    qualifying_part: int | None = None,
) -> None:
    coordinator.is_qualifying_like_session = is_qualifying_like
    coordinator.qualifying_part = qualifying_part


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
async def test_overtake_mode_does_not_restore_when_session_is_terminal(hass) -> None:
    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
    }
    coordinator = _build_coordinator(hass, None)
    coordinator.session_is_terminal = True
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
async def test_overtake_mode_clears_when_session_becomes_terminal(hass) -> None:
    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
    }
    coordinator = _build_coordinator(hass, None)
    coordinator.session_is_terminal = False
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

    coordinator.session_is_terminal = True
    coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()

    after = hass.states.get(entity.entity_id)
    assert after is not None
    assert after.state == STATE_UNAVAILABLE


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
async def test_straight_mode_clears_when_session_becomes_terminal(hass) -> None:
    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
    }
    coordinator = _build_coordinator(hass, None)
    coordinator.session_is_terminal = False
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

    coordinator.session_is_terminal = True
    coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()

    after = hass.states.get(entity.entity_id)
    assert after is not None
    assert after.state == STATE_UNAVAILABLE


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
        _ListenerCoordinator(),
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


@pytest.mark.asyncio
async def test_live_mode_coordinator_clears_state_when_session_finishes(hass) -> None:
    tracker = LiveAvailabilityTracker()
    race_control = _ListenerCoordinator()
    session_status = _ListenerCoordinator({"Status": "Started", "Started": "Started"})
    coordinator = LiveModeCoordinator(
        hass,
        race_control,
        session_status_coordinator=session_status,
        live_state=tracker,
    )
    coordinator._rc_unsub = race_control.async_add_listener(  # noqa: SLF001
        coordinator._on_race_control_update  # noqa: SLF001
    )
    coordinator._status_unsub = session_status.async_add_listener(  # noqa: SLF001
        coordinator._handle_session_status_update  # noqa: SLF001
    )
    coordinator._handle_session_status_update()  # noqa: SLF001
    tracker.set_state(True, "live-Race")
    race_control.push({"Category": "Other", "Message": "OVERTAKE ENABLED"})
    await hass.async_block_till_done()
    assert coordinator.data == {"overtake_enabled": True, "straight_mode": None}

    session_status.push({"Status": "Finished", "Started": "Finished"})
    await hass.async_block_till_done()

    assert coordinator.session_is_terminal is True
    assert coordinator.data is None


class _FormationTracker:
    def __init__(self, snapshot):
        self._snapshot = snapshot
        self._listeners = []

    def add_listener(self, callback):
        self._listeners.append(callback)
        callback(dict(self._snapshot))

        def _remove():
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _remove

    def emit(self, snapshot) -> None:
        self._snapshot = snapshot
        for callback in list(self._listeners):
            callback(dict(snapshot))


@pytest.mark.asyncio
async def test_formation_start_turns_off_once_session_goes_live(hass) -> None:
    entry_id = "test_entry"
    live_state = _LiveState(True)
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": live_state,
    }
    tracker = _FormationTracker(
        {
            "status": "ready",
            "scheduled_start": "2026-03-08T03:59:00+00:00",
            "formation_start": "2026-03-08T04:00:00+00:00",
            "delta_seconds": 0.0,
            "source": "cardata",
            "session_type": "Race",
            "session_name": "Race",
            "error": None,
        }
    )
    entity = F1FormationStartBinarySensor(
        tracker,
        f"{entry_id}_formation_start",
        entry_id,
        "F1",
    )

    initial = await _add_entity_and_get_state(hass, "binary_sensor", entity)
    assert initial.state == "on"

    tracker.emit(
        {
            "status": "live",
            "scheduled_start": "2026-03-08T03:59:00+00:00",
            "formation_start": "2026-03-08T04:00:00+00:00",
            "delta_seconds": 0.0,
            "source": "cardata",
            "session_type": "Race",
            "session_name": "Race",
            "error": None,
        }
    )
    await hass.async_block_till_done()

    after = hass.states.get(entity.entity_id)
    assert after is not None
    assert after.state == "off"


@pytest.mark.asyncio
async def test_safety_car_turns_on_for_vsc_track_status(hass) -> None:
    entry_id = "test_entry"
    status_coordinator = _build_coordinator(hass, {"Status": "Started"})
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
        "session_status_coordinator": status_coordinator,
    }
    coordinator = _build_coordinator(hass, {"Status": "6", "Message": "VSCDeployed"})
    entity = F1SafetyCarBinarySensor(
        coordinator,
        f"{entry_id}_safety_car",
        entry_id,
        "F1",
    )

    state = await _add_entity_and_get_state(hass, "binary_sensor", entity)

    assert state.state == "on"
    assert state.attributes["track_status"] == "VSC"


@pytest.mark.asyncio
async def test_safety_car_clears_when_session_becomes_terminal(hass) -> None:
    entry_id = "test_entry"
    status_coordinator = _build_coordinator(hass, {"Status": "Started"})
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
        "session_status_coordinator": status_coordinator,
    }
    coordinator = _build_coordinator(hass, {"Status": "6", "Message": "VSCDeployed"})
    entity = F1SafetyCarBinarySensor(
        coordinator,
        f"{entry_id}_safety_car",
        entry_id,
        "F1",
    )

    initial = await _add_entity_and_get_state(hass, "binary_sensor", entity)
    assert initial.state == "on"

    status_coordinator.async_set_updated_data({"Status": "Finalised"})
    await hass.async_block_till_done()

    after = hass.states.get(entity.entity_id)
    assert after is not None
    assert after.state == STATE_UNAVAILABLE


@pytest.mark.asyncio
async def test_safety_car_does_not_restore_when_session_is_terminal(hass) -> None:
    entry_id = "test_entry"
    status_coordinator = _build_coordinator(hass, {"Status": "Finalised"})
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
        "session_status_coordinator": status_coordinator,
    }
    coordinator = _build_coordinator(hass, None)
    entity = F1SafetyCarBinarySensor(
        coordinator,
        f"{entry_id}_safety_car",
        entry_id,
        "F1",
    )
    entity.async_get_last_state = AsyncMock(
        return_value=State("binary_sensor.f1_safety_car", "on", {"track_status": "VSC"})
    )

    state = await _add_entity_and_get_state(hass, "binary_sensor", entity)

    assert state.state == STATE_UNAVAILABLE


@pytest.mark.asyncio
async def test_safety_car_keeps_state_during_qualifying_break(hass) -> None:
    entry_id = "test_entry"
    status_coordinator = _build_coordinator(hass, {"Status": "Started"})
    _set_status_context(
        status_coordinator,
        is_qualifying_like=True,
        qualifying_part=2,
    )
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
        "session_status_coordinator": status_coordinator,
    }
    coordinator = _build_coordinator(hass, {"Status": "6", "Message": "VSCDeployed"})
    entity = F1SafetyCarBinarySensor(
        coordinator,
        f"{entry_id}_safety_car",
        entry_id,
        "F1",
    )

    initial = await _add_entity_and_get_state(hass, "binary_sensor", entity)
    assert initial.state == "on"

    status_coordinator.async_set_updated_data({"Status": "Finished"})
    await hass.async_block_till_done()

    after = hass.states.get(entity.entity_id)
    assert after is not None
    assert after.state == "on"


@pytest.mark.asyncio
async def test_track_status_restores_active_state_when_stream_active(hass) -> None:
    entry_id = "test_entry"
    status_coordinator = _build_coordinator(hass, {"Status": "Started"})
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
        "session_status_coordinator": status_coordinator,
    }
    coordinator = _build_coordinator(hass, None)
    entity = F1TrackStatusSensor(
        coordinator,
        f"{entry_id}_track_status",
        entry_id,
        "F1",
    )
    entity.async_get_last_state = AsyncMock(
        return_value=State("sensor.f1_track_status", "VSC", {})
    )

    state = await _add_entity_and_get_state(hass, "sensor", entity)

    assert state.state == "VSC"


@pytest.mark.asyncio
async def test_track_status_clears_when_session_becomes_terminal(hass) -> None:
    entry_id = "test_entry"
    status_coordinator = _build_coordinator(hass, {"Status": "Started"})
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
        "session_status_coordinator": status_coordinator,
    }
    coordinator = _build_coordinator(hass, {"Status": "6", "Message": "VSCDeployed"})
    entity = F1TrackStatusSensor(
        coordinator,
        f"{entry_id}_track_status",
        entry_id,
        "F1",
    )

    initial = await _add_entity_and_get_state(hass, "sensor", entity)
    assert initial.state == "VSC"

    status_coordinator.async_set_updated_data({"Status": "Finalised"})
    await hass.async_block_till_done()

    after = hass.states.get(entity.entity_id)
    assert after is not None
    assert after.state == STATE_UNAVAILABLE


@pytest.mark.asyncio
async def test_track_status_keeps_state_during_qualifying_break(hass) -> None:
    entry_id = "test_entry"
    status_coordinator = _build_coordinator(hass, {"Status": "Started"})
    _set_status_context(
        status_coordinator,
        is_qualifying_like=True,
        qualifying_part=1,
    )
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
        "session_status_coordinator": status_coordinator,
    }
    coordinator = _build_coordinator(hass, {"Status": "6", "Message": "VSCDeployed"})
    entity = F1TrackStatusSensor(
        coordinator,
        f"{entry_id}_track_status",
        entry_id,
        "F1",
    )

    initial = await _add_entity_and_get_state(hass, "sensor", entity)
    assert initial.state == "VSC"

    status_coordinator.async_set_updated_data({"Status": "Finished"})
    await hass.async_block_till_done()

    after = hass.states.get(entity.entity_id)
    assert after is not None
    assert after.state == "VSC"
