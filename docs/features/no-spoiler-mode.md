---
id: no-spoiler-mode
title: No Spoiler Mode
description: Freeze spoiler-sensitive information before a session, watch with Replay Mode, and choose when to reveal results.
---

Turn on No Spoiler Mode **before the session starts** when you plan to watch later. It holds spoiler-sensitive information in F1 Sensor while schedule information remains useful.

## The complete workflow

1. **Before watching:** turn on `switch.f1_no_spoiler_mode` and check that it is on.
2. **During the live session:** F1 Sensor holds spoiler-sensitive updates and stops the live connection. This is not a recording of the session.
3. **When you are ready:** load the completed session in [Replay Mode](/features/replay-mode). Archived data can drive your dashboard and automations while you watch.
4. **After watching:** turn No Spoiler Mode off when you are ready for current results and standings.

## What to expect

The setting survives Home Assistant restarts. It prevents new spoiler-sensitive updates; it does not erase information you already saw or hide results in unrelated apps and integrations.

Turning it off requests fresh data. Availability and update time depend on the source; not every message missed during the live session can be recovered. The live connection can resume if a session is still active.

## What is blocked

| Data | While No Spoiler Mode is on |
| --- | --- |
| Next race, season schedule and calendar | Continues to provide schedule information |
| Race weekend weather | Remains available |
| Live session timing and activity | Live delivery is stopped |
| Results, standings and championship predictions | New spoiler-sensitive information is held |
| FIA documents and Race Control | New spoiler-sensitive information is held |
| Live incident alerts | New alerts are blocked and are not later replayed as missed live notifications |

Use Replay Mode for historical timing and incident alerts. Its coverage depends on what is available in the archive.

## The switch entity

| Entity | Purpose |
| --- | --- |
| `switch.f1_no_spoiler_mode` | Enable or disable spoiler protection |

Find it under the F1 **System** device. It is a global setting: if you have several F1 Sensor entries, the same switch controls them all.

## Using Replay Mode while blocked

Replay can deliver archived timing while No Spoiler Mode remains on. This lets you follow the loaded session without reopening live data. Stopping a replay does not turn off spoiler protection.

Some result cards keep a spoiler overlay until you explicitly allow results. Use the replay controls and live timing cards to follow the session; leave the switch on until you are ready to reveal current results.

## Example: Activate automatically at session time

Schedule protection **before** you expect the session to begin. An automation that waits for Session live may run after the first spoiler-sensitive update has already arrived.

This example turns protection on at a time you choose. Replace `12:00:00` with a time before the session in your Home Assistant timezone, and enable the automation only for the viewing schedule you want.

```yaml
alias: Protect F1 results before watching later
triggers:
  - trigger: time
    at: "12:00:00"
actions:
  - action: switch.turn_on
    target:
      entity_id: switch.f1_no_spoiler_mode
mode: single
```

This example runs daily while enabled. Check the switch before the session and turn it off manually after watching.

## Limitations

- Protection is global, not per entry or per entity.
- It is not a recording service and does not guarantee complete catch-up.
- Replay data depends on the session archive.
- Rewinding a replay can trigger historical automations and notifications again.

Continue with [Replay Mode](/features/replay-mode) or [troubleshooting](/help/overview).
