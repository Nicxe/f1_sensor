from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

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


def _register_sensor_entity(hass, entry, suffix: str) -> er.RegistryEntry:
    registry = er.async_get(hass)
    return registry.async_get_or_create(
        "sensor",
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


@pytest.mark.asyncio
async def test_favorite_driver_device_trigger_is_event_and_entry_scoped(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    entity = _register_sensor_entity(hass, entry, "favorite_driver")
    calls: list[dict[str, Any]] = []

    async def action(variables, _context=None) -> None:
        calls.append(variables["trigger"]["event"].data)

    remove = await device_trigger.async_attach_trigger(
        hass,
        {
            "platform": "device",
            "domain": DOMAIN,
            "type": "favorite_driver_position_gained",
            "entity_id": entity.id,
        },
        action,
        _trigger_info(),
    )
    try:
        hass.bus.async_fire(
            "f1_sensor_favorite_driver_event",
            {"entry_id": entry.entry_id, "event_type": "position_gained"},
        )
        hass.bus.async_fire(
            "f1_sensor_favorite_driver_event",
            {"entry_id": entry.entry_id, "event_type": "position_lost"},
        )
        hass.bus.async_fire(
            "f1_sensor_favorite_driver_event",
            {"entry_id": "other-entry", "event_type": "position_gained"},
        )
        await hass.async_block_till_done()
    finally:
        remove()

    assert [call["event_type"] for call in calls] == ["position_gained"]


def test_find_entity_matches_domain_and_unique_id_suffix(monkeypatch) -> None:
    entries = [
        SimpleNamespace(domain="sensor", unique_id="entry_track_status", id="one"),
        SimpleNamespace(
            domain="binary_sensor", unique_id="entry_track_status", id="two"
        ),
    ]
    monkeypatch.setattr(
        device_trigger.er,
        "async_entries_for_device",
        lambda _registry, _device: entries,
    )
    assert (
        device_trigger._find_entity(object(), "device", "track_status", "sensor")
        == (entries[0])
    )
    assert device_trigger._find_entity(object(), "device", "missing", "sensor") is None


async def test_trigger_discovery_capabilities_and_state_attachment(
    hass, monkeypatch
) -> None:
    backing = SimpleNamespace(id="binary_sensor.safety_car")
    monkeypatch.setattr(device_trigger.er, "async_get", lambda _hass: object())
    monkeypatch.setattr(
        device_trigger,
        "_find_entity",
        lambda _registry, _device, suffix, _domain: (
            backing if suffix == "safety_car" else None
        ),
    )
    triggers = await device_trigger.async_get_triggers(hass, "device")
    assert {trigger["type"] for trigger in triggers} == {
        "safety_car_deployed",
        "safety_car_cleared",
    }

    event_caps = await device_trigger.async_get_trigger_capabilities(
        hass, {"type": "on_track_incident_detected"}
    )
    state_caps = await device_trigger.async_get_trigger_capabilities(
        hass, {"type": "safety_car_deployed"}
    )
    assert event_caps["extra_fields"]({}) == {}
    assert state_caps["extra_fields"]({"for": {"seconds": 2}})

    validate = AsyncMock(
        side_effect=lambda _hass, config: {**config, "validated": True}
    )
    remove = object()
    attach = AsyncMock(return_value=remove)
    monkeypatch.setattr(
        device_trigger.state_trigger, "async_validate_trigger_config", validate
    )
    monkeypatch.setattr(device_trigger.state_trigger, "async_attach_trigger", attach)
    action = AsyncMock()
    result = await device_trigger.async_attach_trigger(
        hass,
        {
            "type": "safety_car_deployed",
            "entity_id": "binary_sensor.safety_car",
            "for": {"seconds": 2},
        },
        action,
        _trigger_info(),
    )
    assert result is remove
    state_config = validate.await_args.args[1]
    assert state_config["to"] == "on"
    assert state_config["for"] == {"seconds": 2}

    await device_trigger.async_attach_trigger(
        hass,
        {
            "type": "new_team_radio",
            "entity_id": "sensor.team_radio",
        },
        action,
        _trigger_info(),
    )
    assert "to" not in validate.await_args.args[1]
