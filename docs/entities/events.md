---
id: events
title: Race Control
---



### Race Control messages

Race Control messages are sent as events in Home Assistant under the event type `f1_sensor_race_control_event`.  

These include flags, steward notes, incident reports, and other live race control communications.  


::::info
Currently, Race Control is published as events only.
In a future release, these messages will also be exposed as a sensor
::::


#### Example payloads
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
