from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging
import time

from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import pytest

from custom_components.f1_sensor.__init__ import (
    SessionClockCoordinator,
    _wrap_delayed_handler,
)
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


def _apply_session_clock_events(
    coordinator: SessionClockCoordinator, events: list[tuple[str, dict]]
) -> None:
    handlers = {
        "SessionInfo": coordinator._on_session_info,
        "SessionStatus": coordinator._on_session_status,
        "SessionData": coordinator._on_session_data,
        "ExtrapolatedClock": coordinator._on_extrapolated_clock,
        "Heartbeat": coordinator._on_heartbeat,
    }
    for stream, payload in events:
        handlers[stream](payload)


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
async def test_session_clock_delay_keeps_heartbeat_stream_updating(hass) -> None:
    coordinator = SessionClockCoordinator(
        hass,
        session_coord=object(),
        delay_seconds=1,
    )
    try:
        coordinator._session_info = {"Type": "Qualifying", "Name": "Qualifying"}
        delayed_clock = _wrap_delayed_handler(
            coordinator, coordinator._on_extrapolated_clock
        )
        delayed_heartbeat = _wrap_delayed_handler(
            coordinator, coordinator._on_heartbeat
        )

        delayed_clock(
            {
                "Utc": "2025-12-06T14:00:01Z",
                "Remaining": "00:17:59",
                "Extrapolating": True,
            }
        )
        delayed_heartbeat({"Utc": "2025-12-06T14:00:01Z"})
        await asyncio.sleep(0.5)
        delayed_heartbeat({"Utc": "2025-12-06T14:00:16Z"})
        await asyncio.sleep(0.65)
        await hass.async_block_till_done()

        state = coordinator.data
        assert state is not None
        assert state["clock_remaining_s"] == 17 * 60 + 59
        assert state["clock_elapsed_s"] == 1
        assert state["source_quality"] == "official"
    finally:
        await coordinator.async_close()


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
async def test_session_clock_qualifying_replay_uses_local_segment_start(
    hass, monkeypatch
) -> None:
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    _apply_session_clock_events(
        coordinator,
        [
            ("SessionInfo", {"Type": "Qualifying", "Name": "Qualifying"}),
            (
                "SessionData",
                {
                    "Series": {
                        "1": {"Utc": "2026-03-07T04:47:26.891Z", "QualifyingPart": 1}
                    }
                },
            ),
            (
                "SessionData",
                {
                    "StatusSeries": {
                        "1": {
                            "Utc": "2026-03-07T05:00:00.195Z",
                            "SessionStatus": "Started",
                        }
                    }
                },
            ),
            (
                "ExtrapolatedClock",
                {
                    "Utc": "2026-03-07T05:00:01.007Z",
                    "Remaining": "00:17:59",
                    "Extrapolating": True,
                },
            ),
            (
                "SessionData",
                {
                    "StatusSeries": {
                        "10": {
                            "Utc": "2026-03-07T05:26:29.197Z",
                            "SessionStatus": "Finished",
                        }
                    }
                },
            ),
            (
                "ExtrapolatedClock",
                {
                    "Utc": "2026-03-07T05:26:29.010Z",
                    "Remaining": "00:00:00",
                    "Extrapolating": False,
                },
            ),
            (
                "SessionData",
                {
                    "Series": {
                        "2": {"Utc": "2026-03-07T05:33:00.090Z", "QualifyingPart": 2}
                    }
                },
            ),
            (
                "SessionData",
                {
                    "StatusSeries": {
                        "14": {
                            "Utc": "2026-03-07T05:34:00.212Z",
                            "SessionStatus": "Started",
                        }
                    }
                },
            ),
            (
                "ExtrapolatedClock",
                {
                    "Utc": "2026-03-07T05:34:01.010Z",
                    "Remaining": "00:14:59",
                    "Extrapolating": True,
                },
            ),
        ],
    )

    now_utc = _utc("2026-03-07T05:40:07Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    clock_anchor_utc = _utc("2026-03-07T05:34:01.010Z")
    expected_remaining = 899 - int((now_utc - clock_anchor_utc).total_seconds())
    expected_elapsed = (15 * 60) - expected_remaining

    state = coordinator._build_state()
    assert state["session_part"] == 2
    assert state["session_status"] == "Started"
    assert state["clock_total_s"] == 15 * 60
    assert state["clock_remaining_s"] == expected_remaining
    assert state["clock_elapsed_s"] == expected_elapsed
    assert state["session_start_utc"] == "2026-03-07T05:34:00+00:00"


@pytest.mark.asyncio
async def test_session_clock_qualifying_replay_restart_keeps_official_elapsed(
    hass, monkeypatch
) -> None:
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    _apply_session_clock_events(
        coordinator,
        [
            ("SessionInfo", {"Type": "Qualifying", "Name": "Qualifying"}),
            (
                "SessionData",
                {
                    "Series": {
                        "3": {"Utc": "2026-03-07T05:57:59.895Z", "QualifyingPart": 3}
                    }
                },
            ),
            (
                "SessionData",
                {
                    "StatusSeries": {
                        "19": {
                            "Utc": "2026-03-07T05:59:00.193Z",
                            "SessionStatus": "Started",
                        }
                    }
                },
            ),
            (
                "ExtrapolatedClock",
                {
                    "Utc": "2026-03-07T05:59:01.010Z",
                    "Remaining": "00:12:59",
                    "Extrapolating": True,
                },
            ),
            (
                "SessionData",
                {
                    "StatusSeries": {
                        "20": {
                            "Utc": "2026-03-07T06:02:13.924Z",
                            "SessionStatus": "Aborted",
                        }
                    }
                },
            ),
            (
                "ExtrapolatedClock",
                {
                    "Utc": "2026-03-07T06:02:14.003Z",
                    "Remaining": "00:09:47",
                    "Extrapolating": False,
                },
            ),
            (
                "SessionData",
                {
                    "StatusSeries": {
                        "26": {
                            "Utc": "2026-03-07T06:10:00.218Z",
                            "SessionStatus": "Started",
                        }
                    }
                },
            ),
            (
                "ExtrapolatedClock",
                {
                    "Utc": "2026-03-07T06:10:00.996Z",
                    "Remaining": "00:09:46",
                    "Extrapolating": True,
                },
            ),
        ],
    )

    now_utc = _utc("2026-03-07T06:10:10Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    clock_anchor_utc = _utc("2026-03-07T06:10:00.996Z")
    expected_remaining = 586 - int((now_utc - clock_anchor_utc).total_seconds())
    expected_elapsed = (12 * 60) - expected_remaining

    state = coordinator._build_state()
    assert state["session_part"] == 3
    assert state["session_status"] == "Started"
    assert state["clock_total_s"] == 12 * 60
    assert state["clock_remaining_s"] == expected_remaining
    assert state["clock_elapsed_s"] == expected_elapsed
    assert state["session_start_utc"] == "2026-03-07T05:59:00+00:00"


@pytest.mark.asyncio
async def test_session_clock_race_replay_freezes_at_first_terminal_marker(
    hass, monkeypatch
) -> None:
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    _apply_session_clock_events(
        coordinator,
        [
            ("SessionInfo", {"Type": "Race", "Name": "Race"}),
            (
                "SessionData",
                {
                    "StatusSeries": {
                        "16": {
                            "Utc": "2026-03-08T04:03:26.365Z",
                            "SessionStatus": "Started",
                        }
                    }
                },
            ),
            (
                "ExtrapolatedClock",
                {
                    "Utc": "2026-03-08T04:03:27.011Z",
                    "Remaining": "01:59:59",
                    "Extrapolating": True,
                },
            ),
            ("Heartbeat", {"Utc": "2026-03-08T05:29:30Z"}),
            (
                "SessionData",
                {
                    "StatusSeries": {
                        "27": {
                            "Utc": "2026-03-08T05:26:33.400Z",
                            "SessionStatus": "Finished",
                        }
                    }
                },
            ),
            (
                "SessionData",
                {
                    "StatusSeries": {
                        "28": {
                            "Utc": "2026-03-08T05:28:37.306Z",
                            "SessionStatus": "Finalised",
                        }
                    }
                },
            ),
        ],
    )

    finish_utc = _utc("2026-03-08T05:26:33.400Z")
    start_clock_utc = _utc("2026-03-08T04:03:27.011Z")
    race_start_utc = _utc("2026-03-08T04:03:26.365Z")
    expected_remaining = 7199 - int((finish_utc - start_clock_utc).total_seconds())
    expected_elapsed = 7200 - expected_remaining
    expected_race_remaining = int(
        ((race_start_utc + timedelta(hours=3)) - finish_utc).total_seconds()
    )

    now_utc = _utc("2026-03-08T05:30:00Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    state = coordinator._build_state()
    assert state["session_status"] == "Finalised"
    assert state["clock_phase"] == "finished"
    assert state["clock_running"] is False
    assert state["clock_remaining_s"] == expected_remaining
    assert state["clock_elapsed_s"] == expected_elapsed
    assert state["race_three_hour_remaining_s"] == expected_race_remaining
    assert state["race_start_utc"] == "2026-03-08T04:03:26+00:00"


@pytest.mark.asyncio
async def test_session_clock_practice_replay_does_not_infer_start_before_green(
    hass, monkeypatch
) -> None:
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    _apply_session_clock_events(
        coordinator,
        [
            ("SessionInfo", {"Type": "Practice", "Name": "Practice 3"}),
            ("SessionStatus", {"Status": "Inactive", "Started": "Inactive"}),
            (
                "ExtrapolatedClock",
                {
                    "Utc": "2026-03-07T01:27:06.009Z",
                    "Remaining": "01:00:00",
                    "Extrapolating": False,
                },
            ),
        ],
    )

    now_utc = _utc("2026-03-07T01:40:00Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    state = coordinator._build_state()
    assert state["session_status"] == "Inactive"
    assert state["clock_total_s"] == 3600
    assert state["clock_remaining_s"] == 3600
    assert state["clock_elapsed_s"] == 0
    assert state["session_start_utc"] is None


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
