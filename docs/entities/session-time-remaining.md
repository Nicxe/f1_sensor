---
id: session-time-remaining
title: "Session Time Remaining"
description: "Time remaining in the current session (beta) \u2014 state, attributes, and examples for F1 Sensor."
---

Time remaining in the current session (beta). Use `sensor.f1_session_time_remaining` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

:::warning[Beta]
This sensor is currently in beta. The behavior has not been verified across all session types, edge cases (red flags, suspensions, qualifying segments), and timing scenarios. Treat the values as indicative rather than definitive until further testing is complete.
:::

`sensor.f1_session_time_remaining` - How much scheduled session time is left, based on the F1 ExtrapolatedClock feed. Like the elapsed sensor, this value follows the available clock data and its running flag. Check `clock_running` and `clock_phase` rather than assuming every interruption pauses the clock.

**State**
- String: remaining time formatted as `H:MM:SS` (e.g., `0:36:15`), or `unavailable` when no data is available.

**Example**
```text
0:36:15
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
| source_quality | string | Data source reliability; see [source quality](/entities/session-time-elapsed#source-quality) |
| session_start_utc | string | ISO‑8601 timestamp of the session start |
| reference_utc | string | ISO‑8601 timestamp used as the clock reference point |
| last_server_utc | string | ISO‑8601 timestamp of the last server heartbeat |
| value_seconds | number | Remaining time in whole seconds |
| formatted_hms | string | Remaining time formatted as `H:MM:SS` |
| clock_total_s | number | Total scheduled session duration in seconds, when known |
:::info[Session clock behavior]
The session clock counts down the scheduled duration of the session. It does not account for race laps — in a race, the session ends when the leader completes the required number of laps, which may happen before or (rarely) after the scheduled time expires. Use `sensor.f1_race_lap_count` for lap-based progress.
:::


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
