---
id: track-status-light
title: Track Status Light
---

# Track Status Light

Turn any RGB light into a live F1 race status indicator. The light color changes automatically to reflect the current track condition — green for clear racing, yellow for caution, red for a red flag, and distinct colors for Safety Car and Virtual Safety Car.

The blueprint is built around the [Track Status](/entities/live-data#track-status) and [Session Status](/entities/live-data#session-status) sensors from F1 Sensor, and includes optional gates for presence, media player state, and a do-not-disturb time window.

:::tip Sync with your TV
For the light to change at the same time as you see the flag on screen, configure the [Live Delay](/features/live-delay) to match your broadcast offset.
:::

---

## Import the Blueprint

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2FNicxe%2Ff1_sensor%2Fmain%2Fblueprints%2Ff1_track_status.yaml)

Or go to **Settings > Automations & Scenes > Blueprints** and import manually using the URL:

```
https://raw.githubusercontent.com/Nicxe/f1_sensor/main/blueprints/f1_track_status.yaml
```

---

## Requirements

- F1 Sensor integration installed with live data enabled
- An RGB-capable light entity in Home Assistant

---

## Step-by-step Setup

### Step 1 — Create an automation from the blueprint

1. Go to **Settings > Automations & Scenes > Blueprints**
2. Find **F1 Sensor - Track Status Light (Modern)**
3. Click **Create Automation**

---

### Step 2 — Data Sources

Link the blueprint to the correct F1 Sensor entities.

| Setting | Description |
| --- | --- |
| **Session Status Sensor** | Select the `*_session_status` sensor. This determines when the automation is active |
| **Track Status Sensor** | Select the `*_track_status` sensor. This drives the light color |
| **Active Session Phases** | The light only updates when the session is in one of these phases. Defaults to `live` and `suspended` |

:::info Session phases
The session goes through a sequence of phases during an event. During `pre`, `break`, `finished`, `finalised`, and `ended` the light will not update unless you include those phases in the active list. See [Session Status values](/entities/live-data#session-status) for the full list.
:::

---

### Step 3 — Session Scope (Optional)

Limit the automation to specific session types, for example only during Race and Qualifying, while ignoring Practice sessions.

| Setting | Description |
| --- | --- |
| **Enable Current Session Filter** | When enabled, the light only updates during the selected session types. Disabled by default |
| **Current Session Sensor** | Select the `*_current_session` sensor. Required when the filter is enabled |
| **Allowed Current Sessions** | Which session types should activate the light. Defaults to all sessions |

:::info
When this filter is enabled, the automation checks the [Current Session](/entities/live-data#current-session) sensor to decide whether to run. If the session type is not in the allowed list, light updates are suppressed entirely for that session.
:::

---

### Step 4 — Light Behavior

| Setting | Description |
| --- | --- |
| **Light Entity** | Select the RGB light that should follow track status |
| **Brightness** | Brightness percentage when the light turns on. Defaults to `100%` |
| **Transition Time** | How long color changes take in seconds. Defaults to `1s` |
| **Snapshot Light At Session Start** | Saves the current light state when the session enters active phases. Used to restore the light to its pre-race state when the session ends. Defaults to `on` |
| **Snapshot Before Alerts** | Saves the light state before a YELLOW, RED, SC, or VSC update. Used to restore the light after an alert clears. Defaults to `on` |

:::info About snapshots
Snapshots are temporary scenes stored in Home Assistant for the duration of the session. They allow the blueprint to restore your light to exactly how it looked before an incident — for example, going back to your normal living room scene once a yellow flag clears. They are automatically deleted when the session ends, unless you disable **Delete Runtime Scenes On Session End** in the session end settings.
:::

---

### Step 5 — Flag Colors

Set the RGB color for each track status. These settings are collapsed by default and come with sensible defaults.

| Track Status | Default Color | When it appears |
| --- | --- | --- |
| **CLEAR** | Green `[0, 255, 0]` | Normal racing conditions |
| **YELLOW** | Yellow `[255, 255, 0]` | Caution, hazard on track |
| **RED** | Red `[255, 0, 0]` | Session stopped |
| **VSC** | Yellow `[255, 255, 0]` | Virtual Safety Car deployed |
| **SC** | Red `[255, 0, 0]` | Safety Car deployed |

---

### Step 6 — Alert Behavior

Configure how the light behaves during flag alerts. YELLOW and RED share one set of options, while SC and VSC share another. All settings in this section are collapsed by default.

**Flash Interval** controls the time between on and off pulses for any flashing mode.

#### YELLOW and RED

| Setting | Description |
| --- | --- |
| **YELLOW/RED Mode** | How the light behaves when YELLOW or RED is active |
| **YELLOW/RED Flash Duration** | How long the light flashes before switching to the after-flash behavior. Used only in timed mode. Defaults to `10s` |
| **YELLOW/RED After Timed Flash** | What the light does after timed flashing ends |

#### SC and VSC

| Setting | Description |
| --- | --- |
| **SC/VSC Mode** | How the light behaves when SC or VSC is active |
| **SC/VSC Flash Duration** | How long the light flashes before switching to the after-flash behavior. Used only in timed mode. Defaults to `10s` |
| **SC/VSC After Timed Flash** | What the light does after timed flashing ends |

**Available modes:**

| Mode | Behavior |
| --- | --- |
| Steady color only | Light switches to the flag color without flashing |
| Flash for a duration then continue | Light flashes for the configured duration, then switches to the after-flash setting |
| Flash continuously until status changes | Light keeps flashing until the track status changes away |

**After timed flash options:**

| Option | Behavior |
| --- | --- |
| Keep steady color | Light stays on the flag color |
| Restore pre-alert scene | Light restores to the state it was in before the alert began (requires **Snapshot Before Alerts** to be enabled) |

---

### Step 7 — CLEAR Behavior

Configure what the light does when the track status returns to CLEAR. This section is collapsed by default.

| Setting | Description |
| --- | --- |
| **CLEAR Mode** | How the light responds when CLEAR is received |
| **CLEAR Restore Delay** | How long the light shows the CLEAR color before restoring. Used only in delayed restore mode. Defaults to `5s` |

**Available modes:**

| Mode | Behavior |
| --- | --- |
| Keep CLEAR color | Light switches to the CLEAR color and stays there |
| Restore pre-alert scene immediately | Light restores to the state it was in before the alert, skipping the CLEAR color entirely |
| CLEAR color then restore after delay | Light shows the CLEAR color briefly, then restores to the pre-alert state after the configured delay |

:::info
The restore options require **Snapshot Before Alerts** to be enabled in the Light Behavior section.
:::

---

### Step 8 — Activation Conditions (Optional)

These optional gates must all pass before the light updates. All are disabled by default.

| Setting | Description |
| --- | --- |
| **Presence Devices** | Select one or more device trackers. At least one must be home for the light to update |
| **Media Player Gate** | Select a media player. The light only updates when the player is on, idle, or playing |
| **Enable Do Not Disturb Window** | Block light updates during a specific time window |
| **DND Start Time** | When the DND window begins. Defaults to `23:00` |
| **DND End Time** | When the DND window ends. Defaults to `07:00`. Overnight windows (e.g. 23:00–07:00) are supported |

---

### Step 9 — Session End Behavior (Optional)

Configure what happens to the light after the session leaves the active phases. This section is collapsed by default.

| Setting | Description |
| --- | --- |
| **End Delay** | Wait this many minutes after the session ends before applying the end action. Defaults to `0` |
| **End Action** | What to do after the delay |
| **Neutral Color** | Color used when End Action is set to **Set neutral color**. Defaults to white |
| **Delete Runtime Scenes On Session End** | Removes the temporary pre-race and pre-alert scenes from Home Assistant after the end action runs. Defaults to `on` |

**End action options:**

| Option | Behavior |
| --- | --- |
| Keep current light state | The light stays exactly as it was when the session ended |
| Turn off light | The light turns off |
| Set neutral color | The light switches to a neutral color of your choice |
| Restore pre-race scene | The light restores to the state it was in when the session started (requires **Snapshot Light At Session Start** to be enabled) |

---

### Step 10 — Notifications (Optional)

The blueprint can also send notifications on track status changes and session end. This section is collapsed and disabled by default.

| Setting | Description |
| --- | --- |
| **Enable Notifications** | Master switch for all notification actions |
| **Notify on Track Status Updates** | Send a notification each time the track status changes |
| **Notify on Session End** | Send a notification when the session leaves the active phases |
| **Notification Actions** | Add one or more Home Assistant actions for delivery |

**Available template variables in notification actions:**

| Variable | Description |
| --- | --- |
| `{{ notification_title }}` | Pre-built title (`F1 Track Status` or `F1 Session Ended`) |
| `{{ notification_message }}` | Pre-built message describing the change |
| `{{ notification_track_state }}` | Current track status in uppercase |
| `{{ notification_session_phase }}` | Current session phase in lowercase |

---

## Testing

You can simulate track and session changes without waiting for a live session.

1. Go to **Developer Tools > States**
2. Find your `*_track_status` or `*_session_status` entity
3. Set the state manually to any valid value (e.g. `SC`, `RED`, `live`)

The automation will react immediately as if the sensor had changed naturally.

:::info
Valid track status values: `CLEAR`, `YELLOW`, `VSC`, `SC`, `RED`

Valid session phase values: `pre`, `live`, `suspended`, `break`, `finished`, `finalised`, `ended`
:::

---

## How it works

The automation has two triggers: one for track status changes and one for session status changes. When a track update arrives and all conditions pass (active session phase, presence, media player, DND window), the light switches to the matching color.

When a session enters active phases, an optional snapshot of the light state is saved. Before each YELLOW, RED, SC, or VSC update, another optional snapshot is taken. These snapshots allow the automation to restore the light to its previous state — either after an alert clears, or when the session ends.

YELLOW, RED, SC, and VSC each support three modes: a steady color, timed flashing (flash for a set duration, then continue with either steady or a restore), or continuous flashing until the status changes away.

When the CLEAR status arrives, the light can show the clear color, restore immediately to the pre-alert state, or show the clear color briefly before restoring.

When the session leaves active phases, the configured end action runs after an optional delay. Temporary scenes created during the session are cleaned up automatically when the session ends.

---

## Related

- [Track Status sensor](/entities/live-data#track-status)
- [Session Status sensor](/entities/live-data#session-status)
- [Live Delay](/features/live-delay)
- [Race Control Notifications blueprint](/blueprints/race-control-notifications)
