---
id: no-spoiler-mode
title: No Spoiler Mode
---

Can't watch the race live? Turn on No Spoiler Mode before the session starts, watch it later with [Replay Mode](/features/replay-mode), and your dashboard will behave exactly as if you were there in real time — without anything spoiling the result first.

When No Spoiler Mode is active, all race results, live timing, and session data are frozen. Your entities stay visible and your automations keep running, but nothing gives away what happened on track.

---

## The complete workflow

1. **Before the session** — Turn on No Spoiler Mode. The integration stops delivering spoiler-sensitive data immediately.
2. **During the session** — Your dashboard stays frozen. The integration still fetches and caches everything in the background so nothing is lost.
3. **When you are ready to watch** — Open [Replay Mode](/features/replay-mode), load the session, and press play at the right moment. Your automations and live entities respond to the replay exactly as they would during a live broadcast.
4. **When you are done** — Turn No Spoiler Mode off. Everything updates at once with the full picture of what happened.

You never miss any data. FIA documents, race control messages, and results all arrive the moment you turn the mode off.

---

## How it works

When No Spoiler Mode is turned on, the integration stops delivering new data to all spoiler-sensitive entities. Internally it continues to fetch and cache data in the background, so when you turn the mode off, everything updates immediately.

Live sessions are handled cleanly too. If a session is in progress when you activate the mode, the live connection is dropped straight away. When you deactivate, blocked data is refreshed at once and the live connection re-establishes if a session is still running.

The setting is remembered across Home Assistant restarts. If you activate No Spoiler Mode before you go to bed and restart Home Assistant in the morning, the mode will still be on when you wake up.

---

## What is blocked

Not all data is blocked. Schedule and calendar data is always kept up to date so you can still see when the next session is.

**Always updates:**
- Next race details
- Season schedule and race calendar
- Race weekend weather

**Frozen while mode is active:**
- Live timing and session activity
- Race and qualifying results
- Driver and constructor standings
- Championship predictions
- FIA documents and race control messages
- Team radio and pit stop data

When you deactivate the mode, all frozen data is refreshed immediately and delivered to your entities at once. If any FIA documents were published during the blackout, they all appear at the same time.

---

## The switch entity

No Spoiler Mode is controlled by a single global switch:

| Entity | Purpose |
| --- | --- |
| `switch.f1_sensor_no_spoiler_mode` | Turn No Spoiler Mode on or off |

The switch is available under the F1 system device, alongside the live delay calibration switch. It controls the mode for all your F1 Sensor entries at once.

:::info One switch for everything
If you have multiple F1 Sensor config entries, there is still only one No Spoiler Mode switch. Activating it blocks spoiler data across all entries simultaneously.
:::

---

## Using Replay Mode while blocked

No Spoiler Mode and Replay Mode work independently. When you start a replay, data flows through normally regardless of whether No Spoiler Mode is on. Your automations and dashboards respond to the replay exactly as they would during a live session.

Finishing a replay does not turn off No Spoiler Mode. You stay protected until you turn the switch off yourself.

See [Replay Mode](/features/replay-mode) for full instructions on loading and playing back a session.

---

## Example: Activate automatically at session time

This automation turns No Spoiler Mode on when a Grand Prix qualifying or race session begins, so you never have to remember to do it manually.

```yaml
automation:
  - alias: "Activate No Spoiler Mode at session start"
    trigger:
      - platform: state
        entity_id: sensor.f1_session_status
        to: "Started"
    action:
      - action: switch.turn_on
        target:
          entity_id: switch.f1_sensor_no_spoiler_mode
```

Turn it off manually when you are done watching the replay.

---

## Limitations

- No Spoiler Mode blocks data from reaching your entities, but the integration keeps its cache warm throughout the blackout so catch-up is instant when you turn it off.
- The mode is global and cannot be scoped to individual config entries or specific entities.
