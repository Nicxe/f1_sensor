---
id: incident-notifications
title: Incident Notifications
---

# Incident Notifications

Get notifications for likely stopped cars and on-track incidents without writing YAML. The blueprint listens to `f1_sensor_incident` events and uses conservative defaults so normal practice running and early candidate signals do not create noisy alerts.

:::warning[Not crash detection]
These notifications mean F1 Sensor detected a likely stopped car or on-track incident. They do not guarantee that a crash happened.
:::

:::tip[Sync with your TV]
For notifications to arrive at the right moment, configure [Live Delay](/features/live-delay) to match your broadcast offset.
:::

---

## Import the Blueprint

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FNicxe%2Ff1_sensor%2Fmain%2Fblueprints%2Ff1_incident_notifications.yaml)

Or go to **Settings > Automations & Scenes > Blueprints** and import manually using the URL:

```text
https://raw.githubusercontent.com/Nicxe/f1_sensor/main/blueprints/f1_incident_notifications.yaml
```

---

## Requirements

- F1 Sensor integration installed with live data enabled
- At least one notification service available in Home Assistant
- The `f1_sensor_incident` event stream available during live or replay sessions

---

## Step-by-step Setup

### Step 1 - Create an automation from the blueprint

1. Go to **Settings > Automations & Scenes > Blueprints**
2. Find **F1 Sensor - Incident Notifications**
3. Click **Create Automation**

### Step 2 - Choose notification actions

Add one or more Home Assistant notification actions. Mobile app notifications and persistent notifications both work.

```yaml
- service: notify.mobile_app_your_phone
  data:
    title: "{{ notification_title }}"
    message: "{{ notification_message }}"
```

### Step 3 - Review filters

The default filters are intentionally conservative.

| Setting | Default | Description |
| --- | --- | --- |
| **Minimum confidence** | `medium` | Notify for `medium` and `high` incidents |
| **Allowed phases** | `confirmed`, `updated` | Ignore early `candidate` events by default |
| **Allowed sessions** | Race, Sprint, Qualifying | Practice is excluded by default to reduce noisy alerts |
| **Notify when cleared** | Off | Cleared updates are available but not sent by default |
| **Notification tag** | `incident_id` | Lets supported notify targets update the same notification for later updates |

Practice sessions can include installation laps, garage work, slow running, and testing procedures. Enable Practice only if you are comfortable with more alerts, or require `high` confidence for Practice.

If you enable Candidate events, some alerts can come from F1TV Auth `CarData.z` low-speed telemetry correlated with yellow flag, Virtual Safety Car, Safety Car, or red flag context. Keep these alerts conservative because they are earlier than confirmed public timing or Race Control evidence.

When Track Map `Position.z` is available, the event can include an optional location summary such as `on track, sector 2` or `off track, sector 1`. The blueprint can include that summary in the notification text, but `Position.z` and F1TV Auth are not required for the basic incident alert flow.

---

## Notification wording

Blueprint messages use neutral wording such as:

```text
Possible on-track incident: GAS stopped
Session: Race
Location: on track, sector 2
```

Avoid wording such as "crash" unless Race Control explicitly uses that term in the message you send.

---

## Related

- [On-track Incident binary sensor](/entities/live-data#on-track-incident)
- [Incident event stream](/entities/events#on-track-incident)
- [Race Control Notifications](/blueprints/race-control-notifications)
- [Live Delay](/features/live-delay)
