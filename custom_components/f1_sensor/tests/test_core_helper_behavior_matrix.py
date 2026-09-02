"""Behavior matrix for integration-level race-control and delay helpers."""

from __future__ import annotations

from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.f1_sensor import (
    RaceControlLogStore,
    _apply_delay_handles_only,
    _apply_delay_simple,
    _apply_delay_with_handles,
    _apply_delay_with_queue,
    _cancel_handle,
    _cancel_handles,
    _close_stream_delay_state,
    _close_unsubs,
    _compute_session_fingerprint,
    _format_race_control_state,
    _init_stream_delay_state,
    _is_replay_delay_reason,
    _is_replay_only_active_reason,
    _normalize_race_control_log_item,
    _normalize_race_control_timestamp,
    _normalize_stored_race_control_log_item,
    _queue_delayed_ingest,
    _rc_cleanup_string,
    _refresh_session_fingerprint,
    _resolve_race_control_session_label,
    _schedule_deliver_handle,
    _seed_driver_map_from_ergast,
    _wrap_delayed_handler,
)
from custom_components.f1_sensor.const import DOMAIN


def test_race_control_normalization_and_session_labels() -> None:
    assert _is_replay_delay_reason("replay") is True
    assert _is_replay_delay_reason(None) is False
    assert _is_replay_only_active_reason("replay-mode") is True
    assert _rc_cleanup_string(None) is None
    assert _rc_cleanup_string("  ") is None
    assert _rc_cleanup_string("abcdef", max_chars=3) == "abc"
    assert _normalize_race_control_timestamp(None) is None
    assert _normalize_race_control_timestamp("bad") == "bad"
    assert _normalize_race_control_timestamp("2026-09-01T12:00:00") == (
        "2026-09-01T12:00:00+00:00"
    )
    assert _format_race_control_state({"Message": " message "}) == "message"
    assert _format_race_control_state({"Flag": "RED", "Sector": 2}) == "RED - 2"
    assert _format_race_control_state({}) == "Race control update"

    item = _normalize_race_control_log_item(
        {
            "utc": "2026-09-01T12:00:00Z",
            "CategoryType": "Flag",
            "Flag": "RED",
            "TrackSegment": 3,
            "Driver": 4,
            "Text": "Stop",
        },
        received_at="received",
        sequence=2,
    )
    assert item["message"] == "Stop"
    assert item["car_number"] == "4"
    restored = _normalize_stored_race_control_log_item(
        {**item, "event_id": "x" * 100, "sequence": "bad"}
    )
    assert len(restored["event_id"]) == 40
    assert restored["sequence"] is None
    assert _normalize_stored_race_control_log_item({})["message"] == (
        "Race control update"
    )

    assert _resolve_race_control_session_label({"Type": "Practice", "Number": 2}) == (
        "Practice 2"
    )
    assert (
        _resolve_race_control_session_label(
            {"Type": "Practice", "Number": "bad", "Name": "Practice"}
        )
        == "Practice"
    )
    assert (
        _resolve_race_control_session_label(
            {"Type": "Qualifying", "Name": "Sprint Shootout"}
        )
        == "Sprint Qualifying"
    )
    assert (
        _resolve_race_control_session_label({"Type": "Race", "Name": "Sprint"})
        == "Sprint"
    )
    assert (
        _resolve_race_control_session_label(
            {"Type": "Race", "Name": "Sprint Qualifying"}
        )
        == "Sprint Qualifying"
    )
    assert _resolve_race_control_session_label({"Type": "Race"}) == "Race"
    assert _resolve_race_control_session_label({}) is None


@pytest.mark.asyncio
async def test_race_control_log_store_restore_append_session_and_close(hass) -> None:
    info = SimpleNamespace(
        data={
            "Type": "Race",
            "Name": "Race",
            "StartDate": "2026-09-01T12:00:00Z",
            "Meeting": {"Key": 1},
        },
        async_add_listener=Mock(return_value=Mock()),
    )
    status = SimpleNamespace(
        data={"Status": "Started"}, async_add_listener=Mock(return_value=Mock())
    )
    store = RaceControlLogStore(
        hass,
        "entry",
        session_info_coordinator=info,
        session_status_coordinator=status,
    )
    store._store = SimpleNamespace(
        async_load=AsyncMock(
            return_value={
                "session_key": "old",
                "items": [
                    "bad",
                    {
                        "event_id": "event",
                        "message": "Stored",
                        "sequence": "bad",
                    },
                    {"message": "Newer", "sequence": 4},
                ],
            }
        ),
        async_save=AsyncMock(),
    )
    await store.async_initialize()
    assert store.session_key.endswith("Race")
    assert len(store.get_items()) == 0
    appended = store.append({"Message": "GREEN FLAG"}, received_at="received")
    assert appended["sequence"] == 1
    assert store.append({"Message": "GREEN FLAG"}) is None
    assert store.get_items(0) == []
    assert store._is_session_active() is True

    info.data["StartDate"] = "2026-09-02T12:00:00Z"
    store._handle_session_context_update()
    assert store.get_items() == []
    store.clear_for_source_stop(reason="init")
    store.clear_for_source_stop(reason="offline")
    await hass.async_block_till_done()
    await store.async_close()
    assert store._save_task is None


@pytest.mark.asyncio
async def test_schedule_cancel_and_delay_helpers(hass) -> None:
    called = []
    handle = _schedule_deliver_handle(hass.loop, None, 0, lambda: called.append(1))
    assert handle is not None
    handle = _cancel_handle(handle)
    assert handle is None
    prior = Mock()
    replacement = _schedule_deliver_handle(hass.loop, prior, 10, Mock())
    prior.cancel.assert_called_once()
    assert replacement is not None
    replacement.cancel()

    unsubs = [Mock(), Mock(side_effect=RuntimeError("unsubscribe"))]
    _close_unsubs(unsubs)
    assert unsubs == []
    handles = [Mock(), Mock(side_effect=RuntimeError("cancel"))]
    _cancel_handles(handles)
    assert handles == []

    instance = SimpleNamespace(
        hass=hass,
        _delay=0,
        _deliver_handle=Mock(),
        set_delay=Mock(),
        _handle_live_state=Mock(),
    )
    delay_controller = SimpleNamespace(add_listener=Mock(return_value=Mock()))
    live_state = SimpleNamespace(add_listener=Mock(return_value=Mock()))
    _init_stream_delay_state(
        instance,
        1,
        bus=Mock(),
        delay_controller=delay_controller,
        live_state=live_state,
    )
    assert instance._delay == 1
    _apply_delay_simple(instance, 2)
    assert instance._delay == 2
    queued = []
    instance._delay = 0
    _queue_delayed_ingest(instance, lambda: queued.append("direct"))
    await hass.async_block_till_done()
    assert queued == ["direct"]
    wrapped = _wrap_delayed_handler(instance, queued.append)
    wrapped("wrapped")
    await hass.async_block_till_done()
    assert queued[-1] == "wrapped"

    instance._delay_queue = deque([(0.0, lambda: queued.append("queued"))])
    instance._delay = 1
    _apply_delay_with_queue(instance, 0)
    assert queued[-1] == "queued"
    _apply_delay_with_queue(instance, 0)
    _apply_delay_handles_only(instance, 3, [])
    assert instance._delay == 3
    instance._deliver_handle = Mock()
    _apply_delay_with_handles(instance, 4, [])
    assert instance._delay == 4
    _close_stream_delay_state(instance)


def test_session_fingerprint_and_ergast_driver_map_seed(hass) -> None:
    assert _compute_session_fingerprint(None) is None
    first = {"Meetings": [{"Key": 1}], "Sessions": []}
    fp = _compute_session_fingerprint(first)
    assert _refresh_session_fingerprint(None, first) == (fp, False)
    assert _refresh_session_fingerprint(fp, first) == (fp, False)
    changed_fp, changed = _refresh_session_fingerprint(fp, {"Meetings": [{"Key": 2}]})
    assert changed is True
    assert changed_fp != fp

    entry = SimpleNamespace(entry_id="entry")
    driver_coord = SimpleNamespace(
        data={
            "MRData": {
                "StandingsTable": {
                    "StandingsLists": [
                        {
                            "DriverStandings": [
                                "bad",
                                {"Driver": "bad"},
                                {"Driver": {"permanentNumber": "bad"}},
                                {
                                    "Driver": {
                                        "permanentNumber": "004",
                                        "code": "NOR",
                                        "givenName": "Lando",
                                        "familyName": "Norris",
                                    },
                                    "Constructors": [{"name": "McLaren"}],
                                },
                                {
                                    "Driver": {
                                        "permanentNumber": "81",
                                        "driverId": "piastri",
                                    },
                                    "Constructors": "bad",
                                },
                            ]
                        }
                    ]
                }
            }
        }
    )
    hass.data.setdefault(DOMAIN, {})["entry"] = {"driver_coordinator": driver_coord}
    driver_map = {"4": {}}
    _seed_driver_map_from_ergast(hass, entry, driver_map)
    assert driver_map["4"] == {
        "tla": "NOR",
        "name": "Lando Norris",
        "team": "McLaren",
    }
    assert driver_map["81"]["tla"] == "piastri"
    _seed_driver_map_from_ergast(hass, None, driver_map)
