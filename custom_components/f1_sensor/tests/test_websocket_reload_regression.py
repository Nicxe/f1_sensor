"""Reload regressions with real stores and surviving dashboard connections."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.f1_sensor.analysis import Phase4AnalysisStore
from custom_components.f1_sensor.analysis_websocket import (
    _ANALYSIS_HUBS,
    _analysis_hub,
    _AnalysisSubscription,
)
from custom_components.f1_sensor.history import LapAnalysisStore
from custom_components.f1_sensor.track_map import TrackMapStore
from custom_components.f1_sensor.track_map_websocket import (
    _TRACK_MAP_HUBS,
    _track_map_hub,
    _TrackMapSnapshotSubscription,
)


class Connection:
    def __init__(self):
        self.events = []
        self.subscriptions = {}

    def send_event(self, msg_id, payload):
        self.events.append((msg_id, payload))


class Bus:
    def __init__(self):
        self.callbacks = {}

    def subscribe(self, stream, callback):
        self.callbacks.setdefault(stream, []).append(callback)
        return lambda: self.callbacks[stream].remove(callback)

    def emit(self, stream, payload):
        for callback in tuple(self.callbacks.get(stream, ())):
            callback(payload)


@pytest.mark.asyncio
async def test_analysis_close_terminates_pending_subscriptions(hass):
    bus = Bus()
    laps = LapAnalysisStore(bus, source_provider=lambda: "f1_live")
    store = Phase4AnalysisStore(bus, laps, source_provider=lambda: "f1_live")
    runtime = SimpleNamespace(
        analysis=SimpleNamespace(store=store),
        live=None,
        replay=None,
        capabilities=SimpleNamespace(requested_streams=[], active_streams=[]),
    )
    connection = Connection()
    hub = _analysis_hub(hass, runtime, store)
    subscription = _AnalysisSubscription(hass, connection, 1, hub, 5)
    connection.subscriptions[1] = subscription.unsubscribe
    subscription.async_send_initial()
    bus.emit("SessionStatus", {"Status": "Started"})
    assert subscription._pending_handle is not None
    try:
        await store.async_close()
        assert connection.events[-1][1]["status"] == "closed"
        assert connection.events[-1][1]["retryable"] is True
        assert hub.closed
        assert store not in _ANALYSIS_HUBS
        assert not store._listeners
        assert subscription._pending_handle is None
        assert subscription._pending_payload is None
        assert not connection.subscriptions
        before = len(connection.events)
        subscription.unsubscribe()
        bus.emit("SessionStatus", {"Status": "Finished"})
        assert len(connection.events) == before
    finally:
        subscription.unsubscribe()
        await store.async_close()
        await laps.async_close()


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", [1, 2])
async def test_track_map_close_terminates_pending_subscriptions(hass, protocol):
    store = TrackMapStore("entry")
    connection = Connection()
    hub = _track_map_hub(hass, store)
    subscription = _TrackMapSnapshotSubscription(hass, connection, 1, hub, protocol, 5)
    connection.subscriptions[1] = subscription.unsubscribe
    subscription.async_send_initial()
    store.update_session_info({"Key": "A", "Name": "Race"})
    assert subscription._pending_handle is not None
    try:
        await store.async_close()
        assert connection.events[-1][1]["status"] == "closed"
        assert connection.events[-1][1]["retryable"] is True
        assert connection.events[-1][1]["snapshot"]["status"] == "closed"
        assert hub.closed
        assert store not in _TRACK_MAP_HUBS
        assert not store._listeners
        assert subscription._pending_handle is None
        assert not connection.subscriptions
        subscription.unsubscribe()
    finally:
        subscription.unsubscribe()
        await store.async_close()


@pytest.mark.asyncio
async def test_fifty_real_entry_reloads_with_surviving_websocket(
    hass, enable_custom_integrations, aioclient_mock, hass_ws_client
):
    """Real HA platforms, bus and stores survive reload on one socket."""
    import asyncio
    import re

    from homeassistant.config_entries import ConfigEntryState
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS

    aioclient_mock.get(
        re.compile(r"https://.*"),
        json={"Meetings": [], "MRData": {"RaceTable": {"Races": []}}},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        data={"sensor_name": "F1"},
        options={
            "operation_mode": "live",
            "enable_race_control": True,
            "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS - {"track_status"}),
        },
    )
    entry.add_to_hass(hass)
    next_id = 0
    retained_unsubscribes = []
    baseline_analysis = set(_ANALYSIS_HUBS)
    baseline_map = set(_TRACK_MAP_HUBS)

    def owned_tasks():
        return {
            task
            for task in asyncio.all_tasks()
            if not task.done()
            and "custom_components/f1_sensor/"
            in getattr(getattr(task.get_coro(), "cr_code", None), "co_filename", "")
        }

    baseline_tasks = owned_tasks()
    # Register HTTP views before the minimum HA test server freezes its router.
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)
    try:
        for cycle in range(50):
            previous_unsubscribes = retained_unsubscribes
            retained_unsubscribes = []
            if cycle:
                assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            assert entry.state == ConfigEntryState.LOADED
            runtime = entry.runtime_data
            registry = hass.data[DOMAIN][entry.entry_id]
            bus = runtime.live.bus
            # There is no real network in this test; feed the actual LiveBus.
            bus._dispatch(
                "SessionInfo", {"Key": str(cycle), "Name": "Race", "Type": "Race"}
            )
            bus._dispatch("SessionStatus", {"Status": "Started"})
            bus._dispatch("TrackStatus", {"Status": "2", "Message": "Yellow"})
            await hass.async_block_till_done()
            active = []
            for _card in range(3):
                for command in ("analysis", "track_map"):
                    next_id += 1
                    msg_id = next_id
                    active.append(msg_id)
                    await client.send_json(
                        {
                            "id": msg_id,
                            "type": f"f1_sensor/{command}/subscribe",
                            "entry_id": entry.entry_id,
                            "protocol_version": 1 if command == "analysis" else 2,
                            "throttle_ms": 5000,
                        }
                    )
                    ack = await client.receive_json()
                    assert ack["id"] == msg_id and ack["success"]
                    initial = await client.receive_json()
                    assert initial["id"] == msg_id and initial["type"] == "event"
                    payload = initial["event"]
                    if command == "analysis":
                        assert payload["session_id"] == f"{cycle}:Race"
                    else:
                        assert payload["type"] == "snapshot"
            await hass.async_block_till_done()
            # Keep a callable from the retiring generation to exercise late unsubscribe.
            demand = runtime.capabilities.requested_streams
            for unsubscribe in previous_unsubscribes:
                unsubscribe()
            await hass.async_block_till_done()
            assert runtime.capabilities.requested_streams == demand
            hubs = (
                _ANALYSIS_HUBS[runtime.analysis.store],
                _TRACK_MAP_HUBS[runtime.track_map_store],
            )
            retained_unsubscribes.extend(
                next(iter(hub._subscribers)).unsubscribe for hub in hubs
            )
            bus._dispatch("SessionStatus", {"Status": "Finished"})
            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()
            terminals = [await client.receive_json() for _ in active]
            assert {event["id"] for event in terminals} == set(active)
            assert all(
                event["event"]["status"] == "closed" and event["event"]["retryable"]
                for event in terminals
            )
            assert set(_ANALYSIS_HUBS) == baseline_analysis
            assert set(_TRACK_MAP_HUBS) == baseline_map
            assert not runtime.analysis.store._listeners
            assert not runtime.track_map_store._listeners
            assert not registry["analysis_bus"]._handlers
            assert not bus._subs
            assert not any(hub._demand_tasks for hub in hubs)
            assert owned_tasks() <= baseline_tasks
    finally:
        if entry.state == ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
        await client.close()
