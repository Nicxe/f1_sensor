---
id: starting-grid
title: "Starting Grid"
description: "Provisional or confirmed Sprint/Race starting grid \u2014 state, attributes, and examples for F1 Sensor."
---

Provisional or confirmed Sprint/Race starting grid. Use `sensor.f1_starting_grid` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`sensor.f1_starting_grid` - Current weekend starting grid for the next relevant Sprint or Race. The sensor keeps old grid data from previous weekends from appearing as current data, and clears the grid when the related start is no longer relevant.

On a normal race weekend, the sensor builds a Race grid from Qualifying. On a sprint weekend, it first builds a Sprint grid from Sprint Qualifying, then clears that grid after the Sprint and builds the Race grid from Qualifying.

**State (enum)**
- One of: `waiting_for_sprint_qualifying`, `waiting_for_qualifying`, `collecting`, `provisional`, `confirmed`, `completed`.

| Value | Description |
| --- | --- |
| `waiting_for_sprint_qualifying` | A sprint weekend is active or likely, and the sensor is waiting for Sprint Qualifying before it can build a Sprint grid. `grid` is empty. |
| `waiting_for_qualifying` | The sensor is waiting for Qualifying before it can build a Race grid. This is used on normal weekends before Qualifying, and on sprint weekends after the Sprint has finished. `grid` is empty. |
| `collecting` | Sprint Qualifying, Qualifying, Sprint, or Race is active and the sensor is collecting timing or grid-position data. `grid` can still be empty until enough data has arrived. |
| `provisional` | A preliminary grid has been built from qualifying timing data. This follows the qualifying order and may still change because of grid penalties, pit-lane starts, or other official updates. |
| `confirmed` | The grid has been confirmed from the live timing grid-position data for the Sprint or Race. This is the best available source and can show movement from the original qualifying order. |
| `completed` | The Race has finished or been finalised, and no active starting grid is exposed. `grid` is empty. On sprint weekends, finishing the Sprint changes the sensor back to `waiting_for_qualifying` instead of `completed`, because the Race grid is still pending. |

**Example**
```text
confirmed
```

### Grid context and source

`grid_context` explains which start the grid applies to:

| Value | Description |
| --- | --- |
| `sprint` | The active grid applies to the Sprint |
| `race` | The active grid applies to the Race |
| `none` | No active grid should be shown |

`source` explains where the current grid came from:

| Value | Description |
| --- | --- |
| `live_timing_qualifying` | A provisional grid built from live qualifying timing data |
| `live_timing_archive` | A provisional grid restored from Formula 1's static live timing archive after Qualifying or Sprint Qualifying |
| `live_timing_gridpos` | A confirmed grid built from live timing grid-position data before the Sprint or Race |
| `null` | No active grid is currently available |

:::info
Archive data is only used while there is still a relevant upcoming Sprint or Race. After the Race has finished, the sensor stays `completed` and does not restore historical grid data for that weekend.
:::

### Weekend flow

On a normal weekend, the expected flow is `waiting_for_qualifying` → `collecting` → `provisional` → `confirmed` → `completed`.

On a sprint weekend, the expected flow is `waiting_for_sprint_qualifying` → `collecting` → `provisional` → `confirmed` for the Sprint. After the Sprint finishes, the Sprint grid is cleared and the sensor moves to `waiting_for_qualifying` for the Race grid. After the Race finishes, the sensor moves to `completed`.

When a new race weekend is detected, the sensor clears the previous grid, resets the driver rows, and starts waiting for the relevant qualifying session. Replay Mode does not replace or clear the live Starting Grid sensor, so replaying an older session will not overwrite the current or upcoming weekend grid.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| status | string | Same value as the sensor state |
| grid_context | string | `sprint`, `race`, or `none`, depending on which start the grid applies to |
| weekend_key | string | Weekend identifier used to keep restored data scoped to the current race weekend |
| weekend_format | string | `normal`, `sprint`, or `unknown` |
| meeting_name | string | Race weekend name |
| session_key | string | Source session identifier when available |
| source_session_name | string | Session used to build the grid, such as `Sprint Qualifying` or `Qualifying` |
| target_session_name | string | Session the grid applies to, such as `Sprint` or `Race` |
| source | string | `live_timing_qualifying`, `live_timing_archive`, `live_timing_gridpos`, or `null` |
| source_updated_at | string | ISO-8601 timestamp for the last source update |
| cleared_at | string | ISO-8601 timestamp when the grid was cleared |
| cleared_reason | string | Reason the grid was cleared, such as `new_weekend`, `sprint_completed`, or `race_completed` |
| grid_count | number | Number of drivers in the grid |
| grid | list | Ordered starting grid rows |

Each entry in `grid` contains:

| Field | Type | Description |
| --- | --- | --- |
| grid_position | number | Starting grid position |
| qualifying_position | number | Original qualifying position |
| racing_number | string | Car number |
| tla | string | Driver TLA |
| driver_name | string | Driver name |
| team_name | string | Team name |
| team_color | string | Team color |
| qualifying_time | string | Best qualifying time used for the grid row |
| qualifying_time_secs | number | Best qualifying time in seconds |
| qualifying_segment | string | Q/SQ segment, such as `Q3` or `SQ3` |
| qualifying_lap | number | Lap number for the qualifying time |
| segment_times | list | Segment timing details used to derive the row |
| grid_delta | number | Difference between grid position and qualifying position |
| changed_from_qualifying | boolean | True when penalties or grid updates moved the driver |
| source | string | Source used for this grid row |
| grid_context | string | `sprint` or `race` |

:::info
The grid is provisional when it is built from qualifying timing and confirmed when final starting grid data becomes available. The `grid` attribute is marked as unrecorded to avoid storing large race-weekend data in the Home Assistant recorder.
:::


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
