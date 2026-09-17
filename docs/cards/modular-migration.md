---
id: modular-migration
title: Move an existing F1 dashboard to the modular card
description: Review a legacy F1 Sensor card conversion, preserve the original and migrate a dashboard without losing a working setup.
toc_max_heading_level: 2
---

Move one card at a time and keep the working dashboard until the modular version
shows the information and behavior you rely on. Existing F1 Sensor cards remain
supported during the development preview.

:::warning Review every conversion
Conversion creates a starting point, not a promise of identical appearance or
behavior. Settings without a supported equivalent stay in the recoverable
original and appear in the review instead of being silently discarded.
:::

## Convert a card

1. Open the dashboard editor and add **F1 Sensor**.
2. Open the conversion option and paste or select the legacy card configuration.
3. Choose the correct F1 Sensor installation if it cannot be identified uniquely.
4. Read every **Carried**, **Changed** and **Review** row before applying the result.
5. Compare the preview with the original card, then save only when the result is
   useful for your dashboard.

The editor keeps an exact copy of the input configuration inside the converted
card. Applying a conversion changes only the editor draft; Home Assistant does
not save the dashboard until you select **Save**.

## Understand the review

| Result | Meaning |
| --- | --- |
| Carried | The value has a supported destination in the modular configuration. |
| Changed | The closest supported behavior is applied and the difference is explained. |
| Review | No equivalent value is applied. Keep the original card if you require it. |

Entity overrides can be replaced by installation-based source discovery. Timing
symbols remain present even when an older card disabled color indicators. Weather
can become separate current-condition and race-start forecast modules. Old
practice, qualifying and race card restrictions are not automatically treated as
a session lock; use the module's phase and session controls explicitly.

Temporary archive or replay selections are not inferred from an old card. Select
the archive event and session or load the replay yourself. Conversion never starts
live data, loads a replay, changes Live Delay or changes global spoiler protection.

## Verify before replacing the original

Check the migrated card between sessions and with the data mode you normally use:

1. Confirm the selected installation, module order, fields and filters.
2. Confirm spoiler behavior and any retained-data choice.
3. Reopen the saved card editor and confirm the choices remain.
4. During a suitable session or replay, compare timing, gaps, sectors and status
   values with the original.
5. Test the dashboard on the phones, tablets and browsers you use.

Do not remove the original card until these checks pass for your setup. Full
semantic parity for every option of all legacy cards is not claimed by the
development preview.

## Restore the legacy configuration

Open the converted card's migration review and choose the restore option. The
editor reconstructs the exact stored legacy configuration. Review it before
saving because changes made only to the modular card are not copied back into the
legacy format.

For general setup, see [the modular card guide](/cards/modular). For readable
layouts and non-color signals, see [the accessibility guide](/cards/modular-accessibility).
