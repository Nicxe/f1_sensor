from __future__ import annotations

from typing import Any

from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import device_trigger
from custom_components.f1_sensor.const import DOMAIN


def _trigger_info() -> dict[str, Any]:
    return {"trigger_data": {"id": "device-trigger-test"}, "variables": {}}


def _register_incident_entity(hass, entry, suffix: str) -> er.RegistryEntry:
    registry = er.async_get(hass)
    return registry.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        f"{entry.entry_id}_{suffix}",
        config_entry=entry,
    )


@pytest.mark.asyncio
async def test_possible_incident_device_trigger_fires_for_each_new_candidate(
    hass,
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    entity = _register_incident_entity(hass, entry, "possible_on_track_incident")
    calls: list[dict[str, Any]] = []

    async def action(variables, _context=None) -> None:
        calls.append(variables["trigger"]["event"].data)

    remove = await device_trigger.async_attach_trigger(
        hass,
        {
            "platform": "device",
            "domain": DOMAIN,
            "type": "possible_on_track_incident_detected",
            "entity_id": entity.id,
        },
        action,
        _trigger_info(),
    )
    try:
        hass.bus.async_fire(
            "f1_sensor_incident",
            {"entry_id": entry.entry_id, "phase": "candidate", "incident_id": "one"},
        )
        hass.bus.async_fire(
            "f1_sensor_incident",
            {"entry_id": entry.entry_id, "phase": "updated", "incident_id": "one"},
        )
        hass.bus.async_fire(
            "f1_sensor_incident",
            {"entry_id": entry.entry_id, "phase": "candidate", "incident_id": "two"},
        )
        hass.bus.async_fire(
            "f1_sensor_incident",
            {"entry_id": "other-entry", "phase": "candidate", "incident_id": "other"},
        )
        await hass.async_block_till_done()
    finally:
        remove()

    assert [call["incident_id"] for call in calls] == ["one", "two"]


@pytest.mark.asyncio
async def test_confirmed_incident_device_trigger_fires_for_each_confirmation(
    hass,
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    entity = _register_incident_entity(hass, entry, "on_track_incident")
    calls: list[dict[str, Any]] = []

    async def action(variables, _context=None) -> None:
        calls.append(variables["trigger"]["event"].data)

    remove = await device_trigger.async_attach_trigger(
        hass,
        {
            "platform": "device",
            "domain": DOMAIN,
            "type": "on_track_incident_detected",
            "entity_id": entity.id,
        },
        action,
        _trigger_info(),
    )
    try:
        hass.bus.async_fire(
            "f1_sensor_incident",
            {"entry_id": entry.entry_id, "phase": "candidate", "incident_id": "one"},
        )
        hass.bus.async_fire(
            "f1_sensor_incident",
            {"entry_id": entry.entry_id, "phase": "confirmed", "incident_id": "one"},
        )
        hass.bus.async_fire(
            "f1_sensor_incident",
            {"entry_id": entry.entry_id, "phase": "confirmed", "incident_id": "two"},
        )
        await hass.async_block_till_done()
    finally:
        remove()

    assert [call["incident_id"] for call in calls] == ["one", "two"]
