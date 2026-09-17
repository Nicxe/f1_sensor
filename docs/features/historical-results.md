---
id: historical-results
title: Browse historical results
description: Use the Historical archive module to review past classifications and lap charts without starting Replay Mode.
---

Add the **Historical archive** module to the [F1 Sensor card](/cards/cards-overview) to browse published classifications, lap times and lap-position history from previous seasons. Archive requests are separate from Replay Mode.

## Before you start

Update F1 Sensor and reload the dashboard. You need a working F1 Sensor installation and access to the historical results provider. F1TV Auth and an active live session are not required.

## Add the archive module

1. Edit an **F1 Sensor** card or add a new one with **Build your own**.
2. Select **Add module > Historical archive**.
3. Under **Module options**, choose the year and archive view.
4. Save the card.
5. In the saved card, choose a Grand Prix and an available session.

| Archive view | What it shows |
| --- | --- |
| **Classification** | Race, Sprint or qualifying results where published |
| **Lap time** | Recorded lap-time history for selected drivers |
| **Lap position** | Recorded position by lap for selected drivers |

Race and Sprint classifications can include grid, laps, finish status and points. Qualifying can include position and Q1-Q3 times. Some sessions or older seasons have incomplete information; an empty field does not mean that the value was zero.

Archive data is requested on demand. Choosing an event does not load every season in the background or start a replay.

## Open the archive first

Use the visual editor for normal setup. This YAML creates a card containing only the Historical archive module and starts with 2024 selected:

```yaml
type: custom:f1-sensor-card
version: 2
title: Historical results
modules:
  - type: archive
    id: archive-1
    options:
      year: 2024
      content: classification
      show_session_selector: true
```

With several F1 Sensor installations, select the intended installation in the editor. An integration entry ID is different from a sensor entity ID.

## Archive or Replay?

| Choose | What happens |
| --- | --- |
| **Historical archive** | Retrieves a published classification or lap series. Other modules keep their configured source. |
| **Replay > Load** | Loads archived timing for playback through supported F1 entities, modules and automations. |
| **Replay telemetry** | Compares selected laps from the replay already loaded in the integration. |

To analyse the timing of an archived session, load that session in [Replay Mode](/features/replay-mode) and use the [analysis modules](/features/weekend-analysis). Merely selecting it in Historical archive does not start playback.

## When data is missing

- **No events or sessions:** check the year and try another published session. Historical availability varies by season and session type.
- **An error with Try again:** retry after checking connectivity. Reinstalling the card cannot make an unavailable provider respond.
- **Classification without lap history:** classifications, lap progression and telemetry have separate coverage.
- **Hidden results:** check [No Spoiler Mode](/features/no-spoiler-mode) and reveal the data only when you are ready.
- **Module unavailable:** confirm that the correct F1 Sensor installation is selected and use the [card loading checks](/cards/installation#card-loading-checks).

If you still use a deprecated Results, Session Archive or Lap Position Progression card, follow [Move to the F1 Sensor card](/cards/modular-migration).
