---
id: cards-overview
title: Dashboard cards
description: Choose from 23 bundled F1 Sensor dashboard cards for schedules, timing, race control, results and replay.
toc_max_heading_level: 2
---

import {CardGallery} from '@site/src/components/Docs';

Choose from 23 bundled cards for your [Home Assistant](https://www.home-assistant.io/) dashboard. [Installation and setup](/cards/installation).

Start with [Next Race](/cards/next-race) between sessions, [Live Session](/cards/live-session) and a timing card on race day, or [Replay Control](/cards/replay-control) when watching later.

## Available cards

Filter by purpose, then open a card for its preview, setup and options. Public live timing works without F1TV Auth; check each card’s data requirements.

<CardGallery cards={[
  {
    "title": "Weekend Hub",
    "href": "/cards/weekend-hub",
    "image": "/img/cards/weekend-hub.png",
    "description": "Follow a race weekend in one place, from the session overview to strategy, battles and replay telemetry.",
    "category": "Session overview",
    "availability": "Live / Replay"
  },
  {
    "title": "Live Session",
    "href": "/cards/live-session",
    "image": "/img/cards/live-session.png",
    "description": "Keep the session name, track condition, weather and lap progress visible above your timing cards.",
    "category": "Session overview",
    "availability": "Public live / Replay"
  },
  {
    "title": "Next Race",
    "href": "/cards/next-race",
    "image": "/img/cards/next-race.png",
    "description": "See when the next Grand Prix starts, its weekend schedule and the circuit location at a glance.",
    "category": "Planning",
    "availability": "No live session needed"
  },
  {
    "title": "Race Weather",
    "href": "/cards/race-weather",
    "image": "/img/cards/race-weather.png",
    "description": "Compare current circuit conditions with the forecast for race start.",
    "category": "Planning",
    "availability": "Forecast / Public live"
  },
  {
    "title": "Season Calendar",
    "href": "/cards/season-calendar",
    "image": "/img/cards/season-calendar.png",
    "description": "Plan the season with a compact list of race weekends.",
    "category": "Planning",
    "availability": "No live session needed"
  },
  {
    "title": "Race Control",
    "href": "/cards/race-control",
    "image": "/img/cards/race-control.png",
    "description": "Follow Race Control messages and flags as they arrive.",
    "category": "Race officials",
    "availability": "Public live / Replay"
  },
  {
    "title": "FIA Documents",
    "href": "/cards/fia-documents",
    "image": "/img/cards/fia-documents.png",
    "description": "Open official FIA documents for the current race weekend from your dashboard.",
    "category": "Race officials",
    "availability": "Published documents"
  },
  {
    "title": "Qualifying Timing",
    "href": "/cards/qualifying-timing",
    "image": "/img/cards/qualifying-timing.png",
    "description": "Follow qualifying order, current sectors and Q1, Q2 and Q3 times in one table.",
    "category": "Timing",
    "availability": "Qualifying / Replay"
  },
  {
    "title": "Practice Timing",
    "href": "/cards/practice-timing",
    "image": "/img/cards/practice-timing.png",
    "description": "Compare practice laps with driver order, tyre age, last lap and personal best.",
    "category": "Timing",
    "availability": "Practice / Replay"
  },
  {
    "title": "Race Lap",
    "href": "/cards/race-lap",
    "image": "/img/cards/race-lap.png",
    "description": "Follow Race or Sprint order with gaps, tyres, pit counts and lap times.",
    "category": "Timing",
    "availability": "Race or Sprint / Replay"
  },
  {
    "title": "Starting Grid",
    "href": "/cards/starting-grid",
    "image": "/img/cards/starting-grid.png",
    "description": "See the provisional or confirmed starting order before a Race or Sprint.",
    "category": "Results and standings",
    "availability": "Published grid"
  },
  {
    "title": "Results",
    "href": "/cards/results",
    "image": "/img/cards/results.png",
    "description": "Review Race and Sprint classifications, then open Archive to browse historical results.",
    "category": "Results and standings",
    "availability": "Published results"
  },
  {
    "title": "Lap Position Progression",
    "href": "/cards/lap-position-progression",
    "image": "/img/cards/lap-position-progression.png",
    "description": "Trace how each driver moved through the field during a completed main race.",
    "category": "Results and standings",
    "availability": "Completed main races"
  },
  {
    "title": "Tyre Statistics",
    "href": "/cards/tyre-statistics",
    "image": "/img/cards/tyre-statistics.png",
    "description": "Compare tyre compounds, stint history and the best lap times set on each compound.",
    "category": "Timing",
    "availability": "Public live / Replay"
  },
  {
    "title": "Pit Stops",
    "href": "/cards/pit-stops",
    "image": "/img/cards/pit-stops.png",
    "description": "Review each driver\u2019s stops, fitted tyres and available pit timing.",
    "category": "Timing",
    "availability": "F1TV live / Replay"
  },
  {
    "title": "Driver Lap Times",
    "href": "/cards/driver-lap-times",
    "image": "/img/cards/driver-lap-times.png",
    "description": "Follow positions, gaps, last laps and personal bests in a detailed timing table.",
    "category": "Timing",
    "availability": "Public live / Replay"
  },
  {
    "title": "Investigations",
    "href": "/cards/investigations",
    "image": "/img/cards/investigations.png",
    "description": "Keep steward investigations and penalties in a focused list.",
    "category": "Race officials",
    "availability": "Public live / Replay"
  },
  {
    "title": "Track Limits",
    "href": "/cards/track-limits",
    "image": "/img/cards/track-limits.png",
    "description": "Track deleted laps, black-and-white warnings and track-limit penalties by driver.",
    "category": "Race officials",
    "availability": "Public live / Replay"
  },
  {
    "title": "Driver Championship",
    "href": "/cards/championship-drivers",
    "image": "/img/cards/championship-drivers.png",
    "description": "Compare current driver championship points with the prediction supplied during a session.",
    "category": "Results and standings",
    "availability": "Standings / F1TV prediction"
  },
  {
    "title": "Constructor Championship",
    "href": "/cards/championship-teams",
    "image": "/img/cards/championship-teams.png",
    "description": "Compare published constructor points with the session\u2019s predicted championship outcome.",
    "category": "Results and standings",
    "availability": "Standings / F1TV prediction"
  },
  {
    "title": "Season Progression",
    "href": "/cards/season-progression",
    "image": "/img/cards/season-progression.png",
    "description": "See how championship points accumulated across the season.",
    "category": "Results and standings",
    "availability": "Published points"
  },
  {
    "title": "Replay Control",
    "href": "/cards/replay-control",
    "image": "/img/cards/replay-control.png",
    "description": "Load and control an archived session from your dashboard.",
    "category": "Session overview",
    "availability": "Replay"
  },
  {
    "title": "Track Map",
    "href": "/cards/track-map",
    "image": "/img/cards/track-map.png",
    "description": "Watch driver markers move around the circuit with lap and track-status context.",
    "category": "Session overview",
    "availability": "F1TV live / Replay"
  }
]} />

## Data availability

The cards cover planning, live timing, race officials, results and replay. Track Map, pit-stop timing and live championship prediction can need optional authenticated data; replay availability depends on the archive. Each card page explains its requirements and what to expect when data is unavailable.

## Installation

### Bundled installation

The cards are bundled with F1 Sensor and registered automatically; no separate HACS dashboard download is needed. [Install the bundled cards](/cards/installation#bundled-installation), restart Home Assistant and reload your dashboard. The integration manages the JavaScript resource. See [Card installation](/cards/installation) if the card picker does not show them.

### Migrating from the old standalone card

Your existing card types remain valid. [Follow the migration steps](/cards/installation#migrate-from-the-standalone-card) to remove old resources after the bundled cards work.

## Adding cards

Open **Edit dashboard > Add card**, search for **F1**, choose a card and save. Start with [Next Race](/cards/next-race) if you want to verify the setup outside an active session.

## Shared options

[Entity selection, themes, fonts, spoiler protection and actions](/cards/shared-options) work consistently across the bundled cards. Each card page lists the settings specific to that card.

## Card reference

These direct links preserve the older card-reference bookmarks. Open the card name for its full guide.

| Card | YAML type |
| --- | --- |
| <span id="f1-weekend-hub-card" />[Weekend Hub](/cards/weekend-hub) | `custom:f1-weekend-hub-card` |
| <span id="f1-live-session-card" />[Live Session](/cards/live-session) | `custom:f1-live-session-card` |
| <span id="f1-next-race-card" />[Next Race](/cards/next-race) | `custom:f1-next-race-card` |
| <span id="f1-race-weather-card" />[Race Weather](/cards/race-weather) | `custom:f1-weather-card` |
| <span id="f1-season-calendar-card" />[Season Calendar](/cards/season-calendar) | `custom:f1-season-calendar-card` |
| <span id="f1-race-control-card" />[Race Control](/cards/race-control) | `custom:f1-race-control-card` |
| <span id="f1-fia-documents-card" />[FIA Documents](/cards/fia-documents) | `custom:f1-fia-documents-card` |
| <span id="f1-qualifying-timing-card" />[Qualifying Timing](/cards/qualifying-timing) | `custom:f1-qualifying-timing-card` |
| <span id="f1-practice-timing-card" />[Practice Timing](/cards/practice-timing) | `custom:f1-practice-timing-card` |
| <span id="f1-race-lap-card" />[Race Lap](/cards/race-lap) | `custom:f1-race-lap-card` |
| <span id="f1-starting-grid-card" />[Starting Grid](/cards/starting-grid) | `custom:f1-starting-grid-card` |
| <span id="f1-results-card" />[Results](/cards/results) | `custom:f1-last-race-results-card` |
| <span id="f1-lap-position-progression-card" />[Lap Position Progression](/cards/lap-position-progression) | `custom:f1-lap-position-progression-card` |
| <span id="f1-tyre-statistics-card" />[Tyre Statistics](/cards/tyre-statistics) | `custom:f1-sensor-live-data-card` |
| <span id="f1-pit-stop-overview-card" />[Pit Stops](/cards/pit-stops) | `custom:f1-pitstop-overview-card` |
| <span id="f1-driver-lap-times-card" />[Driver Lap Times](/cards/driver-lap-times) | `custom:f1-driver-lap-times-card` |
| <span id="f1-investigations-card" />[Investigations](/cards/investigations) | `custom:f1-investigations-card` |
| <span id="f1-track-limits-card" />[Track Limits](/cards/track-limits) | `custom:f1-track-limits-card` |
| <span id="f1-championship-prediction-drivers-card" />[Driver Championship](/cards/championship-drivers) | `custom:f1-championship-prediction-drivers-card` |
| <span id="f1-championship-prediction-teams-card" />[Constructor Championship](/cards/championship-teams) | `custom:f1-championship-prediction-teams-card` |
| <span id="f1-season-progression-card" />[Season Progression](/cards/season-progression) | `custom:f1-season-progression-card` |
| <span id="f1-replay-control-card" />[Replay Control](/cards/replay-control) | `custom:f1-replay-control-card` |
| <span id="f1-track-map-card" />[Track Map](/cards/track-map) | `custom:f1-track-map-card` |

## Related

- [Live data reference](/entities/live-data)
- [Static data reference](/entities/static-data)
- [Replay Mode](/features/replay-mode)
- [F1TV Auth](/features/f1tv-auth)
- [Live Delay](/features/live-delay)
