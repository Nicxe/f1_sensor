"""Live projections retain their semantics with no HA data entities."""

from types import SimpleNamespace
from unittest.mock import Mock

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


@pytest.fixture
def driver_projection_source(hass):
    driver = {
        "identity": {"racing_number": "4", "tla": "NOR", "team_color": "FF8000"},
        "timing": {"position": 1, "gap": "+0.0", "in_pit": False},
        "tyres": {"compound": "MEDIUM", "stint_laps": 12},
        "tyre_history": {"timing_completed_laps": 12, "stints": []},
        "laps": {str(lap): "1:25.000" for lap in range(1, 13)},
    }
    coordinator = SimpleNamespace(
        hass=hass,
        data={
            "drivers": {"4": driver},
            "lap_current": 13,
            "lap_total": 71,
            "tyre_statistics": {
                "fastest_compound": "MEDIUM",
                "compounds": {"MEDIUM": {"fastest_time_secs": 85.0}},
            },
        },
    )
    live_state = SimpleNamespace(is_live=True, reason="replay")
    hass.data[DOMAIN] = {"entry": {"live_state": live_state}}
    return coordinator, driver, live_state


@pytest.mark.parametrize(
    "model_type",
    [models.DriverListModel, models.CurrentTyresModel, models.TyreStatisticsModel],
)
def test_driver_projections_only_refresh_for_relevant_inputs(
    driver_projection_source, model_type
):
    coordinator, driver, live_state = driver_projection_source
    model = model_type(coordinator, None, "entry", None)
    model.refresh_data = Mock(wraps=model.refresh_data)
    first = model.snapshot()
    driver["timing"]["gap"] = "+1.5"
    driver["laps"]["13"] = "1:24.900"

    second = model.snapshot()

    assert second == first
    model.refresh_data.assert_called_once_with()
    if model_type is models.DriverListModel:
        driver["identity"]["tla"] = "NEW"
        second.attributes["drivers"][0]["tla"] = "LOCAL"
        assert model.snapshot().attributes["drivers"][0]["tla"] == "NEW"
        assert first.attributes["drivers"][0]["tla"] == "NOR"
    elif model_type is models.CurrentTyresModel:
        driver["timing"].update(position=2, in_pit=True, retired=True)
        driver["tyre_history"]["timing_completed_laps"] = 13
        driver["tyres"]["stint_laps"] = 13
        coordinator.data["lap_current"] = 14
        second.attributes["drivers"][0]["stint_laps"] = 0
        third = model.snapshot()
        row = third.attributes["drivers"][0]
        assert (row["position"], row["in_pit"], row["retired"]) == ("2", True, True)
        assert (row["stint_laps"], row["completed_laps"]) == (13, 13)
        assert third.attributes["lap_current"] == 14
        assert first.attributes["drivers"][0]["stint_laps"] == 12
    else:
        stats = coordinator.data["tyre_statistics"]["compounds"]["MEDIUM"]
        stats["fastest_time_secs"] = 84.9
        second.attributes["compounds"]["MEDIUM"]["fastest_time_secs"] = 0
        assert (
            model.snapshot().attributes["compounds"]["MEDIUM"]["fastest_time_secs"]
            == 84.9
        )
        assert first.attributes["compounds"]["MEDIUM"]["fastest_time_secs"] == 85.0

    assert model.refresh_data.call_count == 2
    coordinator.hass.data[DOMAIN]["entry"]["session_info_coordinator"] = (
        SimpleNamespace(data={"Key": 1234, "Type": "Race"})
    )
    active = model.snapshot()
    assert model.refresh_data.call_count == 3
    live_state.is_live = False
    inactive = model.snapshot()
    assert model.refresh_data.call_count == 4
    if model_type is not models.DriverListModel:
        assert inactive.value is None
        live_state.is_live = True
        assert model.snapshot() == active
    else:
        assert inactive == active


def test_driver_list_uses_standings_until_live_identity_arrives(hass):
    driver_standings = {
        "Driver": {"permanentNumber": "4", "code": "NOR", "givenName": "Lando"}
    }
    standings = SimpleNamespace(data={})
    coordinator = SimpleNamespace(hass=hass, data={})
    hass.data[DOMAIN] = {"entry": {"driver_coordinator": standings}}
    model = models.DriverListModel(coordinator, None, "entry", None)
    assert model.snapshot().value is None

    standings.data["MRData"] = {
        "StandingsTable": {"StandingsLists": [{"DriverStandings": [driver_standings]}]}
    }
    assert model.snapshot().attributes["source"] == "ergast"

    coordinator.data["drivers"] = {
        "4": {"identity": {"tla": "NOR", "name": "Lando Norris"}}
    }
    live = model.snapshot()
    assert live.attributes["drivers"][0]["name"] == "Lando Norris"
    assert "source" not in live.attributes


@pytest.mark.parametrize(
    ("branch", "field", "updated", "attribute", "expected"),
    [
        ("timing", "position", 2, "position", "2"),
        ("timing", "retired", True, "retired", True),
        ("timing", "in_pit", True, "in_pit", True),
        ("identity", "tla", "NEW", "tla", "NEW"),
        ("tyres", "stint_laps", 13, "stint_laps", 13),
        ("tyre_history", "timing_completed_laps", 13, "completed_laps", 13),
    ],
)
def test_current_tyres_tracks_isolated_driver_changes(
    driver_projection_source, branch, field, updated, attribute, expected
):
    coordinator, driver, _ = driver_projection_source
    model = models.CurrentTyresModel(coordinator, None, "entry", None)
    first = model.snapshot()
    driver[branch][field] = updated
    assert model.snapshot().attributes["drivers"][0][attribute] == expected
    assert first.attributes["drivers"][0][attribute] != expected


def test_tyre_statistics_refreshes_waiting_attributes_and_enters_ready(
    driver_projection_source,
):
    coordinator, driver, _ = driver_projection_source
    model = models.TyreStatisticsModel(coordinator, None, "entry", None)
    stats = coordinator.data.pop("tyre_statistics")
    driver["tyres"]["stint_laps"] = None
    waiting = model.snapshot()
    assert waiting.attributes["status"] == "waiting_for_compound_data"
    assert waiting.attributes["drivers_with_stints"] == 0
    assert waiting.attributes["drivers_with_stint_laps"] == 0

    driver["tyres"]["stint_laps"] = 12
    driver["tyre_history"]["stints"].append({"compound": "UNKNOWN"})
    updated = model.snapshot()
    assert updated.attributes["drivers_with_stints"] == 1
    assert updated.attributes["drivers_with_stint_laps"] == 1

    driver["tyre_history"]["stints"][0]["compound"] = "MEDIUM"
    model.refresh_data = Mock(wraps=model.refresh_data)
    model.snapshot()
    model.refresh_data.assert_called_once_with()

    coordinator.data["tyre_statistics"] = stats
    assert model.snapshot().attributes["status"] == "ready"
