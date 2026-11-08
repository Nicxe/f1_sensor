"""Confirmed feed references belong only to the modular timing payload."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant import config_entries
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import f1_sensor as f1
from custom_components.f1_sensor import LiveDriversCoordinator
from custom_components.f1_sensor.card_data import CardDataStore
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.live_data_models import DriverPositionsModel
from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager
from custom_components.f1_sensor.replay_mode import (
    ReplayFrame,
    ReplaySessionManager,
    ReplayState,
)


@pytest.fixture
async def runtime(hass):
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    object.__setattr__(
        entry, "state", config_entries.ConfigEntryState.SETUP_IN_PROGRESS
    )
    session = {"Key": 11404, "Type": "Race", "Name": "Race", "Meeting": {"Key": 1298}}
    coordinator = LiveDriversCoordinator(
        hass, SimpleNamespace(data={}), config_entry=entry
    )
    data = {
        "drivers_coordinator": coordinator,
        "session_info_coordinator": SimpleNamespace(data=session),
        "live_state": SimpleNamespace(
            is_live=True, reason="replay", replay_generation=1
        ),
        "replay_controller": SimpleNamespace(
            replay_active=True,
            active_session_id="2026_1298_11404",
            state=ReplayState.PLAYING,
        ),
    }
    hass.data[DOMAIN] = {
        "no_spoiler_manager": NoSpoilerModeManager(hass),
        entry.entry_id: data,
    }
    coordinator._on_sessioninfo(session)
    coordinator._merge_driverlist(
        {"12": {"RacingNumber": "12", "Tla": "ANT", "Line": 8}}
    )
    coordinator._merge_timingdata(
        {"Lines": {"12": {"Position": "1", "NumberOfLaps": 12}}}
    )
    coordinator._deliver()
    store = CardDataStore(hass, entry, data)
    yield coordinator, store, data
    await store.async_close()
    await coordinator.async_close()


def reference(store):
    snapshot = store.snapshot("driver_positions")
    assert snapshot["status"] == "ready"
    return snapshot["payload"]["attributes"]["starting_grid_reference"]


async def test_only_explicit_gridpos_can_establish_the_modular_reference(runtime):
    coordinator, store, _ = runtime
    assert reference(store) is None
    coordinator._on_driver_race_info({"12": {"Position": "7"}})
    coordinator._on_lap_history(
        {"12": {"grid_position": "6", "laps": {}, "last_recorded_lap": 0}}
    )
    coordinator._merge_timingapp({"Lines": {"12": {"Line": 2}}})
    assert reference(store) is None
    coordinator._merge_timingapp({"Lines": {"12": {"GridPos": "4"}}})
    assert reference(store) == {
        "source": "TimingAppData.GridPos",
        "session_key": "11404",
        "grid": [{"racing_number": "12", "grid_position": 4}],
    }


async def test_seek_backfill_adds_reference_without_changing_existing_payloads(
    runtime, hass
):
    coordinator, store, data = runtime
    model = DriverPositionsModel(coordinator, None, store.entry.entry_id, None)
    model.hass = hass
    before = model.snapshot()
    history = deepcopy(coordinator._state["drivers"]["12"]["lap_history"])
    # Seek reconstruction injects completed LapHistory before TimingAppData.
    assert history["completed_laps"] == 12
    assert coordinator._merge_timingapp({"Lines": {"12": {"GridPos": "4"}}}) is False
    assert coordinator._state["drivers"]["12"]["lap_history"] == history
    assert model.snapshot() == before
    snapshot = store.snapshot("driver_positions")
    attributes = snapshot["payload"]["attributes"]
    assert attributes.pop("starting_grid_reference")["grid"][0]["grid_position"] == 4
    assert attributes == before.attributes
    assert snapshot["source"] == "replay"
    assert (
        snapshot["context"]["session_id"] == data["replay_controller"].active_session_id
    )
    assert snapshot["generation"] == store.generation


@pytest.mark.parametrize(
    "value", [True, False, -1, 4.5, 4.0, "4.9", "unknown", "", None]
)
async def test_non_integer_gridpos_never_confirms_a_reference(runtime, value):
    coordinator, store, _ = runtime
    coordinator._merge_timingapp({"Lines": {"12": {"GridPos": value}}})
    assert reference(store) is None


async def test_partial_updates_pitlane_and_ambiguous_slots_remain_explicit(runtime):
    coordinator, store, _ = runtime
    coordinator._merge_timingapp(
        {"Lines": {"12": {"GridPos": 4}, "3": {"GridPos": 5}, "30": {"GridPos": 0}}}
    )
    coordinator._merge_timingapp({"Lines": {"12": {"Line": 1}, "3": {"Line": 2}}})
    grid = reference(store)["grid"]
    assert {row["racing_number"]: row["grid_position"] for row in grid} == {
        "12": 4,
        "3": 5,
        "30": 0,
    }
    coordinator._merge_timingapp({"Lines": {"3": {"GridPos": 4}}})
    assert reference(store) is None
    coordinator._merge_timingapp({"Lines": {"3": {"GridPos": 5}}})
    assert reference(store)["grid"] == grid
    coordinator._merge_timingapp({"Lines": {"12": {"GridPos": None}}})
    assert all(row["racing_number"] != "12" for row in reference(store)["grid"])


async def test_roster_updates_preserve_gridpos_without_promoting_new_line_values(
    runtime,
):
    coordinator, store, _ = runtime
    coordinator._merge_timingapp({"Lines": {"12": {"GridPos": "4"}}})
    confirmed = reference(store)
    generation = store.generation
    coordinator._on_driverlist(
        {
            "12": {"RacingNumber": "12", "Tla": "ANT", "Line": 1},
            "99": {"RacingNumber": "99", "Tla": "NEW", "Line": 4},
        }
    )
    assert reference(store) == confirmed
    assert store.generation == generation


async def test_session_and_replay_resets_require_new_feed_evidence(runtime):
    coordinator, store, data = runtime
    coordinator._merge_timingapp({"Lines": {"12": {"GridPos": "4"}}})
    old_generation = store.snapshot("driver_positions")["generation"]
    coordinator.reset_for_replay()
    store.reset_for_replay()
    coordinator._on_sessioninfo(data["session_info_coordinator"].data)
    coordinator._merge_driverlist({"12": {"Line": 8}})
    coordinator._merge_timingdata({"Lines": {"12": {"Position": "1"}}})
    coordinator._deliver()
    store._coordinator_changed("drivers_coordinator")
    assert reference(store) is None
    assert store.snapshot("driver_positions")["generation"] != old_generation
    coordinator._merge_timingapp({"Lines": {"12": {"GridPos": "4"}}})
    assert reference(store)["session_key"] == "11404"
    data["session_info_coordinator"].data = {
        "Key": 11405,
        "Type": "Race",
        "Name": "Race",
    }
    coordinator._on_sessioninfo(data["session_info_coordinator"].data)
    assert coordinator.modular_starting_grid_reference is None


async def test_unknown_or_mismatched_session_cannot_relabel_old_gridpos(runtime):
    coordinator, store, data = runtime
    coordinator.reset_for_replay()
    coordinator._merge_timingapp({"Lines": {"12": {"GridPos": "4"}}})
    assert coordinator.modular_starting_grid_reference is None
    coordinator._on_sessioninfo(data["session_info_coordinator"].data)
    assert coordinator.modular_starting_grid_reference is None
    coordinator._merge_timingapp({"Lines": {"12": {"GridPos": "4"}}})
    assert reference(store)["session_key"] == "11404"
    data["session_info_coordinator"].data = {"Key": 11405}
    # The new current-session projection arrived before the driver coordinator.
    assert reference(store) is None


async def test_grid_reference_obeys_the_existing_delayed_ingest_queue(
    runtime, monkeypatch
):
    coordinator, store, _ = runtime
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
    coordinator.set_delay(30)
    receive = f1._wrap_delayed_handler(coordinator, coordinator._on_timingapp)
    receive({"Lines": {"12": {"GridPos": "4"}}})
    assert reference(store) is None
    clock.value += 29.9
    f1._drain_delayed_ingest_queue(coordinator)
    assert reference(store) is None
    clock.value += 0.1
    f1._drain_delayed_ingest_queue(coordinator)
    assert reference(store)["grid"] == [{"racing_number": "12", "grid_position": 4}]
    coordinator.set_delay(60)
    assert reference(store) is None


async def test_real_seek_checkpoint_restores_only_its_explicit_gridpos(runtime, hass):
    coordinator, store, data = runtime
    manager = ReplaySessionManager(hass, store.entry.entry_id, AsyncMock())
    accumulator = manager._new_seek_checkpoint_accumulator()
    manager._accumulate_seek_checkpoint_frame(
        accumulator,
        ReplayFrame(0, "SessionInfo", data["session_info_coordinator"].data),
    )
    manager._accumulate_seek_checkpoint_frame(
        accumulator, ReplayFrame(1, "DriverList", {"12": {"Line": 8}})
    )
    early = manager._seek_checkpoint_state(accumulator)
    manager._accumulate_seek_checkpoint_frame(
        accumulator,
        ReplayFrame(2, "TimingAppData", {"Lines": {"12": {"GridPos": "4"}}}),
    )
    manager._accumulate_seek_checkpoint_frame(
        accumulator,
        ReplayFrame(
            3000,
            "TimingData",
            {
                "Lines": {
                    "12": {
                        "Position": "1",
                        "NumberOfLaps": 12,
                        "LastLapTime": {"Value": "1:21.500"},
                    }
                }
            },
        ),
    )
    later = manager._seek_checkpoint_state(accumulator)
    for checkpoint in [later, early]:
        coordinator.reset_for_replay()
        coordinator._on_sessioninfo(checkpoint["SessionInfo"])
        coordinator._on_lap_history(checkpoint.get("LapHistory", {}))
        coordinator._on_driverlist(checkpoint.get("DriverList", {}))
        coordinator._on_timingapp(checkpoint.get("TimingAppData", {}))
        coordinator._on_timingdata(checkpoint.get("TimingData", {}))
        if checkpoint is later:
            assert reference(store)["grid"][0]["grid_position"] == 4
            assert (
                coordinator._state["drivers"]["12"]["lap_history"]["grid_position"]
                == "8"
            )
        else:
            assert reference(store) is None


@pytest.mark.parametrize("reason", ["window-ended", "no-spoiler", "replay"])
async def test_source_boundaries_retire_the_private_reference(runtime, reason):
    coordinator, store, _ = runtime
    coordinator._merge_timingapp({"Lines": {"12": {"GridPos": "4"}}})
    assert reference(store) is not None
    coordinator._handle_live_state(reason == "replay", reason)
    assert coordinator.modular_starting_grid_reference is None


async def test_blocked_payload_never_exposes_private_grid_evidence(runtime, hass):
    coordinator, store, _ = runtime
    coordinator._merge_timingapp({"Lines": {"12": {"GridPos": "4"}}})
    assert reference(store) is not None
    await hass.data[DOMAIN]["no_spoiler_manager"].async_set_active(True)
    assert store.snapshot("driver_positions")["payload"] is None
