"""HA disabling replans demand once and unload cancels queued work."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS
from custom_components.f1_sensor.runtime import (
    effective_entry_settings,
    entry_value,
    track_sensor_demand,
)


async def test_registry_disabling_replans_once_and_cleanup_cancels(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        options={"exposed_sensor_keys": ["race_week"], "disabled_sensors": []},
    )
    entry.add_to_hass(hass)
    assert set(entry_value(entry, "disabled_sensors")) == SUPPORTED_SENSOR_KEYS - {
        "race_week"
    }
    assert effective_entry_settings(entry)["disabled_sensors"] == entry_value(
        entry, "disabled_sensors"
    )
    registry = er.async_get(hass)
    first = registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_driver_standings", config_entry=entry
    )
    second = registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_constructor_standings", config_entry=entry
    )
    stop = track_sensor_demand(hass, entry)
    with patch.object(
        hass.config_entries, "async_reload", AsyncMock(return_value=True)
    ) as reload:
        registry.async_update_entity(
            first.entity_id, disabled_by=er.RegistryEntryDisabler.USER
        )
        registry.async_update_entity(
            second.entity_id, disabled_by=er.RegistryEntryDisabler.USER
        )
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
        await hass.async_block_till_done()
        reload.assert_awaited_once_with(entry.entry_id)
        registry.async_update_entity(first.entity_id, disabled_by=None)
        await hass.async_block_till_done()
        stop()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=4))
        await hass.async_block_till_done()
        reload.assert_awaited_once()
