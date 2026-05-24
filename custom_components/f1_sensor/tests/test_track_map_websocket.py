from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.track_map import (
    TRACK_MAP_STATUS_NO_POSITION_DATA,
    TRACK_MAP_STATUS_NO_SESSION,
    TrackMapPosition,
    TrackMapStore,
)
from custom_components.f1_sensor.track_map_websocket import (
    TRACK_MAP_API_STATUS_NO_GEOMETRY,
    TRACK_MAP_API_STATUS_NOT_LOADED,
    TRACK_MAP_WS_GET_TYPE,
    TRACK_MAP_WS_MARKER,
    TRACK_MAP_WS_SUBSCRIBE_TYPE,
    _track_map_payload,
    _ws_get_track_map_snapshot,
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
    store = TrackMapStore(entry_id, stale_after=timedelta(days=30))
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


def test_track_map_subscribe_returns_not_loaded_when_store_is_missing(hass) -> None:
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

    assert connection.results == [
        (
            8,
            {
                "entry_id": "missing",
                "status": TRACK_MAP_API_STATUS_NOT_LOADED,
                "snapshot": None,
            },
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

    assert len(registered) == 2
    assert hass.data[DOMAIN][TRACK_MAP_WS_MARKER] is True
