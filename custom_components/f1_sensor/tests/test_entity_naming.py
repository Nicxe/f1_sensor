from __future__ import annotations

import logging
from unittest.mock import Mock

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import EntityComponent
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import (
    binary_sensor as binary_sensor_platform,
    button as button_platform,
    calendar as calendar_platform,
    media_player as media_player_platform,
    number as number_platform,
    select as select_platform,
    sensor as sensor_platform,
    switch as switch_platform,
)
from custom_components.f1_sensor.const import (
    CONF_ENTITY_NAME_LANGUAGE,
    CONF_ENTITY_NAME_MODE,
    DOMAIN,
    ENTITY_NAME_MODE_LOCALIZED,
    SUPPORTED_SENSOR_KEYS,
)
from custom_components.f1_sensor.entity import (
    async_prepare_translation_names,
    register_entry_name_settings,
)
from custom_components.f1_sensor.helpers import format_entity_name
from custom_components.f1_sensor.number import F1LiveDelayNumber

_LOGGER = logging.getLogger(__name__)


class _DummyDelayController:
    def __init__(self, current: int = 0) -> None:
        self.current = current

    def add_listener(self, _callback):
        return lambda: None


class _DummyListenerManager:
    def __init__(self, *, current=None, is_active: bool = False) -> None:
        self.current = current
        self.is_active = is_active

    def add_listener(self, _callback):
        return lambda: None


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


@pytest.mark.asyncio
async def test_binary_sensor_setup_entry_registers_safety_car_entity(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "RaceHub",
            "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS - {"safety_car"}),
        },
    )
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "track_status_coordinator": Mock(),
    }

    async_add_entities = Mock()
    await binary_sensor_platform.async_setup_entry(hass, entry, async_add_entities)

    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1

    entity = entities[0]
    assert entity.unique_id == f"{entry.entry_id}_safety_car"
    assert entity._attr_translation_key == "safety_car"
    assert entity._attr_suggested_object_id == "f1_safety_car"
    assert entity.name == "Safety car"

    component = EntityComponent(_LOGGER, "binary_sensor", hass)
    await component.async_add_entities([entity])
    await hass.async_block_till_done()

    assert entity.entity_id == "binary_sensor.f1_safety_car"

    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.attributes["friendly_name"] == "Safety car"

    registry = er.async_get(hass)
    registry_entry = registry.async_get(entity.entity_id)
    assert registry_entry is not None
    assert registry_entry.entity_id == "binary_sensor.f1_safety_car"
    assert registry_entry.unique_id == f"{entry.entry_id}_safety_car"


def test_aux_entity_localized_name_uses_entry_language() -> None:
    entry_id = "localized_entry"
    register_entry_name_settings(
        entry_id,
        {
            CONF_ENTITY_NAME_MODE: ENTITY_NAME_MODE_LOCALIZED,
            CONF_ENTITY_NAME_LANGUAGE: "sv-SE",
        },
    )
    entity = F1LiveDelayNumber(
        controller=_DummyDelayController(12),
        calibration=None,
        unique_id="localized_delay",
        entry_id=entry_id,
        device_name="RaceHub",
    )

    assert entity.name == "Livefördröjning"
    assert entity.suggested_object_id == "f1_live_delay"


@pytest.mark.asyncio
async def test_localized_aux_entity_keeps_english_entity_id(hass) -> None:
    hass.config.language = "sv"
    entry_id = "localized_number_entry"
    register_entry_name_settings(
        entry_id,
        {
            CONF_ENTITY_NAME_MODE: ENTITY_NAME_MODE_LOCALIZED,
            CONF_ENTITY_NAME_LANGUAGE: "sv",
        },
    )
    await async_prepare_translation_names(hass, entry_id)
    entity = F1LiveDelayNumber(
        controller=_DummyDelayController(7),
        calibration=None,
        unique_id="localized_delay_number",
        entry_id=entry_id,
        device_name="RaceHub",
    )

    component = EntityComponent(_LOGGER, "number", hass)
    await component.async_add_entities([entity])
    await hass.async_block_till_done()

    assert entity.entity_id == "number.f1_live_delay"
    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.attributes["friendly_name"] == "Livefördröjning"


@pytest.mark.asyncio
async def test_localized_aux_entity_name_uses_preloaded_translations_only(
    hass, monkeypatch
) -> None:
    entry_id = "localized_preload_entry"
    register_entry_name_settings(
        entry_id,
        {
            CONF_ENTITY_NAME_MODE: ENTITY_NAME_MODE_LOCALIZED,
            CONF_ENTITY_NAME_LANGUAGE: "sv",
        },
    )
    await async_prepare_translation_names(hass, entry_id)

    def _fail_read_text(*_args, **_kwargs):
        raise AssertionError("translation files should already be cached")

    monkeypatch.setattr("pathlib.Path.read_text", _fail_read_text)

    entity = F1LiveDelayNumber(
        controller=_DummyDelayController(7),
        calibration=None,
        unique_id="localized_delay_number",
        entry_id=entry_id,
        device_name="RaceHub",
    )

    assert entity.name == "Livefördröjning"


@pytest.mark.asyncio
async def test_legacy_entry_keeps_english_name_and_entity_id(hass) -> None:
    hass.config.language = "sv"
    entry_id = "legacy_number_entry"
    register_entry_name_settings(entry_id, {})
    entity = F1LiveDelayNumber(
        controller=_DummyDelayController(3),
        calibration=None,
        unique_id="legacy_delay_number",
        entry_id=entry_id,
        device_name="RaceHub",
    )

    component = EntityComponent(_LOGGER, "number", hass)
    await component.async_add_entities([entity])
    await hass.async_block_till_done()

    assert entity.entity_id == "number.f1_live_delay"
    state = hass.states.get(entity.entity_id)
    assert state is not None
    assert state.attributes["friendly_name"] == "Live delay"


def test_mode_entities_use_standard_english_object_ids() -> None:
    coordinator = Mock()

    straight_mode = sensor_platform.F1StraightModeSensor(
        coordinator,
        "straight_mode_unique_id",
        "entry_id",
        "Loppcentral",
    )
    overtake_mode = binary_sensor_platform.F1OvertakeModeBinarySensor(
        coordinator,
        "overtake_mode_unique_id",
        "entry_id",
        "Loppcentral",
    )

    assert straight_mode._attr_suggested_object_id == "f1_straight_mode"
    assert overtake_mode._attr_suggested_object_id == "f1_overtake_mode"


@pytest.mark.asyncio
async def test_aux_platforms_use_standard_english_object_ids(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "Loppcentral"})
    entry.add_to_hass(hass)

    replay_controller = Mock(session_manager=Mock())
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "calibration_manager": _DummyListenerManager(),
        "delay_reference_controller": _DummyListenerManager(current="session"),
        "live_delay_controller": _DummyDelayController(5),
        "race_coordinator": Mock(last_update_success=True),
        "replay_controller": replay_controller,
        "replay_start_reference_controller": _DummyListenerManager(current="formation"),
    }
    hass.data[DOMAIN]["no_spoiler_manager"] = _DummyListenerManager(is_active=False)

    add_number_entities = Mock()
    await number_platform.async_setup_entry(hass, entry, add_number_entities)
    number_entities = add_number_entities.call_args[0][0]
    assert number_entities[0].suggested_object_id == "f1_live_delay"

    add_select_entities = Mock()
    await select_platform.async_setup_entry(hass, entry, add_select_entities)
    select_entities = {
        entity.unique_id: entity.suggested_object_id
        for entity in add_select_entities.call_args[0][0]
    }
    assert select_entities[f"{entry.entry_id}_live_delay_reference"] == (
        "f1_live_delay_reference"
    )
    assert select_entities[f"{entry.entry_id}_replay_year_select"] == "f1_replay_year"
    assert select_entities[f"{entry.entry_id}_replay_session_select"] == (
        "f1_replay_session"
    )
    assert select_entities[f"{entry.entry_id}_replay_start_reference"] == (
        "f1_replay_start_reference"
    )

    add_button_entities = Mock()
    await button_platform.async_setup_entry(hass, entry, add_button_entities)
    button_entities = {
        entity.unique_id: entity.suggested_object_id
        for entity in add_button_entities.call_args[0][0]
    }
    assert button_entities[f"{entry.entry_id}_delay_calibration_match"] == (
        "f1_delay_calibration_match"
    )
    assert button_entities[f"{entry.entry_id}_replay_load"] == "f1_replay_load"
    assert button_entities[f"{entry.entry_id}_replay_play"] == "f1_replay_play"
    assert button_entities[f"{entry.entry_id}_replay_pause"] == "f1_replay_pause"
    assert button_entities[f"{entry.entry_id}_replay_back_30"] == "f1_replay_back_30"
    assert button_entities[f"{entry.entry_id}_replay_forward_30"] == (
        "f1_replay_forward_30"
    )
    assert button_entities[f"{entry.entry_id}_replay_stop"] == "f1_replay_stop"
    assert button_entities[f"{entry.entry_id}_replay_refresh"] == "f1_replay_refresh"

    add_switch_entities = Mock()
    await switch_platform.async_setup_entry(hass, entry, add_switch_entities)
    switch_entities = {
        entity.unique_id: entity.suggested_object_id
        for entity in add_switch_entities.call_args[0][0]
    }
    assert switch_entities[f"{entry.entry_id}_delay_calibration_switch"] == (
        "f1_delay_calibration"
    )
    assert switch_entities["f1_sensor_no_spoiler_mode"] == "f1_no_spoiler_mode"

    add_media_player_entities = Mock()
    await media_player_platform.async_setup_entry(
        hass, entry, add_media_player_entities
    )
    media_player_entities = add_media_player_entities.call_args[0][0]
    assert media_player_entities[0].suggested_object_id == "f1_replay_player"

    add_calendar_entities = Mock()
    await calendar_platform.async_setup_entry(hass, entry, add_calendar_entities)
    calendar_entities = add_calendar_entities.call_args[0][0]
    assert calendar_entities[0].suggested_object_id == "f1_season_calendar"


@pytest.mark.asyncio
async def test_live_delay_reference_select_hides_formation_start_option(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "RaceHub"})
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "delay_reference_controller": _DummyListenerManager(current="session_live"),
        "formation_start_tracker": Mock(),
    }

    async_add_entities = Mock()
    await select_platform.async_setup_entry(hass, entry, async_add_entities)

    entities = {
        entity.unique_id: entity for entity in async_add_entities.call_args[0][0]
    }
    select_entity = entities[f"{entry.entry_id}_live_delay_reference"]

    assert select_entity.options == [
        "Session live",
        "Lap sync (race/sprint)",
    ]


@pytest.mark.asyncio
async def test_replay_status_sensor_uses_standard_english_object_id(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "RaceHub",
            "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS),
        },
    )
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "constructor_coordinator": Mock(),
        "driver_coordinator": Mock(),
        "last_race_coordinator": Mock(),
        "race_coordinator": Mock(),
        "replay_controller": Mock(session_manager=Mock()),
        "season_results_coordinator": Mock(),
        "sprint_results_coordinator": Mock(),
    }

    async_add_entities = Mock()
    await sensor_platform.async_setup_entry(hass, entry, async_add_entities)

    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert entities[0].unique_id == f"{entry.entry_id}_replay_status"
    assert entities[0].suggested_object_id == "f1_replay_status"
