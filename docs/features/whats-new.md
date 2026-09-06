---
id: whats-new
title: What's new
description: Discover Weekend Hub, Results Archive, Favorite Driver and easier dashboard setup in F1 Sensor.
---

F1 Sensor brings session analysis, historical results and driver-focused automations into your Home Assistant dashboard. Start with a new card, explore an existing card's new views, or simplify your dashboard setup.

After updating F1 Sensor, restart Home Assistant and reload your dashboard to load the matching bundled cards. See [Card installation and updates](/cards/installation) if a card or option is missing.

## Choose something to try

| You want to… | What you can use | Setup and reference |
| --- | --- | --- |
| Follow a session and examine strategy in one card | **Weekend Hub**, with Overview, Timeline, Strategy, Telemetry and Battles | [Weekend Hub card](/cards/weekend-hub) · [Analysis walkthrough](/features/weekend-analysis) |
| Compare driving traces from a recording | Up to four selected driver/lap combinations from a loaded replay | [Compare replay laps](/features/weekend-analysis#compare-replay-laps) |
| Browse previous seasons without starting playback | **Archive** in Results, including Race, Sprint and qualifying classifications where published | [Historical results guide](/features/historical-results) · [Results settings](/cards/results) |
| React to one driver's position or pit activity | Opt-in **Favorite Driver** selector, sensor and five device triggers | [Favorite Driver setup](/features/favorite-driver) · [Entity reference](/entities/favorite-driver) |
| Use renamed entities without repairing every default source | Automatic entity selection for bundled cards, including multiple-entry setup | [Entity selection](/cards/shared-options#entity-selection) |
| Keep dashboard interaction consistent | Shared focus, gap reference and spoiler context in supported cards; card actions and translated interface text | [Dashboard preferences](/cards/shared-options#dashboard-context) |

## Which cards are new?

**Weekend Hub joins the card picker**, bringing the collection to 23 selectable bundled cards. Results is an existing card with a new Archive view. Strategy, Timeline, Telemetry and Battles are views inside Weekend Hub, not separate cards to install.

The earlier `custom:f1-session-archive-card` remains supported as a compatibility name. It opens Results in Archive mode and is not a separate picker entry. See [Session Archive compatibility](/cards/session-archive) if you already use it.

## Try the new features

Start with these three steps:

1. Add [Weekend Hub](/cards/weekend-hub) with **Overview** as its default view. During a live session, enable the live timing features you want to follow; when watching later, first load a session with [Replay Control](/cards/replay-control).
2. Add [Results](/cards/results) and open **Archive** to explore a completed season. This does not start Replay Mode or move the other cards to that historical session.
3. Enable [Favorite Driver](/features/favorite-driver) if you want driver-specific entities and automations. Weekend Hub's **Focus driver** selection only changes supported dashboard views; it does not select your Favorite Driver entity.

No F1TV token is needed for historical classifications or public replay archives. Live enhanced data still follows the [F1TV availability rules](/features/f1tv-auth).

## Improvements to familiar features

| Area | What changes |
| --- | --- |
| Replay | Improved loading and seeking restore session state across jumps. The existing selectors, playback buttons and media player remain the way to control a replay. See [Replay behavior](/features/replay-mode#replay-improvements). |
| Race Control | Message timestamps follow Home Assistant's timezone and 12/24-hour preference. See [Race Control](/cards/race-control). |
| Session clocks | Elapsed, remaining and race-limit clocks receive restored timing updates. A clock still needs usable session data; missing timing is not a zero value. See [Live Session](/cards/live-session). |
| Dashboard language and interaction | Supported text follows Home Assistant's language, with English fallback. Shared actions, keyboard interaction and reduced-motion handling improve card use. See [Shared card options](/cards/shared-options). |
| F1TV Token Helper | Pairing supports Home Assistant Container setups, with clearer token handling. Use the [pairing guide](/help/f1tv-auth-setup) when reconnecting. |

## Know the data limits

Weekend Hub analyses the timing it has observed. Strategy can wait for clean laps, and its confidence labels describe the available evidence rather than a guaranteed prediction. Telemetry comparison needs usable samples for the selected laps in the loaded replay; it is not a live telemetry recorder. Historical classifications can be available without lap-by-lap timing, practice results or replay telemetry.

Keep [No Spoiler Mode](/features/no-spoiler-mode) enabled until you are ready to see results. Rewinding a replay can trigger the same notifications again.

## If something does not appear

Check that the integration and bundled cards are up to date, then confirm that the relevant features are enabled. When reporting a problem, include your F1 Sensor version, Home Assistant version, card type, selected session, and whether you were viewing live data, replay or Results Archive. Follow [troubleshooting](/help/overview) for the next checks.
