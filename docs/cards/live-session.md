---
id: live-session
title: Live Session
description: "Keep the session name, track condition, weather and lap progress visible above your timing cards."
---

import {Figure} from '@site/src/components/Docs';

Keep the session name, track condition, weather and lap progress visible above your timing cards. Optional clocks add elapsed or remaining session time when the feed supplies it.

<Figure src="/img/cards/live-session.png" alt="Live Session card showing its dashboard layout" caption="Example Live Session layout. Appearance depends on your session, version and display options." />

## Availability

**Public live / Replay.** Enable Current Session and the live context entities you want to display: Session Status, Race Lap Count, Track Status and Track Weather. Next Race supplies upcoming-session context. Formation Start, session clocks, Overtake Mode and Straight Mode add optional detail. Core session context uses public timing and can also follow a replay.

## Add the card

1. Open your dashboard, select **Edit dashboard**, then **Add card**.
2. Search for **F1** and select the Live Session card.
3. Select Current Session under **Data Sources**. In **Display Options**, keep flag, track status and lap progress visible; enable elapsed or remaining time only if you also enable those sensors. Use automatic layout first, then choose a compact or full layout to suit the space.
4. Select **Save**.

If the card is missing from the picker, follow [Card installation](/cards/installation). With more than one F1 Sensor entry, use the sources from the same entry; see [Entity selection](/cards/shared-options#entity-selection).

### Minimal YAML

Use this in a manual dashboard card. Replace any entity ID with the one in your installation if it differs.

```yaml
type: custom:f1-live-session-card
session_entity: sensor.f1_current_session
theme_mode: auto
```

## Use the card

Place this card above Race Lap, Practice Timing or Qualifying Timing. It provides the context needed to interpret the timing table, including periods when a session is suspended or has not started.

## Configuration

### Data sources

The defaults below are the card’s fallback values. Automatic discovery connects standard sources to the selected integration entry, including renamed entity IDs. See [Entity selection](/cards/shared-options#entity-selection).

| Option | Default | Description |
| --- | --- | --- |
| `session_entity` | `sensor.f1_current_session` | Current Session for session type and context. Select the entity from your F1 Sensor entry. |
| `session_status_entity` | `sensor.f1_session_status` | Session Status for active/live/replay context. Select the entity from your F1 Sensor entry. |
| `formation_start_entity` | `binary_sensor.f1_formation_start` | Formation Start indicator. Select the entity from your F1 Sensor entry. |
| `lap_count_entity` | `sensor.f1_race_lap_count` | Race Lap Count for completed and total laps. Select the entity from your F1 Sensor entry. |
| `track_status_entity` | `sensor.f1_track_status` | Track Status for flags and race-neutralization context. Select the entity from your F1 Sensor entry. |
| `weather_entity` | `sensor.f1_track_weather` | Live Track Weather measurements. |
| `next_race_entity` | `sensor.f1_next_race` | Next Race for the next weekend and session schedule. Select the entity from your F1 Sensor entry. |
| `session_time_remaining_entity` | `sensor.f1_session_time_remaining` | Optional Session Time Remaining clock. Select the entity from your F1 Sensor entry. |
| `session_time_elapsed_entity` | `sensor.f1_session_time_elapsed` | Optional Session Time Elapsed clock. Select the entity from your F1 Sensor entry. |
| `overtake_mode_entity` | `binary_sensor.f1_overtake_mode` | Optional Overtake Mode indicator. Select the entity from your F1 Sensor entry. |
| `straight_mode_entity` | `sensor.f1_straight_mode` | Optional Straight Mode status. Select the entity from your F1 Sensor entry. |
| `no_spoiler_entity` | `switch.f1_no_spoiler_mode` | Entity whose `on` state enables spoiler protection. See [No Spoiler Mode](/features/no-spoiler-mode). |

### Display and behavior

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | `dark`, `light` or `auto`; `auto` follows Home Assistant. See [Appearance](/cards/shared-options#appearance). |
| `show_flag` | `true` | Show the track status flag indicator |
| `show_lap_progress` | `true` | Show the lap progress bar |
| `show_track_status` | `true` | Show the current track status label |
| `show_weather` | `true` | Show live track weather |
| `show_time_remaining` | `false` | Show session time remaining when available |
| `show_time_elapsed` | `false` | Show session time elapsed when available |
| `layout_mode` | `auto` | `auto`, `compact` or `full`. Automatic layout responds to available card space. |
| `font_style` | `wide` | `wide`, `balanced` or `system`. See [Typography](/cards/shared-options#typography). |

All bundled cards also support [`f1_entry_id` and card actions](/cards/shared-options). Home Assistant layout settings remain available in the dashboard editor.

## When data is missing

Outside an active session, live measurements and clocks may be unavailable. A missing remaining-time field is normal when the source does not supply a usable clock. If every field is empty during a session, check that the selected entities are enabled and belong to the same F1 Sensor entry.

For an **Entity not found** message, check the selection in **Data Sources** and confirm that the entity is enabled in F1 Sensor. For a missing card type or an old interface after an update, use the [card loading checks](/cards/installation#card-loading-checks).

## Related

- [Race Lap](/cards/race-lap)
- [Qualifying Timing](/cards/qualifying-timing)
- [Practice Timing](/cards/practice-timing)
- [All dashboard cards](/cards/cards-overview)
