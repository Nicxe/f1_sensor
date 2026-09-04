---
id: events
title: Events
description: Use Race Control, incident, and Favorite Driver events in Home Assistant automations.
---

Events are useful when an automation must react to each message or change, including updates that may not change a sensor’s state. Choose a stream below, then use its event type in a Home Assistant event trigger.

## Home Assistant Events

| You need | Use |
| --- | --- |
| Each official Race Control message | `f1_sensor_race_control_event` |
| An incident’s phase, confidence, or update | `f1_sensor_incident` |
| The selected driver’s position, pit, or retirement changes | `f1_sensor_favorite_driver_event` |
| A simple active/inactive condition | The corresponding [entity](/reference/overview) |
| A trigger selected in the visual editor | [Device triggers](/reference/device-triggers) |

These are event-bus event types, not `event.*` entity IDs. In **Developer Tools > Events**, listen for an event type during a suitable live or replay session to inspect the payload from your installation.

:::info[Timing and repeated events]
Live events follow the configured [Live Delay](/features/live-delay). Rewinding [Replay Mode](/features/replay-mode) can emit historical events again, so notifications may repeat. For event types with an `entry_id`, filter that field if you run multiple F1 Sensor entries.
:::

## Event Streams

### On-track Incident

F1 Sensor publishes likely stopped-car and on-track incident changes under the event type `f1_sensor_incident`.
Use this event for notifications and automations that follow individual incident lifecycle changes.

For the full user-facing behavior, see [Incident Detection](/features/incident-detection).

:::warning[Not crash detection]
The event describes a likely stopped car or on-track incident. It does not guarantee that a crash happened. Keep notification wording neutral unless Race Control explicitly says more.
:::

When F1TV Auth is configured and extra live car data is available, F1 Sensor can also publish earlier `candidate` events from low-speed car movement correlated with yellow flag, Virtual Safety Car, Safety Car, or red flag context. These candidates are useful for advanced automations, but they are not confirmed incidents until public timing or Race Control provides stronger evidence.

When Track Map data is available, the event can include useful `location` context such as position status and sector. Location fields can be `null` when fresh context is not available.

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

#### Event fields

| Field | Type | Use |
| --- | --- | --- |
| `entry_id` | string | Scope an automation to one F1 Sensor entry |
| `incident_id` | string | Correlate updates for the same incident |
| `phase` | string | Filter candidate, confirmed, updated, or cleared events |
| `confidence` | string | Filter low, medium, or high confidence |
| `driver` | object | Driver number, abbreviation, name, and team |
| `session` | object | Meeting, session name, and lowercase session type |
| `location` | object | Optional position context; fields can be null or stale |

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

The `location` object is optional context. Its fields may be `null` when Track Map context is unavailable. Treat `location.stale: true` or `location.confidence: low` as informational only.

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
Events remain available as a complementary, low-latency trigger source alongside the sensor.

For example automations using these events, see the [Automation](/automation) page.
:::

### Race Control vs incident events

Race Control events forward official messages as they arrive. Incident events combine stopped-car and track context into a neutral alert lifecycle with phases and confidence.

### Favorite Driver

`f1_sensor_favorite_driver_event` follows the driver selected in `select.f1_favorite_driver`. Enable **Favorite driver** in the integration options and select a driver before using these events. They are scoped to the F1 Sensor configuration entry.

| `event_type` value | Meaning |
| --- | --- |
| `position_gained` | The driver’s position number decreases |
| `position_lost` | The driver’s position number increases |
| `entered_pits` | The driver changes to being in the pit lane |
| `exited_pits` | The driver changes to being outside the pit lane |
| `retired` | The driver changes to retired |

A position change can result from timing corrections or pit activity; it does not establish an on-track overtake. Selecting a different driver does not itself emit these change events.

| Payload field | Type | Description |
| --- | --- | --- |
| `entry_id` | string | F1 Sensor configuration entry |
| `event_type` | string | One of the change types above |
| `driver` | object | Current normalized driver data |
| `previous` | object | Driver data before the change |
| `current` | object | Driver data after the change, also exposed as `driver` |

The driver objects use the fields in the [Favorite Driver reference](/entities/favorite-driver#attributes), without the sensor’s separate `selected` field. Use the [Drivers device triggers](/reference/device-triggers#drivers-device) if you do not need to inspect the raw payload.

## Other event types {/* #future-event-streams */}

The event types documented above are the supported starting points for these automations. Use their exact names and fields; do not infer a new event type from an entity name.
