"""Freeze analysis as soon as No Spoiler Mode is enabled, including during save."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from custom_components import f1_sensor as f1
from custom_components.f1_sensor.analysis import Phase4AnalysisStore
from custom_components.f1_sensor.history import LapAnalysisStore
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager
from custom_components.f1_sensor.tests.test_phase_4_analysis import _Bus


@pytest.mark.asyncio
@pytest.mark.parametrize("delay", [0, 30])
async def test_no_spoiler_blocks_analysis_before_storage_save_and_supervisor_notice(
    hass, monkeypatch, delay
):
    """The manager changes state before storage and supervisor callbacks complete."""
    manager = NoSpoilerModeManager(hass)
    hass.data.setdefault(f1.DOMAIN, {})["no_spoiler_manager"] = manager
    saving, release_save = asyncio.Event(), asyncio.Event()
    notified = []
    manager.add_listener(notified.append)

    async def _async_save(data):
        assert data == {"active": True}
        saving.set()
        await release_save.wait()

    monkeypatch.setattr(manager._store, "async_save", _async_save)
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
    state = LiveAvailabilityTracker()
    state.set_state(True, "live-Race")
    raw = _Bus()
    delayed = f1._DelayedAnalysisBus(hass, raw, delay, None, state)
    laps = LapAnalysisStore(delayed, source_provider=lambda: "f1_live")
    analysis = Phase4AnalysisStore(delayed, laps, source_provider=lambda: "f1_live")
    if delay:
        raw.emit("SessionStatus", {"Status": "Started"})
        assert delayed._delay_queue

    activation = asyncio.create_task(manager.async_set_active(True))
    try:
        await saving.wait()
        assert manager.is_active
        assert not notified
        assert state.reason == "live-Race"
        assert analysis.snapshot()["phase"] == "before"

        if delay:
            clock.value += delay
            f1._drain_delayed_ingest_queue(delayed)
        else:
            raw.emit("SessionStatus", {"Status": "Started"})
        assert analysis.snapshot()["phase"] == "before"
        assert analysis.diagnostics()["updates"] == 0
        assert not delayed._delay_queue

        # Replay remains available while the global No Spoiler setting is active.
        state.set_state(True, "replay")
        raw.emit("SessionInfo", {"Key": "replay-A", "Type": "Race", "Name": "Race"})
        raw.emit("SessionStatus", {"Status": "Started"})
        assert analysis.snapshot()["phase"] == "live"
        assert analysis.snapshot()["session_id"] == "replay-A:Race"
        assert not delayed._delay_queue
    finally:
        release_save.set()
        await activation
        await analysis.async_close()
        await laps.async_close()
        await delayed.async_close()

    assert notified == [True]
    assert not any(raw.callbacks.values())
