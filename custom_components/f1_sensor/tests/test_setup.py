from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import async_setup_entry
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.const import (
    CONF_OPERATION_MODE,
    CONF_REPLAY_FILE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
    OPERATION_MODE_LIVE,
    PLATFORMS,
)


class FakeLiveBus:
    def __init__(self, _hass, _session, transport_factory=None) -> None:
        self._transport_factory = transport_factory
        self.started = False

    async def start(self) -> None:
        self.started = True

    async def async_close(self) -> None:
        self.started = False

    def subscribe(self, _stream, _callback):
        return lambda: None


class DummyCoordinator:
    def __init__(self, *args, **kwargs) -> None:
        self.config_entry = kwargs.get("config_entry")

    async def async_config_entry_first_refresh(self) -> None:
        return None


class FakeReplayController:
    def __init__(self, *args, **kwargs) -> None:
        self._initialized = False

    async def async_initialize(self) -> None:
        self._initialized = True


class FakeLiveSupervisor:
    last_instance = None

    def __init__(self, _hass, _session_coord, _live_bus, **kwargs) -> None:
        self.availability = LiveAvailabilityTracker()
        self.fallback_source = kwargs.get("fallback_source")
        FakeLiveSupervisor.last_instance = self

    async def async_start(self) -> None:
        return None

    def wake(self) -> None:
        return None


@pytest.mark.asyncio
async def test_async_setup_entry_minimal(hass, mock_config_entry) -> None:
    with (
        patch(
            "custom_components.f1_sensor.build_user_agent",
            AsyncMock(return_value="ua"),
        ),
        patch("custom_components.f1_sensor.LiveBus", FakeLiveBus),
        patch(
            "custom_components.f1_sensor.LiveSessionCoordinator",
            DummyCoordinator,
        ),
        patch(
            "custom_components.f1_sensor.ReplayController",
            FakeReplayController,
        ),
    ):
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)

        result = await async_setup_entry(hass, mock_config_entry)

    assert result is True
    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(
        mock_config_entry, PLATFORMS
    )

    entry_data = hass.data[DOMAIN][mock_config_entry.entry_id]
    assert entry_data["operation_mode"] == OPERATION_MODE_DEVELOPMENT
    assert entry_data["replay_file"] == mock_config_entry.data[CONF_REPLAY_FILE]
    assert entry_data["live_bus"].started is True


@pytest.mark.asyncio
async def test_async_setup_entry_live_mode_wires_event_tracker_fallback(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            "enabled_sensors": [],
            "enable_race_control": False,
            CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
            CONF_REPLAY_FILE: "",
        },
    )
    entry.add_to_hass(hass)
    sentinel_source = object()

    with (
        patch(
            "custom_components.f1_sensor.build_user_agent",
            AsyncMock(return_value="ua"),
        ),
        patch("custom_components.f1_sensor.LiveBus", FakeLiveBus),
        patch(
            "custom_components.f1_sensor.LiveSessionCoordinator",
            DummyCoordinator,
        ),
        patch(
            "custom_components.f1_sensor.ReplayController",
            FakeReplayController,
        ),
        patch(
            "custom_components.f1_sensor.EventTrackerScheduleSource",
            lambda *_args, **_kwargs: sentinel_source,
        ),
        patch(
            "custom_components.f1_sensor.LiveSessionSupervisor",
            FakeLiveSupervisor,
        ),
    ):
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
        result = await async_setup_entry(hass, entry)

    assert result is True
    assert FakeLiveSupervisor.last_instance is not None
    assert FakeLiveSupervisor.last_instance.fallback_source is sentinel_source
