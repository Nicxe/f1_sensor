---
id: events
title: Events
---

## Home Assistant Events

Home Assistant provides an **Event Bus** that integrations can use to publish real-time information for low-latency automations and triggers.  
Events are ideal for transient signals and instantaneous state changes that should be reacted to immediately, rather than stored as long-lived sensor states.

For a general introduction to how events work in Home Assistant, see:  
[Home Assistant Event integration documentation](https://www.home-assistant.io/integrations/event/).

## Event Streams

### On-track Incident

F1 Sensor publishes likely stopped-car and on-track incident changes under the event type `f1_sensor_incident`.
Use this event for notifications and automations that should react immediately to incident lifecycle changes.

:::warning[Not crash detection]
The event describes a likely stopped car or on-track incident. It does not guarantee that a crash happened. Keep notification wording neutral unless Race Control explicitly says more.
:::

When F1TV Auth is configured and the authenticated live timing stream is available, F1 Sensor can also publish earlier `candidate` events from `CarData.z` low-speed telemetry correlated with yellow flag, Virtual Safety Car, Safety Car, or red flag context. These candidates are useful for advanced automations, but they are not confirmed incidents until public timing or Race Control provides stronger evidence.

When Track Map data is available from `Position.z`, the event can include optional `location` context such as position status, sector, and track geometry source. This context is used only when it is fresh enough to improve confidence or reduce false positives, and the binary sensors do not expose raw X/Y/Z position samples as state attributes.

**Phases**

| Phase | Meaning |
| --- | --- |
| `candidate` | Early possible incident. Normally useful for advanced automations, not default push alerts |
| `confirmed` | Strong enough evidence for an on-track incident alert |
| `updated` | New information for the same `incident_id`, such as higher confidence |
| `cleared` | The incident appears to be over |

**Confidence**

| Confidence | Meaning |
| --- | --- |
| `low` | Weak or early signal, normally not user-facing |
| `medium` | Reasonable incident candidate, such as a stopped car that is not in pit lane or an auth-based low-speed candidate with flag context |
| `high` | Strong context, such as stopped timing data combined with yellow flag, Safety Car, red flag, or Race Control context |

#### Example payload

```yaml
event_type: f1_sensor_incident
data:
  entry_id: "abc123"
  incident_id: "2026-miami-race-10-2026-05-03T20:14:22Z"
  phase: "confirmed"
  confidence: "high"
  reason: "timing_stopped_with_race_control"
  driver:
    racing_number: "10"
    tla: "GAS"
    name: "Pierre Gasly"
    team: "Alpine"
  session:
    meeting_name: "Miami Grand Prix"
    session_name: "Race"
    session_type: "race"
    session_key: "2026-miami-race"
  track_status:
    status: "YELLOW"
    message: "Yellow"
  race_control:
    message: "DOUBLE YELLOW IN TURN 7"
    category: "Flag"
    flag: "DOUBLE YELLOW"
  location:
    status: "OnTrack"
    source: "live"
    stale: false
    confidence: "high"
    description: "on track, sector 2"
    sector: 2
    corner: null
    pit_lane: false
    track_segment: 42
    distance_to_track: 4.2
    geometry_source: "static_circuit_geometry"
    fallback_state: "static_catalog"
    updated_at: "2026-05-03T20:14:27Z"
  signals:
    - "timing_stopped"
    - "race_control_yellow"
    - "track_map_location"
  started_at: "2026-05-03T20:14:22Z"
  updated_at: "2026-05-03T20:14:28Z"
  data_quality: "live"
```

Use `phase`, `confidence`, `session.session_type`, and `driver.tla` as the main automation fields. `session.session_type` uses lowercase values such as `race`, `sprint`, `qualifying`, `practice`, `testing`, or `unknown`. The payload uses neutral names so it can represent stopped cars, spins, technical failures, and other likely on-track incidents without calling them crashes.

The `location` object is optional context. Treat `location.stale: true`, `location.confidence: low`, or missing `geometry_source` as informational only. The payload intentionally does not include high-frequency raw position samples in entity state history.

### Event vs sensor

Use `f1_sensor_incident` when you want one notification per incident update. Use [`binary_sensor.f1_on_track_incident`](/entities/live-data#on-track-incident) when you want a dashboard indicator or a simple state trigger while any confirmed incident is active.

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

For example automations using these events, see the [Automation](/automation) page.
:::

### Race Control vs incident events

Race Control events forward official messages as they arrive. Incident events combine stopped-car and track context into a neutral alert lifecycle with phases and confidence.

## Future Event Streams

The Event Bus support in F1 Sensor is designed to be extensible.
While Race Control is the first published stream, additional real-time events may be added in future releases.

This page will be extended as new event types are introduced.
