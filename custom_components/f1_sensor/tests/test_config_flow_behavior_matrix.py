"""Behavior matrix for configuration, reauthentication, and options flows."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import config_flow
from custom_components.f1_sensor.config_flow import F1FlowHandler, F1OptionsFlow
from custom_components.f1_sensor.const import (
    CONF_LIVE_TIMING_AUTH_HEADER,
    CONF_OPERATION_MODE,
    CONF_RACE_WEEK_START_DAY,
    CONF_RACE_WEEK_SUNDAY_START,
    CONF_REPLAY_FILE,
    DEFAULT_ENTITY_NAME_LANGUAGE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
    RACE_WEEK_START_MONDAY,
    RACE_WEEK_START_SATURDAY,
    RACE_WEEK_START_SUNDAY,
)


def _flow(hass, source="user", entry_id=None) -> F1FlowHandler:
    flow = F1FlowHandler()
    flow.hass = hass
    flow.context = {"source": source}
    if entry_id is not None:
        flow.context["entry_id"] = entry_id
    flow.flow_id = "flow-id"
    return flow


def _user_input(**updates) -> dict:
    data = {
        "sensor_name": "F1",
        "enabled_sensors": ["next_race"],
        "enable_race_control": False,
        CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        CONF_REPLAY_FILE: "",
    }
    data.update(updates)
    return data


def _entry(hass, **data_updates) -> MockConfigEntry:
    data = {
        "sensor_name": "F1",
        "enable_race_control": False,
        CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
    }
    data.update(data_updates)
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    return entry


def _schema_default(result: dict, name: str):
    marker = next(key for key in result["data_schema"].schema if key.schema == name)
    return marker.default()


def test_language_race_week_and_payload_helpers(hass, monkeypatch) -> None:
    flow = _flow(hass)
    hass.config.language = None
    assert flow._current_backend_language() == DEFAULT_ENTITY_NAME_LANGUAGE
    hass.config.language = " pt_BR "
    assert flow._current_backend_language() == "pt-BR"
    hass.config.language = " "
    assert flow._current_backend_language() == DEFAULT_ENTITY_NAME_LANGUAGE

    assert flow._normalize_race_week_start({CONF_RACE_WEEK_SUNDAY_START: True}) == (
        RACE_WEEK_START_SUNDAY
    )
    assert flow._normalize_race_week_start({CONF_RACE_WEEK_SUNDAY_START: False}) == (
        RACE_WEEK_START_MONDAY
    )
    assert (
        flow._normalize_race_week_start(
            {CONF_RACE_WEEK_SUNDAY_START: RACE_WEEK_START_SATURDAY}
        )
        == RACE_WEEK_START_SATURDAY
    )
    assert flow._normalize_race_week_start({}) == RACE_WEEK_START_MONDAY

    data, options = config_flow._split_entry_payload(
        {"sensor_name": "F1", "disabled_sensors": ["weather"]}
    )
    assert data == {"sensor_name": "F1"}
    assert options == {"disabled_sensors": ["weather"]}
    assert isinstance(F1FlowHandler.async_get_options_flow(Mock()), F1OptionsFlow)


async def test_user_development_replay_validation_matrix(
    hass, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(config_flow.const, "ENABLE_DEVELOPMENT_MODE_UI", True)
    missing = await _flow(hass).async_step_user(_user_input())
    assert missing["errors"][CONF_REPLAY_FILE] == "replay_required"

    invalid = await _flow(hass).async_step_user(
        _user_input(**{CONF_REPLAY_FILE: str(tmp_path / "missing.jsonl")})
    )
    assert invalid["errors"][CONF_REPLAY_FILE] == "replay_missing"

    replay = tmp_path / "race.jsonl"
    replay.write_text("{}\n", encoding="utf-8")
    valid = await _flow(hass).async_step_user(
        _user_input(**{CONF_REPLAY_FILE: f" {replay} "})
    )
    assert valid["type"] == "create_entry"
    assert valid["options"][CONF_REPLAY_FILE] == str(replay)


async def test_reconfigure_development_and_legacy_sensor_defaults(
    hass, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(config_flow.const, "ENABLE_DEVELOPMENT_MODE_UI", True)
    entry = _entry(hass, enabled_sensors=["next_session", "next_session", "bad"])
    flow = _flow(hass, "reconfigure", entry.entry_id)
    form = await flow.async_step_reconfigure()
    enabled = _schema_default(form, "enabled_sensors")
    assert enabled[0] == "next_race"
    assert "favorite_driver" not in enabled

    required = await flow.async_step_reconfigure(_user_input())
    assert required["errors"][CONF_REPLAY_FILE] == "replay_required"
    missing = await flow.async_step_reconfigure(
        _user_input(**{CONF_REPLAY_FILE: str(tmp_path / "missing.jsonl")})
    )
    assert missing["errors"][CONF_REPLAY_FILE] == "replay_missing"

    replay = tmp_path / "race.jsonl"
    replay.write_text("{}\n", encoding="utf-8")
    updated = await flow.async_step_reconfigure(
        _user_input(**{CONF_REPLAY_FILE: str(replay)})
    )
    assert updated["type"] == "abort"
    assert entry.options[CONF_REPLAY_FILE] == str(replay)


async def test_reconfigure_defaults_when_no_sensor_selection_exists(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(config_flow.const, "ENABLE_DEVELOPMENT_MODE_UI", False)
    entry = _entry(hass)
    result = await _flow(hass, "reconfigure", entry.entry_id).async_step_reconfigure()
    assert result["type"] == "form"
    assert "favorite_driver" not in _schema_default(result, "enabled_sensors")


async def test_pairing_unavailable_failed_and_reconfigure_completion(
    hass, monkeypatch
) -> None:
    flow = _flow(hass)
    monkeypatch.setattr(config_flow.const, "ENABLE_F1TV_AUTH", False)
    assert (await flow._async_start_f1tv_pairing(None))["reason"] == (
        "f1tv_pairing_unavailable"
    )
    assert (await flow.async_step_f1tv_pairing({"session_id": "x"}))["reason"] == (
        "f1tv_pairing_unavailable"
    )
    assert (await flow.async_step_reauth_confirm())["reason"] == (
        "reauth_not_supported"
    )

    monkeypatch.setattr(config_flow.const, "ENABLE_F1TV_AUTH", True)
    monkeypatch.setattr(
        config_flow, "async_create_f1tv_pairing_session", Mock(return_value=None)
    )
    assert (await flow._async_start_f1tv_pairing(None))["reason"] == (
        "f1tv_pairing_unavailable"
    )
    assert (await flow.async_step_f1tv_pairing())["step_id"] == "f1tv_pairing_failed"
    assert (await flow.async_step_f1tv_pairing_failed())["reason"] == (
        "f1tv_pairing_failed"
    )
    assert (await flow.async_step_f1tv_pairing_complete())["reason"] == (
        "reconfigure_successful"
    )

    flow._pending_f1tv_setup_data = {"sensor_name": "F1"}
    flow._completed_f1tv_pairing_session_id = "missing"
    monkeypatch.setattr(
        config_flow, "async_pop_f1tv_pairing_session_result", Mock(return_value=None)
    )
    assert (await flow.async_step_f1tv_pairing_complete())["reason"] == (
        "f1tv_pairing_failed"
    )


async def test_reauth_invalid_header_and_pairing_start(hass, monkeypatch) -> None:
    entry = _entry(hass)
    flow = _flow(hass, "reauth", entry.entry_id)
    invalid = await flow.async_step_reauth_confirm(
        {CONF_LIVE_TIMING_AUTH_HEADER: "Bearer bad"}
    )
    assert invalid["errors"][CONF_LIVE_TIMING_AUTH_HEADER] == "invalid_auth_header"

    flow._async_start_f1tv_pairing = AsyncMock(return_value={"type": "external"})
    result = await flow.async_step_reauth_confirm({"start_f1tv_pairing": True})
    assert result == {"type": "external"}
    flow._async_start_f1tv_pairing.assert_awaited_once_with(entry)


async def test_options_flow_replay_validation_and_save(
    hass, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(config_flow.const, "ENABLE_DEVELOPMENT_MODE_UI", True)
    entry = _entry(hass, disabled_sensors=["weather"])
    flow = config_flow.F1FlowHandler.async_get_options_flow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id

    form = await flow.async_step_init()
    assert form["type"] == "form"
    assert "weather" not in _schema_default(form, "enabled_sensors")
    assert CONF_OPERATION_MODE in {key.schema for key in form["data_schema"].schema}

    required = await flow.async_step_init(
        {
            "enabled_sensors": ["next_race"],
            CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
            CONF_REPLAY_FILE: "",
        }
    )
    assert required["errors"][CONF_REPLAY_FILE] == "replay_required"
    missing = await flow.async_step_init(
        {
            "enabled_sensors": ["next_race"],
            CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
            CONF_REPLAY_FILE: str(tmp_path / "missing"),
        }
    )
    assert missing["errors"][CONF_REPLAY_FILE] == "replay_missing"

    replay = tmp_path / "race.jsonl"
    replay.write_text("{}\n", encoding="utf-8")
    saved = await flow.async_step_init(
        {
            "enabled_sensors": ["next_race"],
            CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
            CONF_REPLAY_FILE: str(replay),
        }
    )
    assert saved["type"] == "create_entry"
    assert saved["data"][CONF_REPLAY_FILE] == str(replay)


async def test_replay_file_validators_handle_executor_failures(hass, tmp_path) -> None:
    replay = tmp_path / "race.jsonl"
    replay.write_text("{}\n", encoding="utf-8")
    flow = _flow(hass)
    assert await flow._validate_replay_file(str(replay)) is True
    assert await config_flow._async_validate_replay_file(hass, str(replay)) is True

    failing_hass = SimpleNamespace(
        async_add_executor_job=AsyncMock(side_effect=RuntimeError("executor failed"))
    )
    flow.hass = failing_hass
    assert await flow._validate_replay_file(str(replay)) is False
    assert (
        await config_flow._async_validate_replay_file(failing_hass, str(replay))
        is False
    )
