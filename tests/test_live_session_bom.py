import sys
import types
import json
from pathlib import Path
import importlib.util
import pytest


class FakeResponse:
    def __init__(self, text):
        self.status = 200
        self._text = text

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass


class FakeSession:
    def __init__(self, text):
        self._text = text

    def get(self, url):
        return FakeResponse(self._text)


def load_module(text):
    """Load the integration module with homeassistant stubs."""
    homeassistant = types.ModuleType("homeassistant")
    helpers = types.ModuleType("homeassistant.helpers")
    update = types.ModuleType("homeassistant.helpers.update_coordinator")

    class DataUpdateCoordinator:
        def __init__(self, hass, logger, *, name=None, update_interval=None):
            self.hass = hass
            self.logger = logger
            self.data = None
            self.update_interval = update_interval

    class UpdateFailed(Exception):
        pass

    update.DataUpdateCoordinator = DataUpdateCoordinator
    update.UpdateFailed = UpdateFailed

    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")

    def async_get_clientsession(hass):
        return FakeSession(text)

    aiohttp_client.async_get_clientsession = async_get_clientsession

    helpers.update_coordinator = update
    helpers.aiohttp_client = aiohttp_client
    homeassistant.helpers = helpers
    config_entries = types.ModuleType("homeassistant.config_entries")
    class ConfigEntry:
        pass
    config_entries.ConfigEntry = ConfigEntry
    homeassistant.config_entries = config_entries
    core = types.ModuleType("homeassistant.core")
    class HomeAssistant:
        pass
    core.HomeAssistant = HomeAssistant
    homeassistant.core = core

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.update_coordinator"] = update
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client
    sys.modules["homeassistant.config_entries"] = homeassistant.config_entries
    sys.modules["homeassistant.core"] = homeassistant.core

    spec = importlib.util.spec_from_file_location(
        "custom_components.f1_sensor",
        Path("custom_components/f1_sensor/__init__.py"),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["custom_components"] = types.ModuleType("custom_components")
    sys.modules["custom_components.f1_sensor"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_index_with_bom():
    text = Path("tests/fixtures/index_bom.json").read_text("utf-8")
    module = load_module(text)
    coord = module.LiveSessionCoordinator(object(), 2025)
    result = await coord._async_update_data()
    assert result == json.loads(text.lstrip("\ufeff"))

