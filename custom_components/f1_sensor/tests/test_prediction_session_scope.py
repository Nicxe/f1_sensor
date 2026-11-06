"""Prediction data must belong to an identified race or sprint."""

from __future__ import annotations

import re
from types import SimpleNamespace

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import f1_sensor as f1
from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS
from custom_components.f1_sensor.tests.test_phase_4_analysis import _Bus

PREDICTION = {
    "Drivers": {"4": {"PredictedPosition": 1, "PredictedPoints": 100}},
    "Teams": {"McLaren": {"PredictedPosition": 1, "PredictedPoints": 200}},
}


@pytest.fixture
async def prediction_entry(hass, enable_custom_integrations, aioclient_mock):
    """Load only the prediction feature with mocked external HTTP."""
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
                SUPPORTED_SENSOR_KEYS - {"championship_prediction"}
            ),
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # The test drives transport/session boundaries explicitly; an empty mocked
    # schedule must not concurrently change the live window during those steps.
    await hass.data[DOMAIN][entry.entry_id]["live_supervisor"].async_close()
    unsubscribe = entry.runtime_data.card_data.subscribe(
        ["championship_prediction_drivers", "championship_prediction_teams"],
        lambda _message: None,
    )
    yield entry
    unsubscribe()
    if entry.state == ConfigEntryState.LOADED:
        await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def prediction_states(hass, entry):
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    return {
        kind: hass.states.get(
            next(
                item.entity_id
                for item in entities
                if item.unique_id.endswith(f"championship_prediction_{kind}")
            )
        )
        for kind in ("drivers", "teams")
    }


@pytest.mark.parametrize("mode", ["auth_live", "replay"])
async def test_prediction_snapshot_reconnect_and_recovery(hass, prediction_entry, mode):
    entry = prediction_entry
    registry = hass.data[DOMAIN][entry.entry_id]
    tracker = registry["live_state"]
    bus = entry.runtime_data.live.bus
    if mode == "auth_live":
        bus._auth_enabled = True
        registry["signalr_stream_capabilities"]["auth_enabled"] = True
    reason = "replay-mode" if mode == "replay" else "test-active"
    tracker.set_state(True, reason)
    # Snapshot order on the wire need not put SessionInfo before prediction.
    bus._process_payload(
        {
            "R": {
                "ChampionshipPrediction": PREDICTION,
                "DriverList": {"4": {"Tla": "NOR"}},
                "SessionInfo": {"Key": 1, "Type": "Race"},
            }
        }
    )
    await hass.async_block_till_done()
    assert prediction_states(hass, entry)["drivers"].state == "NOR"
    assert prediction_states(hass, entry)["teams"].state == "McLaren"
    for kind in ("drivers", "teams"):
        payload = entry.runtime_data.card_data.snapshot(
            f"championship_prediction_{kind}"
        )["payload"]
        assert payload["attributes"]["prediction_status"] == "ready"

    tracker.set_state(False, "replay-stopped" if mode == "replay" else "reconnecting")
    tracker.set_state(True, reason)
    bus._dispatch("ChampionshipPrediction", PREDICTION)
    await hass.async_block_till_done()
    for state in prediction_states(hass, entry).values():
        assert state.state == "unknown"
        assert state.attributes["prediction_status"] == "waiting_for_session"
    for kind in ("drivers", "teams"):
        payload = entry.runtime_data.card_data.snapshot(
            f"championship_prediction_{kind}"
        )["payload"]
        assert payload["state"] is None
        assert payload["attributes"]["prediction_status"] == "waiting_for_session"
    bus._dispatch("SessionInfo", {"Key": 2, "Type": "Sprint"})
    await hass.async_block_till_done()
    for state in prediction_states(hass, entry).values():
        assert state.state == "unknown"
        assert state.attributes["prediction_status"] == "waiting_for_prediction"
    for kind in ("drivers", "teams"):
        payload = entry.runtime_data.card_data.snapshot(
            f"championship_prediction_{kind}"
        )["payload"]
        assert payload["state"] is None
        assert payload["attributes"]["prediction_status"] == "waiting_for_prediction"
    bus._dispatch("DriverList", {"4": {"Tla": "NOR"}})
    bus._dispatch("ChampionshipPrediction", PREDICTION)
    await hass.async_block_till_done()
    assert prediction_states(hass, entry)["drivers"].state == "NOR"
    assert prediction_states(hass, entry)["teams"].state == "McLaren"


async def test_prediction_no_spoiler_blocks_new_publication_and_recovers(
    hass, prediction_entry
):
    entry = prediction_entry
    registry = hass.data[DOMAIN][entry.entry_id]
    bus = entry.runtime_data.live.bus
    bus._auth_enabled = True
    registry["signalr_stream_capabilities"]["auth_enabled"] = True
    tracker = registry["live_state"]
    tracker.set_state(True, "test-active")
    bus._dispatch("SessionInfo", {"Key": 1, "Type": "Race"})
    bus._dispatch("DriverList", {"4": {"Tla": "NOR"}})
    bus._dispatch("ChampionshipPrediction", PREDICTION)
    await hass.async_block_till_done()
    before = prediction_states(hass, entry)
    manager = hass.data[DOMAIN]["no_spoiler_manager"]
    await manager.async_set_active(True)
    tracker.set_state(False, "no-spoiler")
    bus._dispatch(
        "ChampionshipPrediction",
        {
            "Drivers": {"4": {"PredictedPoints": 999}},
            "Teams": {"McLaren": {"PredictedPoints": 999}},
        },
    )
    await hass.async_block_till_done()
    for kind, state in prediction_states(hass, entry).items():
        assert state.attributes[kind] == before[kind].attributes[kind]
        direct = entry.runtime_data.card_data.snapshot(
            f"championship_prediction_{kind}"
        )
        assert direct["status"] == "blocked"
        assert direct["payload"] is None
    await manager.async_set_active(False)
    tracker.set_state(True, "test-active")
    bus._dispatch("SessionInfo", {"Key": 2, "Type": "Qualifying"})
    bus._dispatch("ChampionshipPrediction", PREDICTION)
    await hass.async_block_till_done()
    assert prediction_states(hass, entry)["drivers"].state == "unknown"
    bus._dispatch("SessionInfo", {"Key": 3, "Type": "Race"})
    bus._dispatch("DriverList", {"4": {"Tla": "NOR"}})
    bus._dispatch("ChampionshipPrediction", PREDICTION)
    await hass.async_block_till_done()
    assert prediction_states(hass, entry)["drivers"].state == "NOR"
    assert (
        entry.runtime_data.card_data.snapshot("championship_prediction_drivers")[
            "payload"
        ]["state"]
        == "NOR"
    )


async def test_prediction_delay_and_reset_guard_sensor_and_direct_data(
    hass, prediction_entry, monkeypatch
):
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
    entry = prediction_entry
    registry = hass.data[DOMAIN][entry.entry_id]
    coordinator = registry["championship_prediction_coordinator"]
    bus = entry.runtime_data.live.bus
    bus._auth_enabled = True
    registry["signalr_stream_capabilities"]["auth_enabled"] = True
    registry["live_state"].set_state(True, "test-active")
    coordinator.set_delay(30)
    bus._dispatch("SessionInfo", {"Key": 1, "Type": "Race"})
    bus._dispatch("DriverList", {"4": {"Tla": "NOR"}})
    bus._dispatch("ChampionshipPrediction", PREDICTION)
    await hass.async_block_till_done()
    assert prediction_states(hass, entry)["drivers"].state != "NOR"
    clock.value = 129.9
    f1._drain_delayed_ingest_queue(coordinator)
    assert coordinator.data["prediction_status"] == "waiting_for_session"
    clock.value = 130
    f1._drain_delayed_ingest_queue(coordinator)
    await hass.async_block_till_done()
    assert prediction_states(hass, entry)["drivers"].state == "NOR"
    assert (
        entry.runtime_data.card_data.snapshot("championship_prediction_drivers")[
            "payload"
        ]["state"]
        == "NOR"
    )
    bus._dispatch("SessionInfo", {"Key": 2, "Type": "Qualifying"})
    bus._dispatch("ChampionshipPrediction", PREDICTION)
    await hass.async_block_till_done()
    assert prediction_states(hass, entry)["drivers"].attributes["session_key"] == "1"
    clock.value = 160
    f1._drain_delayed_ingest_queue(coordinator)
    await hass.async_block_till_done()
    for kind, state in prediction_states(hass, entry).items():
        assert state.state == "unknown"
        assert state.attributes["prediction_status"] == "not_applicable"
        assert not state.attributes[kind]
        payload = entry.runtime_data.card_data.snapshot(
            f"championship_prediction_{kind}"
        )["payload"]
        assert not payload["attributes"][kind]
        assert payload["attributes"]["prediction_status"] == "not_applicable"
    # Reset/rewind retires callbacks already queued for the previous context.
    bus._dispatch("SessionInfo", {"Key": 3, "Type": "Race"})
    bus._dispatch("ChampionshipPrediction", PREDICTION)
    f1._reset_replay_sensitive_coordinator_state(coordinator)
    clock.value = 190
    f1._drain_delayed_ingest_queue(coordinator)
    await hass.async_block_till_done()
    assert coordinator.data["prediction_status"] == "waiting_for_session"
    assert not coordinator.data["drivers"]


@pytest.mark.parametrize(
    ("kind", "name", "expected"),
    [
        ("Race", "Race", "NOR"),
        ("Race", "Sprint", "NOR"),
        ("Sprint", "Sprint", "NOR"),
        ("Practice", "Practice 1", None),
        ("Qualifying", "Qualifying", None),
        ("Qualifying", "Sprint Qualifying", None),
        ("Qualifying", "Sprint Shootout", None),
        ("Testing", "Testing", None),
        (None, None, None),
    ],
)
async def test_prediction_session_guard_reaches_sensor_and_direct_data(
    hass, enable_custom_integrations, aioclient_mock, kind, name, expected
):
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
                SUPPORTED_SENSOR_KEYS - {"championship_prediction"}
            ),
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    try:
        registry = hass.data[DOMAIN][entry.entry_id]
        registry["live_state"].set_state(True, "replay-mode")
        bus = entry.runtime_data.live.bus
        bus._dispatch("SessionInfo", {"Key": 1, "Type": kind, "Name": name})
        bus._dispatch("DriverList", {"4": {"Tla": "NOR"}})
        bus._dispatch("ChampionshipPrediction", PREDICTION)
        await hass.async_block_till_done()
        direct = entry.runtime_data.card_data.snapshot(
            "championship_prediction_drivers"
        )
        payload = direct.get("payload") or {}
        assert payload.get("state") == expected
        entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        entity = next(
            item
            for item in entities
            if item.unique_id.endswith("championship_prediction_drivers")
        )
        state = hass.states.get(entity.entity_id)
        assert state is not None
        assert state.state == (expected or "unknown")
        if expected is None:
            assert not state.attributes.get("drivers")
            assert not payload.get("attributes", {}).get("drivers")
    finally:
        if entry.state == ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def test_prediction_unknown_session_drops_payload_and_waits_for_fresh_data(hass):
    bus = _Bus()
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    coordinator = f1.ChampionshipPredictionCoordinator(
        hass, SimpleNamespace(data={}), bus=bus, config_entry=entry
    )
    await coordinator.async_config_entry_first_refresh()
    try:
        bus.emit("ChampionshipPrediction", PREDICTION)
        assert coordinator.data["drivers"] == {}
        bus.emit("SessionInfo", {"Key": "A", "Type": "Race"})
        assert coordinator.data["drivers"] == {}
        assert coordinator.data["prediction_status"] == "waiting_for_prediction"
        bus.emit("ChampionshipPrediction", PREDICTION)
        assert coordinator.data["drivers"]["4"]["PredictedPoints"] == 100
        bus.emit("SessionInfo", {"ArchiveStatus": {"Status": "Complete"}})
        assert coordinator.data["drivers"]["4"]["PredictedPoints"] == 100
        bus.emit("SessionInfo", {"Key": "B", "Type": "Qualifying"})
        bus.emit("ChampionshipPrediction", PREDICTION)
        assert coordinator.data["drivers"] == {}
        assert coordinator.data["prediction_status"] == "not_applicable"
        bus.emit("SessionInfo", {"Key": "C"})
        bus.emit("ChampionshipPrediction", PREDICTION)
        assert coordinator.data["prediction_status"] == "waiting_for_session"
        bus.emit("SessionInfo", {"Type": "Sprint"})
        assert coordinator.data["drivers"] == {}
        bus.emit("ChampionshipPrediction", PREDICTION)
        assert coordinator.data["prediction_status"] == "ready"
    finally:
        await coordinator.async_close()


async def test_prediction_session_metadata_uses_the_same_delayed_order(
    hass, monkeypatch
):
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
    bus = _Bus()
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    coordinator = f1.ChampionshipPredictionCoordinator(
        hass, SimpleNamespace(data={}), bus=bus, delay_seconds=30, config_entry=entry
    )
    await coordinator.async_config_entry_first_refresh()
    try:
        bus.emit("SessionInfo", {"Key": "A", "Type": "Race"})
        bus.emit("ChampionshipPrediction", PREDICTION)
        assert coordinator.data["drivers"] == {}
        clock.value = 130.0
        f1._drain_delayed_ingest_queue(coordinator)
        assert coordinator.data["drivers"]["4"]["PredictedPoints"] == 100
        bus.emit("SessionInfo", {"Key": "B", "Type": "Qualifying"})
        bus.emit("ChampionshipPrediction", PREDICTION)
        assert coordinator.data["drivers"]
        clock.value = 160.0
        f1._drain_delayed_ingest_queue(coordinator)
        assert coordinator.data["drivers"] == {}
        assert coordinator.data["prediction_status"] == "not_applicable"
    finally:
        await coordinator.async_close()
    assert not any(bus.callbacks.values())
