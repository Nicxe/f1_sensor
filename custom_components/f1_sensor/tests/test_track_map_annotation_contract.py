"""Network-free identity gates for future track map annotations."""

from copy import deepcopy

import pytest

from custom_components.f1_sensor.track_map_annotation_contract import (
    annotation_binding_matches,
    annotation_context,
    bind_annotation_layers,
    geometry_fingerprint,
)


@pytest.fixture
def singapore_session() -> dict:
    """Return a minimal 2025 SessionInfo snapshot."""
    return {
        "session_key": "9896",
        "circuit_key": "61",
        "path": "2025/2025-10-05_Singapore_Grand_Prix/2025-10-05_Race/",
        "start_date": "2025-10-05T20:00:00",
    }


@pytest.fixture
def singapore_track() -> dict:
    """Return a deliberately small raw geometry fixture, not product data."""
    return {
        "circuit_key": "61",
        "rotation": 0.2,
        "points": [[0, 0], [100, 0], [100, 100], [0, 0]],
    }


@pytest.fixture
def singapore_context(singapore_session: dict, singapore_track: dict):
    """Bind the pilot fixture to one replay generation."""
    return annotation_context(
        entry_id="entry-a",
        session=singapore_session,
        track=singapore_track,
        source="replay",
        session_generation=1,
        replay_year=2025,
    )


@pytest.fixture
def corner_record(singapore_context) -> dict:
    """Return a reviewed-looking sample without a real circuit anchor."""
    return {
        "schema_version": 1,
        "layer": "corners",
        "circuit_key": "61",
        "layout_key": "marina_bay_post_2023",
        "valid_from_season": 2025,
        "valid_to_season": 2025,
        "geometry_fingerprint": singapore_context.geometry_fingerprint,
        "qa_status": "verified",
        "rights_status": "cleared",
        "source": {
            "url": "https://example.test/singapore-map",
            "checked_on": "2026-10-09",
        },
        "items": [
            {
                "id": "turn_1",
                "kind": "point",
                "anchor": [100, 0],
                "label": "1",
                "label_offset": [2, -2],
            }
        ],
    }


def test_pilot_context_requires_explicit_layout_and_stable_geometry(
    singapore_session: dict, singapore_track: dict, singapore_context
) -> None:
    assert singapore_context is not None
    assert singapore_context.layout_key == "marina_bay_post_2023"
    assert singapore_context.season == 2025
    assert singapore_context.geometry_fingerprint == geometry_fingerprint(
        deepcopy(singapore_track)
    )
    assert singapore_context.geometry_fingerprint != geometry_fingerprint(
        {**singapore_track, "rotation": 1}
    )
    live = annotation_context(
        entry_id="entry-a",
        session=singapore_session,
        track=singapore_track,
        source="live",
        session_generation=1,
    )
    assert live is not None
    assert live.source == "live"
    assert live.geometry_fingerprint == singapore_context.geometry_fingerprint
    assert live != singapore_context


@pytest.mark.parametrize(
    ("session_patch", "track_patch", "replay_year"),
    [
        ({"circuit_key": "2"}, {}, 2025),
        ({"path": "2027/singapore/race/", "start_date": "2027-10-09"}, {}, 2027),
        ({"path": "2022/singapore/race/", "start_date": "2025-10-05"}, {}, 2022),
        ({"path": "unknown"}, {}, 2025),
        ({"session_key": None}, {}, 2025),
        ({}, {"circuit_key": "2"}, 2025),
        ({}, {"points": [[0, 0]]}, 2025),
        ({}, {}, 2022),
    ],
)
def test_unknown_or_inconsistent_identity_has_no_context(
    singapore_session: dict,
    singapore_track: dict,
    session_patch: dict,
    track_patch: dict,
    replay_year: int,
) -> None:
    assert (
        annotation_context(
            entry_id="entry-a",
            session={**singapore_session, **session_patch},
            track={**singapore_track, **track_patch},
            source="replay",
            session_generation=1,
            replay_year=replay_year,
        )
        is None
    )


def test_other_circuit_and_old_layout_resolve_without_pilot_annotations(
    singapore_session: dict, singapore_track: dict, corner_record: dict
) -> None:
    for circuit_key, season, layout in (
        ("2", 2025, "silverstone_2025"),
        ("61", 2022, "marina_bay_pre_2023"),
    ):
        context = annotation_context(
            entry_id="entry-a",
            session={
                **singapore_session,
                "circuit_key": circuit_key,
                "path": f"{season}/test/race/",
                "start_date": f"{season}-10-05",
            },
            track={**singapore_track, "circuit_key": circuit_key},
            source="replay",
            session_generation=1,
            replay_year=season,
        )
        assert context is not None
        assert context.layout_key == layout
        assert bind_annotation_layers([corner_record], context, segment_count=3) is None


def test_complete_point_line_and_directed_interval_bind_only_to_pilot(
    singapore_context, corner_record: dict
) -> None:
    start_finish = {
        **corner_record,
        "layer": "start_finish",
        "items": [
            {
                "id": "start_finish",
                "kind": "line",
                "start": [0, -5],
                "end": [0, 5],
                "label": "Start/finish",
            }
        ],
    }
    sectors = {
        **corner_record,
        "layer": "sectors",
        "items": [
            {
                "id": "sector_1",
                "kind": "interval",
                "start": {"segment_index": 2, "fraction": 0.5},
                "end": {"segment_index": 0, "fraction": 0.25},
                "direction": "forward",
                "wraps_start_finish": True,
                "label": "Sector 1",
            }
        ],
    }
    bound = bind_annotation_layers(
        [corner_record, start_finish, sectors], singapore_context, segment_count=3
    )
    assert bound is not None
    assert {layer["layer"] for layer in bound["layers"]} == {
        "corners",
        "start_finish",
        "sectors",
    }
    assert annotation_binding_matches(bound, singapore_context)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("circuit_key", "2"),
        ("layout_key", "marina_bay_pre_2023"),
        ("valid_from_season", 2026),
        ("valid_from_season", True),
        ("valid_to_season", 2024),
        ("geometry_fingerprint", "sha256:wrong"),
        ("qa_status", "candidate"),
        ("rights_status", "pending"),
        ("source", {}),
        ("source", {"url": "https://example.test/map", "checked_on": "2026-99-99"}),
        ("items", []),
        ("items", [{"id": "turn_1", "kind": "point", "label": "1"}]),
        (
            "items",
            [
                {
                    "id": [],
                    "kind": "point",
                    "anchor": [100, 0],
                    "label": "1",
                    "label_offset": [2, -2],
                }
            ],
        ),
        (
            "items",
            [
                {
                    "id": "turn_1",
                    "kind": {},
                    "anchor": [100, 0],
                    "label": "1",
                    "label_offset": [2, -2],
                }
            ],
        ),
        (
            "items",
            [
                {
                    "id": "turn_1",
                    "kind": "point",
                    "anchor": [100, 0],
                    "label": " ",
                    "label_offset": [2, -2],
                }
            ],
        ),
    ],
)
def test_incomplete_or_unapproved_layer_is_not_delivered(
    singapore_context, corner_record: dict, field: str, value
) -> None:
    assert (
        bind_annotation_layers(
            [{**corner_record, field: value}], singapore_context, segment_count=3
        )
        is None
    )


def test_duplicate_layer_fails_closed(singapore_context, corner_record: dict) -> None:
    assert (
        bind_annotation_layers(
            [corner_record, deepcopy(corner_record)], singapore_context, segment_count=3
        )
        is None
    )


def test_invalid_interval_cannot_be_exposed(
    singapore_context, corner_record: dict
) -> None:
    record = {
        **corner_record,
        "layer": "detection_zones",
        "items": [
            {
                "id": "zone_1",
                "kind": "interval",
                "start": {"segment_index": 2, "fraction": 0.5},
                "end": {"segment_index": 0, "fraction": 0.25},
                "direction": "forward",
                "wraps_start_finish": False,
                "label": "Zone 1",
            }
        ],
    }
    assert bind_annotation_layers([record], singapore_context, segment_count=3) is None
    record["items"][0]["wraps_start_finish"] = True
    record["items"][0]["start"]["segment_index"] = 3
    assert bind_annotation_layers([record], singapore_context, segment_count=3) is None


def test_binding_cannot_follow_another_entry_session_or_replay_seek(
    singapore_session: dict,
    singapore_track: dict,
    singapore_context,
    corner_record: dict,
) -> None:
    bound = bind_annotation_layers([corner_record], singapore_context, segment_count=3)
    assert bound is not None
    for entry_id, session_key, generation in (
        ("entry-b", "9896", 1),
        ("entry-a", "new-session", 1),
        ("entry-a", "9896", 2),
    ):
        context = annotation_context(
            entry_id=entry_id,
            session={**singapore_session, "session_key": session_key},
            track=singapore_track,
            source="replay",
            session_generation=generation,
            replay_year=2025,
        )
        assert context is not None
        assert not annotation_binding_matches(bound, context)
    live = annotation_context(
        entry_id="entry-a",
        session=singapore_session,
        track=singapore_track,
        source="live",
        session_generation=1,
    )
    assert live is not None
    assert not annotation_binding_matches(bound, live)


def test_geometry_change_invalidates_existing_binding(
    singapore_session: dict,
    singapore_track: dict,
    singapore_context,
    corner_record: dict,
) -> None:
    bound = bind_annotation_layers([corner_record], singapore_context, segment_count=3)
    changed = annotation_context(
        entry_id="entry-a",
        session=singapore_session,
        track={**singapore_track, "points": [[0, 0], [101, 0], [100, 100], [0, 0]]},
        source="replay",
        session_generation=1,
        replay_year=2025,
    )
    assert changed is not None
    assert not annotation_binding_matches(bound, changed)
    assert bind_annotation_layers([corner_record], changed, segment_count=3) is None
