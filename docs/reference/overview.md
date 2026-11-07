---
id: overview
title: "Entity and automation reference"
description: "Browse all F1 Sensor entities by topic, then look up states, attributes, events, and device triggers."
---

import {EntityCatalog} from '@site/src/components/Docs';

Find the exact entity, state, or attribute you need for a dashboard or automation.

[State values](/reference/values) · [Events](/entities/events) · [Controls](#controls) · [Other references](#choose-a-reference)

## Find an entity

<EntityCatalog>
<span id="schedule-and-weather"></span>
<span id="session-and-track"></span>
<span id="drivers-and-timing"></span>
<span id="results-and-championship"></span>
<span id="officials-and-incidents"></span>
</EntityCatalog>

Search by name, entity ID or attribute, then narrow by topic or data source. The full state, nested fields, examples and source limitations remain on each reference page.

## Choose a reference

| You need | Start here |
| --- | --- |
| An entity ID or attribute | [Search and filter the entity catalogue](#find-an-entity) |
| Track flag or session phase values | [State values and terminology](/reference/values) |
| A trigger in the automation editor | [Device triggers](/reference/device-triggers) |
| An event payload | [Events](/entities/events) |
| Live Delay helper values and calibration | [Live Delay controls](/reference/live-delay-controls) |
| Replay selectors, buttons, and media player actions | [Replay controls](/reference/replay-controls) |
| Token, replay, or connection health | [Diagnostics](/entities/diagnostics) |
| Direct card data without sensor entities | [Card data protocol](/reference/card-data-api) |
| A working automation example | [Automation recipes](/automation#yaml-examples) |

### Controls

- [Live Delay controls](/reference/live-delay-controls): delay helpers and calibration.
- [Replay controls](/reference/replay-controls): session selectors, buttons and playback actions.

## Entity IDs

References show the standard IDs for new installations. Your display names may be translated, and older installations or renamed entities can use different IDs. Check **Settings > Devices & services > Entities** before copying an example. Select the entity from your own installation when using a template, card or automation.

If you are setting up F1 Sensor for the first time, start with [Installation](/getting-started/installation) and [Configuration](/getting-started/add-integration).

## Which weather entity?

| You want | Choose |
| --- | --- |
| Native Home Assistant conditions and hourly, daily or twice-daily forecasts | [Next Race Weather](/entities/next-race-weather) (`weather.f1_weather`) |
| Compact current/race-start forecast attributes for templates or existing dashboards | [Weather Summary](/entities/weather-summary) (`sensor.f1_weather`) |
| Measurements published during the session, including track temperature | [Track Weather](/entities/track-weather) (`sensor.f1_track_weather`) |
| The rain-risk percentage published by Race Control for a specific session | [Session Rain Risk](/entities/session-rain-risk) (`sensor.f1_session_rain_risk`) |

Session rain risk, detected rain and the weather provider's forecast are different observations. A missing rain-risk message does not imply `0 %`.

## Which session clock?

| You want | Choose |
| --- | --- |
| Time passed on the available session clock | [Session Time Elapsed](/entities/session-time-elapsed) |
| Scheduled session time still left | [Session Time Remaining](/entities/session-time-remaining) |
| Countdown to three hours after recorded race start | [Race Three Hour Limit](/entities/race-three-hour-limit) |
| Race or sprint progress measured in laps | [Race Lap](/entities/race-lap) |

The clocks follow their documented source and availability rules. A Safety Car does not by itself mean a clock pauses, and a time estimate does not predict an official race-ending decision.

## Availability before troubleshooting

Live entities depend on the session and data source. [Live data availability](/entities/live-data#availability-model) and [F1TV Auth](/features/f1tv-auth) explain normal waiting or unavailable states. Schedules and completed results have separate update behavior, documented on each page.
