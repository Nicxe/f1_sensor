---
id: modular
title: Build your F1 Sensor card
description: Build one Formula 1 view from presets, configurable modules and accessible visual styles.
toc_max_heading_level: 2
---

Build a compact weekend overview or a detailed session view with the **F1 Sensor** card. Choose your content first, then adjust its appearance in the visual editor.

New cards start with the empty **Build your own** template. The template chooser is open so you can select a preset or add your first module. Existing saved cards keep their modules.

## Start with a preset

1. Edit your Home Assistant dashboard and choose **Add card**.
2. Select **F1 Sensor**. If you have several F1 Sensor installations, choose which one the card follows.
3. Choose a preset from the table below.
4. Review the preview and save the card.

| Preset | Initial content |
| --- | --- |
| Race weekend | Overview, weekend schedule and weather. |
| Weather comparison | Current conditions and race-start forecast. |
| Follow the session | Session overview, timing and Race Control. |
| My driver | Session overview, driver timing with recent laps, and Race Control. Choose a driver in the card or editor. |
| Results and championship | Results, championship standings and points progression. |
| Build your own | An empty card ready for your first module. |

A preset is a starting point. You can change its modules after selecting it. Selecting another preset shows a review before replacing the current content; changing the visual style keeps your content choices.

## Reuse your own template

Open **Reusable templates** in the visual editor, enter a name and export the template JSON. On another dashboard or device, paste the JSON or open the saved JSON file and choose **Review template**. The editor shows the current and incoming content before anything changes.

If the template refers to an F1 Sensor installation that does not exist in the current Home Assistant system, you must explicitly choose the replacement installation. Applying a template does not save the dashboard automatically and can be undone during the editing session.

You can add this card several times to one dashboard. Home Assistant controls where the cards sit; the F1 Sensor editor controls the content inside each card.

## Choose the information you want

Use **Add module** to add content, then select the module to edit it. Select fields or columns, reorder them with the move buttons, and open **Module options** for relevant filters and presentation choices. Modules can be moved, duplicated, disabled or removed.

| Content | Available modules |
| --- | --- |
| Planning | Overview, Schedule and Weather. |
| Session | Timing, Race Control, Tyres, Pit stops and Incidents. |
| Results | Results, Championship, Season progression and Historical archive. |
| Analysis | Lap history chart, Session timeline, Strategy analysis, Battles and position changes, and Track map. |
| Watching later | Replay and Replay telemetry. |
| Officials | FIA documents. |

Data availability depends on the source and session. Adding a module does not create missing observations, enable integration features or guarantee access to every live stream. See [F1TV access and data coverage](/features/f1tv-auth), [historical results](/features/historical-results) and [weekend analysis](/features/weekend-analysis).

Timing can follow a session profile or use your selected columns. Choosing your own timing columns keeps them as a custom selection. A module pinned to a driver keeps that driver when you change the card's general focus.

Set **Recent lap columns** under the Timing module's **Module options** to compare the latest 1–30 completed laps directly in the timing table. The default value is 0, which keeps these columns hidden. Each column is labelled with its lap number; a dash means that no usable time is available for that driver and lap.

Weather, Battles, Strategy and Replay telemetry show a collapsible **About** section by default. To remove it from one module, open that module's **Module options** and clear **Show About section**. Warnings, errors and controls remain visible.

Season progression uses each driver's or team's established Formula 1 color when **Team accents** is enabled. Select a name in the legend or select its line in the chart to hide that series; select the crossed-out legend name to show it again. The data table follows the visible series. This filter is temporary and does not change the saved card configuration; hiding the legend shows every series again.

## Choose and lock a session

Open **Layout and shared focus** to choose whether the card follows the automatic source, the live session or the loaded replay. When the integration exposes a complete stable identity, the editor also offers **Pin current live session** or **Pin loaded replay**. An Archive module can pin the event and session selected from its historical catalogue.

A module can inherit the card, follow a source independently or keep its own pinned session. Module selection has priority over a card lock; a locked card has priority over a temporary group selection. If a saved identity is not available, the card keeps it and explains the mismatch. It never silently shows the current session instead. Pinning a replay does not load or start it, and pinning live data does not start another live source.

Under **Module options**, use **Show in session phases** to choose **Before**, **Active or interrupted**, **Finished** and **Unknown**. A module hidden by the current phase remains saved in the editor. Red-flag and other non-final interruptions count as active; only an explicit end state counts as finished.

## Show modules conditionally

Open a module's **Visibility conditions** to show it only when the current Home
Assistant state matches your choices. You can add conditions for an entity state,
a numeric value, screen size, user, location or time. You can also group
conditions with **All conditions (AND)**, **Any condition (OR)** or **Invert
conditions (NOT)**.

Every condition at the top level must match. These conditions are combined with
the module's selected session phases. The editor shows **Visible now**, **Hidden
now** or **Always visible**, while the saved module remains available for editing.
Hidden modules are removed from stacked content and from the card's tab list.

For example, you can show Timing only when a helper is on and the dashboard is
open on a tablet or desktop:

```yaml
type: custom:f1-sensor-card
version: 3
modules:
  - type: timing
    visibility:
      - condition: state
        entity: input_boolean.show_f1_timing
        state: "on"
      - condition: screen
        media_query: "(min-width: 768px)"
```

Use Home Assistant's card-level **Visibility** tab when you want to hide the
entire F1 Sensor card. Module visibility controls only the content inside the
card. If every module is hidden, a Sections dashboard may still reserve the
card's configured grid area.

:::info
Visibility changes presentation, not permissions. A user who has access to an
entity in Home Assistant may still access it even when a module is hidden.
:::

## Make the card your own

Open **Appearance** to choose a style, light/dark behavior and information density. **F1**, **Home Assistant** and **Minimal** use the same content and filters.

For a simple card, choose a preset and adjust only the style and density. The additional groups let you change titles, surfaces, accents, logos, flags, team colors, typography and tyre presentation. A neutral or team accent changes decoration; timing status has its own color settings.

Open **Custom CSS (advanced)** when the normal appearance controls do not cover
your layout. The CSS applies only to that card and has a live preview. Use the
documented variables and public parts in [custom CSS styling](/cards/modular-styling)
instead of relying on private class names.

Module titles and table headers have separate visibility options under **Module appearance**. Hidden headings and column labels remain available to assistive technology. Chart data tables retain their labels.

The card-level driver menu uses three-letter driver codes to stay compact. Open **Layout and shared focus** and clear **Show driver focus menu** if you do not want the menu on that card. A saved default driver or module-level driver selection continues to apply when the menu is hidden.

:::tip Keep the important fields first
Put the driver and the time or status you follow most near the start of a table. A small number of useful columns is easier to read on a phone than a full timing sheet.
:::

## Read timing colors and symbols

Open **Accessibility and timing colors** to adjust timing colors and the accompanying signals. Color is only one part of the meaning.

| Signal | Meaning |
| --- | --- |
| Purple and diamond | Overall fastest. |
| Green and circle | Personal best. |
| Yellow and square | A recorded time. Yellow does not mean slower than the previous lap. |
| Neutral previous-lap value | The value belongs to the labelled earlier lap. |
| Down triangle with a negative lap delta | A faster lap than the stated reference lap. |
| Up triangle with a positive lap delta | A slower lap than the stated reference lap. |
| Position arrow | A position change against its stated comparison, not a change in lap time. |

The default sector view keeps values from the same lap together. The **Latest sectors, with lap labels** option can mix the most recently supplied sectors; the individual lap labels matter in that view. A theoretical lap is the sum of personal-best sectors and may combine different laps.

Custom colors can help you distinguish the timing states. Keep symbols or text available and check both light and dark themes. High contrast, reduced motion and readable text alternatives are part of the card's controls; automated checks alone do not establish compatibility with every screen reader or device.

Track Map moves driver markers smoothly between consecutive live or replay positions. It moves directly to the new position when reduced motion is enabled, the session changes, the position is stale or the new sample is too far from the previous one to be a continuous movement.

See [card accessibility](/cards/modular-accessibility) for focused keyboard, contrast and motion guidance.

## Times and saved data

Clock times follow your Home Assistant profile's **Time format**: 12-hour, 24-hour, language or system locale. This applies to schedules, Race Control messages, document publication times, map observations, calibration and frozen views. Your profile also controls the time zone, unless you explicitly choose circuit time for a schedule.

Cards keep the focus on the selected Formula 1 content. They do not show automatic update timestamps, elapsed update ages or provider credit lines. Event and session times remain available as content fields.

Under **Module options**, choose **When data is unavailable**:

| Choice | Behavior |
| --- | --- |
| Show explanation | Replace unavailable content with an explanation and keep the saved configuration. |
| Keep saved data | Keep available saved content with a notice when updates are interrupted. |
| Hide module | Hide unavailable content until it can be shown again. The module stays in your configuration. |

When the browser loses its Home Assistant connection, the card shows a clear disconnected notice. Retained values are saved snapshots. Replay, archive and telemetry controls show their own connection state. Spoiler protection still takes precedence over retained or frozen content.

Entity-backed modules can keep their last captured content when a source becomes unavailable, even if its attributes disappear. Filters continue to apply to that saved content. A different installation, session, replay seek, Live Delay or spoiler state clears these snapshots; they are also released when the card is removed or the page reloads. An available empty result replaces the saved result instead of reviving older rows.

**Freeze view** captures a reading snapshot in this card. Its values remain at the capture point, identified by the reading-snapshot notice. **Resume** returns to current data. Freezing does not pause backend replay, change Live Delay or change automations. The button is shown by default; clear **Show Freeze view button** under **Layout and shared focus** if you do not want it on a card.

## Live Delay, spoilers and replay

Under **Layout and shared focus**, enable **Show Live Delay and global spoiler controls** to add the optional **Viewing settings** panel.

- Manual Live Delay changes require **Apply live delay**. They affect the selected installation's live delivery and automations.
- **Calibrate with TV** guides you through choosing a reference, waiting and explicitly matching the moment on TV. Cancel keeps the existing delay. See [Live Delay](/features/live-delay).
- Global spoiler protection affects all F1 Sensor installations. Turning it off includes a review. Local hiding cannot override it.
- Archive selections retrieve history. They do not load or start a replay.
- Replay actions control the selected installation's shared replay. Separate cards are not independent replay players.

Demo previews cannot issue integration actions. A saved card's local driver focus and reading snapshot also leave integration settings unchanged.

## Save, reuse and migrate

Save permanent choices in the Home Assistant card editor. **Export and import** copies the complete card configuration as JSON; importing replaces the editor draft and can be undone before saving.

Converted deprecated configurations retain a recoverable original and show differences for review. Treat conversion as a reviewed starting point and keep a dashboard backup until the new card covers the behavior you use.

Follow [the migration guide](/cards/modular-migration) to convert one card at a time, interpret the review and restore the exact stored deprecated configuration when needed.

Shared driver focus is scoped to the configured group within the same dashboard view and F1 installation. You can also explicitly share temporary session selection; pinned cards keep their own session, and the group cannot operate replay, Live Delay or automations. Temporary group changes are local to that browser connection; they are not synchronized personal preferences across devices.
