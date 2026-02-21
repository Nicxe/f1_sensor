from __future__ import annotations

import logging

import pytest
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.f1_sensor.const import (
    CONF_OPERATION_MODE,
    DOMAIN,
    LATEST_TRACK_STATUS,
    OPERATION_MODE_DEVELOPMENT,
)
from custom_components.f1_sensor.sensor import (
    F1CurrentSessionSensor,
    F1SessionStatusSensor,
)

_LOGGER = logging.getLogger(__name__)


class _LiveState:
    def __init__(self, is_live: bool = True) -> None:
        self.is_live = is_live


def _build_coordinator(hass, data: dict) -> DataUpdateCoordinator:
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="test",
        update_method=None,
    )
    coordinator.data = data
    coordinator.available = True
    return coordinator


def _session_info_payload() -> dict:
    return {
        "Type": "Practice",
        "Name": "Day 3",
        "Number": 3,
        "Meeting": {
            "Key": 1305,
            "Name": "Pre-Season Testing",
            "Location": "Bahrain",
            "Country": {"Name": "Bahrain"},
            "Circuit": {"ShortName": "Sakhir"},
        },
        "StartDate": "2026-02-20T10:00:00",
        "EndDate": "2026-02-20T19:00:00",
        "GmtOffset": "03:00:00",
    }


async def _add_sensors(hass, sensors: list) -> None:
    component = EntityComponent(_LOGGER, "sensor", hass)
    await component.async_add_entities(sensors)
    await hass.async_block_till_done()


def _set_live_context(
    hass,
    entry_id: str,
    *,
    status_coordinator: DataUpdateCoordinator,
) -> None:
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
        "session_status_coordinator": status_coordinator,
    }


@pytest.mark.asyncio
async def test_current_session_keeps_label_when_status_is_inactive_started(
    hass,
) -> None:
    entry_id = "test_entry_current_session_inactive"
    status_coordinator = _build_coordinator(
        hass,
        {"Status": "Started", "Started": "Started"},
    )
    info_coordinator = _build_coordinator(hass, _session_info_payload())

    _set_live_context(hass, entry_id, status_coordinator=status_coordinator)
    hass.data[LATEST_TRACK_STATUS] = {"Status": "1", "Message": "AllClear"}

    status_sensor = F1SessionStatusSensor(
        status_coordinator,
        f"{entry_id}_session_status",
        entry_id,
        "F1",
    )
    current_sensor = F1CurrentSessionSensor(
        info_coordinator,
        f"{entry_id}_current_session",
        entry_id,
        "F1",
    )
    await _add_sensors(hass, [status_sensor, current_sensor])

    status_coordinator.async_set_updated_data(
        {"Status": "Inactive", "Started": "Started"}
    )
    await hass.async_block_till_done()

    status_state = hass.states.get(status_sensor.entity_id)
    assert status_state is not None
    assert status_state.state == "live"

    current_state = hass.states.get(current_sensor.entity_id)
    assert current_state is not None
    assert current_state.state == "Practice 3"
    assert current_state.attributes["live_status"] == "Inactive"
    assert current_state.attributes["active"] is True


@pytest.mark.asyncio
async def test_current_session_keeps_label_when_status_is_aborted_started(hass) -> None:
    entry_id = "test_entry_current_session_aborted"
    status_coordinator = _build_coordinator(
        hass,
        {"Status": "Started", "Started": "Started"},
    )
    info_coordinator = _build_coordinator(hass, _session_info_payload())

    _set_live_context(hass, entry_id, status_coordinator=status_coordinator)
    hass.data[LATEST_TRACK_STATUS] = {"Status": "1", "Message": "AllClear"}

    status_sensor = F1SessionStatusSensor(
        status_coordinator,
        f"{entry_id}_session_status",
        entry_id,
        "F1",
    )
    current_sensor = F1CurrentSessionSensor(
        info_coordinator,
        f"{entry_id}_current_session",
        entry_id,
        "F1",
    )
    await _add_sensors(hass, [status_sensor, current_sensor])

    status_coordinator.async_set_updated_data(
        {"Status": "Aborted", "Started": "Started"}
    )
    await hass.async_block_till_done()

    status_state = hass.states.get(status_sensor.entity_id)
    assert status_state is not None
    assert status_state.state == "live"

    current_state = hass.states.get(current_sensor.entity_id)
    assert current_state is not None
    assert current_state.state == "Practice 3"
    assert current_state.attributes["live_status"] == "Aborted"
    assert current_state.attributes["active"] is True
