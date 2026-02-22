from __future__ import annotations

from unittest.mock import Mock

import pytest
from custom_components.f1_sensor import binary_sensor as binary_sensor_platform
from custom_components.f1_sensor import sensor as sensor_platform
from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS
from custom_components.f1_sensor.helpers import format_entity_name
from pytest_homeassistant_custom_component.common import MockConfigEntry


def test_format_entity_name_humanizes_sensor_keys() -> None:
    assert format_entity_name("F1", "track_status") == "F1 Track Status"
    assert (
        format_entity_name("F1", "track_status", include_base=False) == "Track Status"
    )
    assert format_entity_name("F1", "fia_documents") == "F1 FIA Documents"
    assert (
        format_entity_name("F1", "fia_documents", include_base=False) == "FIA Documents"
    )
    assert format_entity_name("F1", "top_three_p1") == "F1 Top Three P1"


@pytest.mark.asyncio
async def test_sensor_setup_entry_uses_translation_key_for_track_status(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "RaceHub",
            "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS - {"track_status"}),
        },
    )
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "race_coordinator": Mock(),
        "driver_coordinator": Mock(),
        "constructor_coordinator": Mock(),
        "last_race_coordinator": Mock(),
        "season_results_coordinator": Mock(),
        "sprint_results_coordinator": Mock(),
        "track_status_coordinator": Mock(),
    }

    async_add_entities = Mock()
    await sensor_platform.async_setup_entry(hass, entry, async_add_entities)

    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    entity = entities[0]
    assert entity.unique_id == f"{entry.entry_id}_track_status"
    assert entity._attr_translation_key == "track_status"
    assert entity._attr_suggested_object_id == "f1_track_status"


@pytest.mark.asyncio
async def test_binary_sensor_setup_entry_uses_translation_keys(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "RaceHub",
            "disabled_sensors": sorted(
                SUPPORTED_SENSOR_KEYS - {"race_week", "live_timing_diagnostics"}
            ),
        },
    )
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "race_coordinator": Mock(),
    }

    async_add_entities = Mock()
    await binary_sensor_platform.async_setup_entry(hass, entry, async_add_entities)

    entities = async_add_entities.call_args[0][0]
    translation_keys = {
        entity.unique_id: entity._attr_translation_key for entity in entities
    }
    object_ids = {
        entity.unique_id: entity._attr_suggested_object_id for entity in entities
    }

    assert translation_keys[f"{entry.entry_id}_race_week"] == "race_week"
    assert (
        translation_keys[f"{entry.entry_id}_live_timing_online"] == "live_timing_online"
    )
    assert object_ids[f"{entry.entry_id}_race_week"] == "f1_race_week"
    assert object_ids[f"{entry.entry_id}_live_timing_online"] == "f1_live_timing_online"
