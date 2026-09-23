---
id: modular-accessibility
title: Make the F1 Sensor card easier to read and operate
description: Configure readable timing signals, keyboard access, contrast, motion and compact layouts in the F1 Sensor card.
toc_max_heading_level: 2
---

The F1 Sensor card pairs timing colors with symbols or text and keeps important
labels available to assistive technology. Use the visual editor to adapt the card
to your display and input method.

## Start with a readable layout

1. Choose a preset close to the information you need.
2. Put the most important fields first under **Content and columns**.
3. Remove secondary columns instead of relying on horizontal scrolling.
4. Open **Appearance** and choose a comfortable information density.
5. Check the result in both the light and dark Home Assistant themes you use.

On a phone, prefer a focused timing card over a full desktop-width table. A
module hidden for a session phase stays in the saved configuration and returns
when that phase applies.

## Keep meaning independent of color

Open **Accessibility and timing colors** to adjust the palette and accompanying
signals. The default states use both color and a distinct shape:

| State | Additional signal |
| --- | --- |
| Overall fastest | Diamond |
| Personal best | Circle |
| Recorded time | Square |
| Faster lap delta | Down triangle and negative value |
| Slower lap delta | Up triangle and positive value |

Do not choose custom colors that are difficult to distinguish in your active
theme. Keep symbols or text enabled when timing state matters. Position arrows
describe a position comparison; they do not describe whether a lap was faster.

## Use a keyboard or switch input

Use <kbd>Tab</kbd> and <kbd>Shift</kbd>+<kbd>Tab</kbd> to move through interactive
controls. Use <kbd>Enter</kbd> or <kbd>Space</kbd> to activate a focused button,
toggle or disclosure. The editor exposes its tabs, module controls and reorder
buttons in keyboard order.

Hidden visual module headings and table headers retain accessible names. Charts
provide a data-table alternative so their values are not available only as a
graphic.

## Reduce motion and increase contrast

The card follows the browser or operating system preference for reduced motion.
Home Assistant forced-color and high-contrast modes keep controls and focus
indicators visible. Enlarging browser text can increase card height; verify that
the surrounding dashboard section allows the card to grow rather than clipping
it.

## Check your own devices

Before relying on the card during a live session, test the saved dashboard with
the screen reader, zoom level, theme and input method you normally use. Also test
portrait and landscape orientation in the Companion App. Report the exact device,
operating system, Home Assistant version, theme, card module and expected result
when something is not usable.

See [the F1 Sensor card guide](/cards/modular) for timing semantics and [reporting
an issue](/help/contact) for support channels.
