---
id: live-data
title: "Live data entities"
description: "Find live F1 session, driver, track, and race control entities with links to their full references."
---

Use these entities to follow a session, build timing dashboards, and trigger automations. Each entity now has a focused page with its complete state, attributes, and examples.

## Availability model

Most live entities need an active session and **Enable live F1 API** in [Configuration](/getting-started/add-integration). Outside a session they may become unavailable; Driver List retains its last known data for dashboard graphics. Check the individual reference for exceptions.

| Data mode | What to expect |
| --- | --- |
| Public live timing | Session status, track status, Safety Car, Race Control, weather, driver timing, tyres, top three, and confirmed incident detection |
| Optional F1TV Auth | Extra live data can become available when Formula 1 accepts your token and publishes the required streams |
| Replay Mode | Completed session data plays through the same entities when the archive contains it |

[F1TV availability](/features/f1tv-auth) explains which features need extra live data. [Track Map](/features/track-map) is a dashboard feature, not a normal Home Assistant entity. The unofficial live timing API can change without notice.

## Reference: Enum Values

Find [track flags, session phases, tyre compounds, and timing modes](/reference/values) in the state value reference.

:::info[Entity IDs and display names]
The links use standard entity IDs. Display names can be translated, and older or renamed entities may have different IDs. Select the entity from your installation when copying an example.
:::

## Entities Summary

| Entity | Reference |
| --- | --- |
| `sensor.f1_session_status` | [Session Status](/entities/session-status) |
| `sensor.f1_current_session` | [Current Session](/entities/current-session) |
| `sensor.f1_session_time_elapsed` | [Session Time Elapsed](/entities/session-time-elapsed) |
| `sensor.f1_session_time_remaining` | [Session Time Remaining](/entities/session-time-remaining) |
| `sensor.f1_race_time_to_three_hour_limit` | [Race Three Hour Limit](/entities/race-three-hour-limit) |
| `sensor.f1_track_status` | [Track Status](/entities/track-status) |
| `binary_sensor.f1_safety_car` | [Safety Car](/entities/safety-car) |
| `binary_sensor.f1_on_track_incident` | [On-track Incident](/entities/on-track-incident) |
| `binary_sensor.f1_possible_on_track_incident` | [Possible On-track Incident](/entities/possible-on-track-incident) |
| `sensor.f1_race_lap_count` | [Race Lap](/entities/race-lap) |
| `sensor.f1_track_weather` | [Track Weather](/entities/track-weather) |
| `sensor.f1_driver_list` | [Driver List](/entities/driver-list) |
| `sensor.f1_pitstops` | [Pit Stops](/entities/pit-stops) |
| `sensor.f1_team_radio` | [Team Radio](/entities/team-radio) |
| `sensor.f1_current_tyres` | [Current Tyres](/entities/current-tyres) |
| `sensor.f1_tyre_statistics` | [Tyre Statistics](/entities/tyre-statistics) |
| `sensor.f1_favorite_driver` | [Favorite Driver](/entities/favorite-driver) |
| `sensor.f1_driver_positions` | [Driver Positions](/entities/driver-positions) |
| `sensor.f1_starting_grid` | [Starting Grid](/entities/starting-grid) |
| `sensor.f1_top_three_p1` | [Top Three](/entities/top-three) |
| `sensor.f1_race_control` | [Race Control](/entities/race-control) |
| `sensor.f1_track_limits` | [Track Limits](/entities/track-limits) |
| `sensor.f1_investigations` | [Investigations](/entities/investigations) |
| `sensor.f1_championship_prediction_drivers` | [Championship Prediction (Drivers)](/entities/championship-prediction-drivers) |
| `sensor.f1_championship_prediction_teams` | [Championship Prediction (Teams)](/entities/championship-prediction-teams) |
| `binary_sensor.f1_formation_start` | [Formation Start](/entities/formation-start) |
| `binary_sensor.f1_overtake_mode` | [Overtake Mode](/entities/overtake-mode) |
| `sensor.f1_straight_mode` | [Straight Mode](/entities/straight-mode) |

## Browse all reference topics

The [reference index](/reference/overview) groups schedules, timing, drivers, officials, and championship data by task.

## Session Status

[Session Status: state, attributes, and examples](/entities/session-status).

## Current Session

[Current Session: state, attributes, and examples](/entities/current-session).

## Session Time Elapsed

[Session Time Elapsed: state, attributes, and examples](/entities/session-time-elapsed).

## Session Time Remaining

[Session Time Remaining: state, attributes, and examples](/entities/session-time-remaining).

## Race Three Hour Limit

[Race Three Hour Limit: state, attributes, and examples](/entities/race-three-hour-limit).

## Track Status

[Track Status: state, attributes, and examples](/entities/track-status).

## Safety Car

[Safety Car: state, attributes, and examples](/entities/safety-car).

## On-track Incident

[On-track Incident: state, attributes, and examples](/entities/on-track-incident).

## Possible On-track Incident

[Possible On-track Incident: state, attributes, and examples](/entities/possible-on-track-incident).

## Race Lap

[Race Lap: state, attributes, and examples](/entities/race-lap).

## Track Weather

[Track Weather: state, attributes, and examples](/entities/track-weather).

## Driver List

[Driver List: state, attributes, and examples](/entities/driver-list).

## Pit Stops

[Pit Stops: state, attributes, and examples](/entities/pit-stops).

## Team Radio

[Team Radio: state, attributes, and examples](/entities/team-radio).

## Current Tyres

[Current Tyres: state, attributes, and examples](/entities/current-tyres).

## Tyre Statistics

[Tyre Statistics: state, attributes, and examples](/entities/tyre-statistics).

## Favorite Driver

[Favorite Driver: state, attributes, and examples](/entities/favorite-driver).

## Driver Positions

[Driver Positions: state, attributes, and examples](/entities/driver-positions).

## Starting Grid

[Starting Grid: state, attributes, and examples](/entities/starting-grid).

### Grid context and source

[Read grid context and source in the Starting Grid reference](/entities/starting-grid#grid-context-and-source).

### Weekend flow

[Read weekend flow in the Starting Grid reference](/entities/starting-grid#weekend-flow).

## Top Three

[Top Three: state, attributes, and examples](/entities/top-three).

## Race Control

[Race Control: state, attributes, and examples](/entities/race-control).

## Track Limits

[Track Limits: state, attributes, and examples](/entities/track-limits).

## Investigations

[Investigations: state, attributes, and examples](/entities/investigations).

## Championship Prediction (Drivers)

[Championship Prediction (Drivers): state, attributes, and examples](/entities/championship-prediction-drivers).

## Championship Prediction (Teams)

[Championship Prediction (Teams): state, attributes, and examples](/entities/championship-prediction-teams).

## Formation Start

[Formation Start: state, attributes, and examples](/entities/formation-start).

## Overtake Mode

[Overtake Mode: state, attributes, and examples](/entities/overtake-mode).

## Straight Mode

[Straight Mode: state, attributes, and examples](/entities/straight-mode).
