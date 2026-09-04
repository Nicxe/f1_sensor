---
id: overview
title: "Entity and automation reference"
description: "Browse all F1 Sensor entities by topic, then look up states, attributes, events, and device triggers."
---

Find the exact entity, state, or attribute you need for a dashboard or automation. If you are setting up F1 Sensor for the first time, start with [Installation](/getting-started/installation) and [Configuration](/getting-started/add-integration).

## Choose a reference

| You need | Start here |
| --- | --- |
| An entity ID or attribute | Choose a topic below |
| Track flag or session phase values | [State values and terminology](/reference/values) |
| A trigger in the automation editor | [Device triggers](/reference/device-triggers) |
| An event payload | [Events](/entities/events) |
| Live Delay helper values and calibration | [Live Delay controls](/reference/live-delay-controls) |
| Replay selectors, buttons, and media player actions | [Replay controls](/reference/replay-controls) |
| Token, replay, or connection health | [Diagnostics](/entities/diagnostics) |
| A working automation example | [Automation recipes](/automation#yaml-examples) |

:::info[Use your existing entity IDs]
References show the standard IDs for new installations. Your display names may be translated, and older installations or renamed entities can use different IDs. Check **Settings > Devices & services > Entities** before copying an example.
:::

## Schedule and weather

| Reference | Standard entity ID |
| --- | --- |
| [Next Race](/entities/next-race) | `sensor.f1_next_race` |
| [Track Time](/entities/track-time) | `sensor.f1_track_time` |
| [Current Season](/entities/current-season) | `sensor.f1_current_season` |
| [Season Calendar](/entities/season-calendar) | `calendar.f1_season_calendar` |
| [Race Week](/entities/race-week) | `binary_sensor.f1_race_week` |
| [Next Race Weather](/entities/next-race-weather) | `weather.f1_weather` |
| [Weather Summary](/entities/weather-summary) | `sensor.f1_weather` |
| [Track Weather](/entities/track-weather) | `sensor.f1_track_weather` |

## Session and track

| Reference | Standard entity ID |
| --- | --- |
| [Session Status](/entities/session-status) | `sensor.f1_session_status` |
| [Current Session](/entities/current-session) | `sensor.f1_current_session` |
| [Session Time Elapsed](/entities/session-time-elapsed) | `sensor.f1_session_time_elapsed` |
| [Session Time Remaining](/entities/session-time-remaining) | `sensor.f1_session_time_remaining` |
| [Race Three Hour Limit](/entities/race-three-hour-limit) | `sensor.f1_race_time_to_three_hour_limit` |
| [Track Status](/entities/track-status) | `sensor.f1_track_status` |
| [Safety Car](/entities/safety-car) | `binary_sensor.f1_safety_car` |
| [Race Lap](/entities/race-lap) | `sensor.f1_race_lap_count` |
| [Formation Start](/entities/formation-start) | `binary_sensor.f1_formation_start` |
| [Overtake Mode](/entities/overtake-mode) | `binary_sensor.f1_overtake_mode` |
| [Straight Mode](/entities/straight-mode) | `sensor.f1_straight_mode` |

## Drivers and timing

| Reference | Standard entity ID |
| --- | --- |
| [Driver List](/entities/driver-list) | `sensor.f1_driver_list` |
| [Favorite Driver](/entities/favorite-driver) | `sensor.f1_favorite_driver` |
| [Driver Positions](/entities/driver-positions) | `sensor.f1_driver_positions` |
| [Starting Grid](/entities/starting-grid) | `sensor.f1_starting_grid` |
| [Top Three](/entities/top-three) | `sensor.f1_top_three_p1` |
| [Current Tyres](/entities/current-tyres) | `sensor.f1_current_tyres` |
| [Tyre Statistics](/entities/tyre-statistics) | `sensor.f1_tyre_statistics` |
| [Pit Stops](/entities/pit-stops) | `sensor.f1_pitstops` |
| [Team Radio](/entities/team-radio) | `sensor.f1_team_radio` |

## Results and championship

| Reference | Standard entity ID |
| --- | --- |
| [Last Race Results](/entities/last-race-results) | `sensor.f1_last_race_results` |
| [Sprint Results](/entities/sprint-results) | `sensor.f1_sprint_results` |
| [Season Results](/entities/season-results) | `sensor.f1_season_results` |
| [Lap Position Progression](/entities/lap-position-progression) | `sensor.f1_lap_position_progression` |
| [Driver Standings](/entities/driver-standings) | `sensor.f1_driver_standings` |
| [Constructor Standings](/entities/constructor-standings) | `sensor.f1_constructor_standings` |
| [Driver Points Progression](/entities/driver-points-progression) | `sensor.f1_driver_points_progression` |
| [Constructor Points Progression](/entities/constructor-points-progression) | `sensor.f1_constructor_points_progression` |
| [Championship Prediction (Drivers)](/entities/championship-prediction-drivers) | `sensor.f1_championship_prediction_drivers` |
| [Championship Prediction (Teams)](/entities/championship-prediction-teams) | `sensor.f1_championship_prediction_teams` |

## Officials and incidents

| Reference | Standard entity ID |
| --- | --- |
| [Race Control](/entities/race-control) | `sensor.f1_race_control` |
| [Track Limits](/entities/track-limits) | `sensor.f1_track_limits` |
| [Investigations](/entities/investigations) | `sensor.f1_investigations` |
| [FIA Decision Documents](/entities/fia-decision-documents) | `sensor.f1_fia_documents` |
| [On-track Incident](/entities/on-track-incident) | `binary_sensor.f1_on_track_incident` |
| [Possible On-track Incident](/entities/possible-on-track-incident) | `binary_sensor.f1_possible_on_track_incident` |

## Availability before troubleshooting

Live entities depend on the session and data source. [Live data availability](/entities/live-data#availability-model) and [F1TV Auth](/features/f1tv-auth) explain normal waiting or unavailable states. Schedules and completed results have separate update behavior, documented on each page.
