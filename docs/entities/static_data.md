---
id: static-data
title: Static Data
description: To add the integration to your Home Assistant instance
---

Information that rarely changes, such as schedules, drivers, circuits, and championship standings.


### Entities Summary

| Entity                                                                            | Info                                              | 
| ----------------------------------------------------------------------------------| --------------------------------------------------| 
| [sensor.f1_next_race](#next-race)                                                 | Next race info                                    | 
| [sensor.f1_season_calendar](#current-season-race)                                 | Full race schedule                                | 
| [sensor.f1_driver_standings](#driver-standings)                                   | Current driver championship standings             | 
| [sensor.f1_constructor_standings](#constructor-standings)                         | Current constructor standings                     | 
| [sensor.f1_weather](#weather-summary)                                             | Weather forecast at next race circuit             | 
| [sensor.f1_last_race_results](#last-race-results)                                 | Most recent race results                          | 
| [sensor.f1_season_results](#season-results)                                       | All season race results                           | 
| [sensor.f1_driver_points_progression](#driver-points-progression)                 | Drivers Point Progression                         | 
| [sensor.f1_constructor_points_progression](#constructor-points-progression)       | Constructors Point Progression                    | 
| [binary_sensor.f1_race_week](#race-week)                                     | `on` during race week                             | 

::::info
Each timestamp attribute (e.g. `race_start`) is still provided in UTC. In addition, a `_local` variant such as `race_start_local` is available. These values use the circuit's timezone so you can easily create automations at the correct local time.
::::

---

### Next Race 
`sensor.f1_next_race` - Human‑readable schedule for the next race; state is the start time (ISO‑8601).

**State**
  - ISO‑8601 timestamp of the race start, or `unknown` if not available.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| round | string | Round number |
| race_name | string | Grand Prix name |
| race_url | string | Ergast race URL |
| circuit_id | string | Circuit identifier |
| circuit_name | string | Circuit name |
| circuit_url | string | Circuit URL |
| circuit_lat | string | Latitude |
| circuit_long | string | Longitude |
| circuit_locality | string | City/area |
| circuit_country | string | Country |
| circuit_timezone | string | Local timezone (best effort) |
| race_start | string | Race start (UTC ISO‑8601) |
| race_start_local | string | Race start in local circuit time |
| first_practice_start | string | FP1 start (UTC) |
| first_practice_start_local | string | FP1 start (local) |
| second_practice_start | string | FP2 start (UTC) |
| second_practice_start_local | string | FP2 start (local) |
| third_practice_start | string | FP3 start (UTC) |
| third_practice_start_local | string | FP3 start (local) |
| qualifying_start | string | Qualifying start (UTC) |
| qualifying_start_local | string | Qualifying start (local) |
| sprint_qualifying_start | string | Sprint Qualifying/Shootout start (UTC) |
| sprint_qualifying_start_local | string | Sprint Qualifying/Shootout start (local) |
| sprint_start | string | Sprint start (UTC) |
| sprint_start_local | string | Sprint start (local) |

---

### Current Season Race 
`sensor.f1_next_race` - Number of races in the current season.

**State**
  - Integer: count of races in the season.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| races | list | Raw Ergast races array for the season |

---


### Driver Standings
`sensor.f1_next_race` - Driver standings snapshot from Ergast.

**State**
- Integer: number of drivers in the standings list.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| round | string | Round of the standings snapshot |
| driver_standings | list | Ergast “DriverStandings” array (positions, points, wins, driver info, constructor) |

---

### Constructor Standings
`sensor.f1_next_race` - Constructor standings snapshot from Ergast.

**State**
- Integer: number of constructors in the standings list.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| round | string | Round of the standings snapshot |
| constructor_standings | list | Ergast “ConstructorStandings” array (positions, points, wins, constructor info) |


### Weather (Summary)
`sensor.f1_weather` - Compact weather for the circuit location: current and projected at race start.

**State**
- Number: current air temperature (°C), or `unknown`.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| current_temperature | number | Current air temperature (°C) |
| current_temperature_unit | string | “celsius” |
| current_humidity | number | % RH |
| current_humidity_unit | string | “%” |
| current_cloud_cover | number | % cloud cover |
| current_cloud_cover_unit | string | “%” |
| current_precipitation | number | Selected precipitation amount (mm, from best of 1/6/12h blocks) |
| current_precipitation_amount_min | number | Min precip amount (mm) if provided |
| current_precipitation_amount_max | number | Max precip amount (mm) if provided |
| current_precipitation_unit | string | “mm” |
| current_wind_speed | number | Wind speed (m/s) |
| current_wind_speed_unit | string | “m/s” |
| current_wind_direction | string | Cardinal abbreviation (e.g., “NW”) |
| current_wind_from_direction_degrees | number | Wind direction (degrees) |
| current_wind_from_direction_unit | string | “degrees” |
| race_temperature | number | Projected air temperature at race start (°C) |
| race_temperature_unit | string | “celsius” |
| race_humidity | number | % RH at race start |
| race_humidity_unit | string | “%” |
| race_cloud_cover | number | % at race start |
| race_cloud_cover_unit | string | “%” |
| race_precipitation | number | Selected precipitation at race start (mm) |
| race_precipitation_amount_min | number | Min precip amount (mm) if provided |
| race_precipitation_amount_max | number | Max precip amount (mm) if provided |
| race_precipitation_unit | string | “mm” |
| race_wind_speed | number | Wind speed at race start (m/s) |
| race_wind_speed_unit | string | “m/s” |
| race_wind_direction | string | Cardinal abbreviation |
| race_wind_from_direction_degrees | number | Wind direction (degrees) |
| race_wind_from_direction_unit | string | “degrees” |
| race_weather_icon | string | MDI icon name matching weather symbol |

---

### Last Race Results
`sensor.f1_next_race` - Results of the most recent race; state is the winner’s family name.

- State
  - String: winner surname, or `unknown`.

- Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| round | string | Round number |
| race_name | string | Grand Prix name |
| race_url | string | Ergast URL |
| circuit_id | string | Circuit identifier |
| circuit_name | string | Circuit name |
| circuit_url | string | Circuit URL |
| circuit_lat | string | Latitude |
| circuit_long | string | Longitude |
| circuit_locality | string | City/area |
| circuit_country | string | Country |
| circuit_timezone | string | Local timezone (best effort) |
| race_start | string | Race start (UTC ISO‑8601) |
| race_start_local | string | Race start (local) |
| results | list | Cleaned results array: `{number, position, points, status, driver{permanentNumber, code, givenName, familyName}, constructor{constructorId, name}}` |


---

### Season Results
`sensor.f1_next_race` - All results across the current season.

**State**
  - Integer: number of races with results.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| races | list | For each race: `{round, race_name, results:[…]}` where each result has same shape as in “Last Race Results” |



::::caution Known Issue
`sensor.f1_season_results` may trigger a warning in the Home Assistant logs:

```yaml
Logger: homeassistant.components.recorder.db_schema
Source: components/recorder/db_schema.py:663
Integration: Recorder
State attributes for sensor.f1_season_results exceed maximum size of 16384 bytes. This can cause database performance issues; Attributes will not be stored
```

Despite the warning, the sensor should still work fine for display in the frontend. However, to avoid any database load/performance issues, it is recommended to **exclude this sensor from being recorded** in your `recorder:` config:

```yaml
recorder:
  exclude:
    entities:
      - sensor.f1_season_results
```
::::



### Driver Points Progression
`sensor.f1_next_race` - Per‑round driver points (including sprint) with cumulative series, suitable for charts.

**State**
  - Integer: number of rounds covered.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| rounds | list | `[ { round, race_name, date } ]` |
| drivers | object | Map `{ code/driverId: { name, code, driverId, wins_by_round[], totals{points, wins} } }` |
| series | object | `{ labels: ["R1","R2",…], series: [ { key, name, data[], cumulative[] } ] }` |


---

### Constructor Points Progression
`sensor.f1_next_race` - Per‑round constructor points (including sprint) with cumulative series.

**State**
  - Integer: number of rounds covered.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| rounds | list | `[ { round, race_name, date } ]` |
| constructors | object | Map `{ constructorId/name: { name, constructorId, wins_by_round[], totals{points, wins} } }` |
| series | object | `{ labels: ["R1","R2",…], series: [ { key, name, data[], cumulative[] } ] }` |


### Race Week 
`sensor.f1_next_race` - True when the next race is scheduled in the current calendar week.

**State (on/off)**
- `on` during weeks containing the next race date; otherwise `off`.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| days_until_next_race | number | Days from today to the next race date |
| next_race_name | string | Grand Prix name of the next race |

---

::::note API-update
The integration fetches fresh data from the Jolpica-F1 API every 1 hours.
::::