---
id: automation
title: Automate your race weekend
description: Start with a ready-made F1 blueprint, choose a device trigger, or copy a focused Home Assistant automation recipe.
---

Make your lights follow track flags, receive Race Control messages, or get a reminder before a session. Start with a blueprint for a complete setup, or use a device trigger when you want to choose the actions yourself.

## Choose your starting point

| What you want | Recommended starting point |
| --- | --- |
| Lights that follow flags | [Track Status Light blueprint](/blueprints/track-status-light) |
| Official Race Control messages | [Race Control Notifications blueprint](/blueprints/race-control-notifications) |
| Likely stopped-car alerts | [Incident Notifications blueprint](/blueprints/incident-notifications) |
| Pause and resume replay with your TV | [Replay Sync blueprint](/blueprints/replay-sync) |
| Your own actions and conditions | Device automation steps below |

## Build a device automation

1. Open **Settings > Devices & services > Devices** in Home Assistant.
2. Select the F1 Sensor device that contains the data you need, such as **Session** for flags or **Drivers** for your favorite driver.
3. Create an automation and add the relevant device trigger.
4. Add any conditions, such as only running when you are home or watching TV.
5. Add your action, save, and check the automation trace after the matching event.

Only triggers with a backing entity appear. If a trigger is missing, check the enabled features in [Configuration](/getting-started/add-integration).

:::tip[Match your broadcast]
Configure [Live Delay](/features/live-delay) before relying on live notifications or lights. When you watch a recording, use [Replay Mode](/features/replay-mode); rewinding can trigger historical notifications again.
:::

## Device Automation Triggers

The [device trigger reference](/reference/device-triggers) lists every trigger and exactly when it fires. Choose a device below to go straight to its triggers.

### Race device

[Race week starts and ends](/reference/device-triggers#race-device).

### Session device

[Session live, flags, Safety Car, formation start, incidents, and overtake mode](/reference/device-triggers#session-device). **Session live** fires when session status changes to `live`.

### Officials device

[Race Control, FIA documents, and investigations](/reference/device-triggers#officials-device).

### Drivers device

[New team radio message and five Favorite Driver triggers](/reference/device-triggers#drivers-device).

### System device

[Live timing connectivity](/reference/device-triggers#system-device).

## YAML Examples

Open an automation’s YAML editor to use the examples below. Replace `notify.mobile_app_your_phone`, scene names, and entity IDs with those from your installation. Existing entity IDs can differ from the standard IDs in this documentation.

| Recipe | Trigger |
| --- | --- |
| [Race week reminder](#notify-when-race-week-begins) | Race week turns on |
| [Session reminder](#reminder-before-a-session-starts) | Calendar event starts in 30 minutes |
| [Session is live](#session-goes-live) | Session status becomes `live` |
| [Formation start](#race-about-to-start--formation-lap) | Formation start becomes ready |
| [Safety Car](#safety-car-deployed) | Safety Car or VSC becomes active |
| [Race Control messages](#race-control-event-notifications) | A Race Control event arrives |
| [Confirmed incidents](#possible-on-track-incident-notification) | A confirmed incident meets confidence and session filters |
| [Candidate incidents](#optional-candidate-incident-notification) | An earlier, less certain incident signal arrives |
| [Incident dashboard indicator](#dashboard-trigger-for-active-incidents) | At least one confirmed incident is active |

### Notify when race week begins

Uses the [Race Week sensor](/entities/race-week) to send a notification the moment race week starts. Useful for kicking off any weekly routines — changing dashboard views, enabling presence modes, or just a heads-up.

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

Uses the [Season Calendar](/entities/season-calendar) entity to trigger a notification 30 minutes before any session — practice, qualifying, sprint, or race.

```yaml
alias: F1 - Session starting soon
description: Send a reminder 30 minutes before any F1 session
trigger:
  - platform: calendar
    event: start
    entity_id: calendar.f1_season_calendar
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

Triggers the moment a session becomes active, when the [Session Status sensor](/entities/session-status) changes to `live`. Use this to turn on the TV, switch to an F1 dashboard, or send a notification.

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
        {{ states('sensor.f1_current_session') }} at
        {{ state_attr('sensor.f1_session_status', 'meeting_name') }} has started.
mode: single
```

---

### Formation start ready {/* #race-about-to-start--formation-lap */}

The [Formation Start sensor](/entities/formation-start) turns on when its formation start procedure is ready. It needs suitable replay or authenticated live data. Treat this as a timing marker, not a guarantee that the broadcast has reached a particular frame or that lights out is a fixed number of seconds away.

```yaml
alias: F1 - Formation start ready
description: Notify when the formation start marker is ready
trigger:
  - platform: state
    entity_id: binary_sensor.f1_formation_start
    to: "on"
condition: []
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "Formation start"
      message: "The F1 formation start marker is ready."
mode: single
```

---

### Safety car deployed

Triggers when the [Safety Car sensor](/entities/safety-car) turns on. Combine with the Race Control Notifications blueprint for detailed messages, or use this as a quick standalone trigger.

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
      message: "Safety car deployed — track status: {{ state_attr('binary_sensor.f1_safety_car', 'track_status') }}"
mode: single
```

---

### Race Control Event Notifications

Uses [Race Control events](/entities/events) for a low-latency trigger on every race control message — flag changes, incident reports, and steward notes.

You can also use the [Race Control sensor](/entities/race-control) if you prefer a sensor-state trigger with attribute access and history.

```yaml
alias: F1 - Race Control Notification
description: Sends Race Control messages as notifications in Home Assistant
trigger:
  - platform: event
    event_type: f1_sensor_race_control_event
condition: []
action:
  - action: persistent_notification.create
    data:
      title: "Race Control"
      message: "{{ trigger.event.data.message.Message }}"
mode: queued
max: 10
```

---

### Possible on-track incident notification

Uses the [`f1_sensor_incident` event](/entities/events#on-track-incident) to notify only for confirmed medium or high confidence incidents during race, sprint, or qualifying sessions. For a ready-made version, see the [Incident Notifications blueprint](/blueprints/incident-notifications). For behavior details, see [Incident Detection](/features/incident-detection).

:::tip[Sync with your TV]
Incident events respect Live Delay, so set [Live Delay](/features/live-delay) to match your broadcast if you want notifications to line up with the pictures.
:::

```yaml
alias: F1 - Possible on-track incident
description: Notify for confirmed likely stopped cars or on-track incidents
trigger:
  - platform: event
    event_type: f1_sensor_incident
condition:
  - condition: template
    value_template: "{{ trigger.event.data.phase == 'confirmed' }}"
  - condition: template
    value_template: "{{ trigger.event.data.confidence in ['medium', 'high'] }}"
  - condition: template
    value_template: "{{ trigger.event.data.session.session_type in ['race', 'sprint', 'qualifying'] }}"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "Possible F1 incident"
      message: >
        {% set data = trigger.event.data %}
        {% set location = data.get('location') or {} %}
        {{ trigger.event.data.driver.tla }} may have stopped on track
        during {{ trigger.event.data.session.session_name }}.
        {% if location.get('description') and not location.get('stale', true) %}
        Location: {{ location.get('description') }}
        {% endif %}
mode: queued
max: 5
```

The wording is intentionally neutral. F1 Sensor detects likely stopped cars and on-track incidents, not guaranteed crashes. The example includes location text only when the event marks that context as fresh.

---

### Optional candidate incident notification

Candidate incidents are earlier and less certain than confirmed incidents. They can come from public context and can also be improved by optional F1TV Auth car movement data when it correlates with flag or Safety Car context.

:::warning[Advanced use]
Use candidate notifications only if you are comfortable with more false positives. Keep the wording neutral and consider limiting this automation to races and sprints.
:::

```yaml
alias: F1 - Candidate on-track incident
description: Advanced alert for candidate incident events
trigger:
  - platform: event
    event_type: f1_sensor_incident
condition:
  - condition: template
    value_template: "{{ trigger.event.data.phase == 'candidate' }}"
  - condition: template
    value_template: "{{ trigger.event.data.confidence in ['medium', 'high'] }}"
  - condition: template
    value_template: "{{ trigger.event.data.session.session_type in ['race', 'sprint'] }}"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "Possible F1 incident candidate"
      message: >
        {% set data = trigger.event.data %}
        {% set location = data.get('location') or {} %}
        {{ data.driver.tla }} may be slow or stopped
        during {{ data.session.session_name }}.
        {% if location.get('description') and not location.get('stale', true) %}
        Location: {{ location.get('description') }}
        {% endif %}
mode: queued
max: 5
```

---

### Dashboard trigger for active incidents

Use the [On-track Incident binary sensor](/entities/on-track-incident) when you only need to know whether any confirmed incident is currently active.

```yaml
alias: F1 - Incident indicator on
description: Turn on a scene while a confirmed incident is active
trigger:
  - platform: state
    entity_id: binary_sensor.f1_on_track_incident
    to: "on"
condition: []
action:
  - service: scene.turn_on
    target:
      entity_id: scene.f1_caution
mode: single
```
