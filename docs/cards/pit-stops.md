---
id: pit-stops
title: Pit Stops
description: "Review each driver\u2019s stops, fitted tyres and available pit timing."
---

import {Figure} from '@site/src/components/Docs';

Review each driver’s stops, fitted tyres and available pit timing. Compare stop duration and pit-lane time while keeping the latest tyre information beside the stop history.

<Figure src="/img/cards/pit-stops.png" alt="Pit Stops card showing its dashboard layout" caption="Example Pit Stops layout. Appearance depends on your session, version and display options." />

## Availability

**F1TV live / Replay.** Enable Pit Stops, Current Tyres, Driver Positions and Driver List. Live pit-stop timing uses optional F1TV Auth enhanced data. Replay Mode can show pit details when they are present in the archive; it does not guarantee every timing field.

## Add the card

1. Open your dashboard, select **Edit dashboard**, then **Add card**.
2. Search for **F1** and select the Pit Stops card.
3. Select Pit Stops under **Data Sources** and confirm the driver and tyre sources. Keep stop count and tyre information visible. Enable tyre laps if you want stint age alongside each stop.
4. Select **Save**.

If the card is missing from the picker, follow [Card installation](/cards/installation). With more than one F1 Sensor entry, use the sources from the same entry; see [Entity selection](/cards/shared-options#entity-selection).

### Minimal YAML

Use this in a manual dashboard card. Replace any entity ID with the one in your installation if it differs.

```yaml
type: custom:f1-pitstop-overview-card
pitstops_entity: sensor.f1_pitstops
theme_mode: auto
```

## Use the card

Pit-stop duration and total pit-lane time measure different parts of a stop. Missing values are left unavailable rather than estimated. Delta compares available stop times with the fastest stop.

## Configuration

### Data sources

The defaults below are the card’s fallback values. Automatic discovery connects standard sources to the selected integration entry, including renamed entity IDs. See [Entity selection](/cards/shared-options#entity-selection).

| Option | Default | Description |
| --- | --- | --- |
| `drivers_entity` | `sensor.f1_driver_list` | Driver List for names, teams and driver detail. Select the entity from your F1 Sensor entry. |
| `tyres_entity` | `sensor.f1_current_tyres` | Current Tyres for compound and stint detail. Select the entity from your F1 Sensor entry. |
| `pitstops_entity` | `sensor.f1_pitstops` | Pit Stops for stop counts and available timings. Select the entity from your F1 Sensor entry. |
| `positions_entity` | `sensor.f1_driver_positions` | Driver Positions for timing and running order. Select the entity from your F1 Sensor entry. |
| `auth_status_entity` | `sensor.f1_f1tv_token_status` | F1TV token status entity used for enhanced-data notices. |
| `no_spoiler_entity` | `switch.f1_no_spoiler_mode` | Entity whose `on` state enables spoiler protection. See [No Spoiler Mode](/features/no-spoiler-mode). |

### Display and behavior

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | `dark`, `light` or `auto`; `auto` follows Home Assistant. See [Appearance](/cards/shared-options#appearance). |
| `title` | `Pit Stops & Tyres` | Card title |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels |
| `show_tla` | `true` | Show driver TLA |
| `show_full_name` | `false` | Show full driver names |
| `show_team_logo` | `false` | Show team logo |
| `team_logo_style` | `color` | `color` or `white` for team logos. |
| `show_status` | `true` | Show pit stop status |
| `show_tyre` | `true` | Show tyre compound |
| `show_tyre_laps` | `false` | Show laps completed on the current tyre |
| `show_pit_count` | `true` | Show number of stops |
| `show_pit_time` | `true` | Show pit stop duration |
| `show_pit_lane_time` | `true` | Show total pit lane time |
| `show_pit_delta` | `true` | Show delta to fastest stop |
| `show_availability_notice` | `true` | Show informational enhanced-data notices. Expired, invalid or rejected authentication warnings stay visible. |
| `font_style` | `wide` | `wide`, `balanced` or `system`. See [Typography](/cards/shared-options#typography). |

All bundled cards also support [`f1_entry_id` and card actions](/cards/shared-options). Home Assistant layout settings remain available in the dashboard editor.

## When data is missing

Before the first stop, an empty history is expected. Missing pit timing during a live session can indicate that enhanced data is unavailable. Check the notice and F1TV status; a replay may simply lack that field. Hiding availability notices does not hide authentication errors.

For an **Entity not found** message, check the selection in **Data Sources** and confirm that the entity is enabled in F1 Sensor. For a missing card type or an old interface after an update, use the [card loading checks](/cards/installation#card-loading-checks).

## Related

- [Race Lap](/cards/race-lap)
- [Tyre Statistics](/cards/tyre-statistics)
- [Driver Lap Times](/cards/driver-lap-times)
- [All dashboard cards](/cards/cards-overview)
