"""Tests for the bounded shared minisector WebSocket transport."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Any

from custom_components.f1_sensor import minisector_websocket
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.minisector_websocket import (
    _MINISECTOR_HUBS,
    MINISECTOR_PROTOCOL_V1,
    MINISECTOR_WS_MARKER,
    MINISECTOR_WS_SUBSCRIBE_TYPE,
    _active_session_key,
    _driver_changes,
    _numeric_sort_key,
    _transport_drivers,
    _ws_subscribe_minisectors,
    async_register_minisector_websocket,
)
from custom_components.f1_sensor.minisectors import MiniSectorStateStore

FIXTURES = Path(__file__).parent / "fixtures" / "minisectors"
LAP_TRANSITION = json.loads((FIXTURES / "lap_transition.json").read_text())


class FakeConnection:
    """Minimal Home Assistant WebSocket connection test double."""

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


def _payload(statuses: dict[str, dict[int, dict[int, int]]]) -> dict[str, Any]:
    return {
        "Lines": {
            driver: {
                "Sectors": {
                    str(sector): {
                        "Segments": {
                            str(segment): {"Status": status}
                            for segment, status in segments.items()
                        }
                    }
                    for sector, segments in sectors.items()
                }
            }
            for driver, sectors in statuses.items()
        }
    }


def _register_store(
    hass,
    entry_id: str = "entry-1",
    *,
    session_key: str = "77",
    source: str = "live",
) -> MiniSectorStateStore:
    store = MiniSectorStateStore(entry_id=entry_id)
    if source == "replay":
        store.set_source("replay")
    entry_data: dict[str, Any] = {
        "drivers_coordinator": SimpleNamespace(minisector_store=store),
        "session_info_coordinator": SimpleNamespace(data={"Key": session_key}),
    }
    if source == "replay":
        entry_data["replay_controller"] = SimpleNamespace(
            snapshot={"selected_session_key": session_key}
        )
    hass.data.setdefault(DOMAIN, {})[entry_id] = entry_data
    return store


def _subscribe(
    hass,
    connection: FakeConnection,
    *,
    msg_id: int = 1,
    entry_id: str = "entry-1",
    source: str = "live",
    session_key: str = "77",
) -> None:
    _ws_subscribe_minisectors(
        hass,
        connection,
        {
            "id": msg_id,
            "type": MINISECTOR_WS_SUBSCRIBE_TYPE,
            "protocol_version": MINISECTOR_PROTOCOL_V1,
            "entry_id": entry_id,
            "source": source,
            "session_key": session_key,
        },
    )


def test_minisector_websocket_registration_is_idempotent(hass, monkeypatch) -> None:
    registered = []
    monkeypatch.setattr(
        minisector_websocket.websocket_api,
        "async_register_command",
        lambda _hass, handler: registered.append(handler),
    )

    async_register_minisector_websocket(hass)
    async_register_minisector_websocket(hass)

    assert registered == [_ws_subscribe_minisectors]
    assert hass.data[DOMAIN][MINISECTOR_WS_MARKER] is True


def test_subscription_requires_loaded_entry_and_exact_session(hass) -> None:
    missing = FakeConnection()
    _subscribe(hass, missing, entry_id="missing")
    assert missing.errors[0][1] == "not_loaded"
    assert missing.events == []

    _register_store(hass)
    wrong_session = FakeConnection()
    _subscribe(hass, wrong_session, session_key="88")
    event = wrong_session.events[-1][1]
    assert event["type"] == "unavailable"
    assert event["reason"] == "session_unavailable"
    assert "drivers" not in event

    wrong_source = FakeConnection()
    _subscribe(hass, wrong_source, source="replay")
    event = wrong_source.events[-1][1]
    assert event["type"] == "unavailable"
    assert event["reason"] == "source_inactive"
    assert "drivers" not in event

    wrong_session.subscriptions.pop(1)()
    wrong_source.subscriptions.pop(1)()


def test_subscription_rejects_blank_context_after_store_resolution(hass) -> None:
    """Whitespace-only context is rejected even when an entry happens to exist."""
    _register_store(hass, entry_id="")
    connection = FakeConnection()

    _ws_subscribe_minisectors(
        hass,
        connection,
        {
            "id": 1,
            "type": MINISECTOR_WS_SUBSCRIBE_TYPE,
            "protocol_version": MINISECTOR_PROTOCOL_V1,
            "entry_id": " ",
            "source": "live",
            "session_key": "77",
        },
    )

    assert connection.errors == [
        (1, "invalid_format", "entry_id and session_key must be non-empty strings")
    ]


def test_transport_helpers_handle_incomplete_context_and_scoped_reset(hass) -> None:
    """Transport only serializes valid statuses and identifies scoped removals."""
    assert _active_session_key(hass, "missing", "live") is None
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "replay_controller": SimpleNamespace(
            snapshot=None,
            _get_snapshot=lambda: {"selected_session_key": 44},
        ),
        "session_info_coordinator": SimpleNamespace(data={"Key": 9}),
    }
    assert _active_session_key(hass, "entry", "replay") == "44"
    hass.data[DOMAIN]["entry"]["replay_controller"] = SimpleNamespace(
        snapshot=None,
        _get_snapshot=lambda: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )
    assert _active_session_key(hass, "entry", "replay") == "9"

    drivers = _transport_drivers(
        {
            "1": {"sectors": {"0": {"segments": {"0": {"raw_status": 2051}}}}},
            "bad": object(),
            "2": {"sectors": {"0": {"segments": {"1": {}}}}},
        }
    )
    assert drivers == {
        "1": {"sectors": {"0": {"segments": {"0": 2051}}}},
        "2": {"sectors": {}},
    }
    assert _transport_drivers(None) == {}

    changed, removed = _driver_changes(
        {"2": {"sectors": {"0": {"segments": {"0": 2048, "1": 2049}}}}},
        {
            "1": {"sectors": {}},
            "2": {"sectors": {"0": {"segments": {"0": 2051}}}},
        },
    )
    assert changed["1"] == {"sectors": {}}
    assert changed["2"] == {"sectors": {"0": {"segments": {"0": 2051}}}}
    assert removed == ["2"]
    assert sorted(["driver", "10", "2"], key=_numeric_sort_key) == ["2", "10", "driver"]


def test_hub_and_subscription_release_pending_and_blocked_transport(hass) -> None:
    """Pending, closed and rate-limited transport paths do not leak a subscriber."""
    store = _register_store(hass)
    hub = minisector_websocket._minisector_hub(hass, store)
    store.merge_timing_data(_payload({"1": {0: {0: 2048}}}))
    assert (
        hub.current_snapshot()["drivers"]["1"]["sectors"]["0"]["segments"]["0"][
            "raw_status"
        ]
        == 2048
    )

    connection = FakeConnection()
    subscription = minisector_websocket._MiniSectorSubscription(
        hass,
        connection,
        1,
        hub,
        entry_id="entry-1",
        source="live",
        session_key="77",
    )
    subscription._traffic_blocked_until = hass.loop.time() + 1
    subscription.receive(store.snapshot())
    assert connection.events == []
    subscription._traffic_blocked_until = 0
    subscription._traffic.append((hass.loop.time() - 11, 1))
    assert subscription._send_bounded(subscription._event_base("delta", "0", 1)) is True
    connection.subscriptions[1] = subscription.unsubscribe
    subscription.terminate("source_inactive")
    assert 1 not in connection.subscriptions
    subscription.terminate("source_inactive")
    hub.close()
    hub._flush()


def test_live_availability_and_global_spoiler_state_fail_closed(hass) -> None:
    store = _register_store(hass)
    store.merge_timing_data(_payload({"1": {0: {0: 2051}}}))
    hass.data[DOMAIN]["entry-1"]["live_state"] = SimpleNamespace(is_live=False)
    inactive = FakeConnection()

    _subscribe(hass, inactive)
    assert inactive.events[-1][1]["reason"] == "source_inactive"
    assert "drivers" not in inactive.events[-1][1]
    inactive.subscriptions.pop(1)()

    hass.data[DOMAIN]["entry-1"]["live_state"].is_live = True
    hass.data[DOMAIN]["no_spoiler_manager"] = SimpleNamespace(is_active=True)
    protected = FakeConnection()
    _subscribe(hass, protected)
    assert protected.events[-1][1]["reason"] == "spoiler_protected"
    assert "drivers" not in protected.events[-1][1]
    protected.subscriptions.pop(1)()


def test_mid_session_subscription_and_reconnect_start_with_current_snapshot(
    hass,
) -> None:
    store = _register_store(hass)
    store.merge_timing_data(_payload({"1": {0: {0: 2048, 2: 2051}}}))
    first = FakeConnection()

    _subscribe(hass, first)
    snapshot = first.events[-1][1]

    assert snapshot["type"] == "snapshot"
    assert snapshot["protocol_version"] == 1
    assert snapshot["sequence"] == 0
    assert snapshot["source"] == "live"
    assert snapshot["session_key"] == "77"
    assert snapshot["drivers"]["1"]["sectors"]["0"]["segments"] == {
        "0": 2048,
        "2": 2051,
    }

    first.subscriptions.pop(1)()
    assert store.listener_count == 0
    reconnect = FakeConnection()
    _subscribe(hass, reconnect, msg_id=2)
    assert reconnect.events[-1][1]["sequence"] == 0
    assert reconnect.events[-1][1]["drivers"] == snapshot["drivers"]
    reconnect.subscriptions.pop(2)()


async def test_dense_frames_are_coalesced_with_atomic_final_handoff(hass) -> None:
    store = _register_store(hass)
    store.merge_timing_data(_payload({"31": {0: {3: 2051}}, "87": {0: {3: 2049}}}))
    connection = FakeConnection()
    _subscribe(hass, connection)

    for status in (2048, 2064, 2048, 2049):
        store.merge_timing_data(_payload({"31": {0: {3: status}}}))
    store.merge_timing_data(_payload({"31": {0: {3: 2049}}, "87": {0: {3: 2051}}}))
    assert len(connection.events) == 1

    await asyncio.sleep(0.27)
    delta = connection.events[-1][1]
    assert delta["type"] == "delta"
    assert delta["sequence"] == 1
    assert delta["drivers"]["31"]["sectors"]["0"]["segments"] == {"3": 2049}
    assert delta["drivers"]["87"]["sectors"]["0"]["segments"] == {"3": 2051}
    assert len(connection.events) == 2
    connection.subscriptions.pop(1)()


async def test_transport_sends_at_most_four_deltas_per_second(hass) -> None:
    store = _register_store(hass)
    store.merge_timing_data(_payload({"1": {0: {0: 2048}}}))
    connection = FakeConnection()
    _subscribe(hass, connection)

    for index in range(20):
        store.merge_timing_data(_payload({"1": {0: {0: 2048 if index % 2 else 2049}}}))
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.27)

    assert len(connection.events) - 1 <= 4
    assert connection.events[-1][1]["drivers"]["1"]["sectors"]["0"]["segments"] == {
        "0": 2048
    }
    connection.subscriptions.pop(1)()


def test_many_clients_share_one_store_listener_and_release_last_consumer(hass) -> None:
    store = _register_store(hass)
    connections = [FakeConnection() for _ in range(10)]

    for msg_id, connection in enumerate(connections, start=1):
        _subscribe(hass, connection, msg_id=msg_id)

    assert store.listener_count == 1
    assert len(_MINISECTOR_HUBS) == 1
    for msg_id, connection in enumerate(connections[:-1], start=1):
        connection.subscriptions.pop(msg_id)()
    assert store.listener_count == 1
    connections[-1].subscriptions.pop(10)()
    assert store.listener_count == 0
    assert _MINISECTOR_HUBS == {}


async def test_lap_counter_keeps_strip_until_atomic_segment_reset(hass) -> None:
    store = _register_store(hass)
    store.merge_timing_data({"Lines": {"10": LAP_TRANSITION["before"]}})
    connection = FakeConnection()
    _subscribe(hass, connection)

    store.merge_timing_data(LAP_TRANSITION["lap_counter_frame"]["payload"])
    await asyncio.sleep(0.27)
    assert len(connection.events) == 1

    store.merge_timing_data(LAP_TRANSITION["segment_reset_frame"]["payload"])
    await asyncio.sleep(0.27)
    delta = connection.events[-1][1]

    assert delta["type"] == "delta"
    assert delta["sequence"] == 1
    assert delta["drivers"]["10"]["sectors"]["0"]["segments"] == {
        "0": 2051,
        "1": 0,
        "2": 0,
        "3": 0,
        "4": 0,
        "5": 0,
    }
    assert delta["drivers"]["10"]["sectors"]["2"]["segments"]["8"] == 0
    connection.subscriptions.pop(1)()


def test_store_close_terminates_clients_and_releases_hub(hass) -> None:
    store = _register_store(hass)
    connection = FakeConnection()
    _subscribe(hass, connection)

    store.close()

    assert connection.events[-1][1]["type"] == "unavailable"
    assert connection.events[-1][1]["reason"] == "source_inactive"
    assert connection.subscriptions == {}
    assert store.listener_count == 0
    assert _MINISECTOR_HUBS == {}


async def test_generation_reset_cannot_retain_old_colours(hass) -> None:
    store = _register_store(hass)
    store.merge_timing_data(_payload({"44": {0: {0: 2051}}}))
    connection = FakeConnection()
    _subscribe(hass, connection)

    store.reset("session_change")
    store.merge_timing_data(_payload({"44": {1: {0: 2048}}}))
    await asyncio.sleep(0.27)
    snapshot = connection.events[-1][1]

    assert snapshot["type"] == "snapshot"
    assert snapshot["sequence"] == 0
    assert snapshot["generation"] != connection.events[0][1]["generation"]
    assert "0" not in snapshot["drivers"]["44"]["sectors"]
    assert snapshot["drivers"]["44"]["sectors"]["1"]["segments"] == {"0": 2048}
    connection.subscriptions.pop(1)()


async def test_spoiler_unavailable_then_fresh_recovery_snapshot(hass) -> None:
    store = _register_store(hass)
    store.merge_timing_data(_payload({"4": {0: {0: 2051}}}))
    connection = FakeConnection()
    _subscribe(hass, connection)

    store.reset("spoiler_protected")
    await asyncio.sleep(0.27)
    blocked = connection.events[-1][1]
    assert blocked["type"] == "unavailable"
    assert blocked["reason"] == "spoiler_protected"
    assert "drivers" not in blocked

    store.merge_timing_data(_payload({"4": {0: {1: 2048}}}))
    await asyncio.sleep(0.27)
    recovered = connection.events[-1][1]
    assert recovered["type"] == "snapshot"
    assert recovered["sequence"] == blocked["sequence"] + 1
    assert recovered["drivers"]["4"]["sectors"]["0"]["segments"] == {"1": 2048}
    connection.subscriptions.pop(1)()


def test_entry_and_source_contexts_do_not_share_state(hass) -> None:
    live = _register_store(hass, "live-entry", session_key="10")
    replay = _register_store(hass, "replay-entry", session_key="20", source="replay")
    live.merge_timing_data(_payload({"1": {0: {0: 2048}}}))
    replay.merge_timing_data(_payload({"2": {0: {0: 2051}}}))
    live_connection = FakeConnection()
    replay_connection = FakeConnection()

    _subscribe(
        hass,
        live_connection,
        entry_id="live-entry",
        source="live",
        session_key="10",
    )
    _subscribe(
        hass,
        replay_connection,
        entry_id="replay-entry",
        source="replay",
        session_key="20",
    )

    assert set(live_connection.events[-1][1]["drivers"]) == {"1"}
    assert set(replay_connection.events[-1][1]["drivers"]) == {"2"}
    live_connection.subscriptions.pop(1)()
    replay_connection.subscriptions.pop(1)()


def test_oversized_snapshot_fails_closed_without_segment_state(
    hass, monkeypatch
) -> None:
    store = _register_store(hass)
    store.merge_timing_data(
        _payload(
            {
                str(driver): {
                    sector: dict.fromkeys(range(12), 2051) for sector in range(3)
                }
                for driver in range(1, 9)
            }
        )
    )
    monkeypatch.setattr(minisector_websocket, "MAX_MINISECTOR_EVENT_BYTES", 512)
    connection = FakeConnection()

    _subscribe(hass, connection)

    event = connection.events[-1][1]
    assert event["type"] == "unavailable"
    assert event["reason"] == "bounds_exceeded"
    assert "drivers" not in event
    connection.subscriptions.pop(1)()


def test_integer_snapshot_fits_the_declared_store_bounds(hass) -> None:
    entry_id = "0123456789abcdef0123456789abcdef"
    session_key = "1234567890abcdef"
    store = _register_store(hass, entry_id, session_key=session_key)
    store.merge_timing_data(
        _payload(
            {
                str(driver): {
                    sector: dict.fromkeys(range(32), 2051) for sector in range(3)
                }
                for driver in range(1, 33)
            }
        )
    )
    connection = FakeConnection()

    _subscribe(
        hass,
        connection,
        entry_id=entry_id,
        session_key=session_key,
    )

    event = connection.events[-1][1]
    assert event["type"] == "snapshot"
    assert len(json.dumps(event, separators=(",", ":")).encode()) <= 32 * 1024
    connection.subscriptions.pop(1)()


def test_transport_profile_stays_bounded_and_beats_full_sensor_payload(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(minisector_websocket, "MINISECTOR_THROTTLE_SECONDS", 0)
    store = _register_store(hass)
    counts = (6, 7, 9)
    store.merge_timing_data(
        _payload(
            {
                str(driver): {
                    sector: dict.fromkeys(range(count), 2048)
                    for sector, count in enumerate(counts)
                }
                for driver in range(1, 23)
            }
        )
    )
    connections = [FakeConnection() for _ in range(10)]
    for msg_id, connection in enumerate(connections, start=1):
        _subscribe(hass, connection, msg_id=msg_id)

    initial_bytes = len(json.dumps(connections[0].events[0][1]).encode())
    dispatch_ms: list[float] = []
    sensor_bytes = 0
    for frame in range(40):
        changes = {
            str(driver): {
                frame % 3: {frame % counts[frame % 3]: 2051 if frame % 5 == 0 else 2049}
            }
            for driver in range(1, 6)
        }
        started = perf_counter()
        store.merge_timing_data(_payload(changes))
        dispatch_ms.append((perf_counter() - started) * 1000)
        sensor_payload = {
            "state": "active",
            "attributes": {
                "drivers": minisector_websocket._transport_drivers(
                    store.snapshot()["drivers"]
                )
            },
        }
        sensor_bytes += len(json.dumps(sensor_payload).encode())

    update_sizes = [
        len(json.dumps(event).encode()) for _, event in connections[0].events[1:]
    ]
    websocket_bytes = sum(update_sizes)
    p95_index = max(0, int(len(dispatch_ms) * 0.95) - 1)
    metrics = {
        "clients": len(connections),
        "drivers": 22,
        "source_frames": 40,
        "ui_deltas_per_second": 4,
        "initial_snapshot_bytes": initial_bytes,
        "max_event_bytes": max(update_sizes),
        "websocket_bytes_per_client_10s": websocket_bytes,
        "websocket_bytes_per_client_second": round(websocket_bytes / 10, 1),
        "full_sensor_payload_bytes_10s": sensor_bytes,
        "dispatch_p95_ms": round(sorted(dispatch_ms)[p95_index], 3),
    }
    print(f"MINISECTOR_PROFILE={json.dumps(metrics, sort_keys=True)}")

    assert initial_bytes <= 32 * 1024
    assert max(update_sizes) <= 32 * 1024
    assert websocket_bytes <= 16 * 1024 * 10
    assert websocket_bytes < sensor_bytes
    assert metrics["dispatch_p95_ms"] <= 25
    assert store.listener_count == 1

    for msg_id, connection in enumerate(connections, start=1):
        connection.subscriptions.pop(msg_id)()
    assert store.listener_count == 0
