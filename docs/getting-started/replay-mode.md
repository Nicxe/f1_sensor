---
id: replay-mode
title: Replay Mode
---

Replay Mode lets you watch historical F1 sessions with full Home Assistant integration. When you play back a recorded race or qualifying from F1 TV or another service, all your automations and dashboards work exactly as they would during a live broadcast.

Your lights flash red on a red flag. Your dashboard shows live timing. Race Control messages trigger notifications. Everything stays perfectly in sync with what you see on screen.

---

## How it works

Replay Mode downloads session data from Formula 1's public archive and plays it back through the same data pipeline used during live sessions. By starting playback at the same moment the session begins on your TV, all live entities stay synchronized with the broadcast.

---

## Entities

Replay Mode adds several control entities to Home Assistant.

### Configuration entities

| Entity | Purpose |
| --- | --- |
| `select.f1_replay_year` | Select the season year |
| `select.f1_replay_session` | Select which session to replay |
| `select.f1_replay_start_reference` | Choose where playback starts |
| `button.f1_replay_load` | Download and prepare the selected session |
| `button.f1_replay_play` | Start or resume playback |
| `button.f1_replay_pause` | Pause playback |
| `button.f1_replay_stop` | Stop playback and return to idle |
| `button.f1_replay_refresh` | Refresh the session list |

### Media player

| Entity | Purpose |
| --- | --- |
| `media_player.f1_replay_player` | Standard media player with play, pause, stop and position tracking |

The media player entity lets you control replay using any media player integration or remote control. It reports current position, duration, and playback state, making it easy to integrate with other media players in your setup.

### Status sensor

| Entity | Purpose |
| --- | --- |
| `sensor.f1_replay_status` | Shows current replay state and progress |

---

## Using Replay Mode

### Step 1 - Select a session

1. Use `select.f1_replay_year` to choose the season
2. Use `select.f1_replay_session` to pick a session from that year

The session list shows all completed sessions from the selected year, with the most recent first.

:::info Data availability
Session data is typically available 15–60 minutes after a session ends. If you just finished watching a live session, wait a bit before the replay data becomes available.
:::

### Step 2 - Choose the start reference

Use `select.f1_replay_start_reference` to choose where playback begins:

- **Formation start (race/sprint)** - Playback starts from the formation lap. This is the default and recommended for races and sprints, since you can focus on watching the start rather than pressing a button at lights out.
- **Session live** - Playback starts from lights out (races) or pit exit open (practice/qualifying). This is the most precise option but requires you to press play at the exact moment.

:::info
The formation start option only applies to race and sprint sessions. For practice and qualifying, playback always starts from when the session went live.
:::

:::tip Formation lap timing
The formation lap start point is estimated with approximately one second accuracy. The live data stream does not provide an exact marker for when the formation lap begins, so there may be a small offset compared to your broadcast.
:::

### Step 3 - Load the session

Press `button.f1_replay_load` to download the session data.

The `sensor.f1_replay_status` shows download progress. Session data is cached locally, so loading the same session again is faster.

### Step 4 - Sync with your broadcast

Start the session on your TV or streaming service. When you see the session begin, press `button.f1_replay_play` or use `media_player.f1_replay_player` at that exact moment.

**For races and sprints** (with formation start reference): Press play when the formation lap begins.

**For practice and qualifying** (or session live reference): Press play when the pit exit opens and cars start leaving the garage.

From this point, all live sensors update in sync with what you see on screen.

### Step 5 - Control playback

If you pause your TV, pause the replay to stay in sync. When you resume, resume the replay.

- **Pause** - Press `button.f1_replay_pause` or pause `media_player.f1_replay_player`
- **Resume** - Press `button.f1_replay_play` or play `media_player.f1_replay_player`
- **Stop** - Press `button.f1_replay_stop` to end playback and return to idle

---

## Media Player Entity

The `media_player.f1_replay_player` entity provides standard media player controls for replay.

**State (enum)**
- One of: `idle`, `buffering`, `playing`, `paused`

**Features**
- Play, pause, and stop controls
- Position and duration tracking
- Works with any media player card or remote integration

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| media_title | string | Name of the selected session |
| media_position | number | Current position in seconds |
| media_duration | number | Total duration in seconds |
| replay_state | string | Internal replay state |
| playback_position_s | number | Current position in seconds |
| playback_remaining_s | number | Remaining time in seconds |
| playback_total_s | number | Total playback duration in seconds |

---

## Replay Status Sensor

The `sensor.f1_replay_status` entity tracks the current state and provides detailed attributes.

**State (enum)**
- One of: `idle`, `selected`, `loading`, `ready`, `playing`, `paused`

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| selected_session | string | Name of the selected session |
| download_progress | number | Download progress percentage (0–100) |
| download_error | string | Error message if download failed |
| playback_position_s | number | Current playback position in seconds |
| playback_position_formatted | string | Current position as HH:MM:SS |
| playback_total_s | number | Total playback duration in seconds |
| playback_total_formatted | string | Total duration as HH:MM:SS |
| paused | boolean | True when playback is paused |
| sessions_available | number | Number of sessions available for the selected year |
| selected_year | number | Currently selected year |

---

## Example: Sync with Apple TV

This automation keeps replay in sync with your Apple TV. When you pause the Apple TV, the replay pauses. When you play, it resumes.

```yaml
automation:
  - alias: "Pause F1 replay when Apple TV pauses"
    trigger:
      - platform: state
        entity_id: media_player.apple_tv
        to: "paused"
    condition:
      - condition: state
        entity_id: media_player.f1_replay_player
        state: "playing"
    action:
      - service: media_player.media_pause
        target:
          entity_id: media_player.f1_replay_player

  - alias: "Resume F1 replay when Apple TV plays"
    trigger:
      - platform: state
        entity_id: media_player.apple_tv
        to: "playing"
    condition:
      - condition: state
        entity_id: media_player.f1_replay_player
        state: "paused"
    action:
      - service: media_player.media_play
        target:
          entity_id: media_player.f1_replay_player
```

Replace `media_player.apple_tv` with your actual media player entity. This works with any media player that reports play and pause states.

---

## Limitations

- While replay is active, the integration does not receive live data. Stop the replay to return to live mode.
- The live delay calibration feature is disabled during replay.
