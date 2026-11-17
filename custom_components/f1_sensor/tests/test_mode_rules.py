"""Event-specific permissions from Formula 1 SessionInfo and published FIA rules."""

import pytest

from custom_components.f1_sensor.mode_rules import (
    low_grip_disables_overtake,
    safety_car_disables_overtake,
    straight_mode_for_grip,
)
from custom_components.f1_sensor.track_map_annotation_contract import (
    load_annotation_catalog,
)


def _session(start, meeting, circuit):
    return {
        "StartDate": start,
        "Meeting": {"Key": meeting, "Circuit": {"Key": circuit}},
    }


@pytest.mark.parametrize(
    ("session", "grip", "expected"),
    [
        (_session("2026-06-05T13:30:00", 1286, 22), None, "disabled"),
        (_session("2026-06-07T15:00:00", 1286, 22), "low", "disabled"),
        (_session("2026-11-08T14:00:00", 1299, 14), "low", "low_grip"),
        (_session("2026-11-08T14:00:00", 1299, 14), "normal", "normal_grip"),
        (_session("2026-11-08T14:00:00", 1299, 14), None, None),
        (_session("2026-11-20T16:30:00", 9999, 152), "low", None),
        (_session("2026-03-15T15:00:00", "1280", "49"), "normal", "normal_grip"),
        (_session("2027-06-06T15:00:00", 1286, 22), "normal", None),
        (_session("2026-06-07T15:00:00", 9876, 22), "low", None),
        (_session("2026-11-08T14:00:00", 1299, 22), "low", None),
        ({"StartDate": "2026-11-08T14:00:00"}, "low", None),
        (None, "normal", None),
    ],
)
def test_straight_mode_needs_verified_event_zone_policy(session, grip, expected):
    assert straight_mode_for_grip(session, grip) == expected


def test_catalog_backed_permissions_have_markers_for_both_grip_regimes():
    # Include only the event maps whose 2026 activation points are packaged.
    meetings = {
        10: 1279,
        49: 1280,
        46: 1281,
        151: 1284,
        23: 1285,
        15: 1287,
        19: 1288,
        2: 1289,
        7: 1290,
        4: 1291,
        55: 1292,
        39: 1293,
        153: 1294,
        144: 1295,
        12: 1308,
        61: 1296,
    }
    records = {
        int(record["circuit_key"]): record
        for record in load_annotation_catalog()
        if record["layer"] == "detection_zones"
        and record["valid_from_season"] == record["valid_to_season"] == 2026
        and record["qa_status"] == "verified"
    }
    for circuit, meeting in meetings.items():
        marks = [item["id"] for item in records[circuit]["items"]]
        session = _session("2026-09-01", meeting, circuit)
        for grip, suffix in (("normal", "_n"), ("low", "_l")):
            assert any(
                mark.startswith("sm_a") and mark.endswith(suffix) for mark in marks
            )
            assert straight_mode_for_grip(session, grip) == f"{grip}_grip"


@pytest.mark.parametrize(
    ("session", "applies"),
    [
        ({"StartDate": "2026-06-14T15:00:00"}, False),
        ({"StartDate": "2026-06-26T13:30:00"}, True),
        ({"StartDate": "2026-11-08T14:00:00"}, True),
        ({"Path": "2026/2026-11-08_São_Paulo_Grand_Prix/2026-11-08_Race/"}, True),
        ({"StartDate": "2027-03-01T13:00:00"}, False),
        ({"StartDate": "not a date"}, False),
        ({"Path": "2026/2026-11-08_São_Paulo_Grand_Prix/"}, False),
        ({}, False),
        (None, False),
    ],
)
def test_low_grip_rule_uses_the_original_session_date(session, applies):
    assert low_grip_disables_overtake(session) is applies


@pytest.mark.parametrize(
    ("session", "applies"),
    [
        ({"StartDate": "2026-03-15T15:00:00", "Name": "Race"}, True),
        ({"StartDate": "2026-03-14T11:00:00", "Type": "Race", "Name": "Sprint"}, True),
        (
            {
                "Path": "2026/2026-03-15_Chinese_Grand_Prix/2026-03-14_Sprint/",
                "Type": "Race",
            },
            True,
        ),
        (
            {"StartDate": "2026-03-13", "Type": "Race", "Name": "Sprint Qualifying"},
            False,
        ),
        ({"StartDate": "2026-03-13", "Type": "Practice"}, False),
        ({"StartDate": "2026-03-15"}, False),
        ({"StartDate": "2025-03-23", "Name": "Race"}, False),
        ({"Name": "Race"}, False),
        (None, False),
    ],
)
def test_safety_car_rule_requires_a_2026_race_or_sprint(session, applies):
    assert safety_car_disables_overtake(session) is applies
