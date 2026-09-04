---
id: faq
title: Frequently asked questions
description: Short answers about setup, live data, dashboard cards, replay and optional F1TV access.
---

Find a short answer here, or use [symptom-based troubleshooting](/help/overview) for checks in order.

## General Questions

### Which release channel should I use?

Use stable for everyday use. Beta is for testing the next release; dev is for development or a specific maintainer-led test. See [updates and release channels](/getting-started/release-channels).

### Do I need an API key or a separate weather account?

No API key is required for normal setup. F1TV access is optional and only affects additional live features. Start with [installation](/getting-started/installation).

### Can I show the data on an ESPHome display?

Yes, through Home Assistant. F1 Sensor runs in Home Assistant; an ESPHome device can consume the entity states through its Home Assistant connection. The [e-ink example](/example/e-ink) is a separate display project.

### Where are practice and qualifying times?

The Next race and calendar data include the weekend schedule. Use the [Next Race card](/cards/next-race), [Season Calendar card](/cards/season-calendar), or the attributes in the [schedule reference](/entities/next-race).

## Live Data Questions

### Do I need F1TV Auth or an F1 TV Pro subscription?

F1TV Auth is optional. Public live timing supports session status, track flags, Race Control, weather, driver timing, tyres and confirmed incident alerts. Extra live feeds may need an account with the relevant timing access. Read the [availability and subscription guidance](/features/f1tv-auth) before subscribing.

### Why does Track Map work in replay but not live?

Replay can contain archived car-position data. Live positions require optional F1TV access and usable data from the current session. A replay working does not prove that live position access is available. See [Track Map](/features/track-map).

### Why are Pit Stops, Team Radio or Championship Prediction unavailable?

They depend on extra data published for the session. During live timing they can need F1TV Auth; during replay the archive must contain the data. An accepted token alone does not guarantee all feeds. See the [availability matrix](/features/f1tv-auth#availability-matrix).

### Why do live sensors stop between sessions?

Live entities follow active practice, qualifying, sprint or race sessions. Outside the live window they can be inactive, unchanged or unavailable. Schedules and other non-live data continue to serve different purposes.

### How do I match updates to the TV?

Set `number.f1_live_delay` manually or measure the delay with guided calibration. [Live Delay](/features/live-delay) explains both. For recorded sessions, use [Replay Mode](/features/replay-mode) and its playback controls instead.

### Can I watch a session later without seeing results first?

Turn on [No Spoiler Mode](/features/no-spoiler-mode) before the session. Later, load the session archive with [Replay Mode](/features/replay-mode). No Spoiler Mode is not a recording service, and archive coverage varies.

### Replay Mode or Developer mode?

Use Replay Mode for watching completed sessions. [Developer mode](/help/developer-mode) uses a local timing dump for testing; it is a different workflow with different controls.

### How do I find Race Control, flags or the current session?

Use [Race Control](/entities/race-control) for messages, [Track Status](/entities/track-status) for flags, and [Current Session](/entities/current-session) for the session name. [Session Status](/entities/session-status) reports the phase, such as `live` or `suspended`. A live phase alone does not identify a Race rather than a practice session.

### Can I display the lap counter and total laps?

Use `sensor.f1_race_lap_count` and its `total_laps` attribute when available. The [Race Lap reference](/entities/race-lap) explains the state. Missing total laps can mean the source has not supplied them yet.

## Troubleshooting

### Do I install the cards separately?

No. They are bundled with the integration. Restart Home Assistant after installation and refresh your browser. Follow [Your first dashboard](/getting-started/first-dashboard).

### Why do I still see an old card after updating?

The browser may have cached an older resource, or a standalone resource may remain configured. Follow [card installation and migration](/cards/installation). Keep existing dashboard configurations and verify the bundled cards before removing old resources.

### Why does my entity name differ from the documentation?

Display names can be translated; older or customized installations can also have different entity IDs. Select the actual entity in the visual editor. Examples use standard IDs; they are not instructions to rename yours.

### Why are newly added sensors missing?

Open **F1 Sensor → Reconfigure**, enable live data if needed, and select the feature. Some features, including Favorite Driver, are opt-in. Use the [configuration guide](/getting-started/add-integration).

## Can't find the answer you're looking for?

Start with [troubleshooting](/help/overview), then [collect logs](/help/debug-logging) and [get help](/help/contact).
