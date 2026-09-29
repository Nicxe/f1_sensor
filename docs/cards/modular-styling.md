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
