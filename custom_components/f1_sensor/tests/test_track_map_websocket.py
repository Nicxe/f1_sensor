from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import track_map_websocket
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
    TrackGeometry,
    TrackMapBounds,
    TrackMapPosition,
    TrackMapRuntimeData,
    TrackMapStore,
)
from custom_components.f1_sensor.track_map_annotation_contract import (
    load_annotation_catalog,
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
    _merge_v2_deltas,
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


def _singapore_session(*, year: int = 2025, key: str = "9896") -> dict[str, Any]:
    return {
        "Key": key,
        "Path": f"{year}/{year}-10-05_Singapore_Grand_Prix/{year}-10-05_Race/",
        "StartDate": f"{year}-10-05T20:00:00",
        "Meeting": {"Circuit": {"Key": "61", "ShortName": "Singapore"}},
    }


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


@pytest.mark.asyncio
async def test_v2_annotations_follow_exact_map_generation_and_resync(hass) -> None:
    store = _store(hass)
    records = load_annotation_catalog()
    assert all(record["rights_status"] == "cleared" for record in records)
    store.annotation_records = tuple(records)
    store.update_session_info(_singapore_session())
    connection = FakeConnection()
    _ws_subscribe_track_map_snapshot(
        hass,
        connection,
        {
            "id": 61,
            "type": TRACK_MAP_WS_SUBSCRIBE_TYPE,
            "entry_id": store.entry_id,
            "protocol_version": 2,
            "throttle_ms": 0,
        },
    )

    initial = connection.events[-1][1]
    annotations = initial["snapshot"]["annotations"]
    assert annotations["schema_version"] == 1
    assert annotations["binding"]["source"] == "live"
    assert annotations["binding"]["season"] == 2025
    assert (
        annotations["binding"]["geometry_fingerprint"]
        == initial["snapshot"]["track"]["geometry_fingerprint"]
    )
    assert {layer["layer"] for layer in annotations["layers"]} == {
        "corners",
        "start_finish",
        "sectors",
        "speed_traps",
        "detection_zones",
    }
    corner_layer = next(
        layer for layer in annotations["layers"] if layer["layer"] == "corners"
    )
    assert len(corner_layer["items"]) == 19
    assert corner_layer["columns"] == [
        "id",
        "kind",
        "anchor",
        "label",
        "label_offset",
    ]
    raw_payload = {**initial, "snapshot": store.snapshot()}
    added_bytes = len(json.dumps(initial, separators=(",", ":")).encode()) - len(
        json.dumps(raw_payload, separators=(",", ":")).encode()
    )
    assert added_bytes <= 4096

    store.update_positions([_position()], source="live")
    delta = connection.events[-1][1]
    assert delta["type"] == "delta"
    assert "annotations" not in delta["patch"]
    assert "geometry_fingerprint" not in delta["patch"].get("track", {})

    _ws_resync_track_map_snapshot(
        hass,
        connection,
        {
            "id": 62,
            "type": TRACK_MAP_WS_RESYNC_TYPE,
            "entry_id": store.entry_id,
            "protocol_version": 2,
        },
    )
    await hass.async_block_till_done()
    resync = connection.results[-1][1]
    assert resync["snapshot"]["annotations"] == annotations

    store.update_replay_state("seeking", session_key="9896", session_year=2025)
    assert connection.events[-1][1]["patch"]["annotations"] is None
    store.reset_for_replay()
    assert connection.events[-1][1]["patch"]["track"] is None
    store.update_session_info(_singapore_session())
    store.update_replay_state("ready", session_key="9896", session_year=2025)
    replay_annotations = connection.events[-1][1]["patch"]["annotations"]
    assert replay_annotations["binding"]["source"] == "replay"
    assert (
        replay_annotations["binding"]["session_generation"]
        > annotations["binding"]["session_generation"]
    )
    store.update_replay_state("playing", session_key="9896", session_year=2025)
    assert "annotations" not in connection.events[-1][1]["patch"]

    store.update_session_info(_singapore_session(key="other"))
    assert connection.events[-1][1]["patch"]["annotations"] is None
    store.update_replay_state("ready", session_key="other", session_year=2026)
    assert "annotations" not in connection.events[-1][1]["patch"]

    connection.subscriptions.pop(61)()
    assert len(store._listeners) == 0


def test_v2_annotations_remain_gated_by_pending_rights_status(hass) -> None:
    store = _store(hass)
    records = deepcopy(load_annotation_catalog())
    for record in records:
        record["rights_status"] = "pending"
    store.annotation_records = tuple(records)
    store.update_session_info(_singapore_session())
    connection = FakeConnection()
    _ws_subscribe_track_map_snapshot(
        hass,
        connection,
        {
            "id": 63,
            "type": TRACK_MAP_WS_SUBSCRIBE_TYPE,
            "entry_id": store.entry_id,
            "protocol_version": 2,
            "throttle_ms": 0,
        },
    )
    assert connection.events[-1][1]["snapshot"]["annotations"] is None
    connection.subscriptions.pop(63)()


def test_v2_annotations_clear_on_geometry_rebuild_and_reconnect(hass) -> None:
    store = _store(hass)
    records = load_annotation_catalog()
    store.annotation_records = tuple(records)
    store.update_session_info(_singapore_session())
    first = FakeConnection()
    second = FakeConnection()
    for connection, msg_id in ((first, 70), (second, 71)):
        _ws_subscribe_track_map_snapshot(
            hass,
            connection,
            {
                "id": msg_id,
                "type": TRACK_MAP_WS_SUBSCRIBE_TYPE,
                "entry_id": store.entry_id,
                "protocol_version": 2,
                "throttle_ms": 0,
            },
        )
    first_annotations = first.events[-1][1]["snapshot"]["annotations"]
    assert second.events[-1][1]["snapshot"]["annotations"] == first_annotations
    assert len(store._listeners) == 1

    geometry = store.geometry
    assert geometry is not None
    changed_points = (*geometry.points[:-1], (9999, 9999))
    store.set_geometry(
        TrackGeometry(
            points=changed_points,
            bounds=geometry.bounds,
            source="replay_position_z",
            circuit_key=geometry.circuit_key,
            rotation=geometry.rotation,
        )
    )
    for connection in (first, second):
        patch = connection.events[-1][1]["patch"]
        assert patch["annotations"] is None
        assert (
            patch["track"]["geometry_fingerprint"]
            != first_annotations["binding"]["geometry_fingerprint"]
        )

    store.set_geometry(geometry)
    replacement = first.events[-1][1]["patch"]["annotations"]
    assert (
        replacement["binding"]["session_generation"]
        > first_annotations["binding"]["session_generation"]
    )
    first.subscriptions.pop(70)()
    assert len(store._listeners) == 1
    second.subscriptions.pop(71)()
    assert len(store._listeners) == 0

    reconnected = FakeConnection()
    _ws_subscribe_track_map_snapshot(
        hass,
        reconnected,
        {
            "id": 72,
            "type": TRACK_MAP_WS_SUBSCRIBE_TYPE,
            "entry_id": store.entry_id,
            "protocol_version": 2,
            "throttle_ms": 0,
        },
    )
    after_reconnect = reconnected.events[-1][1]["snapshot"]["annotations"]
    assert (
        after_reconnect["binding"]["session_generation"]
        > replacement["binding"]["session_generation"]
    )
    reconnected.subscriptions.pop(72)()


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
    ("availability_is_live", "expected_started", "expected_closed"),
    [(False, False, True), (True, True, False)],
)
async def test_track_map_subscription_adds_and_removes_transient_stream_demand(
    hass,
    availability_is_live: bool,
    expected_started: bool,
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

    assert bus.started is expected_started
    assert bus.requested_streams == TRACK_MAP_STREAMS | {"Heartbeat"}
    assert entry.runtime_data.capabilities.stream_reasons["Position.z"] == (
        "track_map_card",
    )

    connection.subscriptions.pop(50)()
    await hass.async_block_till_done()

    assert bus.requested_streams == frozenset({"Heartbeat"})
    assert bus.closed is expected_closed
    assert "Position.z" not in entry.runtime_data.capabilities.stream_reasons


async def test_track_map_resync_missing_and_hubless_snapshot(hass) -> None:
    connection = FakeConnection()
    _ws_resync_track_map_snapshot(
        hass,
        connection,
        {"id": 60, "entry_id": "missing", "protocol_version": 2},
    )
    await hass.async_block_till_done()
    assert connection.errors[0][1] == TRACK_MAP_WS_ERROR_NOT_LOADED

    store = _store(hass, "entry-hubless")
    store.update_session_info(_session_payload())
    _ws_resync_track_map_snapshot(
        hass,
        connection,
        {"id": 61, "entry_id": "entry-hubless", "protocol_version": 2},
    )
    await hass.async_block_till_done()
    assert connection.results[-1][1]["type"] == "snapshot"
    assert connection.results[-1][1]["sequence"] == 0


def test_track_map_throttle_geometry_and_delta_coalescing(hass) -> None:
    store = _store(hass, "entry-throttle")
    connection = FakeConnection()
    _ws_subscribe_track_map_snapshot(
        hass,
        connection,
        {
            "id": 62,
            "entry_id": "entry-throttle",
            "protocol_version": 2,
            "throttle_ms": 1000,
        },
    )
    store.update_session_info(_session_payload())
    hub = next(
        hub
        for linked, hub in list(track_map_websocket._TRACK_MAP_HUBS.items())
        if linked is store
    )
    before = hub._geometry_revision
    store.set_geometry(
        TrackGeometry(
            points=((0, 0), (1, 1)),
            bounds=TrackMapBounds(0, 1, 0, 1),
            source="test",
        )
    )
    assert hub._geometry_revision == before + 1
    store.update_positions([_position("4")])
    subscription = next(iter(hub._subscribers))
    assert subscription._pending_handle is not None
    subscription.unsubscribe()
    assert subscription._pending_handle is None

    merged = _merge_v2_deltas(
        {
            "type": "delta",
            "base_sequence": 1,
            "changes": {"4": {"x": 1}, "81": {"x": 2}},
            "removed": ["16"],
            "patch": {"status": "old"},
        },
        {
            "type": "delta",
            "base_sequence": 2,
            "changes": {"16": {"x": 3}},
            "removed": ["4"],
            "patch": {"status": "new"},
        },
    )
    assert merged["base_sequence"] == 1
    assert set(merged["changes"]) == {"16", "81"}
    assert merged["removed"] == ["4"]
