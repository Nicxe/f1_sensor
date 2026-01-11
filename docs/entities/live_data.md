---
id: live-data
title: Live Data
---

By enabling [live data](/getting-started/add-integration)  when configuring the F1 Sensor, Home Assistant can react to live data from an ongoing session such as practice, qualifying, or race. These entities update shortly before, during, and shortly after a session. Outside session times, they will not update. This means that a sensor may show as unknown or display the last known state even when no session is active. For example, the Track Status entity often remains `CLEAR` between race weekends.


:::info F1 Live Timing API
The data for these entities comes from the F1 Live Timing API, which is unofficial. There is no known official documentation, and the API may change without prior notice.
:::

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
| [sensor.f1_top_three](#top-three)                     | Dedicated sensors for current P1, P2 and P3 |
| [sensor.f1_race_control](#race-control)               | Race Control messages feed (flags, incidents, key updates) |



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

Live roster of drivers with identity and team information. for the session

**State**
  - Integer: number of drivers in the list.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| drivers | list | `[ { racing_number, tla, name, first_name, last_name, team, team_color, headshot_small, headshot_large, reference } ]` |


---

## Pit Stops

Live pit stop information from the F1 Live Timing feed, including a rolling series per car.

**State**
- Integer: total number of pit stops recorded in the current session, or `unknown` when none are available.

**Example**
```text
7
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| events | list | List of pit stop events with driver, lap, time, and duration |
| series | list | Aggregated pit stop history per driver |
| last_update | string | ISO‑8601 timestamp of the last received pit stop event |

::::info INFO
Active during race and sprint sessions.
::::

---

## Team Radio

Latest team radio message with a short rolling history, sourced from the Team Radio stream. This is a curated selection of radio traffic, similar to what is broadcast during TV coverage, not the full raw radio feed.

**State**
- ISO‑8601 timestamp of the most recent radio message, or `unknown` when none are available.

**Example**
```text
2026-03-14T15:22:31Z
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| driver | string | Driver code (e.g., VER, HAM) |
| message | string | Short text description of the radio clip |
| audio_url | string | URL to the audio clip |
| history | list | Rolling list of recent radio messages (timestamp, driver, url) |

::::info INFO
Updates during all live sessions when radio traffic is available.
::::

---

## Current Tyres

Shows the current tyre compound for each driver in the active session.

**State**
- Short summary string (e.g., `SOFT/MEDIUM/HARD`), or `unknown` when none are available.

**Example**
```text
SOFT/MEDIUM/HARD
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| drivers | list | `[ { driver, compound, age_laps, is_new } ]` |
| last_update | string | ISO‑8601 timestamp |

---

## Top Three

Dedicated live view of the current top three positions.

**State**
- `P1`, `P2`, or `P3` depending on the specific entity, or `unknown` when none are available.

**Example**
```text
P1
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| driver | string | Driver code |
| position | number | 1, 2, or 3 |
| gap_to_leader | string | Time gap to P1 when available |
| team | string | Team name |

::::info INFO
Available during qualifying, sprint, and race sessions.
::::

---

## Race Control

Feed-style sensor exposing Race Control messages such as flags, incidents, and key session updates. This data is also sent on the [event bus](/entities/events)

**State**
- ISO‑8601 timestamp of the latest message, or `unknown` when none are available.

**Example**
```text
2026-03-14T15:24:10Z
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| message | string | Latest Race Control message |
| category | string | Type of message (FLAG, INCIDENT, INFO, etc.) |
| history | list | Rolling list of recent messages with timestamps |

---

