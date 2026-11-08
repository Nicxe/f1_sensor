---
id: modular
title: Build your F1 Sensor card
description: Build one Formula 1 view from presets, configurable modules and accessible visual styles.
toc_max_heading_level: 2
---

Build a compact weekend overview or a detailed session view with the **F1 Sensor** card. Choose your content first, then adjust its appearance in the visual editor.

The card gets [data automatically for its modules](/features/card-data-and-sensors). Keep sensors enabled for automations, templates, standard cards or older F1 cards; they do not limit modular card data. Live enablement, account access and session availability still apply.

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

## Preview your card

Home Assistant provides the card's only preview. At the top of it, **Preview data**
starts with **Actual data** from your installation. Choose **Sample data** to try
practice, qualifying, sprint, race, replay or missing-data scenarios, even when no
session is running. Sample data is clearly marked **DEMO**.

This choice only affects the preview and stays selected while you edit the card.
It is never saved in your dashboard configuration. Preview controls cannot change
integration settings or start replay playback. On small screens, use Home
Assistant's preview toggle to show the same preview.

## Reuse your own template

[Transfer a reusable template](/cards/shared-options#reuse-your-own-template) as JSON. Review it in the editor before saving the dashboard.

## Choose the information you want

Use **Add module** to add content, then select the module to edit it. Select fields or columns, reorder them with the move buttons, and open **Module options** for relevant filters and presentation choices. Modules can be moved, duplicated, disabled or removed.

| Content | Available modules |
| --- | --- |
| Planning | Overview, Schedule and Weather. |
| Session | [Timing](/cards/timing), [Minisectors](/cards/minisectors), Race Control, [Team Radio (experimental)](/cards/team-radio), Tyres, [Pit stops](/cards/pit-stops) and Incidents. |
| Results | Results, Championship, Season progression and Historical archive. |
| Analysis | Lap history chart, Session timeline, Strategy analysis, Battles and position changes, and Track map. |
| Watching later | Replay and Replay telemetry. |
| Officials | FIA documents. |

Data availability depends on the source and session. Adding a module does not create missing observations, enable integration features or guarantee access to every live stream. See [F1TV access and data coverage](/features/f1tv-auth), [historical results](/features/historical-results) and [weekend analysis](/features/weekend-analysis).

Use the focused module guides below for options, examples, waiting states and data interpretation. Shared card settings have their own [configuration reference](/cards/shared-options).

### Choose a minimal Timing view

In **Timing → Module appearance**, set **Module presentation** to **Compact** for colored timing text, smaller tyre marks and lighter table decoration. Choose **Follow card** to use **Card presentation** from **Appearance**. The same card setting supports every module, including results, schedules, analysis, charts and maps. Existing cards keep their current presentation and columns.

Under **Module options**, turn on **Use overview rows on narrow cards** for a concise view with the remaining selected fields available when you open a driver.

Choose **Combined column** to show INT and GAP together. Set the primary value in the editor when building the layout; the combined and narrow views do not add a GAP/INT switch to the card. **Qualifying times to show** can follow the current Q/SQ part or show a chosen part while keeping your saved column choices.

Under **Content and columns**, choose **Position** for the position alone or **Position + change** for the position and places gained or lost from the confirmed starting grid for the same session. The default is **Position**. Driver status badges, dimmed retired rows and tyre age beside the compound remain separate choices. Penalty badges follow recorded decisions; a pit visit alone does not prove that a penalty was served. See [compact Timing options](/cards/modular-styling#choose-a-minimal-timing-presentation) for the settings and defaults.

### Follow push laps

[Follow push laps](/cards/timing#follow-push-laps) to group or filter likely attempts during practice and qualifying.

### Compare a push lap with the best qualifying lap

[Compare with the best qualifying lap](/cards/timing#compare-a-push-lap-with-the-best-qualifying-lap), using one real reference lap from the current part.

### Show Pit stops

[Configure Pit stops](/cards/pit-stops) and keep reported visits separate from timed stop records.

### Show tyre history

Add **Tyres**, open **Module options** and choose **History** under **Tyre content**. Each driver gets a horizontal timeline with one segment per known stint. Completed segments remain visible after a tyre change. All drivers share the same session-lap scale; each driver's bar grows with their own completed laps.

Select a driver to expand all their known stints directly below the row. Select the same driver again to close the details. The table shows the compound, race-lap range, laps driven in that stint, tyre age before fitting and total tyre age. For a completed stint, the total is the age at removal; for the current stint, it is the latest reported age.

A used tyre can start with earlier mileage. For example, **14** laps in this stint plus **3** before fitting means **17** total. Those earlier three laps do not lengthen the segment on the session-lap timeline. Compound letters accompany the colours, and used tyres have a pattern as well.

**Show compound legend** controls the explanation below the timeline and is on by default. Turn it off to remove the complete legend row. In YAML, configure the module as follows:

```yaml
type: custom:f1-sensor-card
modules:
  - id: tyre-history
    type: tyres
    options:
      content: history
      show_legend: true
```

:::info
The view shows known history for the selected session. Connecting late, restarting the integration or receiving an incomplete source snapshot can leave earlier stints or lap boundaries unavailable. Unknown values appear as **—**, not zero. **0** before fitting means a known starting age of zero laps. See [Current Tyres](/entities/current-tyres) for the underlying fields.
:::

During replay, seeking restores the recorded history up to the selected position. Seeking backwards removes later stints from the view. When an older replay cache is loaded, the integration rebuilds its history index from the cached recording; it can only restore observations present in that recording. If **Freeze view** is active, choose **Resume** after seeking to display the history for the new position.

### Compare practice lap times

[Compare practice best laps](/cards/timing#compare-practice-lap-times) against the fastest valid session best.

### Show Team Radio (experimental)

[Set up Team Radio](/cards/team-radio) for experimental clip playback, driver filters and optional manual transcription. Audio and transcription never start automatically.

### Show minisectors

[Add minisector status](/cards/minisectors) beside sector times or in a separate module. The source does not provide a time for each minisector.

### Show session rain risk

Select **Session rain risk** in an **Overview** or **Weather** module's fields. The value shows Race Control's published percentage for the identified session, such as **30 % · Practice 3**. It remains hidden when no matching assessment is available and shows a published **0 %**.

This field is separate from the weather provider's forecast probability and the track's rain-detection indicator. Open its details for the original message and timestamp. See [Session Rain Risk](/entities/session-rain-risk) for availability and session behavior.

### Compare driver details

[Choose driver details and recent laps](/cards/timing#compare-driver-details) without adding every field to the timing table.

## Drag modules into place

[Move and resize modules](/cards/layout#drag-modules-into-place) with drag handles, move buttons or keyboard controls.

## Arrange modules in columns

<span id="give-the-card-enough-space" />

[Arrange columns and card width](/cards/layout#arrange-modules-in-columns), including [giving the card enough space](/cards/layout#give-the-card-enough-space). Home Assistant sets the outer width; module columns fit inside it.

## Choose and lock a session

[Choose or pin a session](/cards/shared-options#follow-or-pin-a-session). A pin keeps an identity; it does not load a replay or start another source.

## Show modules conditionally

[Set module visibility conditions](/cards/shared-options#show-modules-conditionally) for entities, values, screen size, users, location or time. Visibility changes presentation, not permissions.

## Make the card your own

[Configure appearance](/cards/shared-options#choose-appearance), from styles and density to headings, focus menus and [custom CSS](/cards/modular-styling).

## Read timing colors and symbols

[Read the complete timing legend](/cards/timing#read-timing-colors-and-symbols). Color is paired with shape or text; a yellow recorded time does not mean slower than the previous lap.

## Times and saved data

[Understand clock times, missing data and Freeze view](/cards/shared-options#control-unavailable-data). A frozen reading does not pause replay or change automations.

## Live Delay, spoilers and replay

[Use viewing controls](/cards/shared-options#use-spoilers-live-delay-and-replay-controls). Replay and Live Delay affect the selected installation; global spoiler protection affects all entries.

## Save, reuse and migrate

[Save, export or reuse the configuration](/cards/shared-options#export-or-reuse-a-configuration). Use the [migration review](/cards/modular-migration) to convert one deprecated card at a time and retain its original.
