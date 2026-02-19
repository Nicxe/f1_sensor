---
id: race-control-notifications
title: Race Control Notifications
---

# Race Control Notifications

Get instant notifications whenever the race director sends a message — flag changes, safety car deployments, penalties, incident reports, and more.

This blueprint listens to the [Race Control sensor](/entities/live-data#race-control) and forwards messages to any notification service you choose. All filtering is optional, so you can start simple and refine over time.

:::tip Sync with your TV
For notifications to arrive at the right moment, configure the [Live Delay](/features/live-delay) to match your broadcast offset.
:::

---

## Import the Blueprint

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FNicxe%2Ff1_sensor%2Fmain%2Fblueprints%2Ff1_race_control_notifications.yaml)

Or go to **Settings > Automations & Scenes > Blueprints** and import manually using the URL:

```
https://raw.githubusercontent.com/Nicxe/f1_sensor/main/blueprints/f1_race_control_notifications.yaml
```

---

## Requirements

- F1 Sensor integration installed and configured with live data enabled
- At least one notification service available in Home Assistant (mobile app, persistent notification, TTS, etc.)

---

## Step-by-step Setup

### Step 1 — Create an automation from the blueprint

1. Go to **Settings > Automations & Scenes > Blueprints**
2. Find **F1 Sensor - Race Control Notifications**
3. Click **Create Automation**

---

### Step 2 — Configure Source

| Setting | Description |
| --- | --- |
| **Race Control Sensor** | Select the `*_race_control` sensor from your F1 Sensor integration |
| **Require Active Session Phase** | Enable this to only receive notifications during specific session phases |
| **Session Status Sensor** | Required if you enable phase filtering — select the `*_session_status` sensor |
| **Active Session Phases** | Which phases should trigger notifications. Defaults to `live` and `suspended` |

:::info
The Session Status Sensor is only needed when **Require Active Session Phase** is turned on. If you leave it off, notifications arrive for all messages regardless of session state.
:::

---

### Step 3 — Configure Filters (Optional)

All filters are optional and collapsed by default. Leave them empty to receive every race control message.

| Setting | Description |
| --- | --- |
| **Allowed Flags** | Only notify for specific flag types. Leave empty to allow all flags |
| **Allowed Categories** | Comma or semicolon-separated category names. Leave empty to allow all categories |
| **Include Keywords** | Only notify when the message contains at least one of these words |
| **Exclude Keywords** | Skip notifications when the message contains any of these words |

**Available flag values:**

| Flag | When it appears |
| --- | --- |
| `CLEAR` | Track is clear, normal racing conditions |
| `GREEN` | Session start or restart |
| `YELLOW` | Yellow flag, caution on track |
| `DOUBLE YELLOW` | Double yellow, significant hazard |
| `VSC` | Virtual Safety Car deployed |
| `SC` | Safety Car deployed |
| `RED` | Red flag, session stopped |
| `BLUE` | Blue flag shown to a driver being lapped |
| `WHITE` | Slow vehicle on track |
| `BLACK` | Driver disqualified |
| `CHEQUERED` | Session finished |

---

### Step 4 — Configure Notifications

| Setting | Description |
| --- | --- |
| **Title Prefix** | Text prepended to the notification title. Defaults to `F1 Race Control` |
| **Include Fields in Message** | Extra details added below the main message text |
| **Cooldown (seconds)** | Pause between notifications to reduce alert spam. Defaults to `0` (no cooldown) |
| **Notification Actions** | Add one or more Home Assistant actions for delivery |

**Available fields for the message body:**

| Field | What it contains |
| --- | --- |
| Category | The type of race control event |
| Flag | The flag associated with the message |
| Scope | Track-wide or specific sector/car |
| Sector | Which sector is affected (if applicable) |
| Car number | The car number if the message targets a specific driver |
| UTC | Timestamp of the message |
| Event ID | Internal event identifier |
| Session phase | Current session phase at the time of the message |

---

### Step 5 — Add a Notification Action

In the **Notification Actions** field, add your delivery action. Below are examples for the most common services.

**Mobile app notification:**

```yaml
- service: notify.mobile_app_your_phone
  data:
    title: "{{ notification_title }}"
    message: "{{ notification_message }}"
```

**Persistent notification (visible in Home Assistant UI):**

```yaml
- service: persistent_notification.create
  data:
    title: "{{ notification_title }}"
    message: "{{ notification_message }}"
```

**Text-to-speech:**

```yaml
- service: tts.speak
  target:
    entity_id: tts.home_assistant_cloud
  data:
    message: "{{ race_control_message }}"
    media_player_entity_id: media_player.living_room
```

---

## Template Variables

The following variables are available inside your notification actions:

| Variable | Description |
| --- | --- |
| `{{ notification_title }}` | Ready-to-use title combining prefix and flag |
| `{{ notification_message }}` | Ready-to-use message with selected fields |
| `{{ race_control_message }}` | The raw race control message text |
| `{{ race_control_category }}` | Event category |
| `{{ race_control_flag }}` | Flag type |
| `{{ race_control_scope }}` | Scope (track, sector, car) |
| `{{ race_control_sector }}` | Affected sector |
| `{{ race_control_car_number }}` | Car number if applicable |
| `{{ race_control_utc }}` | UTC timestamp |
| `{{ race_control_event_id }}` | Event ID |
| `{{ race_control_session_phase }}` | Current session phase |

---

## Example Configurations

### Notify only for safety car and red flag

Set **Allowed Flags** to `SC`, `VSC`, and `RED`. Leave all other filters empty.

---

### Notify only during the race

Enable **Require Active Session Phase** and set **Active Session Phases** to `live` and `suspended` only.

---

### Exclude administrative messages

Set **Exclude Keywords** to `clerk, official, document` to filter out FIA document references.

---

## Related

- [Race Control sensor](/entities/live-data#race-control)
- [Session Status sensor](/entities/live-data#session-status)
- [Live Delay](/features/live-delay)
- [Track Status Light blueprint](/blueprints/track-status-light)
