---
id: replay-seeking
title: Align and seek a replay
description: Use the replay playbar, 30-second buttons and verified lap or qualifying markers without losing track of event behavior.
toc_max_heading_level: 3
---

Load a session with [Replay Mode](/features/replay-mode), then use these controls to match your recording. Rewinding can emit historical events again, including notifications, lights and incident alerts.

## Replay Seek Controls
:::warning[Replay events can run again]
Seeking backward can replay historical state changes again. Automations, notifications, and incident alerts that react to replayed events may run again when those events are replayed.
:::

The replay seek controls help you line up Home Assistant with the F1 broadcast you are watching. You can use the draggable playbar for larger adjustments, or the 30-second buttons for small catch-up steps.

### Dragging the playbar

The Replay module in the F1 Sensor card shows a draggable playbar when `media_player.f1_replay_player` supports seek. Drag the handle to preview the target position, then release it to seek.

The card sends the seek command only when you release the handle. It does not send a service call for every drag movement, so the dashboard stays responsive while you choose the target point.

During a seek, the replay status may briefly show `seeking`. Longer jumps, especially with Track Map data available, can take a little longer while Replay Mode restores the correct session state.

### How the 30-second buttons work

The **Back 30 seconds** and **Forward 30 seconds** buttons are still useful for small adjustments when your TV or streaming replay is slightly ahead or behind Home Assistant.

When you press **Forward 30 seconds**, Replay Mode does not simply skip to a new position and ignore what happened in between. It applies the events inside that 30-second window first, then continues from the new position.

That means important state changes still land correctly. If a red flag, Race Control update, session clock change, or other tracked event happens inside those 30 seconds, the related entities still end up in the right state after the jump.

When you press **Back 30 seconds**, Replay Mode restores replay state for the new position and then continues from there.

### Syncing to a lap or qualifying part

The **Replay** module can jump directly to a recorded timing marker. Choose the lap that is starting on your broadcast, or choose Q1, Q2, Q3, SQ1, SQ2, or SQ3, then press **Sync replay to point**.

Race and sprint markers use the start of each lap. Qualifying and sprint qualifying markers use the first session start for each part, so a restart after a red flag does not replace the original marker. The control stays hidden when the archive does not contain a verified marker for the loaded session.

The jump uses the same replay seek behavior as the playbar. If replay is paused, it stays paused after the jump. If it is playing, playback resumes after the replay state has been restored.

### What to expect

- The playbar is available in the Replay module in the F1 Sensor card when the replay media player supports seek
- The playbar sends `media_player.media_seek` only after you release the slider
- The 30-second buttons remain available for quick manual adjustments
- Race, sprint, qualifying, and sprint qualifying sessions can expose verified sync points in the Replay module
- The feature is intended to make manual catch-up simpler, not to guarantee perfect sync with every broadcaster
- Rewinding can replay the same historical event again, which means automations and notifications may trigger again by design

### Best way to use it

If your TV or streaming replay is slightly out of sync, pause Replay Mode and use the playbar or 30-second buttons until the on-screen action matches your Home Assistant entities again. A practical reference point is the session clock, track status, or the latest Race Control message.
:::info
Seek controls are designed to preserve the visible replay state after the jump. If a session has a large amount of Track Map data, you may still see a short `seeking` period before playback resumes.
:::

---

## Replay positions and states

For media-player actions, relative playback positions, `seeking` and status fields, see the [Replay control reference](/reference/replay-controls#playback-position-and-seeking).

## Continue

- [Load and watch a session](/features/replay-mode#using-replay-mode)
- [Follow your TV’s play and pause](/blueprints/replay-sync)
- [Keep current results hidden](/features/no-spoiler-mode)
