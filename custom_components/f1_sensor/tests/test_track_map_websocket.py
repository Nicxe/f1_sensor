from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.feature_plan import TRACK_MAP_STREAMS
from custom_components.f1_sensor.providers import ProviderRegistry
from custom_components.f1_sensor.runtime import (
    CacheRuntime,
    CapabilityState,
    F1RuntimeData,
    HistoryRuntime,
    LiveRuntime,
    ProviderRuntime,
    StaticRuntime,
)
from custom_components.f1_sensor.track_map import (
    TRACK_MAP_STATUS_NO_POSITION_DATA,
    TRACK_MAP_STATUS_NO_SESSION,
    TrackMapPosition,
    TrackMapRuntimeData,
    TrackMapStore,
)
from custom_components.f1_sensor.track_map_websocket import (
    TRACK_MAP_API_STATUS_NO_GEOMETRY,
    TRACK_MAP_API_STATUS_NOT_LOADED,
    TRACK_MAP_PROTOCOL_V2,
    TRACK_MAP_WS_ERROR_NOT_LOADED,
    TRACK_MAP_WS_GET_TYPE,
    TRACK_MAP_WS_MARKER,
    TRACK_MAP_WS_RESYNC_TYPE,
    TRACK_MAP_WS_SUBSCRIBE_TYPE,
    _track_map_payload,
    _ws_get_track_map_snapshot,
    _ws_resync_track_map_snapshot,
    _ws_subscribe_track_map_snapshot,
    async_register_track_map_websocket,
)

BASE_TIME = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)


class FakeConnection:
    def __init__(self) -> None:
        self.results: list[tuple[int, Any]] = []
        self.events: list[tuple[int, Any]] = []
        self.errors: list[tuple[int, str, str]] = []
        self.subscriptions: dict[int, Any] = {}

    def send_result(self, msg_id: int, result: Any | None = None) -> None:
        self.results.append((msg_id, result))

    def send_event(self, msg_id: int, event: Any | None = None) -> None:
        self.events.append((msg_id, event))

    def send_error(self, msg_id: int, code: str, message: str) -> None:
        self.errors.append((msg_id, code, message))


def _store(hass, entry_id: str = "entry-1") -> TrackMapStore:
    store = TrackMapStore(entry_id, stale_after=timedelta(days=3650))
    hass.data.setdefault(DOMAIN, {})[entry_id] = {"track_map_store": store}
    return store


def _session_payload() -> dict[str, Any]:
    return {
        "Key": "101",
        "Name": "Race",
        "Type": "Race",
        "Meeting": {"Circuit": {"Key": "999", "ShortName": "Test"}},
    }


def _position(racing_number: str = "1") -> TrackMapPosition:
    return TrackMapPosition(
        racing_number=racing_number,
        timestamp=BASE_TIME,
        x=100,
        y=200,
        z=0,
        status="OnTrack",
    )


def test_track_map_payload_reports_not_loaded_without_store(hass) -> None:
    payload = _track_map_payload(hass)

    assert payload == {
        "entry_id": None,
        "status": TRACK_MAP_API_STATUS_NOT_LOADED,
        "snapshot": None,
    }


@pytest.mark.asyncio
async def test_track_map_get_websocket_returns_snapshot_status(hass) -> None:
    store = _store(hass)
    connection = FakeConnection()

    _ws_get_track_map_snapshot(
        hass,
        connection,
        {"id": 1, "type": TRACK_MAP_WS_GET_TYPE, "entry_id": "entry-1"},
    )
    await hass.async_block_till_done()

    assert connection.results[0][1]["status"] == TRACK_MAP_STATUS_NO_SESSION

    store.update_session_info(_session_payload())
    store.update_positions([_position()])
    _ws_get_track_map_snapshot(
        hass,
        connection,
        {"id": 2, "type": TRACK_MAP_WS_GET_TYPE, "entry_id": "entry-1"},
    )
    await hass.async_block_till_done()

    payload = connection.results[1][1]
    assert payload["entry_id"] == "entry-1"
    assert payload["status"] == TRACK_MAP_API_STATUS_NO_GEOMETRY
    assert payload["snapshot"]["drivers"][0]["racing_number"] == "1"
    assert connection.errors == []


def test_track_map_subscribe_sends_initial_and_update_events(hass) -> None:
    store = _store(hass)
    connection = FakeConnection()

    _ws_subscribe_track_map_snapshot(
        hass,
        connection,
        {
            "id": 7,
            "type": TRACK_MAP_WS_SUBSCRIBE_TYPE,
            "entry_id": "entry-1",
            "throttle_ms": 0,
        },
    )

    assert connection.results == [(7, None)]
    assert connection.events[0][0] == 7
    assert connection.events[0][1]["status"] == TRACK_MAP_STATUS_NO_SESSION
    assert 7 in connection.subscriptions

    store.update_session_info(_session_payload())
    assert connection.events[-1][1]["status"] == TRACK_MAP_STATUS_NO_POSITION_DATA

    store.update_positions([_position("16")])
    assert connection.events[-1][1]["status"] == TRACK_MAP_API_STATUS_NO_GEOMETRY
    assert connection.events[-1][1]["snapshot"]["drivers"][0]["racing_number"] == "16"

    connection.subscriptions.pop(7)()
    store.update_positions([_position("44")])
    assert connection.events[-1][1]["snapshot"]["drivers"][0]["racing_number"] == "16"


def test_track_map_websocket_exposes_live_position_source_and_z(hass) -> None:
    store = _store(hass)
    store.update_session_info(_session_payload())
    store.update_positions([_position("16")], source="live")

    payload = _track_map_payload(hass, "entry-1")

    assert payload["snapshot"]["source"] == "live"
    assert payload["snapshot"]["drivers"][0]["racing_number"] == "16"
    assert payload["snapshot"]["drivers"][0]["z"] == 0


def test_track_map_subscribe_returns_retryable_error_when_store_is_missing(
    hass,
) -> None:
    connection = FakeConnection()

    _ws_subscribe_track_map_snapshot(
        hass,
        connection,
        {
            "id": 8,
            "type": TRACK_MAP_WS_SUBSCRIBE_TYPE,
            "entry_id": "missing",
            "throttle_ms": 0,
        },
    )

    assert connection.results == []
    assert connection.errors == [
        (
            8,
            TRACK_MAP_WS_ERROR_NOT_LOADED,
            "Track map data is not loaded yet; retry the subscription",
        )
    ]
    assert connection.events == []
    assert connection.subscriptions == {}


def test_track_map_websocket_registration_is_idempotent(hass, monkeypatch) -> None:
    registered = []

    def _register(_hass, handler):
        registered.append(handler)

    monkeypatch.setattr(
        "custom_components.f1_sensor.track_map_websocket.websocket_api.async_register_command",
        _register,
    )

    async_register_track_map_websocket(hass)
    async_register_track_map_websocket(hass)

    assert len(registered) == 3
    assert hass.data[DOMAIN][TRACK_MAP_WS_MARKER] is True


def test_track_map_v2_sends_snapshot_then_small_sequenced_delta(hass) -> None:
    store = _store(hass)
    store.update_session_info(_session_payload())
    store.update_positions([_position(str(number)) for number in range(1, 21)])
    connection = FakeConnection()

    _ws_subscribe_track_map_snapshot(
        hass,
        connection,
        {
            "id": 20,
            "type": TRACK_MAP_WS_SUBSCRIBE_TYPE,
            "entry_id": "entry-1",
            "protocol_version": TRACK_MAP_PROTOCOL_V2,
            "throttle_ms": 0,
        },
    )

    initial = connection.events[-1][1]
    assert initial["type"] == "snapshot"
    assert initial["sequence"] == 0
    store.update_positions(
        [
            TrackMapPosition(
                racing_number="1",
                timestamp=BASE_TIME + timedelta(seconds=1),
                x=101,
                y=201,
                z=0,
                status="OnTrack",
            )
        ]
    )
    delta = connection.events[-1][1]

    assert delta["type"] == "delta"
    assert delta["base_sequence"] == 0
    assert delta["sequence"] == 1
    assert set(delta["changes"]) == {"1"}
    assert len(json.dumps(delta)) < len(json.dumps(initial)) * 0.3
    connection.subscriptions.pop(20)()


def test_track_map_v1_and_v2_clients_share_one_store_broadcast(hass) -> None:
    store = _store(hass)
    first = FakeConnection()
    second = FakeConnection()

    _ws_subscribe_track_map_snapshot(
        hass,
        first,
        {
            "id": 30,
            "type": TRACK_MAP_WS_SUBSCRIBE_TYPE,
            "entry_id": "entry-1",
            "protocol_version": 1,
            "throttle_ms": 0,
        },
    )
    _ws_subscribe_track_map_snapshot(
        hass,
        second,
        {
            "id": 31,
            "type": TRACK_MAP_WS_SUBSCRIBE_TYPE,
            "entry_id": "entry-1",
            "protocol_version": 2,
            "throttle_ms": 0,
        },
    )

    assert len(store._listeners) == 1
    store.update_session_info(_session_payload())
    assert first.events[-1][1]["snapshot"]["session"]["session_key"] == "101"
    assert second.events[-1][1]["type"] == "delta"
    first.subscriptions.pop(30)()
    assert len(store._listeners) == 1
    second.subscriptions.pop(31)()
    assert len(store._listeners) == 0


@pytest.mark.asyncio
async def test_track_map_v2_resync_returns_latest_full_snapshot(hass) -> None:
    store = _store(hass)
    connection = FakeConnection()
    _ws_subscribe_track_map_snapshot(
        hass,
        connection,
        {
            "id": 40,
            "type": TRACK_MAP_WS_SUBSCRIBE_TYPE,
            "entry_id": "entry-1",
            "protocol_version": 2,
            "throttle_ms": 0,
        },
    )
    store.update_session_info(_session_payload())

    _ws_resync_track_map_snapshot(
        hass,
        connection,
        {
            "id": 41,
            "type": TRACK_MAP_WS_RESYNC_TYPE,
            "entry_id": "entry-1",
            "protocol_version": 2,
        },
    )
    await hass.async_block_till_done()

    resync = connection.results[-1]
    assert resync[0] == 41
    assert resync[1]["type"] == "snapshot"
    assert resync[1]["sequence"] == 1
    connection.subscriptions.pop(40)()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("availability_is_live", "expected_closed"),
    [(False, True), (True, False)],
)
async def test_track_map_subscription_adds_and_removes_transient_stream_demand(
    hass,
    availability_is_live: bool,
    expected_closed: bool,
) -> None:
    class DemandBus:
        def __init__(self) -> None:
            self.requested_streams = frozenset({"Heartbeat"})
            self.started = False
            self.closed = False

        @property
        def active_streams(self) -> frozenset[str]:
            return self.requested_streams

        async def async_update_streams(self, streams) -> None:
            self.requested_streams = frozenset(streams)

        async def start(self) -> None:
            self.started = True
            self.closed = False

        async def async_close(self) -> None:
            self.started = False
            self.closed = True

    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    entry.add_to_hass(hass)
    store = TrackMapStore(entry.entry_id)
    bus = DemandBus()
    legacy_capabilities = {
        "requested_streams": frozenset({"Heartbeat"}),
        "active_live_streams": frozenset({"Heartbeat"}),
        "stream_reasons": {"Heartbeat": ("live_transport_health",)},
    }
    entry.runtime_data = F1RuntimeData(
        static=StaticRuntime(),
        live=LiveRuntime(
            bus=bus,
            availability=SimpleNamespace(is_live=availability_is_live),
        ),
        replay=None,
        track_map=TrackMapRuntimeData(store),
        cache=CacheRuntime(object(), {}, {}, {}),
        providers=ProviderRuntime(ProviderRegistry()),
        history=HistoryRuntime(service=object()),
        capabilities=CapabilityState(
            frozenset(),
            frozenset({"Heartbeat"}),
            frozenset({"Heartbeat"}),
            {"Heartbeat": ("live_transport_health",)},
        ),
        legacy={"signalr_stream_capabilities": legacy_capabilities},
    )
    connection = FakeConnection()

    _ws_subscribe_track_map_snapshot(
        hass,
        connection,
        {
            "id": 50,
            "type": TRACK_MAP_WS_SUBSCRIBE_TYPE,
            "entry_id": entry.entry_id,
            "protocol_version": 2,
            "throttle_ms": 0,
        },
    )
    await hass.async_block_till_done()

    assert bus.started is True
    assert bus.requested_streams == TRACK_MAP_STREAMS | {"Heartbeat"}
    assert entry.runtime_data.capabilities.stream_reasons["Position.z"] == (
        "track_map_card",
    )

    connection.subscriptions.pop(50)()
    await hass.async_block_till_done()

    assert bus.requested_streams == frozenset({"Heartbeat"})
    assert bus.closed is expected_closed
    assert "Position.z" not in entry.runtime_data.capabilities.stream_reasons
