"""Session suspension is independent of track flags (issue #982)."""

from __future__ import annotations

import json
from pathlib import Path
import re
from types import SimpleNamespace

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import f1_sensor as f1
from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS
from custom_components.f1_sensor.data_helpers import _map_session_status_payload

_CASES = json.loads(
    (Path(__file__).parent / "fixtures/issue_982_suspensions.json").read_text()
)["cases"]


@pytest.fixture
async def live_entry(hass, enable_custom_integrations, aioclient_mock):
    """Set up real entities, coordinators and bus with external HTTP mocked."""
    aioclient_mock.get(
        re.compile(r"https://.*"),
        json={"Meetings": [], "MRData": {"RaceTable": {"Races": []}}},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        data={"sensor_name": "F1", "data_choice_version": 1},
        options={
            "operation_mode": "live",
            "enable_race_control": True,
            "disabled_sensors": sorted(
                SUPPORTED_SENSOR_KEYS
                - {"session_status", "current_session", "track_status"}
            ),
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = hass.data[DOMAIN][entry.entry_id]
    registry["live_state"].set_state(True, "replay")
    try:
        yield entry, registry
    finally:
        if entry.state is ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)


def _state(hass, entry, key):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{key}"
    )
    state = hass.states.get(entity_id)
    assert state is not None
    return state


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["event"])
async def test_recorded_suspension_survives_track_changes_and_snapshots(
    hass, live_entry, case
):
    entry, registry = live_entry
    bus = registry["live_bus"]
    bus.inject_message("SessionInfo", {"Key": 11404, "Type": "Race", "Name": "Race"})
    expected = "unknown"
    for frame in case["frames"]:
        stream, payload = frame["stream"], frame["payload"]
        if stream == "SessionStatus":
            expected = "suspended" if payload["Status"] == "Aborted" else "live"
        bus.inject_message(stream, payload)
        await hass.async_block_till_done()
        assert _state(hass, entry, "session_status").state == expected, frame
        if expected == "suspended":
            # A reconnect/snapshot must not reinterpret the same Aborted as live
            # after RED has cleared. This repeat is synthetic, not an archive row.
            bus.inject_message(
                "SessionStatus", {"Status": "Aborted", "Started": "Started"}
            )
            await hass.async_block_till_done()
            assert _state(hass, entry, "session_status").state == "suspended"
            assert _state(hass, entry, "current_session").attributes["active"] is False
    assert _state(hass, entry, "session_status").state == "live"
    assert _state(hass, entry, "current_session").attributes["active"] is True


@pytest.mark.parametrize("session_name", ["Qualifying", "Sprint Qualifying"])
async def test_qualifying_suspension_and_planned_breaks_remain_distinct(
    hass, live_entry, session_name
):
    entry, registry = live_entry
    bus = registry["live_bus"]
    bus.inject_message(
        "SessionInfo", {"Key": 11403, "Type": "Qualifying", "Name": session_name}
    )
    for part in (1, 2, 3):
        bus.inject_message(
            "SessionData", {"Series": {str(part): {"QualifyingPart": part}}}
        )
        bus.inject_message("TrackStatus", {"Status": "1", "Message": "AllClear"})
        for status, started, expected in [
            ("Started", "Started", "live"),
            ("Aborted", "Started", "suspended"),
            ("Started", "Started", "live"),
            ("Finished", "Finished", "break" if part < 3 else "finished"),
        ]:
            bus.inject_message("SessionStatus", {"Status": status, "Started": started})
            await hass.async_block_till_done()
            assert _state(hass, entry, "session_status").state == expected
            if part < 3 or status != "Finished":
                assert _state(hass, entry, "current_session").state == session_name
        if part < 3:
            bus.inject_message(
                "SessionStatus", {"Status": "Inactive", "Started": "Finished"}
            )
            await hass.async_block_till_done()
            assert _state(hass, entry, "session_status").state == "break"
    for status, expected in [("Finalised", "finalised"), ("Ends", "ended")]:
        bus.inject_message("SessionStatus", {"Status": status, "Started": "Finished"})
        await hass.async_block_till_done()
        assert _state(hass, entry, "session_status").state == expected


@pytest.mark.parametrize("track_status", [None, "1", "2", "4", "5", "6"])
async def test_aborted_snapshot_without_previous_started_frame(
    hass, live_entry, track_status
):
    """Joining during an interruption does not require a cached RED or start."""
    entry, registry = live_entry
    bus = registry["live_bus"]
    if track_status is not None:
        bus.inject_message("TrackStatus", {"Status": track_status})
    bus.inject_message("SessionStatus", {"Status": "Aborted", "Started": "Started"})
    await hass.async_block_till_done()
    assert _state(hass, entry, "session_status").state == "suspended"


async def test_previous_window_aborted_is_discarded_before_next_session(
    hass, live_entry, monkeypatch
):
    entry, registry = live_entry
    bus = registry["live_bus"]
    live_state = registry["live_state"]
    controller = registry["live_delay_controller"]
    coordinator = registry["session_status_coordinator"]
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
    live_state.set_state(False, "replay-stopped")
    live_state.set_state(True, "live-Race")
    await controller.async_set_delay(30)
    bus.inject_message("SessionStatus", {"Status": "Aborted", "Started": "Started"})
    assert coordinator._delay_queue
    live_state.set_state(False, "finished-Race")
    await hass.async_block_till_done()
    assert _state(hass, entry, "session_status").state == "unavailable"
    assert not coordinator._delay_queue
    live_state.set_state(True, "live-Practice 1")
    bus.inject_message(
        "SessionInfo", {"Key": 11405, "Type": "Practice", "Name": "Practice 1"}
    )
    bus.inject_message("SessionStatus", {"Status": "Inactive", "Started": "Inactive"})
    clock.value += 30
    f1._drain_delayed_ingest_queue(coordinator)
    await hass.async_block_till_done()
    assert _state(hass, entry, "session_status").state == "pre"
    bus.inject_message("SessionStatus", {"Status": "Started", "Started": "Started"})
    clock.value += 30
    f1._drain_delayed_ingest_queue(coordinator)
    await hass.async_block_till_done()
    assert _state(hass, entry, "session_status").state == "live"


@pytest.mark.parametrize("started", [None, "Inactive", "Finished"])
def test_aborted_without_started_session_retains_pre(started):
    """Do not promote an unstarted or old terminal context to a live suspension."""
    assert (
        _map_session_status_payload({"Status": "Aborted", "Started": started}, None)
        == "pre"
    )


@pytest.mark.parametrize("session_name", ["Qualifying", "Sprint Qualifying"])
@pytest.mark.parametrize(
    "now", ["2026-11-07T18:02:23.309Z", "2026-11-07T20:03:17.903Z"]
)
async def test_qualifying_red_flag_retains_session_before_and_after_scheduled_end(
    hass, live_entry, freezer, session_name, now
):
    """Issue 1007: a suspended session remains identifiable until it finishes."""
    freezer.move_to(now)
    entry, registry = live_entry
    bus = registry["live_bus"]
    bus.inject_message(
        "SessionInfo",
        {
            "Key": 11408,
            "Type": "Qualifying",
            "Name": session_name,
            "StartDate": "2026-11-07T15:00:00",
            "EndDate": "2026-11-07T16:00:00",
            "GmtOffset": "-03:00:00",
        },
    )
    bus.inject_message("SessionData", {"Series": {"0": {"QualifyingPart": 2}}})
    bus.inject_message("SessionStatus", {"Status": "Started", "Started": "Started"})
    await hass.async_block_till_done()
    assert _state(hass, entry, "current_session").state == session_name

    bus.inject_message("SessionStatus", {"Status": "Aborted", "Started": "Started"})
    await hass.async_block_till_done()
    assert _state(hass, entry, "session_status").state == "suspended"
    current = _state(hass, entry, "current_session")
    assert current.state == session_name
    assert current.attributes["active"] is False
    assert current.attributes["live_status"] == "Aborted"
    bus.inject_message("TrackStatus", {"Status": "5", "Message": "Red"})
    await hass.async_block_till_done()
    assert _state(hass, entry, "current_session").state == session_name
    assert _state(hass, entry, "track_status").state == "RED"

    # Repeated snapshots and cleared track flags must retain the interruption.
    bus.inject_message("TrackStatus", {"Status": "1", "Message": "AllClear"})
    bus.inject_message("SessionStatus", {"Status": "Aborted", "Started": "Started"})
    await hass.async_block_till_done()
    assert _state(hass, entry, "current_session").state == session_name
    assert _state(hass, entry, "session_status").state == "suspended"

    bus.inject_message("SessionStatus", {"Status": "Started", "Started": "Started"})
    await hass.async_block_till_done()
    assert _state(hass, entry, "current_session").attributes["active"] is True
    bus.inject_message("SessionData", {"Series": {"1": {"QualifyingPart": 3}}})
    for status, phase in [
        ("Finished", "finished"),
        ("Finalised", "finalised"),
        ("Ends", "ended"),
    ]:
        bus.inject_message("SessionStatus", {"Status": status, "Started": "Finished"})
        await hass.async_block_till_done()
        assert _state(hass, entry, "session_status").state == phase
        assert _state(hass, entry, "current_session").state == "unknown"

    registry["live_state"].set_state(False, "finished-Qualifying")
    await hass.async_block_till_done()
    assert _state(hass, entry, "current_session").state in ("unknown", "unavailable")
    registry["live_state"].set_state(True, "live-Practice 1")
    bus.inject_message(
        "SessionInfo",
        {"Key": 11409, "Type": "Practice", "Name": "Practice 1", "Number": 1},
    )
    bus.inject_message("SessionStatus", {"Status": "Inactive", "Started": "Inactive"})
    await hass.async_block_till_done()
    assert _state(hass, entry, "current_session").state == "unknown"
    bus.inject_message("SessionStatus", {"Status": "Started", "Started": "Started"})
    await hass.async_block_till_done()
    assert _state(hass, entry, "current_session").state == "Practice 1"


@pytest.mark.parametrize(
    ("end_date", "gmt_offset"),
    [
        ("2026-11-07T16:00:00", "-03:00:00"),
        ("2026-11-07T22:00:00", "+03:00:00"),
        ("2026-11-07T19:00:00Z", "-03:00:00"),
        ("2026-11-07T16:00:00-03:00", "+03:00:00"),
        ("2026-11-07T19:00:00", None),
        ("2026-11-07T19:00:00", "invalid"),
    ],
)
async def test_current_session_stale_fallback_uses_session_timezone(
    hass, live_entry, freezer, end_date, gmt_offset
):
    """Pre-session metadata expires after its UTC end, not the circuit clock."""
    freezer.move_to("2026-11-07T18:15:00Z")
    entry, registry = live_entry
    bus = registry["live_bus"]
    bus.inject_message(
        "SessionInfo",
        {
            "Key": 11403,
            "Type": "Qualifying",
            "Name": "Qualifying",
            "EndDate": end_date,
            "GmtOffset": gmt_offset,
        },
    )
    bus.inject_message("SessionStatus", {"Status": "Inactive", "Started": "Inactive"})
    await hass.async_block_till_done()
    assert _state(hass, entry, "current_session").state == "Qualifying"
    assert _state(hass, entry, "session_status").state == "pre"

    freezer.move_to("2026-11-07T19:06:00Z")
    bus.inject_message("SessionStatus", {"Status": "Inactive", "Started": "Inactive"})
    await hass.async_block_till_done()
    assert _state(hass, entry, "current_session").state == "unknown"


@pytest.mark.parametrize("end_date", [None, "invalid"])
async def test_current_session_missing_end_waits_for_explicit_terminal_status(
    hass, live_entry, freezer, end_date
):
    """Missing or malformed dates must not invent a terminal session state."""
    freezer.move_to("2026-11-07T20:04:00Z")
    entry, registry = live_entry
    bus = registry["live_bus"]
    bus.inject_message(
        "SessionInfo",
        {
            "Key": 11403,
            "Type": "Qualifying",
            "Name": "Qualifying",
            "EndDate": end_date,
            "GmtOffset": "-03:00:00",
        },
    )
    bus.inject_message("SessionStatus", {"Status": "Inactive", "Started": "Inactive"})
    await hass.async_block_till_done()
    assert _state(hass, entry, "current_session").state == "Qualifying"
    bus.inject_message("SessionStatus", {"Status": "Finalised", "Started": "Finished"})
    await hass.async_block_till_done()
    assert _state(hass, entry, "current_session").state == "unknown"
