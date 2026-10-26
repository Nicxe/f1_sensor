"""Recorded late LapCount projections retain totals within a confirmed session."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import f1_sensor as integration
from custom_components.f1_sensor.card_data import CardDataStore
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.feature_plan import build_feature_plan
from custom_components.f1_sensor.live_data_models import LapCountModel
from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager


class Bus:
    def __init__(self):
        self.callbacks = {}

    def subscribe(self, stream, callback):
        self.callbacks[stream] = callback
        return lambda: self.callbacks.pop(stream, None)

    def emit(self, stream, payload):
        if callback := self.callbacks.get(stream):
            callback(deepcopy(payload))


class Context:
    def __init__(self, data):
        self.data = data
        self.listeners = set()

    def async_add_listener(self, callback):
        self.listeners.add(callback)
        return lambda: self.listeners.discard(callback)


@pytest.fixture
def payloads():
    fixture = Path(__file__).parent / "fixtures/race-20261025-lap-payloads.json"
    return json.loads(fixture.read_text())


@pytest.fixture
async def race_runtime(hass, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    context = Context({"Key": 11396, "Type": "Race", "Name": "Race"})
    bus = Bus()
    coordinator = integration.LapCountCoordinator(
        hass, SimpleNamespace(data={}), config_entry=entry, bus=bus
    )
    monkeypatch.setattr(
        DataUpdateCoordinator, "async_config_entry_first_refresh", AsyncMock()
    )
    await coordinator.async_config_entry_first_refresh()
    data = {
        "lap_count_coordinator": coordinator,
        "session_info_coordinator": context,
        "session_status_coordinator": Context({"Status": "Started"}),
        "live_state": SimpleNamespace(is_live=True, reason="live"),
        "live_bus": SimpleNamespace(last_stream_activity_age=lambda: 0),
    }
    manager = NoSpoilerModeManager(hass)
    hass.data[DOMAIN] = {"no_spoiler_manager": manager, entry.entry_id: data}
    yield entry, coordinator, bus, data, manager
    await coordinator.async_close()
    assert bus.callbacks == {}


@pytest.mark.parametrize("initial_before_identity", [False, True])
@pytest.mark.parametrize("optional_model_warmed", [False, True])
async def test_recorded_late_direct_snapshot_keeps_same_race_total(
    hass, race_runtime, payloads, initial_before_identity, optional_model_warmed
):
    entry, coordinator, bus, data, _ = race_runtime
    original = deepcopy(payloads)
    if not initial_before_identity:
        bus.emit("SessionInfo", {"Key": 11396})
    bus.emit("LapCount", payloads["initial"])
    if initial_before_identity:
        bus.emit("SessionInfo", {"Key": 11396})
    warm = None
    if optional_model_warmed:
        warm = LapCountModel(coordinator, None, entry.entry_id, None)
        assert warm.snapshot().attributes["total_laps"] == 56
    bus.emit("LapCount", payloads["incremental"])
    if warm is not None:
        assert warm.snapshot().attributes["total_laps"] == 56
    owner = CardDataStore(hass, entry, data)
    try:
        current = owner.snapshot("race_lap_count")
        assert current["status"] == "ready"
        assert current["context"]["session_id"] == "11396"
        assert current["payload"]["state"] == 2
        assert current["payload"]["attributes"]["total_laps"] == 56
        assert not hass.states.async_all()
        assert payloads == original
    finally:
        await owner.async_close()


async def test_confirmed_new_session_clears_total_and_direct_generation(
    hass, race_runtime, payloads
):
    entry, coordinator, bus, data, _ = race_runtime
    bus.emit("SessionInfo", {"Key": 11396})
    bus.emit("LapCount", payloads["initial"])
    owner = CardDataStore(hass, entry, data)
    stop = owner.subscribe(["race_lap_count"], Mock())
    try:
        first = owner.snapshot("race_lap_count")
        bus.emit(
            "SessionInfo", {"Name": "Race", "ArchiveStatus": {"Status": "Generating"}}
        )
        bus.emit("SessionInfo", {"Key": "11396"})
        bus.emit("LapCount", {"CurrentLap": 2})
        assert (
            owner.snapshot("race_lap_count")["payload"]["attributes"]["total_laps"]
            == 56
        )
        data["session_info_coordinator"].data = {"Key": 11397, "Type": "Race"}
        bus.emit("SessionInfo", {"Key": 11397})
        waiting = owner.snapshot("race_lap_count")
        assert waiting["generation"] != first["generation"]
        assert waiting["payload"] is None
        bus.emit("LapCount", {"CurrentLap": 1})
        current = owner.snapshot("race_lap_count")
        assert current["context"]["session_id"] == "11397"
        assert current["payload"]["state"] == 1
        assert current["payload"]["attributes"]["total_laps"] is None
        late = CardDataStore(hass, entry, data)
        try:
            assert (
                late.snapshot("race_lap_count")["payload"]["attributes"]["total_laps"]
                is None
            )
        finally:
            await late.async_close()
    finally:
        stop()
        await owner.async_close()


async def test_explicit_unknown_total_is_not_replaced_with_old_total(race_runtime):
    _, coordinator, bus, _, _ = race_runtime
    bus.emit("SessionInfo", {"Key": 11396})
    bus.emit("LapCount", {"CurrentLap": 1, "TotalLaps": 56})
    bus.emit("LapCount", {"CurrentLap": 2, "TotalLaps": None})
    assert coordinator.data["TotalLaps"] is None
    bus.emit("LapCount", {"CurrentLap": 3})
    assert coordinator.data.get("TotalLaps") is None


@pytest.mark.parametrize("reset", ["seek", "return_to_live", "window_end"])
async def test_reset_does_not_carry_previous_total(race_runtime, reset):
    _, coordinator, bus, _, _ = race_runtime
    bus.emit("SessionInfo", {"Key": 11396})
    bus.emit("LapCount", {"CurrentLap": 20, "TotalLaps": 56})
    if reset == "seek":
        integration._reset_replay_sensitive_coordinator_state(coordinator)
    elif reset == "return_to_live":
        coordinator._handle_live_state(True, "replay")
        bus.emit("SessionInfo", {"Key": "archived-session"})
        bus.emit("LapCount", {"CurrentLap": 10, "TotalLaps": 53})
        coordinator._handle_live_state(True, "live")
    else:
        coordinator._handle_live_state(False, "window-ended")
    bus.emit("SessionInfo", {"Key": 11396})
    bus.emit("LapCount", {"CurrentLap": 1})
    assert coordinator.data.get("TotalLaps") is None


async def test_delayed_session_reset_preserves_ordered_new_session_frames(race_runtime):
    _, coordinator, bus, _, _ = race_runtime
    bus.emit("SessionInfo", {"Key": 11396})
    bus.emit("LapCount", {"CurrentLap": 1, "TotalLaps": 56})
    coordinator.set_delay(50)
    with patch.object(integration.time, "monotonic", return_value=100):
        bus.emit("LapCount", {"CurrentLap": 2})
        bus.emit("SessionInfo", {"Key": 11397})
        bus.emit("LapCount", {"CurrentLap": 1})
        bus.emit("LapCount", {"CurrentLap": 2})
        assert coordinator.data["CurrentLap"] == 1
    with patch.object(integration.time, "monotonic", return_value=150):
        integration._drain_delayed_ingest_queue(coordinator)
    assert coordinator.data["CurrentLap"] == 2
    assert coordinator.data.get("TotalLaps") is None
    assert not coordinator._delay_queue


async def test_no_spoiler_keeps_frozen_data_until_unblocked(race_runtime):
    _, coordinator, bus, _, manager = race_runtime
    bus.emit("SessionInfo", {"Key": 11396})
    bus.emit("LapCount", {"CurrentLap": 1, "TotalLaps": 56})
    await manager.async_set_active(True)
    coordinator._handle_live_state(True, "no-spoiler")
    bus.emit("LapCount", {"CurrentLap": 2, "TotalLaps": 50})
    assert coordinator.data == {"CurrentLap": 1, "TotalLaps": 56}
    await manager.async_set_active(False)
    bus.emit("LapCount", {"CurrentLap": 3})
    assert coordinator.data == {"CurrentLap": 3, "TotalLaps": 56}


async def test_owned_replay_stop_during_no_spoiler_cannot_carry_replay_total(
    race_runtime,
):
    _, coordinator, bus, _, manager = race_runtime
    coordinator._handle_live_state(True, "replay")
    bus.emit("SessionInfo", {"Key": 11396})
    bus.emit("LapCount", {"CurrentLap": 20, "TotalLaps": 53})
    await manager.async_set_active(True)
    coordinator._handle_live_state(True, "no-spoiler")
    bus.emit("LapCount", {"CurrentLap": 21})
    assert coordinator.data == {"CurrentLap": 20, "TotalLaps": 53}
    # ReplayController.stop runs this owner reset before replay-stopped/live state.
    integration._reset_replay_sensitive_coordinator_state(coordinator)
    coordinator._handle_live_state(False, "replay-stopped")
    await manager.async_set_active(False)
    coordinator._handle_live_state(True, "live")
    # Same session key is insufficient to bind a different live/replay source.
    bus.emit("SessionInfo", {"Key": 11396})
    bus.emit("LapCount", {"CurrentLap": 1})
    assert coordinator.data.get("TotalLaps") is None


async def test_confirmed_session_change_during_no_spoiler_drops_old_total(
    hass,
    race_runtime,
):
    entry, coordinator, bus, data, manager = race_runtime
    bus.emit("SessionInfo", {"Key": 11396})
    bus.emit("LapCount", {"CurrentLap": 20, "TotalLaps": 56})
    owner = CardDataStore(hass, entry, data)
    stop = owner.subscribe(["race_lap_count"], Mock())
    try:
        await manager.async_set_active(True)
        coordinator._handle_live_state(True, "no-spoiler")
        data["session_info_coordinator"].data = {"Key": 11397, "Type": "Race"}
        bus.emit("SessionInfo", {"Key": 11397})
        bus.emit("LapCount", {"CurrentLap": 1, "TotalLaps": 50})
        assert owner.snapshot("race_lap_count")["status"] == "blocked"
        await manager.async_set_active(False)
        coordinator._handle_live_state(True, "live")
        bus.emit("LapCount", {"CurrentLap": 2})
        current = owner.snapshot("race_lap_count")
        assert current["context"]["session_id"] == "11397"
        assert current["payload"]["state"] == 2
        assert current["payload"]["attributes"]["total_laps"] is None
    finally:
        stop()
        await owner.async_close()


def test_lap_only_feature_plan_requests_session_identity():
    assert (
        "SessionInfo"
        in build_feature_plan({"race_lap_count"}, live_enabled=True).public_streams
    )
