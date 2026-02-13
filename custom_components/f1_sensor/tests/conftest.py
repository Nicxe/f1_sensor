from __future__ import annotations

from pathlib import Path
import sys
import types

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

ROOT = Path(__file__).resolve().parents[3]
CUSTOM_COMPONENTS = ROOT / "custom_components"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Ensure our local custom_components package wins over any site-packages module.
if str(CUSTOM_COMPONENTS) not in sys.path:
    sys.path.insert(0, str(CUSTOM_COMPONENTS))
if "custom_components" not in sys.modules:
    namespace = types.ModuleType("custom_components")
    namespace.__path__ = [str(CUSTOM_COMPONENTS)]
    sys.modules["custom_components"] = namespace


@pytest.fixture
def replay_file(tmp_path: Path) -> str:
    path = tmp_path / "replay.txt"
    path.write_text("00:00:00.000{}", encoding="utf-8")
    return str(path)


@pytest.fixture
def mock_config_entry(hass, replay_file: str) -> MockConfigEntry:
    from custom_components.f1_sensor.const import (
        CONF_LIVE_DELAY_REFERENCE,
        CONF_OPERATION_MODE,
        CONF_RACE_WEEK_START_DAY,
        CONF_REPLAY_FILE,
        CONF_REPLAY_START_REFERENCE,
        DEFAULT_LIVE_DELAY_REFERENCE,
        DEFAULT_REPLAY_START_REFERENCE,
        DOMAIN,
        OPERATION_MODE_DEVELOPMENT,
        RACE_WEEK_START_MONDAY,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enabled_sensors": [],
            "enable_race_control": False,
            CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
            CONF_REPLAY_FILE: replay_file,
            CONF_RACE_WEEK_START_DAY: RACE_WEEK_START_MONDAY,
            CONF_LIVE_DELAY_REFERENCE: DEFAULT_LIVE_DELAY_REFERENCE,
            CONF_REPLAY_START_REFERENCE: DEFAULT_REPLAY_START_REFERENCE,
        },
    )
    entry.add_to_hass(hass)
    return entry
