import importlib.util
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def setup_modules():
    ha = types.ModuleType("homeassistant")
    ha.core = types.ModuleType("homeassistant.core")
    ha.core.HomeAssistant = type("HomeAssistant", (), {})
    ha.data = {}
    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.core"] = ha.core
    rc_transform = types.ModuleType("custom_components.f1_sensor.rc_transform")
    rc_transform.clean_rc = lambda data, t0: data
    sys.modules["custom_components.f1_sensor.rc_transform"] = rc_transform
    const_mod = types.ModuleType("custom_components.f1_sensor.const")
    const_mod.FLAG_MACHINE = "flag_machine"
    sys.modules["custom_components.f1_sensor.const"] = const_mod
    aiohttp = types.ModuleType("aiohttp")
    aiohttp.ClientSession = object

    class WS:
        TEXT = 1
        CLOSED = 2
        ERROR = 3

    aiohttp.WSMsgType = WS
    sys.modules["aiohttp"] = aiohttp
    yield
    for m in [
        "homeassistant",
        "homeassistant.core",
        "custom_components.f1_sensor.rc_transform",
        "custom_components.f1_sensor.const",
        "aiohttp",
    ]:
        sys.modules.pop(m, None)


def load_signalr():
    spec = importlib.util.spec_from_file_location(
        "custom_components.f1_sensor.signalr",
        Path("custom_components/f1_sensor/signalr.py"),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["custom_components.f1_sensor.signalr"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_async_update_flag_sensor():
    sig = load_signalr()

    class Machine:
        def __init__(self):
            self.track_red = True
            self.vsc_active = False
            self.active_yellows = {1}

        def apply(self, msg):
            return "red"

    hass = types.SimpleNamespace(
        data={sig.FLAG_MACHINE: Machine()},
        states=types.SimpleNamespace(async_set=lambda eid, s, a=None: a.update({"s": s})),
    )
    client = sig.SignalRClient(hass, None)
    out = {}

    def setter(eid, s, a=None):
        out["state"] = s
        out["attrs"] = a

    hass.states.async_set = setter
    await client._handle_rc({"data": 1})
    assert out["state"] == "red"
    assert out["attrs"]["track_red"]

