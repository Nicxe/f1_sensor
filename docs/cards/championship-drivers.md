---
id: championship-drivers
title: Driver Championship
description: "Compare current driver championship points with the prediction supplied during a session."
---

import {Figure} from '@site/src/components/Docs';

Compare current driver championship points with the prediction supplied during a session. Keep the standings useful between races while clearly separating predicted points from published results.

<Figure src="/img/cards/championship-drivers.png" alt="Driver Championship card showing its dashboard layout" caption="Example Driver Championship layout. Appearance depends on your session, version and display options." />

## Availability

**Standings / F1TV prediction.** Enable Driver Standings for current points and Championship Prediction Drivers for predictions. Driver List adds names and images; Current Session and Session Status add mode context. Live prediction can require F1TV Auth; a replay needs archived prediction data. Current published standings do not require authentication.

## Add the card

1. Open your dashboard, select **Edit dashboard**, then **Add card**.
2. Search for **F1** and select the Driver Championship card.
3. Select Driver Standings as the current standings source, then the prediction source under **Data Sources**. Keep the mode badge visible so current, live and replay context stays clear.
4. Select **Save**.

If the card is missing from the picker, follow [Card installation](/cards/installation). With more than one F1 Sensor entry, use the sources from the same entry; see [Entity selection](/cards/shared-options#entity-selection).

### Minimal YAML

Use this in a manual dashboard card. Replace any entity ID with the one in your installation if it differs.

```yaml
type: custom:f1-championship-prediction-drivers-card
current_entity: sensor.f1_driver_standings
theme_mode: auto
```

## Use the card

Predicted points are provisional. They are not a final championship classification and can change as the race develops. Use the top-driver limit to create a compact championship panel.

## Configuration

### Data sources

The defaults below are the card’s fallback values. Automatic discovery connects standard sources to the selected integration entry, including renamed entity IDs. See [Entity selection](/cards/shared-options#entity-selection).

| Option | Default | Description |
| --- | --- | --- |
| `current_entity` | `sensor.f1_driver_standings` | Current published championship standings. Select the entity from your F1 Sensor entry. |
| `entity` | `sensor.f1_championship_prediction_drivers` | Primary data source for this card. Select the matching entity from your F1 Sensor entry. |
| `drivers_entity` | `sensor.f1_driver_list` | Driver List for names, teams and driver detail. Select the entity from your F1 Sensor entry. |
| `session_entity` | `sensor.f1_current_session` | Current Session for session type and context. Select the entity from your F1 Sensor entry. |
| `session_status_entity` | `sensor.f1_session_status` | Session Status for active/live/replay context. Select the entity from your F1 Sensor entry. |
| `no_spoiler_entity` | `switch.f1_no_spoiler_mode` | Entity whose `on` state enables spoiler protection. See [No Spoiler Mode](/features/no-spoiler-mode). |
| `auth_status_entity` | `sensor.f1_f1tv_token_status` | F1TV token status entity used for enhanced-data notices. |

### Display and behavior

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | `dark`, `light` or `auto`; `auto` follows Home Assistant. See [Appearance](/cards/shared-options#appearance). |
| `title` | `Driver Championship` | Card title |
| `show_header` | `true` | Show the card header |
| `show_mode_badge` | `true` | Show live/replay/no-spoiler mode badge |
| `show_table_header` | `true` | Show column labels |
| `show_position` | `true` | Show championship position |
| `show_tla` | `true` | Show driver TLA |
| `show_full_name` | `false` | Show full driver names |
| `show_team_logo` | `true` | Show team logo |
| `driver_image_type` | `team_logo` | `team_logo` or `headshot`. Chooses the image displayed beside the driver. |
| `team_logo_style` | `color` | `color` or `white` for team logos. |
| `show_predicted_points` | `true` | Show predicted final points |
| `show_current_points` | `true` | Show current points |
| `show_delta` | `true` | Show predicted points delta |
| `show_availability_notice` | `true` | Show informational enhanced-data notices. Expired, invalid or rejected authentication warnings stay visible. |
| `top_limit` | `0` | Limit rows to top N. `0` shows all. |
| `spoiler_placeholder` | `HIDE` | Text used for masked values, converted to uppercase. The spoiler overlay can also cover the card. |
| `font_style` | `wide` | `wide`, `balanced` or `system`. See [Typography](/cards/shared-options#typography). |

All bundled cards also support [`f1_entry_id` and card actions](/cards/shared-options). Home Assistant layout settings remain available in the dashboard editor.

## When data is missing

No prediction between sessions is normal; current standings can still be available. For missing live prediction, check the availability notice and F1TV status. No Spoiler protection intentionally masks sensitive values until you turn it off.

For an **Entity not found** message, check the selection in **Data Sources** and confirm that the entity is enabled in F1 Sensor. For a missing card type or an old interface after an update, use the [card loading checks](/cards/installation#card-loading-checks).

## Related

- [Constructor Championship](/cards/championship-teams)
- [Season Progression](/cards/season-progression)
- [Results](/cards/results)
- [All dashboard cards](/cards/cards-overview)
