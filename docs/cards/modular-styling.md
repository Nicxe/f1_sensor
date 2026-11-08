---
id: modular-styling
title: Style the F1 Sensor card with custom CSS
description: Use scoped CSS, stable F1 variables and public parts to customize one F1 Sensor card.
toc_max_heading_level: 3
---

The F1 Sensor card includes visual appearance controls for common changes and
scoped custom CSS for advanced layouts. Custom CSS affects only the card where
you add it.

## Start with the visual editor

Use the normal appearance controls before adding CSS:

1. Edit the **F1 Sensor** card.
2. Open **Appearance**.
3. Choose the style, theme, density, surface, typography and colors you want.
4. Open **Custom CSS (advanced)** only for changes that the normal controls do
   not provide.

The preview uses the same CSS as the saved card. Save the dashboard only after
checking the narrow and wide layouts you use.

To place Tyre history and Track map under each other beside a taller Timing
module, choose [**Independent stacks** in the layout controls](/cards/modular#stack-modules-beside-a-taller-module).
Each stack controls its own vertical flow inside the same card, without fixed
module heights or custom CSS. The `--f1-module-gap` variable controls spacing
between stacks and between the modules within each stack.

## Choose a compact presentation

Under **Appearance**, set **Card presentation** to **Compact** to use the
lighter presentation throughout the modular card. **Current** remains the
default. Every module supports the shared setting and its own override.

Select a module and open **Module appearance** to choose **Follow card**,
**Current** or **Compact**. This lets you try the compact presentation in one
module or keep one module in its current presentation while the rest follow
the card. A previously saved **Timing presentation** choice is preserved as
an explicit module choice. Set **Module presentation** to **Follow card** if
you want that module to use the card's setting instead.

The card title and outer spacing are shared by the whole card. A module's
**Current** override preserves that module's content styling.

Compact presentation uses lighter headings, smaller identity and tyre marks,
and quieter table and message decoration. It keeps the selected columns,
filters, source choices and module options. The weather layout, combined
INT/GAP values, timing overview rows and tyre content remain separate choices.
Touch controls keep larger targets even when the surrounding content is compact.
Main module text stays at least 14 px and scales with larger base fonts, so a
smaller Home Assistant font setting does not shrink the data a second time.

Charts, track maps and telemetry keep their reading area, units, legends and
data controls. Their headings and surrounding panels use the same lighter
presentation. Compact presentation does not create missing observations or
change the meaning of source, status or analysis-quality labels.

Race Control keeps the full message visible and lets long text wrap. Open
**Details** beside a message to read its complete date and timestamp. Compact
presentation does not change message order, filters or playback timing.

## Choose a minimal Timing presentation

Select a **Timing** module and use **Module appearance** to choose its
presentation. Open **Module options** for the independent timing choices.
These choices work with the existing styles and density settings under
**Appearance**. You can use compact timing in a comfortable layout, or compact
spacing with the current timing presentation.

| Setting | Default | What it changes |
| --- | --- | --- |
| **Module presentation** | Follow card | Compact uses colored timing text, smaller tyre marks and lighter decoration. It retains your chosen columns, timing symbols or text and the meaning of each color. Existing saved Timing presentation choices remain explicit module choices. |
| **Overview rows with expandable details** | Off | Shows the main race or qualifying values and combines GAP/INT in fewer columns at any card width. Open a driver for the remaining selected fields and recent laps. |
| **GAP and INT columns** | Separate columns | Combined shows INT to the car ahead and GAP to the leader in one column. |
| **Primary value in combined GAP / INT** | INT | Choose which value appears first. This is an editor setting; combined columns and overview rows add no GAP/INT switch to the card. |
| **Show driver status badges** | Off | Adds recorded penalty, investigation and pit or retirement status beside the driver. |
| **Dim retired drivers** | Off | Reduces emphasis on drivers marked as retired. Pit out and stopped remain distinct statuses. |
| **Show tyre age beside the compound** | Off | Combines the compound and its recorded tyre age in one cell. Age numbers line up beside the tyre marks. |
| **Qualifying times to show** | All selected qualifying parts | Follow the current Q/SQ part or choose one part. Saved Q1–Q3/SQ1–SQ3 column choices remain available. |

Existing saved cards keep their current presentation. The separate-column **Show live gap toggle** remains available for those layouts. Compact only changes presentation and retains your chosen columns. Overview rows move secondary fields into expandable details; qualifying focus remains a separate choice.

Under **Content and columns**, choose **Position** for the position alone or **Position + change** to include places gained or lost from the confirmed starting grid for the same race or sprint. Selecting either column replaces the other in the same location. **Position** remains the default. Existing saved position-change choices keep their column location. The same alternatives are available under **Driver details**.

Under **Content and columns**, replace **S1**, **S2** or **S3** with the corresponding **S1 with minisectors**, **S2 with minisectors** or **S3 with minisectors** field. Compact presentation aligns sector times at the top and shows small minisector indicators underneath. Plain sector fields remain the default.

Minisectors show the provider's latest reported status. They are not guaranteed to describe the same lap as the sector time above them. Lap context and the timing legend remain available to explain the readings.

A position-change dash means a matching confirmed grid is unavailable. A penalty badge shows received decisions and keeps the decision context in the driver details. A pit visit alone does not confirm service; an unconfirmed penalty status must not be read as proof that the penalty remains unserved. A stopped car is not automatically retired. Unknown data stays unknown.

## Add custom CSS

1. Open **Appearance** and then **Custom CSS (advanced)**.
2. Enter CSS without a `styles:` prefix.
3. Check the preview.
4. Save the card in Home Assistant.

Use **Reset custom CSS** to remove the entire custom stylesheet. Resetting the
normal appearance controls does not remove custom CSS.

When you edit a dashboard as YAML, use the `styles` property:

```yaml
type: custom:f1-sensor-card
title: Race control
modules:
  - id: main-timing
    type: timing
styles: |
  ha-card {
    --f1-card-radius: 22px;
    --f1-surface: rgba(20, 25, 32, 0.88);
    backdrop-filter: blur(16px);
  }

  f1-module-view[data-module-type="timing"] {
    --f1-cell-padding: 6px 8px;
  }

  f1-module-view[data-module-type="timing"]::part(module-title) {
    color: var(--f1-accent);
    text-transform: uppercase;
  }
```

## Use the supported variables

Set variables on `ha-card` to style the complete card. Set them on one
`f1-module-view` to change only that module.

| Variable | Controls |
| --- | --- |
| `--f1-card-radius` | Outer card corner radius |
| `--f1-card-padding` | Outer card spacing |
| `--f1-minimal-padding` | Outer spacing for the Minimal style |
| `--f1-module-gap` | Space between modules |
| `--f1-section-space` | Space between headings and sections |
| `--f1-cell-padding` | Timing and result table cell spacing |
| `--f1-item-padding` | Compact list item spacing |
| `--f1-table-radius` | Table frame corner radius |
| `--f1-surface` | Main card and control background |
| `--f1-panel` | Secondary panels and table headings |
| `--f1-row-alternate` | Alternating table row background |
| `--f1-text` | Primary text color |
| `--f1-muted` | Secondary text color |
| `--f1-border` | Strong borders |
| `--f1-divider` | Dividers and subtle borders |
| `--f1-accent` | Decorative card accent |
| `--f1-focus` | Keyboard focus outline and links |
| `--f1-hover` | Hover background for controls |
| `--f1-heading-font` | Module heading font family |
| `--f1-heading-transform` | Module heading text transformation |
| `--f1-module-heading-size` | Module heading size |
| `--f1-numerals` | Numeric font variant, such as `tabular-nums` |

Timing status colors remain separate from decorative styling. Change them under
**Accessibility and timing colors** so their text and shape equivalents remain
available.

## Target one module

Every module exposes its saved type and id:

```css
f1-module-view[data-module-type="weather"] {
  --f1-panel: rgba(80, 130, 180, 0.12);
}

f1-module-view[data-module-id="main-timing"] {
  --f1-table-radius: 14px;
}
```

Use `data-module-type` for every module of one type. Use `data-module-id` for one
specific saved module. Module ids stay with the module when you reorder it.

## Style public parts

Module content is inside a Shadow DOM. Use the following public parts instead of
depending on private class names:

| Part | Content |
| --- | --- |
| `module-content` | Complete module content |
| `module-header` | Module heading row |
| `module-title` | Module title |
| `module-badge` | Session or status badge beside the title |
| `empty-state` | Missing or unavailable data message |
| `table-container` | Scrollable table frame |
| `table` | Timing or result table |
| `table-header` | Table heading group |
| `table-row` | Table row |
| `table-cell` | Table heading or value cell |
| `driver-detail-row` | Expanded Timing table row beneath a selected driver |
| `driver-detail` | Content inside one expanded driver's row |
| `result-grid` | Result grid instead of a table |
| `result-card` | One result in a result grid |
| `metrics` | Overview metric collection |
| `metric` | One overview metric |
| `controls` | Module-specific controls |
| `map` | Track Map component |
| `chart` | Progression or lap chart component |
| `telemetry` | Replay telemetry component |

For example:

```css
f1-module-view::part(module-header) {
  border-bottom: 1px solid var(--f1-divider);
  padding-bottom: 8px;
}

f1-module-view[data-module-type="timing"]::part(table-row) {
  font-size: 0.92rem;
}
```

The card shell also exposes named elements including `card`, `header`, `title`,
`card-title`, `toolbar`, `tabs`, `modules`, `viewing-controls` and `empty-state`.
Inside the custom CSS editor, target these with normal selectors such as
`ha-card`, `[part~="toolbar"]` or `[part~="tabs"]`.

## Understand the boundaries

:::warning
Custom CSS can hide controls, reduce contrast or create layouts that do not fit
every screen. Check keyboard focus, light and dark themes, narrow layouts and the
accessibility settings you use.
:::

The custom stylesheet is limited to 32,768 characters and stays inside this
card. JavaScript templates, `@import` rules and `url()` resources are not
supported. Use the normal image, logo and typography settings instead of loading
remote resources from CSS.

The documented variables, module data attributes and parts are the supported
styling interface. Other internal class names can change between versions.

See [card accessibility](/cards/modular-accessibility) for contrast, motion,
keyboard and screen-reader guidance.
