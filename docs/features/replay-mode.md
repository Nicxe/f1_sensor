---
id: replay-mode
title: Watch a session with Replay Mode
description: Load a completed Formula 1 session, match it to your recording, and control dashboard playback.
---

import {FlowSteps} from '@site/src/components/Docs';

Replay Mode plays a completed session's archived timing through Home Assistant while you watch a recording. Dashboards, track-flag lights, Race Control notifications and incident alerts can follow the recorded session; optional incident locations need usable archived Track Map data.

## Before you start

- Connect a Formula 1 account through [F1TV access setup](/help/f1tv-auth-setup). A free account worked for the tested archive resources; each session still needs published files.
- Have your own video recording or replay service. F1 Sensor supplies timing data, not F1 TV video replay access.
- For watching later, turn on [No Spoiler Mode](/features/no-spoiler-mode) **before the live session starts**. Keep it on until you want to reveal current results.
- Use normal Replay Mode. A local dump, developer build and paid F1 TV subscription are not required for the tested timing archive.

:::warning[Rewinding can repeat actions]
Rewinding can replay historical state changes and events. Replay-driven automations, lights, incident alerts and notifications may run again by design.
:::

---

<FlowSteps label="Replay workflow" steps={[
  {title: 'Select', description: 'Choose a season, event and completed session.'},
  {title: 'Load', description: 'Download the available archived timing streams.'},
  {title: 'Align', description: 'Find the same session moment in your TV replay.'},
  {title: 'Play', description: 'Start playback, then pause or seek as needed.'},
]} />

## What to expect

Load the session, align the same start reference on your TV, then play. The selectors, buttons and media player let you pause or seek later. Archive access and live-feed permissions are separate.

[Watch Replay Mode in the introduction on YouTube (01:38)](https://www.youtube.com/watch?v=R72LXKdiNxA&t=98s).

:::info[Standard entity IDs]
This page uses the standard Replay Mode entity IDs for new installations, such as `select.f1_replay_year` and `media_player.f1_replay_player`.

If you upgraded from an older release and already have different registry IDs, keep using those existing entities. The integration does not rename installed entities automatically.
:::

---

## Using Replay Mode

### Step 1 - Select a session

1. To use the preselected year, press `button.f1_replay_refresh` to load its sessions. To use a different year, choose it with `select.f1_replay_year`; this loads that year's sessions.
2. Use `select.f1_replay_session` to pick a session from that year.

The list is loaded on demand to avoid unnecessary archive requests. After loading, it shows completed sessions from the selected year, with the most recent first.
:::info[Data availability]
Archive publication is controlled by Formula 1. A completed session may not be available immediately; refresh the session list later if it is missing.
:::

### Step 2 - Choose the start reference

Use `select.f1_replay_start_reference` to choose where playback begins:

- **Formation start (race/sprint)** - Playback starts from the formation lap. This is the default and recommended for races and sprints, since you can focus on watching the start rather than pressing a button at lights out.
- **Session live** - Playback starts from lights out (races) or pit exit open (practice/qualifying). This is the most precise option but requires you to press play at the exact moment.
:::info
The formation start option only applies to race and sprint sessions. For practice and qualifying, playback always starts from when the session went live.
:::
:::tip[Formation lap timing]
The formation lap start point is estimated. If the archive does not provide a usable earlier formation marker, playback starts at the session-live reference instead. Compare the loaded start with your recording and adjust playback if needed.
:::

### Step 3 - Load the session

Press `button.f1_replay_load` to download the session data.

The `sensor.f1_replay_status` shows download progress.

### Step 4 - Sync with your broadcast

Start the session on your TV or streaming service. When you see the session begin, press `button.f1_replay_play` or use `media_player.f1_replay_player` at that exact moment.

**For races and sprints** (with formation start reference): Press play when the formation lap begins.

**For races and sprints with Session live:** press play at lights out.

**For practice and qualifying:** press play when the session goes live at pit exit opening.

From this point, the replayed live sensors follow what you see on screen.

### Step 5 - Control playback

If you pause your TV, pause the replay to stay in sync. When you resume, resume the replay.

- **Pause** - Press `button.f1_replay_pause` or pause `media_player.f1_replay_player`
- **Resume** - Press `button.f1_replay_play` or play `media_player.f1_replay_player`
- **Seek with the playbar** - Drag the playbar in the Replay module in the F1 Sensor card and release it at the target position
- **Back 30 seconds** - Press `button.f1_replay_back_30` to move replay back 30 seconds
- **Forward 30 seconds** - Press `button.f1_replay_forward_30` to move replay forward 30 seconds
- **Stop** - Press `button.f1_replay_stop` to end playback and return to idle

---

## Replay Seek Controls

Use the [playbar, 30-second buttons or verified lap and qualifying markers](/features/replay-seeking) to match your recording. Rewinding can replay historical events and notifications again.

<span id="dragging-the-playbar" />

<span id="how-the-30-second-buttons-work" />

<span id="syncing-to-a-lap-or-qualifying-part" />

<span id="what-to-expect-1" />

<span id="best-way-to-use-it" />

[Read the full seek behavior and practical sync steps](/features/replay-seeking#replay-seek-controls).


## Replay improvements

Loading and seeking restore the session's accumulated timing state. Large jumps can still briefly show `seeking`; wait for that operation to finish before sending another command. A previously watched session may need downloading again.

The selectors, playback buttons and media player remain the controls for Replay Mode. You do not need to recreate them after updating. Rewinding can still emit the same historical events again, so keep the notification behavior described above in mind.

A loaded replay also supplies selected-lap comparisons in [Replay telemetry](/features/weekend-analysis#compare-replay-laps). Browsing [Historical archive](/features/historical-results) is a separate operation: it displays classifications and does not load or start a replay.

### Archive checks and saved sessions

Before playback, F1 Sensor compares the archive's session and meeting identifiers with your selection. A conflicting identifier stops loading before any archived sensor updates or notifications are delivered. Choose another session, or retry after the archive has been corrected. Missing identifiers leave the archive unverified; matching identifiers do not guarantee that every timing value is correct.

Elapsed archive times use millisecond precision. Fractional seconds are interpreted consistently, finer precision is truncated, and invalid timestamps are skipped instead of becoming the start of the session. Durations can exceed 24 hours.

A saved session from an incompatible timestamp parser is downloaded again when you load it. If that download fails, playback remains unavailable and you can retry later. A replacement becomes usable only after its files have been built and checked. Compatible saved sessions are reused, and index-only improvements do not require another download.

## Replay Mode vs Developer mode

Use Replay Mode to watch a completed session. [Developer mode](/help/developer-mode#developer-mode-vs-replay-mode) is for repeatable tests using a local dump; it starts when the integration loads, has no pause or seek controls, and is hidden in normal builds.

## Replay Mode vs live F1TV Auth

Public live timing works without a token. [F1TV Auth](/features/f1tv-auth) is used both for additional live features during a real live session and for downloading Replay Mode data after the session has completed.

This means Replay Mode can sometimes show data that public live timing did not show during the live session. For example, Pit Stops, Team Radio, Championship Prediction, Track Map, and incident location context can work in replay when the archive contains the needed data.

Pit counts and detailed stop records are separate. The saved Singapore and United States race archives contain stationary and pit-lane times that were absent from the sampled United States live `PitStopSeries` delivery. This does not guarantee every archive or immediate publication after a session. A post-session download failure alone does not prove that the account lacks live access. Replay uses archived detailed stop records; the live pit-lane-time fallback does not fill a missing replay archive. See [Pit Stops](/entities/pit-stops) for the meaning of counts and nullable time fields.

## What Replay Mode can replay

| Data | Replay behavior |
| --- | --- |
| Public live timing | Session status, track status, Race Control, weather, driver timing, tyres, and top three can replay when available in the archive |
| Pit Stops | Works when the replay archive contains pit stop data |
| Team Radio | Works when the replay archive contains team radio clips |
| Championship Prediction | Works when the replay archive contains prediction data |
| Formation Start | Works for race and sprint sessions when the replay data supports it |
| Track Map | Best effort when the replay archive contains car position data |
| Incident Detection | Works from replayed public timing and can use replay Track Map location context when available |

Replay Track Map is best effort. If the loaded session does not contain usable car position data, the [Track Map](/features/track-map) card waits instead of showing misleading car positions.

---

## Entities

Replay Mode adds several control entities to Home Assistant.

### Configuration entities

The [complete control list](/reference/replay-controls#configuration-entities) contains the year, session and start-reference selectors plus load, play, pause, stop, seek and refresh buttons.

### Media player

Use `media_player.f1_replay_player` for standard play, pause, stop, seek and position tracking. It can be controlled by compatible media players, dashboards and remote controls. See [states and attributes](/reference/replay-controls#media-player-entity).

### Status sensor

| Entity | Purpose |
| --- | --- |
| `sensor.f1_replay_status` | Shows current replay state and progress |

### Dashboard card

Add the **Replay** module to the [F1 Sensor card](/cards/modular). It combines the Replay Mode selectors, load/play/pause/stop controls, lap or qualifying-part sync, drag-to-seek playbar, 30-second seek buttons, refresh button and progress display in one module. Add **Replay telemetry** when you also want to compare recorded driver laps.

---

## Media Player Entity

Use `media_player.f1_replay_player` for standard play, pause, stop and seek. The [Replay control reference](/reference/replay-controls#media-player-entity) lists its states and attributes.

## Replay Status Sensor

`sensor.f1_replay_status` reports loading, ready, playing, paused and seeking. See [status fields and progress](/reference/replay-controls#replay-status-sensor) when building your own dashboard.

## Example: Sync with Apple TV

Use the [Replay Sync blueprint](/blueprints/replay-sync) after manual alignment, or copy the [complete Apple TV YAML alternative](/blueprints/replay-sync#yaml-alternative). It follows play and pause, not playback position or TV seek.

## Additional entities in Replay Mode

Replay Mode sends supported archived timing through the integration’s live entities. This can include data that public live timing does not provide. Enabled entities can update when the archive contains the required data, and some can also update live with optional [F1TV Auth](/features/f1tv-auth).

| Entity | Description |
| --- | --- |
| `sensor.f1_pitstops` | Pit stop events and timing per car |
| `sensor.f1_championship_prediction_drivers` | Predicted Drivers Championship standings |
| `sensor.f1_championship_prediction_teams` | Predicted Constructors Championship standings |
| `binary_sensor.f1_formation_start` | Formation start detection for race and sprint sessions |

Enabled entities can remain registered before playback starts. Outside Replay Mode, availability depends on the live session, optional F1TV Auth and the published data. See the [availability matrix](/features/f1tv-auth#availability-matrix).

The [Track map module](/features/track-map) is not a normal entity. It can show replay car positions when the replay archive contains the needed position data.

For full details on each entity, see the [Live Data reference](/entities/live-data).

---

## Limitations

- While replay is active, the integration does not receive live data. Stop the replay to return to live mode.
- Replay does not replace every entity with historical data. In particular, [Starting Grid](/entities/starting-grid) keeps the current or upcoming weekend context instead of being overwritten by an older replay.
- The live delay calibration feature is disabled during replay.
- Long seeks can briefly show the replay state as `seeking` while the integration restores the correct session state.
- Rewinding can replay historical events again, so replay-driven automations and notifications may run again.
- Replayed Track Map location context is best-effort and may be missing for sessions without usable car position data.
- Replay Mode does not protect you from spoilers on its own. Use [No Spoiler Mode](/features/no-spoiler-mode) to keep your dashboard frozen until you are ready to watch.
