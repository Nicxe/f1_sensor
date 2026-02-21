from __future__ import annotations

from datetime import UTC, datetime
import logging
import time

from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import pytest

from custom_components.f1_sensor.__init__ import SessionClockCoordinator
from custom_components.f1_sensor.const import (
    CONF_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
)
from custom_components.f1_sensor.sensor import (
    F1RaceTimeToThreeHourLimitSensor,
    F1SessionTimeRemainingSensor,
)

_LOGGER = logging.getLogger(__name__)


class _LiveState:
    def __init__(self, is_live: bool = False) -> None:
        self.is_live = is_live


class _Window:
    def __init__(
        self,
        session_name: str,
        start_utc: datetime,
        end_utc: datetime | None,
    ) -> None:
        self.session_name = session_name
        self.start_utc = start_utc
        self.end_utc = end_utc


class _LiveSupervisor:
    def __init__(self, window: _Window | None) -> None:
        self.current_window = window


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


@pytest.mark.asyncio
async def test_session_clock_qualifying_elapsed_and_remaining(
    hass, monkeypatch
) -> None:
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    coordinator._session_info = {"Type": "Qualifying", "Name": "Qualifying"}
    coordinator._ingest_session_data(
        {
            "Series": {
                "0": {"Utc": "2025-12-06T13:46:34.368Z", "QualifyingPart": 1},
            }
        }
    )
    coordinator._clock_anchor_utc = _utc("2025-12-06T14:00:01.002Z")
    coordinator._clock_anchor_remaining_s = 17 * 60 + 59
    coordinator._clock_anchor_extrapolating = True
    coordinator._update_clock_total(1, coordinator._clock_anchor_remaining_s)
    coordinator._last_heartbeat_utc = _utc("2025-12-06T14:00:06.000Z")
    coordinator._last_heartbeat_mono = time.monotonic()

    now_utc = _utc("2025-12-06T14:00:11.002Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    state = coordinator._build_state()
    assert state["session_part"] == 1
    assert state["clock_total_s"] == 1080
    assert state["clock_remaining_s"] == 1069
    assert state["clock_elapsed_s"] == 11
    assert state["clock_running"] is True
    assert state["clock_phase"] == "running"
    assert state["source_quality"] == "official"


@pytest.mark.asyncio
async def test_session_clock_applies_live_delay_to_elapsed_and_remaining(
    hass, monkeypatch
) -> None:
    coordinator = SessionClockCoordinator(
        hass,
        session_coord=object(),
        delay_seconds=30,
    )
    coordinator._session_info = {"Type": "Qualifying", "Name": "Qualifying"}
    coordinator._clock_anchor_utc = _utc("2025-12-06T14:00:01Z")
    coordinator._clock_anchor_remaining_s = 17 * 60 + 59
    coordinator._clock_anchor_extrapolating = True
    coordinator._last_heartbeat_utc = _utc("2025-12-06T14:00:01Z")
    base_mono = 1000.0
    coordinator._last_heartbeat_mono = base_mono
    monkeypatch.setattr(
        "custom_components.f1_sensor.__init__.time.monotonic",
        lambda: base_mono + 30.0,
    )

    state = coordinator._build_state()
    # With 30s live delay, timers must behave as if server-now == anchor time.
    assert state["clock_remaining_s"] == 17 * 60 + 59
    assert state["clock_elapsed_s"] == 1


@pytest.mark.asyncio
async def test_session_clock_race_three_hour_limit_from_sessiondata(
    hass, monkeypatch
) -> None:
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    coordinator._session_info = {"Type": "Race", "Name": "Race"}
    coordinator._ingest_session_data(
        {
            "StatusSeries": {
                "7": {"Utc": "2025-12-07T13:03:27.584Z", "SessionStatus": "Started"}
            }
        }
    )

    now_utc = _utc("2025-12-07T15:03:27.584Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    state = coordinator._build_state()
    assert state["race_start_utc"] == "2025-12-07T13:03:27+00:00"
    assert state["race_three_hour_cap_utc"] == "2025-12-07T16:03:27+00:00"
    assert state["race_three_hour_remaining_s"] == 3600
    assert state["source_quality"] == "sessiondata_fallback"


@pytest.mark.asyncio
async def test_session_clock_race_start_fallback_from_clock(hass, monkeypatch) -> None:
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    coordinator._session_info = {"Type": "Race", "Name": "Race"}
    coordinator._clock_anchor_utc = _utc("2025-12-07T13:03:28.008Z")
    coordinator._clock_anchor_remaining_s = 7199
    coordinator._clock_anchor_extrapolating = True
    coordinator._update_clock_total(0, 7199)
    coordinator._last_heartbeat_utc = _utc("2025-12-07T13:03:28.008Z")
    coordinator._last_heartbeat_mono = time.monotonic()

    now_utc = _utc("2025-12-07T13:03:28.008Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    state = coordinator._build_state()
    assert state["race_start_utc"] == "2025-12-07T13:03:27+00:00"
    assert state["race_three_hour_cap_utc"] == "2025-12-07T16:03:27+00:00"
    assert state["source_quality"] == "official"


@pytest.mark.asyncio
async def test_session_clock_uses_race_default_total_on_restart(
    hass, monkeypatch
) -> None:
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    coordinator._session_info = {"Type": "Race", "Name": "Race"}
    coordinator._clock_anchor_utc = _utc("2025-12-07T14:30:00Z")
    coordinator._clock_anchor_remaining_s = 3600
    coordinator._clock_anchor_extrapolating = False

    now_utc = _utc("2025-12-07T14:30:05Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    state = coordinator._build_state()
    assert state["clock_total_s"] == 7200
    assert state["clock_remaining_s"] == 3600
    assert state["clock_elapsed_s"] == 3600


@pytest.mark.asyncio
async def test_session_clock_practice_elapsed_uses_live_window_duration(
    hass, monkeypatch
) -> None:
    window = _Window(
        "Practice 1",
        _utc("2025-12-07T08:00:00Z"),
        _utc("2025-12-07T09:00:00Z"),
    )
    coordinator = SessionClockCoordinator(
        hass,
        session_coord=object(),
        live_supervisor=_LiveSupervisor(window),
    )
    coordinator._clock_anchor_utc = _utc("2025-12-07T08:40:00Z")
    coordinator._clock_anchor_remaining_s = 20 * 60
    coordinator._clock_anchor_extrapolating = False

    now_utc = _utc("2025-12-07T08:40:05Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    state = coordinator._build_state()
    assert state["session_type"] == "Practice"
    assert state["session_name"] == "Practice 1"
    assert state["clock_total_s"] == 3600
    assert state["clock_remaining_s"] == 1200
    assert state["clock_elapsed_s"] == 2400


@pytest.mark.asyncio
async def test_session_clock_elapsed_unavailable_without_total_baseline(
    hass, monkeypatch
) -> None:
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    coordinator._clock_anchor_utc = _utc("2025-12-07T08:40:00Z")
    coordinator._clock_anchor_remaining_s = 20 * 60
    coordinator._clock_anchor_extrapolating = False

    now_utc = _utc("2025-12-07T08:40:05Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    state = coordinator._build_state()
    assert state["clock_total_s"] is None
    assert state["clock_remaining_s"] == 1200
    assert state["clock_elapsed_s"] is None


@pytest.mark.asyncio
async def test_session_clock_elapsed_uses_sessiondata_started_when_total_unknown(
    hass, monkeypatch
) -> None:
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    coordinator._ingest_session_data(
        {
            "StatusSeries": {
                "0": {"Utc": "2025-12-07T08:00:00Z", "SessionStatus": "Started"}
            }
        }
    )
    coordinator._clock_anchor_utc = _utc("2025-12-07T08:40:00Z")
    coordinator._clock_anchor_remaining_s = 20 * 60
    coordinator._clock_anchor_extrapolating = False

    now_utc = _utc("2025-12-07T08:40:05Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    state = coordinator._build_state()
    assert state["clock_total_s"] is None
    assert state["clock_remaining_s"] == 1200
    assert state["session_start_utc"] == "2025-12-07T08:00:00+00:00"
    assert state["clock_elapsed_s"] == 2405


@pytest.mark.asyncio
async def test_session_clock_elapsed_uses_live_window_start_when_total_unknown(
    hass, monkeypatch
) -> None:
    window = _Window(
        "Unknown Session",
        _utc("2025-12-07T08:00:00Z"),
        None,
    )
    coordinator = SessionClockCoordinator(
        hass,
        session_coord=object(),
        live_supervisor=_LiveSupervisor(window),
    )
    coordinator._clock_anchor_utc = _utc("2025-12-07T08:40:00Z")
    coordinator._clock_anchor_remaining_s = 20 * 60
    coordinator._clock_anchor_extrapolating = False

    now_utc = _utc("2025-12-07T08:40:05Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    state = coordinator._build_state()
    assert state["clock_total_s"] is None
    assert state["clock_remaining_s"] == 1200
    assert state["session_start_utc"] == "2025-12-07T08:00:00+00:00"
    assert state["clock_elapsed_s"] == 2405


@pytest.mark.asyncio
async def test_session_time_remaining_sensor_uses_coordinator_data(hass) -> None:
    coordinator = DataUpdateCoordinator(hass, _LOGGER, name="clock", update_method=None)
    coordinator.available = True
    coordinator.data = {
        "clock_remaining_s": 120,
        "clock_total_s": 180,
        "session_type": "Qualifying",
        "session_name": "Qualifying",
        "session_part": 1,
        "session_status": "Started",
        "clock_phase": "running",
        "clock_running": True,
        "source_quality": "official",
        "reference_utc": "2025-12-06T14:00:01+00:00",
        "last_server_utc": "2025-12-06T14:01:01+00:00",
    }

    entry_id = "clock_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
    }

    sensor = F1SessionTimeRemainingSensor(
        coordinator,
        f"{entry_id}_session_remaining",
        entry_id,
        "F1",
    )
    component = EntityComponent(_LOGGER, "sensor", hass)
    await component.async_add_entities([sensor])
    await hass.async_block_till_done()

    state = hass.states.get(sensor.entity_id)
    assert state is not None
    assert state.state == "0:02:00"
    assert state.attributes["formatted_hms"] == "0:02:00"
    assert state.attributes["value_seconds"] == 120

    coordinator.async_set_updated_data(
        {
            **coordinator.data,
            "clock_remaining_s": None,
            "source_quality": "unavailable",
        }
    )
    await hass.async_block_till_done()

    state = hass.states.get(sensor.entity_id)
    assert state is not None
    assert state.state == "unavailable"


@pytest.mark.asyncio
async def test_race_three_hour_sensor_hidden_for_sprint(hass) -> None:
    coordinator = DataUpdateCoordinator(hass, _LOGGER, name="clock", update_method=None)
    coordinator.available = True
    coordinator.data = {
        "race_three_hour_remaining_s": 6000,
        "race_start_utc": "2025-12-07T13:00:00+00:00",
        "race_three_hour_cap_utc": "2025-12-07T16:00:00+00:00",
        "session_type": "Race",
        "session_name": "Sprint",
        "session_status": "Started",
        "clock_phase": "running",
        "clock_running": True,
        "source_quality": "official",
        "reference_utc": "2025-12-07T13:00:00+00:00",
        "last_server_utc": "2025-12-07T14:20:00+00:00",
    }

    entry_id = "sprint_entry"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "live_state": _LiveState(True),
    }

    sensor = F1RaceTimeToThreeHourLimitSensor(
        coordinator,
        f"{entry_id}_race_cap",
        entry_id,
        "F1",
    )
    component = EntityComponent(_LOGGER, "sensor", hass)
    await component.async_add_entities([sensor])
    await hass.async_block_till_done()

    state = hass.states.get(sensor.entity_id)
    assert state is not None
    assert state.state == "unavailable"
