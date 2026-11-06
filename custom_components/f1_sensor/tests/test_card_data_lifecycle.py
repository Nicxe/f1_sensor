"""Recorded session data, protected reconnects and runtime-owned history."""

from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
from threading import get_ident
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.f1_sensor import LiveDriversCoordinator, RaceControlCoordinator
from custom_components.f1_sensor.card_data import CardDataStore
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager
from custom_components.f1_sensor.replay_mode import (
    ReplayController,
    ReplayIndex,
    ReplaySession,
    ReplayState,
    ReplayTransport,
)
from custom_components.f1_sensor.runtime import active_sensor_demand
from custom_components.f1_sensor.sensor import F1TrackLimitsSensor
from custom_components.f1_sensor.signalr import LiveBus


class Source:
    def __init__(self, hass, data):
        self.hass, self.data = hass, data
        self.data_list = []
        self.last_update_success = self.available = True
        self.listeners = set()

    def async_add_listener(self, listener):
        self.listeners.add(listener)
        return lambda: self.listeners.discard(listener)

    def update(self):
        for listener in tuple(self.listeners):
            listener()


def setup(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        options={"card_data_features": ["track_limits", "race_lap_count"]},
    )
    entry.add_to_hass(hass)
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/race_control_p2_checkpoint.json").read_text()
    )
    messages = RaceControlCoordinator._extract_items(fixture["checkpoint"])
    coordinator = Source(hass, messages[-1])
    coordinator.data_list = messages
    context = Source(hass, {"Key": fixture["session_id"], "Type": "Practice"})
    live_state = LiveAvailabilityTracker()
    live_state.set_state(True, "replay")
    data = {
        "race_control_coordinator": coordinator,
        "session_info_coordinator": context,
        "lap_count_coordinator": Source(hass, {"CurrentLap": 5, "TotalLaps": 58}),
        "live_state": live_state,
        "live_bus": SimpleNamespace(last_stream_activity_age=lambda: 0),
    }
    hass.data[DOMAIN] = {
        entry.entry_id: data,
        "no_spoiler_manager": NoSpoilerModeManager(hass),
    }
    owner = CardDataStore(hass, entry, data)
    return entry, data, owner


@pytest.mark.parametrize("entity_mode", ["enabled", "disabled", "absent"])
async def test_recorded_track_limits_equal_sensor_with_any_exposure(hass, entity_mode):
    entry, data, owner = setup(hass)
    if entity_mode != "absent":
        er.async_get(hass).async_get_or_create(
            "sensor",
            DOMAIN,
            f"{entry.entry_id}_track_limits",
            config_entry=entry,
            disabled_by=er.RegistryEntryDisabler.USER
            if entity_mode == "disabled"
            else None,
        )
    sensor = F1TrackLimitsSensor(
        data["race_control_coordinator"], "comparison", entry.entry_id, "F1"
    )
    sensor.hass = hass
    sensor.async_write_ha_state = Mock()
    sensor._handle_coordinator_update()
    direct = owner.snapshot("track_limits")
    assert direct["status"] == "ready"
    assert direct["payload"]["state"] == sensor.state
    actual, expected = direct["payload"]["attributes"], sensor.extra_state_attributes
    assert {key: value for key, value in actual.items() if key != "last_update"} == {
        key: value for key, value in expected.items() if key != "last_update"
    }
    assert actual["total_deletions"] > 0
    demand = active_sensor_demand(hass, entry, {"track_limits"})
    assert ("track_limits" in demand) is (entity_mode != "disabled")
    assert not hass.states.async_all()
    await owner.async_close()


async def test_history_collects_without_card_and_survives_runtime_restore(hass):
    entry, data, owner = setup(hass)
    owner._storage.async_load = AsyncMock(return_value=None)
    owner._storage.async_save = AsyncMock()
    await owner.async_start()
    assert len(data["race_control_coordinator"].listeners) == 1
    assert owner._persisted["track_limits"]["model_state"]["_processed_ids"]
    saved = deepcopy(owner._persisted)
    json.dumps(saved)
    expected = owner.snapshot("track_limits")["payload"]["state"]
    await owner.async_close()
    assert not data["race_control_coordinator"].listeners
    # A reconnect can start with only the latest message, not the earlier log.
    data["race_control_coordinator"].data_list = [data["race_control_coordinator"].data]
    restored = CardDataStore(hass, entry, data)
    restored._persisted = saved
    assert restored.snapshot("track_limits")["payload"]["state"] == expected
    await restored.async_close()


async def test_session_change_retires_generation_and_spoiler_clears_reconnect(hass):
    entry, data, owner = setup(hass)
    messages = []
    stop = owner.subscribe(["race_lap_count", "session_context"], messages.append)
    first = owner.snapshot("race_lap_count")
    data["session_info_coordinator"].data = {"Key": "next-session"}
    data["session_info_coordinator"].update()
    current = owner.snapshot("race_lap_count")
    assert first["generation"] != current["generation"]
    assert current["context"]["session_id"] == "next-session"
    assert current["payload"] is None
    assert current["reason"] == "waiting_for_current_context"
    data["lap_count_coordinator"].data = {"CurrentLap": 1, "TotalLaps": 50}
    data["lap_count_coordinator"].update()
    assert owner.snapshot("race_lap_count")["payload"]["state"] == 1
    await hass.data[DOMAIN]["no_spoiler_manager"].async_set_active(True)
    assert owner.snapshot("race_lap_count")["payload"] is None
    reconnect = []
    peer = owner.subscribe(["race_lap_count"], reconnect.append)
    assert reconnect[-1]["status"] == "blocked"
    peer()
    stop()
    await owner.async_close()


async def test_timing_publications_are_coalesced_but_context_is_immediate(hass):
    entry, data, owner = setup(hass)
    messages = []
    with patch("custom_components.f1_sensor.card_data.monotonic", return_value=10):
        stop = owner.subscribe(["race_lap_count"], messages.append)
        for lap in (6, 7, 8):
            data["lap_count_coordinator"].data = {"CurrentLap": lap, "TotalLaps": 58}
            data["lap_count_coordinator"].update()
        assert len(messages) == 2
        assert "race_lap_count" in owner._delayed
        data["session_info_coordinator"].data = {"Key": "new-session"}
        data["session_info_coordinator"].update()
        assert messages[-1]["context"]["session_id"] == "new-session"
    stop()
    await owner.async_close()


async def test_delayed_publication_runs_on_ha_loop_and_persists_latest_update(hass):
    """The real HA timer must not send async storage work to an executor."""
    entry, data, owner = setup(hass)
    loop_thread = get_ident()
    received = []

    def receive(message):
        received.append((get_ident(), message))

    await owner.async_start()
    stop = owner.subscribe(["race_lap_count"], receive)
    try:
        with patch("custom_components.f1_sensor.card_data.monotonic", return_value=10):
            for lap in (6, 7, 8):
                data["lap_count_coordinator"].data = {
                    "CurrentLap": lap,
                    "TotalLaps": 58,
                }
                data["lap_count_coordinator"].update()
            assert [message["payload"]["state"] for _, message in received] == [5, 6]
            assert "race_lap_count" in owner._delayed

            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
            await hass.async_block_till_done()

        assert [message["payload"]["state"] for _, message in received] == [5, 6, 8]
        assert all(thread == loop_thread for thread, _ in received)
        assert "race_lap_count" not in owner._delayed
        assert owner._persisted["race_lap_count"]["payload"]["state"] == 8
    finally:
        stop()
        await owner.async_close()


@pytest.mark.parametrize("retirement", ["reset", "close"])
async def test_retirement_cancels_pending_card_publications(hass, retirement):
    """Real timers cannot publish after their session or entry is retired."""
    entry, data, owner = setup(hass)
    source = data["drivers_coordinator"] = Source(hass, {"drivers": {}})
    stop = owner.subscribe(["driver_list"], lambda _message: None)
    try:
        with patch("custom_components.f1_sensor.card_data.monotonic", return_value=10):
            for number in ("1", "4"):
                source.data["drivers"][number] = {"identity": {"racing_number": number}}
                source.update()
            assert "driver_list" in owner._delayed
            if retirement == "reset":
                owner.reset_for_replay()
            else:
                await owner.async_close()

            assert not owner._delayed
            with patch.object(owner, "_publish", wraps=owner._publish) as publish:
                async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
                await hass.async_block_till_done()
                publish.assert_not_called()
    finally:
        stop()
        await owner.async_close()


async def test_delayed_session_identity_keeps_only_matching_saved_history(hass):
    entry, data, owner = setup(hass)
    expected = owner.snapshot("track_limits")["payload"]["state"]
    saved = deepcopy(owner._persisted)
    session = deepcopy(data["session_info_coordinator"].data)
    await owner.async_close()
    restored = CardDataStore(hass, entry, data)
    restored._persisted = saved
    data["session_info_coordinator"].data = {}
    restored.snapshot("session_context")
    data["session_info_coordinator"].data = session
    data["race_control_coordinator"].data_list = [data["race_control_coordinator"].data]
    assert restored.snapshot("track_limits")["payload"]["state"] == expected
    await restored.async_close()


async def test_replay_delay_clock_and_final_unsubscribe_are_owned_by_runtime(hass):
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    from custom_components.f1_sensor.live_delay import LiveDelayController

    entry, data, owner = setup(hass)
    replay_callbacks = []
    data["replay_controller"] = SimpleNamespace(
        session_manager=SimpleNamespace(
            add_listener=lambda listener: (
                replay_callbacks.append(listener)
                or (lambda: replay_callbacks.remove(listener))
            )
        ),
        get_playback_status=lambda: {"position_ms": 5000, "duration_ms": 10000},
        get_sync_points=lambda: [],
    )
    delay = LiveDelayController(hass, entry.entry_id)
    delay._store.async_save = AsyncMock()
    await delay.async_initialize(0)
    data["live_delay_controller"] = delay
    owner._storage.async_load = AsyncMock(return_value={"products": {}})
    owner._storage.async_save = AsyncMock()
    await owner.async_start()
    await owner.async_start()
    received = []
    stop = owner.subscribe(
        ["replay_status", "session_context", "race_lap_count"], received.append
    )
    replay_callbacks[0]({"state": "playing", "selected_session_id": "replay-session"})
    assert owner.snapshot("replay_status")["source"] == "replay"
    assert owner.snapshot("race_lap_count")["payload"] is None
    data["lap_count_coordinator"].update()
    assert owner.snapshot("race_lap_count")["payload"]["state"] == 5
    await delay.async_set_delay(30)
    assert (
        owner.snapshot("session_context")["payload"]["attributes"]["live_delay_seconds"]
        == 30
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done()
    assert owner._timer is not None
    stop()
    stop()
    await owner.async_close()
    await owner.async_close()
    owner._tick(None)
    owner._schedule_publish("race_lap_count")
    assert not replay_callbacks
    assert owner._timer is None
    await delay.async_close()


async def test_unloaded_loading_stale_and_inactive_sources_remain_distinct(hass):
    entry, data, owner = setup(hass)
    assert owner.snapshot("unknown-product")["status"] == "unsupported"
    source = data["lap_count_coordinator"]
    data["lap_count_coordinator"] = None
    assert owner.snapshot("race_lap_count")["status"] == "unavailable"
    data["lap_count_coordinator"] = source
    source.data = None
    assert owner.snapshot("race_lap_count")["status"] == "loading"
    source.data = {"CurrentLap": 7}
    source.last_update_success = False
    assert owner.snapshot("race_lap_count")["status"] == "stale"
    source.available = False
    assert owner.snapshot("race_lap_count")["status"] == "unavailable"
    await owner.async_close()


async def test_no_sources_is_idle_and_obsolete_selection_does_not_restrict_card_data(
    hass,
):
    from custom_components.f1_sensor.card_data import available_card_features

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    owner = CardDataStore(hass, entry, {})
    owner._storage.async_load = AsyncMock()
    await owner.async_start()
    owner._storage.async_load.assert_awaited_once()
    assert owner._timer is None
    assert not owner._unsubs
    await owner.async_close()
    hass.config_entries.async_update_entry(
        entry, options={"card_data_features": ["driver_positions"]}
    )
    assert {
        "session_context",
        "driver_list",
        "current_tyres",
        "replay_status",
    } <= available_card_features(entry)


async def test_qualifying_context_precedes_throttled_timing_and_respects_spoilers(hass):
    entry, data, owner = setup(hass)
    status = Source(hass, {"Status": "Started"})
    status.is_qualifying_like_session = True
    status.qualifying_part = 1
    data["session_status_coordinator"] = status
    received = []
    with patch("custom_components.f1_sensor.card_data.monotonic", return_value=100):
        stop = owner.subscribe(["race_lap_count", "session_context"], received.append)
        data["lap_count_coordinator"].update()
        status.qualifying_part = 2
        status.update()
        context = [
            message for message in received if message["dataset"] == "session_context"
        ][-1]
        timing = [
            message for message in received if message["dataset"] == "race_lap_count"
        ][-1]
        assert context["context"]["qualifying_part"] == 2
        assert timing["context"]["qualifying_part"] == 1
        assert "race_lap_count" in owner._delayed
        await hass.data[DOMAIN]["no_spoiler_manager"].async_set_active(True)
        assert owner.snapshot("session_context")["context"]["qualifying_part"] is None
    stop()
    await owner.async_close()


async def test_home_assistant_stop_closes_runtime_owned_clock_and_sources(hass):
    from homeassistant.const import EVENT_HOMEASSISTANT_STOP

    entry, data, owner = setup(hass)
    sources = SimpleNamespace(
        reconcile=Mock(), mark_updated=Mock(), async_close=AsyncMock()
    )
    data["card_data_sources"] = sources
    await owner.async_start()
    assert owner._timer is not None
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    assert owner.closed
    assert owner._timer is None
    sources.async_close.assert_awaited_once()
    await owner.async_close()


@pytest.fixture
async def active_replay_card_data(hass, tmp_path):
    """Use actual replay selection and TimingData paths without starting playback."""
    entry, data, owner = setup(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    bus = LiveBus(hass, AsyncMock())
    session = data["session_info_coordinator"]
    session.data = {"Key": "archive-A", "Type": "Race", "Name": "Race"}
    drivers = LiveDriversCoordinator(hass, session, bus=bus, config_entry=entry)
    await drivers.async_config_entry_first_refresh()
    drivers._replay_mode = True
    controller = ReplayController(hass, entry.entry_id, AsyncMock(), bus)
    manager = controller.session_manager
    now = dt_util.utcnow()
    sessions = [
        ReplaySession(
            year=2025,
            meeting_key=1,
            meeting_name="Test",
            session_key=key,
            session_name="Race",
            session_type="Race",
            path=f"2025/Test/{key}",
            start_utc=now,
            end_utc=now,
        )
        for key in (10, 20)
    ]
    index = ReplayIndex(
        session_id=sessions[0].unique_id,
        total_frames=0,
        duration_ms=10000,
        session_started_at_ms=0,
        frames_file=tmp_path / "frames.jsonl",
        index_file=tmp_path / "index.json",
    )
    manager._available_sessions = sessions
    manager._selected_session = sessions[0]
    manager._loaded_index = index
    manager._state = ReplayState.PLAYING
    controller._replay_active = True
    controller._transport = ReplayTransport(hass, index)
    data.update(replay_controller=controller, drivers_coordinator=drivers, live_bus=bus)
    owner._storage.async_load = AsyncMock(return_value=None)
    owner._storage.async_save = AsyncMock()
    await owner.async_start()
    stop = owner.subscribe(
        ["driver_positions", "session_context"], lambda _message: None
    )
    bus.inject_message("SessionInfo", session.data)
    bus.inject_message("DriverList", {"4": {"RacingNumber": "4", "Tla": "NOR"}})
    bus.inject_message("SessionStatus", {"Status": "Started"})

    def timing(lap):
        bus.inject_message(
            "TimingData",
            {
                "Lines": {
                    "4": {
                        "NumberOfLaps": lap,
                        "LastLapTime": {"Value": "1:30.000"},
                    }
                }
            },
        )

    timing(2)
    try:
        yield SimpleNamespace(
            owner=owner,
            data=data,
            controller=controller,
            manager=manager,
            sessions=sessions,
            index=index,
            timing=timing,
        )
    finally:
        stop()
        await owner.async_close()
        await controller.async_close()
        await drivers.async_close()


@pytest.mark.parametrize("operation_mode", ["live", "development"])
@pytest.mark.parametrize("selection", ["session", "year"])
async def test_active_replay_card_data_follows_transport_not_selection(
    active_replay_card_data,
    operation_mode,
    selection,
):
    state = active_replay_card_data
    state.data["operation_mode"] = operation_mode
    before = state.owner.snapshot("driver_positions")
    assert before["source"] == "replay"
    assert before["context"]["session_id"] == state.sessions[0].unique_id
    assert before["payload"]["attributes"]["drivers"][0]["completed_laps"] == 2
    if selection == "session":
        await state.manager.async_select_session(state.sessions[1].unique_id)
    else:
        state.manager.async_fetch_sessions = AsyncMock(return_value=[])
        await state.manager.async_set_year(state.manager.selected_year - 1)
    state.timing(3)
    current = state.owner.snapshot("driver_positions")
    assert current["source"] == "replay"
    assert current["context"]["session_id"] == state.sessions[0].unique_id
    assert current["generation"] == before["generation"]
    assert current["payload"]["attributes"]["drivers"][0]["completed_laps"] == 3


@pytest.mark.parametrize("operation_mode", ["live", "development"])
async def test_active_replay_without_index_stays_pending_after_year_selection(
    active_replay_card_data,
    operation_mode,
):
    state = active_replay_card_data
    state.data["operation_mode"] = operation_mode
    state.controller._transport = None
    state.manager.async_fetch_sessions = AsyncMock(return_value=[])
    await state.manager.async_set_year(state.manager.selected_year - 1)
    state.timing(3)
    current = state.owner.snapshot("driver_positions")
    assert current["source"] == "replay"
    assert current["context"]["session_id"] is None
    assert current["status"] == "loading"
    assert current["reason"] == "waiting_for_current_context"
    assert current["payload"] is None

    # Catch-up can have a verified loaded index before its transport is created.
    state.manager._loaded_index = state.index
    state.timing(4)
    recovered = state.owner.snapshot("driver_positions")
    assert recovered["source"] == "replay"
    assert recovered["context"]["session_id"] == state.sessions[0].unique_id
    assert recovered["status"] == "ready"
    assert recovered["payload"]["attributes"]["drivers"][0]["completed_laps"] == 4


@pytest.mark.parametrize("operation_mode", ["live", "development"])
async def test_inactive_controller_keeps_actual_live_or_legacy_file_identity(
    active_replay_card_data,
    operation_mode,
):
    state = active_replay_card_data
    state.data["operation_mode"] = operation_mode
    state.controller._replay_active = False
    state.controller._transport = None
    await state.manager.async_select_session(state.sessions[1].unique_id)
    state.timing(3)
    current = state.owner.snapshot("driver_positions")
    assert current["source"] == (
        "replay" if operation_mode == "development" else "live"
    )
    assert current["context"]["session_id"] == "archive-A"
    assert current["status"] == "ready"
