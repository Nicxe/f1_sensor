"""Driver projections keep history ownership without repeating growing copies."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.f1_sensor.card_data import CardDataStore
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.live_data_models import DriverPositionsModel
from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager
from custom_components.f1_sensor.sensor import F1DriverPositionsSensor


def _projection(hass, model_type=DriverPositionsModel):
    history = {
        "laps": {str(lap): f"1:{20 + lap % 10:02d}.123" for lap in range(1, 71)},
        "lap_metadata": {
            str(lap): {"association": "confirmed", "reason": None}
            for lap in range(1, 71)
        },
        "completed_laps": 70,
    }
    coordinator = SimpleNamespace(
        hass=hass,
        available=True,
        last_update_success=True,
        data={
            "lap_current": 71,
            "lap_total": 71,
            "drivers": {
                "1": {
                    "identity": {"tla": "VER", "team_color": "123456"},
                    "timing": {"position": "1", "pit_out": False},
                    "lap_history": history,
                }
            },
        },
    )
    registry = {
        "live_state": SimpleNamespace(is_live=True, reason="live"),
        "live_bus": SimpleNamespace(last_stream_activity_age=lambda: 0),
        "session_info_coordinator": SimpleNamespace(data={"Type": "Race"}),
    }
    hass.data[DOMAIN] = {"entry": registry}
    model = model_type(coordinator, None, "entry", None)
    model.hass = hass
    return model, coordinator, registry


def test_driver_snapshot_projects_once(hass):
    """Reading one card snapshot does not calculate the same drivers twice."""
    model, _, _ = _projection(hass)
    model._update_from_coordinator = Mock(wraps=model._update_from_coordinator)

    assert model.snapshot().attributes["drivers"][0]["completed_laps"] == 70

    assert model._update_from_coordinator.call_count == 1


@pytest.mark.parametrize("drivers", [None, [], 0])
def test_snapshot_accepts_empty_partial_driver_payload(hass, drivers):
    """A missing driver map remains an empty feed rather than an exception."""
    model, coordinator, _ = _projection(hass)
    coordinator.data["drivers"] = drivers

    assert model.snapshot().attributes["drivers"] == []


def test_unchanged_history_keeps_owned_branches(hass):
    """Frequent gap updates reuse history rather than allocate every old lap."""
    model, coordinator, _ = _projection(hass)
    model.snapshot()
    previous = model.extra_state_attributes["drivers"][0]
    coordinator.data["drivers"]["1"]["timing"]["gap_to_leader"] = "+1.234"

    current = model.snapshot().attributes["drivers"][0]
    owned = model.extra_state_attributes["drivers"][0]

    assert current["gap_to_leader"] == "+1.234"
    assert owned["laps"] is previous["laps"]
    assert owned["lap_metadata"] is previous["lap_metadata"]
    assert owned["laps"] is not coordinator.data["drivers"]["1"]["lap_history"]["laps"]


def test_snapshot_history_isolated_from_sources_and_other_reads(hass):
    """Source corrections and a consumer's edits cannot rewrite older snapshots."""
    model, coordinator, _ = _projection(hass)
    first = model.snapshot()
    expected = deepcopy(first.attributes)
    source = coordinator.data["drivers"]["1"]["lap_history"]
    source["laps"]["1"] = "1:19.999"
    source["lap_metadata"]["1"]["association"] = "ambiguous"

    corrected = model.snapshot()
    assert first.attributes == expected
    assert corrected.attributes["drivers"][0]["laps"]["1"] == "1:19.999"
    assert (
        corrected.attributes["drivers"][0]["lap_metadata"]["1"]["association"]
        == "ambiguous"
    )
    corrected.attributes["drivers"][0]["lap_metadata"]["1"]["reason"] = "consumer"
    corrected.attributes["drivers"][0]["laps"].clear()

    reread = model.snapshot().attributes["drivers"][0]
    assert reread["laps"]["1"] == "1:19.999"
    assert reread["lap_metadata"]["1"]["reason"] is None
    assert source["lap_metadata"]["1"]["reason"] is None


def test_sensor_history_survives_source_correction_and_consumer_mutation(hass):
    """Shared sensor calculation also owns history, even with in-place deltas."""
    model, coordinator, _ = _projection(hass, F1DriverPositionsSensor)
    model._update_from_coordinator()
    previous = model.extra_state_attributes["drivers"][0]
    source = coordinator.data["drivers"]["1"]["lap_history"]
    source["laps"]["1"] = "1:19.999"
    source["lap_metadata"]["1"]["association"] = "ambiguous"
    model._update_from_coordinator()

    current = model.extra_state_attributes["drivers"][0]
    assert previous["laps"]["1"] == "1:21.123"
    assert previous["lap_metadata"]["1"]["association"] == "confirmed"
    assert current["laps"]["1"] == "1:19.999"
    current["lap_metadata"]["1"]["reason"] = "consumer"
    model._update_from_coordinator()
    assert (
        model.extra_state_attributes["drivers"][0]["lap_metadata"]["1"]["reason"]
        is None
    )
    assert source["lap_metadata"]["1"]["reason"] is None


def test_snapshot_refreshes_pit_expiry_and_context_without_driver_update(hass):
    """Copy reuse must not freeze time-dependent pit status or session gating."""
    model, coordinator, registry = _projection(hass)
    now = [100.0]
    derive_status = model._derive_driver_status
    model._derive_driver_status = lambda *args, **kwargs: derive_status(
        *args, now=now[0], **kwargs
    )
    coordinator.data["drivers"]["1"]["timing"]["pit_out"] = True
    coordinator.data["fastest_lap"] = {"racing_number": "1", "lap": 70}
    first = model.snapshot()
    assert first.attributes["drivers"][0]["status"] == "pit_out"
    assert first.attributes["fastest_lap"] is not None

    now[0] += 7
    registry["session_info_coordinator"].data["Type"] = "Practice"
    current = model.snapshot()
    assert current.attributes["drivers"][0]["status"] == "on_track"
    assert current.attributes["fastest_lap"] is None


def _card_store(hass):
    _, coordinator, registry = _projection(hass)
    registry["drivers_coordinator"] = coordinator
    registry["session_info_coordinator"].data["Key"] = "race"
    manager = NoSpoilerModeManager(hass)
    hass.data[DOMAIN]["no_spoiler_manager"] = manager
    for source in (coordinator, registry["session_info_coordinator"]):
        listeners = set()

        def add_listener(listener, listeners=listeners):
            listeners.add(listener)
            return lambda: listeners.discard(listener)

        source.async_add_listener = add_listener
    entry = SimpleNamespace(entry_id="entry", options={}, data={})
    return CardDataStore(hass, entry, registry), coordinator, registry, manager


async def test_card_owned_history_isolated_at_every_consumer_boundary(hass):
    """Internal copy reuse cannot alter old envelopes, storage or other clients."""
    owner, coordinator, _, _ = _card_store(hass)
    coordinator.modular_starting_grid_reference = {
        "session_key": "race",
        "drivers": [{"position": 1}],
    }
    first, second = [], []

    def mutating_listener(message):
        first.append(message)
        message["payload"]["attributes"]["drivers"][0]["laps"].clear()
        message["payload"]["attributes"]["drivers"][0]["lap_metadata"]["1"][
            "reason"
        ] = "consumer"

    stop_first = owner.subscribe(["driver_positions"], mutating_listener)
    stop_second = owner.subscribe(["driver_positions"], second.append)
    try:
        owner._publish("driver_positions")
        previous = second[-1]
        persisted = owner._persisted["driver_positions"]
        expected_previous, expected_persisted = deepcopy(previous), deepcopy(persisted)
        source = coordinator.data["drivers"]["1"]["lap_history"]
        source["laps"]["1"] = "1:19.999"
        source["lap_metadata"]["1"]["association"] = "ambiguous"
        coordinator.modular_starting_grid_reference["drivers"][0]["position"] = 2
        owner._publish("driver_positions")

        assert previous == expected_previous
        assert persisted == expected_persisted
        current = second[-1]["payload"]["attributes"]
        assert current["drivers"][0]["laps"]["1"] == "1:19.999"
        assert current["drivers"][0]["lap_metadata"]["1"]["reason"] is None
        assert current["starting_grid_reference"]["drivers"][0]["position"] == 2
        public = owner.snapshot("driver_positions")
        public["payload"]["attributes"]["drivers"].clear()
        assert owner.snapshot("driver_positions")["payload"]["attributes"]["drivers"]
        assert source["lap_metadata"]["1"]["reason"] is None
    finally:
        stop_first()
        stop_second()
        await owner.async_close()


async def test_card_owned_history_still_obeys_privacy_and_session_reset(hass):
    """A cached history never bypasses no-spoiler or a new session generation."""
    owner, _, registry, manager = _card_store(hass)
    try:
        first = owner.snapshot("driver_positions")
        assert first["status"] == "ready"
        await manager.async_set_active(True)
        assert owner.snapshot("driver_positions")["payload"] is None
        await manager.async_set_active(False)
        assert owner.snapshot("driver_positions")["status"] == "ready"
        registry["session_info_coordinator"].data["Key"] = "next-race"
        changed = owner.snapshot("driver_positions")
        assert changed["generation"] != first["generation"]
        assert changed["reason"] == "waiting_for_current_context"
        assert changed["payload"] is None
    finally:
        await owner.async_close()


@pytest.mark.parametrize("model_type", [DriverPositionsModel, F1DriverPositionsSensor])
def test_history_rebuilds_backwards_and_evicts_removed_drivers(hass, model_type):
    """A reused projection cannot retain future laps after seeking backwards."""
    model, coordinator, _ = _projection(hass, model_type)

    def read():
        if isinstance(model, DriverPositionsModel):
            return model.snapshot().attributes
        model._update_from_coordinator()
        return deepcopy(model.extra_state_attributes)

    initial = read()
    source = coordinator.data["drivers"]["1"]["lap_history"]
    for completed in (20, 1):
        for name in ("laps", "lap_metadata"):
            retained = {
                lap: value
                for lap, value in source[name].items()
                if int(lap) <= completed
            }
            source[name].clear()
            source[name].update(retained)
        source["completed_laps"] = completed
        coordinator.data["lap_current"] = completed + 1
        current = read()["drivers"][0]
        assert current["completed_laps"] == completed
        assert set(current["laps"]) == {str(lap) for lap in range(1, completed + 1)}
        assert set(current["lap_metadata"]) == set(current["laps"])

    assert len(initial["drivers"][0]["laps"]) == 70
    assert len(initial["drivers"][0]["lap_metadata"]) == 70
    drivers = coordinator.data["drivers"]
    returning = drivers.pop("1")
    drivers["2"] = deepcopy(returning)
    assert {driver["racing_number"] for driver in read()["drivers"]} == {"2"}
    assert "1" not in model._driver_history_cache

    returning["lap_history"] = {"laps": {}, "lap_metadata": {}, "completed_laps": 0}
    drivers["1"] = returning
    current = next(
        driver for driver in read()["drivers"] if driver["racing_number"] == "1"
    )
    assert current["completed_laps"] == 0
    assert current["laps"] == current["lap_metadata"] == {}
