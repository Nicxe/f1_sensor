import importlib.util
import sys
import types
from pathlib import Path
import datetime

from types import SimpleNamespace


def load_sensor_module():
    spec = importlib.util.spec_from_file_location(
        "custom_components.f1_sensor.sensor",
        Path("custom_components/f1_sensor/sensor.py"),
    )
    module = importlib.util.module_from_spec(spec)
    pkg = types.ModuleType("custom_components")
    pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules.setdefault("custom_components", pkg)
    fc = types.ModuleType("custom_components.f1_sensor")
    fc.__path__ = [str(Path("custom_components/f1_sensor"))]  # type: ignore[attr-defined]
    sys.modules["custom_components.f1_sensor"] = fc
    async_timeout_mod = types.ModuleType("async_timeout")

    class _Dummy:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

    async_timeout_mod.timeout = lambda _: _Dummy()
    sys.modules.setdefault("async_timeout", async_timeout_mod)

    ha = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = type("HomeAssistant", (), {})
    ha.core = core
    comps = types.ModuleType("homeassistant.components")
    comps.__path__ = []  # type: ignore[attr-defined]
    sensor_mod = types.ModuleType("homeassistant.components.sensor")
    binary_mod = types.ModuleType("homeassistant.components.binary_sensor")
    sensor_mod.SensorEntity = object
    sensor_mod.SensorDeviceClass = type(
        "SensorDeviceClass",
        (),
        {"TIMESTAMP": "timestamp"},
    )
    binary_mod.BinarySensorEntity = object
    binary_mod.BinarySensorDeviceClass = type(
        "BinarySensorDeviceClass",
        (),
        {"OCCUPANCY": "occupancy", "SAFETY": "safety"},
    )
    comps.sensor = sensor_mod
    comps.binary_sensor = binary_mod
    ha.components = comps
    helpers = types.ModuleType("homeassistant.helpers")
    aio = types.ModuleType("homeassistant.helpers.aiohttp_client")
    aio.async_get_clientsession = lambda hass: None
    helpers.aiohttp_client = aio
    update = types.ModuleType("homeassistant.helpers.update_coordinator")
    update.DataUpdateCoordinator = object

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

        def async_write_ha_state(self):
            pass

    update.CoordinatorEntity = CoordinatorEntity
    update.UpdateFailed = Exception
    helpers.update_coordinator = update
    ha.helpers = helpers
    ha.config_entries = types.ModuleType("homeassistant.config_entries")
    ha.config_entries.ConfigEntry = type("ConfigEntry", (), {})
    sys.modules.update(
        {
            "homeassistant": ha,
            "homeassistant.components": comps,
            "homeassistant.components.sensor": sensor_mod,
            "homeassistant.components.binary_sensor": binary_mod,
            "homeassistant.core": core,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.aiohttp_client": aio,
            "homeassistant.helpers.update_coordinator": update,
            "homeassistant.config_entries": ha.config_entries,
        }
    )

    tf = types.ModuleType("timezonefinder")
    tf.TimezoneFinder = lambda: SimpleNamespace(timezone_at=lambda lat, lng: "UTC")
    sys.modules["timezonefinder"] = tf

    const_spec = importlib.util.spec_from_file_location(
        "custom_components.f1_sensor.const",
        Path("custom_components/f1_sensor/const.py"),
    )
    const_mod = importlib.util.module_from_spec(const_spec)
    sys.modules["custom_components.f1_sensor.const"] = const_mod
    const_spec.loader.exec_module(const_mod)

    entity_spec = importlib.util.spec_from_file_location(
        "custom_components.f1_sensor.entity",
        Path("custom_components/f1_sensor/entity.py"),
    )
    entity_mod = importlib.util.module_from_spec(entity_spec)
    sys.modules["custom_components.f1_sensor.entity"] = entity_mod
    entity_spec.loader.exec_module(entity_mod)

    sys.modules["custom_components.f1_sensor.sensor"] = module
    spec.loader.exec_module(module)
    return module


class DummyCoord:
    def __init__(self, data=None):
        self.data = data or {}
        self.data_list = []

    def async_add_listener(self, _):
        pass

sensor_mod = load_sensor_module()

spec = importlib.util.spec_from_file_location(
    "custom_components.f1_sensor.binary_sensor",
    Path("custom_components/f1_sensor/binary_sensor.py"),
)
binary = importlib.util.module_from_spec(spec)
sys.modules["custom_components.f1_sensor.binary_sensor"] = binary
spec.loader.exec_module(binary)


def test_race_week_sensor_is_on():
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2)
    data = {
        "MRData": {
            "RaceTable": {
                "Races": [
                    {
                        "date": future.date().isoformat(),
                        "time": future.time().isoformat().split("+")[0] + "Z",
                        "Circuit": {"Location": {"lat": "0", "long": "0"}},
                    }
                ]
            }
        }
    }
    sensor = binary.F1RaceWeekSensor(DummyCoord(data), "n", "u", "e", "d")
    assert isinstance(sensor.is_on, bool)
    attrs = sensor.extra_state_attributes
    assert "days_until_next_race" in attrs


def test_safety_car_binary_sensor():
    coord = DummyCoord({"Category": "SafetyCar", "Status": "DEPLOYED"})
    sensor = binary.F1SafetyCarBinarySensor(coord, "n", "u", "e", "d")
    sensor._handle_coordinator_update()
    assert sensor.is_on
