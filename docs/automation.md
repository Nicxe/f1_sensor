---
id: automation
title: Automation
---

Automate your home based on live F1 data. These examples use [live data sensors](/entities/live-data) and [events](/entities/events) to trigger actions during sessions.

:::tip Sync with your TV
For automations to match what you see on screen, configure the [Live Delay](/features/live-delay) to match your broadcast delay.
:::

:::info Ready-made blueprints
Looking for an easy starting point? The [Blueprints](/blueprints/track-status-light) section has ready-made automations for light control and race control notifications — no YAML required.
:::

---

## Device Automation Triggers

The easiest way to build automations is through the Home Assistant UI using device triggers. Go to **Settings > Devices & Services > Devices**, select any F1 Sensor sub-device, and choose **Automations > Add trigger** to see the available triggers without writing any YAML.

:::info
Device triggers are the recommended starting point. They automatically reference the correct entity and are always kept in sync with the integration. YAML examples further down on this page show what happens under the hood.
:::

Triggers are organized per sub-device. Only triggers whose backing entity is enabled will appear.

### Race device

| Trigger | Fires when |
| --- | --- |
| Race week started | The race week indicator turns on |
| Race week ended | The race week indicator turns off |

### Session device

| Trigger | Fires when |
| --- | --- |
| Safety car deployed | Safety car or Virtual Safety Car becomes active |
| Safety car cleared | Safety car or Virtual Safety Car is cleared |
| Formation start ready | Formation start procedure is ready |
| Overtake mode enabled | Track-wide overtake mode is enabled (2026 regulation) |
| Overtake mode disabled | Track-wide overtake mode is disabled (2026 regulation) |
| Session live | Session status changes (any state transition) |
| Track status: CLEAR | Track status becomes CLEAR |
| Track status: YELLOW | Track status becomes YELLOW |
| Track status: Safety Car | Track status becomes SC |
| Track status: VSC | Track status becomes VSC |
| Track status: Red Flag | Track status becomes RED |

### Officials device

| Trigger | Fires when |
| --- | --- |
| New race control message | A new race control message is received |
| New FIA document | A new FIA document is published |
| Investigation changed | An investigation or penalty status changes |

### Drivers device

| Trigger | Fires when |
| --- | --- |
| New team radio | A new team radio clip is available |

### System device

| Trigger | Fires when |
| --- | --- |
| Live timing online | Live timing connection is established |
| Live timing offline | Live timing connection is lost |

---

## YAML Examples

### Notify when race week begins

Uses the [Race Week sensor](/entities/static-data#race-week) to send a notification the moment race week starts. Useful for kicking off any weekly routines — changing dashboard views, enabling presence modes, or just a heads-up.

```yaml
alias: F1 - Race week started
description: Notify when race week begins
trigger:
  - platform: state
    entity_id: binary_sensor.f1_race_week
    to: "on"
condition: []
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "Formula 1"
      message: >
        Race week is here! Next up: {{ state_attr('sensor.f1_next_race', 'race_name') }}
        at {{ state_attr('sensor.f1_next_race', 'circuit_name') }}.
mode: single
```

---

### Reminder before a session starts

Uses the [Season Calendar](/entities/static-data#season-calendar) entity to trigger a notification 30 minutes before any session — practice, qualifying, sprint, or race.

```yaml
alias: F1 - Session starting soon
description: Send a reminder 30 minutes before any F1 session
trigger:
  - platform: calendar
    event: start
    entity_id: calendar.f1_season
    offset: "-0:30:0"
condition: []
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "F1 starting soon"
      message: "{{ trigger.calendar_event.summary }} starts in 30 minutes."
mode: single
```

:::tip
Change the `offset` value to adjust how far in advance the reminder fires. Use `-1:00:0` for one hour, or `"-0:05:0"` for five minutes.
:::

---

### Session goes live

Triggers the moment a session becomes active, when the [Session Status sensor](/entities/live-data#session-status) changes to `live`. Use this to turn on the TV, switch to an F1 dashboard, or send a notification.

```yaml
alias: F1 - Session is live
description: Trigger when a session goes live
trigger:
  - platform: state
    entity_id: sensor.f1_session_status
    to: "live"
condition: []
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "F1 is live"
      message: >
        {{ state_attr('sensor.f1_session_status', 'session_name') }} at
        {{ state_attr('sensor.f1_session_status', 'meeting_name') }} has started.
mode: single
```

---

### Race about to start — formation lap

The [Formation Start sensor](/entities/live-data#formation-start) turns on the moment the formation lap begins, giving you a precise early warning that the race is seconds away.

```yaml
alias: F1 - Formation lap started
description: Notify when the formation lap begins
trigger:
  - platform: state
    entity_id: binary_sensor.f1_formation_start
    to: "on"
condition: []
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "Formation lap"
      message: "The formation lap has started. Lights out soon."
mode: single
```

---

### Safety car deployed

Triggers when the [Safety Car sensor](/entities/live-data#safety-car) turns on. Combine with the Race Control Notifications blueprint for detailed messages, or use this as a quick standalone trigger.

```yaml
alias: F1 - Safety car deployed
description: Notify when the safety car is deployed
trigger:
  - platform: state
    entity_id: binary_sensor.f1_safety_car
    to: "on"
condition: []
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "Safety Car"
      message: "Safety car deployed — {{ state_attr('binary_sensor.f1_safety_car', 'message') }}"
mode: single
```

---

### Race Control Event Notifications

Uses the [Race Control event stream](/entities/events) for a low-latency trigger on every race control message — flag changes, incident reports, and steward notes.

You can also use the [Race Control sensor](/entities/live-data#race-control) if you prefer a sensor-state trigger with attribute access and history.

```yaml
alias: F1 - Race Control Notification
description: Sends Race Control messages as notifications in Home Assistant
trigger:
  - platform: event
    event_type: f1_sensor_race_control_event
condition: []
action:
  - service: notify.persistent_notification
    data:
      title: "Race Control"
      message: "{{ trigger.event.data.message.Message }}"
mode: queued
max: 10
```