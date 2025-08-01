import importlib.util
import sys
import types
from pathlib import Path
import asyncio
import pytest

restore_value = None

class FakeState:
    def __init__(self, state, attributes=None):
        self.state = state
        self.attributes = attributes or {}

@pytest.fixture
def sensor_module():
    async_timeout_mod = types.ModuleType("async_timeout")
    class _Dummy:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
    def timeout(_):
        return _Dummy()
    async_timeout_mod.timeout = timeout
    sys.modules.setdefault("async_timeout", async_timeout_mod)

    tf = types.ModuleType("timezonefinder")
    tf.TimezoneFinder = object
    sys.modules.setdefault("timezonefinder", tf)

    homeassistant = types.ModuleType("homeassistant")
    components = types.ModuleType("homeassistant.components")
    sensor_comp = types.ModuleType("homeassistant.components.sensor")
    sensor_comp.SensorEntity = type(
        "SensorEntity",
        (),
        {"async_write_ha_state": lambda self: None},
    )
    sensor_comp.SensorDeviceClass = type("SensorDeviceClass", (), {})
    components.sensor = sensor_comp
    homeassistant.components = components

    helpers = types.ModuleType("homeassistant.helpers")
    update = types.ModuleType("homeassistant.helpers.update_coordinator")
    update.DataUpdateCoordinator = object
    update.UpdateFailed = Exception
    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator
        async def async_added_to_hass(self):
            pass

    update.CoordinatorEntity = CoordinatorEntity
    helpers.update_coordinator = update

    restore_state = types.ModuleType("homeassistant.helpers.restore_state")
    class RestoreEntity:
        async def async_get_last_state(self):
            return restore_value
    restore_state.RestoreEntity = RestoreEntity
    helpers.restore_state = restore_state

    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client.async_get_clientsession = lambda hass: None
    helpers.aiohttp_client = aiohttp_client

    homeassistant.helpers = helpers

    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = type("ConfigEntry", (), {})
    homeassistant.config_entries = config_entries

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = type("HomeAssistant", (), {})
    homeassistant.core = core

    for name, mod in {
        "homeassistant": homeassistant,
        "homeassistant.components": components,
        "homeassistant.components.sensor": sensor_comp,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.update_coordinator": update,
        "homeassistant.helpers.restore_state": restore_state,
        "homeassistant.helpers.aiohttp_client": aiohttp_client,
        "homeassistant.config_entries": config_entries,
        "homeassistant.core": core,
    }.items():
        sys.modules[name] = mod

    sys.modules["custom_components"] = types.ModuleType("custom_components")
    cc_f1 = types.ModuleType("custom_components.f1_sensor")
    cc_f1.__path__ = []
    sys.modules["custom_components.f1_sensor"] = cc_f1

    spec_const = importlib.util.spec_from_file_location(
        "custom_components.f1_sensor.const",
        Path("custom_components/f1_sensor/const.py"),
    )
    const_mod = importlib.util.module_from_spec(spec_const)
    sys.modules["custom_components.f1_sensor.const"] = const_mod
    spec_const.loader.exec_module(const_mod)

    spec_entity = importlib.util.spec_from_file_location(
        "custom_components.f1_sensor.entity",
        Path("custom_components/f1_sensor/entity.py"),
    )
    entity_mod = importlib.util.module_from_spec(spec_entity)
    sys.modules["custom_components.f1_sensor.entity"] = entity_mod
    spec_entity.loader.exec_module(entity_mod)

    spec_flag = importlib.util.spec_from_file_location(
        "custom_components.f1_sensor.flag_state",
        Path("custom_components/f1_sensor/flag_state.py"),
    )
    flag_mod = importlib.util.module_from_spec(spec_flag)
    sys.modules["custom_components.f1_sensor.flag_state"] = flag_mod
    spec_flag.loader.exec_module(flag_mod)

    spec_sensor = importlib.util.spec_from_file_location(
        "custom_components.f1_sensor.sensor",
        Path("custom_components/f1_sensor/sensor.py"),
    )
    sensor_mod = importlib.util.module_from_spec(spec_sensor)
    sys.modules["custom_components.f1_sensor.sensor"] = sensor_mod
    spec_sensor.loader.exec_module(sensor_mod)

    return sensor_mod

class FakeHass:
    def __init__(self):
        self.data = {}
    def async_create_task(self, coro):
        return asyncio.create_task(coro)

class FakeCoordinator:
    def __init__(self):
        self.data_list = []
    def async_add_listener(self, _):
        pass

@pytest.mark.asyncio
async def test_restore_last_state(sensor_module):
    global restore_value
    hass1 = FakeHass()
    coord1 = FakeCoordinator()
    s1 = sensor_module.F1FlagSensor(coord1, "flag", "uid1", "entry", "dev")
    s1.hass = hass1
    await s1.async_added_to_hass()

    # simulate some state
    s1._machine.state = "yellow"
    s1._machine.track_flag = "yellow"
    s1._machine.vsc_mode = None
    s1._machine.active_yellows = {2}
    s1._update_attrs()

    restore_value = FakeState(s1.state, s1._attr_extra_state_attributes)

    hass2 = FakeHass()
    coord2 = FakeCoordinator()
    s2 = sensor_module.F1FlagSensor(coord2, "flag", "uid2", "entry", "dev")
    s2.hass = hass2
    await s2.async_added_to_hass()

    assert s2.state == "yellow"
    assert s2._attr_extra_state_attributes["track_flag"] == "yellow"
    assert s2._attr_extra_state_attributes["active_sectors"] == [2]
