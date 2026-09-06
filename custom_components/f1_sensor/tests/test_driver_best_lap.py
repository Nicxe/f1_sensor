"""Official individual best laps survive partial live history and source updates."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import re
from types import SimpleNamespace
from unittest.mock import Mock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import f1_sensor as f1
from custom_components.f1_sensor import (
    LiveDriversCoordinator,
    _reset_replay_sensitive_coordinator_state,
    sensor as sensor_platform,
)
from custom_components.f1_sensor.const import (
    CONF_LIVE_TIMING_AUTH_HEADER,
    DOMAIN,
    SUPPORTED_SENSOR_KEYS,
)
from custom_components.f1_sensor.sensor import F1DriverPositionsSensor
from custom_components.f1_sensor.signalr import LiveBus
from custom_components.f1_sensor.tests.test_auth import _jwt


@pytest.fixture
async def live_driver(hass):
    """Use actual bus subscription, timing ingestion and sensor transformation."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", ConfigEntryState.SETUP_IN_PROGRESS)
    bus = LiveBus(hass, Mock())
    coordinator = LiveDriversCoordinator(
        hass, SimpleNamespace(data={}), bus=bus, config_entry=entry
    )
    await coordinator.async_config_entry_first_refresh()
    sensor = F1DriverPositionsSensor(coordinator, "best", entry.entry_id, "F1")
    sensor.hass = hass
    sensor._session_info_coordinator = SimpleNamespace(
        data={"Type": "Practice", "Name": "Practice 3"}
    )

    def send(line):
        bus._dispatch("TimingData", {"Lines": {"1": line}})
        sensor._update_from_coordinator()
        return next(
            driver
            for driver in sensor.extra_state_attributes["drivers"]
            if driver["racing_number"] == "1"
        )

    try:
        yield coordinator, sensor, send
    finally:
        await coordinator.async_close()
        await bus.async_close()


def _partial_snapshot():
    # Synthetic source times: connection begins after the earlier best lap.
    return {
        "Position": "4",
        "NumberOfLaps": 17,
        "LastLapTime": {"Value": "1:41.181"},
        "BestLapTime": {"Value": "1:22.345", "Lap": 5},
    }


async def test_partial_history_exposes_official_individual_best(live_driver):
    _, _, send = live_driver
    driver = send(_partial_snapshot())
    assert driver["laps"] == {"17": "1:41.181"}
    assert driver["best_lap_time"] == "1:22.345"
    assert driver["best_lap_time_secs"] == pytest.approx(82.345)
    assert driver["best_lap_lap"] == 5
    # The existing session-fastest flag still does not apply to practice.
    assert driver["fastest_lap"] is False
    assert driver["fastest_lap_time"] is None


async def test_best_survives_omitted_deltas_and_accepts_slower_correction(live_driver):
    _, _, send = live_driver
    send(_partial_snapshot())
    driver = send({"Position": "6", "BestLapTime": {}})
    assert driver["best_lap_time"] == "1:22.345"
    assert driver["best_lap_lap"] == 5
    driver = send({"BestLapTime": {"Value": "1:25.678", "Lap": 8}})
    assert driver["best_lap_time"] == "1:25.678"
    assert driver["best_lap_time_secs"] == pytest.approx(85.678)
    assert driver["best_lap_lap"] == 8
    # Local history can include a subsequently deleted lap; it is not authority.
    driver = send({"NumberOfLaps": 18, "LastLapTime": {"Value": "1:20.000"}})
    assert driver["best_lap_time"] == "1:25.678"
    assert driver["best_lap_lap"] == 8
    driver = send({"BestLapTime": {"Value": "1:26.000"}})
    assert driver["best_lap_time"] == "1:26.000"
    assert driver["best_lap_lap"] is None
    driver = send({"BestLapTime": {"Lap": 9}})
    assert driver["best_lap_time"] == "1:26.000"
    assert driver["best_lap_lap"] == 9


@pytest.mark.parametrize(
    "cleared",
    [None, {"Value": None}, {"Value": ""}, {"Deleted": True}],
)
async def test_explicit_best_clear_does_not_resurrect_local_history(
    live_driver, cleared
):
    _, _, send = live_driver
    send(_partial_snapshot())
    driver = send({"BestLapTime": cleared})
    assert driver["best_lap_time"] is None
    assert driver["best_lap_time_secs"] is None
    assert driver["best_lap_lap"] is None
    driver = send({"NumberOfLaps": 18, "LastLapTime": {"Value": "1:20.000"}})
    assert driver["laps"]["18"] == "1:20.000"
    assert driver["best_lap_time"] is None
    assert driver["best_lap_time_secs"] is None
    assert driver["best_lap_lap"] is None


@pytest.mark.parametrize("value", ["NaN", "inf", "0", "-1", "invalid"])
async def test_invalid_official_best_is_unknown(live_driver, value):
    _, _, send = live_driver
    driver = send({"BestLapTime": {"Value": value, "Lap": 5}})
    assert driver["best_lap_time"] is None
    assert driver["best_lap_time_secs"] is None
    assert driver["best_lap_lap"] is None


@pytest.mark.parametrize("reset", ["live_window", "replay"])
async def test_best_resets_at_live_and_replay_session_boundaries(live_driver, reset):
    coordinator, _, send = live_driver
    send(_partial_snapshot())
    if reset == "replay":
        _reset_replay_sensitive_coordinator_state(coordinator)
    else:
        coordinator._handle_live_state(False, "window-ended")
        coordinator._handle_live_state(True, "live_window")
    driver = send({"Position": "1"})
    assert driver["best_lap_time"] is None
    assert driver["best_lap_time_secs"] is None
    assert driver["best_lap_lap"] is None
    driver = send({"NumberOfLaps": 1, "LastLapTime": {"Value": "1:30.000"}})
    assert driver["best_lap_time"] == "1:30.000"
    assert driver["best_lap_time_secs"] == 90.0


async def test_restored_driver_keeps_stable_best_attributes(live_driver):
    _, sensor, _ = live_driver
    attrs = sensor._normalize_restored_attributes({"drivers": [{"racing_number": "1"}]})
    driver = attrs["drivers"][0]
    assert driver["best_lap_time"] is None
    assert driver["best_lap_time_secs"] is None
    assert driver["best_lap_lap"] is None


@pytest.mark.parametrize("delay", [0, 30])
async def test_registered_driver_entity_delivers_best_at_existing_delay(
    hass, enable_custom_integrations, aioclient_mock, monkeypatch, delay
):
    """Verify the real entry and HA state, including exactly one live delay."""
    aioclient_mock.get(
        re.compile(r"https://.*"),
        json={"Meetings": [], "MRData": {"RaceTable": {"Races": []}}},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        data={
            "sensor_name": "F1",
            CONF_LIVE_TIMING_AUTH_HEADER: (
                f"Bearer {_jwt({'exp': int((datetime.now(UTC) + timedelta(days=2)).timestamp())})}"
            ),
        },
        options={
            "operation_mode": "live",
            "enable_race_control": True,
            "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS - {"driver_positions"}),
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    timer_cancels = []
    try:
        registry = hass.data[DOMAIN][entry.entry_id]
        bus = entry.runtime_data.live.bus
        coordinator = registry["drivers_coordinator"]
        controller = registry["live_delay_controller"]
        registry["live_state"].set_state(True, "live-Practice")
        await controller.async_set_delay(0)
        bus._dispatch("SessionInfo", {"Key": "practice", "Type": "Practice"})
        bus._dispatch("TimingData", {"Lines": {"1": _partial_snapshot()}})
        await asyncio.sleep(1.05)  # Preserve the sensor's existing 1 Hz write limit.
        await hass.async_block_till_done()
        entity_id = er.async_get(hass).async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_driver_positions"
        )

        def best():
            return hass.states.get(entity_id).attributes["drivers"][0]["best_lap_time"]

        assert best() == "1:22.345"
        clock = SimpleNamespace(value=100.0)
        monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
        await controller.async_set_delay(delay)
        bus._dispatch(
            "TimingData", {"Lines": {"1": {"BestLapTime": {"Value": "1:25.678"}}}}
        )
        bus._dispatch("TimingData", {"Lines": {"1": {"Position": "5"}}})
        await hass.async_block_till_done()
        if delay:
            assert best() == "1:22.345"
            clock.value = 129.9
            f1._drain_delayed_ingest_queue(coordinator)
            await hass.async_block_till_done()
            assert best() == "1:22.345"
            clock.value = 130.0
            f1._drain_delayed_ingest_queue(coordinator)
        await asyncio.sleep(1.05)
        await hass.async_block_till_done()
        assert best() == "1:25.678"
        assert not coordinator._delay_queue
        entity = hass.data["sensor"].get_entity(entity_id)
        assert not entity._pending_write

        # Unload while a subsequent real entity write is still rate limited.
        # Capture the actual HA timer remover, without replacing its scheduling.
        schedule = sensor_platform.async_call_later

        def record_timer(*args, **kwargs):
            cancel = Mock(wraps=schedule(*args, **kwargs))
            timer_cancels.append(cancel)
            return cancel

        monkeypatch.setattr(sensor_platform, "async_call_later", record_timer)
        await controller.async_set_delay(0)
        bus._dispatch(
            "TimingData", {"Lines": {"1": {"BestLapTime": {"Value": "1:27.000"}}}}
        )
        bus._dispatch(
            "TimingData", {"Lines": {"1": {"BestLapTime": {"Value": "1:28.000"}}}}
        )
        assert entity._pending_write
        assert len(timer_cancels) == 1
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert timer_cancels[0].called, (
            "Entry unload must cancel the pending state write"
        )
        assert not entity._pending_write
    finally:
        if entry.state is ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)
        # Clean up the real timer even against the intentionally failing baseline.
        for cancel in timer_cancels:
            cancel()
