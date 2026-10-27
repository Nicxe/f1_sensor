"""Retain source-backed live lane times without inventing stationary services."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant import config_entries
import pytest

from custom_components import f1_sensor as f1
from custom_components.f1_sensor.signalr import LiveBus


@pytest.fixture
def race_pits():
    return json.loads(
        (Path(__file__).parent / "fixtures/pit_lane_us_race.json").read_text()
    )


@pytest.fixture
async def pit_runtime(hass):
    bus = LiveBus(hass, MagicMock(), auth_header="Bearer test-token")
    entry = MagicMock()
    entry.state = config_entries.ConfigEntryState.SETUP_IN_PROGRESS
    coordinator = f1.PitStopCoordinator(
        hass, SimpleNamespace(data={}), bus=bus, config_entry=entry
    )
    await coordinator.async_config_entry_first_refresh()
    try:
        yield bus, coordinator
    finally:
        await coordinator.async_close()
    assert not any(bus._subs.values())


def lane(bus, car="41", **fields):
    bus.inject_message("PitLaneTimeCollection", {"PitTimes": {car: fields}})


@pytest.mark.asyncio
async def test_saved_multiple_stops_survive_collection_expiry(pit_runtime, race_pits):
    bus, coordinator = pit_runtime
    bus.inject_message("SessionInfo", race_pits["session"])
    for event in race_pits["lane_events"]:
        bus.inject_message("PitLaneTimeCollection", event["payload"])
    assert coordinator.data["total_stops"] == 3
    assert not coordinator._lane_partial
    stop = coordinator.data["cars"]["41"]["stops"][0]
    assert stop == {
        "lap": 18,
        "timestamp": None,
        "pit_stop_time": None,
        "pit_lane_time": 23.7,
        "pit_delta": None,
        "source": "PitLaneTimeCollection",
    }
    # A new connection's empty snapshot and repeated rows cannot erase or double history.
    bus.inject_message("PitLaneTimeCollection", {"PitTimes": {}, "_kf": True})
    for event in race_pits["lane_events"]:
        bus.inject_message("PitLaneTimeCollection", event["payload"])
    assert coordinator.data["total_stops"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("series_first", [False, True])
async def test_authoritative_series_wins_in_either_order(
    pit_runtime, race_pits, series_first
):
    bus, coordinator = pit_runtime
    bus.inject_message("SessionInfo", race_pits["session"])

    def send_series():
        for event in race_pits["series_events"]:
            bus.inject_message("PitStopSeries", event["payload"])

    if series_first:
        send_series()
    for event in race_pits["lane_events"]:
        bus.inject_message("PitLaneTimeCollection", event["payload"])
    if not series_first:
        send_series()
    assert coordinator.data["total_stops"] == 3
    stop = coordinator.data["cars"]["41"]["stops"][0]
    assert stop["source"] == "PitStopSeries"
    assert stop["pit_stop_time"] == 2.3
    assert stop["pit_lane_time"] == 23.793
    assert stop["timestamp"] == "2026-10-25T20:35:26.655Z"


@pytest.mark.asyncio
async def test_partial_updates_lap_changes_and_corrections(pit_runtime):
    bus, coordinator = pit_runtime
    bus.inject_message("SessionInfo", {"Key": 11396})
    lane(bus, Lap="18")
    assert coordinator.data["total_stops"] == 0
    lane(bus, Duration="23.7")
    lane(bus, Duration="23.8")
    assert coordinator.data["total_stops"] == 1
    assert coordinator.data["cars"]["41"]["stops"][0]["pit_lane_time"] == 23.8
    lane(bus, Lap="19")
    assert coordinator.data["total_stops"] == 1
    lane(bus, Duration="24.1")
    assert [s["lap"] for s in coordinator.data["cars"]["41"]["stops"]] == [18, 19]
    bus.inject_message("PitLaneTimeCollection", {"PitTimes": {"_deleted": ["41"]}})
    lane(bus, Duration="25.1")
    assert coordinator.data["total_stops"] == 2
    # A keyframe must drop incomplete state as well as complete active rows.
    bus.inject_message("PitLaneTimeCollection", {"PitTimes": {}, "_kf": True})
    lane(bus, Lap="20")
    assert coordinator.data["total_stops"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("car", "fields"),
    [
        ("../41", {"Lap": "18", "Duration": "23.7"}),
        ("41", {"RacingNumber": "44", "Lap": "18", "Duration": "23.7"}),
        ("41", {"Lap": True, "Duration": "23.7"}),
        ("41", {"Lap": "18.5", "Duration": "23.7"}),
        ("41", {"Lap": -1, "Duration": "23.7"}),
        ("41", {"Lap": "18", "Duration": True}),
        ("41", {"Lap": "18", "Duration": "NaN"}),
        ("41", {"Lap": "18", "Duration": "inf"}),
        ("41", {"Lap": "18", "Duration": -1}),
        ("41", {"Lap": "18", "Duration": 0}),
        ("41", {"Lap": "18", "Duration": {}}),
    ],
)
async def test_invalid_collection_rows_do_not_invent_stops(pit_runtime, car, fields):
    bus, coordinator = pit_runtime
    bus.inject_message("SessionInfo", {"Key": 11396})
    lane(bus, car, **fields)
    assert coordinator.data["total_stops"] == 0
    assert not coordinator._by_car


@pytest.mark.asyncio
async def test_live_gates_reset_and_replay(pit_runtime, hass):
    bus, coordinator = pit_runtime
    lane(bus, Lap="18", Duration="23.7")
    assert not coordinator._by_car  # Session identity has not been established.
    bus.inject_message("SessionInfo", {"Key": 11396})
    lane(bus, Lap="18")
    bus.inject_message("SessionInfo", {"Key": 11397})
    lane(bus, Duration="23.7")
    assert not coordinator._by_car  # Previous session's partial lap is gone.
    lane(bus, Lap="1", Duration="24.0")
    assert coordinator.data["total_stops"] == 1
    f1._reset_replay_sensitive_coordinator_state(coordinator)
    assert not coordinator._lane_partial
    assert not coordinator._by_car
    coordinator._replay_mode = True
    bus.inject_message("SessionInfo", {"Key": 11396})
    lane(bus, Lap="18", Duration="23.7")
    assert not coordinator._by_car
    bus.inject_message(
        "PitStopSeries",
        {
            "PitTimes": {
                "41": [
                    {
                        "Timestamp": "2026-10-25T20:35:26.655Z",
                        "PitStop": {
                            "Lap": 18,
                            "PitStopTime": 2.3,
                            "PitLaneTime": 23.793,
                        },
                    }
                ]
            }
        },
    )
    assert coordinator.data["total_stops"] == 1
    coordinator._replay_mode = False
    f1._reset_replay_sensitive_coordinator_state(coordinator)
    bus.inject_message("SessionInfo", {"Key": 11396})
    hass.data.setdefault(f1.DOMAIN, {})["no_spoiler_manager"] = SimpleNamespace(
        is_active=True
    )
    lane(bus, Lap="18", Duration="23.7")
    assert not coordinator._by_car
    hass.data[f1.DOMAIN]["no_spoiler_manager"].is_active = False
    bus._auth_enabled = False
    lane(bus, Lap="18", Duration="23.7")
    assert not coordinator._by_car


@pytest.mark.asyncio
async def test_series_corrections_do_not_duplicate_distinct_events(pit_runtime):
    bus, coordinator = pit_runtime
    bus.inject_message("SessionInfo", {"Key": 11396})

    def series(timestamp, duration):
        bus.inject_message(
            "PitStopSeries",
            {
                "PitTimes": {
                    "41": [
                        {
                            "Timestamp": timestamp,
                            "PitStop": {
                                "Lap": 18,
                                "PitStopTime": 2.3,
                                "PitLaneTime": duration,
                            },
                        }
                    ]
                }
            },
        )

    lane(bus, Lap="18", Duration="23.7")
    series("2026-10-25T20:35:26.655Z", 23.793)
    series("2026-10-25T20:35:26.655Z", 23.795)
    assert len(coordinator.data["cars"]["41"]["stops"]) == 1
    series("2026-10-25T20:36:26.655Z", 24.1)
    lane(bus, Lap="18", Duration="24.1")
    stops = coordinator.data["cars"]["41"]["stops"]
    assert len(stops) == 2
    assert [s["pit_lane_time"] for s in stops] == [23.795, 24.1]
    assert all(s["source"] == "PitStopSeries" for s in stops)


@pytest.mark.asyncio
async def test_fallback_shares_50_second_delay_and_pending_cleanup(
    pit_runtime, monkeypatch
):
    bus, coordinator = pit_runtime
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
    coordinator.set_delay(50)
    bus.inject_message("SessionInfo", {"Key": 11396})
    lane(bus, Lap="18", Duration="23.7")
    assert not coordinator._by_car
    clock.value += 49.9
    f1._drain_delayed_ingest_queue(coordinator)
    assert not coordinator._by_car
    clock.value += 0.1
    f1._drain_delayed_ingest_queue(coordinator)
    assert coordinator.data["total_stops"] == 1
    lane(bus, Lap="19", Duration="24.1")
    coordinator._handle_live_state(False, "no-spoiler")
    clock.value += 50
    f1._drain_delayed_ingest_queue(coordinator)
    assert coordinator.data["total_stops"] == 1
    assert not coordinator._lane_partial


@pytest.mark.asyncio
async def test_collection_history_and_partial_state_are_bounded(pit_runtime):
    bus, coordinator = pit_runtime
    bus.inject_message("SessionInfo", {"Key": 11396})
    for lap_number in range(1, 25):
        lane(bus, Lap=lap_number, Duration="23.7")
    assert (
        len(coordinator.data["cars"]["41"]["stops"]) == f1.PITSTOP_MAX_HISTORY_PER_CAR
    )
    for car in range(1, f1.PITSTOP_MAX_CARS + 30):
        lane(bus, str(car), Lap=1, Duration="23.7")
    assert len(coordinator._by_car) == f1.PITSTOP_MAX_CARS
    assert len(coordinator._lane_partial) <= f1.PITSTOP_MAX_CARS


@pytest.mark.asyncio
async def test_late_series_lap_correction_suppresses_fallback(pit_runtime):
    bus, coordinator = pit_runtime
    bus.inject_message("SessionInfo", {"Key": 11396})
    timestamp = "2026-10-25T20:35:26.655Z"
    bus.inject_message(
        "PitStopSeries",
        {
            "PitTimes": {
                "41": [
                    {
                        "Timestamp": timestamp,
                        "PitStop": {"PitStopTime": 2.3},
                    }
                ]
            }
        },
    )
    lane(bus, Lap="18", Duration="23.7")
    assert coordinator.data["total_stops"] == 2  # Association is not yet known.
    bus.inject_message(
        "PitStopSeries",
        {
            "PitTimes": {
                "41": [
                    {
                        "Timestamp": timestamp,
                        "PitStop": {"Lap": 18, "PitLaneTime": 23.793},
                    }
                ]
            }
        },
    )
    stops = coordinator.data["cars"]["41"]["stops"]
    assert len(stops) == 1
    assert stops[0]["pit_stop_time"] == 2.3
    assert stops[0]["lap"] == 18
    assert stops[0]["source"] == "PitStopSeries"


@pytest.mark.asyncio
async def test_lap_loss_updates_do_not_mutate_published_snapshots(pit_runtime):
    bus, coordinator = pit_runtime
    bus.inject_message("SessionInfo", {"Key": 11396})
    driver = {"lap_history": {"laps": {"17": "1:40.000"}}}
    coordinator._drivers_coord = SimpleNamespace(data={"drivers": {"41": driver}})
    lane(bus, Lap="18", Duration="23.7")
    previous = coordinator.data
    assert previous["cars"]["41"]["stops"][0]["pit_delta"] is None
    driver["lap_history"]["laps"].update({"18": "2:00.000", "19": "1:40.000"})
    coordinator._on_drivers_update()
    assert coordinator.data["cars"]["41"]["stops"][0]["pit_delta"] == 20
    assert previous["cars"]["41"]["stops"][0]["pit_delta"] is None
