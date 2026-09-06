---
id: historical-results
title: Browse historical results
description: Open the Results archive to compare past Race, Sprint and qualifying classifications without starting Replay Mode.
---

import {Figure} from '@site/src/components/Docs';

Use the **Archive** view in [Results](/cards/results) to browse published classifications from previous seasons. It is useful for checking a finishing order, grid movement, points or qualifying times without loading a full replay.

<Figure src="/img/cards/results-archive.png" alt="Results Archive showing the 2024 Abu Dhabi Grand Prix race classification and season, event and session selectors" caption="The 2024 Abu Dhabi Grand Prix race result, captured from Results Archive in Home Assistant." />

## Before you start

Update F1 Sensor and reload the dashboard so it uses the matching bundled cards. You need a working F1 Sensor entry and access to the historical results provider. F1TV Auth and an active live session are not required.

## Open a classification

1. Add the **F1 Results** card through **Edit dashboard → Add card**, or open an existing Results card.
2. Select **Archive** in the card.
3. Choose a season using the year controls, then select a Grand Prix and an available session.
4. Wait for the classification. Use **Refresh** to request an updated result if the source has published a correction.

Race and Sprint classifications show race fields such as grid, laps, finish status and points. Qualifying uses position, driver and Q1–Q3 times. Some sessions or older seasons have incomplete information; an empty field does not mean the driver had a zero time.

Opening Archive fetches the selected historical data on demand. It does not load every season in the background or start a replay.

<Figure src="/img/cards/results-archive-qualifying.png" alt="Results Archive qualifying classification with Q1, Q2 and Q3 times" caption="Selecting Qualifying switches the same card to Q1–Q3 times. Shown here: Abu Dhabi, 2024." />

## Open Archive by default

Paste this into a manual dashboard card. It opens the 2024 season's archive and lets you select an event and session:

```yaml
type: custom:f1-last-race-results-card
default_scope: archive
show_archive: true
history_year: 2024
history_entry_id: auto
theme_mode: auto
```

With several F1 Sensor entries, select the intended sources in the card editor and set **Archive config entry id** when necessary. An integration entry ID is different from a sensor entity ID. Keep custom entity names already used by your dashboard. See [Results configuration](/cards/results#configuration) for all display options.

## Archive or Replay?

| Choose | What happens |
| --- | --- |
| **Results → Archive** | Displays a published classification. Other live entities continue following their existing session. |
| **Replay Control → Load** | Loads archived timing for playback through supported F1 entities and automations. |
| **Weekend Hub → Telemetry** | Compares selected laps from the replay you have already loaded. |

Selecting an Archive event does not load it into Weekend Hub. To analyse its timing there, select and load that session in [Replay Mode](/features/replay-mode) and follow the [analysis walkthrough](/features/weekend-analysis).

## When a result is missing

- **No events or sessions:** check the year and try another published session. Practice classifications are not supplied by this archive; historical Race, Sprint and qualifying availability varies.
- **An error with Try again:** retry the request after checking connectivity. Reinstalling the card cannot make an unavailable provider respond.
- **A result without lap progression:** classification and lap-by-lap coverage are separate. A Sprint result does not guarantee a position chart or telemetry.
- **Hidden results:** check the configured [spoiler protection](/features/no-spoiler-mode). Reveal results only when you are ready.
- **Archive is absent:** check the installed version, `show_archive`, and the [card loading checks](/cards/installation#card-loading-checks).

If you previously installed a separate Session Archive card, use the [compatibility guide](/cards/session-archive). Existing configurations continue to open Archive.
