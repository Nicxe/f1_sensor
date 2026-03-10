from __future__ import annotations

import logging
from types import SimpleNamespace

from homeassistant.const import STATE_UNKNOWN
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import pytest

from custom_components.f1_sensor.const import (
    CONF_OPERATION_MODE,
    DOMAIN,
    LATEST_TRACK_STATUS,
    OPERATION_MODE_DEVELOPMENT,
)
from custom_components.f1_sensor.replay_mode import ReplayState
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


def _session_info_payload(
    *,
    session_type: str = "Practice",
    name: str = "Day 3",
    number: int | None = 3,
    start_date: str = "2099-02-20T10:00:00",
    end_date: str = "2099-02-20T19:00:00",
) -> dict:
    return {
        "Type": session_type,
        "Name": name,
        "Number": number,
        "Meeting": {
            "Key": 1305,
            "Name": "Pre-Season Testing",
            "Location": "Bahrain",
            "Country": {"Name": "Bahrain"},
            "Circuit": {"ShortName": "Sakhir"},
        },
        "StartDate": start_date,
        "EndDate": end_date,
        "GmtOffset": "03:00:00",
    }


def _set_status_context(
    coordinator: DataUpdateCoordinator,
    *,
    is_qualifying_like_session: bool = False,
    qualifying_part: int | None = None,
) -> None:
    coordinator.is_qualifying_like_session = is_qualifying_like_session
    coordinator.qualifying_part = qualifying_part


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


def _set_replay_context(
    hass,
    entry_id: str,
    *,
    status_coordinator: DataUpdateCoordinator,
) -> None:
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "session_status_coordinator": status_coordinator,
        "replay_controller": SimpleNamespace(state=ReplayState.PLAYING),
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("qualifying_part", "session_name", "expected_label"),
    [
        (1, "Qualifying", "Qualifying"),
        (2, "Qualifying", "Qualifying"),
        (1, "Sprint Shootout", "Sprint Qualifying"),
    ],
)
async def test_qualifying_finished_maps_to_break_until_final_segment(
    hass,
    qualifying_part: int,
    session_name: str,
    expected_label: str,
) -> None:
    entry_id = f"test_entry_qualifying_break_{qualifying_part}_{session_name.lower().replace(' ', '_')}"
    status_coordinator = _build_coordinator(
        hass,
        {"Status": "Started", "Started": "Started"},
    )
    _set_status_context(
        status_coordinator,
        is_qualifying_like_session=True,
        qualifying_part=qualifying_part,
    )
    info_coordinator = _build_coordinator(
        hass,
        _session_info_payload(
            session_type="Qualifying",
            name=session_name,
            number=None,
        ),
    )

    _set_live_context(hass, entry_id, status_coordinator=status_coordinator)
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
        {"Status": "Finished", "Started": "Finished"}
    )
    await hass.async_block_till_done()

    status_state = hass.states.get(status_sensor.entity_id)
    assert status_state is not None
    assert status_state.state == "break"

    current_state = hass.states.get(current_sensor.entity_id)
    assert current_state is not None
    assert current_state.state == expected_label
    assert current_state.attributes["live_status"] == "Finished"
    assert current_state.attributes["active"] is False


@pytest.mark.asyncio
async def test_qualifying_finished_stays_terminal_for_final_segment(hass) -> None:
    entry_id = "test_entry_qualifying_final_segment"
    status_coordinator = _build_coordinator(
        hass,
        {"Status": "Started", "Started": "Started"},
    )
    _set_status_context(
        status_coordinator,
        is_qualifying_like_session=True,
        qualifying_part=3,
    )
    info_coordinator = _build_coordinator(
        hass,
        _session_info_payload(
            session_type="Qualifying",
            name="Qualifying",
            number=None,
        ),
    )

    _set_live_context(hass, entry_id, status_coordinator=status_coordinator)
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
        {"Status": "Finished", "Started": "Finished"}
    )
    await hass.async_block_till_done()

    status_state = hass.states.get(status_sensor.entity_id)
    assert status_state is not None
    assert status_state.state == "finished"

    current_state = hass.states.get(current_sensor.entity_id)
    assert current_state is not None
    assert current_state.state == STATE_UNKNOWN
    assert current_state.attributes["live_status"] == "Finished"
    assert current_state.attributes["active"] is False
    assert current_state.attributes["last_label"] == "Qualifying"


@pytest.mark.asyncio
async def test_current_session_keeps_replay_qualifying_label_after_scheduled_end(
    hass,
) -> None:
    entry_id = "test_entry_replay_qualifying_past_end"
    status_coordinator = _build_coordinator(
        hass,
        {"Status": "Inactive", "Started": "Started"},
    )
    info_coordinator = _build_coordinator(
        hass,
        _session_info_payload(
            session_type="Qualifying",
            name="Qualifying",
            number=None,
            start_date="2026-03-07T16:00:00",
            end_date="2026-03-07T17:00:00",
        ),
    )

    _set_replay_context(hass, entry_id, status_coordinator=status_coordinator)
    hass.data[LATEST_TRACK_STATUS] = {"Status": "1", "Message": "AllClear"}

    current_sensor = F1CurrentSessionSensor(
        info_coordinator,
        f"{entry_id}_current_session",
        entry_id,
        "F1",
    )
    await _add_sensors(hass, [current_sensor])

    current_state = hass.states.get(current_sensor.entity_id)
    assert current_state is not None
    assert current_state.state == "Qualifying"
    assert current_state.attributes["live_status"] == "Inactive"
    assert current_state.attributes["active"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session_type", "session_name"),
    [
        ("Practice", "Day 3"),
        ("Race", "Race"),
    ],
)
async def test_non_qualifying_finished_remains_finished(
    hass,
    session_type: str,
    session_name: str,
) -> None:
    entry_id = f"test_entry_non_qualifying_finished_{session_type.lower()}"
    status_coordinator = _build_coordinator(
        hass,
        {"Status": "Started", "Started": "Started"},
    )
    _set_status_context(status_coordinator)

    _set_live_context(hass, entry_id, status_coordinator=status_coordinator)
    status_sensor = F1SessionStatusSensor(
        status_coordinator,
        f"{entry_id}_session_status",
        entry_id,
        "F1",
    )
    await _add_sensors(hass, [status_sensor])

    status_coordinator.async_set_updated_data(
        {"Status": "Finished", "Started": "Finished"}
    )
    await hass.async_block_till_done()

    status_state = hass.states.get(status_sensor.entity_id)
    assert status_state is not None
    assert status_state.state == "finished"
