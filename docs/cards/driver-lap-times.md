---
id: driver-lap-times
title: Driver Lap Times
description: "Follow positions, gaps, last laps and personal bests in a detailed timing table."
---

import {Figure} from '@site/src/components/Docs';

Follow positions, gaps, last laps and personal bests in a detailed timing table. Add lap-history columns when you want to compare a driver’s recent pace.

<Figure src="/img/cards/driver-lap-times.png" alt="Driver Lap Times card showing its dashboard layout" caption="Example Driver Lap Times layout. Appearance depends on your session, version and display options." />

## Availability

**Public live / Replay.** Enable Driver Positions and Driver List. Core timing uses public live data or archived replay timing. Lap-history columns depend on the laps available in the current session data.

## Add the card

1. Open your dashboard, select **Edit dashboard**, then **Add card**.
2. Search for **F1** and select the Driver Lap Times card.
3. Select Driver Positions under **Data Sources** and confirm Driver List. Start with lap history off for a compact live table. If you enable history, set a small recent-lap limit on narrow dashboards.
4. Select **Save**.

If the card is missing from the picker, follow [Card installation](/cards/installation). With more than one F1 Sensor entry, use the sources from the same entry; see [Entity selection](/cards/shared-options#entity-selection).

### Minimal YAML

Use this in a manual dashboard card. Replace any entity ID with the one in your installation if it differs.

```yaml
type: custom:f1-driver-lap-times-card
positions_entity: sensor.f1_driver_positions
theme_mode: auto
```

## Use the card

Switch the gap reference between the car ahead and the leader using the visible toggle. Lap trends show whether times became faster or slower. Supported Weekend Hub context selections can also change the focus driver and gap reference.

## Configuration

### Data sources

The defaults below are the card’s fallback values. Automatic discovery connects standard sources to the selected integration entry, including renamed entity IDs. See [Entity selection](/cards/shared-options#entity-selection).

| Option | Default | Description |
| --- | --- | --- |
| `drivers_entity` | `sensor.f1_driver_list` | Driver List for names, teams and driver detail. Select the entity from your F1 Sensor entry. |
| `positions_entity` | `sensor.f1_driver_positions` | Driver Positions for timing and running order. Select the entity from your F1 Sensor entry. |
| `no_spoiler_entity` | `switch.f1_no_spoiler_mode` | Entity whose `on` state enables spoiler protection. See [No Spoiler Mode](/features/no-spoiler-mode). |

### Display and behavior

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | `dark`, `light` or `auto`; `auto` follows Home Assistant. See [Appearance](/cards/shared-options#appearance). |
| `title` | `Driver Lap Times` | Card title |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels |
| `show_position` | `true` | Show current position |
| `show_team_logo` | `true` | Show team logo |
| `show_tla` | `true` | Show driver TLA |
| `show_full_name` | `false` | Show full driver names |
| `show_status` | `true` | Show driver status |
| `show_gap` | `true` | Show gap or interval |
| `gap_mode` | `ahead` | `ahead` for the interval to the car ahead, or `leader` for the gap to P1. |
| `show_gap_toggle` | `true` | Show the gap mode toggle |
| `show_last_lap` | `true` | Show last lap time |
| `show_best_lap` | `true` | Show personal best lap time |
| `show_lap_history` | `false` | Show lap-by-lap history columns |
| `lap_history_limit` | `0` | Number of recent lap columns. `0` shows all laps. |
| `show_lap_trend` | `true` | Show faster/slower trend indicators |
| `team_logo_style` | `color` | `color` or `white` for team logos. |
| `font_style` | `wide` | `wide`, `balanced` or `system`. See [Typography](/cards/shared-options#typography). |

All bundled cards also support [`f1_entry_id` and card actions](/cards/shared-options). Home Assistant layout settings remain available in the dashboard editor.

## When data is missing

No lap history before timed laps arrive is normal. A driver can have a position without a valid completed lap. For an empty table during a session, verify both source entities are enabled and contain drivers.

For an **Entity not found** message, check the selection in **Data Sources** and confirm that the entity is enabled in F1 Sensor. For a missing card type or an old interface after an update, use the [card loading checks](/cards/installation#card-loading-checks).

## Related

- [Weekend Hub](/cards/weekend-hub)
- [Race Lap](/cards/race-lap)
- [Tyre Statistics](/cards/tyre-statistics)
- [All dashboard cards](/cards/cards-overview)
