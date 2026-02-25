---
id: no-spoiler-mode
title: No Spoiler Mode
---

No Spoiler Mode lets you record a session and watch it later without your dashboard giving away the result. When active, all race results, live timing, and session data are frozen so nothing spoils what happened on track.

Your entities stay visible and your automations keep running, but the data they see remains exactly as it was when you turned the mode on.

---

## How it works

When No Spoiler Mode is turned on, the integration stops delivering new data to all spoiler-sensitive entities. Internally, the integration continues to fetch and cache data in the background, so when you turn the mode off, everything updates immediately with the full picture of what happened.

Live sessions are handled cleanly too. If a session is in progress when you activate the mode, the live connection is dropped right away. When you deactivate, all blocked data is refreshed at once and the live connection re-establishes if a session is still running.

The setting is remembered across Home Assistant restarts. If you activate No Spoiler Mode before you go to bed and restart Home Assistant in the morning, the mode will still be on when you wake up.

---

## What is blocked

Not all data is blocked. Schedule and calendar data is always kept up to date so you can still see when the next race is.

**Always updates:**
- Next race details
- Season schedule and race calendar
- Race weekend weather
- Any other schedule-based information

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

## Replay Mode

No Spoiler Mode and [Replay Mode](/features/replay-mode) work independently of each other. When you start a replay, the replay data flows through normally regardless of whether No Spoiler Mode is on. This means you can watch a session through Replay Mode while No Spoiler Mode is active, and your automations and dashboards will reflect the replay exactly as they would during a live session.

Finishing a replay does not turn off No Spoiler Mode. You stay protected until you turn the switch off yourself.

---

## Example: Automate with your TV

This automation turns No Spoiler Mode on when you start watching a recording and off when you are done.

```yaml
automation:
  - alias: "Activate No Spoiler Mode when watching F1 recording"
    trigger:
      - platform: state
        entity_id: media_player.your_tv
        to: "playing"
    condition:
      - condition: state
        entity_id: input_boolean.watching_f1_recording
        state: "on"
    action:
      - action: switch.turn_on
        target:
          entity_id: switch.f1_sensor_no_spoiler_mode

  - alias: "Deactivate No Spoiler Mode when done watching"
    trigger:
      - platform: state
        entity_id: media_player.your_tv
        to: "idle"
    action:
      - action: switch.turn_off
        target:
          entity_id: switch.f1_sensor_no_spoiler_mode
```

Replace `media_player.your_tv` with your actual media player entity. The `input_boolean.watching_f1_recording` lets you control when the automation should activate so it does not trigger for other content.

---

## Limitations

- No Spoiler Mode blocks data from reaching your entities, but it does not prevent Home Assistant from receiving data internally. The integration keeps its cache warm throughout the blackout so catch-up is instant.
- The mode is global and cannot be scoped to individual config entries or specific entities.
