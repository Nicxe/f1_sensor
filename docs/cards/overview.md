---
id: cards-overview
title: F1 Sensor dashboard card
description: Build one Formula 1 dashboard card from presets and configurable modules.
---

import {Figure} from '@site/src/components/Docs';

F1 Sensor includes one dashboard card: **F1 Sensor**. Start with a ready-made preset, then add, remove and arrange modules in the visual editor. The same card can cover a race weekend, a live session, results, championship progress, replay and detailed analysis.

<Figure src="/img/cards/f1-sensor-race-weekend.png" alt="F1 Sensor Race weekend card showing the Azerbaijan Grand Prix, circuit, countdown and schedule" caption="The Race weekend preset running in Home Assistant." />

<span id="adding-cards" />
<span id="bundled-installation" />
<span id="installation" />

## Add your first card

1. [Install or update F1 Sensor](/getting-started/installation) and restart Home Assistant.
2. Open a dashboard and select **Edit dashboard > Add card**.
3. Search for **F1 Sensor** and select the card.
4. Choose the F1 Sensor installation if Home Assistant shows more than one.
5. The editor starts empty with **Build your own**. Add a module or select a preset, review the preview and save.

The minimal YAML configuration is:

```yaml
type: custom:f1-sensor-card
```

With one F1 Sensor installation, the card discovers that installation and its entities automatically. Use the visual editor for normal configuration; YAML is available for copying or reviewing advanced setups.

<span id="available-cards" />
<span id="card-reference" />

## Choose which cards to install

In the F1 Sensor integration settings, **Install bundled dashboard cards** controls whether the dashboard cards are registered at all. **Install legacy dashboard cards** additionally enables the deprecated card types and requires the main installation option to be enabled.

New installations leave legacy cards disabled. Existing installations keep them enabled until you choose otherwise. [Migrate existing legacy cards](/cards/modular-migration) before switching them off, then reload the browser. Saved legacy cards cannot render while their card types are disabled. The F1 Sensor card and your entities are unaffected by switching off legacy cards.

These resources are shared by Home Assistant. If you have several F1 Sensor installations, legacy cards remain available while any enabled installation with dashboard cards enabled requests them. Independently installed HACS resources are not removed by this option.

## Choose a starting preset

| Preset | Best for | Initial modules |
| --- | --- | --- |
| **Race weekend** | The next event and its conditions | Overview, schedule and two weather views |
| **Weather comparison** | Current conditions and the race-start forecast | Two weather views |
| **Follow the session** | Practice, qualifying, sprint or race | Overview, timing and Race Control |
| **My driver** | A focused driver view | Overview, driver timing with recent laps and Race Control |
| **Results and championship** | Completed events and season progress | Results, championship and points progression |
| **Build your own** | A completely custom view | No modules |

Presets are starting points, not separate card types. You can change every module after choosing a preset.

## Combine the available modules

The card provides 20 modules in one visual editor.

| Purpose | Modules |
| --- | --- |
| Plan a weekend | Overview, Schedule, Weather |
| Follow a session | Timing, Race Control, Tyres, Pit stops, Incidents |
| Review results | Results, Championship, Historical archive, Season progression |
| Analyse a session | Lap history chart, Session timeline, Strategy analysis, Battles and position changes, Track map |
| Watch later | Replay, Replay telemetry |
| Read official material | FIA documents |

Modules can be reordered, duplicated, temporarily disabled or shown only during selected session phases. Each module has its own fields, filters, data-availability behavior and optional driver or team focus.

<Figure src="/img/cards/f1-sensor-replay-session.png" alt="F1 Sensor session card during an Abu Dhabi Practice 1 replay with overview, timing and Race Control modules" caption="The same card following a recorded session in Replay Mode." />

## Configure the card visually

The editor groups the main choices so you can work from content to presentation:

1. Choose a preset or add modules.
2. Select the fields, filters and presentation for each module.
3. Choose a stacked or tabbed layout and set the shared driver, team and session focus.
4. Adjust the style, density, typography and timing signals.
5. Preview the result before saving.

You can export the complete card configuration or a named reusable template as JSON. Import shows a review before replacing the current editor draft.

## Continue from here

<span id="shared-options" />
<span id="migrating-from-the-old-standalone-card" />
<span id="related" />
<span id="f1-weekend-hub-card" />
<span id="f1-live-session-card" />
<span id="f1-next-race-card" />
<span id="f1-race-weather-card" />
<span id="f1-season-calendar-card" />
<span id="f1-race-control-card" />
<span id="f1-fia-documents-card" />
<span id="f1-qualifying-timing-card" />
<span id="f1-practice-timing-card" />
<span id="f1-race-lap-card" />
<span id="f1-starting-grid-card" />
<span id="f1-results-card" />
<span id="f1-lap-position-progression-card" />
<span id="f1-tyre-statistics-card" />
<span id="f1-pit-stop-overview-card" />
<span id="f1-driver-lap-times-card" />
<span id="f1-investigations-card" />
<span id="f1-track-limits-card" />
<span id="f1-championship-prediction-drivers-card" />
<span id="f1-championship-prediction-teams-card" />
<span id="f1-season-progression-card" />
<span id="f1-replay-control-card" />
<span id="f1-track-map-card" />

- [Build and configure the card](/cards/modular)
- [Understand shared configuration](/cards/shared-options)
- [Move from a deprecated card](/cards/modular-migration)
- [Improve readability and keyboard access](/cards/modular-accessibility)
- [Fix card loading problems](/cards/installation#card-loading-checks)
