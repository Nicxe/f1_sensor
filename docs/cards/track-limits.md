---
id: track-limits
title: Track Limits
description: "Track deleted laps, black-and-white warnings and track-limit penalties by driver."
---

import {Figure} from '@site/src/components/Docs';

Track deleted laps, black-and-white warnings and track-limit penalties by driver. Use the affected-driver view to keep routine timing separate from stewarding information.

<Figure src="/img/cards/track-limits.png" alt="Track Limits card showing its dashboard layout" caption="Example Track Limits layout. Appearance depends on your session, version and display options." />

## Availability

**Public live / Replay.** Enable Track Limits, Driver List and Driver Positions. Updates follow available Race Control information during public live timing or replay.

## Add the card

1. Open your dashboard, select **Edit dashboard**, then **Add card**.
2. Search for **F1** and select the Track Limits card.
3. Select Track Limits under **Data Sources** and confirm the driver sources. Leave **Show all drivers** off to show only drivers with recorded violations.
4. Select **Save**.

If the card is missing from the picker, follow [Card installation](/cards/installation). With more than one F1 Sensor entry, use the sources from the same entry; see [Entity selection](/cards/shared-options#entity-selection).

### Minimal YAML

Use this in a manual dashboard card. Replace any entity ID with the one in your installation if it differs.

```yaml
type: custom:f1-track-limits-card
track_limits_entity: sensor.f1_track_limits
theme_mode: auto
```

## Use the card

A deleted lap, a warning and a penalty are different events. The card presents the information received for each driver; use Race Control and FIA Documents for additional context.

## Configuration

### Data sources

The defaults below are the card’s fallback values. Automatic discovery connects standard sources to the selected integration entry, including renamed entity IDs. See [Entity selection](/cards/shared-options#entity-selection).

| Option | Default | Description |
| --- | --- | --- |
| `track_limits_entity` | `sensor.f1_track_limits` | Track Limits violations and warnings. Select the entity from your F1 Sensor entry. |
| `drivers_entity` | `sensor.f1_driver_list` | Driver List for names, teams and driver detail. Select the entity from your F1 Sensor entry. |
| `positions_entity` | `sensor.f1_driver_positions` | Driver Positions for timing and running order. Select the entity from your F1 Sensor entry. |
| `no_spoiler_entity` | `switch.f1_no_spoiler_mode` | Entity whose `on` state enables spoiler protection. See [No Spoiler Mode](/features/no-spoiler-mode). |

### Display and behavior

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | `dark`, `light` or `auto`; `auto` follows Home Assistant. See [Appearance](/cards/shared-options#appearance). |
| `title` | `Track Limits` | Card title |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels |
| `show_team_logo` | `false` | Show team logo |
| `show_full_name` | `false` | Show full driver names |
| `team_logo_style` | `color` | `color` or `white` for team logos. |
| `show_all_drivers` | `false` | Show all drivers, not only drivers with violations |
| `font_style` | `wide` | `wide`, `balanced` or `system`. See [Typography](/cards/shared-options#typography). |

All bundled cards also support [`f1_entry_id` and card actions](/cards/shared-options). Home Assistant layout settings remain available in the dashboard editor.

## When data is missing

An empty affected-driver list can mean that no track-limit violations have been reported. It does not imply the integration is disconnected. Check the Track Limits entity if messages are present in Race Control but the card remains empty.

For an **Entity not found** message, check the selection in **Data Sources** and confirm that the entity is enabled in F1 Sensor. For a missing card type or an old interface after an update, use the [card loading checks](/cards/installation#card-loading-checks).

## Related

- [Race Control](/cards/race-control)
- [Investigations](/cards/investigations)
- [FIA Documents](/cards/fia-documents)
- [All dashboard cards](/cards/cards-overview)
