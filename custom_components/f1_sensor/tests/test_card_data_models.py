"""User-visible projections shared by entities and direct card data."""

from copy import deepcopy

import pytest

from custom_components.f1_sensor.card_data_models import standings_snapshot


@pytest.mark.parametrize(
    ("kind", "rows_key", "source_key"),
    [
        ("drivers", "driver_standings", "DriverStandings"),
        ("constructors", "constructor_standings", "ConstructorStandings"),
    ],
)
def test_standings_contract_without_entities(kind, rows_key, source_key):
    rows = [{"position": "1", "points": "331", "wins": "7"}]
    payload = {
        "MRData": {
            "StandingsTable": {
                "StandingsLists": [{"season": "2026", "round": "18", source_key: rows}]
            }
        }
    }
    original = deepcopy(payload)
    snapshot = standings_snapshot(payload, kind)
    assert snapshot.value == 1
    assert snapshot.attributes == {"season": "2026", "round": "18", rows_key: rows}
    snapshot.attributes[rows_key][0]["points"] = "0"
    assert payload == original
    assert standings_snapshot(payload, kind).attributes[rows_key][0]["points"] == "331"


@pytest.mark.parametrize(
    "payload", [None, {}, {"MRData": {"StandingsTable": {"StandingsLists": []}}}]
)
@pytest.mark.parametrize("kind", ["drivers", "constructors"])
def test_empty_standings_preserve_existing_sensor_contract(payload, kind):
    snapshot = standings_snapshot(payload, kind)
    assert snapshot.value == 0
    assert snapshot.attributes == {}
