---
id: layout
title: Arrange modules and card width
description: Move and resize modules, use columns and give the F1 Sensor card enough space in Home Assistant.
toc_max_heading_level: 3
---

Choose stacked content, tabs or columns in the [F1 Sensor card editor](/cards/modular). Home Assistant controls the outer card width; the F1 Sensor layout controls modules inside it.

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

## Continue

- [Shared focus and session settings](/cards/shared-options)
- [Conditional module visibility](/cards/shared-options#show-modules-conditionally)
- [Readable layouts and keyboard use](/cards/modular-accessibility)
