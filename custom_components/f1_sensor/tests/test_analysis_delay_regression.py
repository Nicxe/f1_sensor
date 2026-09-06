"""Analysis must share the existing delayed time line and reset boundaries."""

from __future__ import annotations

import re
from types import SimpleNamespace

from homeassistant.config_entries import ConfigEntryState
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import f1_sensor as f1
from custom_components.f1_sensor.analysis import Phase4AnalysisStore
from custom_components.f1_sensor.analysis_websocket import _analysis_payload
from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS
from custom_components.f1_sensor.history import LapAnalysisStore
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.tests.test_phase_4_analysis import _Bus, _timing_pair


def _runtime(store):
    return SimpleNamespace(
        analysis=SimpleNamespace(store=store),
        live=None,
        replay=None,
        capabilities=SimpleNamespace(requested_streams=[], active_streams=[]),
    )


def _session(bus, session="A"):
    bus.emit("SessionInfo", {"Key": session, "Type": "Race", "Name": "Race"})
    bus.emit("SessionStatus", {"Status": "Started"})
    bus.emit(
        "RaceControlMessages",
        {"Messages": {"1": {"Message": f"Session {session}", "Category": "Other"}}},
    )
    bus.emit(
        "TimingData",
        _timing_pair(
            2, first_position=1, second_position=2, first_gap="", second_gap="+0.4"
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("delay", [0, 30])
async def test_analysis_and_laps_share_delayed_input(hass, monkeypatch, delay):
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
    raw = _Bus()
    delayed = f1._DelayedAnalysisBus(hass, raw, delay, None, None)
    laps = LapAnalysisStore(delayed, source_provider=lambda: "f1_live")
    analysis = Phase4AnalysisStore(delayed, laps, source_provider=lambda: "f1_live")
    observed = []
    analysis.add_listener(
        lambda: observed.append((analysis.diagnostics(), laps.diagnostics()))
    )
    try:
        _session(raw)
        # A second client reads the same delayed store while raw frames wait.
        if delay:
            snapshot = _analysis_payload(_runtime(analysis))
            assert snapshot["phase"] == "before"
            assert snapshot["session_id"] is None
            assert laps.diagnostics()["laps"] == 0
            assert analysis.diagnostics()["timeline_events"] == 0
            clock.value += 29.9
            f1._drain_delayed_ingest_queue(delayed)
            assert analysis.snapshot()["phase"] == "before"
            clock.value += 0.1
            f1._drain_delayed_ingest_queue(delayed)
        assert analysis.snapshot()["phase"] == "live"
        assert analysis.snapshot()["session_id"] == "A:Race"
        assert analysis.diagnostics()["timeline_events"] > 0
        assert laps.diagnostics()["laps"] == 2
        # The analysis callback must see the lap store updated for this frame.
        assert observed[-1][1]["laps"] == 2
        assert analysis.diagnostics()["updates"] == 4
        assert len(raw.callbacks["TimingData"]) == 1
        assert not delayed._delay_queue
    finally:
        await analysis.async_close()
        await laps.async_close()
        await delayed.async_close()
    assert not any(raw.callbacks.values())


@pytest.mark.asyncio
async def test_delay_changes_preserve_receipt_order_and_reset_drops_old_frames(
    hass, monkeypatch
):
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
    raw = _Bus()
    state = LiveAvailabilityTracker()
    state.set_state(True, "live_window")
    delayed = f1._DelayedAnalysisBus(hass, raw, 30, None, state)
    laps = LapAnalysisStore(delayed, source_provider=lambda: "f1_live")
    analysis = Phase4AnalysisStore(delayed, laps, source_provider=lambda: "f1_live")
    try:
        _session(raw, "A")
        delayed.set_delay(60)
        clock.value += 30
        f1._drain_delayed_ingest_queue(delayed)
        assert analysis.snapshot()["phase"] == "before"
        delayed.set_delay(0)
        assert analysis.snapshot()["session_id"] == "A:Race"
        delayed.set_delay(30)
        _session(raw, "stale")
        delayed.reset_for_replay()
        laps.reset_for_replay()
        analysis.reset_for_replay()
        state.set_state(True, "replay-mode")
        _session(raw, "B")
        assert analysis.snapshot()["session_id"] == "B:Race"
        assert not delayed._delay_queue
        state.set_state(False, "replay-ended")
        state.set_state(True, "live_window")
        _session(raw, "C")
        assert analysis.snapshot()["session_id"] == "B:Race"
        clock.value += 30
        f1._drain_delayed_ingest_queue(delayed)
        assert analysis.snapshot()["session_id"] == "C:Race"
        _session(raw, "after-close")
        await delayed.async_close()
        clock.value += 100
        f1._drain_delayed_ingest_queue(delayed)
        assert analysis.snapshot()["session_id"] == "C:Race"
        assert not delayed._delay_queue
        assert delayed._delay_queue_handle is None
    finally:
        await analysis.async_close()
        await laps.async_close()
        await delayed.async_close()


@pytest.mark.asyncio
async def test_new_websocket_during_delay_gets_only_delivered_analysis(
    hass, enable_custom_integrations, aioclient_mock, hass_ws_client, monkeypatch
):
    """The real HA subscribe command must not expose a raw pending session."""
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
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = None
    try:
        registry = hass.data[DOMAIN][entry.entry_id]
        bus = entry.runtime_data.live.bus
        analysis = entry.runtime_data.analysis.store
        delayed = registry["analysis_bus"]
        controller = registry["live_delay_controller"]
        registry["live_state"].set_state(True, "live-Race")
        await controller.async_set_delay(0)
        bus._dispatch(
            "SessionInfo", {"Key": "delivered", "Name": "Race", "Type": "Race"}
        )
        bus._dispatch("SessionStatus", {"Status": "Started"})
        assert analysis.snapshot()["session_id"] == "delivered:Race"

        # Keep the real entry, delay controller, bus, stores and websocket.
        # Advance only the integration's ingest clock, not HA's socket clock.
        clock = SimpleNamespace(value=100.0)
        monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
        await controller.async_set_delay(30)
        bus._dispatch("SessionInfo", {"Key": "pending", "Name": "Race", "Type": "Race"})
        assert delayed._delay_queue
        client = await hass_ws_client(hass)
        await client.send_json(
            {
                "id": 1,
                "type": "f1_sensor/analysis/subscribe",
                "entry_id": entry.entry_id,
                "protocol_version": 1,
                "throttle_ms": 100,
            }
        )
        acknowledgment = await client.receive_json()
        assert acknowledgment["id"] == 1 and acknowledgment["success"]
        initial = await client.receive_json()
        assert initial["id"] == 1 and initial["type"] == "event"
        assert initial["event"]["session_id"] == "delivered:Race"
        assert initial["event"]["phase"] == "live"

        clock.value = 129.9
        f1._drain_delayed_ingest_queue(delayed)
        await client.send_json(
            {
                "id": 2,
                "type": "f1_sensor/analysis/get",
                "entry_id": entry.entry_id,
            }
        )
        before_boundary = await client.receive_json()
        assert before_boundary["id"] == 2 and before_boundary["success"]
        assert before_boundary["result"]["session_id"] == "delivered:Race"

        clock.value = 130.0
        f1._drain_delayed_ingest_queue(delayed)
        updated = await client.receive_json()
        assert updated["id"] == 1 and updated["type"] == "event"
        assert updated["event"]["session_id"] == "pending:Race"
        assert not delayed._delay_queue
    finally:
        if client is not None:
            await client.close()
        if entry.state == ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
