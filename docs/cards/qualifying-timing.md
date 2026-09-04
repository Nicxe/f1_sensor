---
id: qualifying-timing
title: Qualifying Timing
description: "Follow qualifying order, current sectors and Q1, Q2 and Q3 times in one table."
---

import {Figure} from '@site/src/components/Docs';

Follow qualifying order, current sectors and Q1, Q2 and Q3 times in one table. Eliminated drivers are dimmed so the active field remains easy to follow.

<Figure src="/img/cards/qualifying-timing.png" alt="Qualifying Timing card showing its dashboard layout" caption="Example Qualifying Timing layout. Appearance depends on your session, version and display options." />

## Availability

**Qualifying / Replay.** Enable Driver Positions and Current Session. Driver List, Current Tyres and Session Status add names, tyres and session context. The card is intended for Qualifying and Sprint Qualifying, using public timing or an archived replay of those sessions.

## Add the card

1. Open your dashboard, select **Edit dashboard**, then **Add card**.
2. Search for **F1** and select the Qualifying Timing card.
3. Select Driver Positions under **Data Sources**. Start with **Current** sector mode. Enable timing indicators if you want fastest and personal-best timing cells highlighted.
4. Select **Save**.

If the card is missing from the picker, follow [Card installation](/cards/installation). With more than one F1 Sensor entry, use the sources from the same entry; see [Entity selection](/cards/shared-options#entity-selection).

### Minimal YAML

Use this in a manual dashboard card. Replace any entity ID with the one in your installation if it differs.

```yaml
type: custom:f1-qualifying-timing-card
positions_entity: sensor.f1_driver_positions
theme_mode: auto
```

## Use the card

Current sector mode keeps S1, S2 and S3 from the same lap together. After a completed lap, its sectors remain visible and dimmed until the next S1 arrives. Personal-best and hybrid modes provide alternative comparisons without requiring extra dashboard cards.

## Configuration

### Data sources

The defaults below are the card’s fallback values. Automatic discovery connects standard sources to the selected integration entry, including renamed entity IDs. See [Entity selection](/cards/shared-options#entity-selection).

| Option | Default | Description |
| --- | --- | --- |
| `positions_entity` | `sensor.f1_driver_positions` | Driver Positions for timing and running order. Select the entity from your F1 Sensor entry. |
| `tyres_entity` | `sensor.f1_current_tyres` | Current Tyres for compound and stint detail. Select the entity from your F1 Sensor entry. |
| `drivers_entity` | `sensor.f1_driver_list` | Driver List for names, teams and driver detail. Select the entity from your F1 Sensor entry. |
| `session_entity` | `sensor.f1_current_session` | Current Session for session type and context. Select the entity from your F1 Sensor entry. |
| `session_status_entity` | `sensor.f1_session_status` | Session Status for active/live/replay context. Select the entity from your F1 Sensor entry. |
| `no_spoiler_entity` | `switch.f1_no_spoiler_mode` | Entity whose `on` state enables spoiler protection. See [No Spoiler Mode](/features/no-spoiler-mode). |

### Display and behavior

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | `dark`, `light` or `auto`; `auto` follows Home Assistant. See [Appearance](/cards/shared-options#appearance). |
| `title` | `Qualifying` | Card title |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels |
| `show_team_logo` | `true` | Show team logo |
| `show_full_name` | `false` | Show full driver names |
| `show_delta` | `true` | Show timing delta when available |
| `show_timing_indicators` | `false` | Highlight overall fastest, personal fastest, and timed sector states |
| `sector_display_mode` | `current` | Sector display mode. Use `current`, `personal_best`, or `hybrid` |
| `team_logo_style` | `color` | `color` or `white` for team logos. |
| `color_overall_fastest` | `Card palette` | Optional CSS color for overall-fastest timing cells. |
| `color_personal_fastest` | `Card palette` | Optional CSS color for personal-best timing cells. |
| `color_timed` | `Card palette` | Optional CSS color for normally timed cells. |
| `font_style` | `wide` | `wide`, `balanced` or `system`. See [Typography](/cards/shared-options#typography). |

All bundled cards also support [`f1_entry_id` and card actions](/cards/shared-options). Home Assistant layout settings remain available in the dashboard editor.

## When data is missing

An unavailable message outside Qualifying or Sprint Qualifying is expected. Empty sectors early in a lap are also normal. During an appropriate session, check Driver Positions, Current Session and Session Status before changing display settings.

For an **Entity not found** message, check the selection in **Data Sources** and confirm that the entity is enabled in F1 Sensor. For a missing card type or an old interface after an update, use the [card loading checks](/cards/installation#card-loading-checks).

## Related

- [Practice Timing](/cards/practice-timing)
- [Race Lap](/cards/race-lap)
- [Starting Grid](/cards/starting-grid)
- [All dashboard cards](/cards/cards-overview)
