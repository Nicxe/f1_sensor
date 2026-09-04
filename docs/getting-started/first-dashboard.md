---
id: first-dashboard
title: Your first dashboard
description: Add a Next Race card in Home Assistant and verify your setup even between Formula 1 sessions.
---

Start with **F1 Next Race**. It shows the upcoming race and weekend schedule, so you can check your dashboard before a live session begins.

## Before you start

[Install and configure F1 Sensor](/getting-started/installation). Include the Next race sensor in your enabled features. The cards are bundled with the integration; they do not need a separate HACS dashboard download.

## Add your first card

1. Open a Home Assistant dashboard you can edit.
2. Select **Edit dashboard → Add card**.
3. Search for **F1** and choose **F1 Next Race**.
4. Select your Next race entity in **Data Sources**. New installations normally use `sensor.f1_next_race`.
5. Save the card, then finish editing the dashboard.

You should see the next race, circuit and available weekend times. Weather appears when its supporting data is available.

### YAML alternative

In a Manual card, paste:

```yaml
type: custom:f1-next-race-card
next_race_entity: sensor.f1_next_race
theme_mode: auto
```

If your existing entity has a different ID, select it in the visual editor or replace the example ID. Updating F1 Sensor does not rename your existing entities.

## Add live timing when a session is running

Choose **F1 Live Session** or a timing card from the [card gallery](/cards/cards-overview). Enable the card's required live features in the integration first.

A card waiting for a session is different from a card with a missing entity. Live timing is available around active practice, qualifying, sprint and race sessions. Check [data availability](/features/f1tv-auth#availability-matrix) before expecting live cars, pit stops or radio clips.

## If the card does not appear

Restart Home Assistant after installing or updating, then reload your browser. If you previously used the standalone card repository, follow the [card migration guide](/cards/installation). If the card is present but empty, use [troubleshooting](/help/overview).

## Make it yours

- [Explore all dashboard cards](/cards/cards-overview).
- [Match timing to your TV](/features/live-delay).
- [Make your lights respond to track flags](/blueprints/track-status-light).
