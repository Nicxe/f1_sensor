---
id: investigations
title: Investigations
description: "Keep steward investigations and penalties in a focused list."
---

import {Figure} from '@site/src/components/Docs';

Keep steward investigations and penalties in a focused list. Show only affected drivers for a compact view, or include the whole field for context.

<Figure src="/img/cards/investigations.png" alt="Investigations card showing its dashboard layout" caption="Example Investigations layout. Appearance depends on your session, version and display options." />

## Availability

**Public live / Replay.** Enable Investigations, Driver List and Driver Positions. The card follows Race Control-derived information from public live timing or a replay. It does not replace published FIA decisions.

## Add the card

1. Open your dashboard, select **Edit dashboard**, then **Add card**.
2. Search for **F1** and select the Investigations card.
3. Select Investigations under **Data Sources** and confirm Driver List and Driver Positions. Leave **Show all drivers** off to keep attention on active cases.
4. Select **Save**.

If the card is missing from the picker, follow [Card installation](/cards/installation). With more than one F1 Sensor entry, use the sources from the same entry; see [Entity selection](/cards/shared-options#entity-selection).

### Minimal YAML

Use this in a manual dashboard card. Replace any entity ID with the one in your installation if it differs.

```yaml
type: custom:f1-investigations-card
investigations_entity: sensor.f1_investigations
theme_mode: auto
```

## Use the card

Read the investigation or penalty status alongside Race Control messages. For the published decision itself, open FIA Documents.

## Configuration

### Data sources

The defaults below are the card’s fallback values. Automatic discovery connects standard sources to the selected integration entry, including renamed entity IDs. See [Entity selection](/cards/shared-options#entity-selection).

| Option | Default | Description |
| --- | --- | --- |
| `investigations_entity` | `sensor.f1_investigations` | Investigations and penalty information. Select the entity from your F1 Sensor entry. |
| `drivers_entity` | `sensor.f1_driver_list` | Driver List for names, teams and driver detail. Select the entity from your F1 Sensor entry. |
| `positions_entity` | `sensor.f1_driver_positions` | Driver Positions for timing and running order. Select the entity from your F1 Sensor entry. |
| `no_spoiler_entity` | `switch.f1_no_spoiler_mode` | Entity whose `on` state enables spoiler protection. See [No Spoiler Mode](/features/no-spoiler-mode). |

### Display and behavior

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | `dark`, `light` or `auto`; `auto` follows Home Assistant. See [Appearance](/cards/shared-options#appearance). |
| `title` | `Investigations & Penalties` | Card title |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels |
| `show_team_logo` | `false` | Show team logo |
| `show_full_name` | `false` | Show full driver names |
| `team_logo_style` | `color` | `color` or `white` for team logos. |
| `show_all_drivers` | `false` | Show all drivers, not only affected drivers |
| `font_style` | `wide` | `wide`, `balanced` or `system`. See [Typography](/cards/shared-options#typography). |

All bundled cards also support [`f1_entry_id` and card actions](/cards/shared-options). Home Assistant layout settings remain available in the dashboard editor.

## When data is missing

No affected drivers is a normal state when there are no investigations or penalties to show. Turn on **Show all drivers** only if you prefer a full field view. If you know a case exists, check whether it has reached the Investigations entity.

For an **Entity not found** message, check the selection in **Data Sources** and confirm that the entity is enabled in F1 Sensor. For a missing card type or an old interface after an update, use the [card loading checks](/cards/installation#card-loading-checks).

## Related

- [Race Control](/cards/race-control)
- [FIA Documents](/cards/fia-documents)
- [Track Limits](/cards/track-limits)
- [All dashboard cards](/cards/cards-overview)
