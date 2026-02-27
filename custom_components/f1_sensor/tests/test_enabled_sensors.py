from __future__ import annotations

from unittest.mock import Mock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import binary_sensor as binary_sensor_platform
from custom_components.f1_sensor.const import DOMAIN


@pytest.mark.asyncio
async def test_formation_start_created_when_tracker_exists(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
        },
    )
    entry.add_to_hass(hass)

    tracker = Mock()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "race_coordinator": Mock(),
        "formation_start_tracker": tracker,
    }

    async_add_entities = Mock()
    await binary_sensor_platform.async_setup_entry(hass, entry, async_add_entities)

    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    entity_types = [type(e).__name__ for e in entities]
    assert "F1FormationStartBinarySensor" in entity_types
