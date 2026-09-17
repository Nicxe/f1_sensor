---
id: modular-migration
title: Move to the F1 Sensor card
description: Convert a deprecated F1 dashboard card, review every change and keep a recoverable original.
toc_max_heading_level: 2
---

The earlier single-purpose F1 dashboard cards are deprecated. Move each dashboard configuration to `custom:f1-sensor-card`, which replaces them with configurable modules in one visual editor.

:::warning[Deprecated cards]
Deprecated card types are kept only to help existing dashboards move. Do not use them for a new dashboard. Future development and documentation target the **F1 Sensor** card.
:::

## Convert an existing card

1. Make a dashboard backup. To compare both versions, duplicate the old card before converting the copy.
2. Open the old card in the Home Assistant dashboard editor.
3. In **Try the modular F1 Sensor card**, select **Review conversion**.
4. Choose the correct F1 Sensor installation if the converter cannot identify it uniquely.
5. Open every **Choose again or keep the original**, **Changed behavior** and **Transferred settings** section.
6. Review the sample-data preview and accept the review statement.
7. Select **Apply conversion**. This changes only the editor draft.
8. Configure any missing choices in the new editor, preview the result and select **Save** in Home Assistant.

The converter stores an exact copy of the original configuration inside the converted card. Canceling the conversion leaves the original unchanged.

## Understand what the converter creates

| Deprecated card purpose | New starting point |
| --- | --- |
| Weekend Hub | Overview, Session timeline, Strategy analysis, Battles and position changes, Replay telemetry |
| Next Race | Overview, Schedule, current weather and race-start forecast |
| Race Weather | Current weather and race-start forecast |
| Season Calendar | Season Schedule |
| Live Session | Overview and track weather |
| Practice, qualifying or race timing | Timing, with Pit stops added for the race view |
| Starting Grid | Results in starting-grid mode |
| Race Control | Race Control |
| FIA Documents | FIA documents |
| Investigations or Track Limits | Incidents in the matching view |
| Tyre Statistics | Tyres in statistics mode |
| Pit Stops | Pit stops and Tyres |
| Driver Lap Times | Timing with gap controls |
| Results | Results and Historical archive |
| Session Archive or Lap Position Progression | Historical archive in the matching view |
| Driver or constructor championship | Championship for drivers or teams |
| Season Progression | Season progression |
| Replay Control | Replay |
| Track Map | Track map |

This is a sensible starting point, not an exact visual copy. The new card combines shared focus, session selection, accessibility and data-availability behavior that did not exist consistently across the deprecated cards.

## Read the conversion review

| Review group | Meaning |
| --- | --- |
| **Transferred settings** | The setting has a supported destination in the new card. |
| **Changed behavior** | The closest supported behavior is applied and the difference is explained. |
| **Choose again or keep the original** | No equivalent is applied; choose a new value or retain the original configuration. |

Entity overrides normally become installation-based source discovery. Timing symbols remain available even when a deprecated card hid color indicators. Weather settings can become separate current-condition and race-start forecast modules.

Temporary archive and replay selections are not inferred. Select an archive event in its module or load a replay after conversion. Conversion never starts live data, loads a replay, changes Live Delay or changes global spoiler protection.

## Finish the new configuration

After applying the conversion draft:

1. Confirm the selected installation and card title.
2. Reorder, add or remove modules for the dashboard's purpose.
3. Review fields, filters, driver or team focus and unavailable-data behavior for every module.
4. Choose stacked or tabbed layout and adjust appearance and timing signals.
5. Save the card, reopen its editor and confirm the saved choices.

The old configuration may contain options with no direct equivalent. These remain in the stored original and are shown in the review instead of being silently discarded.

## Restore or export the original

Open the converted card editor and expand its migration section.

- **Export original** copies the exact stored deprecated configuration as JSON.
- **Restore original…** shows a confirmation inside the editor, then replaces the current draft with that stored configuration.

Restoring does not save the dashboard automatically. Review the draft and select **Save** only if you intentionally want to return to the deprecated card.

## Build the replacement manually

If a deprecated card does not open its converter, add a new **F1 Sensor** card and choose the closest preset from [the card overview](/cards/cards-overview). Use the mapping above to add the equivalent modules, then remove the deprecated card after the new configuration is saved.

For module setup, see [Build your F1 Sensor card](/cards/modular). For readable layouts and non-color signals, see [card accessibility](/cards/modular-accessibility).
