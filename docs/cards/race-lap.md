---
id: race-lap
title: Race Lap
description: "Follow Race or Sprint order with gaps, tyres, pit counts and lap times."
---

import {Figure} from '@site/src/components/Docs';

Follow Race or Sprint order with gaps, tyres, pit counts and lap times. Switch between the interval to the car ahead and the gap to the leader without leaving the table.

<Figure src="/img/cards/race-lap.png" alt="Race Lap card showing its dashboard layout" caption="Example Race Lap layout. Appearance depends on your session, version and display options." />

## Availability

**Race or Sprint / Replay.** Enable Driver Positions and Current Session. Race Lap Count, Session Status, Driver List and Current Tyres add race context. Pit-stop detail can require optional F1TV Auth during live sessions or archived replay data. Public timing still provides the core race table.

## Add the card

1. Open your dashboard, select **Edit dashboard**, then **Add card**.
2. Search for **F1** and select the Race Lap card.
3. Select Driver Positions under **Data Sources**. Keep the gap toggle visible and start with **Ahead**. Enable sectors only when the card has enough width; choose the pit-stop source if you want pit counts.
4. Select **Save**.

If the card is missing from the picker, follow [Card installation](/cards/installation). With more than one F1 Sensor entry, use the sources from the same entry; see [Entity selection](/cards/shared-options#entity-selection).

### Minimal YAML

Use this in a manual dashboard card. Replace any entity ID with the one in your installation if it differs.

```yaml
type: custom:f1-race-lap-card
positions_entity: sensor.f1_driver_positions
theme_mode: auto
```

## Use the card

The gap toggle changes the reference for the gap column. Optional sectors follow the same lap-aligned behavior as the qualifying and practice cards. A blank pit value can indicate missing enhanced data while the rest of the table remains useful.

## Configuration

### Data sources

The defaults below are the card’s fallback values. Automatic discovery connects standard sources to the selected integration entry, including renamed entity IDs. See [Entity selection](/cards/shared-options#entity-selection).

| Option | Default | Description |
| --- | --- | --- |
| `positions_entity` | `sensor.f1_driver_positions` | Driver Positions for timing and running order. Select the entity from your F1 Sensor entry. |
| `lap_count_entity` | `sensor.f1_race_lap_count` | Race Lap Count for completed and total laps. Select the entity from your F1 Sensor entry. |
| `session_entity` | `sensor.f1_current_session` | Current Session for session type and context. Select the entity from your F1 Sensor entry. |
| `session_status_entity` | `sensor.f1_session_status` | Session Status for active/live/replay context. Select the entity from your F1 Sensor entry. |
| `drivers_entity` | `sensor.f1_driver_list` | Driver List for names, teams and driver detail. Select the entity from your F1 Sensor entry. |
| `tyres_entity` | `sensor.f1_current_tyres` | Current Tyres for compound and stint detail. Select the entity from your F1 Sensor entry. |
| `pitstops_entity` | `sensor.f1_pitstops` | Pit Stops for stop counts and available timings. Select the entity from your F1 Sensor entry. |
| `auth_status_entity` | `sensor.f1_f1tv_token_status` | F1TV token status entity used for enhanced-data notices. |
| `no_spoiler_entity` | `switch.f1_no_spoiler_mode` | Entity whose `on` state enables spoiler protection. See [No Spoiler Mode](/features/no-spoiler-mode). |

### Display and behavior

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | `dark`, `light` or `auto`; `auto` follows Home Assistant. See [Appearance](/cards/shared-options#appearance). |
| `title` | `Race Lap` | Card title |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels |
| `show_position` | `true` | Show current position |
| `show_team_logo` | `true` | Show team logo |
| `show_full_name` | `false` | Show full driver names |
| `show_status` | `true` | Show inline driver status |
| `show_gap` | `true` | Show gap or interval |
| `gap_mode` | `ahead` | `ahead` for the interval to the car ahead, or `leader` for the gap to P1. |
| `show_gap_toggle` | `true` | Show the gap mode toggle |
| `show_tyre` | `true` | Show tyre compound |
| `show_tyre_age` | `true` | Show tyre stint age |
| `show_pit_count` | `true` | Show number of pit stops |
| `show_sectors` | `false` | Show optional S1, S2, and S3 live sector columns |
| `show_last_lap` | `true` | Show last lap time |
| `show_fastest_lap` | `true` | Show personal fastest lap |
| `show_timing_indicators` | `false` | Highlight timing states |
| `team_logo_style` | `color` | `color` or `white` for team logos. |
| `show_availability_notice` | `true` | Show informational enhanced-data notices. Expired, invalid or rejected authentication warnings stay visible. |
| `font_style` | `wide` | `wide`, `balanced` or `system`. See [Typography](/cards/shared-options#typography). |
| `color_overall_fastest` | `Card palette` | Optional CSS color for overall-fastest timing cells. |
| `color_personal_fastest` | `Card palette` | Optional CSS color for personal-best timing cells. |
| `color_timed` | `Card palette` | Optional CSS color for normally timed cells. |

All bundled cards also support [`f1_entry_id` and card actions](/cards/shared-options). Home Assistant layout settings remain available in the dashboard editor.

## When data is missing

This card is intended for Race and Sprint sessions. Outside those sessions, an unavailable state is normal. For missing pit details, read the availability notice and check the F1TV status or replay contents. Authentication warnings remain visible even when informational notices are hidden.

For an **Entity not found** message, check the selection in **Data Sources** and confirm that the entity is enabled in F1 Sensor. For a missing card type or an old interface after an update, use the [card loading checks](/cards/installation#card-loading-checks).

## Related

- [Live Session](/cards/live-session)
- [Pit Stops](/cards/pit-stops)
- [Driver Lap Times](/cards/driver-lap-times)
- [All dashboard cards](/cards/cards-overview)
