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

Setting `number.f1_live_delay` changes the delay used for live updates.

**State**

A delay from **0–300 seconds**, in steps of **1 second**.

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
| calibration_idle_reason | string or null | Why calibration returned to idle; see the outcomes below. Null before the first attempt and while waiting or measuring. |
| calibration_reference | string | Selected reference used for calibration (best effort) |
| calibration_waiting_since | string | ISO‑8601 timestamp when calibration started waiting (best effort) |
| calibration_started_at | string | ISO‑8601 timestamp when the timer started (best effort) |
| calibration_elapsed | number | Elapsed seconds since start (best effort) |
| calibration_timeout_at | string | ISO‑8601 timestamp when calibration times out (best effort) |
| calibration_last_result | object or null | Most recent saved calibration, containing `seconds`, `completed_at`, and `source`. An older result remains available after cancellation or timeout. |
| calibration_message | string | Human-readable status message (best effort) |

## Calibration switch

Turning `switch.f1_delay_calibration` on arms the selected reference. Turning it off cancels calibration. Use its status to identify the moment to match on TV.

**State**

- `on`: calibration is waiting for its reference or measuring the delay.
- `off`: calibration is idle.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| mode | string | Calibration mode such as `idle`, `waiting`, or `running` (best effort) |
| idle_reason | string or null | Why calibration returned to idle; see the outcomes below. Null before the first attempt and while waiting or measuring. |
| last_result | object or null | Most recent saved calibration: `seconds`, `completed_at`, and `source`. This arrives with the switch's mode and outcome in the same update. |
| reference | string | Selected reference used for calibration (best effort) |
| message | string | Human-readable status message (best effort) |
| waiting_since | string | ISO‑8601 timestamp when calibration started waiting (best effort) |
| started_at | string | ISO‑8601 timestamp when the timer started (best effort) |
| elapsed | number | Elapsed seconds since start (best effort) |
| timeout_at | string | ISO‑8601 timestamp when calibration times out (best effort) |
| recorded_lap | number | Lap number recorded for lap sync calibration, or null if not applicable (best effort) |

### Calibration outcomes

Use `idle_reason` together with `mode`. A previous saved result does not mean the latest attempt succeeded.

| Idle reason | Meaning |
| --- | --- |
| `completed` | The measured delay was saved. |
| `cancelled` | Calibration was cancelled without saving a new delay. |
| `timeout` | The matching window expired without saving a new delay. |
| `session_ended` | The session ended during measurement; calibration stopped without saving. |
| `replay` | Selecting or using replay stopped calibration without saving. |
| `unsupported_session` | Lap sync could not start because the session was not a race or sprint. |
| `null` | No outcome yet, or calibration is waiting or measuring. |

The number entity exposes the same outcome as `calibration_idle_reason`. Both its `calibration_last_result` and the switch's `last_result` have this form when a calibration has been saved:

```json
{
  "seconds": 32,
  "completed_at": "2026-09-14T13:00:32+00:00",
  "source": "button"
}
```

## Reference selector and match button

Choose **Session live** for the start of a session, or **Lap sync (race/sprint)** for the next completed lap. Press `button.f1_delay_calibration_match` when your broadcast reaches the recorded reference point.

A completed lap and the next lap starting describe the same boundary: `Lap 52 completed` usually matches the TV counter changing to lap 53. If you missed it, cancel and arm calibration again.

- [Follow the calibration guide](/features/live-delay#option-2---guided-calibration)
- [Replay controls](/reference/replay-controls)
