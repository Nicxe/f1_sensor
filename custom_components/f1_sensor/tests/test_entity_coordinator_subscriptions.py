"""Real config-entry regressions for coordinator listener ownership."""

from __future__ import annotations

from collections import Counter
from functools import wraps
import inspect
import re
from unittest.mock import AsyncMock

from homeassistant.helpers.entity_platform import async_get_platforms
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import binary_sensor, sensor
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.entity import F1BaseEntity
from custom_components.f1_sensor.signalr import LiveBus


@pytest.mark.asyncio
async def test_primary_coordinator_notifies_each_entity_once_after_reload(
    hass, enable_custom_integrations, aioclient_mock, monkeypatch
) -> None:
    """HA owns primary subscriptions; context listeners survive and all detach."""
    aioclient_mock.get(
        re.compile(r"https?://.*"),
        json={
            "Meetings": [],
            "MRData": {
                "total": "0",
                "limit": "100",
                "offset": "0",
                "RaceTable": {"Races": []},
                "StandingsTable": {"StandingsLists": []},
                "DriverTable": {"Drivers": []},
                "ConstructorTable": {"Constructors": []},
            },
        },
    )
    calls = Counter()

    def counted(original):
        @wraps(original)
        def update(entity):
            calls[entity.entity_id] += 1
            return original(entity)

        return update

    for module in (sensor, binary_sensor):
        for cls in vars(module).values():
            if (
                inspect.isclass(cls)
                and cls.__module__ == module.__name__
                and issubclass(cls, F1BaseEntity)
                and (method := cls.__dict__.get("_handle_coordinator_update"))
            ):
                monkeypatch.setattr(cls, "_handle_coordinator_update", counted(method))
    monkeypatch.setattr(LiveBus, "start", AsyncMock())
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        data={
            "sensor_name": "F1",
            "enable_race_control": True,
            "operation_mode": "live",
            "disabled_sensors": [],
        },
        options={"live_delay_seconds": 0},
    )
    entry.add_to_hass(hass)
    for _ in range(2):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entities = [
            entity
            for platform in async_get_platforms(hass, DOMAIN)
            for entity in platform.entities.values()
            if isinstance(entity, F1BaseEntity)
        ]
        positions = next(
            entity
            for entity in entities
            if isinstance(entity, sensor.F1DriverPositionsSensor)
        )
        coordinators = {entity.coordinator for entity in entities}
        try:
            for coordinator in coordinators:
                calls.clear()
                coordinator.async_update_listeners()
                for entity in entities:
                    if entity.coordinator is coordinator:
                        method = entity._handle_coordinator_update
                        if hasattr(method, "__wrapped__"):
                            assert calls[entity.entity_id] == 1, entity.entity_id
            # These are distinct context subscriptions and must not be removed.
            for coordinator, method in (
                (
                    positions._session_info_coordinator,
                    positions._handle_session_info_update,
                ),
                (
                    positions._session_status_coordinator,
                    positions._handle_session_status_update,
                ),
            ):
                assert (
                    sum(
                        callback == method
                        for callback, _context in coordinator._listeners.values()
                    )
                    == 1
                )
        finally:
            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()
        for coordinator in coordinators:
            assert not any(
                getattr(callback, "__self__", None) in entities
                for callback, _context in coordinator._listeners.values()
            )
