"""Declared card products, dependencies and optional dedicated transports."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import live_data_models as live
from .card_data_models import DataSnapshot, standings_snapshot
from .static_data_models import (
    ConstructorPointsProgressionModel,
    CurrentSeasonModel,
    DriverPointsProgressionModel,
    FiaDocumentsModel,
    LapPositionProgressionModel,
    LastRaceModel,
    NextRaceModel,
    SeasonResultsModel,
    SprintResultsModel,
    TrackTimeModel,
    WeatherModel,
)

# Each product names the existing shared coordinator and an entity-free projector.
DATA_PRODUCTS: dict[str, tuple[str, Callable[[Any], DataSnapshot]]] = {
    "driver_standings": (
        "driver_coordinator",
        lambda value: standings_snapshot(value, "drivers"),
    ),
    "constructor_standings": (
        "constructor_coordinator",
        lambda value: standings_snapshot(value, "constructors"),
    ),
}
DATA_PRODUCTS.update(
    {
        "next_race": ("race_coordinator", NextRaceModel),
        "track_time": ("race_coordinator", TrackTimeModel),
        "current_season": ("race_coordinator", CurrentSeasonModel),
        "weather": ("race_weather_coordinator", WeatherModel),
        "last_race_results": ("last_race_coordinator", LastRaceModel),
        "season_results": ("season_results_coordinator", SeasonResultsModel),
        "sprint_results": ("sprint_results_coordinator", SprintResultsModel),
        "lap_position_progression": (
            "lap_position_progression_coordinator",
            LapPositionProgressionModel,
        ),
        "fia_documents": ("fia_documents_coordinator", FiaDocumentsModel),
        "driver_points_progression": (
            "season_results_coordinator",
            DriverPointsProgressionModel,
        ),
        "constructor_points_progression": (
            "season_results_coordinator",
            ConstructorPointsProgressionModel,
        ),
    }
)
DATA_DEPENDENCIES = {
    "next_race": ("race_coordinator", "next_race_history_coordinator"),
    "weather": ("race_weather_coordinator", "race_coordinator"),
    "fia_documents": ("fia_documents_coordinator", "race_coordinator"),
    "lap_position_progression": (
        "lap_position_progression_coordinator",
        "race_coordinator",
        "season_results_coordinator",
        "sprint_results_coordinator",
    ),
    "driver_points_progression": (
        "season_results_coordinator",
        "sprint_results_coordinator",
        "driver_coordinator",
        "race_coordinator",
    ),
    "constructor_points_progression": (
        "season_results_coordinator",
        "sprint_results_coordinator",
        "constructor_coordinator",
        "race_coordinator",
    ),
}
NON_SPOILER_PRODUCTS = frozenset(
    {"next_race", "track_time", "current_season", "weather"}
)


LIVE_PRODUCTS = {
    "track_weather": ("weather_data_coordinator", live.TrackWeatherModel),
    "track_status": ("track_status_coordinator", live.TrackStatusModel),
    "session_status": ("session_status_coordinator", live.SessionStatusModel),
    "current_session": ("session_info_coordinator", live.CurrentSessionModel),
    "session_time_remaining": ("session_clock_coordinator", live.TimeRemainingModel),
    "session_time_elapsed": ("session_clock_coordinator", live.TimeElapsedModel),
    "race_time_to_three_hour_limit": ("session_clock_coordinator", live.RaceLimitModel),
    "race_lap_count": ("lap_count_coordinator", live.LapCountModel),
    "driver_list": ("drivers_coordinator", live.DriverListModel),
    "driver_positions": ("drivers_coordinator", live.DriverPositionsModel),
    "current_tyres": ("drivers_coordinator", live.CurrentTyresModel),
    "tyre_statistics": ("drivers_coordinator", live.TyreStatisticsModel),
    "starting_grid": ("starting_grid_coordinator", live.StartingGridModel),
    "race_control": ("race_control_coordinator", live.RaceControlModel),
    "track_limits": ("race_control_coordinator", live.TrackLimitsModel),
    "investigations": ("race_control_coordinator", live.InvestigationsModel),
    "team_radio": ("team_radio_coordinator", live.TeamRadioModel),
    "pitstops": ("pitstop_coordinator", live.PitStopsModel),
    "championship_prediction_drivers": (
        "championship_prediction_coordinator",
        live.DriverPredictionModel,
    ),
    "championship_prediction_teams": (
        "championship_prediction_coordinator",
        live.TeamPredictionModel,
    ),
    "straight_mode": ("live_mode_coordinator", live.StraightModeModel),
}
DATA_PRODUCTS.update(LIVE_PRODUCTS)
# Context products have no separate external source.
DATA_PRODUCTS.update({"session_context": ("", None), "replay_status": ("", None)})
DEDICATED_CARD_FEATURES = frozenset(
    {"track_map", "analysis", "minisectors", "replay", "telemetry", "archive"}
)
CARD_FEATURE_KEYS = frozenset(DATA_PRODUCTS) | DEDICATED_CARD_FEATURES
HISTORY_PRODUCTS = frozenset(
    {
        "driver_positions",
        "track_limits",
        "investigations",
        "race_control",
        "team_radio",
        "pitstops",
    }
)
NON_SPOILER_PRODUCTS |= {"session_context", "replay_status"}
for key, (coordinator, model) in LIVE_PRODUCTS.items():
    context_dependencies = {
        "session_info_coordinator",
        "session_status_coordinator",
        *model.context_bindings.values(),
    }
    if key in {"investigations", "track_limits", "session_status"}:
        context_dependencies.add("race_control_coordinator")
    DATA_DEPENDENCIES[key] = tuple(sorted({coordinator, *context_dependencies}))
DATA_DEPENDENCIES["session_context"] = (
    "session_info_coordinator",
    "session_status_coordinator",
)
DATA_DEPENDENCIES["replay_status"] = ()


def card_feature_requirements(features):
    """Resolve data selections to the existing static/live feature planner."""
    result = set(features) & (set(DATA_PRODUCTS) - {"session_context", "replay_status"})
    if result & {"championship_prediction_drivers", "championship_prediction_teams"}:
        result.add("championship_prediction")
    if set(features) & DEDICATED_CARD_FEATURES - {"archive"}:
        result.update(
            {"driver_positions", "current_session", "session_status", "race_control"}
        )
    if "driver_list" in result:
        result.add("driver_standings")
    return result


def static_source_requirements(features):
    """Resolve sensor or module dependencies without acquiring any sources."""
    features = set(features)
    if features & {"race_week", "calendar", "season_results", "sprint_results"}:
        features.add("current_season")
    return {
        name
        for key in features
        if key in DATA_PRODUCTS
        for name in DATA_DEPENDENCIES.get(key, (DATA_PRODUCTS[key][0],))
        if key not in LIVE_PRODUCTS and name
    }
