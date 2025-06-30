import importlib.util
import json
import sys
import types
from pathlib import Path

async_timeout_mod = types.ModuleType("async_timeout")


class _Dummy:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass


def timeout(_):  # noqa: D401 - simplified dummy
    return _Dummy()


async_timeout_mod.timeout = timeout
sys.modules.setdefault("async_timeout", async_timeout_mod)
tf = types.ModuleType("timezonefinder")
tf.TimezoneFinder = object
sys.modules.setdefault("timezonefinder", tf)
homeassistant = types.ModuleType("homeassistant")
components = types.ModuleType("homeassistant.components")
sensor_mod = types.ModuleType("homeassistant.components.sensor")
binary_mod = types.ModuleType("homeassistant.components.binary_sensor")
sensor_mod.SensorEntity = type("SensorEntity", (), {})
sensor_mod.SensorDeviceClass = type("SensorDeviceClass", (), {})
binary_mod.BinarySensorEntity = type("BinarySensorEntity", (), {})
binary_mod.BinarySensorDeviceClass = type(
    "BinarySensorDeviceClass",
    (),
    {"OCCUPANCY": "occupancy", "SAFETY": "safety"},
)
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
update.CoordinatorEntity = object
helpers.aiohttp_client = aiohttp_client
helpers.update_coordinator = update
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
sys.modules.setdefault("homeassistant.config_entries", config_entries)
sys.modules.setdefault("homeassistant.core", core)

sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
cc_f1 = types.ModuleType("custom_components.f1_sensor")
cc_f1.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("custom_components.f1_sensor", cc_f1)

spec_const = importlib.util.spec_from_file_location(
    "custom_components.f1_sensor.const",
    Path("custom_components/f1_sensor/const.py"),
)
assert spec_const and spec_const.loader
const_mod = importlib.util.module_from_spec(spec_const)
sys.modules["custom_components.f1_sensor.const"] = const_mod
spec_const.loader.exec_module(const_mod)

spec_entity = importlib.util.spec_from_file_location(
    "custom_components.f1_sensor.entity",
    Path("custom_components/f1_sensor/entity.py"),
)
assert spec_entity and spec_entity.loader
entity_mod = importlib.util.module_from_spec(spec_entity)
sys.modules["custom_components.f1_sensor.entity"] = entity_mod
spec_entity.loader.exec_module(entity_mod)

spec_helpers = importlib.util.spec_from_file_location(
    "custom_components.f1_sensor.helpers",
    Path("custom_components/f1_sensor/helpers.py"),
)
assert spec_helpers and spec_helpers.loader
helpers_mod = importlib.util.module_from_spec(spec_helpers)
sys.modules["custom_components.f1_sensor.helpers"] = helpers_mod
spec_helpers.loader.exec_module(helpers_mod)

spec = importlib.util.spec_from_file_location(
    "custom_components.f1_sensor.sensor",
    Path("custom_components/f1_sensor/sensor.py"),
)
assert spec and spec.loader
sensor = importlib.util.module_from_spec(spec)
sys.modules["custom_components.f1_sensor.sensor"] = sensor
spec.loader.exec_module(sensor)
FlagStateMachine = sensor.FlagStateMachine

spec_bs = importlib.util.spec_from_file_location(
    "custom_components.f1_sensor.binary_sensor",
    Path("custom_components/f1_sensor/binary_sensor.py"),
)
assert spec_bs and spec_bs.loader
bs = importlib.util.module_from_spec(spec_bs)
sys.modules["custom_components.f1_sensor.binary_sensor"] = bs
spec_bs.loader.exec_module(bs)
SafetyCarStateMachine = bs.SafetyCarStateMachine


def _load_msgs(name):
    return json.loads(Path(f"tests/fixtures/{name}").read_text())


def test_yellow_vsc_green_sequence():
    msgs = _load_msgs("flag_vsc_green.json")
    sm = FlagStateMachine()
    states = [sm.handle_message(m) for m in msgs]
    assert states == ["yellow", "vsc", "green"]


def test_yellow_sectors():
    msgs = _load_msgs("flag_yellow_sector.json")
    sm = FlagStateMachine()
    for msg in msgs:
        sm.handle_message(msg)
    assert sm.state == "yellow"
    assert sm.active_yellow_sectors == {2}


def test_red_flag_during_vsc():
    msgs = _load_msgs("flag_red_mid_vsc.json")
    sm = FlagStateMachine()
    for msg in msgs:
        sm.handle_message(msg)
    assert sm.state == "red"
    assert sm.track_red
    assert not sm.vsc_active


def test_safety_car_sequence():
    msgs = _load_msgs("safety_car.json")
    sm = SafetyCarStateMachine()
    states = [sm.handle_message(m) for m in msgs]
    assert states == [True, True, False]
