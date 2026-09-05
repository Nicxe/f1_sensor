"""Analysis must share the existing delayed time line and reset boundaries."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components import f1_sensor as f1
from custom_components.f1_sensor.analysis import Phase4AnalysisStore
from custom_components.f1_sensor.analysis_websocket import _analysis_payload
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
