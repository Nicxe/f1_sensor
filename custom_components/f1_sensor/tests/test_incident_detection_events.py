from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import (
    _INCIDENT_EVENT,
    _INCIDENT_STREAMS,
    IncidentCoordinator,
)
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker


class FakeIncidentLiveBus:
    def __init__(
        self, last_payload: dict[str, Any] | None = None, *, auth_header: str = ""
    ) -> None:
        self.last_payload = last_payload or {}
        self.auth_header = auth_header
        self.subscribers: dict[str, list] = {}
        self.unsubscribe_count = 0

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_header)

    def subscribe(self, stream: str, callback):
        self.subscribers.setdefault(stream, []).append(callback)
        if stream in self.last_payload:
            callback(self.last_payload[stream])

        def _unsub() -> None:
            callbacks = self.subscribers.get(stream, [])
            if callback in callbacks:
                callbacks.remove(callback)
                self.unsubscribe_count += 1

        return _unsub

    def emit(self, stream: str, payload: Any) -> None:
        for callback in list(self.subscribers.get(stream, [])):
            callback(payload)


def _entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, entry_id="incident-entry")
    entry.add_to_hass(hass)
    return entry


async def _coordinator(
    hass,
    bus: FakeIncidentLiveBus,
    *,
    delay_seconds: int = 0,
    live_state: LiveAvailabilityTracker | None = None,
) -> IncidentCoordinator:
    if live_state is None:
        live_state = LiveAvailabilityTracker()
        live_state.set_state(True, "live")
    coordinator = IncidentCoordinator(
        hass,
        session_coord=object(),
        delay_seconds=delay_seconds,
        bus=bus,
        config_entry=_entry(hass),
        live_state=live_state,
    )
    await coordinator.async_refresh()
    for stream in _INCIDENT_STREAMS:
        coordinator._subscribe_stream(bus, stream)  # noqa: SLF001
    return coordinator


def _driver_list() -> dict[str, Any]:
    return {
        "10": {
            "Tla": "GAS",
            "FullName": "Pierre Gasly",
            "TeamName": "Alpine",
        }
    }


def _session_info() -> dict[str, Any]:
    return {
        "Meeting": {"Name": "Miami Grand Prix"},
        "Name": "Race",
        "Type": "Race",
        "Path": "2026-miami-race",
        "StartDate": "2026-05-03T20:00:00Z",
    }


def _timing(stopped: bool) -> dict[str, Any]:
    return {
        "Lines": {
            "10": {
                "Stopped": stopped,
                "InPit": False,
                "PitOut": False,
                "Retired": False,
            }
        }
    }


def _race_control() -> dict[str, Any]:
    return {
        "Messages": [
            {
                "Category": "Flag",
                "Flag": "DOUBLE YELLOW",
                "Message": "DOUBLE YELLOW FOR CAR 10",
            }
        ]
    }


async def _prime_context(hass, bus: FakeIncidentLiveBus) -> None:
    bus.emit("SessionInfo", _session_info())
    bus.emit("DriverList", _driver_list())
    bus.emit("TimingData", _timing(False))
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_startup_cache_does_not_fire_incident(hass) -> None:
    bus = FakeIncidentLiveBus(
        {
            "TimingData": _timing(True),
            "RaceControlMessages": _race_control(),
        }
    )
    events = []
    unsub = hass.bus.async_listen(_INCIDENT_EVENT, lambda event: events.append(event))

    coordinator = await _coordinator(hass, bus)
    try:
        await hass.async_block_till_done()
        assert events == []
        assert coordinator.data["active_count"] == 0

        bus.emit("TimingData", _timing(True))
        await hass.async_block_till_done()

        assert events == []
        assert coordinator.data["active_count"] == 0
    finally:
        unsub()
        await coordinator.async_close()


@pytest.mark.asyncio
async def test_incident_events_confirm_update_dedupe_and_clear(hass) -> None:
    bus = FakeIncidentLiveBus()
    events = []
    unsub = hass.bus.async_listen(
        _INCIDENT_EVENT, lambda event: events.append(event.data)
    )
    coordinator = await _coordinator(hass, bus)

    try:
        await _prime_context(hass, bus)

        bus.emit("TimingData", _timing(True))
        await hass.async_block_till_done()

        assert [event["phase"] for event in events] == ["confirmed"]
        confirmed = events[-1]
        assert confirmed["entry_id"] == "incident-entry"
        assert confirmed["confidence"] == "medium"
        assert confirmed["driver"] == {
            "racing_number": "10",
            "tla": "GAS",
            "name": "Pierre Gasly",
            "team": "Alpine",
        }

        bus.emit("TimingData", _timing(True))
        await hass.async_block_till_done()
        assert [event["phase"] for event in events] == ["confirmed"]

        bus.emit("RaceControlMessages", _race_control())
        await hass.async_block_till_done()

        assert [event["phase"] for event in events] == ["confirmed", "updated"]
        updated = events[-1]
        assert updated["incident_id"] == confirmed["incident_id"]
        assert updated["confidence"] == "high"
        assert updated["race_control"]["message"] == "DOUBLE YELLOW FOR CAR 10"

        bus.emit("RaceControlMessages", _race_control())
        await hass.async_block_till_done()
        assert [event["phase"] for event in events] == ["confirmed", "updated"]

        bus.emit("TimingData", _timing(False))
        await hass.async_block_till_done()

        assert [event["phase"] for event in events] == [
            "confirmed",
            "updated",
            "cleared",
        ]
        assert events[-1]["incident_id"] == confirmed["incident_id"]
        assert coordinator.data["active_count"] == 0
        assert coordinator.data["latest_phase"] == "cleared"
    finally:
        unsub()
        await coordinator.async_close()


@pytest.mark.asyncio
async def test_incident_payload_is_stable_json_and_does_not_leak_tokens(
    hass, caplog
) -> None:
    caplog.set_level(logging.DEBUG, logger="custom_components.f1_sensor")
    bus = FakeIncidentLiveBus(auth_header="Bearer secret-token")
    events = []
    unsub = hass.bus.async_listen(
        _INCIDENT_EVENT, lambda event: events.append(event.data)
    )
    coordinator = await _coordinator(hass, bus)

    try:
        await _prime_context(hass, bus)
        bus.emit(
            "TimingData",
            {
                "Authorization": "Bearer secret-token",
                "subscription_token": "secret-token",
                **_timing(True),
            },
        )
        await hass.async_block_till_done()

        payload = events[-1]
        json.dumps(payload)
        assert set(payload) == {
            "entry_id",
            "incident_id",
            "phase",
            "confidence",
            "reason",
            "driver",
            "session",
            "track_status",
            "race_control",
            "signals",
            "started_at",
            "updated_at",
            "data_quality",
        }
        assert set(payload["driver"]) == {"racing_number", "tla", "name", "team"}
        assert set(payload["session"]) == {
            "meeting_name",
            "session_name",
            "session_type",
            "session_key",
        }
        assert set(payload["track_status"]) == {"status", "message"}
        assert set(payload["race_control"]) == {"message", "category", "flag"}
        serialized = json.dumps(payload)
        assert "secret-token" not in serialized
        assert "Bearer" not in serialized
        assert "secret-token" not in caplog.text
    finally:
        unsub()
        await coordinator.async_close()


@pytest.mark.asyncio
async def test_incident_events_respect_live_delay(hass) -> None:
    bus = FakeIncidentLiveBus()
    events = []
    unsub = hass.bus.async_listen(
        _INCIDENT_EVENT, lambda event: events.append(event.data)
    )
    coordinator = await _coordinator(hass, bus)

    try:
        await _prime_context(hass, bus)
        coordinator.set_delay(1)
        bus.emit("TimingData", _timing(True))

        await asyncio.sleep(0.2)
        await hass.async_block_till_done()
        assert events == []

        await asyncio.sleep(0.9)
        await hass.async_block_till_done()
        assert [event["phase"] for event in events] == ["confirmed"]
    finally:
        unsub()
        await coordinator.async_close()


@pytest.mark.asyncio
async def test_incident_replay_bypasses_live_delay(hass) -> None:
    live_state = LiveAvailabilityTracker()
    live_state.set_state(True, "replay-mode")
    bus = FakeIncidentLiveBus()
    events = []
    unsub = hass.bus.async_listen(
        _INCIDENT_EVENT, lambda event: events.append(event.data)
    )
    coordinator = await _coordinator(
        hass,
        bus,
        delay_seconds=1,
        live_state=live_state,
    )

    try:
        await _prime_context(hass, bus)
        bus.emit("TimingData", _timing(True))
        await hass.async_block_till_done()

        assert [event["phase"] for event in events] == ["confirmed"]
        assert events[-1]["data_quality"] == "replay"
    finally:
        unsub()
        await coordinator.async_close()


@pytest.mark.asyncio
async def test_incident_close_unsubscribes_and_cancels_delayed_events(hass) -> None:
    bus = FakeIncidentLiveBus()
    events = []
    unsub = hass.bus.async_listen(
        _INCIDENT_EVENT, lambda event: events.append(event.data)
    )
    coordinator = await _coordinator(hass, bus)

    try:
        await _prime_context(hass, bus)
        coordinator.set_delay(1)
        bus.emit("TimingData", _timing(True))

        await coordinator.async_close()
        await asyncio.sleep(1.1)
        await hass.async_block_till_done()

        assert events == []
        assert bus.unsubscribe_count == len(_INCIDENT_STREAMS)
    finally:
        unsub()
        await coordinator.async_close()
