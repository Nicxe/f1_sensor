---
id: starting-grid
title: Starting Grid
description: "See the provisional or confirmed starting order before a Race or Sprint."
---

import {Figure} from '@site/src/components/Docs';

See the provisional or confirmed starting order before a Race or Sprint. Compare qualifying positions with the final grid to spot changes and penalties.

<Figure src="/img/cards/starting-grid.png" alt="Starting Grid card showing its dashboard layout" caption="Example Starting Grid layout. Appearance depends on your session, version and display options." />

## Availability

**Published grid.** Enable Starting Grid. On Sprint weekends, Sprint Qualifying supplies the Sprint grid and Qualifying supplies the Race grid. The card uses the grid currently relevant to the weekend and does not require F1TV Auth.

## Add the card

1. Open your dashboard, select **Edit dashboard**, then **Add card**.
2. Search for **F1** and select the Starting Grid card.
3. Select Starting Grid under **Data Sources**. Choose **Grid** for a visual lineup or **Table** for a compact comparison. Keep status and source badges visible so you can distinguish provisional information from a confirmed grid.
4. Select **Save**.

If the card is missing from the picker, follow [Card installation](/cards/installation). With more than one F1 Sensor entry, use the sources from the same entry; see [Entity selection](/cards/shared-options#entity-selection).

### Minimal YAML

Use this in a manual dashboard card. Replace any entity ID with the one in your installation if it differs.

```yaml
type: custom:f1-starting-grid-card
entity: sensor.f1_starting_grid
theme_mode: auto
```

## Use the card

Qualifying position and grid position are different values. The movement column shows the change between them. A provisional grid can change when official decisions are published.

## Configuration

### Data sources

The defaults below are the card’s fallback values. Automatic discovery connects standard sources to the selected integration entry, including renamed entity IDs. See [Entity selection](/cards/shared-options#entity-selection).

| Option | Default | Description |
| --- | --- | --- |
| `entity` | `sensor.f1_starting_grid` | Primary data source for this card. Select the matching entity from your F1 Sensor entry. |
| `no_spoiler_entity` | `switch.f1_no_spoiler_mode` | Entity whose `on` state enables spoiler protection. See [No Spoiler Mode](/features/no-spoiler-mode). |

### Display and behavior

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | `dark`, `light` or `auto`; `auto` follows Home Assistant. See [Appearance](/cards/shared-options#appearance). |
| `title` | `Starting Grid` | Card title |
| `display_mode` | `grid` | Use `grid` or `table` layout |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels in table mode |
| `show_team_logo` | `true` | Show team logo |
| `show_full_name` | `false` | Show full driver names |
| `show_qualifying_position` | `true` | Show original qualifying position |
| `show_qualifying_time` | `true` | Show qualifying lap time |
| `show_qualifying_delta` | `false` | Show delta to the reference qualifying time |
| `show_qualifying_segment` | `true` | Show Q/SQ segment |
| `show_grid_delta` | `true` | Show movement from qualifying position to grid position |
| `show_status_badge` | `true` | Show provisional/confirmed status |
| `show_source_badge` | `true` | Show data source badge |
| `show_metadata` | `true` | Show source session and target session metadata |
| `team_logo_style` | `color` | `color` or `white` for team logos. |
| `font_style` | `wide` | `wide`, `balanced` or `system`. See [Typography](/cards/shared-options#typography). |

All bundled cards also support [`f1_entry_id` and card actions](/cards/shared-options). Home Assistant layout settings remain available in the dashboard editor.

## When data is missing

The grid may not be available before qualifying data has been published. Do not treat provisional positions as a final starting order. If the card shows a previous context, inspect the source session and target session metadata before assuming a display error.

For an **Entity not found** message, check the selection in **Data Sources** and confirm that the entity is enabled in F1 Sensor. For a missing card type or an old interface after an update, use the [card loading checks](/cards/installation#card-loading-checks).

## Related

- [Qualifying Timing](/cards/qualifying-timing)
- [FIA Documents](/cards/fia-documents)
- [Results](/cards/results)
- [All dashboard cards](/cards/cards-overview)
