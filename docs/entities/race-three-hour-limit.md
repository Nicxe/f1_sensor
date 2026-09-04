---
id: race-three-hour-limit
title: "Race Three Hour Limit"
description: "Time remaining until the FIA 3-hour race duration cap (beta) \u2014 state, attributes, and examples for F1 Sensor."
---

Time remaining until the FIA 3-hour race duration cap (beta). Use `sensor.f1_race_time_to_three_hour_limit` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

:::warning[Beta]
This sensor is currently in beta. The behavior has not been verified across all edge cases and timing scenarios. Treat the values as indicative rather than definitive until further testing is complete.
:::

`sensor.f1_race_time_to_three_hour_limit` - Time remaining until the FIA three-hour race duration cap is reached. This sensor is only available during the main race session (not sprint races).

This sensor counts down to three hours after the recorded race start, independently of the session clock. It is a timing aid and does not predict the final lap or an official decision about when the race will end.

**State**
- String: remaining time formatted as `H:MM:SS` (e.g., `2:14:30`), or `unavailable` when no data is available or outside the main race.

**Example**
```text
2:14:30
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| session_type | string | Session type (e.g., "Race") |
| session_name | string | Session name (e.g., "Race") |
| session_part | number | Session part, when available |
| session_status | string | Current session status from the feed |
| clock_phase | string | Clock state: `idle`, `running`, `paused`, `overtime`, or `finished` |
| clock_running | boolean | Whether the clock is actively counting |
| source_quality | string | Data source reliability; see [source quality](/entities/session-time-elapsed#source-quality) |
| session_start_utc | string | ISO‑8601 timestamp of the session start |
| reference_utc | string | ISO‑8601 timestamp used as the clock reference point |
| last_server_utc | string | ISO‑8601 timestamp of the last server heartbeat |
| value_seconds | number | Remaining time until three-hour cap in whole seconds |
| formatted_hms | string | Remaining time formatted as `H:MM:SS` |
| race_start_utc | string | ISO‑8601 timestamp of the race start |
| race_three_hour_cap_utc | string | ISO‑8601 timestamp of the three-hour deadline |
:::info[Info]
This sensor is only available during the main race session. It becomes unavailable during practice, qualifying, and sprint sessions.
:::


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
