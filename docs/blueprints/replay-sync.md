---
id: replay-sync
title: F1 Replay Sync
---

# F1 Replay Sync

Keep your F1 replay in perfect sync with your TV. When you pause your main TV, the replay pauses automatically. When you resume, the replay resumes. No need to manually pause and unpause the replay every time you take a break.

The blueprint works with any media player entity — Apple TV, a smart TV, or any other player that reports play and pause states.

:::info Replay Mode required
This blueprint requires [Replay Mode](/features/replay-mode) to be set up and a session to be loaded and playing.
:::

---

## Import the Blueprint

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FNicxe%2Ff1_sensor%2Fblob%2Fmain%2Fblueprints%2Ff1_replay_sync.yaml)

Or go to **Settings > Automations & Scenes > Blueprints** and import manually using the URL:

```
https://raw.githubusercontent.com/Nicxe/f1_sensor/main/blueprints/f1_replay_sync.yaml
```

---

## Requirements

- F1 Sensor integration installed with Replay Mode enabled
- A session loaded and ready to play in Replay Mode
- A TV or media player entity that reports `playing` and `paused` states

---

## Setup

### Step 1 — Create an automation from the blueprint

1. Go to **Settings > Automations & Scenes > Blueprints**
2. Find **F1 Replay Sync**
3. Click **Create Automation**

---

### Step 2 — Configure inputs

| Setting | Description |
| --- | --- |
| **Main TV** | The media player you are watching the F1 replay on. Any media player entity works — Apple TV, smart TV, or similar |
| **F1 Replay Player** | The standard `media_player.f1_replay_player` entity from the F1 Sensor integration. If you upgraded from an older release and already have a different registry ID, select your existing replay player entity instead |

---

## How it works

The blueprint watches your main TV for state changes. When the TV pauses and the F1 replay is currently playing, the replay is paused. When the TV resumes and the replay is currently paused, the replay resumes.

Both directions include a condition check so the blueprint only acts when the replay is actually in the expected opposite state. This avoids unintended interactions — for example, if the replay is already paused for another reason, resuming the TV will not double-trigger.

---

## Related

- [Replay Mode](/features/replay-mode)
- [Live Delay](/features/live-delay)
