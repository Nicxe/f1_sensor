"""A completed lap needs explicit evidence before it is usable in Race Trace."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import LiveDriversCoordinator
from custom_components.f1_sensor.card_data import CardDataStore
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.lap_history import record_lap_time, update_lap_metadata
from custom_components.f1_sensor.live_data_models import DriverPositionsModel
from custom_components.f1_sensor.live_delay import LiveDelayController
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager
from custom_components.f1_sensor.signalr import timing_source_payload


@pytest.mark.parametrize("number", [2, "2", "02"])
def test_explicit_lap_time_pair_is_confirmed(number) -> None:
    history = {"laps": {}}
    assert update_lap_metadata(history, 2, "1:30.000", explicit_number=number) is True
    assert history["lap_metadata"] == {
        "2": {"association": "confirmed", "reason": None}
    }
    assert history["laps"] == {}


@pytest.mark.parametrize("number", [None, 0, -1, True, 2.5, "bad", "2.0"])
def test_missing_or_invalid_number_cannot_confirm_lap(number) -> None:
    history = {"laps": {}}
    update_lap_metadata(history, 2, "1:30.000", explicit_number=number)
    assert history["lap_metadata"]["2"] == {
        "association": "inferred",
        "reason": "missing_lap_number",
    }


def test_cached_number_and_merged_snapshot_are_not_explicit_pairs() -> None:
    history = {"laps": {}}
    update_lap_metadata(history, 2, "1:30.000", retained_number=True)
    assert history["lap_metadata"]["2"] == {
        "association": "inferred",
        "reason": "retained_lap_number",
    }
    update_lap_metadata(history, 2, "1:30.000", explicit_number=2, snapshot=True)
    assert history["lap_metadata"]["2"] == {
        "association": "ambiguous",
        "reason": "snapshot_unverified",
    }


def test_uncertain_correction_invalidates_previous_confirmation() -> None:
    history = {
        "laps": {"2": "1:30.000"},
        "lap_metadata": {"2": {"association": "confirmed", "reason": None}},
    }
    assert update_lap_metadata(history, 2, "1:31.000", retained_number=True) is True
    assert history["lap_metadata"]["2"] == {
        "association": "ambiguous",
        "reason": "ambiguous_correction",
    }
    history["laps"]["2"] = "1:31.000"
    assert update_lap_metadata(history, 2, "1:31.000", explicit_number=2) is True
    assert history["lap_metadata"]["2"] == {
        "association": "confirmed",
        "reason": None,
    }


def test_matching_snapshot_keeps_existing_confirmed_evidence_idempotently() -> None:
    history = {
        "laps": {"2": "1:30.000"},
        "lap_metadata": {"2": {"association": "confirmed", "reason": None}},
    }
    before = deepcopy(history)
    assert (
        update_lap_metadata(history, 2, "1:30.000", explicit_number=2, snapshot=True)
        is False
    )
    assert history == before


def test_same_time_on_different_explicit_laps_has_distinct_evidence() -> None:
    history = {"laps": {"2": "1:30.000"}}
    update_lap_metadata(history, 2, "1:30.000", explicit_number=2)
    update_lap_metadata(history, 3, "1:30.000", explicit_number=3)
    assert history["lap_metadata"] == {
        "2": {"association": "confirmed", "reason": None},
        "3": {"association": "confirmed", "reason": None},
    }


def test_shared_writer_preserves_legacy_inference_and_explicit_identical_laps():
    history = {"laps": {}, "last_recorded_lap": 0, "completed_laps": 0}
    assert record_lap_time(history, "1:30.000") == (1, True)
    assert history["completed_laps"] == 1
    assert history["lap_metadata"]["1"]["association"] == "inferred"
    assert record_lap_time(history, "1:30.000", 1) == (1, False)
    assert record_lap_time(history, "1:30.000", 2, explicit_number=2) == (2, True)
    assert history["laps"] == {"1": "1:30.000", "2": "1:30.000"}
    assert history["completed_laps"] == history["last_recorded_lap"] == 2
    assert history["lap_metadata"]["2"]["association"] == "confirmed"


@pytest.fixture
async def drivers(hass):
    coordinator = LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    yield coordinator
    await coordinator.async_close()


def _timing(number=None, time=None, *, snapshot=False):
    row = {}
    if number is not None:
        row["NumberOfLaps"] = number
    if time is not None:
        row["LastLapTime"] = {"Value": time}
    return {"Lines": {"4": row}, "_f1_snapshot": snapshot}


@pytest.mark.parametrize("first", ["number", "time"])
async def test_separate_count_and_time_do_not_claim_explicit_pair(drivers, first):
    drivers._merge_timingdata(_timing(1, "1:30.000"))
    frames = [_timing(2), _timing(time="1:31.000")]
    if first == "time":
        frames.reverse()
    for frame in frames:
        drivers._merge_timingdata(frame)
    history = drivers._state["drivers"]["4"]["lap_history"]
    if first == "number":
        assert history["laps"] == {"1": "1:30.000", "2": "1:31.000"}
        assert history["lap_metadata"]["2"] == {
            "association": "inferred",
            "reason": "retained_lap_number",
        }
    else:
        # Preserve the older chart's association, but do not certify it.
        assert history["laps"] == {"1": "1:31.000"}
        assert history["lap_metadata"]["1"] == {
            "association": "ambiguous",
            "reason": "ambiguous_correction",
        }
    drivers._merge_timingdata(_timing(2, "1:31.000"))
    assert history["lap_metadata"]["2"] == {"association": "confirmed", "reason": None}


async def test_live_identical_laps_and_explicit_correction_have_bound_metadata(drivers):
    for lap in (2, 3):
        drivers._merge_timingdata(_timing(lap, "1:30.000"))
    drivers._merge_timingdata(_timing(2, "1:31.000"))
    history = drivers._state["drivers"]["4"]["lap_history"]
    assert history["laps"] == {"2": "1:31.000", "3": "1:30.000"}
    assert history["completed_laps"] == 3
    drivers._merge_timingdata(_timing(1))
    assert history["completed_laps"] == 3
    assert history["lap_metadata"] == {
        "2": {"association": "confirmed", "reason": None},
        "3": {"association": "confirmed", "reason": None},
    }


@pytest.mark.parametrize("stream", ["timing", "app"])
async def test_raw_pairs_and_initial_snapshots_keep_distinct_evidence(drivers, stream):
    if stream == "timing":
        merge = drivers._merge_timingdata
        frame = _timing(12, "1:30.000", snapshot=True)
    else:
        merge = drivers._merge_timingapp
        frame = {
            "Lines": {"4": {"Stints": {"0": {"LapNumber": 12, "LapTime": "1:30.000"}}}},
            "_f1_snapshot": True,
        }
    merge(frame)
    history = drivers._state["drivers"]["4"]["lap_history"]
    assert history["lap_metadata"]["12"] == {
        "association": "ambiguous",
        "reason": "snapshot_unverified",
    }
    frame.pop("_f1_snapshot")
    assert merge(frame) is True
    assert history["lap_metadata"]["12"] == {"association": "confirmed", "reason": None}


async def test_missing_lap_number_keeps_legacy_time_but_labels_inference(drivers):
    drivers._merge_timingdata(_timing(time="1:30.000"))
    history = drivers._state["drivers"]["4"]["lap_history"]
    assert history["laps"] == {"1": "1:30.000"}
    assert history["completed_laps"] == 1
    assert history["lap_metadata"]["1"] == {
        "association": "inferred",
        "reason": "missing_lap_number",
    }


async def test_projection_uses_delivered_session_type_and_resets_metadata(
    hass, drivers
):
    model = DriverPositionsModel(drivers, None, "entry", None)
    model.hass = hass
    model._session_info_coordinator = SimpleNamespace(data={"Type": "Race"})
    drivers.async_set_updated_data(drivers._state)
    model._update_from_coordinator(initial=True)
    assert model._attr_extra_state_attributes["lap_history_version"] == 1
    assert model._attr_extra_state_attributes["lap_history_session_type"] is None
    drivers._on_sessioninfo({"Key": 123, "Type": "Race"})
    drivers._merge_timingdata(_timing(2, "1:30.000"))
    drivers._on_sessioninfo({"Name": "Race"})
    assert model._update_from_coordinator(initial=False)
    attrs = model._attr_extra_state_attributes
    assert attrs["lap_history_session_type"] == "Race"
    assert attrs["drivers"][0]["lap_metadata"]["2"]["association"] == "confirmed"
    drivers._on_sessioninfo({"Key": 124, "Type": "Qualifying"})
    model._update_from_coordinator(initial=False)
    assert model._attr_extra_state_attributes["drivers"][0]["lap_metadata"] == {}
    assert (
        model._attr_extra_state_attributes["lap_history_session_type"] == "Qualifying"
    )
    drivers.reset_for_replay()
    model._update_from_coordinator(initial=False)
    assert model._attr_extra_state_attributes["lap_history_session_type"] is None


async def test_restored_legacy_history_cannot_claim_current_generation(hass, drivers):
    model = DriverPositionsModel(drivers, None, "entry", None)
    model.hass = hass
    restored = model._normalize_restored_attributes(
        {
            "lap_history_version": 1,
            "lap_history_session_type": "Race",
            "drivers": [
                {
                    "racing_number": "4",
                    "laps": {"2": "1:30.000"},
                    "lap_metadata": {"2": {"association": "confirmed", "reason": None}},
                }
            ],
        }
    )
    assert restored["lap_history_session_type"] is None
    assert restored["drivers"][0]["laps"] == {"2": "1:30.000"}
    assert restored["drivers"][0]["lap_metadata"] == {}


async def test_transport_marks_timingapp_snapshot_before_live_ingestion(drivers):
    raw = {"Lines": {"4": {"Stints": {"0": {"LapNumber": 12, "LapTime": "1:30.000"}}}}}
    drivers._merge_timingapp(timing_source_payload("TimingAppData", raw, snapshot=True))
    assert drivers._state["drivers"]["4"]["lap_history"]["lap_metadata"]["12"] == {
        "association": "ambiguous",
        "reason": "snapshot_unverified",
    }
    assert "_f1_snapshot" not in raw
    assert timing_source_payload("TimingAppData", raw, source_time=12.0) == {
        **raw,
        "_f1_source_time": 12.0,
        "_f1_source_domain": "replay_offset",
    }


@pytest.mark.parametrize("start,end", [(0, 30), (30, 0), (30, 30)])
@pytest.mark.parametrize("owner_first", [False, True])
async def test_delay_context_cannot_republish_old_confirmed_laps(
    hass, drivers, start, end, owner_first
):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    delay = LiveDelayController(hass, entry.entry_id)
    delay._value = start
    delay._store.async_save = AsyncMock()
    drivers._delay = start
    drivers._on_sessioninfo({"Key": 123, "Type": "Race"})
    drivers._on_timingdata(_timing(2, "1:30.000"))
    drivers._on_timingdata(_timing(3, "1:31.000"))
    context = SimpleNamespace(
        data={"Key": 123, "Type": "Race"}, async_add_listener=lambda cb: lambda: None
    )
    tracker = LiveAvailabilityTracker()
    tracker.set_state(True, "live-Race")
    data = {
        "drivers_coordinator": drivers,
        "session_info_coordinator": context,
        "live_delay_controller": delay,
        "live_state": tracker,
        "live_bus": SimpleNamespace(last_stream_activity_age=lambda: 0),
    }
    hass.data[DOMAIN] = {
        entry.entry_id: data,
        "no_spoiler_manager": NoSpoilerModeManager(hass),
    }
    owner = CardDataStore(hass, entry, data)
    owner._storage.async_load = AsyncMock(return_value=None)
    owner._storage.async_save = AsyncMock()
    if not owner_first:
        remove_delay = delay.add_listener(drivers.set_delay)
    await owner.async_start()
    if owner_first:
        remove_delay = delay.add_listener(drivers.set_delay)
    messages = []
    unsubscribe = owner.subscribe(["driver_positions"], messages.append)
    before = owner.snapshot("driver_positions")
    assert (
        before["payload"]["attributes"]["drivers"][0]["lap_metadata"]["3"][
            "association"
        ]
        == "confirmed"
    )
    messages.clear()
    await delay.async_set_delay(end)
    after = owner.snapshot("driver_positions")
    history = drivers._state["drivers"]["4"]["lap_history"]
    assert history["laps"] == {"2": "1:30.000", "3": "1:31.000"}
    if start == end:
        assert after["generation"] == before["generation"]
        assert history["lap_metadata"]["3"]["association"] == "confirmed"
        assert messages == []
    else:
        assert after["generation"] != before["generation"]
        assert history["lap_metadata"] == {}
        for message in [*messages, after]:
            for driver in (
                (message.get("payload") or {}).get("attributes", {}).get("drivers", [])
            ):
                assert driver["lap_metadata"] == {}
        drivers._on_timingdata(_timing(2, "1:30.000"))
        current = owner.snapshot("driver_positions")["payload"]["attributes"][
            "drivers"
        ][0]
        assert current["lap_metadata"] == {
            "2": {"association": "confirmed", "reason": None}
        }
    unsubscribe()
    remove_delay()
    await owner.async_close()
    await delay.async_close()
