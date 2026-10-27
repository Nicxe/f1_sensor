"""Static card data works with no Entity object or registered sensor."""

from types import SimpleNamespace

from homeassistant.helpers.entity import Entity
import pytest

from custom_components.f1_sensor.static_data_models import (
    ConstructorPointsProgressionModel,
    CurrentSeasonModel,
    DriverPointsProgressionModel,
    FiaDocumentsModel,
    LapPositionProgressionModel,
    LastRaceModel,
    NextRaceModel,
    SeasonResultsModel,
    SprintResultsModel,
    WeatherModel,
)


@pytest.mark.parametrize(
    "model_type",
    [
        CurrentSeasonModel,
        DriverPointsProgressionModel,
        ConstructorPointsProgressionModel,
        FiaDocumentsModel,
        LastRaceModel,
        LapPositionProgressionModel,
        NextRaceModel,
        SeasonResultsModel,
        SprintResultsModel,
        WeatherModel,
    ],
)
def test_models_handle_empty_sources_without_entities(hass, model_type):
    coordinator = SimpleNamespace(hass=hass, data={}, last_update_success=True)
    model = model_type(coordinator, None, "entry", None)
    assert not isinstance(model, Entity)
    snapshot = model.snapshot()
    assert isinstance(snapshot.attributes, dict)
    assert not hass.states.async_all()


def test_season_result_projection_keeps_race_identity_and_zero_points(hass):
    result = {
        "number": "44",
        "position": "1",
        "points": "0",
        "Driver": {
            "driverId": "hamilton",
            "givenName": "Lewis",
            "familyName": "Hamilton",
        },
        "Constructor": {"constructorId": "ferrari", "name": "Ferrari"},
        "status": "Finished",
    }
    race = {
        "season": "2026",
        "round": "1",
        "raceName": "Australian Grand Prix",
        "Circuit": {"circuitId": "albert_park", "Location": {"country": "Australia"}},
        "Results": [result],
    }
    coordinator = SimpleNamespace(
        hass=hass, data={"MRData": {"RaceTable": {"season": "2026", "Races": [race]}}}
    )
    snapshot = SeasonResultsModel(coordinator, None, "entry", None).snapshot()
    assert snapshot.value == 1
    assert snapshot.attributes["races"][0]["round"] == "1"
    assert snapshot.attributes["races"][0]["results"][0]["points"] == "0"
