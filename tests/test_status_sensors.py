import asyncio
import pytest
from homeassistant.core import HomeAssistant

from custom_components.f1_sensor.realtime_coordinators import (
    TrackStatusWSCoordinator,
    SessionStatusCoordinator,
)
from custom_components.f1_sensor.sensor import F1TrackStatusSensor
from custom_components.f1_sensor.binary_sensor import F1SessionActiveBinary


@pytest.mark.asyncio
async def test_track_status_sensor_state():
    hass = HomeAssistant('.')
    coord = TrackStatusWSCoordinator(hass)
    sensor = F1TrackStatusSensor(coord, 'track', 'uid', 'entry', 'F1')
    coord.async_set_updated_data({'Status': 2, 'Sectors': {'1': 1, '2': 2, '3': 1}})
    assert sensor.state == 2
    attrs = sensor.extra_state_attributes
    assert attrs['sector_flags']['sector2'] == 2


@pytest.mark.asyncio
async def test_session_active_binary():
    hass = HomeAssistant('.')
    coord = SessionStatusCoordinator(hass)
    sensor = F1SessionActiveBinary(coord, 'sess', 'uid2', 'entry', 'F1')
    coord.async_set_updated_data({'SessionPhase': 'Green'})
    assert sensor.is_on
    coord.async_set_updated_data({'SessionPhase': 'Red'})
    assert not sensor.is_on

