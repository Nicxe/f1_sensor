---
id: replay-controls
title: Replay controls
description: Find Replay Mode selectors, buttons, media player actions, playback states, and status attributes.
---

Use these entities to select, load, and control a completed F1 session. For the normal watching workflow, follow [Replay Mode](/features/replay-mode).

## Configuration entities

| Entity | Purpose |
| --- | --- |
| `select.f1_replay_year` | Select the season year |
| `select.f1_replay_session` | Select which session to replay |
| `select.f1_replay_start_reference` | Choose where playback starts |
| `button.f1_replay_load` | Download and prepare the selected session |
| `button.f1_replay_play` | Start or resume playback |
| `button.f1_replay_pause` | Pause playback |
| `button.f1_replay_stop` | Stop playback and return to idle |
| `button.f1_replay_back_30` | Move replay back 30 seconds |
| `button.f1_replay_forward_30` | Move replay forward 30 seconds |
| `button.f1_replay_refresh` | Refresh the session list |

## Media Player Entity

The `media_player.f1_replay_player` entity provides standard media player controls for replay.

**State (enum)**
- One of: `idle`, `buffering`, `playing`, `paused`

**Features**
- Play, pause, and stop controls
- Seek to a specific playback position
- Position and duration tracking
- Can be controlled through standard Home Assistant media player actions and compatible cards or automations

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| media_title | string | Name of the selected session |
| media_position | number | Current position in seconds |
| media_duration | number | Total duration in seconds |
| replay_state | string | Replay state (`idle`, `selected`, `loading`, `ready`, `playing`, `paused`, `seeking`) |
| selected_session | string | Name of the selected session |
| selected_session_id | string | Internal session identifier (best effort) |
| playback_position_s | number | Current position in seconds |
| playback_remaining_s | number | Remaining time in seconds |
| playback_total_s | number | Total playback duration in seconds |
| session_start_offset_s | number | Start offset in seconds from the underlying session archive (best effort) |

---

## Replay Status Sensor

The `sensor.f1_replay_status` entity tracks the current state and provides detailed attributes.

**State (enum)**
- One of: `idle`, `selected`, `loading`, `ready`, `playing`, `paused`, `seeking`

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
| session_start_offset_s | number | Start offset in seconds from the underlying session archive (best effort) |
| paused | boolean | True when playback is paused |
| sessions_available | number | Number of sessions available for the selected year |
| selected_year | number | Currently selected year |
| index_year | number | Year that the session index was loaded from (best effort) |
| index_status | string | Index status such as `ok`, `no_data`, or `error` (best effort) |
| index_error | string | Error details when index fetch fails (best effort) |


## Playback position and seeking

Playback positions and duration are relative to the chosen playback start reference. `session_start_offset_s` is the session-start offset in the archive; it is not the current playback position.

The media player reports `buffering` while loading or seeking. Its detailed `replay_state` distinguishes `loading` from `seeking`, and `selected` or `ready` from `idle`. During loading or seeking, the standard media position and duration can be zero; use the replay state to decide what to display.

Seek is supported when replay is `ready`, `playing`, or `paused`. For example, seek to 90 seconds after the chosen start reference:

```yaml
action: media_player.media_seek
target:
  entity_id: media_player.f1_replay_player
data:
  seek_position: 90
```

:::warning[Rewinding can repeat events]
Historical state changes and events can be emitted again when you rewind. Replay-driven automations, lights, and notifications may run again.
:::

## Next steps

- [Load and watch a replay](/features/replay-mode)
- [Pause and resume with your TV](/blueprints/replay-sync)
- [Keep upcoming results hidden](/features/no-spoiler-mode)
- [Diagnose replay loading or playback](/entities/diagnostics#replay-status)
