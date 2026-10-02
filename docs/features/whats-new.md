---
id: whats-new
title: What's new
description: Discover the unified F1 Sensor dashboard card, its presets, modules and migration workflow.
---

F1 Sensor now provides one configurable dashboard card for the complete Formula 1 experience. The **F1 Sensor** card combines weekend planning, live timing, officials' messages, results, replay and analysis in a visual editor.

After updating F1 Sensor, restart Home Assistant and reload the dashboard to load the matching card files. See [card installation and updates](/cards/installation) if the card or an option is missing.

## Start with one card

Add **F1 Sensor** from the Home Assistant card picker and choose one of six presets:

| You want to… | Start with |
| --- | --- |
| Plan the next event | **Race weekend** |
| Compare current and forecast weather | **Weather comparison** |
| Follow practice, qualifying, sprint or race | **Follow the session** |
| Keep one driver in focus | **My driver** |
| Review results and championship progress | **Results and championship** |
| Choose every module yourself | **Build your own** |

Presets are editable starting points. All use `custom:f1-sensor-card` and the same editor.

## Combine 20 modules

The card includes modules for Overview, Schedule, Timing, Race Control, Results, Championship, Historical archive, Replay, Replay telemetry, Lap history chart, Season progression, FIA documents, Track map, Battles and position changes, Strategy analysis, Session timeline, Tyres, Pit stops, Incidents and Weather.

Modules can be reordered, duplicated, disabled or limited to selected session phases. They can inherit the card's driver, team and session focus or keep independent choices.

## Configure content and presentation together

The visual editor now covers:

- module fields, filters and presentation
- shared or pinned live, replay and archive sessions
- stacked or tabbed layouts
- F1, Home Assistant and Minimal visual styles
- density, typography, logos, flags, team colors and tyre display
- timing colors with shape or text signals
- unavailable-data behavior, retained readings and Freeze view
- reusable templates and complete JSON export/import

See [Build your F1 Sensor card](/cards/modular) for the full workflow.

## Move an existing dashboard

The earlier single-purpose card types are deprecated. Their editors offer **Review conversion**, which builds a new F1 Sensor card configuration, lists transferred and changed settings, keeps unsupported choices visible and stores the exact original for recovery.

Conversion changes only the editor draft until you save in Home Assistant. Follow [Move to the F1 Sensor card](/cards/modular-migration) before replacing an existing dashboard card.

## Use archive, replay and analysis deliberately

| Need | Use |
| --- | --- |
| Browse a published past classification | Historical archive |
| Play a recorded session through F1 entities | Replay |
| Compare recorded driver laps | Replay telemetry |
| Examine pace and pit-cycle evidence | Strategy analysis |
| Review detected session events | Session timeline |
| Examine close running and position changes | Battles and position changes |

Historical archive selection does not start Replay Mode. Replay and Live Delay remain shared integration controls rather than independent players inside each card.

## Know the data limits

Public timing, optional F1TV data, historical providers and replay archives have different coverage. Missing information is shown as unavailable rather than guessed. A result can exist without lap progression or telemetry, and a live map still requires usable car-position data.

If something does not appear, confirm that F1 Sensor and the card resource are current, then check the selected installation, module explanation and enabled integration features. Follow [troubleshooting](/help/overview) for the next checks.
