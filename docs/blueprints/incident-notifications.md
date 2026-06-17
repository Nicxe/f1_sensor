---
id: incident-notifications
title: Incident Notifications
---

Get notifications for likely stopped cars and on-track incidents without writing YAML. The blueprint listens to `f1_sensor_incident` events and uses conservative defaults so normal practice running and early candidate signals do not create noisy alerts.

For the full feature behavior, see [Incident Detection](/features/incident-detection).

:::warning[Not crash detection]
These notifications mean F1 Sensor detected a likely stopped car or on-track incident. They do not guarantee that a crash happened.
:::

:::tip[Sync with your TV]
For notifications to arrive at the right moment, configure [Live Delay](/features/live-delay) to match your broadcast offset.
:::

---

## Import the blueprint

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FNicxe%2Ff1_sensor%2Fmain%2Fblueprints%2Ff1_incident_notifications.yaml)

Or go to **Settings > Automations & Scenes > Blueprints** and import manually using the URL:

```text
https://raw.githubusercontent.com/Nicxe/f1_sensor/main/blueprints/f1_incident_notifications.yaml
```

---

## Requirements

- F1 Sensor integration installed with live data enabled
- At least one notification service available in Home Assistant
- The `f1_sensor_incident` event available during live or replay sessions

---

## Step-by-step setup

### Step 1 - Create an automation from the blueprint

1. Go to **Settings > Automations & Scenes > Blueprints**
2. Find **F1 Sensor - Incident Notifications**
3. Click **Create Automation**

### Step 2 - Choose notification targets

Configure at least one target in the **Notification Targets** section.

| Setting | Example | Description |
| --- | --- | --- |
| **Notify Services** | `notify.mobile_app_your_phone` | Enter one or more service names separated by commas or semicolons |
| **Notify Entity Targets** | `notify.your_device` | Select one or more notify entities that support `notify.send_message` |

You can use either method or combine them. The automation does not send anything until at least one notification target is configured.

### Step 3 - Review filters

The default filters are intentionally conservative.

| Setting | Default | Description |
| --- | --- | --- |
| **Minimum Confidence** | Medium | Notify for medium- and high-confidence incidents |
| **Session Types** | Race, Sprint, Qualifying | Exclude Practice, Testing, and Unknown sessions |
| **Notify Candidate Events** | Off | Ignore earlier and less certain candidate events |
| **Notify When Cleared** | Off | Do not send a separate update when the incident clears |
| **Title Prefix** | `F1 Incident Alert` | Set the notification title shown before the confidence level |

Practice sessions can include installation laps, garage work, slow running, and testing procedures. Enable Practice only if you are comfortable with more alerts, or require `high` confidence for Practice.

If you enable Candidate events, some alerts can come from F1TV Auth car movement data correlated with yellow flag, Virtual Safety Car, Safety Car, or red flag context. Keep these alerts conservative because they are earlier than confirmed public timing or Race Control evidence.

When Track Map location data is available, the event can include an optional location summary such as `on track, sector 2` or `off track, sector 1`. The blueprint can include that summary in the notification text, but Track Map and F1TV Auth are not required for the basic incident alert flow.

Public confirmed incident alerts work without F1TV Auth. F1TV Auth can improve candidate signals, and Track Map can improve location context when fresh position data exists.

Supported notification services receive a stable tag based on `incident_id`. This lets later updates replace the existing notification instead of creating a duplicate.

### Step 4 - Add activation conditions

Activation conditions are optional. Leave them empty if incident notifications should always use the filters above.

| Setting | Default | Description |
| --- | --- | --- |
| **Presence Devices** | Empty | If configured, at least one selected device tracker must be `home` |
| **Media Player Gate** | Empty | If configured, the selected media player must be `on`, `idle`, or `playing` |
| **Enable Do Not Disturb Window** | Off | Blocks incident notifications during the configured time window |
| **DND Start Time** | `23:00:00` | Start of the quiet window |
| **DND End Time** | `07:00:00` | End of the quiet window |
| **Activation Condition** | Empty | Extra Home Assistant conditions that must pass before a notification is sent |

Use activation conditions when you only want incident alerts while someone is home, while a Formula 1 screen is active, or outside quiet hours.

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
- [Incident Detection](/features/incident-detection)
- [Incident events](/entities/events#on-track-incident)
- [Race Control Notifications](/blueprints/race-control-notifications)
- [Live Delay](/features/live-delay)
