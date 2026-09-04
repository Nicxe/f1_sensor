---
id: session-time-elapsed
title: "Session Time Elapsed"
description: "Time elapsed in the current session (beta) \u2014 state, attributes, and examples for F1 Sensor."
---

Time elapsed in the current session (beta). Use `sensor.f1_session_time_elapsed` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

:::warning[Beta]
This sensor is currently in beta. The behavior has not been verified across all session types, edge cases (red flags, suspensions, qualifying segments), and timing scenarios. Treat the values as indicative rather than definitive until further testing is complete.
:::

`sensor.f1_session_time_elapsed` - How much of the scheduled session time has passed, based on the F1 ExtrapolatedClock feed. The value follows the available session clock and its running flag. A Safety Car alone does not imply that this clock pauses; check `clock_running` and `clock_phase`.

**State**
- String: elapsed time formatted as `H:MM:SS` (e.g., `0:23:45`), or `unavailable` when no data is available.

**Example**
```text
0:23:45
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| session_type | string | Session type (e.g., "Practice", "Qualifying", "Race") |
| session_name | string | Session name (e.g., "Practice 1", "Race") |
| session_part | number | Session part, for example the qualifying segment (Q1/Q2/Q3) |
| session_status | string | Current session status from the feed |
| clock_phase | string | Clock state: `idle`, `running`, `paused`, `overtime`, or `finished` |
| clock_running | boolean | Whether the clock is actively counting |
| source_quality | string | Data source reliability (see below) |
| session_start_utc | string | ISO‑8601 timestamp of the session start |
| reference_utc | string | ISO‑8601 timestamp used as the clock reference point |
| last_server_utc | string | ISO‑8601 timestamp of the last server heartbeat |
| value_seconds | number | Elapsed time in whole seconds |
| formatted_hms | string | Elapsed time formatted as `H:MM:SS` |
| clock_total_s | number | Total scheduled session duration in seconds, when known |
| clock_remaining_s | number | Remaining time in seconds, when known |

### Source quality

| Value | Description |
| --- | --- |
| `official` | Clock data from ExtrapolatedClock with server heartbeat confirmation |
| `official_no_heartbeat` | Clock data from ExtrapolatedClock, but no heartbeat received yet |
| `sessiondata_fallback` | Elapsed time estimated from session schedule data, not from the live clock feed |
| `unavailable` | No usable timing data available |


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
