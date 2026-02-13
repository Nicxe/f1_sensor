from __future__ import annotations

from unittest.mock import Mock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor import sensor as sensor_platform


@pytest.mark.asyncio
async def test_sensor_setup_keeps_formation_start_enabled(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enabled_sensors": ["formation_start"],
        },
    )
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "race_coordinator": object(),
        "driver_coordinator": object(),
        "constructor_coordinator": object(),
        "last_race_coordinator": object(),
        "season_results_coordinator": object(),
        "sprint_results_coordinator": object(),
    }

    async_add_entities = Mock()
    await sensor_platform.async_setup_entry(hass, entry, async_add_entities)

    assert "formation_start" in entry.data["enabled_sensors"]
