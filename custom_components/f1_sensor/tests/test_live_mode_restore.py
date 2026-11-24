from __future__ import annotations

import logging
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import State
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import (
    LiveModeCoordinator,
    TrackStatusCoordinator,
    _reset_replay_sensitive_coordinator_state,
)
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
from custom_components.f1_sensor.sensor import (
    F1ChampionshipPredictionDriversSensor,
    F1ChampionshipPredictionTeamsSensor,
    F1PitStopsSensor,
    F1StraightModeSensor,
    F1TeamRadioSensor,
    F1TrackStatusSensor,
    F1TrackWeatherSensor,
)
from custom_components.f1_sensor.signalr import LiveBus

_LOGGER = logging.getLogger(__name__)


class _LiveState:
    def __init__(self, is_live: bool = False, reason: str | None = "init") -> None:
        self.is_live = is_live
        self.reason = reason
        self._listeners = []

    def add_listener(self, callback):
        self._listeners.append(callback)
        callback(self.is_live, self.reason)

        def _remove():
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _remove

    def set_live(self, is_live: bool, reason: str | None = None) -> None:
        self.is_live = is_live
        self.reason = reason
        for callback in list(self._listeners):
            callback(is_live, reason)


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
    coordinator.is_restored = lambda _field: False
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
    hass.data.setdefault("_f1_sensor_test_entity_components", []).append(component)
    await component.async_add_entities([entity])
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert state is not None
    return state


@pytest.mark.parametrize(
    ("entity_type", "domain", "expected", "cross_attribute", "cross_value"),
    [
        (
            F1OvertakeModeBinarySensor,
            "binary_sensor",
            "on",
            "straight_mode",
            STRAIGHT_MODE_LOW,
        ),
        (F1StraightModeSensor, "sensor", STRAIGHT_MODE_LOW, "overtake_enabled", True),
    ],
)
@pytest.mark.parametrize("initially_live", [False, True])
async def test_mode_entities_display_confirmed_session_restore_and_updates(
    hass, entity_type, domain, expected, cross_attribute, cross_value, initially_live
) -> None:
    entry_id = "mode_entry"
    live_state = _LiveState(initially_live)
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
        "live_state": live_state,
        "live_bus": _LiveBus(0.0),
    }
    payload = {"overtake_enabled": True, "straight_mode": STRAIGHT_MODE_LOW}
    coordinator = _build_coordinator(hass, payload)
    confirmed_restores = {"overtake_enabled", "straight_mode"}
    coordinator.is_restored = confirmed_restores.__contains__
    entity = entity_type(coordinator, "mode", entry_id, "F1")
    state = await _add_entity_and_get_state(hass, domain, entity)
    if not initially_live:
        assert state.state == STATE_UNAVAILABLE
        live_state.set_live(True)
        coordinator.async_set_updated_data(payload)
        state = hass.states.get(entity.entity_id)

    assert state.state == expected
    assert state.attributes[cross_attribute] == cross_value
    assert state.attributes["restored"] is True

    companion_value = False if cross_attribute == "overtake_enabled" else "disabled"
    payload[cross_attribute] = companion_value
    confirmed_restores.discard(cross_attribute)
    coordinator.async_set_updated_data(payload)
    state = hass.states.get(entity.entity_id)
    assert state.state == expected
    assert state.attributes[cross_attribute] == companion_value
    assert state.attributes["restored"] is True

    confirmed_restores.clear()
    coordinator.async_set_updated_data(payload)
    state = hass.states.get(entity.entity_id)
    assert state.state == expected
    assert not state.attributes.get("restored")

    coordinator.session_is_terminal = True
    coordinator.async_set_updated_data(payload)
    assert hass.states.get(entity.entity_id).state == STATE_UNAVAILABLE


@pytest.mark.parametrize(
    ("entity_type", "domain", "value", "attribute", "other_value"),
    [
        (
            F1OvertakeModeBinarySensor,
            "binary_sensor",
            "on",
            "straight_mode",
            "low_grip",
        ),
        (F1StraightModeSensor, "sensor", "low_grip", "overtake_enabled", True),
    ],
)
async def test_mode_entities_do_not_carry_values_into_next_session(
    hass, entity_type, domain, value, attribute, other_value
) -> None:
    entry_id = "mode_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
    }
    coordinator = _build_coordinator(
        hass, {"overtake_enabled": True, "straight_mode": STRAIGHT_MODE_LOW}
    )
    entity = entity_type(coordinator, "mode", entry_id, "F1")
    initial = await _add_entity_and_get_state(hass, domain, entity)
    assert initial.state == value
    assert initial.attributes[attribute] == other_value

    coordinator.async_set_updated_data(None)
    assert hass.states.get(entity.entity_id).state == STATE_UNAVAILABLE


@pytest.mark.parametrize(
    ("entity_type", "domain", "old_value"),
    [
        (F1OvertakeModeBinarySensor, "binary_sensor", "on"),
        (F1StraightModeSensor, "sensor", STRAIGHT_MODE_LOW),
    ],
)
@pytest.mark.parametrize("has_previous_state", [False, True])
async def test_mode_entities_remain_unavailable_without_current_session_evidence(
    hass, entity_type, domain, old_value, has_previous_state
) -> None:
    entry_id = "mode_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
    }
    coordinator = _build_coordinator(hass, None)
    entity = entity_type(coordinator, "mode", entry_id, "F1")
    entity.async_get_last_state = AsyncMock(
        return_value=State(f"{domain}.old", old_value) if has_previous_state else None
    )

    state = await _add_entity_and_get_state(hass, domain, entity)
    assert state.state == STATE_UNAVAILABLE


@pytest.mark.asyncio
async def test_live_mode_coordinator_notifies_when_live_window_opens(hass) -> None:
    tracker = LiveAvailabilityTracker()
    bus = LiveBus(hass, AsyncMock())
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    coordinator = LiveModeCoordinator(hass, bus, live_state=tracker, config_entry=entry)
    observed: list[object] = []
    unsub = coordinator.async_add_listener(lambda: observed.append(coordinator.data))
    try:
        await coordinator.async_config_entry_first_refresh()
        tracker.set_state(True, "live-Test")
        await hass.async_block_till_done()
        assert observed
    finally:
        unsub()
        await coordinator.async_close()
        await bus.async_close()


@pytest.mark.asyncio
async def test_live_mode_coordinator_clears_state_when_session_finishes(hass) -> None:
    tracker = LiveAvailabilityTracker()
    bus = LiveBus(hass, AsyncMock())
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    status = _build_coordinator(hass, {"Status": "Started", "Started": "Started"})
    coordinator = LiveModeCoordinator(
        hass,
        bus,
        session_status_coordinator=status,
        live_state=tracker,
        config_entry=entry,
    )
    try:
        await coordinator.async_config_entry_first_refresh()
        tracker.set_state(True, "live-Race")
        bus.inject_message("SessionInfo", {"Key": 11412, "Type": "Race"})
        bus.inject_message(
            "RaceControlMessages", {"Category": "Other", "Message": "OVERTAKE ENABLED"}
        )
        await hass.async_block_till_done()
        assert coordinator.data == {
            "overtake_enabled": True,
            "straight_mode": None,
            "track_grip": None,
        }
        status.async_set_updated_data({"Status": "Finished", "Started": "Finished"})
        await hass.async_block_till_done()
        assert coordinator.session_is_terminal is True
        assert coordinator.data is None
    finally:
        await coordinator.async_close()
        await bus.async_close()


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
async def test_formation_start_turns_off_once_session_goes_live(
    hass, cleanup_test_entity_components
) -> None:
    entry_id = "test_entry"
    live_state = _LiveState(True, "replay-mode")
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
async def test_formation_start_is_unavailable_during_public_live_sessions(
    hass, cleanup_test_entity_components
) -> None:
    entry_id = "test_entry"
    live_state = _LiveState(True, "live-Race")
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
        "live_state": live_state,
        "live_bus": _LiveBus(0.0),
    }
    tracker = _FormationTracker(
        {
            "status": "ready",
            "scheduled_start": "2026-03-08T03:59:00+00:00",
            "formation_start": "2026-03-08T04:00:00+00:00",
            "delta_seconds": 0.0,
            "source": "replay_index",
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

    state = await _add_entity_and_get_state(hass, "binary_sensor", entity)

    assert state.state == STATE_UNAVAILABLE


@pytest.mark.asyncio
async def test_formation_start_is_available_during_auth_live_sessions(
    hass, cleanup_test_entity_components
) -> None:
    entry_id = "test_entry"
    live_state = _LiveState(True, "live-Race")
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
        "live_state": live_state,
        "live_bus": _LiveBus(0.0),
        "signalr_stream_capabilities": {
            "auth_enabled": True,
            "auth_gated_live_streams": frozenset({"CarData.z"}),
        },
    }
    tracker = _FormationTracker(
        {
            "status": "ready",
            "scheduled_start": "2026-03-08T03:59:00+00:00",
            "formation_start": "2026-03-08T04:00:00+00:00",
            "delta_seconds": 0.0,
            "source": "signalr_cardata",
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

    state = await _add_entity_and_get_state(hass, "binary_sensor", entity)

    assert state.state == "on"
    assert state.attributes["source"] == "signalr_cardata"


@pytest.mark.parametrize(
    ("factory", "restored_state", "attributes"),
    [
        (
            lambda coordinator, entry_id: F1TeamRadioSensor(
                coordinator, f"{entry_id}_team_radio", entry_id, "F1"
            ),
            "2026-03-08T04:00:00+00:00",
            {"history": []},
        ),
        (
            lambda coordinator, entry_id: F1PitStopsSensor(
                coordinator, f"{entry_id}_pitstops", entry_id, "F1"
            ),
            "3",
            {"cars": {}, "last_update": "2026-03-08T04:00:00+00:00"},
        ),
    ],
)
@pytest.mark.asyncio
async def test_replay_capable_sensors_stay_unavailable_during_public_live(
    hass, factory, restored_state, attributes
) -> None:
    entry_id = "test_entry"
    live_state = _LiveState(True, "live-Race")
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
        "live_state": live_state,
        "live_bus": _LiveBus(0.0),
    }
    coordinator = _build_coordinator(hass, None)
    coordinator.available = False
    entity = factory(coordinator, entry_id)
    entity.async_get_last_state = AsyncMock(
        return_value=State(f"sensor.{entity.unique_id}", restored_state, attributes)
    )

    state = await _add_entity_and_get_state(hass, "sensor", entity)

    assert state.state == STATE_UNAVAILABLE


@pytest.mark.parametrize(
    ("factory", "restored_state", "attributes", "stream", "expected_state"),
    [
        (
            lambda coordinator, entry_id: F1TeamRadioSensor(
                coordinator, f"{entry_id}_team_radio", entry_id, "F1"
            ),
            "2026-03-08T04:00:00+00:00",
            {"history": []},
            "TeamRadio",
            "unknown",
        ),
        (
            lambda coordinator, entry_id: F1PitStopsSensor(
                coordinator, f"{entry_id}_pitstops", entry_id, "F1"
            ),
            "3",
            {"cars": {}, "last_update": "2026-03-08T04:00:00+00:00"},
            "PitStopSeries",
            "3",
        ),
    ],
)
@pytest.mark.asyncio
async def test_replay_capable_sensors_handle_restored_state_during_auth_live(
    hass, factory, restored_state, attributes, stream, expected_state
) -> None:
    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
        "live_state": _LiveState(True, "live-Race"),
        "live_bus": _LiveBus(0.0),
        "signalr_stream_capabilities": {
            "auth_enabled": True,
            "auth_gated_live_streams": frozenset({stream}),
        },
    }
    coordinator = _build_coordinator(hass, None)
    coordinator.available = True
    entity = factory(coordinator, entry_id)
    entity.async_get_last_state = AsyncMock(
        return_value=State(f"sensor.{entity.unique_id}", restored_state, attributes)
    )

    state = await _add_entity_and_get_state(hass, "sensor", entity)

    # Radio URLs need captures in the current store; pit stop totals can restore.
    assert state.state == expected_state
    if stream == "TeamRadio":
        assert not state.attributes.get("history")
        assert not state.attributes.get("clip_url")


@pytest.mark.parametrize(
    ("factory", "restored_state", "attributes"),
    [
        (
            lambda coordinator, entry_id: F1ChampionshipPredictionDriversSensor(
                coordinator,
                f"{entry_id}_championship_prediction_drivers",
                entry_id,
                "F1",
            ),
            "NOR",
            {"drivers": {}, "predicted_driver_p1": None, "last_update": None},
        ),
        (
            lambda coordinator, entry_id: F1ChampionshipPredictionTeamsSensor(
                coordinator,
                f"{entry_id}_championship_prediction_teams",
                entry_id,
                "F1",
            ),
            "McLaren",
            {"teams": {}, "predicted_team_p1": None, "last_update": None},
        ),
    ],
)
@pytest.mark.asyncio
async def test_championship_prediction_sensors_stay_unavailable_in_public_live(
    hass, factory, restored_state, attributes
) -> None:
    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
        "live_state": _LiveState(True, "live-Race"),
        "live_bus": _LiveBus(0.0),
        "signalr_stream_capabilities": {
            "auth_enabled": False,
            "auth_gated_live_streams": frozenset({"ChampionshipPrediction"}),
        },
    }
    coordinator = _build_coordinator(hass, None)
    coordinator.available = False
    entity = factory(coordinator, entry_id)
    entity.async_get_last_state = AsyncMock(
        return_value=State(f"sensor.{entity.unique_id}", restored_state, attributes)
    )

    state = await _add_entity_and_get_state(hass, "sensor", entity)

    assert state.state == STATE_UNAVAILABLE


@pytest.mark.parametrize(
    ("factory", "restored_state", "attributes"),
    [
        (
            lambda coordinator, entry_id: F1ChampionshipPredictionDriversSensor(
                coordinator,
                f"{entry_id}_championship_prediction_drivers",
                entry_id,
                "F1",
            ),
            "NOR",
            {"drivers": {}, "predicted_driver_p1": None, "last_update": None},
        ),
        (
            lambda coordinator, entry_id: F1ChampionshipPredictionTeamsSensor(
                coordinator,
                f"{entry_id}_championship_prediction_teams",
                entry_id,
                "F1",
            ),
            "McLaren",
            {"teams": {}, "predicted_team_p1": None, "last_update": None},
        ),
    ],
)
@pytest.mark.asyncio
async def test_championship_prediction_sensors_restore_during_replay(
    hass, factory, restored_state, attributes
) -> None:
    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
        "live_state": _LiveState(True, "replay-mode"),
        "live_bus": _LiveBus(0.0),
        "signalr_stream_capabilities": {
            "auth_enabled": False,
            "auth_gated_live_streams": frozenset({"ChampionshipPrediction"}),
        },
    }
    coordinator = _build_coordinator(hass, None)
    coordinator.available = True
    coordinator.prediction_context = {"session_key": "race-a", "session_type": "race"}
    attributes = {**attributes, **coordinator.prediction_context}
    entity = factory(coordinator, entry_id)
    entity.async_get_last_state = AsyncMock(
        return_value=State(f"sensor.{entity.unique_id}", restored_state, attributes)
    )

    state = await _add_entity_and_get_state(hass, "sensor", entity)

    assert state.state == restored_state


@pytest.mark.parametrize(
    ("factory", "restored_state", "attributes"),
    [
        (
            lambda coordinator, entry_id: F1ChampionshipPredictionDriversSensor(
                coordinator,
                f"{entry_id}_championship_prediction_drivers",
                entry_id,
                "F1",
            ),
            "NOR",
            {"drivers": {}, "predicted_driver_p1": None, "last_update": None},
        ),
        (
            lambda coordinator, entry_id: F1ChampionshipPredictionTeamsSensor(
                coordinator,
                f"{entry_id}_championship_prediction_teams",
                entry_id,
                "F1",
            ),
            "McLaren",
            {"teams": {}, "predicted_team_p1": None, "last_update": None},
        ),
    ],
)
@pytest.mark.asyncio
async def test_championship_prediction_sensors_restore_during_auth_live(
    hass, factory, restored_state, attributes
) -> None:
    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
        "live_state": _LiveState(True, "live-Race"),
        "live_bus": _LiveBus(0.0),
        "signalr_stream_capabilities": {
            "auth_enabled": True,
            "auth_gated_live_streams": frozenset({"ChampionshipPrediction"}),
        },
    }
    coordinator = _build_coordinator(hass, None)
    coordinator.available = True
    coordinator.prediction_context = {"session_key": "race-a", "session_type": "race"}
    attributes = {**attributes, **coordinator.prediction_context}
    entity = factory(coordinator, entry_id)
    entity.async_get_last_state = AsyncMock(
        return_value=State(f"sensor.{entity.unique_id}", restored_state, attributes)
    )

    state = await _add_entity_and_get_state(hass, "sensor", entity)

    assert state.state == restored_state


@pytest.mark.parametrize("reason", ["live-Race", "replay"])
@pytest.mark.asyncio
async def test_track_weather_does_not_restore_before_first_payload(
    hass, reason
) -> None:
    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
        "live_state": _LiveState(True, reason),
        "live_bus": _LiveBus(0.0),
    }
    coordinator = _build_coordinator(hass, None)
    entity = F1TrackWeatherSensor(
        coordinator,
        f"{entry_id}_track_weather",
        entry_id,
        "F1",
    )
    entity.async_get_last_state = AsyncMock(
        return_value=State(
            "sensor.f1_track_weather",
            "27.4",
            {"air_temperature": 27.4, "track_temperature": 34.6},
        )
    )

    state = await _add_entity_and_get_state(hass, "sensor", entity)

    assert state.state == STATE_UNAVAILABLE
    entity.async_get_last_state.assert_not_called()


@pytest.mark.asyncio
async def test_track_weather_becomes_available_after_first_payload(hass) -> None:
    entry_id = "test_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
        "live_state": _LiveState(True, "live-Race"),
        "live_bus": _LiveBus(0.0),
    }
    coordinator = _build_coordinator(hass, None)
    entity = F1TrackWeatherSensor(
        coordinator,
        f"{entry_id}_track_weather",
        entry_id,
        "F1",
    )

    initial = await _add_entity_and_get_state(hass, "sensor", entity)
    assert initial.state == STATE_UNAVAILABLE

    coordinator.async_set_updated_data(
        {
            "AirTemp": "21.5",
            "TrackTemp": "35.0",
            "Humidity": "64",
            "Pressure": "1014.2",
            "Rainfall": "0",
            "WindDirection": "90",
            "WindSpeed": "2.1",
        }
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == "21.5"
    assert state.attributes["air_temperature"] == 21.5
    assert state.attributes["track_temperature"] == 35.0

    coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()

    after_empty_update = hass.states.get(entity.entity_id)
    assert after_empty_update is not None
    assert after_empty_update.state == "21.5"


@pytest.mark.asyncio
async def test_formation_start_is_unavailable_outside_replay(
    hass, cleanup_test_entity_components
) -> None:
    entry_id = "test_entry_live"
    live_state = _LiveState(True)
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
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

    assert initial.state == STATE_UNAVAILABLE

    live_state.set_live(True, "replay")
    tracker.emit(
        {
            "status": "ready",
            "scheduled_start": "2026-03-08T03:59:00+00:00",
            "formation_start": "2026-03-08T04:00:00+00:00",
            "delta_seconds": 0.0,
            "source": "replay_index",
            "session_type": "Race",
            "session_name": "Race",
            "error": None,
        }
    )
    await hass.async_block_till_done()

    after = hass.states.get(entity.entity_id)
    assert after is not None
    assert after.state == "on"


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resumed_status",
    [
        pytest.param({"Status": "Inactive", "Started": "Finished"}, id="break"),
        pytest.param({"Status": "Started"}, id="live"),
    ],
)
@pytest.mark.parametrize(
    ("track_status", "expected_state"),
    [pytest.param("1", "CLEAR", id="clear"), pytest.param("6", "VSC", id="vsc")],
)
async def test_track_status_recovers_after_terminal_status_without_track_update(
    hass, resumed_status, track_status, expected_state
) -> None:
    entry_id = "test_entry"
    status_coordinator = _build_coordinator(hass, {"Status": "Started"})
    _set_status_context(status_coordinator, is_qualifying_like=True, qualifying_part=3)
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
        "session_status_coordinator": status_coordinator,
    }
    cached_track_status = {"Status": track_status}
    coordinator = _build_coordinator(hass, cached_track_status)
    entity = F1TrackStatusSensor(
        coordinator, f"{entry_id}_track_status", entry_id, "F1"
    )

    initial = await _add_entity_and_get_state(hass, "sensor", entity)
    assert initial.state == expected_state

    status_coordinator.async_set_updated_data({"Status": "Finished"})
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id).state == STATE_UNAVAILABLE

    status_coordinator.async_set_updated_data(resumed_status)
    await hass.async_block_till_done()

    assert coordinator.data is cached_track_status
    assert hass.states.get(entity.entity_id).state == expected_state


@pytest.mark.asyncio
@pytest.mark.parametrize("guard", ["missing_data", "inactive_stream", "replay_reset"])
async def test_track_status_recovery_requires_current_active_track_data(
    hass, guard
) -> None:
    entry_id = "test_entry"
    status_coordinator = _build_coordinator(hass, {"Status": "Finished"})
    _set_status_context(status_coordinator, is_qualifying_like=True, qualifying_part=3)
    live_state = _LiveState(True)
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": live_state,
        "session_status_coordinator": status_coordinator,
    }
    coordinator = TrackStatusCoordinator(hass, session_coord=None)
    if guard != "missing_data":
        coordinator._deliver({"Status": "6", "Message": "VSCDeployed"})
    entity = F1TrackStatusSensor(
        coordinator, f"{entry_id}_track_status", entry_id, "F1"
    )

    initial = await _add_entity_and_get_state(hass, "sensor", entity)
    assert initial.state == STATE_UNAVAILABLE

    if guard == "inactive_stream":
        live_state.set_live(False)
    elif guard == "replay_reset":
        _reset_replay_sensitive_coordinator_state(coordinator)

    status_coordinator.async_set_updated_data({"Status": "Started"})
    await hass.async_block_till_done()

    assert hass.states.get(entity.entity_id).state == STATE_UNAVAILABLE
    assert entity.native_value is None


@pytest.mark.parametrize("stored_key", [None, "previous-race"])
async def test_prediction_restore_rejects_missing_or_different_session(
    hass, stored_key
):
    entry_id = "prediction_scope"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
        "live_state": _LiveState(True, "replay-mode"),
        "live_bus": _LiveBus(0.0),
    }
    coordinator = _build_coordinator(hass, None)
    coordinator.available = True
    coordinator.prediction_context = {"session_key": "race-a", "session_type": "race"}
    entity = F1ChampionshipPredictionDriversSensor(
        coordinator, "prediction_scope", entry_id, "F1"
    )
    entity.async_get_last_state = AsyncMock(
        return_value=State(
            "sensor.prediction_scope",
            "NOR",
            {"session_key": stored_key, "session_type": "race"},
        )
    )
    state = await _add_entity_and_get_state(hass, "sensor", entity)
    assert state.state in {"unknown", "unavailable"}
    assert not state.attributes.get("drivers")
