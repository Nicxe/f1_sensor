---
id: static-data
title: Static Data
---

Information that rarely changes, such as schedules, drivers, circuits, and championship standings.


## Entities Summary

| Entity                                                                            | Info                                              | 
| ----------------------------------------------------------------------------------| --------------------------------------------------| 
| [sensor.f1_next_race](#next-race)                                                       | Next race info                                    |
| [sensor.f1_track_time](#track-time)                                               | Current local time at the next race circuit       |
| [sensor.f1_current_season](#current-season)                                       | Full race schedule                                | 
| [sensor.f1_driver_standings](#driver-standings)                                   | Current driver championship standings             | 
| [sensor.f1_constructor_standings](#constructor-standings)                         | Current constructor standings                     | 
| [sensor.f1_weather](#weather-summary)                                             | Weather forecast at next race circuit             | 
| [sensor.f1_last_race_results](#last-race-results)                                 | Most recent race results                          | 
| [sensor.f1_season_results](#season-results)                                       | All season race results                           | 
| [sensor.f1_driver_points_progression](#driver-points-progression)                 | Drivers Point Progression                         | 
| [sensor.f1_constructor_points_progression](#constructor-points-progression)       | Constructors Point Progression                    | 
| [binary_sensor.f1_race_week](#race-week)                                          | `on` during race week                             | 
| [sensor.f1_sprint_results](#sprint-results)                                       | Sprint classification results |
| [sensor.f1_fia_documents](#fia-decision-documents)                                | FIA decisions and documents for the current weekend |
| [calendar.f1_race_season_calendar](#season-calendar)                              | Full season calendar with all sessions              |


::::info
Many schedule timestamps are provided in three variants: an explicit UTC value (for example `race_start_utc`), a Home Assistant local-time value (for example `race_start`), and a circuit-local value (for example `race_start_local`). The circuit-local timestamps use the circuit's timezone so you can build automations against local session times.
::::

---

## Next Race 
`sensor.f1_next_race` - Schedule for the next race; state is the race start timestamp (ISO‑8601).

**State**
  - ISO‑8601 timestamp (UTC) of the race start, or `unknown` if not available.

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
| country_code | string | ISO country code (e.g., "GB", "IT", "US") |
| country_flag_url | string | URL to country flag image |
| circuit_map_url | string | URL to official circuit map image |
| circuit_timezone | string | Local timezone (best effort) |
| race_start_utc | string | Race start (UTC ISO‑8601) |
| race_start | string | Race start in Home Assistant local time |
| race_start_local | string | Race start in circuit local time |
| first_practice_start_utc | string | FP1 start (UTC ISO‑8601) |
| first_practice_start | string | FP1 start in Home Assistant local time |
| first_practice_start_local | string | FP1 start in circuit local time |
| second_practice_start_utc | string | FP2 start (UTC ISO‑8601) |
| second_practice_start | string | FP2 start in Home Assistant local time |
| second_practice_start_local | string | FP2 start in circuit local time |
| third_practice_start_utc | string | FP3 start (UTC ISO‑8601) |
| third_practice_start | string | FP3 start in Home Assistant local time |
| third_practice_start_local | string | FP3 start in circuit local time |
| qualifying_start_utc | string | Qualifying start (UTC ISO‑8601) |
| qualifying_start | string | Qualifying start in Home Assistant local time |
| qualifying_start_local | string | Qualifying start in circuit local time |
| sprint_qualifying_start_utc | string | Sprint Qualifying/Shootout start (UTC ISO‑8601) |
| sprint_qualifying_start | string | Sprint Qualifying/Shootout start in Home Assistant local time |
| sprint_qualifying_start_local | string | Sprint Qualifying/Shootout start in circuit local time |
| sprint_start_utc | string | Sprint start (UTC ISO‑8601) |
| sprint_start | string | Sprint start in Home Assistant local time |
| sprint_start_local | string | Sprint start in circuit local time |

---

## Track Time
`sensor.f1_track_time` - Current local time at the next race circuit.

**State**
- String: local time at the circuit, formatted as `HH:MM`, or `unknown`.

**Example**
```text
14:05
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| timezone | string | Circuit timezone (IANA, best effort) |
| utc_offset | string | UTC offset at the circuit, formatted as `+HHMM` |
| offset_from_home | string | Difference between circuit time and Home Assistant time (best effort) |
| circuit_name | string | Circuit name |
| circuit_locality | string | City/area |
| circuit_country | string | Country |

---

## Current Season
`sensor.f1_current_season` - Number of races in the current season.

**State**

  - Integer: count of races in the season.

**Example**
```text
24
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| races | list | Enriched races array for the season |

Each entry in `races` contains the standard Ergast race data plus:

| Field | Type | Description |
| --- | --- | --- |
| country_code | string | ISO country code (e.g., "GB", "IT", "US") |
| country_flag_url | string | URL to country flag image |
| circuit_map_url | string | URL to official circuit map image |

---


## Driver Standings
`sensor.f1_driver_standings` - Driver standings snapshot from Ergast.

**State**

- Integer: number of drivers in the standings list.

**Example**
```text
20
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| round | string | Round of the standings snapshot |
| driver_standings | list | Ergast "DriverStandings" array |

Each entry in `driver_standings` contains:

| Field | Type | Description |
| --- | --- | --- |
| position | string | Championship position |
| positionText | string | Position as display text |
| points | string | Total points |
| wins | string | Number of wins |
| Driver | object | Driver information |
| Constructors | list | List of constructor(s) the driver has raced for |

The `Driver` object contains:

| Field | Type | Description |
| --- | --- | --- |
| driverId | string | Driver identifier (e.g., "max_verstappen") |
| permanentNumber | string | Permanent car number |
| code | string | Three-letter driver code (TLA) |
| url | string | Wikipedia URL |
| givenName | string | First name |
| familyName | string | Last name |
| dateOfBirth | string | Date of birth (YYYY-MM-DD) |
| nationality | string | Nationality |

Each entry in `Constructors` contains:

| Field | Type | Description |
| --- | --- | --- |
| constructorId | string | Constructor identifier |
| url | string | Wikipedia URL |
| name | string | Team name |
| nationality | string | Team nationality |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "season": "2025",
  "round": "12",
  "driver_standings": [
    {
      "position": "1",
      "positionText": "1",
      "points": "255",
      "wins": "7",
      "Driver": {
        "driverId": "max_verstappen",
        "permanentNumber": "1",
        "code": "VER",
        "url": "http://en.wikipedia.org/wiki/Max_Verstappen",
        "givenName": "Max",
        "familyName": "Verstappen",
        "dateOfBirth": "1997-09-30",
        "nationality": "Dutch"
      },
      "Constructors": [
        {
          "constructorId": "red_bull",
          "url": "http://en.wikipedia.org/wiki/Red_Bull_Racing",
          "name": "Red Bull",
          "nationality": "Austrian"
        }
      ]
    },
    {
      "position": "2",
      "positionText": "2",
      "points": "180",
      "wins": "2",
      "Driver": {
        "driverId": "lewis_hamilton",
        "permanentNumber": "44",
        "code": "HAM",
        "url": "http://en.wikipedia.org/wiki/Lewis_Hamilton",
        "givenName": "Lewis",
        "familyName": "Hamilton",
        "dateOfBirth": "1985-01-07",
        "nationality": "British"
      },
      "Constructors": [
        {
          "constructorId": "ferrari",
          "url": "http://en.wikipedia.org/wiki/Scuderia_Ferrari",
          "name": "Ferrari",
          "nationality": "Italian"
        }
      ]
    }
  ]
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get championship leader:**
```jinja2
{% set standings = state_attr('sensor.f1_driver_standings', 'driver_standings') %}
{% if standings and standings | length > 0 %}
  {% set leader = standings[0] %}
  Leader: {{ leader.Driver.givenName }} {{ leader.Driver.familyName }} ({{ leader.points }} pts)
{% endif %}
```

**Get a specific driver's position:**
```jinja2
{% set standings = state_attr('sensor.f1_driver_standings', 'driver_standings') %}
{% set ver = standings | selectattr('Driver.code', 'eq', 'VER') | first %}
{% if ver %}
  VER is P{{ ver.position }} with {{ ver.points }} points and {{ ver.wins }} wins
{% endif %}
```

**Calculate points gap to leader:**
```jinja2
{% set standings = state_attr('sensor.f1_driver_standings', 'driver_standings') %}
{% if standings and standings | length > 1 %}
  {% set leader_pts = standings[0].points | int %}
  {% set second_pts = standings[1].points | int %}
  Gap: {{ leader_pts - second_pts }} points
{% endif %}
```

**List top 5 drivers:**
```jinja2
{% set standings = state_attr('sensor.f1_driver_standings', 'driver_standings') %}
{% for d in standings[:5] %}
  P{{ d.position }}: {{ d.Driver.code }} - {{ d.points }} pts
{% endfor %}
```

**Get driver by car number:**
```jinja2
{% set standings = state_attr('sensor.f1_driver_standings', 'driver_standings') %}
{% set driver = standings | selectattr('Driver.permanentNumber', 'eq', '44') | first %}
{% if driver %}
  #44 {{ driver.Driver.familyName }} is P{{ driver.position }}
{% endif %}
```

</details>

---

## Constructor Standings
`sensor.f1_constructor_standings` - Constructor standings snapshot from Ergast.

**State**

- Integer: number of constructors in the standings list.

**Example**
```text
10
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| round | string | Round of the standings snapshot |
| constructor_standings | list | Ergast “ConstructorStandings” array (positions, points, wins, constructor info) |


## Weather (Summary)
`sensor.f1_weather` - Compact weather for the circuit location: current and projected at race start.

**State**
- Number: current air temperature (°C), or `unknown`.

**Example**
```text
18.6
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year for the next race |
| round | string | Round number for the next race |
| race_name | string | Grand Prix name |
| race_url | string | Ergast race URL |
| circuit_id | string | Circuit identifier |
| circuit_name | string | Circuit name |
| circuit_url | string | Circuit URL |
| circuit_lat | string | Latitude |
| circuit_long | string | Longitude |
| circuit_locality | string | City/area |
| circuit_country | string | Country |
| current_temperature | number | Current air temperature (°C) |
| current_temperature_unit | string | “celsius” |
| current_humidity | number | % RH |
| current_humidity_unit | string | “%” |
| current_cloud_cover | number | % cloud cover |
| current_cloud_cover_unit | string | “%” |
| current_precipitation | number | Selected precipitation amount (mm, best effort) |
| current_precipitation_amount_min | number | Min precip amount (mm) if provided |
| current_precipitation_amount_max | number | Max precip amount (mm) if provided |
| current_precipitation_probability | number | Probability of precipitation (%) when provided |
| current_precipitation_probability_unit | string | “%” |
| current_precipitation_unit | string | “mm” |
| current_wind_speed | number | Wind speed (m/s) |
| current_wind_speed_unit | string | “m/s” |
| current_wind_direction | string | Cardinal abbreviation (e.g., "NW") |
| current_wind_from_direction_degrees | number | Wind direction (degrees) |
| current_wind_from_direction_unit | string | "degrees" |
| current_wind_gusts | number | Wind gust speed (m/s) |
| current_wind_gusts_unit | string | "m/s" |
| current_visibility | number | Visibility (m) |
| current_visibility_unit | string | "m" |
| current_weather_code | number | WMO weather interpretation code |
| current_weather_source | string | "open-meteo" |
| race_temperature | number | Projected air temperature at race start (°C) |
| race_temperature_unit | string | “celsius” |
| race_humidity | number | % RH at race start |
| race_humidity_unit | string | “%” |
| race_cloud_cover | number | % at race start |
| race_cloud_cover_unit | string | “%” |
| race_precipitation | number | Selected precipitation at race start (mm) |
| race_precipitation_amount_min | number | Min precip amount (mm) if provided |
| race_precipitation_amount_max | number | Max precip amount (mm) if provided |
| race_precipitation_probability | number | Probability of precipitation (%) when provided |
| race_precipitation_probability_unit | string | “%” |
| race_precipitation_unit | string | “mm” |
| race_wind_speed | number | Wind speed at race start (m/s) |
| race_wind_speed_unit | string | “m/s” |
| race_wind_direction | string | Cardinal abbreviation |
| race_wind_from_direction_degrees | number | Wind direction (degrees) |
| race_wind_from_direction_unit | string | "degrees" |
| race_wind_gusts | number | Projected wind gust speed at race start (m/s) |
| race_wind_gusts_unit | string | "m/s" |
| race_visibility | number | Projected visibility at race start (m) |
| race_visibility_unit | string | "m" |
| race_weather_code | number | WMO weather interpretation code at race start |
| race_weather_source | string | "open-meteo" |
| race_weather_icon | string | MDI icon name matching weather symbol |

---

## Last Race Results
`sensor.f1_last_race_results` - Results of the most recent race; state is the winner’s family name.

**State**
  - String: winner surname, or `unknown`.

**Example**
```text
Verstappen
```

**Attributes**

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
| race_start_utc | string | Race start (UTC ISO‑8601) |
| race_start | string | Race start in Home Assistant local time |
| race_start_local | string | Race start in circuit local time |
| results | list | Cleaned results array: `{number, position, points, status, driver{permanentNumber, code, givenName, familyName}, constructor{constructorId, name}}` |


---

## Season Results
`sensor.f1_season_results` - All results across the current season.

**State**

  - Integer: number of races with results.

**Example**
```text
22
```

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



## Driver Points Progression
`sensor.f1_driver_points_progression` - Per‑round driver points (including sprint) with cumulative series, suitable for charts.

**State**

  - Integer: number of rounds covered.

**Example**
```text
12
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| rounds | list | List of rounds with metadata |
| drivers | object | Map of driver codes to their progression data |
| series | object | Pre-formatted data for charting libraries |

Each entry in `rounds` contains:

| Field | Type | Description |
| --- | --- | --- |
| round | string | Round number |
| race_name | string | Grand Prix name |
| date | string | Race date (YYYY-MM-DD) |

Each entry in `drivers` (keyed by driver code) contains:

| Field | Type | Description |
| --- | --- | --- |
| name | string | Driver's full name |
| code | string | Three-letter driver code |
| driverId | string | Driver identifier |
| points_by_round | list | Points scored in each round |
| cumulative_points | list | Running total of points after each round |
| wins_by_round | list | Wins per round (1 or 0) |
| totals | object | `{ points, wins }` - season totals |

The `series` object contains:

| Field | Type | Description |
| --- | --- | --- |
| labels | list | Round labels for chart X-axis (e.g., ["R1", "R2", ...]) |
| series | list | Array of series objects for charting |

Each entry in `series.series` contains:

| Field | Type | Description |
| --- | --- | --- |
| key | string | Driver code |
| name | string | Driver's full name |
| data | list | Points per round |
| cumulative | list | Cumulative points per round |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "season": "2025",
  "rounds": [
    { "round": "1", "race_name": "Bahrain Grand Prix", "date": "2025-03-02" },
    { "round": "2", "race_name": "Saudi Arabian Grand Prix", "date": "2025-03-09" },
    { "round": "3", "race_name": "Australian Grand Prix", "date": "2025-03-23" }
  ],
  "drivers": {
    "VER": {
      "name": "Max Verstappen",
      "code": "VER",
      "driverId": "max_verstappen",
      "points_by_round": [25, 18, 25],
      "cumulative_points": [25, 43, 68],
      "wins_by_round": [1, 0, 1],
      "totals": {
        "points": 68,
        "wins": 2
      }
    },
    "HAM": {
      "name": "Lewis Hamilton",
      "code": "HAM",
      "driverId": "lewis_hamilton",
      "points_by_round": [18, 25, 15],
      "cumulative_points": [18, 43, 58],
      "wins_by_round": [0, 1, 0],
      "totals": {
        "points": 58,
        "wins": 1
      }
    }
  },
  "series": {
    "labels": ["R1", "R2", "R3"],
    "series": [
      {
        "key": "VER",
        "name": "Max Verstappen",
        "data": [25, 18, 25],
        "cumulative": [25, 43, 68]
      },
      {
        "key": "HAM",
        "name": "Lewis Hamilton",
        "data": [18, 25, 15],
        "cumulative": [18, 43, 58]
      }
    ]
  }
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get a driver's total points:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_points_progression', 'drivers') %}
{% if drivers and drivers.VER %}
  VER total: {{ drivers.VER.totals.points }} points, {{ drivers.VER.totals.wins }} wins
{% endif %}
```

**Get points scored in the last round:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_points_progression', 'drivers') %}
{% if drivers and drivers.VER %}
  {% set pts = drivers.VER.points_by_round %}
  Last round: {{ pts[-1] if pts else 0 }} points
{% endif %}
```

**List rounds with names:**
```jinja2
{% set rounds = state_attr('sensor.f1_driver_points_progression', 'rounds') %}
{% for r in rounds %}
  R{{ r.round }}: {{ r.race_name }} ({{ r.date }})
{% endfor %}
```

**Calculate points gained in last 3 rounds:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_points_progression', 'drivers') %}
{% set ver = drivers.VER %}
{% if ver %}
  {% set last_3 = ver.points_by_round[-3:] | sum %}
  VER last 3 rounds: {{ last_3 }} points
{% endif %}
```

**Get driver with most wins:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_points_progression', 'drivers') %}
{% set winner = drivers.values() | sort(attribute='totals.wins', reverse=true) | first %}
{% if winner %}
  Most wins: {{ winner.code }} with {{ winner.totals.wins }}
{% endif %}
```

</details>

:::tip Chart Integration
The `series` attribute is pre-formatted for use with charting libraries like ApexCharts. See the [Season Progression Charts](/example/season-progression-charts) example for a complete implementation.
:::

---

## Constructor Points Progression
`sensor.f1_constructor_points_progression` - Per‑round constructor points (including sprint) with cumulative series, suitable for charts.

**State**

  - Integer: number of rounds covered.

**Example**
```text
12
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| rounds | list | List of rounds with metadata |
| constructors | object | Map of constructor IDs to their progression data |
| series | object | Pre-formatted data for charting libraries |

Each entry in `rounds` contains:

| Field | Type | Description |
| --- | --- | --- |
| round | string | Round number |
| race_name | string | Grand Prix name |
| date | string | Race date (YYYY-MM-DD) |

Each entry in `constructors` (keyed by constructor ID) contains:

| Field | Type | Description |
| --- | --- | --- |
| name | string | Team name |
| constructorId | string | Constructor identifier |
| points_by_round | list | Points scored in each round |
| cumulative_points | list | Running total of points after each round |
| wins_by_round | list | Wins per round |
| totals | object | `{ points, wins }` - season totals |

The `series` object contains:

| Field | Type | Description |
| --- | --- | --- |
| labels | list | Round labels for chart X-axis (e.g., ["R1", "R2", ...]) |
| series | list | Array of series objects for charting |

Each entry in `series.series` contains:

| Field | Type | Description |
| --- | --- | --- |
| key | string | Constructor ID |
| name | string | Team name |
| data | list | Points per round |
| cumulative | list | Cumulative points per round |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "season": "2025",
  "rounds": [
    { "round": "1", "race_name": "Bahrain Grand Prix", "date": "2025-03-02" },
    { "round": "2", "race_name": "Saudi Arabian Grand Prix", "date": "2025-03-09" },
    { "round": "3", "race_name": "Australian Grand Prix", "date": "2025-03-23" }
  ],
  "constructors": {
    "red_bull": {
      "name": "Red Bull Racing",
      "constructorId": "red_bull",
      "points_by_round": [44, 33, 40],
      "cumulative_points": [44, 77, 117],
      "wins_by_round": [1, 0, 1],
      "totals": {
        "points": 117,
        "wins": 2
      }
    },
    "ferrari": {
      "name": "Ferrari",
      "constructorId": "ferrari",
      "points_by_round": [33, 44, 28],
      "cumulative_points": [33, 77, 105],
      "wins_by_round": [0, 1, 0],
      "totals": {
        "points": 105,
        "wins": 1
      }
    },
    "mclaren": {
      "name": "McLaren",
      "constructorId": "mclaren",
      "points_by_round": [28, 25, 33],
      "cumulative_points": [28, 53, 86],
      "wins_by_round": [0, 0, 0],
      "totals": {
        "points": 86,
        "wins": 0
      }
    }
  },
  "series": {
    "labels": ["R1", "R2", "R3"],
    "series": [
      {
        "key": "red_bull",
        "name": "Red Bull Racing",
        "data": [44, 33, 40],
        "cumulative": [44, 77, 117]
      },
      {
        "key": "ferrari",
        "name": "Ferrari",
        "data": [33, 44, 28],
        "cumulative": [33, 77, 105]
      }
    ]
  }
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get a team's total points:**
```jinja2
{% set constructors = state_attr('sensor.f1_constructor_points_progression', 'constructors') %}
{% if constructors and constructors.red_bull %}
  Red Bull total: {{ constructors.red_bull.totals.points }} points
{% endif %}
```

**Get points scored in the last round:**
```jinja2
{% set constructors = state_attr('sensor.f1_constructor_points_progression', 'constructors') %}
{% set ferrari = constructors.ferrari %}
{% if ferrari %}
  {% set pts = ferrari.points_by_round %}
  Ferrari last round: {{ pts[-1] if pts else 0 }} points
{% endif %}
```

**Calculate gap between two teams:**
```jinja2
{% set c = state_attr('sensor.f1_constructor_points_progression', 'constructors') %}
{% if c.red_bull and c.ferrari %}
  {% set gap = c.red_bull.totals.points - c.ferrari.totals.points %}
  Red Bull leads Ferrari by {{ gap }} points
{% endif %}
```

**Get team with most wins:**
```jinja2
{% set constructors = state_attr('sensor.f1_constructor_points_progression', 'constructors') %}
{% set winner = constructors.values() | sort(attribute='totals.wins', reverse=true) | first %}
{% if winner %}
  Most wins: {{ winner.name }} with {{ winner.totals.wins }}
{% endif %}
```

**List all teams by points:**
```jinja2
{% set constructors = state_attr('sensor.f1_constructor_points_progression', 'constructors') %}
{% for c in constructors.values() | sort(attribute='totals.points', reverse=true) %}
  {{ c.name }}: {{ c.totals.points }} pts
{% endfor %}
```

</details>

:::tip Chart Integration
The `series` attribute is pre-formatted for use with charting libraries like ApexCharts. See the [Season Progression Charts](/example/season-progression-charts) example for a complete implementation.
:::

## Race Week 
`binary_sensor.f1_race_week` - True when the next race is scheduled in the current calendar week.

**State (on/off)**
- `on` during weeks containing the next race date; otherwise `off`.

**Example**
```text
on
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| days_until_next_race | number | Days from today to the next race date |
| next_race_name | string | Grand Prix name of the next race |

---



## Sprint Results

Classification results for all sprint sessions in the current season.

**State**
- Integer: number of sprint races with results, or `0` when none are available.

**Example**
```text
6
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| races | list | List of sprint races with results |

Each entry in `races` contains:

| Field | Type | Description |
| --- | --- | --- |
| round | string | Round number |
| race_name | string | Grand Prix name |
| results | list | List of classification results |

Each entry in `results` contains:

| Field | Type | Description |
| --- | --- | --- |
| number | string | Car number |
| position | string | Final position |
| points | string | Points awarded |
| status | string | Finish status |
| driver | object | `{ permanentNumber, code, givenName, familyName }` |
| constructor | object | `{ name }` |

---

## FIA Decision Documents

::::caution BETA
This sensor is in BETA. Data structure and availability may change as the upstream feed and parsing are refined.
::::

Collects FIA decisions and official documents for the current race weekend.

**State**
- Integer: latest document number (e.g., 27 for "Doc 27"), or `0` when none are available.

**Example**
```text
27
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| name | string | Document title (e.g., "Doc 27 - Penalty Decision") |
| url | string | URL to the FIA document |
| published | string | ISO‑8601 timestamp when the document was published |

The sensor maintains a history of up to 100 documents internally. When a new race weekend starts (detected by "Document 1"), the history is reset.

---

## Season Calendar

`calendar.f1_race_season_calendar` - Native Home Assistant calendar showing every session of the current Formula 1 season.

The calendar appears in the Home Assistant calendar panel and shows each session as a separate event: Practice 1, Practice 2, Practice 3, Qualifying, Sprint Qualifying, Sprint, and Race. On sprint weekends, Practice 3 is replaced by Sprint Qualifying and Sprint.

**State**
- `on` when a session is currently in progress; otherwise `off`.

**Event fields**

| Field | Description |
| --- | --- |
| summary | Session name, e.g. "Monaco Grand Prix - Qualifying" |
| description | Round context, e.g. "Round 7 of the 2025 Formula 1 Season" |
| location | Circuit name, city, and country |
| start | Session start time (UTC) |
| end | Estimated session end time (UTC) |

**Estimated session durations**

| Session | Duration |
| --- | --- |
| Practice 1 | 60 min |
| Practice 2 | 60 min |
| Practice 3 | 60 min |
| Qualifying | 60 min |
| Sprint Qualifying | 45 min |
| Sprint | 35 min |
| Race | 120 min |

::::info
Session end times are estimated based on standard session lengths. Actual sessions may run shorter or longer due to red flags or delays.
::::

**Automation example**

Trigger an automation 30 minutes before any F1 session starts:

```yaml
alias: F1 - Session Starting Soon
description: Notify before any F1 session begins
trigger:
  - platform: calendar
    event: start
    entity_id: calendar.f1_season
    offset: "-00:30:00"
action:
  - service: notify.persistent_notification
    data:
      title: "F1 Session Starting Soon"
      message: "{{ trigger.calendar_event.summary }} starts in 30 minutes"
mode: single
```

::::tip
The calendar entity complements `sensor.f1_current_season`. Use the sensor when you need race data in templates and attributes. Use the calendar when you want a visual schedule or calendar-based automations.
::::

