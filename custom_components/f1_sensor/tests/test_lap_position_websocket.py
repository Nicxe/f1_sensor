"""Tests for lap position progression WebSocket API."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import lap_position_websocket
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.lap_position_websocket import (
    LAP_POSITION_WS_MARKER,
    LAP_POSITION_WS_SESSION_TYPE,
    _ws_get_lap_position_session,
    async_register_lap_position_websocket,
)


class FakeConnection:
    def __init__(self) -> None:
        self.results: list[tuple[int, Any]] = []
        self.errors: list[tuple[int, str, str]] = []

    def send_result(self, msg_id: int, result: Any | None = None) -> None:
        self.results.append((msg_id, result))

    def send_error(self, msg_id: int, code: str, message: str) -> None:
        self.errors.append((msg_id, code, message))


async def test_lap_position_websocket_returns_selected_session(hass) -> None:
    coordinator = AsyncMock()
    coordinator.async_get_session.return_value = {
        "status": "available",
        "session": {"key": "race:2026:1", "status": "available"},
    }
    hass.data.setdefault(DOMAIN, {})["entry-1"] = {
        "lap_position_progression_coordinator": coordinator
    }
    connection = FakeConnection()

    _ws_get_lap_position_session(
        hass,
        connection,
        {
            "id": 4,
            "type": LAP_POSITION_WS_SESSION_TYPE,
            "entity_id": "sensor.f1_lap_position_progression",
            "session_key": "race:2026:1",
        },
    )
    await hass.async_block_till_done()

    assert connection.errors == []
    assert connection.results == [
        (
            4,
            {
                "status": "available",
                "session": {"key": "race:2026:1", "status": "available"},
            },
        )
    ]
    coordinator.async_get_session.assert_awaited_once_with("race:2026:1")


async def test_lap_position_websocket_errors_without_coordinator(hass) -> None:
    connection = FakeConnection()

    _ws_get_lap_position_session(
        hass,
        connection,
        {
            "id": 5,
            "type": LAP_POSITION_WS_SESSION_TYPE,
            "entity_id": "sensor.missing_lap_position_progression",
            "session_key": "race:2026:1",
        },
    )
    await hass.async_block_till_done()

    assert connection.results == []
    assert connection.errors[0][0] == 5
    assert connection.errors[0][1] == "not_found"


def test_lap_position_websocket_registration_is_idempotent(hass, monkeypatch) -> None:
    registered = []

    def _register(_hass, handler):
        registered.append(handler)

    monkeypatch.setattr(
        "custom_components.f1_sensor.lap_position_websocket.websocket_api.async_register_command",
        _register,
    )

    async_register_lap_position_websocket(hass)
    async_register_lap_position_websocket(hass)

    assert registered == [_ws_get_lap_position_session]
    assert hass.data[DOMAIN][LAP_POSITION_WS_MARKER] is True


def test_lap_position_coordinator_resolves_from_entity_config_entry(
    hass, monkeypatch
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, entry_id="entry-1")
    entry.add_to_hass(hass)
    entity = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, "lap-position", config_entry=entry
    )
    coordinator = object()
    monkeypatch.setattr(
        lap_position_websocket,
        "runtime_from_hass",
        lambda _hass, entry_id: (
            {"lap_position_progression_coordinator": coordinator}
            if entry_id == entry.entry_id
            else None
        ),
    )

    assert (
        lap_position_websocket._resolve_lap_position_coordinator(hass, entity.entity_id)
        is coordinator
    )
