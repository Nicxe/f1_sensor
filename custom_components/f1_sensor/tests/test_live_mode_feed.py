"""Race director mode changes on the ordered live/replay feed."""

from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import LiveModeCoordinator
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.signalr import LiveBus


@pytest.mark.parametrize("status,expected", [("4", False), ("6", True), ("7", True)])
async def test_overtake_safety_car_requires_fresh_permission(hass, status, expected):
    bus = LiveBus(hass, AsyncMock())
    live = LiveAvailabilityTracker()
    entry = MockConfigEntry(domain="f1_sensor")
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    mode = LiveModeCoordinator(hass, bus, config_entry=entry, live_state=live)
    try:
        live.set_state(True, "live-Race")
        await mode.async_config_entry_first_refresh()
        bus.inject_message(
            "SessionInfo",
            {"Key": 11321, "Name": "Sprint", "StartDate": "2026-07-04T12:00:00"},
        )
        bus.inject_message(
            "RaceControlMessages", {"Category": "Other", "Message": "OVERTAKE ENABLED"}
        )
        bus.inject_message("TrackStatus", {"Status": status})
        assert mode.data["overtake_enabled"] is expected
        bus.inject_message("TrackStatus", {"Status": "1"})
        assert mode.data["overtake_enabled"] is expected
        bus.inject_message(
            "RaceControlMessages", {"Category": "Other", "Message": "OVERTAKE ENABLED"}
        )
        assert mode.data["overtake_enabled"] is True
    finally:
        await mode.async_close()
        await bus.async_close()


@pytest.fixture
async def make_source(hass):
    entry = MockConfigEntry(domain="f1_sensor")
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    active = []

    async def create(reason="live-Race"):
        if active:
            old_mode, old_bus = active.pop()
            await old_mode.async_close()
            await old_bus.async_close()
        bus = LiveBus(hass, AsyncMock())
        tracker = LiveAvailabilityTracker()
        mode = LiveModeCoordinator(hass, bus, config_entry=entry, live_state=tracker)
        active.append((mode, bus))
        tracker.set_state(True, reason)
        await mode.async_config_entry_first_refresh()
        return mode, bus

    yield create
    for mode, bus in active:
        await mode.async_close()
        await bus.async_close()


SAO_PAULO = {
    "Key": 11412,
    "Name": "Race",
    "StartDate": "2026-11-08T14:00:00",
    "GmtOffset": "-03:00:00",
    "Meeting": {"Key": 1299, "Circuit": {"Key": 14}},
}


def _report(bus, text, stamp=None):
    item = {"Category": "Other", "Message": text}
    if stamp:
        item["Utc"] = stamp
    bus.inject_message("RaceControlMessages", item)


async def test_snapshot_before_identity_hydrates_once_and_filters_previous_session(
    make_source,
):
    mode, bus = await make_source()
    states = []
    mode.async_add_listener(lambda: states.append(mode.data))
    bus.inject_message(
        "RaceControlMessages",
        {
            "Messages": {
                "1": {
                    "Category": "Other",
                    "Message": "OVERTAKE ENABLED",
                    "Utc": "2026-11-07T16:50:00",
                },
                "2": {
                    "Category": "Other",
                    "Message": "LOW GRIP CONDITIONS",
                    "Utc": "2026-11-08T16:13:00",
                },
            }
        },
    )
    bus.inject_message("SessionInfo", {"Key": SAO_PAULO["Key"]})
    assert mode.data is None
    bus.inject_message("SessionInfo", SAO_PAULO)
    assert mode.data == {
        "track_grip": "low",
        "straight_mode": "low_grip",
        "overtake_enabled": False,
    }
    assert [d for d in states if d is not None] == [mode.data]
    _report(bus, "OVERTAKE ENABLED", "2026-11-08T16:14:00")
    assert mode.data["overtake_enabled"] is False
    _report(bus, "NORMAL GRIP CONDITIONS", "2026-11-08T17:35:00")
    assert mode.data == {
        "track_grip": "normal",
        "straight_mode": "normal_grip",
        "overtake_enabled": False,
    }
    _report(bus, "OVERTAKE ENABLED", "2026-11-08T17:37:00")
    assert mode.data["overtake_enabled"] is True
    _report(bus, "LOW GRIP CONDITIONS", "2026-11-08T16:13:00")
    assert mode.data["overtake_enabled"] is True
    assert mode.data["track_grip"] == "normal"


async def test_same_session_disk_restore_is_per_field_and_excludes_replay(make_source):
    mode, bus = await make_source()
    bus.inject_message("SessionInfo", SAO_PAULO)
    _report(bus, "NORMAL GRIP CONDITIONS", "2026-11-08T17:35:00")
    _report(bus, "OVERTAKE ENABLED", "2026-11-08T17:37:00")
    mode, bus = await make_source()
    assert mode.data is None
    bus.inject_message("SessionInfo", SAO_PAULO)
    assert mode.data == {
        "track_grip": "normal",
        "straight_mode": "normal_grip",
        "overtake_enabled": True,
    }
    assert mode.is_restored("straight_mode") and mode.is_restored("overtake_enabled")
    _report(bus, "OVERTAKE DISABLED", "2026-11-08T17:40:00")
    assert mode.is_restored("straight_mode")
    assert not mode.is_restored("overtake_enabled")
    mode, bus = await make_source("replay")
    bus.inject_message("SessionInfo", SAO_PAULO)
    assert mode.data is None
    _report(bus, "OVERTAKE ENABLED", "2026-11-08T16:59:00")
    assert mode.data["overtake_enabled"] is True
    mode, bus = await make_source()
    bus.inject_message("SessionInfo", SAO_PAULO)
    assert mode.data["overtake_enabled"] is False
    bus.inject_message("SessionInfo", {"Key": 11420, "Name": "Race"})
    assert mode.data is None
    assert not mode.is_restored("straight_mode")


async def test_grip_delta_does_not_declare_grip_or_disable_earlier_overtake(
    make_source,
):
    mode, bus = await make_source()
    bus.inject_message(
        "SessionInfo",
        {
            "Key": 11253,
            "Name": "Race",
            "StartDate": "2026-05-03T13:00:00",
            "Meeting": {"Key": 1284, "Circuit": {"Key": 151}},
        },
    )
    _report(bus, "LOW GRIP DELTA ACTIVE")
    assert mode.data is None
    _report(bus, "OVERTAKE ENABLED")
    _report(bus, "LOW GRIP CONDITIONS")
    assert mode.data == {
        "overtake_enabled": True,
        "straight_mode": "low_grip",
        "track_grip": "low",
    }


async def test_unverified_zones_keep_straight_unknown_and_monaco_has_none(make_source):
    mode, bus = await make_source()
    bus.inject_message(
        "SessionInfo",
        {
            "Key": 10,
            "StartDate": "2026-09-01T12:00:00",
            "Meeting": {"Key": 1, "Circuit": {"Key": 1}},
        },
    )
    _report(bus, "NORMAL GRIP CONDITIONS")
    assert mode.data == {
        "overtake_enabled": None,
        "straight_mode": None,
        "track_grip": "normal",
    }
    bus.inject_message(
        "SessionInfo",
        {
            "Key": 11,
            "StartDate": "2026-06-07T15:00:00",
            "Meeting": {"Key": 1286, "Circuit": {"Key": 22}},
        },
    )
    assert mode.data == {
        "overtake_enabled": None,
        "straight_mode": "disabled",
        "track_grip": None,
    }


@pytest.mark.parametrize("enabled_after_sc", [True, False])
async def test_sc_before_session_type_keeps_source_order(make_source, enabled_after_sc):
    mode, bus = await make_source()
    bus.inject_message(
        "SessionInfo", {"Key": 11412, "StartDate": SAO_PAULO["StartDate"]}
    )
    _report(bus, "OVERTAKE ENABLED", "2026-11-08T17:04:00")
    bus.inject_message("TrackStatus", {"Status": "4", "Utc": "2026-11-08T17:06:00"})
    if enabled_after_sc:
        _report(bus, "OVERTAKE ENABLED", "2026-11-08T17:06:00")
    bus.inject_message("SessionInfo", {"Name": "Race"})
    assert mode.data["overtake_enabled"] is enabled_after_sc


async def test_unmapped_grip_keeps_explicit_mode(make_source):
    mode, bus = await make_source()
    bus.inject_message(
        "SessionInfo",
        {"Key": 7, "Name": "Practice 1", "StartDate": "2026-06-05T12:00:00"},
    )
    _report(bus, "STRAIGHT MODE - DISABLED")
    _report(bus, "NORMAL GRIP CONDITIONS")
    assert mode.data["straight_mode"] == "disabled"
    assert mode.data["track_grip"] == "normal"


async def test_stale_terminal_does_not_consume_next_sessions_messages(hass):
    import logging

    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

    entry = MockConfigEntry(domain="f1_sensor")
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    status = DataUpdateCoordinator(hass, logging.getLogger(__name__), name="session")
    bus = LiveBus(hass, AsyncMock())
    live = LiveAvailabilityTracker()
    mode = LiveModeCoordinator(hass, bus, status, config_entry=entry, live_state=live)
    try:
        live.set_state(True, "live-Race")
        await mode.async_config_entry_first_refresh()
        bus.inject_message("SessionInfo", {"Key": 11, "Name": "Race"})
        status.async_set_updated_data({"Status": "Ends"})
        bus.inject_message("SessionInfo", {**SAO_PAULO, "Key": 12})
        _report(bus, "OVERTAKE DISABLED")
        status.async_set_updated_data({"Status": "Started"})
        assert mode.data["overtake_enabled"] is False
    finally:
        await mode.async_close()
        await bus.async_close()


async def test_restore_preserves_order_of_explicit_and_derived_state_in_same_second(
    make_source,
):
    mode, bus = await make_source()
    bus.inject_message("SessionInfo", SAO_PAULO)
    stamp = "2026-11-08T17:35:00"
    _report(bus, "NORMAL GRIP CONDITIONS", stamp)
    _report(bus, "STRAIGHT MODE - DISABLED", stamp)
    assert mode.data["straight_mode"] == "disabled"
    mode, bus = await make_source()
    bus.inject_message("SessionInfo", SAO_PAULO)
    assert mode.data["straight_mode"] == "disabled"
    assert mode.is_restored("straight_mode")
