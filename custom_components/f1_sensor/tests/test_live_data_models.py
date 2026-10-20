"""Live projections retain their semantics with no HA data entities."""

from types import SimpleNamespace

from homeassistant.helpers.entity import Entity
import pytest

from custom_components.f1_sensor import live_data_models as models
from custom_components.f1_sensor.const import DOMAIN

MODEL_TYPES = [
    models.TrackWeatherModel,
    models.TrackStatusModel,
    models.SessionStatusModel,
    models.TimeRemainingModel,
    models.TimeElapsedModel,
    models.RaceLimitModel,
    models.CurrentSessionModel,
    models.RaceControlModel,
    models.TrackLimitsModel,
    models.InvestigationsModel,
    models.TeamRadioModel,
    models.PitStopsModel,
    models.DriverPredictionModel,
    models.TeamPredictionModel,
    models.LapCountModel,
    models.DriverListModel,
    models.CurrentTyresModel,
    models.TyreStatisticsModel,
    models.StartingGridModel,
    models.DriverPositionsModel,
    models.StraightModeModel,
]


@pytest.mark.parametrize("model_type", MODEL_TYPES)
def test_live_models_handle_empty_feed_without_entities(hass, model_type):
    coordinator = SimpleNamespace(
        hass=hass, data={}, data_list=[], last_update_success=True, available=True
    )
    hass.data[DOMAIN] = {
        "entry": {
            "live_state": SimpleNamespace(is_live=True, reason="replay"),
            "live_bus": SimpleNamespace(last_stream_activity_age=lambda: 0),
        }
    }
    model = model_type(coordinator, None, "entry", None)
    assert not isinstance(model, Entity)
    snapshot = model.snapshot()
    assert isinstance(snapshot.attributes, dict)
    assert not hass.states.async_all()


def test_lap_count_keeps_last_distance_when_delta_omits_it(hass):
    coordinator = SimpleNamespace(hass=hass, data={"CurrentLap": 4, "TotalLaps": 58})
    hass.data[DOMAIN] = {
        "entry": {"live_state": SimpleNamespace(is_live=True, reason="replay")}
    }
    model = models.LapCountModel(coordinator, None, "entry", None)
    first = model.snapshot()
    coordinator.data = {"CurrentLap": 5}
    second = model.snapshot()
    assert first.value == 4
    assert second.value == 5
    assert second.attributes["total_laps"] == 58
