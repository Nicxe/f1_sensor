# F1 Sensor for Home Assistant

![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=)
<img alt="Maintenance" src="https://img.shields.io/maintenance/yes/2025"> <img alt="GitHub last commit" src="https://img.shields.io/github/last-commit/Nicxe/f1_sensor"><br><br>
<img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/Nicxe/f1_sensor">


## What is F1 Sensor?

This is a custom integration for Home Assistant that creates sensors using data from the [Jolpica-F1 API](https://github.com/jolpica/jolpica-f1).  

It also fetches live data from Formula 1’s unofficial **Live Timing API** during active sessions (practice, qualifying, sprint, race). These live sensors only update shortly before, during, and shortly after a session. Outside of session times, they will not update.  

It is designed for users who want to build automations, scripts, notifications, TTS messages, or more advanced use cases such as generating dynamic dashboards, triggering race-day routines, syncing events to calendars, or integrating with external services based on upcoming Formula 1 events.  


> [!TIP]
>Visit the [F1 Sensor Community at Home Assistant Community Forum](https://community.home-assistant.io/t/formula-1-racing-sensor/) to share your project and get help and inspiration.
>Visit  to share you procejt and get help and inspiration


#### ENTITIES

| Entity                            | Info                                                                                   | 
| --------                          | -------------------------------------------------------------------------------------- | 
| sensor.f1_next_race               | Next race info                                                                         | 
| sensor.f1_season_calendar         | Full race schedule                                                                     | 
| sensor.f1_driver_standings        | Current driver championship standings                                                  | 
| sensor.f1_constructor_standings   | Current constructor standings                                                          | 
| sensor.f1_weather                 | Weather forecast at next race circuit                                                  | 
| sensor.f1_last_race_results       | Most recent race results                                                               | 
| sensor.f1_season_results          | All season race results                                                                | 
| binary_sensor.f1_race_week        | `on` during race week                                                                  | 
| sensor.f1_session_status          | LIVE - Current session phase (pre, live, suspended, finished, finalised, ended)        | 
| sensor.f1_track_status            | LIVE - Current track status (CLEAR, YELLOW, VSC, SC, RED)                              | 
| binary_sensor.f1_safety_car       | LIVE - `on` when Safety Car (SC) or Virtual Safety Car (VSC) is active                 | 
| sensor.f1_track_weather           | LIVE - Current on-track weather (air temp, track temp, rainfall, wind speed, etc.)     |
| sensor.f1_race_lap_count          | LIVE - Current race lap number (only updates during a race, not during practice/qualy) | 


---


### Live data setup

When adding or reconfiguring the integration, you can choose to enable live data via Formula 1’s unofficial Live Timing API.  

- **Enable live F1 API (Race Control/Track/Session)**  
  Creates three additional live entities:  
  - `sensor.f1_session_status`  
  - `sensor.f1_track_status`  
  - `binary_sensor.f1_safety_car`
  - `sensor.f1_track_weather`
  - `sensor.f1_race_lap_count`

  If this option is not selected, these live sensors are not created.

- **Live update delay (seconds)**  
  Lets you delay delivery of live messages to better align with what you see on TV or streaming.  

  Typical broadcast delays:  
  - Broadcast TV (satellite/cable/terrestrial): ~5–10 seconds behind  
  - Streaming services: ~20–45 seconds behind, sometimes more  
  - Sports cable/OTT providers: 45–60 seconds or more depending on provider  

  By setting the delay accordingly, your Home Assistant automations (for example flashing lights on a red flag) can sync more closely with the live pictures you are watching.

![F1SensorFlag-ezgif com-video-to-gif-converter (5)](https://github.com/user-attachments/assets/18a74679-76e2-4d10-8a0d-d3f111c42593)



<details>
<summary>More info! - Live session entities</summary>
<br>
In addition to season and race data, F1 Sensor provides live session entities during race weekends.  

---

##### `sensor.f1_session_status`

Reflects the current phase of a session, powered by SessionStatus feed and an internal started_flag.

**Possible states**
- **pre** – session is open but not yet started (typically ~1h before lights out).  
  
- **live** – session is running.  
  
- **suspended** – a started session is stopped (red flag or interruption).  
  
- **finished** – clock is over, chequered flag. RaceControl may still send flags on in-laps.  
  
- **finalised** – results have been confirmed.  
  
- **ended** – feed is closed for the session.  
  

**Typical transitions**  
`pre → live → suspended ↔ live → finished → finalised → ended`  
After finalised or ended, logic resets and next session begins at **pre**.

---

##### `sensor.f1_track_status`

Directly reflects the latest TrackStatus feed.  

**Possible states**
- CLEAR  
- YELLOW  
- VSC  
- SC  
- RED  

> State reflects the last received track status and may persist briefly after *finished* while in-laps are ongoing.

---

##### `binary_sensor.f1_safety_car`

Boolean entity derived from track status.  

**States**
- **on** – when `sensor.f1_track_status` is SC or VSC.  
- **off** – in all other cases.

---

##### `sensor.f1_track_weather`

Updates approximately every minute during an active session.  

**Attributes include**
- Air temperature  
- Track temperature  
- Rainfall  
- Wind speed  

---

##### `sensor.f1_race_lap_count`

Only updates during an active race session.  
Shows the current lap number in real time.  

</details>


---



<img width="612" height="490" alt="image" src="https://github.com/user-attachments/assets/b31c82a2-077d-4447-a367-dc0095e0e72e" />


### Race Control messages

Race Control messages are sent as events in Home Assistant under the event type `f1_sensor_race_control_event`.  
These include flags, steward notes, incident reports, and other live race control communications.  

Example payloads:  
```yaml
event_type: f1_sensor_race_control_event
data:
  message:
    Utc: "2025-09-19T12:40:18"
    Category: Flag
    Flag: CLEAR
    Scope: Sector
    Sector: 6
    Message: CLEAR IN TRACK SECTOR 6
  received_at: "2025-09-19T12:40:44+00:00"
origin: LOCAL
time_fired: "2025-09-19T12:40:44.106956+00:00"

event_type: f1_sensor_race_control_event
data:
  message:
    Utc: "2025-09-19T12:40:07"
    Category: Flag
    Flag: YELLOW
    Scope: Sector
    Sector: 6
    Message: YELLOW IN TRACK SECTOR 6
  received_at: "2025-09-19T12:40:44+00:00"

event_type: f1_sensor_race_control_event
data:
  message:
    Utc: "2025-09-19T12:40:06"
    Category: Other
    Message: INCIDENT INVOLVING CAR 81 (PIA) NOTED - YELLOW FLAG INFRINGEMENT
  received_at: "2025-09-19T12:40:44+00:00"
```

> [!NOTE]
>Currently, Race Control is published as events only.
>In a future release, these messages will also be exposed as a > sensor.

---


Each timestamp attribute (e.g. `race_start`) is still provided in UTC. In addition, a `_local` variant such as `race_start_local` is available. These values use the circuit's timezone so you can easily create automations at the correct local time.


During installation, you can choose exactly which sensors you want to include in your setup.  
This gives you control over which data points to load — for example, only the next race and weather, without standings or calendar.

You can always change this selection later by reconfiguring the integration via **Settings > Devices & Services** in Home Assistant.

The integration fetches fresh data from the Jolpica-F1 API every 1 hours.

I personally use this integration to display the next race and the following three races on an e-ink display. You can read more about that setup [here](https://github.com/Nicxe/esphome).


> [!NOTE]
> If your goal is to visually display upcoming race information, current standings, and more in your Home Assistant dashboard, the [FormulaOne Card](https://github.com/marcokreeft87/formulaone-card) is the better choice for that purpose.

---

### Known Issue

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

---

## Installation

You can install this integration as a custom repository by following one of these guides:

### With HACS (Recommended)

To install the custom component using HACS:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Nicxe&repository=f1_sensor&category=integration)

or
1. Install HACS if you don't have it already
2. Open HACS in Home Assistant
3. Search for "F1 Sensor"
4. Click the download button. ⬇️


<details>
<summary>Without HACS</summary>

1. Download the latest release of the F1 Sensor integration from **[GitHub Releases](https://github.com/Nicxe/f1_sensor/releases)**.
2. Extract the downloaded files and place the `f1_sensor` folder in your Home Assistant `custom_components` directory (usually located in the `config/custom_components` directory).
3. Restart your Home Assistant instance to load the new integration.

</details>

---

## Configuration

To add the integration to your Home Assistant instance, use the button below:

[![Open your Home Assistant instance and start configuration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=f1_sensor)

### Manual Configuration

If the button above does not work, you can also perform the following steps manually:

1. Browse to your Home Assistant instance.
2. Go to **Settings > Devices & Services**.
3. In the bottom right corner, select the **Add Integration** button.
4. From the list, select **F1 Sensor**.
5. Follow the on-screen instructions to complete the setup.

<br>

## Example
### Blueprint

> [!NOTE]  
>The Formula 1 track status blueprint for Home Assistant is now maintained by EvertJob.
>You can find the latest version and full instructions here:
>👉 [github.com/EvertJob/F1-Blueprint](https://github.com/EvertJob/F1-Blueprint)


### E-ink display

This [e-ink display project](https://github.com/Nicxe/esphome) uses the sensors from this integration to show upcoming Formula 1 races, including race countdown and schedule.

![E-ink example](https://github.com/user-attachments/assets/96185a06-ed0b-421a-afa6-884864baca63)

---

### Custom F1 Card by the Community

Community user Tiidler has used the sensors from this integration to create a fully custom F1 dashboard card in Home Assistant, displaying race schedule, standings, podium results, and weather, all styled to fit their setup.

![image (1)](https://github.com/user-attachments/assets/4ed2748c-2ae7-4529-8767-bedbaa98636f)


---


> [!NOTE]  
> ### Support the API that makes this possible  
> This integration relies entirely on the amazing [Jolpica-F1 API](https://github.com/jolpica/jolpica-f1), which provides high-quality and up-to-date Formula 1 data for free.  
> If you find this integration useful, please consider supporting the creator of the API by donating to their Ko-fi page: [https://ko-fi.com/jolpic](https://ko-fi.com/jolpic)  
> Without this API, this integration would not be possible, so any support helps keep it live and maintained. 🙏



## Contributing

Contributions, bug reports, and feedback are welcome. Please feel free to open issues or pull requests on GitHub.
