import importlib.util
import sys
import types
from pathlib import Path


homeassistant = types.ModuleType("homeassistant")
homeassistant.core = types.ModuleType("homeassistant.core")
homeassistant.core.HomeAssistant = type("HomeAssistant", (), {})
sys.modules.setdefault("homeassistant", homeassistant)
sys.modules.setdefault("homeassistant.core", homeassistant.core)

spec = importlib.util.spec_from_file_location(
    "custom_components.f1_sensor.flag_state",
    Path("custom_components/f1_sensor/flag_state.py"),
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["custom_components.f1_sensor.flag_state"] = module
spec.loader.exec_module(module)
FlagState = module.FlagState


def test_track_red_overrides_all():
    fs = FlagState()
    fs.apply({"category": "Flag", "flag": "YELLOW", "scope": "Sector", "sector": 1})
    assert fs.state == "yellow"
    fs.apply({"category": "Flag", "flag": "RED", "scope": "Track"})
    assert fs.state == "red"
    fs.apply({"category": "SafetyCar", "Status": "VSC DEPLOYED", "scope": "Track"})
    assert fs.state == "red"


def test_sector_clear_does_not_cancel_track_red():
    fs = FlagState()
    fs.apply({"category": "Flag", "flag": "RED", "scope": "Track"})
    fs.apply({"category": "Flag", "flag": "CLEAR", "scope": "Sector", "sector": 1})
    assert fs.track_red
    assert fs.state == "red"


def test_track_clear_requires_no_yellows_for_green():
    fs = FlagState()
    fs.apply({"category": "Flag", "flag": "RED", "scope": "Track"})
    fs.apply({"category": "Flag", "flag": "YELLOW", "scope": "Sector", "sector": 2})
    fs.apply({"category": "Flag", "flag": "CLEAR", "scope": "Track"})
    assert fs.state == "yellow"
    fs.apply({"category": "Flag", "flag": "CLEAR", "scope": "Sector", "sector": 2})
    assert fs.state == "green"

