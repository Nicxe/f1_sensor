from __future__ import annotations

import logging
from typing import Any
from unittest.mock import Mock

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.json import json_bytes
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.json import json_loads
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import binary_sensor as binary_sensor_platform
from custom_components.f1_sensor.binary_sensor import F1OnTrackIncidentBinarySensor
from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS

_LOGGER = logging.getLogger(__name__)


def _coordinator(hass, data: dict[str, Any]) -> DataUpdateCoordinator:
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="incident-test",
        update_method=None,
    )
    coordinator.data = data
    coordinator.available = True
    return coordinator


async def _add_entity_and_get_state(hass, entity: F1OnTrackIncidentBinarySensor):
    component = EntityComponent(_LOGGER, "binary_sensor", hass)
    await component.async_add_entities([entity])
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert state is not None
    return state


def _state_recorder_attrs(state) -> dict[str, Any]:
    unrecorded = frozenset()
    if state.state_info is not None:
        unrecorded = state.state_info.get("unrecorded_attributes", frozenset())
    recorded = {
        key: value for key, value in state.attributes.items() if key not in unrecorded
    }
    return json_loads(json_bytes(recorded))


def _incident(
    *,
    phase: str = "confirmed",
    confidence: str = "medium",
    incident_id: str = "2026-miami-race-10-2026-05-03T17:00:01Z",
) -> dict[str, Any]:
    return {
        "incident_id": incident_id,
        "phase": phase,
        "confidence": confidence,
        "reason": "timing_stopped",
        "driver": {
            "racing_number": "10",
            "tla": "GAS",
            "name": "Pierre Gasly",
            "team": "Alpine",
        },
        "session": {
            "meeting_name": "Miami Grand Prix",
            "session_name": "Race",
            "session_type": "race",
            "session_key": "2026-miami-race",
        },
        "signals": ["timing_stopped"],
    }


def _coordinator_data(
    active_incidents: list[dict[str, Any]],
    *,
    latest_phase: str = "confirmed",
) -> dict[str, Any]:
    return {
        "active_count": len(active_incidents),
        "highest_confidence": "medium" if active_incidents else None,
        "latest_incident_id": "2026-miami-race-10-2026-05-03T17:00:01Z",
        "latest_driver_number": "10",
        "latest_driver_tla": "GAS",
        "latest_reason": "timing_stopped",
        "latest_phase": latest_phase,
        "session_type": "race",
        "session_name": "Race",
        "data_quality": "live",
        "active_incidents": active_incidents,
    }


@pytest.mark.asyncio
async def test_on_track_incident_setup_entry_uses_incident_coordinator(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "RaceHub",
            "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS - {"on_track_incident"}),
        },
    )
    entry.add_to_hass(hass)
    coordinator = _coordinator(hass, _coordinator_data([]))
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "race_coordinator": Mock(),
        "incident_coordinator": coordinator,
    }

    async_add_entities = Mock()
    await binary_sensor_platform.async_setup_entry(hass, entry, async_add_entities)

    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    entity = entities[0]
    assert isinstance(entity, F1OnTrackIncidentBinarySensor)
    assert entity.coordinator is coordinator
    assert entity.unique_id == f"{entry.entry_id}_on_track_incident"
    assert entity._attr_translation_key == "on_track_incident"
    assert entity._attr_has_entity_name is True
    assert entity._attr_suggested_object_id == "f1_on_track_incident"


@pytest.mark.asyncio
async def test_on_track_incident_state_and_attributes_follow_confirmed_incidents(
    hass,
) -> None:
    coordinator = _coordinator(hass, _coordinator_data([]))
    entity = F1OnTrackIncidentBinarySensor(
        coordinator,
        "incident-entry_on_track_incident",
        "incident-entry",
        "F1",
    )

    state = await _add_entity_and_get_state(hass, entity)
    assert state.state == STATE_OFF
    assert state.attributes["active_count"] == 0
    assert set(state.attributes) >= {
        "active_count",
        "highest_confidence",
        "latest_incident_id",
        "latest_driver_number",
        "latest_driver_tla",
        "latest_reason",
        "latest_phase",
        "session_type",
        "session_name",
        "data_quality",
    }

    coordinator.async_set_updated_data(
        _coordinator_data(
            [
                _incident(confidence="medium"),
                _incident(
                    confidence="high",
                    incident_id="2026-miami-race-44-2026-05-03T17:00:02Z",
                ),
            ]
        )
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["active_count"] == 2
    assert state.attributes["highest_confidence"] == "high"
    assert state.attributes["latest_incident_id"] == (
        "2026-miami-race-10-2026-05-03T17:00:01Z"
    )
    assert state.attributes["latest_driver_number"] == "10"
    assert state.attributes["latest_driver_tla"] == "GAS"
    assert state.attributes["latest_phase"] == "confirmed"
    assert state.attributes["session_type"] == "race"
    assert state.attributes["session_name"] == "Race"
    assert state.attributes["data_quality"] == "live"

    coordinator.async_set_updated_data(_coordinator_data([], latest_phase="cleared"))
    await hass.async_block_till_done()

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes["active_count"] == 0
    assert state.attributes["highest_confidence"] is None
    assert state.attributes["latest_phase"] == "cleared"


@pytest.mark.asyncio
async def test_on_track_incident_ignores_active_candidates(hass) -> None:
    coordinator = _coordinator(
        hass,
        _coordinator_data([_incident(phase="candidate", confidence="high")]),
    )
    entity = F1OnTrackIncidentBinarySensor(
        coordinator,
        "incident-entry_on_track_incident",
        "incident-entry",
        "F1",
    )

    state = await _add_entity_and_get_state(hass, entity)

    assert state.state == STATE_OFF
    assert state.attributes["active_count"] == 0
    assert state.attributes["highest_confidence"] is None


@pytest.mark.asyncio
async def test_on_track_incident_unavailable_without_available_coordinator(
    hass,
) -> None:
    missing = F1OnTrackIncidentBinarySensor(
        None,
        "incident-entry_on_track_incident_missing",
        "incident-entry",
        "F1",
    )
    state = await _add_entity_and_get_state(hass, missing)
    assert state.state == STATE_UNAVAILABLE

    coordinator = _coordinator(hass, _coordinator_data([_incident()]))
    coordinator.available = False
    unavailable = F1OnTrackIncidentBinarySensor(
        coordinator,
        "incident-entry_on_track_incident_unavailable",
        "incident-entry",
        "F1",
    )
    state = await _add_entity_and_get_state(hass, unavailable)
    assert state.state == STATE_UNAVAILABLE


@pytest.mark.asyncio
async def test_on_track_incident_does_not_expose_active_list_to_recorder(
    hass,
) -> None:
    coordinator = _coordinator(
        hass,
        _coordinator_data([_incident(confidence="high")]),
    )
    entity = F1OnTrackIncidentBinarySensor(
        coordinator,
        "incident-entry_on_track_incident",
        "incident-entry",
        "F1",
    )

    state = await _add_entity_and_get_state(hass, entity)

    assert "active_incidents" not in state.attributes
    assert state.state_info is not None
    assert "active_incidents" in state.state_info["unrecorded_attributes"]
    recorded_attrs = _state_recorder_attrs(state)
    assert "active_incidents" not in recorded_attrs
    assert recorded_attrs["active_count"] == 1
