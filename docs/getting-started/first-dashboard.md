---
id: first-dashboard
title: Your first dashboard
description: Add the F1 Sensor card and verify your setup between Formula 1 sessions.
---

import {Figure} from '@site/src/components/Docs';

Start with the **Race weekend** preset. It shows the next Grand Prix, circuit, countdown, weekend schedule and available weather, so you can confirm the dashboard before a live session begins.

## Before you start

[Install and configure F1 Sensor](/getting-started/installation). The card is bundled with the integration and does not need a separate Marketplace or HACS dashboard download.

## Add your first card

1. Open a Home Assistant dashboard you can edit.
2. Select **Edit dashboard > Add card**.
3. Search for **F1 Sensor** and select the card.
4. Choose the **Race weekend** preset.
5. Select the intended F1 Sensor installation if Home Assistant shows more than one.
6. Review the preview, save the card and finish editing the dashboard.

You should see the next Grand Prix, circuit, countdown and available weekend times. Weather appears when its supporting data is available.

<Figure src="/img/getting-started/card-template-picker.png" alt="F1 Sensor template chooser in Home Assistant, with Race weekend and five other starting templates" caption="The template chooser in HAdev. Select Race weekend for your first dashboard." />

<details>
<summary>See an example of the working preview</summary>

<Figure src="/img/getting-started/race-weekend-preview.png" alt="Excerpt of the Race weekend preview set to Actual data, showing the Grand Prix, circuit and countdown" caption="Actual data in an unsaved HAdev card preview, captured on 3 November 2026. This excerpt shows the overview and the start of the schedule; dates and countdown are examples from that day." />

</details>

### YAML alternative

In a Manual card, paste:

```yaml
type: custom:f1-sensor-card
```

When you paste this minimal YAML, it uses the Race weekend modules by default. Adding a new card through the visual picker instead opens the empty **Build your own** template; choose **Race weekend** there. Continue in the editor to select another preset, add modules or adjust appearance.

The modular card gets its data automatically. You do not need to enable matching Next race, weather or timing sensors just for its modules; keep those entities when other cards, templates or automations use them.

## Add live timing

Edit the same card and choose the **Follow the session** preset, or add the Overview, Timing and Race Control modules yourself. Enable **Enable live F1 API** in the integration first. Extra live feeds can also require connected account access.

A card waiting for a session is different from a card with a missing source. Live timing is available around active practice, qualifying, sprint and race sessions. Check [data availability](/features/f1tv-auth#availability-matrix) before expecting live cars, pit stops, telemetry or radio clips.

## If the card does not appear

Restart Home Assistant after installing or updating, then reload the browser. If you previously used the standalone resource or a deprecated card type, follow [card installation](/cards/installation) and [card migration](/cards/modular-migration). If the card opens but a module is empty, use [troubleshooting](/help/overview).

## Make it yours

- [Explore the F1 Sensor card](/cards/cards-overview)
- [Build a custom module layout](/cards/modular)
- [Match timing to your TV](/features/live-delay)
- [Make your lights respond to track flags](/blueprints/track-status-light)
