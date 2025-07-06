import importlib.util
import sys
import types
from pathlib import Path

import pytest


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

    # Stub Home Assistant modules
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
    tf.TimezoneFinder = lambda: types.SimpleNamespace(timezone_at=lambda lat, lng: "Europe/Stockholm")
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


sensor = load_sensor_module()


class DummyCoord:
    def __init__(self, data=None):
        self.data = data or {}
        self.data_list = []

    def async_add_listener(self, _):
        pass


@pytest.mark.parametrize(
    "date_str,time_str,expected",
    [
        ("2025-06-01", "18:00:00Z", "2025-06-01T18:00:00+00:00"),
        ("2025-06-01", None, "2025-06-01T00:00:00+00:00"),
    ],
)
def test_combine_date_time(date_str, time_str, expected):
    s = sensor.F1NextRaceSensor(DummyCoord(), "name", "uid", "eid", "dev")
    assert s.combine_date_time(date_str, time_str) == expected


def test_to_local_and_timezone():
    s = sensor.F1NextRaceSensor(DummyCoord(), "name", "uid", "eid", "dev")
    s._tf = sensor.TimezoneFinder()
    tz = s._timezone_from_location(59.3, 18.1)
    iso = s._to_local("2025-06-01T10:00:00+00:00", tz)
    assert tz == "Europe/Stockholm"
    assert iso.endswith("+02:00")


def test_weather_extract_and_abbr():
    w = sensor.F1WeatherSensor(DummyCoord(), "w", "uid", "eid", "dev")
    data = {
        "air_temperature": 10,
        "relative_humidity": 50,
        "cloud_area_fraction": 20,
        "wind_from_direction": 90,
    }
    result = w._extract(data)
    assert result["temperature"] == 10
    assert w._abbr(90) == "E"


def test_last_race_sensor_attrs():
    coord = DummyCoord(
        {
            "MRData": {
                "RaceTable": {
                    "Races": [
                        {
                            "round": "1",
                            "raceName": "Test",
                            "Results": [
                                {"positionText": "1", "Driver": {"familyName": "Verstappen"}},
                                {"positionText": "2", "Driver": {"familyName": "Norris"}},
                            ],
                        }
                    ]
                }
            }
        }
    )
    sensor_obj = sensor.F1LastRaceSensor(coord, "n", "uid", "eid", "dev")
    assert sensor_obj.state == "Verstappen"
    attrs = sensor_obj.extra_state_attributes
    assert attrs["round"] == "1"
    assert len(attrs["results"]) == 2

