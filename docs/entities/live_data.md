---
id: live-data
title: Live Data
---

By enabling [live data](/getting-started/add-integration) when configuring the F1 Sensor, Home Assistant can react to live data from an ongoing session such as practice, qualifying, or race. These entities update shortly before, during, and shortly after a session. Outside session times, they become **unavailable**. The only exception is the Driver List sensor, which retains its last known state to support dashboard graphics even between sessions.


:::info F1 Live Timing API
The data for these entities comes from the F1 Live Timing API, which is unofficial. There is no known official documentation, and the API may change without prior notice.
:::

---

## Reference: Enum Values

Use this section to understand the possible values for enum-type states and attributes across all live data sensors.

<details>
<summary>Tyre Compounds</summary>

| Value | Short | Color | Description |
| --- | --- | --- | --- |
| `SOFT` | S | `#FF0000` (red) | Soft compound - fastest, least durable |
| `MEDIUM` | M | `#FFFF00` (yellow) | Medium compound - balanced performance |
| `HARD` | H | `#FFFFFF` (white) | Hard compound - slowest, most durable |
| `INTERMEDIATE` | I | `#00FF00` (green) | Intermediate - light rain conditions |
| `WET` | W | `#0000FF` (blue) | Full wet - heavy rain conditions |

</details>

<details>
<summary>Track Status</summary>

| Value | Description |
| --- | --- |
| `CLEAR` | Normal racing conditions, green flag |
| `YELLOW` | Yellow flag - caution, hazard on track |
| `VSC` | Virtual Safety Car deployed |
| `SC` | Safety Car deployed |
| `RED` | Red flag - session stopped |

</details>

<details>
<summary>Session Status</summary>

| Value | Description |
| --- | --- |
| `pre` | Pre-session, typically 60-15 minutes before start |
| `live` | Session is active (lights out for race) |
| `suspended` | Session temporarily halted |
| `break` | Break between session segments |
| `finished` | Session has finished |
| `finalised` | Results have been finalised |
| `ended` | Session has ended |

**Typical transition flow:** `pre` → `live` → `suspended` ↔ `live` → `finished` → `finalised` → `ended`

</details>

<details>
<summary>Current Session Types</summary>

| Value | Description |
| --- | --- |
| `Practice 1` | First practice session |
| `Practice 2` | Second practice session |
| `Practice 3` | Third practice session |
| `Qualifying` | Qualifying session |
| `Sprint Qualifying` | Sprint qualifying/shootout |
| `Sprint` | Sprint race |
| `Race` | Main race |
| `unknown` | Session type not determined |

</details>

<details>
<summary>Live Timing Mode</summary>

| Value | Description |
| --- | --- |
| `idle` | No active session, connection inactive |
| `live` | Connected to live F1 timing feed |
| `replay` | Playing back recorded session data |

</details>

<details>
<summary>Driver Status (in driver_positions)</summary>

| Value | Description |
| --- | --- |
| `on_track` | Driver is currently on track |
| `pit_in` | Driver is in the pit lane |
| `pit_out` | Driver has just exited pits |
| `out` | Driver has retired or stopped |

</details>

---

### Entities Summary

| Entity                                                | Info                                                                                                                 |  
| --------                                              | --------                                                                                                              |  
| [sensor.f1_session_status](#session-status)           | Current session phase| 
| [sensor.f1_current_session](#current-session)         | Current ongoing session, like Practice 1, Qualification, Race| 
| [sensor.f1_track_status](#track-status)               | Current track status |
| [binary_sensor.f1_safety_car](#safety-car)            | Safety Car (SC) or Virtual Safety Car (VSC) is active|  
| [sensor.f1_race_lap_count](#race-lap)                 | Current race lap number|
| [sensor.f1_track_weather](#track-weather)             | Current on-track weather (air temp, track temp, rainfall, wind speed, etc.)|
| [sensor.f1_driver_list](#driver-list)                 | Show list and details on all drivers, including team color, headshot URL etc| 
| [sensor.f1_pit_stops](#pit-stops)                      | Live pit stop events and aggregated pit stop series per car |
| [sensor.f1_team_radio](#team-radio)                   | Latest team radio message and rolling history |
| [sensor.f1_current_tyres](#current-tyres)             | Current tyre compound per driver |
| [sensor.f1_tyre_statistics](#tyre-statistics)         | Aggregated tyre statistics per compound |
| [sensor.f1_driver_positions](#driver-positions)       | Driver positions and lap times |
| [sensor.f1_top_three_p1](#top-three)                  | Dedicated sensors for current P1, P2 and P3 |
| [sensor.f1_race_control](#race-control)               | Race Control messages feed (flags, incidents, key updates) |
| [binary_sensor.f1_formation_start](#formation-start)  | Indicates when formation start procedure is ready |
| [sensor.f1_championship_prediction_drivers](#championship-prediction-drivers) | Drivers championship prediction (P1 and list) |
| [sensor.f1_championship_prediction_teams](#championship-prediction-teams)| Constructors championship prediction (P1 and list) |


---



:::info Entities
All of these entities update **only in relation to an active session**, typically starting less than an hour before and continuing for a few minutes after the session ends. Outside these windows, the entities will be set to **Unavailable** (not updating and not providing new data).
:::



## Session Status
Semantic session lifecycle based on the live Session Status. The `pre` state usually occurs 60–15 minutes before a session begins. The sensor goes `live` when the session officially starts, for races, this means lights out, not the beginning of the formation lap. 





**State (enum)**
- One of: `pre`, `live`, `suspended`, `break`, `finished`, `finalised`, `ended`.

**Example**
```text
live
```


**Typical transitions**  
`pre → live → suspended ↔ live → finished → finalised → ended`  
After finalised or ended, logic resets and next session begins at **pre**.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| (none) |  | No extra attributes |

---

## Current Session
Human-readable label for the active session. Only shows a state when `sensor.f1_session_status` is `live`

**State (enum/string)**
- `Practice 1`, `Practice 2`, `Practice 3`, `Qualifying`, `Sprint Qualifying`, `Sprint`, `Race`, or `unknown` when inactive (e.g., outside live/eligible windows).

**Example**
```text
Qualifying
```

**Attribute**

| Attribute | Type | Description |
| --- | --- | --- |
| type | string | Raw `Type` from feed (Practice/Qualifying/Race) |
| name | string | Raw `Name` (may carry “Sprint”/“Sprint Qualifying”) |
| number | number | Session number (e.g., 1/2/3 for practice) |
| session_part | number | Detected session part (e.g., 1/2/3 for Q1/Q2/Q3) when available |
| meeting_key | number | Meeting key |
| meeting_name | string | Meeting name |
| meeting_location | string | Location |
| meeting_country | string | Country |
| circuit_short_name | string | Circuit short name |
| gmt_offset | string | Event GMT offset |
| start | string | Session start ISO‑8601 |
| end | string | Session end ISO‑8601 |
| live_status | string | Raw `SessionStatus` message (`Started`, `Finished`, etc.) |
| active | boolean | True when live running is active |
| last_label | string | Last resolved label when not active |

---

## Track Status

Current track status from the live feed. The state is often `CLEAR` even when no session is active.

**State (enum)**
  - One of: `CLEAR`, `YELLOW`, `VSC`, `SC`, `RED`.

**Example**
```text
CLEAR
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| (none) |  | No extra attributes |

---

## Safety Car
On while the Safety Car or Virtual Safety Car is in effect.

**State (on/off)**
- `on` when track status is `SC` or `VSC`; otherwise `off`.

**Example**
```text
on
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| track_status | string | Normalized track status (`CLEAR`, `YELLOW`, `VSC`, `SC`, `RED`) |

---

## Race Lap
Current lap and total laps during the race.

**State**
  - Integer: current lap, or `unknown` if none available or stale cleared.

**Example**
```text
23
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| total_laps | number | Total laps when known; preserved across updates |



::::info Info
This sensor is active only during sprint and race sessions.
::::
---

## Track Weather

Live trackside weather from F1 Live Timing. Updates only in direct connection with a session, and remains unchanged otherwise.

**State**
- Number: air temperature (°C), or `unknown`.

**Example**
```text
18.6
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| air_temperature | number | Air temperature (°C) |
| air_temperature_unit | string | “celsius” |
| humidity | number | % RH |
| humidity_unit | string | “%” |
| pressure | number | hPa |
| pressure_unit | string | “hPa” |
| rainfall | number | mm |
| rainfall_unit | string | “mm” |
| track_temperature | number | Track temperature (°C) |
| track_temperature_unit | string | “celsius” |
| wind_speed | number | m/s |
| wind_speed_unit | string | “m/s” |
| wind_from_direction_degrees | number | Wind direction (degrees) |
| wind_from_direction_unit | string | “degrees” |
| measurement_inferred | boolean | True if payload had no explicit timestamp |


::::info INFO
Updates approximately every minute during an active session.
::::


---

## Driver List

Live roster of drivers with identity and team information for the session.

**State**
- Integer: number of drivers in the list.

**Example**
```text
20
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| drivers | list | List of driver information, sorted by car number |

Each entry in `drivers` contains:

| Field | Type | Description |
| --- | --- | --- |
| racing_number | string | Car number |
| tla | string | Three-letter abbreviation (driver code) |
| name | string | Full name |
| first_name | string | First name |
| last_name | string | Last name |
| team | string | Team name |
| team_color | string | Team color as hex code (e.g., "#3671C6") |
| headshot_small | string | URL to small driver headshot image |
| headshot_large | string | URL to large driver headshot image |
| reference | string | External reference URL or ID |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "drivers": [
    {
      "racing_number": "1",
      "tla": "VER",
      "name": "Max VERSTAPPEN",
      "first_name": "Max",
      "last_name": "Verstappen",
      "team": "Red Bull Racing",
      "team_color": "#3671C6",
      "headshot_small": "https://media.formula1.com/content/dam/fom-website/drivers/M/MAXVER01_Max_Verstappen/maxver01.png",
      "headshot_large": "https://media.formula1.com/content/dam/fom-website/drivers/M/MAXVER01_Max_Verstappen/maxver01-large.png",
      "reference": "max_verstappen"
    },
    {
      "racing_number": "44",
      "tla": "HAM",
      "name": "Lewis HAMILTON",
      "first_name": "Lewis",
      "last_name": "Hamilton",
      "team": "Ferrari",
      "team_color": "#ED1131",
      "headshot_small": "https://media.formula1.com/content/dam/fom-website/drivers/L/LEWHAM01_Lewis_Hamilton/lewham01.png",
      "headshot_large": "https://media.formula1.com/content/dam/fom-website/drivers/L/LEWHAM01_Lewis_Hamilton/lewham01-large.png",
      "reference": "lewis_hamilton"
    }
  ]
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get a driver's headshot URL:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_list', 'drivers') %}
{% set ver = drivers | selectattr('tla', 'eq', 'VER') | first %}
{% if ver %}
  {{ ver.headshot_large }}
{% endif %}
```

**Get team color for styling:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_list', 'drivers') %}
{% set driver = drivers | selectattr('racing_number', 'eq', '44') | first %}
{% if driver %}
  background-color: {{ driver.team_color }};
{% endif %}
```

**List all drivers for a team:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_list', 'drivers') %}
{% for d in drivers if d.team == 'Ferrari' %}
  {{ d.name }} (#{{ d.racing_number }})
{% endfor %}
```

**Create a driver lookup by TLA:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_list', 'drivers') %}
{% set lookup = dict.from_keys(drivers | map(attribute='tla') | list, drivers) %}
{{ lookup.VER.name }} drives for {{ lookup.VER.team }}
```

**Generate image elements for all drivers:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_list', 'drivers') %}
{% for d in drivers %}
  <img src="{{ d.headshot_small }}" alt="{{ d.name }}" style="border: 2px solid {{ d.team_color }}">
{% endfor %}
```

</details>

:::tip Headshot Images
The headshot URLs are provided by F1 and may change between sessions. This sensor retains its last known state between sessions to support dashboard graphics even when no session is active.
:::

---

## Pit Stops

Live pit stop information from the F1 Live Timing feed, aggregated per car.

**State**
- Integer: total number of pit stops recorded in the current session, or `0` when none are available.

**Example**
```text
7
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| cars | object | Map of racing numbers to pit stop details. Each entry contains a list of stops with timestamp, lap, and duration |
| last_update | string | ISO‑8601 timestamp of the last received pit stop event |

::::info INFO
Active during race and sprint sessions.
::::

---

## Team Radio

Latest team radio clip with a rolling history, sourced from the Team Radio stream. This is a curated selection of radio traffic, similar to what is broadcast during TV coverage, not the full raw radio feed.

**State**
- ISO‑8601 timestamp of the most recent radio clip, or `unknown` when none are available.

**Example**
```text
2026-03-14T15:22:31Z
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| utc | string | ISO‑8601 timestamp of the radio clip |
| received_at | string | ISO‑8601 timestamp when Home Assistant received the message |
| racing_number | string | Car number of the driver (e.g., "1", "44") |
| path | string | Relative path to the audio file |
| clip_url | string | Full URL to the audio clip |
| sequence | number | Message counter for deduplication |
| history | list | Rolling list of recent radio clips (up to 20), each with `utc`, `racing_number`, `path`, and `clip_url` |
| raw_message | object | Original payload from the live feed |

::::info INFO
Updates during all live sessions when radio traffic is available.
::::

---

## Current Tyres

Shows the current tyre compound for each driver in the active session.

**State**
- Integer: number of drivers with tyre information available.

**Example**
```text
20
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| drivers | list | List of driver tyre information, sorted by car number |

Each entry in `drivers` contains:

| Field | Type | Description |
| --- | --- | --- |
| racing_number | string | Car number |
| tla | string | Three-letter abbreviation (driver code) |
| team_color | string | Team color as hex code (e.g., "#3671C6") |
| position | string | Current position in the session |
| compound | string | Tyre compound name (e.g., "SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET") |
| compound_short | string | Single-letter abbreviation ("S", "M", "H", "I", "W") |
| compound_color | string | Hex color code for the compound (e.g., "#FF0000" for soft) |
| new | boolean | Whether the tyres are brand new |
| stint_laps | number | Number of laps on the current set |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "drivers": [
    {
      "racing_number": "1",
      "tla": "VER",
      "team_color": "#3671C6",
      "position": "1",
      "compound": "MEDIUM",
      "compound_short": "M",
      "compound_color": "#FFFF00",
      "new": false,
      "stint_laps": 15
    },
    {
      "racing_number": "44",
      "tla": "HAM",
      "team_color": "#ED1131",
      "position": "2",
      "compound": "HARD",
      "compound_short": "H",
      "compound_color": "#FFFFFF",
      "new": true,
      "stint_laps": 3
    },
    {
      "racing_number": "4",
      "tla": "NOR",
      "team_color": "#FF8000",
      "position": "3",
      "compound": "SOFT",
      "compound_short": "S",
      "compound_color": "#FF0000",
      "new": true,
      "stint_laps": 1
    }
  ]
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get a driver's current tyre:**
```jinja2
{% set drivers = state_attr('sensor.f1_current_tyres', 'drivers') %}
{% set ver = drivers | selectattr('tla', 'eq', 'VER') | first %}
{% if ver %}
  VER on {{ ver.compound }} ({{ ver.stint_laps }} laps{% if ver.new %}, NEW{% endif %})
{% endif %}
```

**Count drivers on each compound:**
```jinja2
{% set drivers = state_attr('sensor.f1_current_tyres', 'drivers') %}
{% if drivers %}
  SOFT: {{ drivers | selectattr('compound', 'eq', 'SOFT') | list | length }}
  MEDIUM: {{ drivers | selectattr('compound', 'eq', 'MEDIUM') | list | length }}
  HARD: {{ drivers | selectattr('compound', 'eq', 'HARD') | list | length }}
{% endif %}
```

**List drivers on fresh tyres:**
```jinja2
{% set drivers = state_attr('sensor.f1_current_tyres', 'drivers') %}
{% for d in drivers if d.new %}
  {{ d.tla }} - fresh {{ d.compound }}
{% endfor %}
```

**Find driver with most laps on current stint:**
```jinja2
{% set drivers = state_attr('sensor.f1_current_tyres', 'drivers') %}
{% if drivers %}
  {% set longest = drivers | sort(attribute='stint_laps', reverse=true) | first %}
  {{ longest.tla }} has {{ longest.stint_laps }} laps on {{ longest.compound }}
{% endif %}
```

**Create a tyre summary with colors:**
```jinja2
{% set drivers = state_attr('sensor.f1_current_tyres', 'drivers') %}
{% for d in drivers | sort(attribute='position') %}
  P{{ d.position }} {{ d.tla }}: {{ d.compound_short }} ({{ d.stint_laps }} laps)
{% endfor %}
```

</details>

---

## Tyre Statistics

`sensor.f1_tyre_statistics` - Aggregated tyre performance statistics per compound, showing fastest times and usage across all drivers.

**State**
- String: name of the fastest compound (e.g., "SOFT"), or `unknown` when not available.

**Example**
```text
SOFT
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| fastest_time | string | Overall fastest lap time across all compounds |
| fastest_time_secs | number | Fastest lap time in seconds |
| deltas | object | Time delta to fastest for each compound (e.g., `{"MEDIUM": "+0.342", "HARD": "+0.891"}`) |
| start_compounds | list | List of compounds used at race start, one entry per driver with racing number and compound |
| compounds | object | Detailed statistics per compound |

Each entry in `compounds` (keyed by compound name) contains:

| Field | Type | Description |
| --- | --- | --- |
| best_times | list | Top 3 fastest lap times on this compound |
| total_laps | number | Total laps completed on this compound |
| sets_used | number | Number of new tyre sets used |
| sets_used_total | number | Total stints on this compound |
| compound_color | string | Hex color code for the compound |

Each entry in `best_times` contains:

| Field | Type | Description |
| --- | --- | --- |
| time | string | Lap time (e.g., "1:31.234") |
| racing_number | string | Car number |
| tla | string | Driver code |

Each entry in `start_compounds` contains:

| Field | Type | Description |
| --- | --- | --- |
| racing_number | string | Car number |
| compound | string | Tyre compound used at race start |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "fastest_time": "1:31.234",
  "fastest_time_secs": 91.234,
  "deltas": {
    "SOFT": "+0.000",
    "MEDIUM": "+0.342",
    "HARD": "+0.891"
  },
  "start_compounds": [
    { "racing_number": "1", "compound": "MEDIUM" },
    { "racing_number": "44", "compound": "HARD" },
    { "racing_number": "4", "compound": "MEDIUM" }
  ],
  "compounds": {
    "SOFT": {
      "best_times": [
        { "time": "1:31.234", "racing_number": "1", "tla": "VER" },
        { "time": "1:31.456", "racing_number": "4", "tla": "NOR" },
        { "time": "1:31.567", "racing_number": "44", "tla": "HAM" }
      ],
      "total_laps": 45,
      "sets_used": 8,
      "sets_used_total": 12,
      "compound_color": "#FF0000"
    },
    "MEDIUM": {
      "best_times": [
        { "time": "1:31.576", "racing_number": "1", "tla": "VER" },
        { "time": "1:31.789", "racing_number": "16", "tla": "LEC" }
      ],
      "total_laps": 120,
      "sets_used": 15,
      "sets_used_total": 20,
      "compound_color": "#FFFF00"
    },
    "HARD": {
      "best_times": [
        { "time": "1:32.125", "racing_number": "63", "tla": "RUS" }
      ],
      "total_laps": 80,
      "sets_used": 6,
      "sets_used_total": 8,
      "compound_color": "#FFFFFF"
    }
  }
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get the fastest compound:**
```jinja2
Fastest compound: {{ states('sensor.f1_tyre_statistics') }}
```

**Get fastest time on a specific compound:**
```jinja2
{% set compounds = state_attr('sensor.f1_tyre_statistics', 'compounds') %}
{% if compounds and compounds.SOFT %}
  {% set best = compounds.SOFT.best_times | first %}
  Fastest on SOFT: {{ best.time }} by {{ best.tla }}
{% endif %}
```

**Show delta between compounds:**
```jinja2
{% set deltas = state_attr('sensor.f1_tyre_statistics', 'deltas') %}
{% if deltas %}
  MEDIUM vs SOFT: {{ deltas.MEDIUM | default('N/A') }}
  HARD vs SOFT: {{ deltas.HARD | default('N/A') }}
{% endif %}
```

**Count drivers who started on each compound:**
```jinja2
{% set starts = state_attr('sensor.f1_tyre_statistics', 'start_compounds') %}
{% if starts %}
  {% set mediums = starts | selectattr('compound', 'eq', 'MEDIUM') | list | length %}
  {% set hards = starts | selectattr('compound', 'eq', 'HARD') | list | length %}
  Started on MEDIUM: {{ mediums }}
  Started on HARD: {{ hards }}
{% endif %}
```

**Get total laps on all compounds:**
```jinja2
{% set compounds = state_attr('sensor.f1_tyre_statistics', 'compounds') %}
{% if compounds %}
  {% set total = namespace(laps=0) %}
  {% for name, data in compounds.items() %}
    {% set total.laps = total.laps + (data.total_laps | default(0)) %}
  {% endfor %}
  Total tyre laps recorded: {{ total.laps }}
{% endif %}
```

</details>

:::tip Compound Colors
Use the `compound_color` field to style your dashboard elements. The colors match the official Pirelli tyre colors: SOFT (red), MEDIUM (yellow), HARD (white), INTERMEDIATE (green), WET (blue).
:::

---

## Driver Positions

`sensor.f1_driver_positions` - Live driver positions and lap-by-lap timing data for all drivers in the session.

**State**
- Integer: current lap number (leader's lap), or `unknown` when not available.

**Example**
```text
45
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| drivers | object | Map of racing numbers to driver position and timing data |
| total_laps | number | Total race distance in laps, when known |

Each entry in `drivers` (keyed by racing number) contains:

| Field | Type | Description |
| --- | --- | --- |
| racing_number | string | Car number |
| tla | string | Three-letter abbreviation (driver code) |
| name | string | Driver's full name |
| team | string | Team name |
| team_color | string | Team color as hex code (e.g., "#3671C6") |
| grid_position | string | Starting grid position |
| current_position | string | Current position in the session |
| laps | object | Map of lap numbers to lap times (e.g., `{"1": "1:32.456", "2": "1:31.789"}`) |
| completed_laps | number | Number of laps completed by this driver |
| status | string | Driver status: `on_track`, `pit_in`, `pit_out`, or `out` |
| in_pit | boolean | Whether driver is currently in pit lane |
| pit_out | boolean | Whether driver just exited pits |
| retired | boolean | Whether driver has retired from the session |
| stopped | boolean | Whether driver has stopped on track |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "drivers": {
    "1": {
      "racing_number": "1",
      "tla": "VER",
      "name": "Max Verstappen",
      "team": "Red Bull Racing",
      "team_color": "#3671C6",
      "grid_position": "1",
      "current_position": "1",
      "laps": {
        "1": "1:32.456",
        "2": "1:31.789",
        "3": "1:31.234"
      },
      "completed_laps": 45,
      "status": "on_track",
      "in_pit": false,
      "pit_out": false,
      "retired": false,
      "stopped": false
    },
    "44": {
      "racing_number": "44",
      "tla": "HAM",
      "name": "Lewis Hamilton",
      "team": "Ferrari",
      "team_color": "#ED1131",
      "grid_position": "3",
      "current_position": "2",
      "laps": {
        "1": "1:33.012",
        "2": "1:31.567",
        "3": "1:31.890"
      },
      "completed_laps": 45,
      "status": "on_track",
      "in_pit": false,
      "pit_out": false,
      "retired": false,
      "stopped": false
    }
  },
  "total_laps": 70
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get the race leader:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% if drivers %}
  {% set leader = drivers.values() | selectattr('current_position', 'eq', '1') | first %}
  {% if leader %}
    Leader: {{ leader.tla }} ({{ leader.name }})
  {% endif %}
{% endif %}
```

**Get a specific driver by number:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% set driver = drivers.get('44') %}
{% if driver %}
  {{ driver.name }} is in P{{ driver.current_position }}
{% endif %}
```

**Get driver's last lap time:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% set driver = drivers.get('1') %}
{% if driver and driver.laps %}
  {% set last_lap = driver.completed_laps | string %}
  Last lap: {{ driver.laps.get(last_lap, 'N/A') }}
{% endif %}
```

**List all drivers in pit lane:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% for num, d in drivers.items() if d.status == 'pit_in' %}
  {{ d.tla }} is in the pits
{% endfor %}
```

**Show race progress:**
```jinja2
{% set current = states('sensor.f1_driver_positions') %}
{% set total = state_attr('sensor.f1_driver_positions', 'total_laps') %}
{% if current != 'unknown' and total %}
  Lap {{ current }} of {{ total }}
{% endif %}
```

**Get position changes from grid:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% for num, d in drivers.items() %}
  {% set change = d.grid_position | int - d.current_position | int %}
  {{ d.tla }}: {% if change > 0 %}+{% endif %}{{ change }}
{% endfor %}
```

</details>

::::info INFO
This sensor retains its last known state between sessions to support dashboard displays.
::::

---

## Top Three

Three dedicated sensors for the current P1, P2, and P3 positions: `sensor.f1_top_three_p1`, `sensor.f1_top_three_p2`, and `sensor.f1_top_three_p3`.

**State**
- Driver TLA code (e.g., "VER", "HAM", "NOR"), or `unknown` when data is withheld or unavailable.

**Example**
```text
VER
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| withheld | boolean | Whether the position is currently withheld by broadcast rules |
| position | number | Position in the standings (1, 2, or 3) |
| racing_number | string | Car number |
| tla | string | Three-letter abbreviation (driver code) |
| broadcast_name | string | Name as shown on broadcast |
| full_name | string | Driver's full name |
| first_name | string | Driver's first name |
| last_name | string | Driver's last name |
| team | string | Team name |
| team_color | string | Team color as hex code (e.g., "#3671C6") |
| lap_time | string | Current lap time when available |
| overall_fastest | boolean | Whether this is the overall fastest lap |
| personal_fastest | boolean | Whether this is the driver's personal best |
| last_update_ts | string | ISO‑8601 timestamp of the last update |

::::info INFO
Available during qualifying, sprint, and race sessions. When the broadcast withholds position data (common at session start), the `withheld` attribute will be `true` and the state will be `unknown`.
::::

---

## Race Control

Feed-style sensor exposing Race Control messages such as flags, incidents, and key session updates. This data is also sent on the [event bus](/entities/events).

**State**
- The latest Race Control message text (max 255 characters), or `unknown` when none are available.

**Example**
```text
YELLOW FLAG IN TURN 4
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| utc | string | ISO‑8601 timestamp when the message was issued |
| received_at | string | ISO‑8601 timestamp when Home Assistant received it |
| category | string | Type of message (e.g., "Flag", "SafetyCar", "Other") |
| flag | string | Flag type when applicable (e.g., "YELLOW", "GREEN", "RED") |
| scope | string | Scope of the message (e.g., "Track", "Sector") |
| sector | string | Track sector affected, if applicable |
| car_number | string | Car number involved, if applicable |
| message | string | Full message text |
| event_id | string | Composite ID for deduplication |
| sequence | number | Message counter |
| history | list | Rolling list of recent messages (up to 5), each with `event_id`, `utc`, `category`, `flag`, and `message` |
| raw_message | object | Original payload from the live feed |

---

## Championship Prediction (Drivers)

Predicted Drivers Championship winner and points table, sourced from the live ChampionshipPrediction stream.

**State**
- Predicted P1 driver TLA, or `unknown` when not available.

**Example**
```text
VER
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| predicted_driver_p1 | object | The driver currently predicted to lead the championship |
| drivers | object | Map of all drivers keyed by racing number |
| last_update | string | ISO-8601 timestamp of the last prediction update |

The `predicted_driver_p1` object contains:

| Field | Type | Description |
| --- | --- | --- |
| racing_number | string | Car number |
| tla | string | Three-letter abbreviation |
| points | number | Predicted final points |
| entry | object | Full entry data from the feed |

Each entry in `drivers` (keyed by racing number) contains:

| Field | Type | Description |
| --- | --- | --- |
| RacingNumber | string | Car number |
| CurrentPosition | number | Current championship position |
| PredictedPosition | number | Predicted final position |
| CurrentPoints | number | Current points total |
| PredictedPoints | number | Predicted final points |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "predicted_driver_p1": {
    "racing_number": "1",
    "tla": "VER",
    "points": 450,
    "entry": {
      "RacingNumber": "1",
      "CurrentPosition": 1,
      "PredictedPosition": 1,
      "CurrentPoints": 350,
      "PredictedPoints": 450
    }
  },
  "drivers": {
    "1": {
      "RacingNumber": "1",
      "CurrentPosition": 1,
      "PredictedPosition": 1,
      "CurrentPoints": 350,
      "PredictedPoints": 450
    },
    "44": {
      "RacingNumber": "44",
      "CurrentPosition": 2,
      "PredictedPosition": 2,
      "CurrentPoints": 280,
      "PredictedPoints": 380
    },
    "4": {
      "RacingNumber": "4",
      "CurrentPosition": 3,
      "PredictedPosition": 3,
      "CurrentPoints": 260,
      "PredictedPoints": 350
    }
  },
  "last_update": "2025-06-15T14:32:45Z"
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get predicted champion:**
```jinja2
{% set p1 = state_attr('sensor.f1_championship_prediction_drivers', 'predicted_driver_p1') %}
{% if p1 %}
  Predicted champion: {{ p1.tla }} with {{ p1.points }} points
{% endif %}
```

**Show points gain prediction for a driver:**
```jinja2
{% set drivers = state_attr('sensor.f1_championship_prediction_drivers', 'drivers') %}
{% set ver = drivers.get('1') %}
{% if ver %}
  {% set gain = ver.PredictedPoints - ver.CurrentPoints %}
  VER: {{ ver.CurrentPoints }} -> {{ ver.PredictedPoints }} (+{{ gain }})
{% endif %}
```

**List drivers predicted to gain positions:**
```jinja2
{% set drivers = state_attr('sensor.f1_championship_prediction_drivers', 'drivers') %}
{% for num, d in drivers.items() if d.PredictedPosition < d.CurrentPosition %}
  #{{ num }}: P{{ d.CurrentPosition }} -> P{{ d.PredictedPosition }}
{% endfor %}
```

**Calculate predicted gap to leader:**
```jinja2
{% set p1 = state_attr('sensor.f1_championship_prediction_drivers', 'predicted_driver_p1') %}
{% set drivers = state_attr('sensor.f1_championship_prediction_drivers', 'drivers') %}
{% set ham = drivers.get('44') %}
{% if p1 and ham %}
  Gap to leader: {{ p1.points - ham.PredictedPoints }} points
{% endif %}
```

</details>

---

## Championship Prediction (Teams)

Predicted Constructors Championship winner and points table, sourced from the live ChampionshipPrediction stream.

**State**
- Predicted P1 team name, or `unknown` when not available.

**Example**
```text
Red Bull Racing
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| predicted_team_p1 | object | The team currently predicted to lead the constructors' championship |
| teams | object | Map of all teams keyed by team key |
| last_update | string | ISO-8601 timestamp of the last prediction update |

The `predicted_team_p1` object contains:

| Field | Type | Description |
| --- | --- | --- |
| team_key | string | Team identifier |
| team_name | string | Team display name |
| points | number | Predicted final points |
| entry | object | Full entry data from the feed |

Each entry in `teams` (keyed by team key) contains:

| Field | Type | Description |
| --- | --- | --- |
| TeamKey | string | Team identifier |
| TeamName | string | Team display name |
| CurrentPosition | number | Current championship position |
| PredictedPosition | number | Predicted final position |
| CurrentPoints | number | Current points total |
| PredictedPoints | number | Predicted final points |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "predicted_team_p1": {
    "team_key": "red_bull",
    "team_name": "Red Bull Racing",
    "points": 850,
    "entry": {
      "TeamKey": "red_bull",
      "TeamName": "Red Bull Racing",
      "CurrentPosition": 1,
      "PredictedPosition": 1,
      "CurrentPoints": 650,
      "PredictedPoints": 850
    }
  },
  "teams": {
    "red_bull": {
      "TeamKey": "red_bull",
      "TeamName": "Red Bull Racing",
      "CurrentPosition": 1,
      "PredictedPosition": 1,
      "CurrentPoints": 650,
      "PredictedPoints": 850
    },
    "ferrari": {
      "TeamKey": "ferrari",
      "TeamName": "Ferrari",
      "CurrentPosition": 2,
      "PredictedPosition": 2,
      "CurrentPoints": 520,
      "PredictedPoints": 700
    },
    "mclaren": {
      "TeamKey": "mclaren",
      "TeamName": "McLaren",
      "CurrentPosition": 3,
      "PredictedPosition": 3,
      "CurrentPoints": 480,
      "PredictedPoints": 650
    }
  },
  "last_update": "2025-06-15T14:32:45Z"
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get predicted constructors champion:**
```jinja2
{% set p1 = state_attr('sensor.f1_championship_prediction_teams', 'predicted_team_p1') %}
{% if p1 %}
  Predicted constructors champion: {{ p1.team_name }}
{% endif %}
```

**Compare two teams:**
```jinja2
{% set teams = state_attr('sensor.f1_championship_prediction_teams', 'teams') %}
{% set rb = teams.get('red_bull') %}
{% set ferrari = teams.get('ferrari') %}
{% if rb and ferrari %}
  Gap: {{ rb.PredictedPoints - ferrari.PredictedPoints }} points
{% endif %}
```

**List teams by predicted finish:**
```jinja2
{% set teams = state_attr('sensor.f1_championship_prediction_teams', 'teams') %}
{% for key, t in teams.items() | sort(attribute='1.PredictedPosition') %}
  P{{ t.PredictedPosition }}: {{ t.TeamName }} ({{ t.PredictedPoints }} pts)
{% endfor %}
```

**Show teams predicted to change position:**
```jinja2
{% set teams = state_attr('sensor.f1_championship_prediction_teams', 'teams') %}
{% for key, t in teams.items() if t.PredictedPosition != t.CurrentPosition %}
  {{ t.TeamName }}: P{{ t.CurrentPosition }} -> P{{ t.PredictedPosition }}
{% endfor %}
```

</details>

---

## Formation Start

Indicates when the formation start procedure is ready. Useful for triggering automations at race start.

**State (on/off)**
- `on` when formation start procedure is ready; otherwise `off`.

**Example**
```text
on
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| status | string | Current status (e.g., "ready", "waiting", "active") |
| scheduled_start | string | ISO‑8601 scheduled start time |
| formation_start | string | ISO‑8601 timestamp when formation start actually happened |
| delta_seconds | number | Seconds between scheduled and actual start |
| source | string | How the data was derived |
| session_type | string | Type of session (e.g., "Race", "Sprint") |
| session_name | string | Name of the session |
| error | string | Error message if any issue occurred |

::::info INFO
Active only during race and sprint sessions.
::::


