from __future__ import annotations

from custom_components.f1_sensor.config_flow import F1FlowHandler
from custom_components.f1_sensor.const import (
    CONF_ENTITY_NAME_LANGUAGE,
    CONF_ENTITY_NAME_MODE,
    CONF_RACE_WEEK_START_DAY,
    ENTITY_NAME_MODE_LOCALIZED,
    RACE_WEEK_START_MONDAY,
)


async def test_user_flow_stores_entity_name_metadata(hass) -> None:
    hass.config.language = "sv"

    flow = F1FlowHandler()
    flow.hass = hass
    flow.context = {"source": "user"}

    result = await flow.async_step_user(
        {
            "sensor_name": "RaceHub",
            "enabled_sensors": ["next_race"],
            "enable_race_control": False,
            CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
        },
    )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_ENTITY_NAME_MODE] == ENTITY_NAME_MODE_LOCALIZED
    assert result["data"][CONF_ENTITY_NAME_LANGUAGE] == "sv"
