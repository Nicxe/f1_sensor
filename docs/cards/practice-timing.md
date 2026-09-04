---
id: practice-timing
title: Practice Timing
description: "Compare practice laps with driver order, tyre age, last lap and personal best."
---

import {Figure} from '@site/src/components/Docs';

Compare practice laps with driver order, tyre age, last lap and personal best. Optional sector columns help you follow a run in more detail.

<Figure src="/img/cards/practice-timing.png" alt="Practice Timing card showing its dashboard layout" caption="Example Practice Timing layout. Appearance depends on your session, version and display options." />

## Availability

**Practice / Replay.** Enable Driver Positions and Current Session for a practice session. Driver List, Current Tyres and Session Status provide the remaining context. Public timing and practice replays can supply these values; fields depend on the available session feed.

## Add the card

1. Open your dashboard, select **Edit dashboard**, then **Add card**.
2. Search for **F1** and select the Practice Timing card.
3. Select Driver Positions under **Data Sources**. Keep sectors off for a compact table, or enable them on a wider dashboard. Timing indicators can highlight overall fastest and personal-best values.
4. Select **Save**.

If the card is missing from the picker, follow [Card installation](/cards/installation). With more than one F1 Sensor entry, use the sources from the same entry; see [Entity selection](/cards/shared-options#entity-selection).

### Minimal YAML

Use this in a manual dashboard card. Replace any entity ID with the one in your installation if it differs.

```yaml
type: custom:f1-practice-timing-card
positions_entity: sensor.f1_driver_positions
theme_mode: auto
```

## Use the card

The optional S1–S3 columns preserve completed-lap sectors until the next S1 arrives, matching the Qualifying and Race Lap cards. Tyre age and lap time may update at different points in a run.

## Configuration

### Data sources

The defaults below are the card’s fallback values. Automatic discovery connects standard sources to the selected integration entry, including renamed entity IDs. See [Entity selection](/cards/shared-options#entity-selection).

| Option | Default | Description |
| --- | --- | --- |
| `positions_entity` | `sensor.f1_driver_positions` | Driver Positions for timing and running order. Select the entity from your F1 Sensor entry. |
| `session_entity` | `sensor.f1_current_session` | Current Session for session type and context. Select the entity from your F1 Sensor entry. |
| `session_status_entity` | `sensor.f1_session_status` | Session Status for active/live/replay context. Select the entity from your F1 Sensor entry. |
| `drivers_entity` | `sensor.f1_driver_list` | Driver List for names, teams and driver detail. Select the entity from your F1 Sensor entry. |
| `tyres_entity` | `sensor.f1_current_tyres` | Current Tyres for compound and stint detail. Select the entity from your F1 Sensor entry. |
| `no_spoiler_entity` | `switch.f1_no_spoiler_mode` | Entity whose `on` state enables spoiler protection. See [No Spoiler Mode](/features/no-spoiler-mode). |

### Display and behavior

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | `dark`, `light` or `auto`; `auto` follows Home Assistant. See [Appearance](/cards/shared-options#appearance). |
| `title` | `Free Practice` | Card title |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels |
| `show_position` | `true` | Show current position |
| `show_team_logo` | `true` | Show team logo |
| `show_full_name` | `false` | Show full driver names |
| `show_status` | `true` | Show driver status |
| `show_tyre` | `true` | Show tyre compound |
| `show_tyre_age` | `true` | Show tyre stint age |
| `show_sectors` | `false` | Show optional S1, S2, and S3 live sector columns |
| `show_last_lap` | `true` | Show last lap |
| `show_fastest_lap` | `true` | Show personal fastest lap |
| `show_timing_indicators` | `false` | Highlight timing states |
| `team_logo_style` | `color` | `color` or `white` for team logos. |
| `font_style` | `wide` | `wide`, `balanced` or `system`. See [Typography](/cards/shared-options#typography). |
| `color_overall_fastest` | `Card palette` | Optional CSS color for overall-fastest timing cells. |
| `color_personal_fastest` | `Card palette` | Optional CSS color for personal-best timing cells. |
| `color_timed` | `Card palette` | Optional CSS color for normally timed cells. |

All bundled cards also support [`f1_entry_id` and card actions](/cards/shared-options). Home Assistant layout settings remain available in the dashboard editor.

## When data is missing

Wait for drivers to complete timed laps before expecting best-lap values. A practice-only view may be unavailable in another session type. Check the session and tyre sources if lap timing appears but optional columns do not.

For an **Entity not found** message, check the selection in **Data Sources** and confirm that the entity is enabled in F1 Sensor. For a missing card type or an old interface after an update, use the [card loading checks](/cards/installation#card-loading-checks).

## Related

- [Qualifying Timing](/cards/qualifying-timing)
- [Race Lap](/cards/race-lap)
- [Tyre Statistics](/cards/tyre-statistics)
- [All dashboard cards](/cards/cards-overview)
