"""Upgrades operate immediately; only voluntary sensor removals need review."""

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import async_migrate_entry, async_setup_entry
from custom_components.f1_sensor.config_flow import F1OptionsFlow
from custom_components.f1_sensor.const import DOMAIN


def entry(hass, minor_version=3):
    result = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        minor_version=minor_version,
        data={"sensor_name": "F1", "secret": "preserved"},
        options={"enable_race_control": False, "disabled_sensors": ["weather"]},
    )
    result.add_to_hass(hass)
    return result


async def test_options_open_directly_without_card_data_or_upgrade_choice(hass):
    config = entry(hass)
    before = (dict(config.data), dict(config.options))
    flow = F1OptionsFlow(config)
    flow.hass = hass
    flow.flow_id = "options"
    flow.handler = config.entry_id
    result = await flow.async_step_init()
    assert result["step_id"] == "init"
    assert "card_data_features" not in result["data_schema"].schema
    assert (dict(config.data), dict(config.options)) == before
    assert not hasattr(flow, "async_step_data_choice")


async def test_voluntary_reduction_is_reviewed_without_changing_live(hass):
    config = entry(hass)
    flow = F1OptionsFlow(config)
    flow.hass = hass
    flow.flow_id = "options"
    flow.handler = config.entry_id
    result = await flow.async_step_init(
        {"enabled_sensors": ["race_week"], "enable_race_control": False}
    )
    assert result["step_id"] == "sensor_review"
    assert "Driver standings" in result["description_placeholders"]["removed_sensors"]
    before = dict(config.options)
    result = await flow.async_step_sensor_review({"confirm": False})
    assert result["errors"]
    assert dict(config.options) == before
    result = await flow.async_step_sensor_review({"confirm": True})
    assert result["type"] == "create_entry"
    assert result["data"]["enable_race_control"] is False
    assert "driver_standings" in result["data"]["disabled_sensors"]
    assert "data_choice_version" not in config.data


async def test_missing_marker_never_blocks_runtime_or_triggers_reload(hass):
    config = entry(hass)
    with (
        patch(
            "custom_components.f1_sensor.async_notify_card_data", AsyncMock()
        ) as notify,
        patch(
            "custom_components.f1_sensor._async_setup_entry",
            AsyncMock(return_value=True),
        ) as setup,
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload,
    ):
        assert await async_setup_entry(hass, config)
        setup.assert_awaited_once()
        notify.assert_awaited_once_with(hass, config)
        reload.assert_not_awaited()
    assert "data_choice_version" not in config.data


@pytest.mark.parametrize("minor", [2, 3, 4])
async def test_migration_preserves_sensor_configuration_and_is_idempotent(hass, minor):
    config = entry(hass, minor_version=minor)
    before = (dict(config.data), dict(config.options))
    assert await async_migrate_entry(hass, config)
    assert config.minor_version == 4
    assert (dict(config.data), dict(config.options)) == before
    assert await async_migrate_entry(hass, config)
    assert (dict(config.data), dict(config.options)) == before
