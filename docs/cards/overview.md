---
id: cards-overview
title: F1 Sensor dashboard card
description: Build one Formula 1 dashboard card from presets and configurable modules.
---

import {CardGallery, Figure, NativeDetails} from '@site/src/components/Docs';
import {cardsCatalog} from '@site/src/data/cardsCatalog';

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

With one F1 Sensor installation, the card discovers it and requests data for its modules automatically. Matching sensor entities are optional; keep them for automations, templates, standard cards and older F1 cards. Use the visual editor for normal configuration; YAML is available for copying or reviewing advanced setups.

## Find a module

Search by name or choose a topic. Open a result for configuration and source requirements.

<CardGallery cards={cardsCatalog} compact itemLabel="module" regionLabel="Dashboard module catalogue" searchLabel="Find a module" />

Module guides explain required sources and normal waiting states. Adding a module does not unlock live feeds or create missing data.

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

The card combines the following modules in one visual editor. [Choose a focused module guide](/cards/modular#choose-the-information-you-want) for setup and interpretation.

| Purpose | Modules |
| --- | --- |
| Plan a weekend | Overview, Schedule, Weather |
| Follow a session | [Timing](/cards/timing), [Minisectors](/cards/minisectors), Race Control, [Team Radio (experimental)](/cards/team-radio), Tyres, [Pit stops](/cards/pit-stops), Incidents |
| Review results | Results, Championship, Historical archive, Season progression |
| Analyse a session | Lap history chart, Session timeline, Strategy analysis, Battles and position changes, Track map |
| Watch later | Replay, Replay telemetry |
| Read official material | FIA documents |

Modules can be reordered, duplicated, temporarily disabled or shown only during selected session phases. Each module has its own fields, filters, data-availability behavior and optional driver or team focus.

Minisectors provide source status blocks for S1, S2 and S3. You can also add the
same optional blocks below the existing sector times in Timing. The source does not
provide a time for each minisector. See [Show minisectors](/cards/modular#show-minisectors).

<Figure src="/img/cards/f1-sensor-replay-session.png" alt="F1 Sensor session card during an Abu Dhabi Practice 1 replay with overview, timing and Race Control modules" caption="The same card following a recorded session in Replay Mode." />

## Configure the card visually

The editor groups the main choices so you can work from content to presentation:

1. Choose a preset or add modules.
2. Select the fields, filters and presentation for each module.
3. Choose a [stacked, tabbed or column layout](/cards/layout) and set the shared driver, team and session focus.
4. Adjust the style, density, typography and timing signals.
5. Preview the result before saving.

You can export the complete card configuration or a named reusable template as JSON. Import shows a review before replacing the current editor draft.

## Module options and data notes

The focused guides in the finder cover Timing, Minisectors, Team Radio, Pit stops, archive, replay and analysis. Open these notes for the remaining modules.

<NativeDetails summary="Read options for planning, results and other modules">

### Overview module {/* #overview-module */}

Add **Overview** and start with the meeting, circuit and countdown fields. Optional session status, track status, lap progress and session clocks use the data available for the card's selected installation and session.

Use [Next Race](/entities/next-race) for schedule fields, [Current Session](/entities/current-session) for the session label and the [clock comparison](/reference/overview#which-session-clock) to choose the appropriate timer.

### Schedule module {/* #calendar-module */}

Add **Schedule**. Under **Module options**, choose the weekend or whole season, included session types and Home Assistant, circuit or UTC time. You can dim or hide past starts, mark the next session and show circuit time.

The dashboard module uses [next-race](/entities/next-race) and [season schedule](/entities/current-season) data. The native [Season Calendar entity](/entities/season-calendar) is a separate way to display sessions and build calendar automations.

### Weather module {/* #weather-module */}

Add **Weather** and choose its content under **Module options**: current conditions, race-start forecast, track conditions or an overview/automatic view. Choose metrics or a compact list, then select the fields you want.

Forecasts and session measurements have different sources and availability. See the [weather comparison](/reference/overview#which-weather-entity) and [Track Weather](/entities/track-weather) before interpreting a missing value as current conditions.

### Race Control module {/* #race-control-module */}

Add **Race Control** and choose a list or the latest message. **Module options** control text search, message categories, ordering and the number of messages. With driver focus, you can include or hide session-wide messages.

Use the [Race Control reference](/entities/race-control) to understand message fields. The card's automatic data channel and the [public automation event](/entities/events#race-control) have separate demand rules; displaying the module does not enable additional public automation events.

### Results module {/* #results-module */}

Add **Results**. Choose the latest race, race results, sprint results or starting grid as the content. Select a round where supported, choose the fields and sorting, and use a table or grid presentation.

[Race classification](/entities/last-race-results), [sprint classification](/entities/sprint-results) and the [current Starting Grid](/entities/starting-grid) are different sources. A provisional starting grid is not a final race result, and the grid's waiting or completed states do not mean the results archive is empty.

### Championship module {/* #standings-module */}

Add **Championship** and choose drivers or teams. Select position, points and wins, then adjust sorting, row count and driver/team focus.

Published [driver standings](/entities/driver-standings) and [constructor standings](/entities/constructor-standings) differ from optional prediction fields. [Championship prediction](/entities/championship-prediction-drivers) has its own source and live/replay requirements; a standings table does not guarantee that predicted positions or points are available.

### Lap history chart module {/* #lap-chart-module */}

Add **Lap history chart**. Choose lap time or change between laps, select drivers and a lap range, and use a chart, table or both. Limit the number of driver series when you want a clearer comparison.

The module uses the session's [observed driver timing](/entities/driver-positions). Use [Historical archive](/features/historical-results) for another year's published results or available historical lap data. Classification and lap coverage are separate.

### Season progression module {/* #progression-module */}

Add **Season progression** and choose drivers or teams. Compare cumulative points, points per round or wins; narrow the round range and selected competitors, then choose a chart, table or both.

Use the [driver](/entities/driver-points-progression) and [constructor progression](/entities/constructor-points-progression) references for the underlying series. [Legend selection](/cards/shared-options#module-specific-presentation) can temporarily hide or restore a series without changing the saved card configuration.

### FIA documents module {/* #documents-module */}

Add **FIA documents** and choose a list or the latest document. Search titles, select ordering and row count, and choose whether document links open in a new tab. Optional document type, count and race-context fields help identify what is being shown.

The [FIA Documents reference](/entities/fia-decision-documents) explains the rolling document list, current-weekend context and source limitations. Open the published document for its official contents.

### Tyres module {/* #tyres-module */}

Add **Tyres** and choose current tyres or compound statistics. The current view follows drivers and their compounds or stint age; statistics compare recorded best runs, usage and sets. Compound filters, sorting and row limits control what you see.

[Current Tyres](/entities/current-tyres) and [Tyre Statistics](/entities/tyre-statistics) describe these different datasets. For pace estimates and clean-lap comparisons, use [Strategy analysis](/features/weekend-analysis#understand-strategy-estimates).

### Incidents module {/* #incidents-module */}

Add **Incidents** and choose investigations, track-limit events or a track-limit summary. Filter statuses or text and choose list or table presentation; driver/team focus can narrow the records.

This module uses [steward investigations and penalties](/entities/investigations) and [track-limit violations](/entities/track-limits). The separate [Incident Detection feature](/features/incident-detection) exposes likely stopped-car and on-track incident candidates through its own entities and events; the module name does not make these the same dataset.

</NativeDetails>

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
