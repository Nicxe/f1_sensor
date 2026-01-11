---
id: events
title: Events
---

## Home Assistant Events

Home Assistant provides an **Event Bus** that integrations can use to publish real-time information for low-latency automations and triggers.  
Events are ideal for transient signals and instantaneous state changes that should be reacted to immediately, rather than stored as long-lived sensor states.

For a general introduction to how events work in Home Assistant, see:  
https://www.home-assistant.io/integrations/event/

## Event Streams

### Race Control

Race Control messages are available both as a **sensor** and as **events** in Home Assistant.  
Events are published under the event type `f1_sensor_race_control_event` and act as a real-time complement to the Race Control sensor.

They include flags, steward notes, incident reports, and other live race control communications.  


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

:::info
Race Control is now exposed both as a [sensor](/entities/live-data#race-control) (for dashboards and history) and as events (for real-time automations and triggers).  
The event stream remains available as a complementary, low-latency feed alongside the sensor.
:::

## Future Event Streams

The Event Bus support in F1 Sensor is designed to be extensible.  
While Race Control is the first published stream, additional real-time events may be added in future releases, such as:

This page will be extended as new event types are introduced.