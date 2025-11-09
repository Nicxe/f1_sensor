---
id: live-data
title: Live Data
description: To add the integration to your Home Assistant instance
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


---

# Entities 
All of these entities update only in relation to an active session, typically starting less than an hour before and continuing for a few minutes after the session ends.

## Session Status
Semantic session lifecycle based on the live Session Status. The `pre` state usually occurs 60–15 minutes before a session begins. The sensor goes `live` when the session officially starts, for races, this means lights out, not the beginning of the formation lap. 





**State (enum)**
- One of: `pre`, `live`, `suspended`, `break`, `finished`, `finalised`, `ended`.


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

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| (none) |  | No extra attributes |

---

## Safety Car
On while the Safety Car or Virtual Safety Car is in effect.

**State (on/off)**
- `on` when track status is `SC` or `VSC`; otherwise `off`.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| track_status | string | Normalized track status (`CLEAR`, `YELLOW`, `VSC`, `SC`, `RED`) |

---

## Race Lap
Current lap and total laps during the race.

**State**
  - Integer: current lap, or `unknown` if none available or stale cleared.

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






