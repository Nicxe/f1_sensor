"""Tests for Phase 4 analysis WebSocket lifecycle and demand."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor.analysis import (
    PHASE4_ANALYSIS_STREAMS,
    Phase4AnalysisStore,
)
from custom_components.f1_sensor.analysis_websocket import (
    ANALYSIS_PROTOCOL_VERSION,
    ANALYSIS_SUBSCRIBE_WS_TYPE,
    _ws_subscribe_analysis,
)
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.history import LapAnalysisStore
from custom_components.f1_sensor.providers import ProviderRegistry
from custom_components.f1_sensor.runtime import (
    AnalysisRuntime,
    CacheRuntime,
    CapabilityState,
    F1RuntimeData,
    HistoryRuntime,
    LiveRuntime,
    ProviderRuntime,
    StaticRuntime,
)
from custom_components.f1_sensor.track_map import TrackMapRuntimeData, TrackMapStore


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


class DemandBus:
    def __init__(self) -> None:
        self.callbacks: dict[str, list] = {}
        self.requested_streams = frozenset({"Heartbeat"})
        self.started = False
        self.closed = False
        self.is_connected = True

    @property
    def active_streams(self) -> frozenset[str]:
        return self.requested_streams

    def subscribe(self, stream, callback):
        self.callbacks.setdefault(stream, []).append(callback)
        return lambda: self.callbacks[stream].remove(callback)

    async def async_update_streams(self, streams) -> None:
        self.requested_streams = frozenset(streams)

    async def start(self) -> None:
        self.started = True
        self.closed = False

    async def async_close(self) -> None:
        self.started = False
        self.closed = True


@pytest.mark.asyncio
async def test_analysis_subscription_owns_transient_stream_demand(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    entry.add_to_hass(hass)
    bus = DemandBus()
    lap_store = LapAnalysisStore(bus, source_provider=lambda: "f1_live")
    analysis_store = Phase4AnalysisStore(
        bus,
        lap_store,
        source_provider=lambda: "f1_live",
    )
    entry.runtime_data = F1RuntimeData(
        static=StaticRuntime(),
        live=LiveRuntime(bus=bus, availability=SimpleNamespace(is_live=True)),
        replay=None,
        track_map=TrackMapRuntimeData(TrackMapStore(entry.entry_id)),
        cache=CacheRuntime(object(), {}, {}, {}),
        providers=ProviderRuntime(ProviderRegistry()),
        history=HistoryRuntime(service=object(), lap_analysis=lap_store),
        capabilities=CapabilityState(
            frozenset(),
            frozenset({"Heartbeat"}),
            frozenset({"Heartbeat"}),
            {"Heartbeat": ("live_transport_health",)},
        ),
        legacy={},
        analysis=AnalysisRuntime(store=analysis_store, telemetry=object()),
    )
    connection = FakeConnection()

    _ws_subscribe_analysis(
        hass,
        connection,
        {
            "id": 40,
            "type": ANALYSIS_SUBSCRIBE_WS_TYPE,
            "entry_id": entry.entry_id,
            "protocol_version": ANALYSIS_PROTOCOL_VERSION,
            "throttle_ms": 500,
        },
    )
    await hass.async_block_till_done()

    assert connection.results == [(40, None)]
    assert connection.events[0][1]["status"] == "ready"
    assert connection.events[0][1]["capabilities"]["connection"] == "connected"
    assert bus.requested_streams == PHASE4_ANALYSIS_STREAMS | {"Heartbeat"}
    assert bus.started is True
    assert entry.runtime_data.capabilities.stream_reasons["TimingData"] == (
        "weekend_hub_card",
    )

    connection.subscriptions.pop(40)()
    await hass.async_block_till_done()

    assert bus.requested_streams == frozenset({"Heartbeat"})
    assert "TimingData" not in entry.runtime_data.capabilities.stream_reasons
    assert bus.closed is False
    await analysis_store.async_close()
    await lap_store.async_close()
