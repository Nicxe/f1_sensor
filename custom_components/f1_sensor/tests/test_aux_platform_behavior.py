"""Behavior coverage for small configuration entity platforms."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from custom_components.f1_sensor import (
    number as number_platform,
    select as select_platform,
    switch as switch_platform,
)
from custom_components.f1_sensor.const import DOMAIN, LIVE_DELAY_REFERENCE_LAP_SYNC
from custom_components.f1_sensor.favorite_driver import (
    FAVORITE_DRIVER_NONE,
    FavoriteDriverController,
)
from custom_components.f1_sensor.number import F1LiveDelayNumber
from custom_components.f1_sensor.select import (
    F1FavoriteDriverSelect,
    F1LiveDelayReferenceSelect,
)
from custom_components.f1_sensor.switch import (
    F1DelayCalibrationSwitch,
    F1NoSpoilerSwitch,
)


class _ListenerController:
    def __init__(self, current=0) -> None:
        self.current = current
        self.listener = None
        self.remove = Mock()
        self.async_set_delay = AsyncMock()
        self.async_set_reference = AsyncMock()

    def add_listener(self, listener):
        self.listener = listener
        return self.remove


def _entry():
    return SimpleNamespace(
        entry_id="entry",
        data={"sensor_name": "F1"},
        options={},
        runtime_data=None,
    )


async def test_number_platform_setup_and_entity_lifecycle(hass) -> None:
    entry = _entry()
    add_entities = Mock()
    await number_platform.async_setup_entry(hass, entry, add_entities)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"other": True}
    await number_platform.async_setup_entry(hass, entry, add_entities)
    add_entities.assert_not_called()

    controller = _ListenerController(12)
    calibration = SimpleNamespace(add_listener=Mock(return_value=Mock()))
    hass.data[DOMAIN][entry.entry_id] = {
        "live_delay_controller": controller,
        "calibration_manager": calibration,
    }
    await number_platform.async_setup_entry(hass, entry, add_entities)
    entity = add_entities.call_args.args[0][0]
    assert entity.entity_id == "number.f1_live_delay"

    entity.hass = hass
    entity.entity_id = "number.test"
    entity.async_write_ha_state = Mock()
    entity._handle_delay_update(12)
    entity._handle_delay_update(14)
    await entity.async_set_native_value(14.6)
    controller.async_set_delay.assert_awaited_once_with(15, source="number_entity")
    entity._handle_calibration_update({"mode": "running", "elapsed": 1.26})
    assert entity.extra_state_attributes["calibration_elapsed"] == 1.3
    await entity.async_will_remove_from_hass()
    controller.remove.assert_called_once()

    def fail_remove():
        raise RuntimeError("remove")

    entity = F1LiveDelayNumber(controller, calibration, "uid2", "entry", "F1")
    entity._controller_unsub = fail_remove
    entity._calibration_unsub = fail_remove
    await entity.async_will_remove_from_hass()


async def test_select_platform_setup_and_reference_lifecycle(hass) -> None:
    entry = _entry()
    add_entities = Mock()
    await select_platform.async_setup_entry(hass, entry, add_entities)
    add_entities.assert_not_called()

    reference = _ListenerController("session")
    favorite = FavoriteDriverController(
        hass,
        entry.entry_id,
        SimpleNamespace(data={"drivers": {}}, available=True),
    )
    replay = SimpleNamespace(session_manager=SimpleNamespace())
    start_reference = _ListenerController("formation")
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "delay_reference_controller": reference,
        "favorite_driver_controller": favorite,
        "replay_controller": replay,
        "replay_start_reference_controller": start_reference,
    }
    await select_platform.async_setup_entry(hass, entry, add_entities)
    assert len(add_entities.call_args.args[0]) == 5

    entity = F1LiveDelayReferenceSelect(reference, "uid", "entry", "F1")
    entity.hass = hass
    entity.entity_id = "select.test"
    entity.async_write_ha_state = Mock()
    await entity.async_added_to_hass()
    await entity.async_select_option("Lap sync (race/sprint)")
    reference.async_set_reference.assert_awaited_with(
        LIVE_DELAY_REFERENCE_LAP_SYNC, source="select_entity"
    )
    await entity.async_select_option("unknown")
    reference.listener("unknown")
    await entity.async_will_remove_from_hass()
    reference.remove.assert_called_once()

    entity._unsub = Mock(side_effect=RuntimeError("remove"))
    await entity.async_will_remove_from_hass()


async def test_favorite_driver_select_behavior(hass) -> None:
    controller = SimpleNamespace(
        options=["HAM", "VER"],
        selected_tla=None,
        add_listener=Mock(return_value=Mock()),
        async_set_driver=AsyncMock(),
    )
    entity = F1FavoriteDriverSelect(controller, "uid", "entry", "F1")
    assert entity.options == [FAVORITE_DRIVER_NONE, "HAM", "VER"]
    assert entity.current_option == FAVORITE_DRIVER_NONE
    await entity.async_added_to_hass()
    await entity.async_select_option(FAVORITE_DRIVER_NONE)
    await entity.async_select_option("VER")
    assert [call.args[0] for call in controller.async_set_driver.await_args_list] == [
        None,
        "VER",
    ]
    entity.hass = hass
    entity.entity_id = "select.favorite"
    entity.async_write_ha_state = Mock()
    entity._handle_update()
    await entity.async_will_remove_from_hass()


async def test_switch_entities_delegate_and_publish_snapshots(hass) -> None:
    calibration = SimpleNamespace(
        add_listener=Mock(return_value=Mock()),
        async_prepare=AsyncMock(),
        async_cancel=AsyncMock(),
    )
    entity = F1DelayCalibrationSwitch(calibration, "uid", "entry", "F1")
    entity.hass = hass
    entity.entity_id = "switch.calibration"
    entity.async_write_ha_state = Mock()
    await entity.async_turn_on()
    await entity.async_turn_off()
    calibration.async_prepare.assert_awaited_once_with(source="switch")
    calibration.async_cancel.assert_awaited_once_with(source="switch")
    entity._handle_snapshot({"mode": "waiting", "reference": "lap", "elapsed": 2})
    assert entity.is_on is True
    assert entity.extra_state_attributes["mode"] == "waiting"
    await entity.async_will_remove_from_hass()

    no_spoiler = SimpleNamespace(
        is_active=False,
        add_listener=Mock(return_value=Mock()),
        async_set_active=AsyncMock(),
    )
    spoiler = F1NoSpoilerSwitch(no_spoiler, "uid2", "entry", "F1")
    spoiler.hass = hass
    spoiler.entity_id = "switch.spoiler"
    spoiler.async_write_ha_state = Mock()
    await spoiler.async_turn_on()
    await spoiler.async_turn_off()
    spoiler._handle_state_change(True)
    assert spoiler.is_on is True
    await spoiler.async_will_remove_from_hass()


async def test_switch_platform_owns_global_no_spoiler_entity_once(hass) -> None:
    entry = _entry()
    add_entities = Mock()
    await switch_platform.async_setup_entry(hass, entry, add_entities)
    add_entities.assert_not_called()

    calibration = SimpleNamespace(add_listener=Mock(return_value=Mock()))
    no_spoiler = SimpleNamespace(
        is_active=False,
        add_listener=Mock(return_value=Mock()),
    )
    root = hass.data.setdefault(DOMAIN, {})
    root[entry.entry_id] = {"calibration_manager": calibration}
    root["no_spoiler_manager"] = no_spoiler
    root["no_spoiler_switch_entry_id"] = "stale"
    await switch_platform.async_setup_entry(hass, entry, add_entities)
    assert len(add_entities.call_args.args[0]) == 2
    assert root["no_spoiler_switch_entry_id"] == entry.entry_id
