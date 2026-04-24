from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import config_flow as config_flow_module
from custom_components.f1_sensor.config_flow import F1FlowHandler
from custom_components.f1_sensor.const import (
    CONF_ENTITY_NAME_LANGUAGE,
    CONF_ENTITY_NAME_MODE,
    CONF_LIVE_TIMING_AUTH_HEADER,
    CONF_OPERATION_MODE,
    CONF_RACE_WEEK_START_DAY,
    CONF_REPLAY_FILE,
    DEFAULT_OPERATION_MODE,
    DOMAIN,
    ENTITY_NAME_MODE_LOCALIZED,
    RACE_WEEK_START_MONDAY,
)


def _schema_key_names(result: dict) -> set[str]:
    """Return the string field names from a config flow form schema."""
    return {str(key.schema) for key in result["data_schema"].schema}


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


async def test_user_flow_hides_auth_header_when_development_ui_disabled(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(config_flow_module, "ENABLE_DEVELOPMENT_MODE_UI", False)

    flow = F1FlowHandler()
    flow.hass = hass
    flow.context = {"source": "user"}

    result = await flow.async_step_user()

    assert result["type"] == "form"
    keys = _schema_key_names(result)
    assert CONF_LIVE_TIMING_AUTH_HEADER not in keys
    assert "clear_live_timing_auth_header" not in keys


async def test_user_flow_stores_trimmed_live_timing_auth_header(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(config_flow_module, "ENABLE_DEVELOPMENT_MODE_UI", True)

    flow = F1FlowHandler()
    flow.hass = hass
    flow.context = {"source": "user"}

    result = await flow.async_step_user(
        {
            "sensor_name": "RaceHub",
            "enabled_sensors": ["next_race"],
            "enable_race_control": False,
            CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
            CONF_LIVE_TIMING_AUTH_HEADER: "  Authorization: Bearer test-token  ",
        },
    )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_LIVE_TIMING_AUTH_HEADER] == "Bearer test-token"


async def test_reconfigure_hides_auth_header_when_development_ui_disabled(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(config_flow_module, "ENABLE_DEVELOPMENT_MODE_UI", False)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": False,
            "disabled_sensors": [],
            CONF_OPERATION_MODE: DEFAULT_OPERATION_MODE,
            CONF_REPLAY_FILE: "",
            CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
            CONF_LIVE_TIMING_AUTH_HEADER: "Bearer existing-token",
        },
    )
    entry.add_to_hass(hass)

    flow = F1FlowHandler()
    flow.hass = hass
    flow.context = {"source": "reconfigure", "entry_id": entry.entry_id}

    result = await flow.async_step_reconfigure()

    assert result["type"] == "form"
    keys = _schema_key_names(result)
    assert CONF_LIVE_TIMING_AUTH_HEADER not in keys
    assert "clear_live_timing_auth_header" not in keys


async def test_reconfigure_blank_auth_header_keeps_existing_value(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(config_flow_module, "ENABLE_DEVELOPMENT_MODE_UI", True)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": False,
            "disabled_sensors": [],
            CONF_OPERATION_MODE: DEFAULT_OPERATION_MODE,
            CONF_REPLAY_FILE: "",
            CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
            CONF_LIVE_TIMING_AUTH_HEADER: "Bearer existing-token",
        },
    )
    entry.add_to_hass(hass)

    flow = F1FlowHandler()
    flow.hass = hass
    flow.context = {"source": "reconfigure", "entry_id": entry.entry_id}

    result = await flow.async_step_reconfigure(
        {
            "sensor_name": "F1",
            "enabled_sensors": ["next_race"],
            "enable_race_control": False,
            CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
            CONF_OPERATION_MODE: DEFAULT_OPERATION_MODE,
            CONF_REPLAY_FILE: "",
            CONF_LIVE_TIMING_AUTH_HEADER: "",
            "clear_live_timing_auth_header": False,
        },
    )

    assert result["type"] == "abort"
    assert entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == "Bearer existing-token"


async def test_reconfigure_can_clear_auth_header(hass, monkeypatch) -> None:
    monkeypatch.setattr(config_flow_module, "ENABLE_DEVELOPMENT_MODE_UI", True)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": False,
            "disabled_sensors": [],
            CONF_OPERATION_MODE: DEFAULT_OPERATION_MODE,
            CONF_REPLAY_FILE: "",
            CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
            CONF_LIVE_TIMING_AUTH_HEADER: "Bearer existing-token",
        },
    )
    entry.add_to_hass(hass)

    flow = F1FlowHandler()
    flow.hass = hass
    flow.context = {"source": "reconfigure", "entry_id": entry.entry_id}

    result = await flow.async_step_reconfigure(
        {
            "sensor_name": "F1",
            "enabled_sensors": ["next_race"],
            "enable_race_control": False,
            CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
            CONF_OPERATION_MODE: DEFAULT_OPERATION_MODE,
            CONF_REPLAY_FILE: "",
            CONF_LIVE_TIMING_AUTH_HEADER: "",
            "clear_live_timing_auth_header": True,
        },
    )

    assert result["type"] == "abort"
    assert entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == ""


async def test_reauth_updates_auth_header(hass, monkeypatch) -> None:
    monkeypatch.setattr(config_flow_module, "ENABLE_DEVELOPMENT_MODE_UI", True)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": False,
            CONF_OPERATION_MODE: DEFAULT_OPERATION_MODE,
            CONF_REPLAY_FILE: "",
            CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
            CONF_LIVE_TIMING_AUTH_HEADER: "Bearer old-token",
        },
    )
    entry.add_to_hass(hass)

    flow = F1FlowHandler()
    flow.hass = hass
    flow.context = {"source": "reauth", "entry_id": entry.entry_id}

    result = await flow.async_step_reauth_confirm(
        {CONF_LIVE_TIMING_AUTH_HEADER: "  Authorization: Bearer new-token  "}
    )

    assert result["type"] == "abort"
    assert entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == "Bearer new-token"


async def test_reauth_can_clear_auth_header(hass, monkeypatch) -> None:
    monkeypatch.setattr(config_flow_module, "ENABLE_DEVELOPMENT_MODE_UI", True)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": False,
            CONF_OPERATION_MODE: DEFAULT_OPERATION_MODE,
            CONF_REPLAY_FILE: "",
            CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
            CONF_LIVE_TIMING_AUTH_HEADER: "Bearer old-token",
        },
    )
    entry.add_to_hass(hass)

    flow = F1FlowHandler()
    flow.hass = hass
    flow.context = {"source": "reauth", "entry_id": entry.entry_id}

    result = await flow.async_step_reauth_confirm(
        {
            CONF_LIVE_TIMING_AUTH_HEADER: "",
            "clear_live_timing_auth_header": True,
        }
    )

    assert result["type"] == "abort"
    assert entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == ""


async def test_reauth_requires_auth_header(hass, monkeypatch) -> None:
    monkeypatch.setattr(config_flow_module, "ENABLE_DEVELOPMENT_MODE_UI", True)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": False,
            CONF_OPERATION_MODE: DEFAULT_OPERATION_MODE,
            CONF_REPLAY_FILE: "",
            CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
        },
    )
    entry.add_to_hass(hass)

    flow = F1FlowHandler()
    flow.hass = hass
    flow.context = {"source": "reauth", "entry_id": entry.entry_id}

    result = await flow.async_step_reauth_confirm({CONF_LIVE_TIMING_AUTH_HEADER: ""})

    assert result["type"] == "form"
    assert result["errors"][CONF_LIVE_TIMING_AUTH_HEADER] == "auth_header_required"


async def test_reauth_is_hidden_when_development_ui_disabled(hass, monkeypatch) -> None:
    monkeypatch.setattr(config_flow_module, "ENABLE_DEVELOPMENT_MODE_UI", False)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": False,
            CONF_OPERATION_MODE: DEFAULT_OPERATION_MODE,
            CONF_REPLAY_FILE: "",
            CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
        },
    )
    entry.add_to_hass(hass)

    flow = F1FlowHandler()
    flow.hass = hass
    flow.context = {"source": "reauth", "entry_id": entry.entry_id}

    result = await flow.async_step_reauth()

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_not_supported"
