---
id: race-control
title: Race Control
description: "Follow Race Control messages and flags as they arrive."
---

import {Figure} from '@site/src/components/Docs';

Follow Race Control messages and flags as they arrive. Choose a single latest-message banner for a compact dashboard or a scrollable feed to review earlier messages.

<Figure src="/img/cards/race-control.png" alt="Race Control card showing its dashboard layout" caption="Example Race Control layout. Appearance depends on your session, version and display options." />

## Availability

**Public live / Replay.** Enable Race Control. Messages use public live timing and are also available in Replay Mode when included in the session archive. F1TV Auth is not required.

## Add the card

1. Open your dashboard, select **Edit dashboard**, then **Add card**.
2. Search for **F1** and select the Race Control card.
3. Select Race Control under **Data Sources**. Choose **Latest** for a banner or **List** for a message feed. Leave filters off initially so you can see which messages the source supplies.
4. Select **Save**.

If the card is missing from the picker, follow [Card installation](/cards/installation). With more than one F1 Sensor entry, use the sources from the same entry; see [Entity selection](/cards/shared-options#entity-selection).

### Minimal YAML

Use this in a manual dashboard card. Replace any entity ID with the one in your installation if it differs.

```yaml
type: custom:f1-race-control-card
entity: sensor.f1_race_control
theme_mode: auto
```

## Use the card

Blue-flag and track-limit filters change the messages visible in this card; they do not remove stored history or change your notification automations. A minimum display time can keep a banner readable when several messages arrive close together.

## Configuration

### Data sources

The defaults below are the card’s fallback values. Automatic discovery connects standard sources to the selected integration entry, including renamed entity IDs. See [Entity selection](/cards/shared-options#entity-selection).

| Option | Default | Description |
| --- | --- | --- |
| `entity` | `sensor.f1_race_control` | Primary data source for this card. Select the matching entity from your F1 Sensor entry. |
| `no_spoiler_entity` | `switch.f1_no_spoiler_mode` | Entity whose `on` state enables spoiler protection. See [No Spoiler Mode](/features/no-spoiler-mode). |

### Display and behavior

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | `dark`, `light` or `auto`; `auto` follows Home Assistant. See [Appearance](/cards/shared-options#appearance). |
| `display_mode` | `latest` | Use `latest` for a compact card or `list` for a feed view |
| `show_fia_logo` | `true` | Show the FIA logo in the header |
| `hide_blue_flags` | `false` | Hide blue flag messages |
| `hide_track_limits` | `false` | Hide track limits messages from the banner or list without deleting saved history |
| `min_display_time` | `0` | Minimum time in milliseconds before rotating to a newer message |
| `list_max_height` | `600` | List height in pixels, clamped to 240–2000; used in list mode. |
| `show_clear_button` | `true` | Show the clear button in list mode |
| `font_style` | `wide` | `wide`, `balanced` or `system`. See [Typography](/cards/shared-options#typography). |

All bundled cards also support [`f1_entry_id` and card actions](/cards/shared-options). Home Assistant layout settings remain available in the dashboard editor.

## When data is missing

No messages before the first Race Control update is normal. If messages seem missing, check the two filters and the display mode first. For a completely empty card during a session, confirm that the Race Control entity has data.

For an **Entity not found** message, check the selection in **Data Sources** and confirm that the entity is enabled in F1 Sensor. For a missing card type or an old interface after an update, use the [card loading checks](/cards/installation#card-loading-checks).

## Related

- [Investigations](/cards/investigations)
- [Track Limits](/cards/track-limits)
- [FIA Documents](/cards/fia-documents)
- [All dashboard cards](/cards/cards-overview)
