---
id: pit-stops
title: "Pit Stops"
description: "Pit stop events and aggregated pit stop series per car (Replay Mode or F1TV Auth live timing) \u2014 state, attributes, and examples for F1 Sensor."
---

Pit stop events and aggregated pit stop series per car (Replay Mode or F1TV Auth live timing). Use `sensor.f1_pitstops` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

:::info[Replay Mode or F1TV Auth live timing]
This entity stays registered in Home Assistant. It updates in [Replay Mode](/features/replay-mode) and can update during live sessions when [F1TV Auth](/features/f1tv-auth) is paired with a valid token and live pit stop data is available.
:::

`sensor.f1_pitstops` - Pit stop information from the F1 Live Timing feed, aggregated per car.

**State**
- Integer: total number of pit stops recorded in the current session, or `0` when none are available.

**Example**
```text
7
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| cars | object | Map of racing numbers to pit stop details |
| last_update | string | ISO‑8601 timestamp of the last received pit stop event |

Each entry in `cars` (keyed by racing number) contains:

| Field | Type | Description |
| --- | --- | --- |
| tla | string | Driver code (TLA) when available |
| name | string | Driver name when available |
| team | string | Team name when available |
| count | number | Number of pit stops recorded for the car |
| stops | list | List of pit stops (most recent stops kept, best effort) |

Each entry in `stops` contains:

| Field | Type | Description |
| --- | --- | --- |
| lap | number | Lap number when the stop happened |
| timestamp | string | Timestamp from the feed when available |
| pit_stop_time | number | Stationary time (seconds), when available |
| pit_lane_time | number | Total pit lane time (seconds), when available |
| pit_delta | number | Estimated loss vs a normal lap (seconds), when available |
:::info[INFO]
Available during race and sprint sessions in Replay Mode, and during live F1TV Auth timing when the required extra live data is available.
:::


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
