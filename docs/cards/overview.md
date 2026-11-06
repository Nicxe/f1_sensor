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

These resources are shared by Home Assistant. If you have several F1 Sensor installations, legacy cards remain available while any enabled installation with dashboard cards enabled requests them. Independently installed Marketplace or HACS resources are not removed by this option.

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

Add **Lap history chart**. Choose lap time, change between laps or **Race Trace**, select drivers and a lap range, and use a chart, table or both. Existing lap-time and lap-change configurations keep their behavior.

The module uses the session's [observed driver timing](/entities/driver-positions). Use [Historical archive](/features/historical-results) for another year's published results or available historical lap data. Classification and lap coverage are separate.

**Race Trace** compares accumulated recorded lap times in an identified **Race** or **Sprint**, live or in replay. It requires no additional F1 TV access beyond the timing data already available to the card.

1. Select **Race Trace** as the measure.
2. Choose a fixed **Reference driver** and up to three comparison drivers. The reference counts toward the four-driver limit. Leaving the comparison selection empty shows only the reference.
3. Leave **Reset after lap** at `0` to use the earliest common completed lap with confirmed timing association, or choose an explicit lap. The card shows the actual anchor, including when recording starts late.
4. Choose **Chart**, **Table** or **Both**. Adjust **First lap** and **Last lap** to change the displayed interval.

Each comparison starts at zero **after** the anchor lap. The anchor's lap time is not included in the sum:

```text
Delta at lap n = sum of (driver lap time − reference lap time)
                for laps after the anchor through lap n
```

Positive values mean the driver has accumulated more recorded lap time than the reference since the anchor; negative values mean less. For example, with an anchor after lap 1:

| Lap | Reference | Comparison driver | Accumulated delta |
| --- | --- | --- | --- |
| 1 | 90.0 s | 91.0 s | 0.0 s |
| 2 | 90.0 s | 89.5 s | −0.5 s |
| 3 | 91.0 s | 92.0 s | +0.5 s |
| 4 | 90.0 s | 110.0 s | +20.5 s |

The automatic anchor stays fixed for the same session context, reference and driver selection. Receiving an older lap later does not move it. Changing the displayed interval does not reset the sum; use **Reset after lap** for that. Changing the reference or comparison drivers establishes a new comparison. Shared driver focus does not replace the reference.

A missing, invalid or uncertain lap breaks that driver's line and all following cumulative values. A missing reference lap affects every comparison. Filling the gap or receiving an accepted correction recalculates the following values. If the locked anchor becomes unavailable, the view waits for that anchor to return or for you to choose another one. It never silently restarts at zero.

Race Trace compares the same lap numbers, with a maximum of 500 laps. It does **not** measure the simultaneous gap between cars, distance to the leader or wall-clock race time. Crossings are not evidence of an overtake, and fewer recorded laps do not prove a retirement or lapping. Recorded pit and neutralised laps remain included; no red-flag pause is added or subtracted. An official lap-time deletion alone does not remove an otherwise available recorded duration.

[Live Delay and No Spoiler](/cards/shared-options) apply to the graph, table and event details. Older backends without the required [lap-history contract](/reference/card-data-api#lap-history-for-race-trace) show Race Trace as unsupported while existing lap-time charts remain available. A supported backend waits when session identity or confirmed lap data is still missing.

**Event markers** are optional and start disabled. Select **Pit stop**, **Safety Car**, **Virtual Safety Car** or **Red flag** to add observed events. In YAML, the `event_markers` option defaults to `[]` and accepts `pit`, `sc`, `vsc` and `red_flag`.

Pit markers use an explicit driver and lap. Global flag markers use the reference driver's last confirmed completed lap at the event observation, labelled **after observed reference lap**. This does not locate the event at an exact instant or mean that it affected the whole lap. Events without a safe anchor remain in the timeline rather than being assigned a guessed lap.

Start, ending announcement and observed end are separate points. **Ending announced** does not mean the track is clear. Missing starts or ends are not filled in, and no shaded interval or invented endpoint is drawn. Markers appear in a separate event strip, including when that lap's cumulative delta is missing. Use **Inspect lap** with the keyboard to read details; the table includes the same events. Markers do not change delta values or seek the replay.

Marker history is limited by the shared timeline's 500 retained events, including completed laps for every driver. Earlier pit stops and flags can therefore be missing by the end of a race even when Race Trace still has the full recorded lap history. The markers are not a complete race-event archive.

The base graph remains available when marker data is unsupported or waiting. In particular, events wait if analysis has advanced beyond the timing observation used by the graph. During an interruption, or after the final timing update, they may keep waiting until another timing observation arrives. Older backends with the lap-history contract can therefore show the graph even when they cannot supply markers.

Enabling markers uses the card's shared analysis subscription and the existing F1 connection. Pit markers depend on the available pit-stop feed, which retains its existing live authentication requirement; selecting the option does not unlock that feed.

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
