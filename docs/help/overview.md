---
id: overview
title: Find and fix a problem
description: Start with the symptom, distinguish waiting for data from a setup issue, and collect useful F1 Sensor logs.
---

Choose the symptom closest to what you see. Check your installed version and whether you are using live timing, Replay Mode or schedule data before changing settings.

## Where to start

| What you see | Check first | Next step |
| --- | --- | --- |
| F1 Sensor is missing from Add integration | Installation completed and Home Assistant restarted | [Installation](/getting-started/installation) |
| No F1 Sensor card in the dashboard picker | Restart after update, then refresh the browser | [Card installation and loading checks](/cards/installation) |
| A modular card has no data | Correct F1 Sensor installation, live setting, session and any required account access | [Automatic card data](/features/card-data-and-sensors) |
| An automation, standard card or older F1 card has a missing entity | Entity selected and actual entity ID used | [Configuration](/getting-started/add-integration) |
| Live entities are inactive | There is an active/upcoming session and live data is enabled | [No live updates](#no-live-updates) |
| Track Map has no cars | Session, token health and position-data availability | [Track Map status messages](/features/track-map#status-messages) |
| Data arrives before the TV picture | Broadcast delay is not yet matched | [Live Delay](/features/live-delay) |
| Replay session is missing | Correct season selected, session list loaded, and archive available | [Replay setup](/features/replay-mode#using-replay-mode) |
| Results remain frozen | No Spoiler Mode is still on | [No Spoiler Mode](/features/no-spoiler-mode) |
| Token pairing fails | Original pairing tab is active and link has not expired | [Token Helper troubleshooting](/help/f1tv-token-helper#troubleshooting) |
| Recorder warns about large attributes | A large result sensor is being recorded | [Recorder guidance](/help/issues) |

## No live updates

1. Open F1 Sensor **Reconfigure** and confirm **Enable live F1 API** is on.
2. For modular cards, check the selected installation and module explanation. Their automatic data does not require matching sensors. For an automation, template, standard card or older F1 card, confirm that its required entities are selected.
3. Read the card’s session context, or `sensor.f1_current_session` and `sensor.f1_session_status` if selected. Between sessions, waiting is normal.
4. Check `switch.f1_no_spoiler_mode`. If it is on, live delivery is intentionally stopped.
5. If Replay Mode is active, stop it when you want to return to live timing.
6. For an authenticated feature, check `sensor.f1_f1tv_token_status` and the [availability matrix](/features/f1tv-auth#availability-matrix).

If a diagnostic entity is disabled or has a different ID, find it in the integration's entity list before copying a reference into your dashboard.

## A replay session is missing

1. Check the year selected in `select.f1_replay_year`.
2. Refresh the session list with `button.f1_replay_refresh`.
3. Inspect `sensor.f1_replay_status` for `index_error` or `download_error`.
4. If the session just ended, try again later. Formula 1 controls when archived timing becomes available.

See [Replay Mode](/features/replay-mode#using-replay-mode) for loading and playback, and [Replay controls](/reference/replay-controls#replay-status-sensor) for status fields.

## Missing entity or old card

The modular F1 Sensor card discovers data from its selected installation. It does not need an entity enabled for each module.

Standard cards, older F1 cards, templates and automations use actual entity IDs, which may differ from the examples. Select the existing entity rather than renaming a working setup to match a guide.

After updating, restart Home Assistant and refresh the browser. Follow the [migration guide](/cards/installation) if you used the old standalone card. Confirm the bundled card works before removing old resources.

## Still not working?

[Collect debug logs](/help/debug-logging), reproduce the issue once, and [choose the right support channel](/help/contact). Include the F1 Sensor and Home Assistant versions, session/mode, expected result and actual result. Review files for credentials before sharing them.

For short answers, browse the [FAQ](/help/faq).
