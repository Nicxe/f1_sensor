import importlib.util
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def setup_ha_modules(monkeypatch):
    ha = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            pass

        async def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}

        def async_update_reload_and_abort(self, *args, **kwargs):
            return {"type": "abort"}

    config_entries.ConfigFlow = ConfigFlow
    ha.config_entries = config_entries

    helpers = types.ModuleType("homeassistant.helpers")
    cv = types.SimpleNamespace(string=str, boolean=bool, multi_select=lambda x: x)
    helpers.config_validation = cv
    ha.helpers = helpers

    vol = types.ModuleType("voluptuous")
    vol.Schema = lambda x: x
    vol.Required = lambda key, default=None: key
    vol.Optional = lambda key, default=None: key
    sys.modules["voluptuous"] = vol

    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.config_validation"] = cv
    yield
    for m in [
        "homeassistant",
        "homeassistant.config_entries",
        "homeassistant.helpers",
        "homeassistant.helpers.config_validation",
        "voluptuous",
    ]:
        sys.modules.pop(m, None)


def load_flow():
    spec = importlib.util.spec_from_file_location(
        "custom_components.f1_sensor.config_flow",
        Path("custom_components/f1_sensor/config_flow.py"),
    )
    module = importlib.util.module_from_spec(spec)
    const_spec = importlib.util.spec_from_file_location(
        "custom_components.f1_sensor.const",
        Path("custom_components/f1_sensor/const.py"),
    )
    const_mod = importlib.util.module_from_spec(const_spec)
    sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
    sys.modules["custom_components.f1_sensor.const"] = const_mod
    const_spec.loader.exec_module(const_mod)
    sys.modules["custom_components.f1_sensor.config_flow"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_step_user_strips_race_control():
    flow_mod = load_flow()
    flow = flow_mod.F1FlowHandler()
    flow.hass = types.SimpleNamespace()
    data = {
        "sensor_name": "Test",
        "enabled_sensors": ["next_race", "flag", "safety_car"],
        "enable_race_control": False,
    }
    result = await flow.async_step_user(data)
    assert result["type"] == "create_entry"
    assert result["title"] == "Test"
    assert "flag" not in result["data"]["enabled_sensors"]
    assert "safety_car" not in result["data"]["enabled_sensors"]


@pytest.mark.asyncio
async def test_get_reconfigure_entry():
    flow_mod = load_flow()
    flow = flow_mod.F1FlowHandler()
    flow.hass = types.SimpleNamespace(
        config_entries=types.SimpleNamespace(async_entries=lambda domain: [42])
    )
    assert flow._get_reconfigure_entry() == 42
