"""Restore and startup lifecycle coverage for live sensor entities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.sensor import (
    F1CurrentSessionSensor,
    F1InvestigationsSensor,
    F1RaceControlSensor,
    F1SessionStatusSensor,
    F1StartingGridSensor,
    F1TeamRadioSensor,
    F1TrackLimitsSensor,
    F1TrackStatusSensor,
)


def _coordinator(hass, data=None) -> DataUpdateCoordinator:
    coordinator = DataUpdateCoordinator(
        hass,
        logging.getLogger(__name__),
        name="sensor-lifecycle",
    )
    coordinator.data = data
    coordinator.data_list = []
    return coordinator


def _ready(sensor, hass, entity_id: str) -> None:
    sensor.hass = hass
    sensor.entity_id = entity_id
    sensor.async_write_ha_state = Mock()
    sensor._safe_write_ha_state = Mock()


async def test_track_and_session_status_startup_lifecycle(hass) -> None:
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": SimpleNamespace(is_live=True, reason="live")
    }
    status_coordinator = _coordinator(hass, {"Status": "Started"})
    info_coordinator = _coordinator(
        hass,
        {
            "Meeting": {
                "Name": "Test GP",
                "Location": "Test",
                "Country": {"Name": "Sweden"},
                "Circuit": {"ShortName": "Test Ring"},
            },
            "StartDate": "2026-09-01T10:00:00Z",
            "EndDate": "2026-09-01T12:00:00Z",
        },
    )
    race_control = _coordinator(hass, {"Message": "NORMAL GRIP CONDITIONS"})
    race_control.data_list = [{"Message": "NORMAL GRIP CONDITIONS"}]
    hass.data[DOMAIN]["entry"].update(
        {
            "session_status_coordinator": status_coordinator,
            "session_info_coordinator": info_coordinator,
            "race_control_coordinator": race_control,
        }
    )

    track = F1TrackStatusSensor(
        _coordinator(hass, {"Status": "2"}), "track", "entry", "F1"
    )
    _ready(track, hass, "sensor.track")
    await track.async_added_to_hass()
    assert track.state == "YELLOW"
    assert track._session_status_coordinator is status_coordinator
    assert track.async_write_ha_state.called

    session = F1SessionStatusSensor(status_coordinator, "session", "entry", "F1")
    _ready(session, hass, "sensor.session")
    await session.async_added_to_hass()
    assert session._attr_native_value == "live"
    assert session.extra_state_attributes["meeting_name"] == "Test GP"
    assert session.extra_state_attributes["track_grip"] == "normal"
    assert session.async_write_ha_state.called


async def test_track_and_session_status_restore_when_payload_missing(hass) -> None:
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": SimpleNamespace(is_live=True, reason="live")
    }
    track = F1TrackStatusSensor(_coordinator(hass), "track_restore", "entry", "F1")
    _ready(track, hass, "sensor.track_restore")
    track.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(state="SC", attributes={})
    )
    await track.async_added_to_hass()
    assert track.state == "SC"

    session = F1SessionStatusSensor(
        _coordinator(hass), "session_restore", "entry", "F1"
    )
    _ready(session, hass, "sensor.session_restore")
    session.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="suspended",
            attributes={
                "meeting_name": "Saved GP",
                "circuit_short_name": "Saved Ring",
                "ignored": "drop",
            },
        )
    )
    await session.async_added_to_hass()
    assert session._attr_native_value == "suspended"
    assert session.extra_state_attributes == {
        "meeting_name": "Saved GP",
        "circuit_short_name": "Saved Ring",
    }


async def test_current_session_restore_and_live_payload_startup(hass) -> None:
    status_coordinator = _coordinator(hass, {"Status": "Inactive"})
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": SimpleNamespace(is_live=True, reason="live"),
        "session_status_coordinator": status_coordinator,
    }
    current = F1CurrentSessionSensor(
        _coordinator(hass), "current_restore", "entry", "F1"
    )
    _ready(current, hass, "sensor.current_restore")
    current.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="Race",
            attributes={
                "end": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                "meeting_name": "Old GP",
            },
        )
    )
    await current.async_added_to_hass()
    assert current.state is None
    assert current.extra_state_attributes["last_label"] == "Race"
    assert current.extra_state_attributes["active"] is False

    status_coordinator.data = {"Status": "Started"}
    live = F1CurrentSessionSensor(
        _coordinator(
            hass,
            {
                "Type": "Practice",
                "Name": "Practice 1",
                "Number": 1,
                "EndDate": "2099-01-01T12:00:00Z",
            },
        ),
        "current_live",
        "entry",
        "F1",
    )
    _ready(live, hass, "sensor.current_live")
    live.async_get_last_state = AsyncMock(return_value=None)
    await live.async_added_to_hass()
    assert live.state == "Practice 1"
    assert live.extra_state_attributes["active"] is True


async def test_race_control_and_team_radio_startup_payloads(hass) -> None:
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": SimpleNamespace(is_live=True, reason="live"),
        "live_supervisor": SimpleNamespace(
            current_window=SimpleNamespace(path="test/session")
        ),
        "session_coordinator": SimpleNamespace(year=2026),
    }
    race = F1RaceControlSensor(
        _coordinator(
            hass,
            {"Utc": "2026-09-01T12:00:00Z", "Flag": "RED", "Message": "Stop"},
        ),
        "race_control",
        "entry",
        "F1",
    )
    _ready(race, hass, "sensor.race_control")
    await race.async_added_to_hass()
    assert race.state == "Stop"
    assert race.extra_state_attributes["sequence"] == 1

    radio = F1TeamRadioSensor(
        _coordinator(
            hass,
            {
                "latest": {
                    "Utc": "2026-09-01T12:00:01Z",
                    "RacingNumber": "4",
                    "Path": "NOR/clip.mp3",
                }
            },
        ),
        "team_radio",
        "entry",
        "F1",
    )
    _ready(radio, hass, "sensor.team_radio")
    radio._is_stream_active = Mock(return_value=True)
    await radio.async_added_to_hass()
    assert radio.state == "2026-09-01T12:00:01+00:00"
    assert radio.extra_state_attributes["clip_url"].endswith(
        "/2026/test/session/NOR/clip.mp3"
    )


async def test_officials_sensors_restore_then_process_live_messages(hass) -> None:
    live_listener = Mock(return_value=Mock())
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": SimpleNamespace(
            is_live=True,
            reason="live",
            add_listener=live_listener,
        )
    }
    limits_coordinator = _coordinator(hass)
    limits_coordinator.data_list = [
        {
            "Utc": "2026-09-01T12:00:01Z",
            "Message": "BLACK AND WHITE FLAG FOR CAR 4 (NOR) - TRACK LIMITS",
        }
    ]
    limits = F1TrackLimitsSensor(limits_coordinator, "limits", "entry", "F1")
    _ready(limits, hass, "sensor.limits")
    limits.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="1",
            attributes={
                "by_driver": {
                    "PIA": {
                        "racing_number": "81",
                        "deletions": 1,
                        "warning": False,
                        "penalty": None,
                        "violations": [],
                    }
                }
            },
        )
    )
    await limits.async_added_to_hass()
    assert limits.state == 2
    assert set(limits.extra_state_attributes["by_driver"]) == {"NOR", "PIA"}

    investigations_coordinator = _coordinator(hass)
    investigations_coordinator.data_list = [
        {
            "Utc": "2026-09-01T12:00:02Z",
            "Message": "INCIDENT INVOLVING CAR 4 (NOR) NOTED - TURN 1",
        }
    ]
    investigations = F1InvestigationsSensor(
        investigations_coordinator, "investigations", "entry", "F1"
    )
    _ready(investigations, hass, "sensor.investigations")
    investigations.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="0",
            attributes={
                "noted": [],
                "under_investigation": [],
                "no_further_action": [],
                "penalties": [],
            },
        )
    )
    await investigations.async_added_to_hass()
    assert investigations.state == 1
    assert investigations.extra_state_attributes["noted"][0]["drivers"] == ["NOR"]
    assert live_listener.call_count == 2


async def test_starting_grid_restore_relevance_matrix(hass) -> None:
    coordinator = _coordinator(
        hass,
        {"weekend_key": "meeting:10", "grid_context": "race"},
    )
    sensor = F1StartingGridSensor(coordinator, "grid", "entry", "F1")
    _ready(sensor, hass, "sensor.grid")
    sensor.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="ready",
            attributes={
                "status": "ready",
                "weekend_key": "meeting:10",
                "grid_context": "race",
                "grid": [{"position": 1, "tla": "NOR"}],
            },
        )
    )
    await sensor.async_added_to_hass()
    assert sensor.native_value == "ready"
    assert sensor.extra_state_attributes["grid_count"] == 1

    sensor.async_get_last_state = AsyncMock(return_value=None)
    assert await sensor._restore_if_relevant() is False
    sensor.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(state="unknown", attributes={})
    )
    assert await sensor._restore_if_relevant() is False
