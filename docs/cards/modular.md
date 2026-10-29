---
id: modular
title: Build your F1 Sensor card
description: Build one Formula 1 view from presets, configurable modules and accessible visual styles.
toc_max_heading_level: 2
---

:::info[Automatic card data]
Add the modules you want to the F1 Sensor card. Its [data is available automatically](/features/card-data-and-sensors), independently of the sensors exposed in Home Assistant. Existing installations keep their sensor choices and start normally after updating; see [Upgrading to automatic card data](/getting-started/required-data-choice).
:::


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

Open **Reusable templates** in the visual editor, enter a name and export the template JSON. On another dashboard or device, paste the JSON or open the saved JSON file and choose **Review template**. The editor shows the current and incoming content before anything changes.

If the template refers to an F1 Sensor installation that does not exist in the current Home Assistant system, you must explicitly choose the replacement installation. Applying a template does not save the dashboard automatically and can be undone during the editing session.

You can add this card several times to one dashboard. Home Assistant controls where the cards sit; the F1 Sensor editor controls the content inside each card.

## Choose the information you want

Use **Add module** to add content, then select the module to edit it. Select fields or columns, reorder them with the move buttons, and open **Module options** for relevant filters and presentation choices. Modules can be moved, duplicated, disabled or removed.

| Content | Available modules |
| --- | --- |
| Planning | Overview, Schedule and Weather. |
| Session | Timing, Minisectors, Race Control, Team Radio (experimental), Tyres, Pit stops and Incidents. |
| Results | Results, Championship, Season progression and Historical archive. |
| Analysis | Lap history chart, Session timeline, Strategy analysis, Battles and position changes, and Track map. |
| Watching later | Replay and Replay telemetry. |
| Officials | FIA documents. |

Data availability depends on the source and session. Adding a module does not create missing observations, enable integration features or guarantee access to every live stream. See [F1TV access and data coverage](/features/f1tv-auth), [historical results](/features/historical-results) and [weekend analysis](/features/weekend-analysis).

Timing can follow a session profile or use your selected columns. Choosing your own timing columns keeps them as a custom selection. A module pinned to a driver keeps that driver when you change the card's general focus.

### Follow push laps

In a **Timing** module, open **Module options** and choose **Push laps** to
follow drivers making a likely fast attempt during practice, qualifying or
sprint qualifying.

| Setting | What you see |
| --- | --- |
| Off | Your usual timing table and sorting. This is the default. |
| Push laps first | Likely push laps appear in a group above the other drivers. The remaining rows keep your selected sorting. |
| Push laps only | Only likely push laps and their briefly retained results appear. Duplicate a Timing module to create a separate compact panel. |

Push laps are ordered by progress around the current lap, with the driver
nearest the next finish-line crossing first. The position column still shows
the driver's classification. Timing and minisector passages provide an
approximate track order; it is not an exact position measurement. Driver and
team selections still apply, and push laps are selected before the row limit.

The card distinguishes a possible push lap from a stronger pace assessment.
Highlighted attempts show only received sectors from the current attempt;
earlier lap times do not fill the remaining sectors.
After a highlighted lap finishes, its result stays visible briefly. A driver
who slows down or enters the pits leaves the active group. If there are no
current attempts, the card explains this separately from missing timing data.

The assessment uses fresh timing progress and comparable recent sector pace.
It cannot establish a driver's intention, fuel load or practice programme.
Early attempts, changing weather and incomplete data can make the assessment
less certain. A push lap does not need a green or purple sector.

Live Delay, No Spoiler and replay apply to the assessment and the displayed
timing together. After seeking or reconnecting, the assessment may need fresh
lap evidence before it can highlight a driver. The push setting does not change
race or sprint-race sorting.

### Show Pit stops

Add **Pit stops** to follow reported pit visits and any timed stop records available for the current session. The module distinguishes counts from details: an available count does not establish the lap or duration of an individual stop.

When a driver has a reported count but no detailed stop records, **Reported pit visits** shows the driver, current status and count separately. In a session with mixed coverage, this summary appears alongside genuine detailed stop rows. **All stops** and **Latest stop** apply to the detailed records; summary rows do not become invented stop events.

Select **Stationary time** for the stationary part of a stop, **Pit lane time** for the full passage through the pit lane and **Estimated lap loss** for a lap-time estimate. Unknown times remain unavailable. A driver's **Current status** describes their present state, not their state at an earlier stop. Driver and team selections still filter the module's data.

An observed live pit-lane duration can provide a detail row with a lap and lane time while stationary time and event time remain unknown. The card explains this partial timing coverage. It does not present a lane duration as a stationary service time.

Live counts can arrive while times are missing, and the module explains this partial coverage. The same selected session, live delay and No Spoiler rules apply to counts and details. Connecting access or loading an archive does not guarantee every field. See [Pit Stops](/entities/pit-stops) for field definitions and [F1TV access and data coverage](/features/f1tv-auth) for the tested account differences.

### Compare practice lap times

In a **Timing** module, add **Gap to fastest lap** (`best_lap_gap`) to your
selected columns. During practice it shows each driver's best lap relative to
the fastest valid best lap of the session, for example `+0.412`. The fastest
time shows `0.000`; drivers without a valid best time show `—`.

The card prefers the gap supplied by live timing. When it is unavailable, it
calculates the difference from the timing source's current valid best times.
Selecting one driver or team still compares against the whole session. Deleted
or corrected best times update the comparison; old observed laps are not used
to restore a removed time.

This optional column is available for practice in live timing and replay. It
does not replace race gaps or the current-part qualifying gap. Existing timing
profiles and saved columns stay unchanged.

### Show Team Radio (experimental)

:::warning Experimental feature

The Team Radio module, audio playback and AI-generated transcript display are
experimental. Their behavior and saved options may change while the feature is
tested in beta. AI transcripts can contain errors, and speaker separation only
distinguishes different voices, not the driver or race engineer.

:::

The module shows the latest Team Radio clip published by Formula 1, or a recent
list of up to ten clips. Each message can include the racing number, driver,
team, team accent, team logo, message time, audio controls and transcript. The
card never starts audio or AI transcription automatically.

To set it up:

1. Enable [F1TV access](/features/f1tv-auth) for live Team Radio, or load a replay
   that contains radio clips.
2. Confirm that `sensor.f1_team_radio` is enabled and has a `clip_url` attribute.
3. Edit an **F1 Sensor** card and choose **Add module** >
   **Team Radio (experimental)**.
4. Select **Latest matching message** or **Recent messages**, then choose the
   fields and module options you want.
5. To show transcripts, follow the experimental Gemini setup in
   [Team Radio](/entities/team-radio), then select that **AI Task entity for
   transcription** under the module options.

For the latest untranscribed clip, the module shows a small **Transcribe** button
beside **Play**. Pressing it manually runs `f1_sensor.transcribe_team_radio` with
the selected AI Task entity and never requests a forced retranscription. The
button is disabled in previews and frozen views. It is not shown for older
history items because the action accepts only the latest published clip. You can
hide the button in the module options.

The audio button uses F1 Sensor's signed local media URL. The Formula 1 access
token is not exposed to the browser. A signed URL can expire; reload the
dashboard after the integration refreshes the clip if playback no longer works.

Choose a driver or team in the card focus controls to show only matching clips.
You can also give the module its own driver or team selection under **Module
options**. **Recent messages** uses the sensor's rolling history, so it can only
show clips that remain in that history.

When a genuinely new clip arrives, **Mark new messages** adds a **New Team
Radio** indicator. Adding or correcting a transcript for the same clip does not
mark it as new. The indicator belongs to the current card instance and clears
when the clip is played; reloading the dashboard starts with the latest clip as
the baseline.

Transcribed turns alternate between the left and right sides of the card to
separate the two anonymous voices without adding visible speaker labels. If the
provider returns a full transcript without usable speaker turns, the card shows
the text as one full-width passage. Driver and team details are taken from the
radio message and can fall back to the Driver List sensor when the clip only
contains a racing number. The module only displays transcript data already
stored on the Team Radio sensor; it never calls the AI provider by itself. You
supply the Gemini API key and are responsible for provider usage and charges.
See [Team Radio](/entities/team-radio) for the complete setup, action YAML,
status attributes and troubleshooting.

### Show minisectors

Minisectors show the status published for each small segment of S1, S2 and S3.
The source does not publish a time for each minisector, so the card does not
calculate or estimate one.

Choose the presentation that fits each module:

| Presentation | Fields to select |
| --- | --- |
| Sector time only | **S1**, **S2** and **S3** in Timing. |
| Sector time with status blocks | **S1 with minisectors**, **S2 with minisectors** and **S3 with minisectors**. |
| Status blocks only | **S1 minisectors**, **S2 minisectors** and **S3 minisectors**, either in Timing or in a separate **Minisectors** module. |

These are ordinary optional fields. You can reorder them, combine them with other
fields and configure each Timing or Minisectors module independently. The separate
Minisectors module starts with Driver and the three status strips. No existing
Timing profile adds minisectors automatically.

Status strips are available for live and replay practice, qualifying, sprint
qualifying, sprint and race sessions when the source has supplied segment data.
Different circuits can have different numbers of blocks. Before the first segment
frame, or when a selected archive has no segment data, the module follows its
**When data is unavailable** setting. Ordinary sector timing remains available
when only minisector data is unavailable.

Set **Recent lap columns** under the Timing module's **Module options** to compare the latest 1–30 completed laps directly in the timing table. The default value is 0, which keeps these columns hidden. Each column is labelled with its lap number; a dash means that no usable time is available for that driver and lap.

### Compare driver details

Open **Driver details** in a Timing module to choose information that appears when you select a driver. These choices are independent of **Content and columns**. The initial detail fields are Best lap, Tyre age and Status. You can choose other Timing fields, including S1, S2 and S3 minisectors, without adding them to the table. Minisector data is requested only while a selected driver needs it.

Select a driver to expand a detail row directly beneath that driver in the Timing table. You can open several drivers at once, and each driver's details stay attached to their row as the order changes. Select a driver again to close that row, or use **Close all driver details** above the table. Your selection is temporary and belongs to this Timing module. It does not change the card's driver focus. Changing session or replay context clears the selection.

Fields already shown as table columns are omitted from the detail panels. **Recent laps in driver details** can include older completed laps without repeating the laps already shown as table columns. If the chosen detail fields and laps add nothing to the table, the driver names are not opening controls. Clear **Show driver details** to disable them explicitly. Missing values remain missing; the card does not estimate minisector times.

Use **Show text below times** to hide the lap number, qualifying part and other supporting text below timing values. Use **Show time status icon** to hide the arrow, dot or square in a timing value. These choices apply independently to Last lap, Best lap, sector times, combined sector and minisector fields, qualifying times and lap comparisons in that Timing module.

Weather, Battles, Strategy and Replay telemetry show a collapsible **About** section by default. To remove it from one module, open that module's **Module options** and clear **Show About section**. Warnings, errors and controls remain visible.

Season progression uses each driver's or team's established Formula 1 color when **Team accents** is enabled. Select a name in the legend or select its line in the chart to hide that series; select the crossed-out legend name to show it again. The data table follows the visible series. This filter is temporary and does not change the saved card configuration; hiding the legend shows every series again.

## Drag modules into place

Open **Modules → Arrange modules** in the card editor. The layout overview
shows each module as a named tile. Choose **Module layout → Columns** and
**Columns in layout** for a layout with two, three or four columns.

- Drag the dotted handle to move a module. A dashed outline shows where it
  will land, and the other tiles move to show the resulting order.
- In **Columns**, drag the arrow handle at a tile's lower right edge to change
  its width. Widths snap to whole columns; following modules wrap to the next
  row when needed.
- Select a tile and use **Width of selected module → Full card width** to keep
  that module across the entire row, even when the column count changes.
- Use **Undo** to reverse a completed drag. Press **Escape** to cancel a drag,
  or release a move outside the overview to leave the order unchanged.

You can also use the existing move buttons and width choices. With a handle
focused, arrow keys move or resize the module; **Home** and **End** select the
first/last position or smallest/largest width. Stacked modules and tabs support
reordering, while width handles are available in **Columns**.

On small screens, scroll the overview sideways to reach all columns. Drag only
from a handle; the rest of the overview supports normal touch scrolling.
Hidden and conditional modules remain available in the overview, while the
finished card respects their visibility rules. Tile heights in the overview
are illustrative; module heights on the dashboard follow their content.

The overview changes module order and width within the card. It does not store
fixed row positions or intentional empty cells. Save the card in Home Assistant
to keep the arrangement on your dashboard.

## Arrange modules in columns

Choose **Columns** under **Card settings → Layout and shared focus → Layout**
to place modules beside each other inside one card. Set **Maximum columns** to
2, 3 or 4, then select each module and set its **Module width** to 1–4 columns
or **Full card width**.

For example, use three columns with Timing at **2 columns**, Track map at
**1 column**, and Race Control at **Full card width**. Timing and Track map share
the first row; Race Control fills the row below them.

Modules follow the order in the module list, from left to right and then onto
the next row. If a module does not fit in the remaining space, it starts on the
next row. Later modules do not move ahead to fill earlier gaps. Hidden modules
do not reserve a column.

### Give the card enough space

1. In Home Assistant's **Sections** view settings, allow enough sections across
   the dashboard.
2. Edit the section containing the card and increase its width to 2, 3 or 4
   section columns.
3. In the card's Home Assistant **Layout** tab, enable **Full width card**.
4. In the F1 Sensor editor, choose the module column count and widths.

Home Assistant controls the outer card width. **Maximum columns** only arranges
content inside the available space; it does not enlarge the dashboard section.
See [Home Assistant card sizing](https://www.home-assistant.io/dashboards/cards/#resizing-a-card).

The card uses fewer columns when space is limited and stacks modules on narrow
cards. A module's width is limited to the columns that fit; **Full card width**
always fills a row. Your saved widths return when the card becomes wider.
Switching to **Stacked modules** or **Tabs** also keeps those width choices.

Use **Arrange modules** to set the order and widths. Home Assistant limits the
width of its built-in preview, so a multi-column card may appear stacked there.
Check the final layout on the dashboard at its actual width. A single section
remains a narrow card even on a wide desktop screen.

<details>
  <summary>Optional YAML example</summary>

```yaml
type: custom:f1-sensor-card
layout: columns
columns: 3
grid_options:
  columns: full
modules:
  - type: timing
    column_span: 2
  - type: map
    column_span: 1
  - type: race_control
    column_span: full
```

Place this card in a section wide enough for three columns. The containing
section's width is configured separately in Home Assistant.

</details>

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
Hidden modules are removed from stacked content, column layouts and the card's tab list.

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

The same purple diamond, green circle and yellow square are used for minisector
status. Yellow means that the provider marked the segment as recorded without a
personal or overall best status. It does not prove that the segment was slower
than the driver's preceding lap. Reset, special, missing and unrecognized source
statuses stay neutral instead of receiving an assumed meaning. Turn on the
Minisectors module's status legend when you want the explanation beside the data.

Minisector status is short-lived dashboard data and can update several times per
second across all drivers. It is delivered only while a visible modular card needs
it and is not exposed as Home Assistant sensor state. This avoids filling Recorder
or sending a complete timing grid for every small change. It also means minisector
status is intended for the F1 Sensor card rather than entity-based automations.

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
