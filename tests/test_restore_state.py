import importlib.util
import sys
import types
from pathlib import Path

import pytest

# Reuse environment setup from test_flag_safety but add RestoreEntity stub
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

# timezonefinder stub
tf = types.ModuleType("timezonefinder")
tf.TimezoneFinder = object
sys.modules.setdefault("timezonefinder", tf)

# homeassistant stubs
homeassistant = types.ModuleType("homeassistant")
components = types.ModuleType("homeassistant.components")
sensor_mod = types.ModuleType("homeassistant.components.sensor")
binary_mod = types.ModuleType("homeassistant.components.binary_sensor")

sensor_mod.SensorEntity = type("SensorEntity", (), {})
sensor_mod.SensorDeviceClass = type("SensorDeviceClass", (), {})
binary_mod.BinarySensorEntity = type("BinarySensorEntity", (), {})
binary_mod.BinarySensorDeviceClass = type("BinarySensorDeviceClass", (), {})
components.sensor = sensor_mod
components.binary_sensor = binary_mod
homeassistant.components = components

helpers = types.ModuleType("homeassistant.helpers")
aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")

def async_get_clientsession(hass):
    return None

aiohttp_client.async_get_clientsession = async_get_clientsession
update = types.ModuleType("homeassistant.helpers.update_coordinator")
update.DataUpdateCoordinator = object
update.UpdateFailed = Exception

class CoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator

update.CoordinatorEntity = CoordinatorEntity
helpers.aiohttp_client = aiohttp_client
helpers.update_coordinator = update

# restore_state stub
restore_state = types.ModuleType("homeassistant.helpers.restore_state")

class FakeState:
    def __init__(self, state, attributes):
        self.state = state
        self.attributes = attributes

restore_state.LAST_STATE = None

class RestoreEntity:
    async def async_get_last_state(self):
        return restore_state.LAST_STATE

    async def async_added_to_hass(self):
        return None

    async def async_will_remove_from_hass(self):
        return None

restore_state.RestoreEntity = RestoreEntity
helpers.restore_state = restore_state

homeassistant.helpers = helpers

config_entries = types.ModuleType("homeassistant.config_entries")
config_entries.ConfigEntry = type("ConfigEntry", (), {})
homeassistant.config_entries = config_entries
core = types.ModuleType("homeassistant.core")
core.HomeAssistant = type("HomeAssistant", (), {})
homeassistant.core = core

sys.modules.setdefault("homeassistant", homeassistant)
sys.modules.setdefault("homeassistant.components", components)
sys.modules.setdefault("homeassistant.components.sensor", sensor_mod)
sys.modules.setdefault("homeassistant.components.binary_sensor", binary_mod)
sys.modules.setdefault("homeassistant.helpers", helpers)
sys.modules.setdefault("homeassistant.helpers.aiohttp_client", aiohttp_client)
sys.modules.setdefault("homeassistant.helpers.update_coordinator", update)
sys.modules.setdefault("homeassistant.helpers.restore_state", restore_state)
sys.modules.setdefault("homeassistant.config_entries", config_entries)
sys.modules.setdefault("homeassistant.core", core)

sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
cc_f1 = types.ModuleType("custom_components.f1_sensor")
cc_f1.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("custom_components.f1_sensor", cc_f1)

# load modules
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

spec_helpers = importlib.util.spec_from_file_location(
    "custom_components.f1_sensor.helpers",
    Path("custom_components/f1_sensor/helpers.py"),
)
helpers_mod = importlib.util.module_from_spec(spec_helpers)
sys.modules["custom_components.f1_sensor.helpers"] = helpers_mod
spec_helpers.loader.exec_module(helpers_mod)

spec_sensor = importlib.util.spec_from_file_location(
    "custom_components.f1_sensor.sensor",
    Path("custom_components/f1_sensor/sensor.py"),
)
sensor = importlib.util.module_from_spec(spec_sensor)
sys.modules["custom_components.f1_sensor.sensor"] = sensor
spec_sensor.loader.exec_module(sensor)

F1RaceControlSensor = sensor.F1RaceControlSensor
F1FlagSensor = sensor.F1FlagSensor

class DummyCoordinator:
    def __init__(self):
        self.data = None
        self.data_list = []

    def async_add_listener(self, cb):
        pass


@pytest.mark.asyncio
async def test_racecontrol_restore_state():
    restore_state.LAST_STATE = FakeState("15", {"Message": "OK"})
    coord = DummyCoordinator()
    ent = F1RaceControlSensor(coord, "rc", "uid", "entry", "F1")
    await ent.async_added_to_hass()
    assert ent.state == "15"


@pytest.mark.asyncio
async def test_flag_restore_state():
    restore_state.LAST_STATE = FakeState(
        "yellow",
        {"track_red": False, "vsc_active": False, "active_yellow_sectors": [2]},
    )
    coord = DummyCoordinator()
    ent = F1FlagSensor(coord, "flag", "uid", "entry", "F1")
    await ent.async_added_to_hass()
    assert ent.state == "yellow"
    assert ent.extra_state_attributes["active_yellow_sectors"] == [2]
