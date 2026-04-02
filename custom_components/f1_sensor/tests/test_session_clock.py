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
from custom_components.f1_sensor.replay_mode import ReplayState
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


@pytest.mark.asyncio
async def test_session_clock_qualifying_break_does_not_show_stale_elapsed(
    hass, monkeypatch
) -> None:
    """During the break between Q1 and Q2 the segment advances before new
    ExtrapolatedClock data arrives.  The stale Q1 anchor (remaining=0) must
    not be combined with the Q2 total to produce a misleading elapsed value."""
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    _apply_session_clock_events(
        coordinator,
        [
            ("SessionInfo", {"Type": "Qualifying", "Name": "Qualifying"}),
            # Q1 start & clock
            (
                "SessionData",
                {"Series": {"1": {"Utc": "2026-03-07T05:00:00Z", "QualifyingPart": 1}}},
            ),
            (
                "SessionData",
                {
                    "StatusSeries": {
                        "1": {
                            "Utc": "2026-03-07T05:00:00Z",
                            "SessionStatus": "Started",
                        }
                    }
                },
            ),
            (
                "ExtrapolatedClock",
                {
                    "Utc": "2026-03-07T05:00:01Z",
                    "Remaining": "00:17:59",
                    "Extrapolating": True,
                },
            ),
            # Q1 finished
            (
                "SessionData",
                {
                    "StatusSeries": {
                        "10": {
                            "Utc": "2026-03-07T05:18:00Z",
                            "SessionStatus": "Finished",
                        }
                    }
                },
            ),
            (
                "ExtrapolatedClock",
                {
                    "Utc": "2026-03-07T05:18:00Z",
                    "Remaining": "00:00:00",
                    "Extrapolating": False,
                },
            ),
            # Q2 qualifying part arrives during break — no ExtrapolatedClock yet
            (
                "SessionData",
                {"Series": {"2": {"Utc": "2026-03-07T05:25:00Z", "QualifyingPart": 2}}},
            ),
        ],
    )

    now_utc = _utc("2026-03-07T05:26:00Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    state = coordinator._build_state()
    assert state["session_part"] == 2
    # Remaining and elapsed should be None — no Q2 clock data yet
    assert state["clock_remaining_s"] is None
    assert state["clock_elapsed_s"] is None


@pytest.mark.asyncio
async def test_session_clock_qualifying_break_recovers_when_new_clock_arrives(
    hass, monkeypatch
) -> None:
    """After the qualifying break, the first ExtrapolatedClock for Q2 must
    restore normal remaining and elapsed values."""
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    _apply_session_clock_events(
        coordinator,
        [
            ("SessionInfo", {"Type": "Qualifying", "Name": "Qualifying"}),
            (
                "SessionData",
                {"Series": {"1": {"Utc": "2026-03-07T05:00:00Z", "QualifyingPart": 1}}},
            ),
            (
                "ExtrapolatedClock",
                {
                    "Utc": "2026-03-07T05:00:01Z",
                    "Remaining": "00:17:59",
                    "Extrapolating": True,
                },
            ),
            (
                "ExtrapolatedClock",
                {
                    "Utc": "2026-03-07T05:18:00Z",
                    "Remaining": "00:00:00",
                    "Extrapolating": False,
                },
            ),
            # Q2 segment + start + new clock
            (
                "SessionData",
                {"Series": {"2": {"Utc": "2026-03-07T05:25:00Z", "QualifyingPart": 2}}},
            ),
            (
                "SessionData",
                {
                    "StatusSeries": {
                        "14": {
                            "Utc": "2026-03-07T05:26:00Z",
                            "SessionStatus": "Started",
                        }
                    }
                },
            ),
            (
                "ExtrapolatedClock",
                {
                    "Utc": "2026-03-07T05:26:01Z",
                    "Remaining": "00:14:59",
                    "Extrapolating": True,
                },
            ),
        ],
    )

    now_utc = _utc("2026-03-07T05:27:01Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    state = coordinator._build_state()
    assert state["session_part"] == 2
    assert state["clock_total_s"] == 15 * 60
    assert state["clock_remaining_s"] == 899 - 60  # 839
    assert state["clock_elapsed_s"] == 15 * 60 - state["clock_remaining_s"]
    assert state["clock_running"] is True


@pytest.mark.asyncio
async def test_session_clock_race_overtime_phase(hass, monkeypatch) -> None:
    """When the race 2-hour clock reaches 0 but status is still Started,
    clock_phase should be 'overtime' rather than 'idle'."""
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    coordinator._session_info = {"Type": "Race", "Name": "Race"}
    coordinator._clock_anchor_utc = _utc("2026-03-08T13:00:01Z")
    coordinator._clock_anchor_remaining_s = 7199
    coordinator._clock_anchor_extrapolating = True
    coordinator._update_clock_total(0, 7199)
    coordinator._last_heartbeat_utc = _utc("2026-03-08T15:00:05Z")
    coordinator._last_heartbeat_mono = time.monotonic()

    # Simulate: 2h+ have passed, remaining is now 0 but race still Started
    coordinator._session_status = {"Status": "Started"}

    now_utc = _utc("2026-03-08T15:01:00Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    state = coordinator._build_state()
    assert state["clock_remaining_s"] == 0
    assert state["clock_running"] is False
    assert state["clock_phase"] == "overtime"


class _FakeSessionManager:
    """Minimal session manager that supports add_listener/notify."""

    def __init__(self, state: ReplayState = ReplayState.IDLE) -> None:
        self._state = state
        self._listeners: list = []

    def add_listener(self, callback):
        self._listeners.append(callback)
        callback(self._get_snapshot())

        def _unsub():
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _unsub

    def _get_snapshot(self) -> dict:
        return {"state": self._state.value}

    def notify(self, state: ReplayState) -> None:
        self._state = state
        snapshot = self._get_snapshot()
        for listener in list(self._listeners):
            listener(snapshot)


class _FakeReplayController:
    """Minimal replay controller exposing session_manager."""

    def __init__(self) -> None:
        self._sm = _FakeSessionManager()
        self.state = ReplayState.IDLE

    @property
    def session_manager(self):
        return self._sm


@pytest.mark.asyncio
async def test_session_clock_replay_pause_triggers_immediate_deliver(
    hass, monkeypatch
) -> None:
    """When replay pauses, the clock coordinator should immediately update
    clock_running=False and clock_phase='paused' without waiting for the
    next stream message or tick."""
    fake_rc = _FakeReplayController()
    coordinator = SessionClockCoordinator(
        hass, session_coord=object(), replay_controller=fake_rc
    )
    # Manually subscribe (normally done in async_config_entry_first_refresh)
    coordinator._replay_state_unsub = fake_rc.session_manager.add_listener(
        coordinator._on_replay_state_change
    )

    # Set up a running race clock
    coordinator._session_info = {"Type": "Race", "Name": "Race"}
    coordinator._session_status = {"Status": "Started"}
    coordinator._clock_anchor_utc = _utc("2026-03-08T13:00:01Z")
    coordinator._clock_anchor_remaining_s = 7000
    coordinator._clock_anchor_extrapolating = True
    coordinator._update_clock_total(0, 7000)
    coordinator._last_heartbeat_utc = _utc("2026-03-08T13:00:06Z")
    coordinator._last_heartbeat_mono = time.monotonic()

    now_utc = _utc("2026-03-08T13:00:11Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    # Verify clock is running initially
    coordinator._deliver()
    state = coordinator.data
    assert state["clock_running"] is True
    assert state["clock_phase"] == "running"

    # Simulate replay pause — make _replay_controller_state return PAUSED
    fake_rc.state = ReplayState.PAUSED
    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.PAUSED
    )

    # Fire the session manager notification
    fake_rc.session_manager.notify(ReplayState.PAUSED)

    # The coordinator should have been delivered with paused state
    state = coordinator.data
    assert state["clock_running"] is False
    assert state["clock_phase"] == "paused"


@pytest.mark.asyncio
async def test_session_clock_replay_resume_triggers_immediate_deliver(
    hass, monkeypatch
) -> None:
    """When replay resumes from paused, the clock coordinator should
    immediately update clock_running=True and restart the tick."""
    fake_rc = _FakeReplayController()
    coordinator = SessionClockCoordinator(
        hass, session_coord=object(), replay_controller=fake_rc
    )
    coordinator._replay_state_unsub = fake_rc.session_manager.add_listener(
        coordinator._on_replay_state_change
    )

    # Set up a race clock that was paused
    coordinator._session_info = {"Type": "Race", "Name": "Race"}
    coordinator._session_status = {"Status": "Started"}
    coordinator._clock_anchor_utc = _utc("2026-03-08T13:00:01Z")
    coordinator._clock_anchor_remaining_s = 7000
    coordinator._clock_anchor_extrapolating = True
    coordinator._update_clock_total(0, 7000)
    coordinator._last_heartbeat_utc = _utc("2026-03-08T13:00:06Z")
    coordinator._last_heartbeat_mono = time.monotonic()

    now_utc = _utc("2026-03-08T13:00:11Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    # Start in paused state
    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.PAUSED
    )
    coordinator._deliver()
    state = coordinator.data
    assert state["clock_running"] is False
    assert state["clock_phase"] == "paused"

    # Simulate replay resume
    fake_rc.state = ReplayState.PLAYING
    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.PLAYING
    )

    fake_rc.session_manager.notify(ReplayState.PLAYING)

    state = coordinator.data
    assert state["clock_running"] is True
    assert state["clock_phase"] == "running"


@pytest.mark.asyncio
async def test_session_clock_replay_seeking_freezes_clock(hass, monkeypatch) -> None:
    """During a replay seek, time should freeze at the last heartbeat."""
    fake_rc = _FakeReplayController()
    coordinator = SessionClockCoordinator(
        hass, session_coord=object(), replay_controller=fake_rc
    )
    coordinator._replay_state_unsub = fake_rc.session_manager.add_listener(
        coordinator._on_replay_state_change
    )

    coordinator._session_info = {"Type": "Race", "Name": "Race"}
    coordinator._session_status = {"Status": "Started"}
    coordinator._clock_anchor_utc = _utc("2026-03-08T13:00:01Z")
    coordinator._clock_anchor_remaining_s = 7000
    coordinator._clock_anchor_extrapolating = True
    coordinator._update_clock_total(0, 7000)
    heartbeat_utc = _utc("2026-03-08T13:00:06Z")
    coordinator._last_heartbeat_utc = heartbeat_utc
    coordinator._last_heartbeat_mono = time.monotonic()

    # Running state — clock advances with monotonic
    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.PLAYING
    )
    coordinator._deliver()
    state = coordinator.data
    assert state["clock_running"] is True

    # Start seeking — clock should freeze at heartbeat
    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.SEEKING
    )
    fake_rc.session_manager.notify(ReplayState.SEEKING)

    state = coordinator.data
    assert state["clock_running"] is False
    assert state["clock_phase"] == "paused"
    frozen_remaining = state["clock_remaining_s"]

    # Even with time passing, the remaining should stay the same during seek
    coordinator._deliver()
    state2 = coordinator.data
    assert state2["clock_remaining_s"] == frozen_remaining


@pytest.mark.asyncio
async def test_session_clock_replay_server_now_utc_uses_heartbeat(
    hass, monkeypatch
) -> None:
    """In replay mode, _server_now_utc should derive time from the heartbeat
    anchor, not from wall-clock. This ensures clock values follow replay time."""
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    heartbeat_utc = _utc("2026-03-08T13:00:00Z")
    coordinator._last_heartbeat_utc = heartbeat_utc
    mono_ref = time.monotonic()
    coordinator._last_heartbeat_mono = mono_ref

    # Simulate 5 seconds of monotonic time passing
    monkeypatch.setattr(time, "monotonic", lambda: mono_ref + 5.0)

    now = coordinator._server_now_utc()
    expected = heartbeat_utc + timedelta(seconds=5)
    assert abs((now - expected).total_seconds()) < 0.1


@pytest.mark.asyncio
async def test_session_clock_replay_pause_freezes_server_now_utc(
    hass, monkeypatch
) -> None:
    """When replay is paused, _server_now_utc should return the frozen
    heartbeat time and not advance with monotonic clock."""
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    heartbeat_utc = _utc("2026-03-08T13:05:00Z")
    mono_ref = time.monotonic()
    coordinator._last_heartbeat_utc = heartbeat_utc
    coordinator._last_heartbeat_mono = mono_ref

    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.PAUSED
    )

    # Even with 30 seconds of monotonic time passing, server_now stays frozen
    monkeypatch.setattr(time, "monotonic", lambda: mono_ref + 30.0)

    now = coordinator._server_now_utc()
    assert now == heartbeat_utc


@pytest.mark.asyncio
async def test_session_clock_replay_pause_freezes_current_logical_time(
    hass, monkeypatch
) -> None:
    """Pausing replay must freeze the current logical replay time, not jump
    back to the last raw heartbeat timestamp."""
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    heartbeat_utc = _utc("2026-03-08T13:05:00Z")
    mono_ref = time.monotonic()
    coordinator._last_heartbeat_utc = heartbeat_utc
    coordinator._last_heartbeat_mono = mono_ref
    coordinator._replay_now_anchor_utc = heartbeat_utc
    coordinator._replay_now_anchor_mono = mono_ref

    paused_mono = mono_ref + 55.0
    monkeypatch.setattr(time, "monotonic", lambda: paused_mono)
    coordinator._on_replay_state_change({"state": ReplayState.PAUSED.value})
    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.PAUSED
    )

    now = coordinator._server_now_utc()
    assert now == heartbeat_utc + timedelta(seconds=55)


@pytest.mark.asyncio
async def test_session_clock_replay_resume_keeps_pause_gap_out_of_logical_time(
    hass, monkeypatch
) -> None:
    """Resuming replay must continue from the frozen replay time instead of
    adding the wall-clock pause duration to the logical session time."""
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    heartbeat_utc = _utc("2026-03-08T13:05:00Z")
    mono_ref = time.monotonic()
    coordinator._last_heartbeat_utc = heartbeat_utc
    coordinator._last_heartbeat_mono = mono_ref
    coordinator._replay_now_anchor_utc = heartbeat_utc
    coordinator._replay_now_anchor_mono = mono_ref

    paused_mono = mono_ref + 55.0
    monkeypatch.setattr(time, "monotonic", lambda: paused_mono)
    coordinator._on_replay_state_change({"state": ReplayState.PAUSED.value})
    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.PAUSED
    )

    resumed_mono = paused_mono + 30.0
    monkeypatch.setattr(time, "monotonic", lambda: resumed_mono)
    coordinator._on_replay_state_change({"state": ReplayState.PLAYING.value})
    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.PLAYING
    )

    after_resume_mono = resumed_mono + 5.0
    monkeypatch.setattr(time, "monotonic", lambda: after_resume_mono)

    now = coordinator._server_now_utc()
    assert now == heartbeat_utc + timedelta(seconds=60)


@pytest.mark.asyncio
async def test_session_clock_replay_full_lifecycle(hass, monkeypatch) -> None:
    """End-to-end test: replay plays, pauses, resumes, finishes —
    clock state transitions mirror what would happen in live mode."""
    fake_rc = _FakeReplayController()
    coordinator = SessionClockCoordinator(
        hass, session_coord=object(), replay_controller=fake_rc
    )
    coordinator._replay_state_unsub = fake_rc.session_manager.add_listener(
        coordinator._on_replay_state_change
    )

    # Capture real monotonic at heartbeat time
    mono_base = time.monotonic()

    # Phase 1: Replay starts playing a practice session
    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.PLAYING
    )
    _apply_session_clock_events(
        coordinator,
        [
            ("SessionInfo", {"Type": "Practice", "Name": "Practice 1"}),
            ("SessionStatus", {"Status": "Started"}),
            (
                "ExtrapolatedClock",
                {
                    "Utc": "2026-03-06T01:30:01Z",
                    "Remaining": "00:59:59",
                    "Extrapolating": True,
                },
            ),
            ("Heartbeat", {"Utc": "2026-03-06T01:30:06Z"}),
        ],
    )
    # Fix heartbeat mono anchor to our known base
    coordinator._last_heartbeat_mono = mono_base
    coordinator._replay_now_anchor_mono = mono_base

    # Simulate 5 seconds after heartbeat
    monkeypatch.setattr(time, "monotonic", lambda: mono_base + 5.0)

    state = coordinator._build_state()
    assert state["clock_running"] is True
    assert state["clock_phase"] == "running"
    assert state["clock_remaining_s"] == 3589  # 59:59 - 10s
    assert state["session_name"] == "Practice 1"

    # Phase 2: User pauses replay
    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.PAUSED
    )
    fake_rc.session_manager.notify(ReplayState.PAUSED)

    state = coordinator.data
    assert state["clock_running"] is False
    assert state["clock_phase"] == "paused"
    paused_remaining = state["clock_remaining_s"]

    # Phase 3: Real time passes while paused — remaining should not change
    # because _server_now_utc freezes at last heartbeat during pause
    monkeypatch.setattr(time, "monotonic", lambda: mono_base + 300.0)
    coordinator._deliver()
    state = coordinator.data
    assert state["clock_remaining_s"] == paused_remaining

    # Phase 4: User resumes replay — new heartbeat arrives
    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.PLAYING
    )
    coordinator._on_heartbeat({"Utc": "2026-03-06T01:30:11Z"})
    mono_resume = mono_base + 301.0
    coordinator._last_heartbeat_mono = mono_resume
    monkeypatch.setattr(time, "monotonic", lambda: mono_resume)
    fake_rc.session_manager.notify(ReplayState.PLAYING)

    state = coordinator.data
    assert state["clock_running"] is True
    assert state["clock_phase"] == "running"

    # Phase 5: Session finishes
    coordinator._on_session_status({"Status": "Finished"})
    coordinator._on_extrapolated_clock(
        {
            "Utc": "2026-03-06T02:30:00Z",
            "Remaining": "00:00:00",
            "Extrapolating": False,
        }
    )
    coordinator._on_heartbeat({"Utc": "2026-03-06T02:30:05Z"})
    mono_finish = mono_resume + 5.0
    coordinator._last_heartbeat_mono = mono_finish
    monkeypatch.setattr(time, "monotonic", lambda: mono_finish)
    coordinator._deliver()

    state = coordinator.data
    assert state["clock_running"] is False
    assert state["clock_phase"] == "finished"
    assert state["clock_remaining_s"] == 0


@pytest.mark.asyncio
async def test_session_clock_should_tick_stops_during_seeking(
    hass, monkeypatch
) -> None:
    """_should_tick should return False during SEEKING state, not just PAUSED."""
    coordinator = SessionClockCoordinator(hass, session_coord=object())
    coordinator._session_info = {"Type": "Race", "Name": "Race"}
    coordinator._session_status = {"Status": "Started"}
    coordinator._clock_anchor_utc = _utc("2026-03-08T13:00:01Z")
    coordinator._clock_anchor_remaining_s = 7000
    coordinator._clock_anchor_extrapolating = True
    coordinator._update_clock_total(0, 7000)
    coordinator._last_heartbeat_utc = _utc("2026-03-08T13:00:06Z")
    coordinator._last_heartbeat_mono = time.monotonic()

    now_utc = _utc("2026-03-08T13:00:11Z")
    monkeypatch.setattr(coordinator, "_server_now_utc", lambda: now_utc)

    # Running — should tick
    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.PLAYING
    )
    state = coordinator._build_state()
    assert coordinator._should_tick(state) is True

    # Paused — should not tick
    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.PAUSED
    )
    state = coordinator._build_state()
    assert coordinator._should_tick(state) is False

    # Seeking — should not tick
    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.SEEKING
    )
    state = coordinator._build_state()
    assert coordinator._should_tick(state) is False

    # Back to playing — should tick again
    monkeypatch.setattr(
        coordinator, "_replay_controller_state", lambda: ReplayState.PLAYING
    )
    state = coordinator._build_state()
    assert coordinator._should_tick(state) is True
