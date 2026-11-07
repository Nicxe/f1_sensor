"""Session rain risk is a retained, session-bound Race Control assessment."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import re
from types import SimpleNamespace

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components import f1_sensor as f1
from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS
from custom_components.f1_sensor.replay_mode import ReplayState
from custom_components.f1_sensor.session_rain_risk import parse_session_rain_risk
from custom_components.f1_sensor.tests.test_replay_seek import _build_index


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("RISK OF RAIN FOR F1 FREE PRACTICE 3 IS 30%", ("practice_3", 30)),
        ("RISK OF RAIN FOR THE F1 RACE IS 0%", ("race", 0)),
        ("risk of rain for F1 sprint qualifying is 100 %", ("sprint_qualifying", 100)),
        ("RISK OF RAIN FOR F1 QUALIFYING IS 42.5%", ("qualifying", 42.5)),
        ("RISK OF RAIN FOR F1 SPRINT IS 60%", ("sprint", 60)),
        ("RISK OF RAIN FOR F1 PRACTICE 1 IS 10%", ("practice_1", 10)),
        ("RISK OF RAIN FOR F1 SPRINT SHOOTOUT IS 20%", ("sprint_qualifying", 20)),
        ("RISK OF RAIN FOR F1 RACE IS 101%", None),
        ("RISK OF RAIN FOR F1 RACE IS -1%", None),
        ("RISK OF RAIN FOR F1 RACE IS nan%", None),
        ("RISK OF RAIN FOR F2 RACE IS 30%", None),
        ("RISK OF RAIN FOR F1 UNKNOWN IS 30%", None),
        ("CAR 30 UNDER INVESTIGATION", None),
        ("RISK OF RAIN FOR F1 RACE IS 30% OTHER TEXT", None),
        (None, None),
    ],
)
def test_parse_session_rain_risk(message, expected):
    assert parse_session_rain_risk(message) == expected


def _info(now, *, key="session-a", name="Practice 3", meeting="meeting-a"):
    start = now + timedelta(minutes=15)
    return {
        "Key": key,
        "Name": name,
        "Type": "Practice" if name.startswith("Practice") else name,
        "StartDate": start.isoformat(),
        "EndDate": (start + timedelta(hours=2)).isoformat(),
        "GmtOffset": "00:00:00",
        "Meeting": {"Key": meeting, "Name": "Test Grand Prix"},
    }


def _message(now, percentage=30, label="FREE PRACTICE 3"):
    return {
        "Messages": {
            "1": {
                "Utc": now.isoformat(),
                "Category": "Other",
                "Message": f"RISK OF RAIN FOR F1 {label} IS {percentage}%",
            }
        }
    }


async def _setup(hass, aioclient_mock, *, cards=False, replay=True, delay=0):
    aioclient_mock.get(
        re.compile(r"https://.*"),
        json={"Meetings": [], "MRData": {"RaceTable": {"Races": []}}},
    )
    options = {
        "operation_mode": "live",
        "enable_race_control": True,
        "live_delay_seconds": delay,
        "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS - {"session_rain_risk"}),
    }
    if cards:
        options["card_data_features"] = ["session_rain_risk"]
        options["exposed_sensor_keys"] = []
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        minor_version=4,
        entry_id="rain-entry",
        data={"sensor_name": "F1", "data_choice_version": 1},
        options=options,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = hass.data[DOMAIN][entry.entry_id]
    registry["live_state"].set_state(True, "replay" if replay else "live-window")
    return entry, registry


@pytest.mark.parametrize("cards", [False, True])
async def test_real_entry_retains_zero_and_clears_on_session_end_and_change(
    hass, enable_custom_integrations, aioclient_mock, cards
):
    entry, registry = await _setup(hass, aioclient_mock, cards=cards)
    bus = registry["live_bus"]
    rain = registry["session_rain_risk_coordinator"]
    now = dt_util.utcnow()
    events = []
    unsub = hass.bus.async_listen(f1._RC_LOG_EVENT, lambda event: events.append(event))
    try:
        # A snapshot may precede SessionInfo. It cannot assign an unverified session.
        bus._dispatch("RaceControlMessages", _message(now))
        await hass.async_block_till_done()
        assert rain.data["percentage"] is None
        bus._dispatch("SessionInfo", _info(now))
        bus._dispatch("SessionStatus", {"Status": "Inactive"})
        await hass.async_block_till_done()
        assert rain.data["percentage"] == 30
        assert rain.data["session_key"] == "session-a"
        bus._dispatch("RaceControlMessages", {"Message": "CLEAR IN TRACK SECTOR 2"})
        bus._dispatch("SessionStatus", {"Status": "Aborted", "Started": "Started"})
        await hass.async_block_till_done()
        assert rain.data["percentage"] == 30
        bus._dispatch("RaceControlMessages", _message(now + timedelta(seconds=1), 0))
        await hass.async_block_till_done()
        assert rain.data["percentage"] == 0
        if cards:
            snapshot = registry["card_data_store"].snapshot("session_rain_risk")
            assert snapshot["payload"]["state"] == 0
        else:
            entity_id = er.async_get(hass).async_get_entity_id(
                "sensor", DOMAIN, f"{entry.entry_id}_session_rain_risk"
            )
            assert hass.states.get(entity_id).state == "0"
            assert hass.states.get(entity_id).attributes["unit_of_measurement"] == "%"
        bus._dispatch("SessionStatus", {"Status": "Finished"})
        await hass.async_block_till_done()
        assert rain.data["percentage"] is None
        bus._dispatch("SessionInfo", _info(now, key="session-b", name="Qualifying"))
        bus._dispatch("SessionStatus", {"Status": "Started"})
        bus._dispatch("RaceControlMessages", _message(now, 99))
        await hass.async_block_till_done()
        assert rain.data["percentage"] is None
        assert rain.data["session_key"] == "session-b"
        assert (
            not events
        )  # A rain-only feature never republishes old Race Control alerts.
    finally:
        unsub()
        if entry.state is ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)


async def test_rain_risk_obeys_delayed_input_rewind_and_spoiler_boundaries(
    hass, enable_custom_integrations, aioclient_mock, monkeypatch
):
    entry, registry = await _setup(hass, aioclient_mock)
    bus = registry["live_bus"]
    rain = registry["session_rain_risk_coordinator"]
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
    try:
        registry["live_state"].set_state(False, "replay-stopped")
        registry["live_state"].set_state(True, "live-window")
        await registry["live_delay_controller"].async_set_delay(30)
        now = dt_util.utcnow()
        bus._dispatch("SessionInfo", _info(now))
        bus._dispatch("SessionStatus", {"Status": "Started"})
        bus._dispatch("RaceControlMessages", _message(now))
        assert rain.data["percentage"] is None
        clock.value += 30
        f1._drain_delayed_ingest_queue(registry["analysis_bus"])
        f1._drain_delayed_ingest_queue(registry["session_info_coordinator"])
        f1._drain_delayed_ingest_queue(registry["session_status_coordinator"])
        await hass.async_block_till_done()
        assert rain.data["percentage"] == 30
        bus._dispatch("SessionStatus", {"Status": "Finished"})
        assert rain.data["percentage"] == 30
        clock.value += 30
        f1._drain_delayed_ingest_queue(registry["session_status_coordinator"])
        await hass.async_block_till_done()
        assert rain.data["percentage"] is None
        rain.reset_for_replay()
        registry["live_state"].set_state(True, "replay")
        bus._dispatch("SessionInfo", _info(now))
        bus._dispatch("SessionStatus", {"Status": "Started"})
        bus._dispatch("RaceControlMessages", _message(now))
        await hass.async_block_till_done()
        assert rain.data["percentage"] == 30
        for reset in registry["replay_reset_callbacks"]:
            reset()
        bus._dispatch("SessionInfo", _info(now))
        bus._dispatch("SessionStatus", {"Status": "Started"})
        bus._dispatch("RaceControlMessages", {"Messages": {}})
        await hass.async_block_till_done()
        assert rain.data["percentage"] is None
        bus._dispatch("RaceControlMessages", _message(now))
        await hass.async_block_till_done()
        assert rain.data["percentage"] == 30
        registry["live_state"].set_state(False, "replay-stopped")
        registry["live_state"].set_state(False, "no-spoiler")
        assert rain.data["percentage"] is None
    finally:
        if entry.state is ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("source", ["own", "legacy"])
@pytest.mark.parametrize("matching", [True, False])
async def test_restart_restores_only_matching_session_without_republishing_events(
    hass, enable_custom_integrations, aioclient_mock, hass_storage, source, matching
):
    now = dt_util.utcnow()
    info = _info(now)
    message = next(iter(_message(now - timedelta(minutes=2))["Messages"].values()))
    if source == "own":
        key = f"{DOMAIN}_rain-entry_session_rain_risk"
        saved = {
            "identity": [
                "meeting-a" if matching else "different-meeting",
                "session-a",
                info["StartDate"],
            ],
            "message": message,
        }
    else:
        key = f"{DOMAIN}_rain-entry_race_control_log_v1"
        saved = {
            "session_key": f"{'meeting-a' if matching else 'different-meeting'}|{info['StartDate']}|Practice 3",
            "items": [message],
        }
    hass_storage[key] = {"version": 1, "minor_version": 1, "key": key, "data": saved}
    entry, registry = await _setup(hass, aioclient_mock, replay=False)
    rain = registry["session_rain_risk_coordinator"]
    events = []
    unsub = hass.bus.async_listen(f1._RC_LOG_EVENT, lambda event: events.append(event))
    try:
        assert rain.data["percentage"] is None
        registry["live_bus"]._dispatch("SessionInfo", info)
        registry["live_bus"]._dispatch("SessionStatus", {"Status": "Inactive"})
        await hass.async_block_till_done()
        assert rain.data["percentage"] == (30 if matching else None)
        assert not events
    finally:
        unsub()
        if entry.state is ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)


async def test_delay_change_restores_same_session_without_new_session_info(
    hass, enable_custom_integrations, aioclient_mock
):
    entry, registry = await _setup(hass, aioclient_mock, replay=False)
    bus = registry["live_bus"]
    rain = registry["session_rain_risk_coordinator"]
    now = dt_util.utcnow()
    try:
        bus._dispatch("SessionInfo", _info(now))
        bus._dispatch("SessionStatus", {"Status": "Inactive"})
        bus._dispatch("RaceControlMessages", _message(now - timedelta(minutes=2)))
        await hass.async_block_till_done()
        assert rain.data["percentage"] == 30
        await registry["live_delay_controller"].async_set_delay(30)
        assert rain.data["percentage"] == 30
        assert rain.data["session_key"] == "session-a"
        await registry["live_delay_controller"].async_set_delay(0)
        assert rain.data["percentage"] == 30
        bus._dispatch("RaceControlMessages", _message(now, 60))
        await hass.async_block_till_done()
        assert rain.data["percentage"] == 60
    finally:
        if entry.state is ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)


async def test_actual_replay_seek_restores_only_rain_messages_already_played(
    hass, enable_custom_integrations, aioclient_mock, tmp_path
):
    entry, registry = await _setup(hass, aioclient_mock)
    controller = registry["replay_controller"]
    rain = registry["session_rain_risk_coordinator"]
    now = dt_util.utcnow()
    initial = {"SessionInfo": _info(now), "SessionStatus": {"Status": "Started"}}
    frames = [
        (0, "SessionInfo", initial["SessionInfo"]),
        (0, "SessionStatus", initial["SessionStatus"]),
        (15_000, "RaceControlMessages", _message(now + timedelta(seconds=15))),
        (90_000, "Heartbeat", {"Utc": (now + timedelta(seconds=90)).isoformat()}),
    ]
    index = _build_index(tmp_path, initial_state=initial, frames=frames)
    controller.session_manager._loaded_index = index
    controller.session_manager._state = ReplayState.READY
    try:
        await controller.async_play()
        await controller.async_pause()
        await asyncio.sleep(0)
        assert rain.data["percentage"] is None
        await controller.async_seek_to_position(20)
        await asyncio.sleep(0)
        assert rain.data["percentage"] == 30
        await controller.async_seek_to_position(5)
        await asyncio.sleep(0)
        assert rain.data["percentage"] is None
        await controller.async_seek_to_position(20)
        await asyncio.sleep(0)
        assert rain.data["percentage"] == 30
    finally:
        await controller.async_stop()
        if entry.state is ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)


async def test_new_session_assessment_can_arrive_before_its_session_info(
    hass, enable_custom_integrations, aioclient_mock
):
    entry, registry = await _setup(hass, aioclient_mock)
    bus = registry["live_bus"]
    rain = registry["session_rain_risk_coordinator"]
    now = dt_util.utcnow()
    try:
        bus._dispatch("SessionInfo", _info(now))
        bus._dispatch("RaceControlMessages", _message(now))
        bus._dispatch("RaceControlMessages", _message(now, 60, "QUALIFYING"))
        await hass.async_block_till_done()
        assert rain.data["percentage"] == 30
        bus._dispatch("SessionInfo", _info(now, key="session-b", name="Qualifying"))
        await hass.async_block_till_done()
        assert rain.data["percentage"] == 60
        assert rain.data["session_key"] == "session-b"
    finally:
        if entry.state is ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)


async def test_finished_session_info_blocks_persisted_assessment_before_status_arrives(
    hass, enable_custom_integrations, aioclient_mock, hass_storage
):
    now = dt_util.utcnow()
    info = _info(now)
    info["SessionStatus"] = "Finished"
    key = f"{DOMAIN}_rain-entry_session_rain_risk"
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {
            "identity": ["meeting-a", "session-a", info["StartDate"]],
            "message": next(
                iter(_message(now - timedelta(minutes=2))["Messages"].values())
            ),
        },
    }
    entry, registry = await _setup(hass, aioclient_mock, replay=False)
    try:
        registry["live_bus"]._dispatch("SessionInfo", info)
        await hass.async_block_till_done()
        assert registry["session_rain_risk_coordinator"].data["percentage"] is None
    finally:
        if entry.state is ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("source", ["own", "legacy"])
@pytest.mark.parametrize("cancel", [None, "session", "spoiler", "spoiler-saving"])
async def test_restored_assessment_waits_for_viewing_time_and_cancels_safely(
    hass,
    enable_custom_integrations,
    aioclient_mock,
    hass_storage,
    freezer,
    monkeypatch,
    source,
    cancel,
):
    now = dt_util.utcnow()
    info = _info(now)
    message = next(iter(_message(now - timedelta(seconds=5))["Messages"].values()))
    if source == "own":
        key = f"{DOMAIN}_rain-entry_session_rain_risk"
        saved = {
            "identity": ["meeting-a", "session-a", info["StartDate"]],
            "message": message,
        }
    else:
        key = f"{DOMAIN}_rain-entry_race_control_log_v1"
        saved = {
            "session_key": f"meeting-a|{info['StartDate']}|Practice 3",
            "items": [message],
        }
    hass_storage[key] = {"version": 1, "minor_version": 1, "key": key, "data": saved}
    entry, registry = await _setup(hass, aioclient_mock, replay=False, delay=30)
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
    rain = registry["session_rain_risk_coordinator"]
    activation = None
    release_save = asyncio.Event()
    try:
        registry["live_bus"]._dispatch("SessionInfo", info)
        clock.value += 30
        f1._drain_delayed_ingest_queue(registry["session_info_coordinator"])
        await hass.async_block_till_done()
        assert rain.data["percentage"] is None
        if cancel == "session":
            registry["live_bus"]._dispatch("SessionInfo", _info(now, key="different"))
            clock.value += 30
            f1._drain_delayed_ingest_queue(registry["session_info_coordinator"])
        elif cancel == "spoiler":
            registry["live_state"].set_state(False, "no-spoiler")
        elif cancel == "spoiler-saving":
            manager = hass.data[DOMAIN]["no_spoiler_manager"]
            saving = asyncio.Event()

            async def delayed_save(_data):
                saving.set()
                await release_save.wait()

            monkeypatch.setattr(manager._store, "async_save", delayed_save)
            activation = asyncio.create_task(manager.async_set_active(True))
            await saving.wait()
            assert manager.is_active
            assert registry["live_state"].is_live
        freezer.tick(timedelta(seconds=26))
        async_fire_time_changed(hass)
        if activation is None:
            await hass.async_block_till_done()
        else:
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        assert rain.data["percentage"] == (30 if cancel is None else None)
    finally:
        release_save.set()
        if activation is not None:
            await activation
        if entry.state is ConfigEntryState.LOADED:
            assert await hass.config_entries.async_unload(entry.entry_id)
