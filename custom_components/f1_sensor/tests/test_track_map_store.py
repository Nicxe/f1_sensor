from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.f1_sensor.track_map import (
    TRACK_MAP_FALLBACK_STATE_STATIC_CATALOG,
    TRACK_MAP_FALLBACK_STATE_WAITING_FOR_REPLAY_POSITION_Z,
    TRACK_MAP_STATIC_GEOMETRY_SOURCE,
    TRACK_MAP_STATUS_ACTIVE,
    TRACK_MAP_STATUS_CLOSED,
    TRACK_MAP_STATUS_NO_POSITION_DATA,
    TRACK_MAP_STATUS_STALE,
    TrackGeometry,
    TrackMapBounds,
    TrackMapPosition,
    TrackMapStore,
)
from custom_components.f1_sensor.track_map_static_geometry import (
    STATIC_TRACK_GEOMETRY_APPROVAL_VISUAL_APPROVED,
)

BASE_TIME = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)


def _session_payload(session_key: str = "101") -> dict:
    return {
        "Key": session_key,
        "Name": "Race",
        "Type": "Race",
        "Path": f"2026/Test/{session_key}",
        "Meeting": {
            "Key": "55",
            "Name": "Test Grand Prix",
            "Circuit": {
                "Key": "999",
                "ShortName": "Test Circuit",
            },
        },
    }


def _static_session_payload(
    *,
    circuit_key: str = "151",
    short_name: str = "Miami",
) -> dict:
    payload = _session_payload()
    payload["Meeting"]["Circuit"] = {
        "Key": circuit_key,
        "ShortName": short_name,
    }
    return payload


def _position(
    racing_number: str,
    *,
    seconds: int = 0,
    x: int = 100,
    y: int = 200,
    z: int | None = 0,
    status: str = "OnTrack",
) -> TrackMapPosition:
    return TrackMapPosition(
        racing_number=racing_number,
        timestamp=BASE_TIME + timedelta(seconds=seconds),
        x=x,
        y=y,
        z=z,
        status=status,
    )


def test_track_map_store_snapshot_uses_latest_position_and_metadata() -> None:
    store = TrackMapStore("entry-1")
    store.update_session_info(_session_payload())
    store.update_driver_list(
        {
            "1": {
                "RacingNumber": "1",
                "Tla": "VER",
                "FullName": "Max Verstappen",
                "BroadcastName": "M VERSTAPPEN",
                "TeamName": "Red Bull Racing",
                "TeamColour": "#3671C6",
            },
            "4": {
                "RacingNumber": "4",
                "Tla": "NOR",
                "FullName": "Lando Norris",
                "TeamName": "McLaren",
            },
        }
    )
    store.set_geometry(
        TrackGeometry(
            points=((0, 0), (100, 200)),
            bounds=TrackMapBounds(min_x=0, max_x=100, min_y=0, max_y=200),
            source="test",
            circuit_key="149",
        )
    )
    store.update_positions(
        [
            _position("1", seconds=0, x=100, y=200),
            _position("4", seconds=0, x=300, y=400),
        ],
        source="replay",
    )
    store.update_positions([_position("1", seconds=1, x=110, y=205)])

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=2))

    assert snapshot["status"] == TRACK_MAP_STATUS_ACTIVE
    assert snapshot["source"] == "replay"
    assert snapshot["session"]["session_key"] == "101"
    assert snapshot["track"]["bounds"]["max_y"] == 200
    assert snapshot["track"]["points"] == [[0, 0], [100, 200]]
    assert snapshot["drivers"][0]["racing_number"] == "1"
    assert snapshot["drivers"][0]["x"] == 110
    assert snapshot["drivers"][0]["y"] == 205
    assert snapshot["drivers"][0]["name"] == "Max Verstappen"
    assert snapshot["drivers"][0]["team_color"] == "3671C6"


def test_track_map_store_handles_missing_geometry_and_driver_metadata() -> None:
    store = TrackMapStore("entry-1")
    store.update_session_info(_session_payload())
    store.update_positions([_position("63")])

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=1))

    assert snapshot["status"] == TRACK_MAP_STATUS_ACTIVE
    assert snapshot["track"] is None
    assert snapshot["drivers"][0]["racing_number"] == "63"
    assert snapshot["drivers"][0]["name"] is None
    assert snapshot["drivers"][0]["team_name"] is None


def test_track_map_store_filters_position_entries_without_driver_metadata() -> None:
    store = TrackMapStore("entry-1")
    store.update_session_info(_session_payload())
    store.update_driver_list(
        {
            "10": {"RacingNumber": "10", "Tla": "GAS"},
            "27": {"RacingNumber": "27", "Tla": "HUL"},
        }
    )

    store.update_positions(
        [
            _position("10", x=100, y=200),
            _position("27", x=300, y=400),
            _position("242", x=0, y=0, status="OffTrack"),
            _position("243", x=500, y=600),
        ],
        source="replay",
    )

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=1))

    assert [driver["racing_number"] for driver in snapshot["drivers"]] == ["10", "27"]
    assert [driver["tla"] for driver in snapshot["drivers"]] == ["GAS", "HUL"]


def test_track_map_store_prunes_unknown_positions_when_driver_list_arrives() -> None:
    store = TrackMapStore("entry-1")
    store.update_session_info(_session_payload())
    store.update_positions([_position("243", x=500, y=600)], source="replay")

    store.update_driver_list({"10": {"RacingNumber": "10", "Tla": "GAS"}})

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=1))

    assert snapshot["status"] == TRACK_MAP_STATUS_NO_POSITION_DATA
    assert snapshot["drivers"] == []


def test_track_map_store_sets_static_geometry_from_known_session() -> None:
    store = TrackMapStore("entry-1")

    store.update_session_info(_static_session_payload())

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=1))
    diagnostics = store.diagnostics(now=BASE_TIME + timedelta(seconds=1))

    assert snapshot["status"] == TRACK_MAP_STATUS_NO_POSITION_DATA
    assert snapshot["track"]["source"] == TRACK_MAP_STATIC_GEOMETRY_SOURCE
    assert snapshot["track"]["circuit_key"] == "151"
    assert snapshot["track"]["rotation"] == 11.2
    assert snapshot["track"]["points"][0] == snapshot["track"]["points"][-1]
    assert diagnostics["geometry_source"] == TRACK_MAP_STATIC_GEOMETRY_SOURCE
    assert diagnostics["circuit_key"] == "151"
    assert diagnostics["circuit_id"] == "miami"
    assert diagnostics["point_count"] == len(snapshot["track"]["points"])
    assert diagnostics["rotation"] == 11.2
    assert diagnostics["approval_status"] == (
        STATIC_TRACK_GEOMETRY_APPROVAL_VISUAL_APPROVED
    )
    assert diagnostics["fallback_state"] == TRACK_MAP_FALLBACK_STATE_STATIC_CATALOG


def test_track_map_store_diagnostics_reports_pending_replay_fallback() -> None:
    store = TrackMapStore("entry-1")

    store.update_session_info(_session_payload())
    store.update_positions([_position("63", z=None)])

    diagnostics = store.diagnostics(now=BASE_TIME + timedelta(seconds=1))

    assert diagnostics["geometry_source"] is None
    assert diagnostics["circuit_key"] == "999"
    assert diagnostics["circuit_id"] is None
    assert diagnostics["point_count"] == 0
    assert diagnostics["rotation"] is None
    assert diagnostics["approval_status"] is None
    assert diagnostics["fallback_state"] == (
        TRACK_MAP_FALLBACK_STATE_WAITING_FOR_REPLAY_POSITION_Z
    )
    assert diagnostics["driver_count"] == 1


def test_track_map_store_reports_stale_snapshot_and_location_context() -> None:
    store = TrackMapStore("entry-1", stale_after=timedelta(seconds=5))
    store.update_session_info(_session_payload())
    store.update_positions([_position("16")], source="live")

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=6))
    location = store.location_context("16", now=BASE_TIME + timedelta(seconds=6))

    assert snapshot["status"] == TRACK_MAP_STATUS_STALE
    assert snapshot["stale"] is True
    assert snapshot["drivers"][0]["stale"] is True
    assert location is not None
    assert location.stale is True
    assert location.as_dict()["source"] == "live"
    assert location.confidence == "low"
    assert location.fallback_state == (
        TRACK_MAP_FALLBACK_STATE_WAITING_FOR_REPLAY_POSITION_Z
    )
    assert "x" in location.as_dict()


def test_track_map_store_does_not_stale_replay_positions() -> None:
    store = TrackMapStore("entry-1", stale_after=timedelta(seconds=5))
    store.update_session_info(_session_payload())
    store.update_positions([_position("16")], source="replay")
    store.update_replay_state("paused")

    snapshot = store.snapshot(now=BASE_TIME + timedelta(days=30))
    location = store.location_context("16", now=BASE_TIME + timedelta(days=30))

    assert snapshot["status"] == TRACK_MAP_STATUS_ACTIVE
    assert snapshot["replay_state"] == "paused"
    assert snapshot["stale"] is False
    assert snapshot["drivers"][0]["stale"] is False
    assert location is not None
    assert location.stale is False
    assert location.confidence == "medium"
    assert location.sector is None
    assert location.track_segment is None
    assert location.geometry_source is None


def test_track_map_location_context_includes_static_geometry_summary() -> None:
    store = TrackMapStore("entry-1")
    store.update_session_info(_static_session_payload())
    store.update_positions([_position("16")], source="replay")

    location = store.location_context("16", now=BASE_TIME)

    assert location is not None
    assert location.confidence == "high"
    assert location.sector in {1, 2, 3}
    assert location.track_segment is not None
    assert location.distance_to_track is not None
    assert location.geometry_source == TRACK_MAP_STATIC_GEOMETRY_SOURCE
    assert location.fallback_state == TRACK_MAP_FALLBACK_STATE_STATIC_CATALOG
    assert location.description is not None


def test_track_map_store_resets_session_bound_data_on_session_switch() -> None:
    store = TrackMapStore("entry-1")
    store.update_session_info(_session_payload("101"))
    store.update_driver_list({"1": {"RacingNumber": "1", "FullName": "Old Driver"}})
    store.set_geometry(
        TrackGeometry(
            points=((10, 10),),
            bounds=TrackMapBounds(min_x=10, max_x=10, min_y=10, max_y=10),
            source="test",
        )
    )
    store.update_positions([_position("1")])

    store.update_session_info(_session_payload("102"))
    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=1))

    assert snapshot["status"] == TRACK_MAP_STATUS_NO_POSITION_DATA
    assert snapshot["session"]["session_key"] == "102"
    assert snapshot["track"] is None
    assert snapshot["drivers"] == []
    assert store.location_context("1") is None


def test_track_map_store_keeps_offtrack_positions_visible() -> None:
    store = TrackMapStore("entry-1")
    store.update_session_info(_session_payload())
    store.update_positions(
        [_position("44", x=0, y=0, z=None, status="OffTrack")],
    )

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=1))

    assert snapshot["status"] == TRACK_MAP_STATUS_ACTIVE
    assert snapshot["drivers"][0]["racing_number"] == "44"
    assert snapshot["drivers"][0]["status"] == "OffTrack"
    assert snapshot["drivers"][0]["z"] is None


@pytest.mark.asyncio
async def test_track_map_store_async_close_clears_runtime_snapshot() -> None:
    store = TrackMapStore("entry-1")
    store.update_session_info(_session_payload())
    store.update_positions([_position("81")])

    await store.async_close()

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=1))
    assert snapshot["status"] == TRACK_MAP_STATUS_CLOSED
    assert snapshot["drivers"] == []
