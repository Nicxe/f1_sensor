---
id: live-delay-controls
title: Live Delay controls
description: Look up the Live Delay number, calibration switch, reference selector, match button, and their attributes.
---

These controls align live timing with your broadcast. For the step-by-step workflow, use [Live Delay](/features/live-delay). Replay follows its own playback controls and does not wait for this delay.

## Controls at a glance

| Entity | Purpose |
| --- | --- |
| `number.f1_live_delay` | Delay live updates by a number of seconds |
| `switch.f1_delay_calibration` | Arm calibration or cancel it |
| `select.f1_live_delay_reference` | Choose **Session live** or **Lap sync (race/sprint)** |
| `button.f1_delay_calibration_match` | Save the measured delay when your TV reaches the reference |

Use your existing entity IDs if they differ from these standard IDs.

## Live Delay number

`number.f1_live_delay` accepts **0–300 seconds**, in steps of **1 second**. Setting the value changes the delay used for live updates.

**Example**

```yaml
action: number.set_value
target:
  entity_id: number.f1_live_delay
data:
  value: 30
```

**Calibration attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| calibration_mode | string | Calibration mode such as `idle`, `waiting`, or `running` (best effort) |
| calibration_reference | string | Selected reference used for calibration (best effort) |
| calibration_waiting_since | string | ISO‑8601 timestamp when calibration started waiting (best effort) |
| calibration_started_at | string | ISO‑8601 timestamp when the timer started (best effort) |
| calibration_elapsed | number | Elapsed seconds since start (best effort) |
| calibration_timeout_at | string | ISO‑8601 timestamp when calibration times out (best effort) |
| calibration_last_result | number | Most recent saved delay value in seconds (best effort) |
| calibration_message | string | Human-readable status message (best effort) |

## Calibration switch

`switch.f1_delay_calibration` is `on` while calibration is `waiting` or `running`. Turning it off cancels calibration. Turning it on arms the selected reference; use the status message to identify the moment to match on TV.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| mode | string | Calibration mode such as `idle`, `waiting`, or `running` (best effort) |
| reference | string | Selected reference used for calibration (best effort) |
| message | string | Human-readable status message (best effort) |
| waiting_since | string | ISO‑8601 timestamp when calibration started waiting (best effort) |
| started_at | string | ISO‑8601 timestamp when the timer started (best effort) |
| elapsed | number | Elapsed seconds since start (best effort) |
| timeout_at | string | ISO‑8601 timestamp when calibration times out (best effort) |
| recorded_lap | number | Lap number recorded for lap sync calibration, or null if not applicable (best effort) |

## Reference selector and match button

Choose **Session live** for the start of a session, or **Lap sync (race/sprint)** for the next completed lap. Press `button.f1_delay_calibration_match` when your broadcast reaches the recorded reference point.

A completed lap and the next lap starting describe the same boundary: `Lap 52 completed` usually matches the TV counter changing to lap 53. If you missed it, cancel and arm calibration again.

- [Follow the calibration guide](/features/live-delay#option-2---guided-calibration)
- [Replay controls](/reference/replay-controls)
