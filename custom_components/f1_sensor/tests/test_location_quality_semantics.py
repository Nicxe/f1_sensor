"""Geometry thirds are approximate context, never official timing sectors."""

from datetime import timedelta

import pytest

from custom_components.f1_sensor import track_map
from custom_components.f1_sensor.tests.test_track_map_store import (
    BASE_TIME,
    _position,
    _static_session_payload,
)
from custom_components.f1_sensor.track_map import (
    TrackGeometry,
    TrackMapBounds,
    TrackMapPosition,
    TrackMapStore,
    _position_geometry_context,
)
from custom_components.f1_sensor.track_map_annotation_contract import (
    load_annotation_catalog,
)
from custom_components.f1_sensor.track_map_websocket import _v2_map_snapshot


@pytest.mark.parametrize(
    ("season", "conflicting_layout", "has_annotations"),
    [
        (2022, True, False),
        (2025, False, True),
        (2026, False, True),
        (2027, False, False),
    ],
)
def test_same_circuit_key_is_not_a_historical_layout_identity(
    season, conflicting_layout, has_annotations
):
    store = TrackMapStore("entry-1", annotation_records=load_annotation_catalog())
    payload = _static_session_payload(circuit_key="61", short_name="Singapore")
    payload["Path"] = f"{season}/Singapore/Race/"
    payload["StartDate"] = f"{season}-10-01T20:00:00"
    store.update_session_info(payload)
    geometry = store.geometry
    assert geometry.circuit_key == "61"
    x, y = geometry.points[10]
    store.update_positions([_position("4", x=x, y=y)], source="live")
    context = store.location_context("4", now=BASE_TIME)
    assert context.sector in {1, 2, 3}  # The legacy alias keeps its path-third value.
    if conflicting_layout:
        assert context.approximate_track_third is None
        assert "track section" not in context.description
    else:
        assert context.approximate_track_third == context.sector
        assert "approximate track section" in context.description

    # Base geometry remains keyed by circuit. Only the separately reviewed
    # year/layout/fingerprint binding permits optional official annotations.
    wire = _v2_map_snapshot(store, store.snapshot(now=BASE_TIME), 1)
    assert bool(wire["annotations"]) is has_annotations


def test_catalog_without_layout_provenance_remains_approximate(monkeypatch):
    entry = dict(track_map.STATIC_TRACK_GEOMETRIES["61"])
    entry.pop("provenance")
    monkeypatch.setitem(track_map.STATIC_TRACK_GEOMETRIES, "61", entry)
    store = TrackMapStore("entry-1")
    store.update_session_info(
        _static_session_payload(circuit_key="61", short_name="Singapore")
    )
    x, y = store.geometry.points[10]
    store.update_positions([_position("4", x=x, y=y)], source="live")
    context = store.location_context("4", now=BASE_TIME)
    assert context.sector_basis == "geometry_third"
    assert "approximate track section" in context.description
    assert (
        _v2_map_snapshot(store, store.snapshot(now=BASE_TIME), 1)["annotations"] is None
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_closed_geometry_start_finish_is_ambiguous_in_either_direction(reverse):
    points = ((0, 0), (90, 0), (90, 90), (0, 90), (0, 0))
    geometry = TrackGeometry(
        points=tuple(reversed(points)) if reverse else points,
        bounds=TrackMapBounds(min_x=0, max_x=90, min_y=0, max_y=90),
        source="test",
    )
    position = TrackMapPosition(
        racing_number="4", timestamp=BASE_TIME, x=0, y=0, z=0, status="OnTrack"
    )
    context = _position_geometry_context(position, geometry)
    assert context["approximate_track_third"] is None
    assert context["sector_basis"] == "geometry_third"
    assert context["sector"] in {1, 3}  # Compatibility alias is not an official sector.


@pytest.mark.parametrize("reverse,expected", [(False, 1), (True, 3)])
def test_reversed_geometry_describes_path_thirds_not_official_timing(reverse, expected):
    points = ((0, 0), (90, 0))
    geometry = TrackGeometry(
        points=tuple(reversed(points)) if reverse else points,
        bounds=TrackMapBounds(min_x=0, max_x=90, min_y=0, max_y=0),
        source="test",
    )
    position = TrackMapPosition(
        racing_number="4", timestamp=BASE_TIME, x=15, y=0, z=0, status="OnTrack"
    )
    context = _position_geometry_context(position, geometry)
    assert context["approximate_track_third"] == expected
    assert context["sector_basis"] == "geometry_third"


def test_mismatched_geometry_does_not_describe_an_approximate_track_third():
    store = TrackMapStore("entry-1")
    store.update_session_info(_static_session_payload())
    store.set_geometry(
        TrackGeometry(
            points=((0, 0), (90, 0)),
            bounds=TrackMapBounds(min_x=0, max_x=90, min_y=0, max_y=0),
            source="test",
            circuit_key="a-different-circuit",
        )
    )
    store.update_positions([_position("4", x=15, y=0)], source="live")
    context = store.location_context("4", now=BASE_TIME)
    assert context.approximate_track_third is None
    assert "track section" not in context.description
    assert context.sector == 1  # Preserve the existing automation alias.


@pytest.mark.parametrize(
    ("x", "third"), [(0, 1), (29, 1), (30, 2), (59, 2), (60, 3), (90, 3)]
)
def test_geometry_thirds_have_explicit_basis_at_boundaries(x, third):
    geometry = TrackGeometry(
        points=((0, 0), (90, 0)),
        bounds=TrackMapBounds(min_x=0, max_x=90, min_y=0, max_y=0),
        source="test",
    )
    position = TrackMapPosition(
        racing_number="4", timestamp=BASE_TIME, x=x, y=0, z=0, status="OnTrack"
    )
    context = _position_geometry_context(position, geometry)
    assert context["approximate_track_third"] == third
    assert context["sector_basis"] == "geometry_third"
    assert context["sector"] == third  # Legacy alias retains its existing meaning.


def test_equidistant_geometry_sections_withhold_approximate_third():
    geometry = TrackGeometry(
        points=((0, 0), (90, 0), (90, 10), (0, 10)),
        bounds=TrackMapBounds(min_x=0, max_x=90, min_y=0, max_y=10),
        source="test",
    )
    position = TrackMapPosition(
        racing_number="4", timestamp=BASE_TIME, x=45, y=5, z=0, status="OnTrack"
    )
    context = _position_geometry_context(position, geometry)
    assert context["sector"] == 1
    assert context["approximate_track_third"] is None
    assert context["sector_basis"] == "geometry_third"


@pytest.mark.parametrize("status", ["OnTrack", "OffTrack", "PitLane"])
def test_location_description_uses_approximate_context_and_suppresses_stale_third(
    status,
):
    store = TrackMapStore("entry-1", stale_after=timedelta(seconds=5))
    store.update_session_info(_static_session_payload())
    store.update_positions([_position("16", status=status)], source="live")
    context = store.location_context("16", now=BASE_TIME)
    assert context is not None
    assert context.as_dict()["sector_basis"] == "geometry_third"
    assert ", sector " not in context.description
    if status == "PitLane":
        assert context.approximate_track_third is None
        assert context.description == "pit lane"
    else:
        assert context.approximate_track_third == context.sector
        assert "approximate track section" in context.description
    stale = store.location_context("16", now=BASE_TIME + timedelta(seconds=6))
    assert stale.stale is True
    assert stale.approximate_track_third is None
    assert "track section" not in stale.description
