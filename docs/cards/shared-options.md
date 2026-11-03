---
id: shared-options
title: Configure the F1 Sensor card
description: Understand installation selection, layout, focus, sessions, appearance and saved card behavior.
---

Use the visual editor to configure the **F1 Sensor** card. The editor writes one `custom:f1-sensor-card` configuration containing the card's modules, shared context and appearance.

## Select an F1 Sensor installation

With one integration entry, the card discovers that installation and its entities automatically. With several entries, select the intended installation at the top of the editor.

The saved `f1_entry_id` identifies an integration setup, not an entity. Do not paste a sensor entity ID into this field.

```yaml
type: custom:f1-sensor-card
f1_entry_id: 01JEXAMPLEENTRYID
```

The card resolves renamed entity IDs and entry suffixes automatically. Modules then use the matching entities from the selected installation.

## Choose layout and shared focus

Choose **Stack** to show modules one after another, **Tabs** for one module at a time, or **Columns** to place modules side by side. See [module layout and card width](/cards/layout) for sizing and keyboard controls. The card can also keep a shared driver or team focus so related modules follow the same selection.

The driver focus menu shows compact three-letter driver codes. Clear **Show driver focus menu** to hide it from the card. The menu is shown by default, and hiding it does not remove a saved default driver or a module's own driver selection.

For several cards on the same dashboard view, assign the same context group to share temporary focus. You can also share temporary session selection. Group state is local to that dashboard view, browser connection and F1 Sensor installation; it does not change the integration's Favorite Driver selector, Replay Mode, Live Delay or automations.

Pinned cards and independently configured modules keep their own selection instead of following the group. The group cannot operate replay, Live Delay or automations. Temporary group choices are not synchronized personal preferences across devices.

## Follow or pin a session

Open **Layout and shared focus** to choose whether the card follows the automatic source, the live session or the loaded replay. When the integration exposes a complete stable identity, the editor also offers **Pin current live session** or **Pin loaded replay**. An Archive module can pin the event and session selected from its historical catalogue.

| Source | Behavior |
| --- | --- |
| **Automatic source** | Uses the most relevant current source |
| **Follow live session** | Follows the active live session |
| **Follow loaded replay** | Follows the session currently loaded in Replay Mode |
| A pinned live, replay or archive identity | Keeps the selected session instead of silently following another one |

A module can inherit the card, follow a source independently or keep its own pinned session. Module selection has priority over a card lock; a locked card has priority over a temporary group selection. If a saved identity is not available, the card keeps it and explains the mismatch. It never silently shows the current session instead. Pinning a replay does not load or start it, and pinning live data does not start another live source. Pinning changes display context without changing shared Replay Mode.

Under **Module options**, use **Show in session phases** to choose **Before**, **Active or interrupted**, **Finished** and **Unknown**. A module hidden by the current phase remains saved in the editor. Red-flag and other non-final interruptions count as active; only an explicit end state counts as finished.

## Control unavailable data

<span id="times-and-saved-data" />

Clock times follow your Home Assistant profile's **Time format**: 12-hour, 24-hour, language or system locale. This applies to schedules, Race Control messages, document publication times, map observations, calibration and frozen views. Your profile also controls the time zone, unless you explicitly choose circuit time for a schedule.

Cards keep the focus on the selected Formula 1 content. They do not show automatic update timestamps, elapsed update ages or provider credit lines. Event and session times remain available as content fields.

Under **Module options**, choose **When data is unavailable**:

| Choice | Behavior |
| --- | --- |
| Show explanation | Replace unavailable content with an explanation and keep the saved configuration. |
| Keep saved data | Keep available saved content with a notice when updates are interrupted. |
| Hide module | Hide unavailable content until it can be shown again. The module stays in your configuration. |

When the browser loses its Home Assistant connection, the card shows a clear disconnected notice. Retained values are reading snapshots, not proof of a current live state. Replay, archive and telemetry controls show their own connection state. Spoiler protection still takes precedence over retained or frozen content.

Entity-backed modules can keep their last captured content when a source becomes unavailable, even if its attributes disappear. Filters continue to apply to that saved content. A different installation, session, replay seek, Live Delay or spoiler state clears these snapshots; they are also released when the card is removed or the page reloads. An available empty result replaces the saved result instead of reviving older rows.

**Freeze view** captures a reading snapshot in this card. Its values remain at the capture point, identified by the reading-snapshot notice. **Resume** returns to current data. Freezing does not pause backend replay, change Live Delay or change automations. The button is shown by default; clear **Show Freeze view button** under **Layout and shared focus** if you do not want it on a card.

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

## Choose appearance

Open **Appearance** to choose the style first, then adjust these controls. The current English editor labels are:

| Setting | Choices |
| --- | --- |
| **Style** | F1, Home Assistant, Minimal |
| **Theme** | Automatic, Light, Dark |
| **Density** | Compact, Normal, Spacious |
| **Heading font** | Follow style, F1 inspired, Home Assistant |
| **Numerals** | Aligned timing numerals, Home Assistant |
| **Surface** | Follow style, Defined frame, Soft corners and alternating rows, Flat, without a frame |
| **Decorative accent** | Follow style, Neutral, F1, Favorite team, Custom color |
| **Logo variant** | Automatic, Color, Monochrome, White |
| **Logo size** | Small, Normal, Large |
| **Tyre appearance** | Colored ring and letter, Tyre image and letter, Compound name, Tyre image and name |

These styles use the same content and filters. For a simple card, choose a preset and adjust only style and density. The additional groups control titles, surfaces, accents, logos, flags, team colors, typography and tyre presentation. A neutral or team accent changes decoration; timing status has its own color settings.

Open **Custom CSS (advanced)** when the normal appearance controls do not cover
your layout. The CSS applies only to that card and has a live preview. Use the
documented variables and public parts in [custom CSS styling](/cards/modular-styling)
instead of relying on private class names.

Module titles and table headers have separate visibility options under **Module appearance**. Hidden headings and column labels remain available to assistive technology. Chart data tables retain their labels.

The card-level driver menu uses three-letter driver codes to stay compact. Open **Layout and shared focus** and clear **Show driver focus menu** if you do not want the menu on that card. A saved default driver or module-level driver selection continues to apply when the menu is hidden.

:::tip[Keep the important fields first]
Put the driver and the time or status you follow most near the start of a table. A small number of useful columns is easier to read on a phone than a full timing sheet.
:::

### Module-specific presentation

Weather, Battles, Strategy and Replay telemetry show a collapsible **About** section by default. To remove it from one module, open that module's **Module options** and clear **Show About section**. Warnings, errors and controls remain visible.

Season progression uses each driver's or team's established Formula 1 color when **Team accents** is enabled. Select a name in the legend or select its line in the chart to hide that series; select the crossed-out legend name to show it again. The data table follows the visible series. This filter is temporary and does not change the saved card configuration; hiding the legend shows every series again.

## Keep timing meaning visible

Timing states pair color with a shape or text signal. Purple with a diamond means overall fastest, green with a circle means personal best, and yellow with a square means a recorded time. Lap deltas and position changes use separate arrows and references.

In a Timing module, set **Recent lap columns** to a value from 1 to 30 to show that many latest completed laps as labelled comparison columns. Keep it at 0 to hide the extra columns.

Timing and Minisectors modules can each show status-only strips or the existing
S1, S2 and S3 times combined with their strips. Each module keeps its own fields,
order, driver or team focus, session source and visibility conditions. Minisector
blocks contain provider status only; they do not contain or estimate a time.

Use **Accessibility and timing colors** to change the palette, enable high contrast, reduce motion and choose shape, text or both. See [card accessibility](/cards/modular-accessibility) for the complete guidance.

Track Map interpolates consecutive driver positions for smoother live and replay movement. Reduced motion, stale positions, session changes and unusually large jumps are shown without animation.

## Use spoilers, Live Delay and replay controls

Under **Layout and shared focus**, enable **Show Live Delay and global spoiler controls** to add the optional **Viewing settings** panel.

- Manual Live Delay changes require **Apply live delay**. They affect the selected installation's live delivery and automations.
- **Calibrate with TV** guides you through choosing a reference, waiting and explicitly matching the moment on TV. Cancel keeps the existing delay. See [Live Delay](/features/live-delay).
- Global spoiler protection affects all F1 Sensor installations. Turning it off includes a review. Local hiding cannot override it.
- Archive selections retrieve history. They do not load or start a replay.
- Replay actions control the selected installation's shared replay. Separate cards are not independent replay players.

Demo previews cannot issue integration actions. A saved card's local driver focus and reading snapshot also leave integration settings unchanged.

## Export or reuse a configuration

**Export and import** transfers the complete card configuration as JSON. Import replaces the editor draft and can be undone before saving.

### Reuse your own template

Open **Reusable templates** in the visual editor, enter a name and export the template JSON. On another dashboard or device, paste the JSON or open the saved JSON file and choose **Review template**. The editor shows the current and incoming content before anything changes.

If the template refers to an F1 Sensor installation that does not exist in the current Home Assistant system, you must explicitly choose the replacement installation. Applying a template does not save the dashboard automatically and can be undone during the editing session.

You can add this card several times to one dashboard. Home Assistant controls where the cards sit; the F1 Sensor editor controls the content inside each card.


For direct YAML editing, keep the card type and configuration version:

```yaml
type: custom:f1-sensor-card
version: 3
title: Race weekend
layout: stack
modules:
  - type: overview
    id: overview-1
  - type: calendar
    id: calendar-1
```

Prefer the visual editor for module fields and options because it validates the available choices.

### Save and migrate

Save permanent choices in the Home Assistant card editor.

Converted deprecated configurations retain a recoverable original and show differences for review. Treat conversion as a reviewed starting point and keep a dashboard backup until the new card covers the behavior you use.

Follow [the migration guide](/cards/modular-migration) to convert one card at a time, interpret the review and restore the exact stored deprecated configuration when needed.


## Related

- [Build the card](/cards/modular)
- [Move from a deprecated card](/cards/modular-migration)
- [Card installation and loading checks](/cards/installation)
