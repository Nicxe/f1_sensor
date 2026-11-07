"""A real session change clears old values without losing queued new frames."""

import asyncio
from copy import deepcopy
import logging
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import f1_sensor as integration
from custom_components.f1_sensor.const import DOMAIN, LATEST_TRACK_STATUS
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.signalr import LiveBus


@pytest.mark.parametrize("delay", [0, 1], ids=["live", "delayed"])
@pytest.mark.parametrize(
    ("coordinator_type", "stream", "initial", "following"),
    [
        (
            integration.TeamRadioCoordinator,
            "TeamRadio",
            {
                "Captures": [
                    {
                        "Utc": "2026-11-07T18:00:00Z",
                        "RacingNumber": "16",
                        "Path": "TeamRadio/LEC_16_previous.mp3",
                    }
                ]
            },
            {
                "Captures": [
                    {
                        "Utc": "2026-11-07T20:00:00Z",
                        "RacingNumber": "63",
                        "Path": "TeamRadio/RUS_63_current.mp3",
                    }
                ]
            },
        ),
        (
            integration.TopThreeCoordinator,
            "TopThree",
            {"Lines": [{"Tla": "OLD"}, {"Tla": "OLD"}, {"Tla": "OLD"}]},
            {"Lines": {"0": {"Tla": "RUS"}}},
        ),
        (
            integration.TrackStatusCoordinator,
            "TrackStatus",
            {"Status": "5", "Message": "Red"},
            {"Status": "5", "Message": "Red"},
        ),
        (
            integration.WeatherDataCoordinator,
            "WeatherData",
            {"AirTemp": "22.0", "TrackTemp": "30.0", "Rainfall": "0"},
            {"AirTemp": "22.0", "TrackTemp": "30.0", "Rainfall": "0"},
        ),
        (
            integration.RaceControlCoordinator,
            "RaceControlMessages",
            {"Category": "Other", "Message": "OVERTAKE ENABLED"},
            {"Category": "Other", "Message": "OVERTAKE ENABLED"},
        ),
    ],
    ids=["radio", "podium", "flag", "weather", "race-control"],
)
async def test_same_identity_keeps_data_and_new_identity_resets_before_queued_frames(
    hass, coordinator_type, stream, initial, following, delay
):
    schedule = DataUpdateCoordinator(hass, logging.getLogger(__name__), name="schedule")
    schedule.data = {}
    bus = LiveBus(hass, AsyncMock(), auth_header="test-token")
    live = LiveAvailabilityTracker()
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    coordinator = coordinator_type(
        hass, schedule, bus=bus, live_state=live, config_entry=entry
    )
    observed = []
    unsubscribe = coordinator.async_add_listener(
        lambda: observed.append(deepcopy(coordinator.data))
    )
    try:
        live.set_state(True, "live-Qualifying")
        bus.inject_message("SessionInfo", {"Key": 11408, "Type": "Qualifying"})
        await coordinator.async_config_entry_first_refresh()
        bus.inject_message(stream, initial)
        await hass.async_block_till_done()
        previous = deepcopy(coordinator.data)
        assert previous

        bus.inject_message("SessionInfo", {"ArchiveStatus": {"Status": "Generating"}})
        bus.inject_message("SessionInfo", {"Key": 11408, "Type": "Qualifying"})
        await hass.async_block_till_done()
        assert coordinator.data == previous

        observed.clear()
        coordinator.set_delay(delay)
        bus.inject_message("SessionInfo", {"Key": 11409, "Type": "Race"})
        bus.inject_message(stream, following)
        if delay:
            assert coordinator.data == previous
            await asyncio.sleep(delay + 0.05)
        await hass.async_block_till_done()

        if stream == "TeamRadio":
            assert len(coordinator.data["history"]) == 1
            assert (
                coordinator.data["latest"]["Path"] == following["Captures"][0]["Path"]
            )
        elif stream == "TopThree":
            assert coordinator.data["lines"] == [{"Tla": "RUS"}, None, None]
        else:
            assert None in observed
            assert coordinator.data == following
            if stream == "TrackStatus":
                assert hass.data[LATEST_TRACK_STATUS] == following
    finally:
        unsubscribe()
        await coordinator.async_close()
        await bus.async_close()
    assert not bus._subs


@pytest.mark.parametrize("delay", [0, 1], ids=["live", "delayed"])
async def test_new_session_clears_old_modes_before_delivering_new_race_control(
    hass, delay
):
    schedule = DataUpdateCoordinator(hass, logging.getLogger(__name__), name="schedule")
    schedule.data = {}
    bus = LiveBus(hass, AsyncMock())
    live = LiveAvailabilityTracker()
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    race_control = integration.RaceControlCoordinator(
        hass, schedule, bus=bus, live_state=live, config_entry=entry
    )
    mode = integration.LiveModeCoordinator(
        hass, race_control, live_state=live, config_entry=entry
    )
    try:
        live.set_state(True, "live-Qualifying")
        bus.inject_message("SessionInfo", {"Key": 11408, "Type": "Qualifying"})
        await race_control.async_config_entry_first_refresh()
        await mode.async_config_entry_first_refresh()
        bus.inject_message(
            "RaceControlMessages", {"Category": "Other", "Message": "OVERTAKE ENABLED"}
        )
        bus.inject_message(
            "RaceControlMessages",
            {"Category": "Other", "Message": "STRAIGHT MODE - NORMAL GRIP"},
        )
        await hass.async_block_till_done()
        assert mode.data == {"overtake_enabled": True, "straight_mode": "normal_grip"}

        bus.inject_message(
            "SessionInfo", {"Key": 11408, "ArchiveStatus": {"Status": "Generating"}}
        )
        await hass.async_block_till_done()
        assert mode.data["overtake_enabled"] is True

        race_control.set_delay(delay)
        bus.inject_message("SessionInfo", {"Key": 11409, "Type": "Race"})
        following = {"Category": "Flag", "Flag": "GREEN", "Message": "GREEN LIGHT"}
        bus.inject_message("RaceControlMessages", following)
        if delay:
            assert mode.data["overtake_enabled"] is True
            await asyncio.sleep(delay + 0.05)
        await hass.async_block_till_done()

        assert mode.data is None
        assert race_control.data == following
        assert live.is_live
    finally:
        await mode.async_close()
        await race_control.async_close()
        await bus.async_close()
    assert not bus._subs
