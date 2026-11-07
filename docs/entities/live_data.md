---
id: live-data
title: "Live data entities"
description: "Find live F1 session, driver, track, and race control entities with links to their full references."
---

import {EntityCatalog} from '@site/src/components/Docs';

Use these entities to follow a session, build timing dashboards, and trigger automations. Each entity has a focused page with its complete state, attributes, and examples.

## Availability model

Most live entities need an active session and **Enable live F1 API** in [Configuration](/getting-started/add-integration). Outside a session they may become unavailable; Driver List retains its last known data for dashboard graphics. Check the individual reference for exceptions.

| Data mode | What to expect |
| --- | --- |
| Public live timing | Session status, track status, Safety Car, Race Control, weather, driver timing, tyres, top three, and confirmed incident detection |
| Optional F1TV Auth | Extra live data depends on token acceptance, your account’s permissions, and the streams published for the session |
| Replay Mode | Completed session data plays through the same entities when the archive contains it |

[F1TV availability](/features/f1tv-auth) compares anonymous access, a free account, and a paid account. A valid token does not guarantee every extra live feed. [Track Map](/features/track-map) is a dashboard feature, not a normal Home Assistant entity. The unofficial live timing API can change without notice.

## Reference: Enum Values

Find [track flags, session phases, tyre compounds, and timing modes](/reference/values) in the state value reference.

:::info[Entity IDs and display names]
The links use standard entity IDs. Display names can be translated, and older or renamed entities may have different IDs. Select the entity from your installation when copying an example.
:::

## Entities Summary

Search by name, standard entity ID or attribute. Open any result for its complete state, fields, examples and limitations.

<EntityCatalog scope="live">
<span id="session-status"></span>
<span id="current-session"></span>
<span id="session-time-elapsed"></span>
<span id="session-time-remaining"></span>
<span id="race-three-hour-limit"></span>
<span id="track-status"></span>
<span id="safety-car"></span>
<span id="on-track-incident"></span>
<span id="possible-on-track-incident"></span>
<span id="race-lap"></span>
<span id="track-weather"></span>
<span id="session-rain-risk"></span>
<span id="driver-list"></span>
<span id="pit-stops"></span>
<span id="team-radio"></span>
<span id="current-tyres"></span>
<span id="tyre-statistics"></span>
<span id="favorite-driver"></span>
<span id="driver-positions"></span>
<span id="starting-grid"></span>
<span id="grid-context-and-source"></span>
<span id="weekend-flow"></span>
<span id="top-three"></span>
<span id="race-control"></span>
<span id="track-limits"></span>
<span id="investigations"></span>
<span id="championship-prediction-drivers"></span>
<span id="championship-prediction-teams"></span>
<span id="formation-start"></span>
<span id="overtake-mode"></span>
<span id="straight-mode"></span>
</EntityCatalog>

## Browse all reference topics

The [complete reference catalogue](/reference/overview) includes all data sources, event payloads, device triggers and playback controls.
