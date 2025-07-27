import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

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


@pytest.fixture
def rc_dump():
    path = Path("tests/fixtures/race_dump_2025_07_06.json")
    return json.loads(path.read_text())


@pytest.mark.asyncio
async def test_flag_state_sequence(rc_dump):
    fs = FlagState()

    # First yellow sector
    changed, _ = await fs.apply(rc_dump[0])
    assert changed == "yellow"

    # Clear another sector should keep yellow
    changed, _ = await fs.apply(rc_dump[1])
    assert changed is None
    assert fs.state == "yellow"

    # VSC deployment
    changed, _ = await fs.apply(rc_dump[2])
    assert changed == "vsc"

    # VSC ending - still yellow because sector 1 active
    changed, _ = await fs.apply(rc_dump[3])
    assert changed == "yellow"

    # Track clear after SC with no yellows -> green
    changed, _ = await fs.apply(rc_dump[4])
    assert changed == "green"

    # Chequered flag
    changed, _ = await fs.apply(rc_dump[5])
    assert changed == "chequered"
