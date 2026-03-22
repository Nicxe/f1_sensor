---
id: live-data
title: Live Data
---

By enabling [live data](/getting-started/add-integration) when configuring the F1 Sensor, Home Assistant can react to live data from an ongoing session such as practice, qualifying, or race. These entities update shortly before, during, and shortly after a session. Outside session times, they become **unavailable**. The only exception is the Driver List sensor, which retains its last known state to support dashboard graphics even between sessions.

:::info Entity IDs vs display names
This page documents the standard `entity_id` for each entity, for example `sensor.f1_track_status`.

Display names in Home Assistant can be localized, and older installations may already use different registry IDs. If you cannot find an entity by name, search for the documented `entity_id` or for the `f1_` suffix in the entity list.
:::

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

<details>
<summary>Straight Mode (2026 regulation)</summary>

| Value | Description |
| --- | --- |
| `normal_grip` | Normal aerodynamic configuration permitted on straight sections |
| `low_grip` | Restricted aerodynamic configuration on straight sections |
| `disabled` | Straight mode system is not active |

</details>

---

### Entities Summary

| Entity                                                | Info                                                                                                                 |  
| --------                                              | --------                                                                                                              |  
| [sensor.f1_session_status](#session-status)           | Current session phase|
| [sensor.f1_current_session](#current-session)         | Current ongoing session, like Practice 1, Qualification, Race|
| [sensor.f1_session_time_elapsed](#session-time-elapsed) | Time elapsed in the current session `(beta)` |
| [sensor.f1_session_time_remaining](#session-time-remaining) | Time remaining in the current session `(beta)` |
| [sensor.f1_race_three_hour_limit](#race-three-hour-limit) | Time remaining until the FIA 3-hour race duration cap `(beta)` |
| [sensor.f1_track_status](#track-status)               | Current track status |
| [binary_sensor.f1_safety_car](#safety-car)            | Safety Car (SC) or Virtual Safety Car (VSC) is active|  
| [sensor.f1_race_lap_count](#race-lap)                 | Current race lap number|
| [sensor.f1_track_weather](#track-weather)             | Current on-track weather (air temp, track temp, rainfall, wind speed, etc.)|
| [sensor.f1_driver_list](#driver-list)                 | Show list and details on all drivers, including team color, headshot URL etc| 
| [sensor.f1_pitstops](#pit-stops)                      | Live pit stop events and aggregated pit stop series per car `(Replay Mode only)` |
| [sensor.f1_team_radio](#team-radio)                   | Latest team radio message and rolling history `(Replay Mode only)` |
| [sensor.f1_current_tyres](#current-tyres)             | Current tyre compound per driver |
| [sensor.f1_tyre_statistics](#tyre-statistics)         | Aggregated tyre statistics per compound |
| [sensor.f1_driver_positions](#driver-positions)       | Driver positions and lap times |
| [sensor.f1_top_three_p1](#top-three)                  | Dedicated sensors for current P1, P2 and P3 |
| [sensor.f1_race_control](#race-control)               | Race Control messages feed (flags, incidents, key updates) |
| [sensor.f1_track_limits](#track-limits)               | Track limits violations per driver (deletions, warnings, penalties) |
| [sensor.f1_investigations](#investigations)           | Active steward investigations and pending penalties |
| [binary_sensor.f1_formation_start](#formation-start)  | Indicates when formation start procedure is ready `(Replay Mode only)` |
| [sensor.f1_championship_prediction_drivers](#championship-prediction-drivers) | Drivers championship prediction (P1 and list) `(Replay Mode only)` |
| [sensor.f1_championship_prediction_teams](#championship-prediction-teams)| Constructors championship prediction (P1 and list) `(Replay Mode only)` |
| [binary_sensor.f1_overtake_mode](#overtake-mode)      | ON when track-wide overtake mode is enabled (2026 regulation, experimental) |
| [sensor.f1_straight_mode](#straight-mode)             | Active aerodynamic straight mode state (2026 regulation, experimental) |


---



:::info Entities
All of these entities update **only in relation to an active session**, typically starting less than an hour before and continuing for a few minutes after the session ends. Outside these windows, the entities will be set to **Unavailable** (not updating and not providing new data).
:::

:::note Replay Mode only entities
Some entities are marked `(Replay Mode only)` in the table above. These entities stay registered in Home Assistant, but they are unavailable outside [Replay Mode](/features/replay-mode) because the underlying data streams require authentication that the integration does not currently support during live sessions. When you start a replay, they begin updating normally.

The affected entities are: Pit Stops, Team Radio, Championship Prediction (Drivers), Championship Prediction (Teams), and Formation Start.
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
| meeting_name | string | Meeting name (e.g., "Monaco Grand Prix") |
| meeting_location | string | Meeting location (e.g., "Monte Carlo") |
| meeting_country | string | Meeting country (e.g., "Monaco") |
| circuit_short_name | string | Circuit short name (e.g., "Monaco") |
| gmt_offset | string | Event GMT offset |
| start | string | Session start ISO‑8601 |
| end | string | Session end ISO‑8601 |
| track_grip | string | Track grip state from Race Control, when available (best effort) |

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

## Session Time Elapsed

:::caution Beta
This sensor is currently in beta. The behavior has not been verified across all session types, edge cases (red flags, suspensions, qualifying segments), and timing scenarios. Treat the values as indicative rather than definitive until further testing is complete.
:::

`sensor.f1_session_time_elapsed` - How much of the scheduled session time has passed, based on the F1 ExtrapolatedClock feed. The clock advances in real time while a session is running and pauses during interruptions such as red flags or safety car delays.

**State**
- String: elapsed time formatted as `H:MM:SS` (e.g., `0:23:45`), or `unavailable` when no data is available.

**Example**
```text
0:23:45
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| session_type | string | Session type (e.g., "Practice", "Qualifying", "Race") |
| session_name | string | Session name (e.g., "Practice 1", "Race") |
| session_part | number | Session part, for example the qualifying segment (Q1/Q2/Q3) |
| session_status | string | Current session status from the feed |
| clock_phase | string | Clock state: `idle`, `running`, `paused`, or `finished` |
| clock_running | boolean | Whether the clock is actively counting |
| source_quality | string | Data source reliability (see below) |
| session_start_utc | string | ISO‑8601 timestamp of the session start |
| reference_utc | string | ISO‑8601 timestamp used as the clock reference point |
| last_server_utc | string | ISO‑8601 timestamp of the last server heartbeat |
| value_seconds | number | Elapsed time in whole seconds |
| formatted_hms | string | Elapsed time formatted as `H:MM:SS` |
| clock_total_s | number | Total scheduled session duration in seconds, when known |
| clock_remaining_s | number | Remaining time in seconds, when known |

**`source_quality` values**

| Value | Description |
| --- | --- |
| `official` | Clock data from ExtrapolatedClock with server heartbeat confirmation |
| `official_no_heartbeat` | Clock data from ExtrapolatedClock, but no heartbeat received yet |
| `sessiondata_fallback` | Elapsed time estimated from session schedule data, not from the live clock feed |
| `unavailable` | No usable timing data available |

---

## Session Time Remaining

:::caution Beta
This sensor is currently in beta. The behavior has not been verified across all session types, edge cases (red flags, suspensions, qualifying segments), and timing scenarios. Treat the values as indicative rather than definitive until further testing is complete.
:::

`sensor.f1_session_time_remaining` - How much scheduled session time is left, based on the F1 ExtrapolatedClock feed. Like the elapsed sensor, this clock pauses during interruptions and resumes when the session restarts.

**State**
- String: remaining time formatted as `H:MM:SS` (e.g., `0:36:15`), or `unavailable` when no data is available.

**Example**
```text
0:36:15
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| session_type | string | Session type (e.g., "Practice", "Qualifying", "Race") |
| session_name | string | Session name (e.g., "Practice 1", "Race") |
| session_part | number | Session part, for example the qualifying segment (Q1/Q2/Q3) |
| session_status | string | Current session status from the feed |
| clock_phase | string | Clock state: `idle`, `running`, `paused`, or `finished` |
| clock_running | boolean | Whether the clock is actively counting |
| source_quality | string | Data source reliability (see `source_quality` values above) |
| session_start_utc | string | ISO‑8601 timestamp of the session start |
| reference_utc | string | ISO‑8601 timestamp used as the clock reference point |
| last_server_utc | string | ISO‑8601 timestamp of the last server heartbeat |
| value_seconds | number | Remaining time in whole seconds |
| formatted_hms | string | Remaining time formatted as `H:MM:SS` |
| clock_total_s | number | Total scheduled session duration in seconds, when known |

:::info Session clock behavior
The session clock counts down the scheduled duration of the session. It does not account for race laps — in a race, the session ends when the leader completes the required number of laps, which may happen before or (rarely) after the scheduled time expires. Use `sensor.f1_race_lap_count` for lap-based progress.
:::

---

## Race Three Hour Limit

:::caution Beta
This sensor is currently in beta. The behavior has not been verified across all edge cases and timing scenarios. Treat the values as indicative rather than definitive until further testing is complete.
:::

`sensor.f1_race_three_hour_limit` - Time remaining until the FIA three-hour race duration cap is reached. This sensor is only available during the main race session (not sprint races).

Under FIA regulations, a race must finish within three hours of the original start time. This sensor counts down to that absolute limit, independently of the session clock which may be paused during red flags.

**State**
- String: remaining time formatted as `H:MM:SS` (e.g., `2:14:30`), or `unavailable` when no data is available or outside the main race.

**Example**
```text
2:14:30
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| session_type | string | Session type (e.g., "Race") |
| session_name | string | Session name (e.g., "Race") |
| session_part | number | Session part, when available |
| session_status | string | Current session status from the feed |
| clock_phase | string | Clock state: `idle`, `running`, `paused`, or `finished` |
| clock_running | boolean | Whether the clock is actively counting |
| source_quality | string | Data source reliability (see `source_quality` values above) |
| session_start_utc | string | ISO‑8601 timestamp of the session start |
| reference_utc | string | ISO‑8601 timestamp used as the clock reference point |
| last_server_utc | string | ISO‑8601 timestamp of the last server heartbeat |
| value_seconds | number | Remaining time until three-hour cap in whole seconds |
| formatted_hms | string | Remaining time formatted as `H:MM:SS` |
| race_start_utc | string | ISO‑8601 timestamp of the race start |
| race_three_hour_cap_utc | string | ISO‑8601 timestamp of the three-hour deadline |

::::info Info
This sensor is only available during the main race session. It becomes unavailable during practice, qualifying, and sprint sessions.
::::

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
| team_color_rgb | list | Team color as RGB values (e.g., `[54, 113, 198]`) |
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
      "team_color_rgb": [54, 113, 198],
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
      "team_color_rgb": [237, 17, 49],
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

**Set a light to a driver's team color:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_list', 'drivers') %}
{% set ver = drivers | selectattr('tla', 'eq', 'VER') | first %}
{% if ver and ver.team_color_rgb %}
service: light.turn_on
data:
  entity_id: light.living_room
  rgb_color: {{ ver.team_color_rgb }}
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

:::note Replay Mode only
This entity stays registered in Home Assistant and is unavailable outside [Replay Mode](/features/replay-mode). The pit stop data stream requires authentication that the integration does not currently support during live sessions.
:::

`sensor.f1_pitstops` - Pit stop information from the F1 Live Timing feed, aggregated per car.

**State**
- Integer: total number of pit stops recorded in the current session, or `0` when none are available.

**Example**
```text
7
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| cars | object | Map of racing numbers to pit stop details |
| last_update | string | ISO‑8601 timestamp of the last received pit stop event |

Each entry in `cars` (keyed by racing number) contains:

| Field | Type | Description |
| --- | --- | --- |
| tla | string | Driver code (TLA) when available |
| name | string | Driver name when available |
| team | string | Team name when available |
| count | number | Number of pit stops recorded for the car |
| stops | list | List of pit stops (most recent stops kept, best effort) |

Each entry in `stops` contains:

| Field | Type | Description |
| --- | --- | --- |
| lap | number | Lap number when the stop happened |
| timestamp | string | Timestamp from the feed when available |
| pit_stop_time | number | Stationary time (seconds), when available |
| pit_lane_time | number | Total pit lane time (seconds), when available |
| pit_delta | number | Estimated loss vs a normal lap (seconds), when available |

::::info INFO
Available during race and sprint sessions in Replay Mode.
::::

---

## Team Radio

:::note Replay Mode only
This entity stays registered in Home Assistant and is unavailable outside [Replay Mode](/features/replay-mode). The team radio data stream requires authentication that the integration does not currently support during live sessions.
:::

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
Available during Replay Mode sessions when radio traffic is present in the session archive.
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
| team_color_rgb | list | Team color as RGB values (e.g., `[54, 113, 198]`) |
| position | string | Current position in the session |
| compound | string | Tyre compound name (e.g., "SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET") |
| compound_short | string | Single-letter abbreviation ("S", "M", "H", "I", "W") |
| compound_color | string | Hex color code for the compound (e.g., "#FF0000" for soft) |
| compound_color_rgb | list | Compound color as RGB values (e.g., `[255, 0, 0]` for soft) |
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
      "team_color_rgb": [54, 113, 198],
      "position": "1",
      "compound": "MEDIUM",
      "compound_short": "M",
      "compound_color": "#FFFF00",
      "compound_color_rgb": [255, 255, 0],
      "new": false,
      "stint_laps": 15
    },
    {
      "racing_number": "44",
      "tla": "HAM",
      "team_color": "#ED1131",
      "team_color_rgb": [237, 17, 49],
      "position": "2",
      "compound": "HARD",
      "compound_short": "H",
      "compound_color": "#FFFFFF",
      "compound_color_rgb": [255, 255, 255],
      "new": true,
      "stint_laps": 3
    },
    {
      "racing_number": "4",
      "tla": "NOR",
      "team_color": "#FF8000",
      "team_color_rgb": [255, 128, 0],
      "position": "3",
      "compound": "SOFT",
      "compound_short": "S",
      "compound_color": "#FF0000",
      "compound_color_rgb": [255, 0, 0],
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
| compound_color_rgb | list | Compound color as RGB values (e.g., `[255, 0, 0]` for soft) |

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
      "compound_color": "#FF0000",
      "compound_color_rgb": [255, 0, 0]
    },
    "MEDIUM": {
      "best_times": [
        { "time": "1:31.576", "racing_number": "1", "tla": "VER" },
        { "time": "1:31.789", "racing_number": "16", "tla": "LEC" }
      ],
      "total_laps": 120,
      "sets_used": 15,
      "sets_used_total": 20,
      "compound_color": "#FFFF00",
      "compound_color_rgb": [255, 255, 0]
    },
    "HARD": {
      "best_times": [
        { "time": "1:32.125", "racing_number": "63", "tla": "RUS" }
      ],
      "total_laps": 80,
      "sets_used": 6,
      "sets_used_total": 8,
      "compound_color": "#FFFFFF",
      "compound_color_rgb": [255, 255, 255]
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
| drivers | list | List of drivers, sorted by position when available |
| total_laps | number | Total race distance in laps, when known |
| fastest_lap | object | Fastest lap details during races and sprints; `null` in other session types |
| current_qualifying_part | number | Active qualifying segment (1, 2, or 3); `null` outside qualifying sessions |

Each entry in `drivers` contains:

| Field | Type | Description |
| --- | --- | --- |
| racing_number | string | Car number |
| tla | string | Three-letter abbreviation (driver code) |
| name | string | Driver's full name |
| team | string | Team name |
| team_color | string | Team color as hex code (e.g., "#3671C6") |
| team_color_rgb | list | Team color as RGB values (e.g., `[54, 113, 198]`) |
| grid_position | string | Starting grid position |
| current_position | string | Current position in the session |
| laps | object | Map of lap numbers to lap times (e.g., `{"1": "1:32.456", "2": "1:31.789"}`) |
| completed_laps | number | Number of laps completed by this driver |
| status | string | Driver status: `on_track`, `pit_in`, `pit_out`, or `out` |
| in_pit | boolean | Whether driver is currently in pit lane |
| pit_out | boolean | Whether driver just exited pits |
| retired | boolean | Whether driver has retired from the session |
| stopped | boolean | Whether driver has stopped on track |
| fastest_lap | boolean | True if this driver currently holds fastest lap (race/sprint only) |
| fastest_lap_time | string | Fastest lap time (race/sprint only) |
| fastest_lap_time_secs | number | Fastest lap time in seconds (race/sprint only) |
| fastest_lap_lap | number | Lap number of the fastest lap (race/sprint only) |
| sector_1 | number | Current sector 1 time in seconds; `null` while sector has not been completed this lap |
| sector_2 | number | Current sector 2 time in seconds; `null` while not yet completed |
| sector_3 | number | Current sector 3 time in seconds; `null` while not yet completed |
| sector_1_overall_fastest | boolean | True if the current sector 1 time is the fastest by any driver this session |
| sector_1_personal_fastest | boolean | True if the current sector 1 time is this driver's personal best |
| sector_2_overall_fastest | boolean | True if the current sector 2 time is the overall fastest |
| sector_2_personal_fastest | boolean | True if the current sector 2 time is this driver's personal best |
| sector_3_overall_fastest | boolean | True if the current sector 3 time is the overall fastest |
| sector_3_personal_fastest | boolean | True if the current sector 3 time is this driver's personal best |
| best_sector_1 | number | Driver's personal best sector 1 time this session (or segment, in qualifying) |
| best_sector_2 | number | Driver's personal best sector 2 time this session (or segment, in qualifying) |
| best_sector_3 | number | Driver's personal best sector 3 time this session (or segment, in qualifying) |
| q1_time | string | Best lap time set in Q1; `null` if no time was set or outside qualifying |
| q1_knocked_out | boolean | True if the driver did not advance past Q1; `null` outside qualifying |
| q1_position | number | Finishing rank in Q1 based on best lap time; `null` if no time was set |
| q2_time | string | Best lap time set in Q2; `null` if did not participate or no time set |
| q2_knocked_out | boolean | True if the driver did not advance past Q2; `null` outside qualifying |
| q2_position | number | Finishing rank in Q2; `null` if no time was set |
| q3_time | string | Best lap time set in Q3; `null` if did not participate |
| q3_knocked_out | boolean | Always `false` (Q3 is the final segment); `null` outside qualifying |
| q3_position | number | Finishing rank in Q3; `null` if no time was set |

<details>
<summary>JSON Structure Example — Race</summary>

```json
{
  "drivers": [
    {
      "racing_number": "1",
      "tla": "VER",
      "name": "Max Verstappen",
      "team": "Red Bull Racing",
      "team_color": "#3671C6",
      "team_color_rgb": [54, 113, 198],
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
      "stopped": false,
      "fastest_lap": true,
      "fastest_lap_time": "1:29.123",
      "fastest_lap_time_secs": 89.123,
      "fastest_lap_lap": 42,
      "sector_1": 28.123,
      "sector_2": null,
      "sector_3": null,
      "sector_1_overall_fastest": true,
      "sector_1_personal_fastest": true,
      "sector_2_overall_fastest": null,
      "sector_2_personal_fastest": null,
      "sector_3_overall_fastest": null,
      "sector_3_personal_fastest": null,
      "best_sector_1": 27.891,
      "best_sector_2": 31.456,
      "best_sector_3": 29.776,
      "q1_time": null,
      "q1_knocked_out": null,
      "q1_position": null,
      "q2_time": null,
      "q2_knocked_out": null,
      "q2_position": null,
      "q3_time": null,
      "q3_knocked_out": null,
      "q3_position": null
    }
  ],
  "total_laps": 70,
  "fastest_lap": {
    "racing_number": "1",
    "tla": "VER",
    "name": "Max Verstappen",
    "team": "Red Bull Racing",
    "team_color": "#3671C6",
    "team_color_rgb": [54, 113, 198],
    "lap": 42,
    "time": "1:29.123",
    "time_secs": 89.123
  },
  "current_qualifying_part": null
}
```

</details>

<details>
<summary>JSON Structure Example — Qualifying</summary>

```json
{
  "drivers": [
    {
      "racing_number": "1",
      "tla": "VER",
      "name": "Max Verstappen",
      "team": "Red Bull Racing",
      "team_color": "#3671C6",
      "team_color_rgb": [54, 113, 198],
      "grid_position": "1",
      "current_position": "1",
      "laps": {},
      "completed_laps": 6,
      "status": "on_track",
      "in_pit": false,
      "pit_out": false,
      "retired": false,
      "stopped": false,
      "fastest_lap": false,
      "fastest_lap_time": null,
      "fastest_lap_time_secs": null,
      "fastest_lap_lap": null,
      "sector_1": 16.911,
      "sector_2": null,
      "sector_3": null,
      "sector_1_overall_fastest": true,
      "sector_1_personal_fastest": true,
      "sector_2_overall_fastest": null,
      "sector_2_personal_fastest": null,
      "sector_3_overall_fastest": null,
      "sector_3_personal_fastest": null,
      "best_sector_1": 16.802,
      "best_sector_2": 44.213,
      "best_sector_3": 22.087,
      "q1_time": "1:23.100",
      "q1_knocked_out": false,
      "q1_position": 3,
      "q2_time": "1:22.500",
      "q2_knocked_out": false,
      "q2_position": 2,
      "q3_time": "1:21.987",
      "q3_knocked_out": false,
      "q3_position": 1
    },
    {
      "racing_number": "10",
      "tla": "GAS",
      "name": "Pierre Gasly",
      "team": "Alpine",
      "team_color": "#FF87BC",
      "grid_position": "16",
      "current_position": "16",
      "laps": {},
      "completed_laps": 4,
      "status": "on_track",
      "in_pit": false,
      "pit_out": false,
      "retired": false,
      "stopped": false,
      "fastest_lap": false,
      "fastest_lap_time": null,
      "fastest_lap_time_secs": null,
      "fastest_lap_lap": null,
      "sector_1": null,
      "sector_2": null,
      "sector_3": null,
      "sector_1_overall_fastest": null,
      "sector_1_personal_fastest": null,
      "sector_2_overall_fastest": null,
      "sector_2_personal_fastest": null,
      "sector_3_overall_fastest": null,
      "sector_3_personal_fastest": null,
      "best_sector_1": null,
      "best_sector_2": null,
      "best_sector_3": null,
      "q1_time": "1:24.892",
      "q1_knocked_out": true,
      "q1_position": 16,
      "q2_time": null,
      "q2_knocked_out": false,
      "q2_position": null,
      "q3_time": null,
      "q3_knocked_out": false,
      "q3_position": null
    }
  ],
  "total_laps": null,
  "fastest_lap": null,
  "current_qualifying_part": 3
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get the race leader:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% if drivers %}
  {% set leader = drivers | selectattr('current_position', 'eq', '1') | first %}
  {% if leader %}
    Leader: {{ leader.tla }} ({{ leader.name }})
  {% endif %}
{% endif %}
```

**Get a specific driver by number:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% set driver = drivers | selectattr('racing_number', 'eq', '44') | first %}
{% if driver %}
  {{ driver.name }} is in P{{ driver.current_position }}
{% endif %}
```

**Get driver's last lap time:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% set driver = drivers | selectattr('racing_number', 'eq', '1') | first %}
{% if driver and driver.laps %}
  {% set last_lap = driver.completed_laps | string %}
  Last lap: {{ driver.laps.get(last_lap, 'N/A') }}
{% endif %}
```

**List all drivers in pit lane:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% for d in drivers if d.status == 'pit_in' %}
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
{% for d in drivers %}
  {% set change = d.grid_position | int - d.current_position | int %}
  {{ d.tla }}: {% if change > 0 %}+{% endif %}{{ change }}
{% endfor %}
```

**Get Q3 qualifying results sorted by position:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% set q3 = drivers | selectattr('q3_time', 'ne', None) | sort(attribute='q3_position') %}
{% for d in q3 %}
  P{{ d.q3_position }}: {{ d.tla }} — {{ d.q3_time }}
{% endfor %}
```

**List drivers knocked out in Q1:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% for d in drivers if d.q1_knocked_out %}
  {{ d.tla }} eliminated in Q1 ({{ d.q1_time or 'no time' }})
{% endfor %}
```

**Show active qualifying segment:**
```jinja2
{% set part = state_attr('sensor.f1_driver_positions', 'current_qualifying_part') %}
{% if part %}
  Q{{ part }} in progress
{% endif %}
```

</details>

:::info
Fastest lap details are only exposed during races and sprints. In practice and qualifying, `fastest_lap` is `null` and each driver has `fastest_lap: false`.
:::

:::info
Sector times (`sector_1`, `sector_2`, `sector_3`) update live as drivers complete each sector during a lap. They are set to `null` until the sector is crossed, and reset at the start of each new lap. The `best_sector_*` fields hold the driver's personal best for the current session — or the current qualifying segment if in Q1, Q2, or Q3.
:::

:::info
Qualifying segment data (`q1_time`, `q2_time`, `q3_time` and their associated `_knocked_out` and `_position` fields) is only populated during qualifying and sprint shootout sessions. In all other session types these fields are `null`. All 20 drivers are always present regardless of whether they set a time. `q1_knocked_out: true` means the driver did not advance to Q2, and `q2_knocked_out: true` means the driver did not reach Q3.
:::

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
| team_color_rgb | list | Team color as RGB values (e.g., `[54, 113, 198]`) |
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

## Track Limits

`sensor.f1_track_limits` - Aggregated track limits violations per driver, including deleted lap times, black and white flag warnings, and penalties.

**State**
- Integer: total number of track limit violations (deletions + warnings) in this session.

**Example**
```text
12
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| by_driver | object | Map of driver TLAs to their violation data |
| total_deletions | number | Total count of deleted times/laps across all drivers |
| total_warnings | number | Count of BLACK AND WHITE flags issued for track limits |
| total_penalties | number | Count of track limits penalties issued |
| last_update | string | ISO-8601 timestamp of last update |

Each entry in `by_driver` (keyed by driver TLA) contains:

| Field | Type | Description |
| --- | --- | --- |
| racing_number | string | Car number |
| deletions | number | Number of times/laps deleted for this driver |
| warning | boolean | Whether a BLACK AND WHITE flag has been shown |
| penalty | string | Penalty text if issued (e.g., "5 SECOND TIME PENALTY"), or null |
| violations | list | Detailed list of all violations |

Each entry in `violations` contains:

| Field | Type | Description |
| --- | --- | --- |
| utc | string | ISO-8601 timestamp of the violation |
| lap | number | Lap number when violation occurred |
| turn | number | Turn number where violation occurred (for deletions) |
| type | string | Violation type: `time_deleted`, `warning`, or `penalty` |
| penalty | string | Penalty text (only present when type is `penalty`) |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "by_driver": {
    "HAM": {
      "racing_number": "44",
      "deletions": 3,
      "warning": true,
      "penalty": null,
      "violations": [
        { "utc": "2025-12-07T13:09:47Z", "lap": 5, "turn": 1, "type": "time_deleted" },
        { "utc": "2025-12-07T13:40:05Z", "lap": 25, "turn": 1, "type": "time_deleted" },
        { "utc": "2025-12-07T13:43:05Z", "lap": 27, "turn": 1, "type": "time_deleted" },
        { "utc": "2025-12-07T13:48:58Z", "lap": 31, "turn": null, "type": "warning" }
      ]
    },
    "GAS": {
      "racing_number": "10",
      "deletions": 4,
      "warning": true,
      "penalty": "5 SECOND TIME PENALTY",
      "violations": [
        { "utc": "2025-12-07T13:11:44Z", "lap": 6, "turn": 6, "type": "time_deleted" },
        { "utc": "2025-12-07T13:38:57Z", "lap": 24, "turn": 4, "type": "time_deleted" },
        { "utc": "2025-12-07T13:49:07Z", "lap": 31, "turn": null, "type": "warning" },
        { "utc": "2025-12-07T14:09:18Z", "lap": 44, "turn": 4, "type": "time_deleted" },
        { "utc": "2025-12-07T14:11:25Z", "lap": 46, "turn": null, "type": "penalty", "penalty": "5 SECOND TIME PENALTY" }
      ]
    },
    "LAW": {
      "racing_number": "30",
      "deletions": 4,
      "warning": true,
      "penalty": null,
      "violations": [
        { "utc": "2025-12-07T13:10:33Z", "lap": 5, "turn": 1, "type": "time_deleted" },
        { "utc": "2025-12-07T13:14:11Z", "lap": 8, "turn": 1, "type": "time_deleted" },
        { "utc": "2025-12-07T13:34:40Z", "lap": 21, "turn": 7, "type": "time_deleted" },
        { "utc": "2025-12-07T13:37:38Z", "lap": 23, "turn": null, "type": "warning" }
      ]
    }
  },
  "total_deletions": 11,
  "total_warnings": 3,
  "total_penalties": 1,
  "last_update": "2025-12-07T14:11:25Z"
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get a driver's track limits count:**
```jinja2
{% set by_driver = state_attr('sensor.f1_track_limits', 'by_driver') %}
{% set ham = by_driver.get('HAM') %}
{% if ham %}
  HAM: {{ ham.deletions }} deletions{% if ham.warning %}, WARNING{% endif %}
{% endif %}
```

**List drivers with warnings:**
```jinja2
{% set by_driver = state_attr('sensor.f1_track_limits', 'by_driver') %}
{% for tla, data in by_driver.items() if data.warning %}
  {{ tla }} (#{{ data.racing_number }}) - {{ data.deletions }} deletions
{% endfor %}
```

**Find drivers at risk (3+ deletions, no warning yet):**
```jinja2
{% set by_driver = state_attr('sensor.f1_track_limits', 'by_driver') %}
{% for tla, data in by_driver.items() if data.deletions >= 3 and not data.warning %}
  {{ tla }}: {{ data.deletions }} deletions - at risk!
{% endfor %}
```

**Get total session track limits:**
```jinja2
{% set deletions = state_attr('sensor.f1_track_limits', 'total_deletions') %}
{% set warnings = state_attr('sensor.f1_track_limits', 'total_warnings') %}
{% set penalties = state_attr('sensor.f1_track_limits', 'total_penalties') %}
Deletions: {{ deletions }}, Warnings: {{ warnings }}, Penalties: {{ penalties }}
```

**List drivers with penalties:**
```jinja2
{% set by_driver = state_attr('sensor.f1_track_limits', 'by_driver') %}
{% for tla, data in by_driver.items() if data.penalty %}
  {{ tla }}: {{ data.penalty }}
{% endfor %}
```

</details>

:::tip Track Limits Progression
The typical track limits progression is: 3 deleted lap times → BLACK AND WHITE flag warning → penalty on the next violation. Use the `deletions` count and `warning` flag to identify drivers at risk.
:::

---

## Investigations

`sensor.f1_investigations` - Active steward investigations and pending penalties. Shows only currently relevant information with automatic lifecycle management.

**State**
- Integer: count of actionable items (noted incidents + under investigation + pending penalties).

**Example**
```text
3
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| noted | list | Incidents noted but not yet under investigation |
| under_investigation | list | Active steward investigations |
| no_further_action | list | Recent NFI decisions (auto-expire after 5 minutes) |
| penalties | list | Penalties issued but not yet served |
| last_update | string | ISO-8601 timestamp of last update |

Each entry in `noted` and `under_investigation` contains:

| Field | Type | Description |
| --- | --- | --- |
| utc | string | ISO-8601 timestamp when the incident was noted |
| lap | number | Lap number when the incident occurred |
| drivers | list | Driver TLAs involved (sorted alphabetically) |
| racing_numbers | list | Car numbers involved |
| location | string | Location such as "TURN 7", "PIT LANE" (or null) |
| reason | string | Reason such as "CAUSING A COLLISION", "LEAVING THE TRACK AND GAINING AN ADVANTAGE" (or null) |
| after_race | boolean | Whether the investigation will happen after the race (only in `under_investigation`) |

Each entry in `no_further_action` contains the same fields plus:

| Field | Type | Description |
| --- | --- | --- |
| nfi_utc | string | ISO-8601 timestamp when NFI was decided (used for auto-expiry) |

Each entry in `penalties` contains:

| Field | Type | Description |
| --- | --- | --- |
| driver | string | Driver TLA who received the penalty |
| racing_number | string | Car number |
| penalty | string | Penalty type (e.g., "5 SECOND TIME PENALTY", "DRIVE THROUGH PENALTY") |
| reason | string | Reason for the penalty |
| utc | string | ISO-8601 timestamp when penalty was issued |
| lap | number | Lap number when penalty was issued |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "noted": [
    {
      "utc": "2025-12-07T13:30:57Z",
      "lap": 19,
      "drivers": ["LEC", "RUS"],
      "racing_numbers": ["16", "63"],
      "location": "TURN 9",
      "reason": "MOVING UNDER BRAKING"
    }
  ],
  "under_investigation": [
    {
      "utc": "2025-12-07T13:40:46Z",
      "lap": 25,
      "drivers": ["NOR", "TSU"],
      "racing_numbers": ["4", "22"],
      "location": "TURN 5",
      "reason": "FORCING ANOTHER DRIVER OFF THE TRACK",
      "after_race": false
    }
  ],
  "no_further_action": [
    {
      "utc": "2025-12-07T13:06:50Z",
      "lap": 3,
      "drivers": ["ALB", "HAM"],
      "racing_numbers": ["23", "44"],
      "location": "TURN 7",
      "reason": "LEAVING THE TRACK AND GAINING AN ADVANTAGE",
      "nfi_utc": "2025-12-07T13:12:53Z"
    }
  ],
  "penalties": [
    {
      "driver": "TSU",
      "racing_number": "22",
      "penalty": "5 SECOND TIME PENALTY",
      "reason": "MORE THAN ONE CHANGE OF DIRECTION",
      "utc": "2025-12-07T13:46:38Z",
      "lap": 29
    },
    {
      "driver": "ALB",
      "racing_number": "23",
      "penalty": "5 SECOND TIME PENALTY",
      "reason": "SPEEDING IN THE PIT LANE",
      "utc": "2025-12-07T14:00:05Z",
      "lap": 38
    }
  ],
  "last_update": "2025-12-07T14:00:05Z"
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Check if a driver is under investigation:**
```jinja2
{% set investigations = state_attr('sensor.f1_investigations', 'under_investigation') %}
{% set ver_involved = investigations | selectattr('drivers', 'contains', 'VER') | list %}
{% if ver_involved | length > 0 %}
  VER is under investigation!
{% endif %}
```

**List all pending penalties:**
```jinja2
{% set penalties = state_attr('sensor.f1_investigations', 'penalties') %}
{% for p in penalties %}
  {{ p.driver }}: {{ p.penalty }} ({{ p.reason }})
{% endfor %}
```

**Count active investigations:**
```jinja2
{% set noted = state_attr('sensor.f1_investigations', 'noted') | length %}
{% set investigating = state_attr('sensor.f1_investigations', 'under_investigation') | length %}
Noted: {{ noted }}, Under Investigation: {{ investigating }}
```

**Get post-race investigations:**
```jinja2
{% set investigations = state_attr('sensor.f1_investigations', 'under_investigation') %}
{% for inv in investigations if inv.after_race %}
  {{ inv.drivers | join(' vs ') }} - {{ inv.reason }} (after race)
{% endfor %}
```

**Show recent NFI decisions:**
```jinja2
{% set nfi = state_attr('sensor.f1_investigations', 'no_further_action') %}
{% for item in nfi %}
  {{ item.drivers | join('/') }}: No Further Action ({{ item.reason }})
{% endfor %}
```

**Create investigation summary:**
```jinja2
{% set sensor = 'sensor.f1_investigations' %}
{% set total = states(sensor) | int %}
{% if total > 0 %}
  {{ total }} active matter{{ 's' if total > 1 else '' }}:
  {% set penalties = state_attr(sensor, 'penalties') %}
  {% for p in penalties %}
    - {{ p.driver }}: {{ p.penalty }}
  {% endfor %}
{% else %}
  No active investigations
{% endif %}
```

</details>

:::info Incident Lifecycle
- **NOTED** → Stays until escalated to UNDER INVESTIGATION, resolved as NFI, or penalized
- **UNDER INVESTIGATION** → Stays until resolved as NFI or penalty issued
- **NO FURTHER ACTION** → Auto-expires after 5 minutes of session time
- **PENALTY** → Stays until PENALTY SERVED message received
:::

---

## Championship Prediction (Drivers)

:::note Replay Mode only
This entity stays registered in Home Assistant and is unavailable outside [Replay Mode](/features/replay-mode). The championship prediction data stream requires authentication that the integration does not currently support during live sessions.
:::

Predicted Drivers Championship winner and points table, sourced from the ChampionshipPrediction stream.

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

:::note Replay Mode only
This entity stays registered in Home Assistant and is unavailable outside [Replay Mode](/features/replay-mode). The championship prediction data stream requires authentication that the integration does not currently support during live sessions.
:::

Predicted Constructors Championship winner and points table, sourced from the ChampionshipPrediction stream.

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

:::note Replay Mode only
This entity stays registered in Home Assistant and is unavailable outside [Replay Mode](/features/replay-mode). The underlying data stream used for formation start detection requires authentication that the integration does not currently support during live sessions.
:::

Indicates when the formation start procedure is ready. Useful for triggering automations at race start during replay.

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
Available during race and sprint sessions in Replay Mode.
::::

---

## Overtake Mode

:::caution Experimental — 2026 regulation
This sensor is based on data observed during 2026 pre-season testing. It should be considered experimental until confirmed against live race conditions. The exact message format from Formula 1 may be adjusted in a future update once the first race weekend has been evaluated.
:::

`binary_sensor.f1_overtake_mode` - Indicates whether the track-wide overtake mode is currently enabled. This is a 2026 Formula 1 regulation feature that allows a driver who was within one second of the car ahead at the final corner detection point to deploy an additional 0.5 MJ of electrical energy on the following straight.

**State (on/off)**
- `on` when overtake mode is enabled track-wide; otherwise `off`.

**Example**
```text
on
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| straight_mode | string | Current straight mode state (`normal_grip`, `low_grip`, or `disabled`) |
| restored | boolean | True if the state was restored from history after a Home Assistant restart |

::::info INFO
Active only during sessions where the 2026 overtake mode regulation applies. The state is restored from history when Home Assistant restarts during an active session.
::::

---

## Straight Mode

:::caution Experimental — 2026 regulation
This sensor is based on data observed during 2026 pre-season testing. It should be considered experimental until confirmed against live race conditions. The exact message format from Formula 1 may be adjusted in a future update once the first race weekend has been evaluated.
:::

`sensor.f1_straight_mode` - Shows the track-wide active aerodynamic permission for straight sections, broadcasted via Race Control messages. This is a 2026 Formula 1 regulation feature where the car's aerodynamic profile on designated straight sections of the circuit is regulated by the FIA.

**State (enum)**
- One of: `normal_grip`, `low_grip`, `disabled`.

| Value | Description |
| --- | --- |
| `normal_grip` | Normal aerodynamic configuration permitted on straight sections |
| `low_grip` | Restricted aerodynamic configuration on straight sections |
| `disabled` | Straight mode system is not active |

**Example**
```text
normal_grip
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| overtake_enabled | boolean | Whether overtake mode is currently enabled |
| restored | boolean | True if the state was restored from history after a Home Assistant restart |

::::info INFO
Active only during sessions where the 2026 straight mode regulation applies. The state is restored from history when Home Assistant restarts during an active session.
::::
