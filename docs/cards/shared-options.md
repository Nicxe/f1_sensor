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

Choose **Stack** to show modules one after another or **Tabs** to show one module at a time. The card can also keep a shared driver or team focus so related modules follow the same selection.

The driver focus menu shows compact three-letter driver codes. Clear **Show driver focus menu** to hide it from the card. The menu is shown by default, and hiding it does not remove a saved default driver or a module's own driver selection.

For several cards on the same dashboard view, assign the same context group to share temporary focus. You can also share temporary session selection. Group state is local to that dashboard view, browser connection and F1 Sensor installation; it does not change the integration's Favorite Driver selector, Replay Mode, Live Delay or automations.

Pinned cards and independently configured modules keep their own selection instead of following the group.

## Follow or pin a session

The card can follow:

| Source | Behavior |
| --- | --- |
| **Automatic** | Uses the most relevant current source. |
| **Live** | Follows the active live session. |
| **Replay** | Follows the session currently loaded in Replay Mode. |
| **Pinned** | Keeps the selected live, replay or archive identity. |

A pin stores the session identity; it does not start live timing, load a replay or change Replay Mode. If the saved identity is unavailable, the card explains the mismatch instead of silently switching sessions.

Each module can inherit the card selection, follow another source or keep its own pin. You can also show a module only **Before**, **Active or interrupted**, **Finished** or **Unknown** phases.

## Control unavailable data

Each module has a **When data is unavailable** setting.

| Choice | Behavior |
| --- | --- |
| **Show explanation** | Replaces the unavailable content with an explanation and keeps the configuration. |
| **Keep saved data** | Retains the last captured content with a notice when updates stop. |
| **Hide module** | Hides the module until its data is available again. |

Retained values are reading snapshots, not proof of a current live state. Changing installation, session, replay position, Live Delay or spoiler state clears incompatible snapshots.

**Freeze view** captures the currently displayed reading in that card. **Resume** returns to current data. Freezing the card does not pause Replay Mode or change any integration setting. To remove this control from a card, open **Layout and shared focus** and clear **Show Freeze view button**. The button is shown by default.

Weather, Battles, Strategy and Replay telemetry also show a collapsible **About** section by default. Clear **Show About section** under the relevant module's **Module options** to hide that explanation without hiding warnings, errors or controls.

## Choose appearance

Use **Appearance** to choose:

- F1, Home Assistant or Minimal style
- automatic, light or dark mode
- comfortable, compact or spacious density
- F1 or system typography
- accent, surface, logo, flag, team-color and tyre presentation
- stacked or tabbed module layout

Module headings and table headers can be hidden visually while their accessible names remain available. Put important fields first and remove secondary columns for a clearer phone layout.

## Keep timing meaning visible

Timing states pair color with a shape or text signal. Purple with a diamond means overall fastest, green with a circle means personal best, and yellow with a square means a recorded time. Lap deltas and position changes use separate arrows and references.

In a Timing module, set **Recent lap columns** to a value from 1 to 30 to show that many latest completed laps as labelled comparison columns. Keep it at 0 to hide the extra columns.

Use **Accessibility and timing colors** to change the palette, enable high contrast, reduce motion and choose shape, text or both. See [card accessibility](/cards/modular-accessibility) for the complete guidance.

Track Map interpolates consecutive driver positions for smoother live and replay movement. Reduced motion, stale positions, session changes and unusually large jumps are shown without animation.

## Use spoilers, Live Delay and replay controls

Enable **Show Live Delay and global spoiler controls** to add the optional viewing panel.

- Manual Live Delay changes require **Apply live delay** and affect the selected integration entry.
- **Calibrate with TV** keeps the existing delay until you explicitly match the moment shown on television.
- Global spoiler protection affects all F1 Sensor installations. Local hiding can add protection but cannot override the global setting.
- Replay controls operate the selected installation's shared Replay Mode. Separate cards are not independent replay players.
- Archive selections retrieve historical data without loading or starting a replay.

See [Live Delay](/features/live-delay), [No Spoiler Mode](/features/no-spoiler-mode) and [Replay Mode](/features/replay-mode) for the integration-wide behavior.

## Export or reuse a configuration

**Export and import** copies the complete card configuration as JSON. **Reusable templates** let you name and transfer the same configuration to another dashboard or Home Assistant system.

An import is first applied to the editor draft and can be undone before saving. If a template references an installation that does not exist on the current system, choose its replacement explicitly.

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

## Related

- [Build the card](/cards/modular)
- [Move from a deprecated card](/cards/modular-migration)
- [Card installation and loading checks](/cards/installation)
