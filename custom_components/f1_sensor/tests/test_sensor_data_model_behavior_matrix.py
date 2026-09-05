"""Behavior coverage for sensor aggregation and document models."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.f1_sensor.sensor import (
    F1ConstructorPointsProgressionSensor,
    F1DriverPointsProgressionSensor,
    F1FiaDocumentsSensor,
)


def _coordinator(data):
    return SimpleNamespace(data=data, available=True)


def _race_results():
    return {
        "MRData": {
            "RaceTable": {
                "Races": [
                    {"round": "bad", "Results": []},
                    {
                        "season": "2026",
                        "round": "1",
                        "raceName": "Opening GP",
                        "date": "2026-03-01",
                        "time": "12:00:00Z",
                        "Results": [
                            {
                                "position": "1",
                                "points": "25",
                                "Driver": {
                                    "code": "NOR",
                                    "driverId": "norris",
                                    "givenName": "Lando",
                                    "familyName": "Norris",
                                },
                                "Constructor": {
                                    "constructorId": "mclaren",
                                    "name": "McLaren",
                                },
                            },
                            {
                                "positionText": "2",
                                "points": "18",
                                "Driver": {
                                    "driverId": "piastri",
                                    "givenName": "Oscar",
                                    "familyName": "Piastri",
                                },
                                "Constructor": {
                                    "constructorId": "mclaren",
                                    "name": "McLaren",
                                },
                            },
                            {"points": "bad", "Driver": {}, "Constructor": {}},
                        ],
                    },
                ]
            }
        }
    }


def _sprint_results():
    return [
        {"round": "bad", "SprintResults": []},
        {
            "round": "2",
            "raceName": "Sprint GP",
            "date": "2026-03-08",
            "SprintResults": [
                {
                    "points": "8",
                    "Driver": {"code": "NOR"},
                    "Constructor": {
                        "constructorId": "mclaren",
                        "name": "McLaren",
                    },
                },
                {"points": 1, "Driver": {}, "Constructor": {}},
            ],
        },
    ]


def test_driver_points_progression_merges_sprint_and_newer_standings() -> None:
    sensor = F1DriverPointsProgressionSensor(
        _coordinator(_race_results()), "driver_points", "entry", "F1"
    )
    sensor._get_sprint_results = _sprint_results
    sensor._get_driver_standings = lambda: ({"NOR": 40.0, "unknown": 5.0}, 3)
    sensor._recompute()
    assert sensor._attr_native_value == 3
    attrs = sensor.extra_state_attributes
    assert attrs["series"]["labels"] == ["R1", "R2", "R3"]
    assert attrs["drivers"]["NOR"]["totals"]["points"] == 40.0
    assert attrs["drivers"]["NOR"]["totals"]["wins"] == 1
    assert attrs["drivers"]["piastri"]["identity"]["code"] is None


def test_constructor_points_progression_merges_sprint_and_standings() -> None:
    sensor = F1ConstructorPointsProgressionSensor(
        _coordinator(_race_results()), "constructor_points", "entry", "F1"
    )
    sensor._get_sprint_results = _sprint_results
    sensor._get_constructor_standings = lambda: (
        {"mclaren": 60.0, "unknown": 5.0},
        3,
    )
    sensor._recompute()
    assert sensor._attr_native_value == 3
    attrs = sensor.extra_state_attributes
    assert attrs["constructors"]["mclaren"]["totals"]["points"] == 60.0
    assert attrs["constructors"]["mclaren"]["totals"]["wins"] == 1
    assert attrs["series"]["labels"] == ["R1", "R2", "R3"]


def test_fia_documents_reset_bounding_sorting_and_cleaning() -> None:
    sensor = F1FiaDocumentsSensor(_coordinator({}), "fia", "entry", "F1")
    assert sensor._should_reset_for_doc({"name": None}) is False
    assert sensor._should_reset_for_doc({"name": "   "}) is False
    assert sensor._published_timestamp({"published": None}) is None
    assert sensor._published_timestamp({"published": "bad"}) is None
    assert sensor._extract_doc_number(None) == 0
    assert sensor._extract_doc_number("Decision") == 0
    assert sensor._select_latest_document([]) is None
    assert sensor._clean_document_attribute(None) == {}
    assert sensor._clean_race_attribute(None) is None

    old_docs = [
        {
            "name": f"Document {number} - Decision",
            "url": f"https://fia.test/{number}",
            "published": f"2026-08-{(number % 28) + 1:02d}T12:00:00Z",
        }
        for number in range(2, 107)
    ]
    sensor.coordinator.data = {
        "event_key": "2026-1",
        "race": {
            "season": "2026",
            "round": "1",
            "race_name": "Test GP",
            "extra": "ignored",
        },
        "documents": list(reversed(old_docs)) + [None, {"name": "missing url"}],
    }
    assert sensor._update_from_coordinator(force=True) is True
    assert len(sensor.extra_state_attributes["documents"]) == 100
    assert sensor._attr_native_value == 106

    sensor.coordinator.data = {
        "event_key": "2026-1",
        "race": sensor.coordinator.data["race"],
        "documents": [
            {
                "name": "Document 2 - New weekend",
                "url": "https://fia.test/new-2",
                "published": "bad",
            },
            {
                "name": "Document 1 - New weekend",
                "url": "https://fia.test/new-1",
                "published": "2026-09-01T12:00:00",
            },
        ],
    }
    assert sensor._update_from_coordinator() is True
    assert sensor._attr_native_value == 2
    assert len(sensor.extra_state_attributes["documents"]) == 2
    assert sensor._update_from_coordinator() is False
