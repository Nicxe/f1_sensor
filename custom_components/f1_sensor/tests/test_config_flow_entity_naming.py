from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
import json

from pytest_homeassistant_custom_component.common import MockConfigEntry
from yarl import URL

from custom_components.f1_sensor.auth_http import (
    async_process_f1tv_pairing_callback,
)
from custom_components.f1_sensor.config_flow import (
    CONF_START_F1TV_PAIRING,
    F1FlowHandler,
)
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


def test_f1tv_auth_is_enabled_by_default() -> None:
    from custom_components.f1_sensor.const import ENABLE_F1TV_AUTH

    assert ENABLE_F1TV_AUTH is True


def _schema_key_names(result: dict) -> set[str]:
    """Return the string field names from a config flow form schema."""
    return {str(key.schema) for key in result["data_schema"].schema}


def _schema_key_order(result: dict) -> list[str]:
    """Return the form field names in display order."""
    return [str(key.schema) for key in result["data_schema"].schema]


def _schema_required_key_names(result: dict) -> set[str]:
    """Return the required string field names from a config flow form schema."""
    return {
        str(key.schema)
        for key in result["data_schema"].schema
        if key.__class__.__name__ == "Required"
    }


def _part(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _jwt(exp: datetime) -> str:
    return ".".join(
        (
            _part({"alg": "RS256", "typ": "JWT"}),
            _part({"exp": int(exp.timestamp())}),
            "signature",
        )
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


async def test_user_flow_shows_auth_but_hides_development_fields_when_development_ui_disabled(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", False
    )

    flow = F1FlowHandler()
    flow.hass = hass
    flow.context = {"source": "user"}

    result = await flow.async_step_user()

    assert result["type"] == "form"
    keys = _schema_key_names(result)
    assert CONF_OPERATION_MODE not in keys
    assert CONF_REPLAY_FILE not in keys
    assert CONF_LIVE_TIMING_AUTH_HEADER in keys
    assert "clear_live_timing_auth_header" not in keys
    assert CONF_START_F1TV_PAIRING in keys
    order = _schema_key_order(result)
    assert order.index(CONF_START_F1TV_PAIRING) < order.index(
        CONF_LIVE_TIMING_AUTH_HEADER
    )
    assert CONF_LIVE_TIMING_AUTH_HEADER not in _schema_required_key_names(result)


async def test_user_flow_shows_f1tv_pairing_when_development_ui_enabled(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )

    flow = F1FlowHandler()
    flow.hass = hass
    flow.context = {"source": "user"}

    result = await flow.async_step_user()

    assert result["type"] == "form"
    keys = _schema_key_names(result)
    assert CONF_OPERATION_MODE in keys
    assert CONF_REPLAY_FILE in keys
    assert CONF_LIVE_TIMING_AUTH_HEADER in keys
    assert CONF_START_F1TV_PAIRING in keys
    assert "clear_live_timing_auth_header" not in keys
    order = _schema_key_order(result)
    assert order.index(CONF_START_F1TV_PAIRING) < order.index(
        CONF_LIVE_TIMING_AUTH_HEADER
    )


async def test_user_flow_stores_trimmed_live_timing_auth_header(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )

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


async def test_user_flow_can_start_f1tv_pairing_when_development_ui_disabled(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", False
    )
    token = _jwt(datetime.now(UTC) + timedelta(days=2))

    flow = F1FlowHandler()
    flow.hass = hass
    flow.context = {"source": "user"}
    flow.flow_id = "flow-id"

    result = await flow.async_step_user(
        {
            "sensor_name": "RaceHub",
            "enabled_sensors": ["next_race"],
            "enable_race_control": False,
            CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
            CONF_OPERATION_MODE: DEFAULT_OPERATION_MODE,
            CONF_REPLAY_FILE: "",
            CONF_START_F1TV_PAIRING: True,
        },
    )

    assert result["type"] == "external"
    assert result["step_id"] == "f1tv_pairing"
    assert "subscription_token" not in result["url"]

    helper_url = URL(result["url"])
    status, response = await async_process_f1tv_pairing_callback(
        hass,
        {
            "session_id": helper_url.query["session_id"],
            "nonce": helper_url.query["nonce"],
            "subscription_token": token,
        },
    )

    assert status is HTTPStatus.OK
    assert response["ok"] is True

    result = await flow.async_step_f1tv_pairing(
        {"session_id": helper_url.query["session_id"]}
    )
    assert result["type"] == "external_done"

    result = await flow.async_step_f1tv_pairing_complete()

    assert result["type"] == "create_entry"
    assert result["title"] == "RaceHub"
    assert result["data"][CONF_LIVE_TIMING_AUTH_HEADER] == f"Bearer {token}"


async def test_reconfigure_shows_auth_but_hides_development_fields_when_development_ui_disabled(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", False
    )
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
    assert CONF_OPERATION_MODE not in keys
    assert CONF_REPLAY_FILE not in keys
    assert CONF_LIVE_TIMING_AUTH_HEADER in keys
    assert "clear_live_timing_auth_header" not in keys
    assert CONF_START_F1TV_PAIRING in keys
    order = _schema_key_order(result)
    assert order.index(CONF_START_F1TV_PAIRING) < order.index(
        CONF_LIVE_TIMING_AUTH_HEADER
    )


async def test_reconfigure_can_start_f1tv_pairing_when_development_ui_disabled(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", False
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enable_race_control": False,
            "disabled_sensors": [],
            CONF_OPERATION_MODE: DEFAULT_OPERATION_MODE,
            CONF_REPLAY_FILE: "",
            CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
        },
    )
    entry.add_to_hass(hass)

    flow = F1FlowHandler()
    flow.hass = hass
    flow.context = {"source": "reconfigure", "entry_id": entry.entry_id}
    flow.flow_id = "flow-id"

    result = await flow.async_step_reconfigure(
        {
            "sensor_name": "F1",
            "enabled_sensors": ["next_race"],
            "enable_race_control": False,
            CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
            CONF_OPERATION_MODE: DEFAULT_OPERATION_MODE,
            CONF_REPLAY_FILE: "",
            CONF_START_F1TV_PAIRING: True,
        },
    )

    assert result["type"] == "external"
    assert result["step_id"] == "f1tv_pairing"
    assert "subscription_token" not in result["url"]


async def test_reconfigure_blank_auth_header_keeps_existing_value(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )

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


async def test_reconfigure_ignores_legacy_clear_auth_header(hass, monkeypatch) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )

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
    assert entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == "Bearer existing-token"


async def test_reauth_updates_auth_header(hass, monkeypatch) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )

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
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )

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
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )

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


async def test_reauth_is_available_when_development_ui_disabled(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", False
    )
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

    assert result["type"] == "form"
    keys = _schema_key_names(result)
    assert CONF_LIVE_TIMING_AUTH_HEADER in keys
    assert CONF_START_F1TV_PAIRING in keys
    order = _schema_key_order(result)
    assert order.index(CONF_START_F1TV_PAIRING) < order.index(
        CONF_LIVE_TIMING_AUTH_HEADER
    )
    assert CONF_LIVE_TIMING_AUTH_HEADER not in _schema_required_key_names(result)


async def test_reauth_is_hidden_when_f1tv_auth_disabled(hass, monkeypatch) -> None:
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", False)
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
