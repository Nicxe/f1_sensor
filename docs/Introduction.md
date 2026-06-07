---
id: introduction
title: Introduction
slug: /
---

[![Buy me a Coffee](https://img.shields.io/badge/Support-Buy%20me%20a%20coffee-fdd734?logo=buy-me-a-coffee)](https://www.buymeacoffee.com/NiklasV) [![Last commit](https://img.shields.io/github/last-commit/Nicxe/f1_sensor)](#) [![Version](https://img.shields.io/github/v/release/Nicxe/f1_sensor)](#) [![HA Community forum](https://img.shields.io/badge/Home%20Assistant-Community%20Forum-319fee?logo=home-assistant)](https://community.home-assistant.io/t/formula-1-racing-sensor/880842)

## Your home, in sync with Formula 1

F1 Sensor is a custom [Home Assistant](https://www.home-assistant.io/) integration for Formula 1 schedules, standings, live timing, post-race analysis, dashboards, automations, and replayed sessions.

It works without F1TV Auth. Public live timing powers core live entities such as track status, race control, weather, driver timing, tyres, and conservative incident alerts. Optional [F1TV Auth](/features/f1tv-auth) can unlock extra live timing features when Formula 1 provides the data.

![F1SensorFlag-ezgif com-video-to-gif-converter (5)](https://github.com/user-attachments/assets/18a74679-76e2-4d10-8a0d-d3f111c42593)

## Getting started

Start with the [installation guide](/getting-started/installation), then use [configuration](/getting-started/add-integration) to add F1 Sensor to Home Assistant.

Most users should install the stable release. See [Release Channels](/getting-started/release-channels) before using beta or `dev` builds.

## Version 5.1

Version 5.1 expands live, replay, dashboard, and automation support:

- [Track Map](/features/track-map) adds live and replay circuit maps with driver markers
- [Incident Detection](/features/incident-detection) adds neutral stopped-car and on-track incident alerts
- [Incident Notifications](/blueprints/incident-notifications) adds a ready-made notification blueprint with conservative defaults
- [F1TV Auth](/features/f1tv-auth) becomes a standard optional feature for supported extra live timing data
- [Replay Mode](/features/replay-mode) adds a draggable seek bar and improved replay state restoration
- [Live Data Cards](/cards/cards-overview) add lap position and championship progression charts, Track Map, and compact layouts

Version 5.1 also includes reliability fixes for replay controls, practice timing, pit stop and tyre data, next-race updates, expired F1TV access, and consecutive Track Status blueprint alerts.

## Features

Take your setup further with focused feature pages:

- [Live Delay](/features/live-delay) - Sync live data with your TV broadcast
- [Replay Mode](/features/replay-mode) - Relive historical sessions with Home Assistant entities and dashboard cards
- [No Spoiler Mode](/features/no-spoiler-mode) - Freeze spoiler-sensitive data until you are ready to watch
- [F1TV Auth](/features/f1tv-auth) - Add optional live timing enhancements while public live timing continues to work
- [Track Map](/features/track-map) - Show car markers on a circuit map during live or replay sessions
- [Incident Detection](/features/incident-detection) - Detect likely stopped cars or on-track incidents with neutral alerts

## Blueprints

Use ready-made blueprints for [Track Status lights](/blueprints/track-status-light), [Race Control notifications](/blueprints/race-control-notifications), [Incident Notifications](/blueprints/incident-notifications), and [Replay Sync](/blueprints/replay-sync).

## Timing modes

| Mode | What it means |
| --- | --- |
| Public live timing | Standard live mode without F1TV Auth. Core live entities and confirmed incident alerts work here |
| F1TV Auth live timing | Optional mode for extra live features such as live Track Map, Pit Stops, Championship Prediction, and earlier incident candidates |
| Replay Mode | Historical playback from Formula 1's session archive. Some live-auth features can appear later when the archived session contains the needed data |
| Developer mode | Advanced testing with a local replay dump. Use it to reproduce integration behavior, not to follow a TV replay |

For the difference between the two recorded-data workflows, see [Replay Mode](/features/replay-mode#replay-mode-vs-developer-mode) and [Developer Mode with Replay Dumps](/help/developer-mode).

## Dashboards and automations

Use [Live Data Cards](/cards/cards-overview) for ready-made dashboards, or build your own automations from [live entities](/entities/live-data), [events](/entities/events), and [device triggers](/automation#device-automation-triggers).

## Support

If you enjoy using `F1 Sensor`, you can find ways to support the project [here](/support).

:::info
F1 Sensor is an unofficial project and is not associated in any way with the Formula 1 companies. F1, FORMULA ONE, FORMULA 1, FIA FORMULA ONE WORLD CHAMPIONSHIP, GRAND PRIX and related marks are trade marks of Formula One Licensing B.V.
:::
