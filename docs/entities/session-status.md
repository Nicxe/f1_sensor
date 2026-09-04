---
id: session-status
title: "Session Status"
description: "Current session phase \u2014 state, attributes, and examples for F1 Sensor."
---

Current session phase. Use `sensor.f1_session_status` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

Semantic session lifecycle based on the live Session Status. The `pre` state usually occurs 60–15 minutes before a session begins. The sensor goes `live` when the session officially starts, for races, this means lights out, not the beginning of the formation lap.


**State (enum)**
- One of: `pre`, `live`, `suspended`, `break`, `finished`, `finalised`, `ended`.

**Example**
```text
live
```


**Typical transitions**
`pre → live → suspended ↔ live → finished → finalised → ended`
After finalised or ended, logic resets and next session begins at **pre**.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| meeting_name | string | Meeting name (e.g., "Monaco Grand Prix") |
| meeting_location | string | Meeting location (e.g., "Monte Carlo") |
| meeting_country | string | Meeting country (e.g., "Monaco") |
| circuit_short_name | string | Circuit short name (e.g., "Monaco") |
| gmt_offset | string | Event GMT offset |
| start | string | Session start ISO‑8601 |
| end | string | Session end ISO‑8601 |
| track_grip | string | Track grip state from Race Control, when available (best effort) |


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
