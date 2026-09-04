---
id: track-status
title: "Track Status"
description: "Current track status \u2014 state, attributes, and examples for F1 Sensor."
---

Current track status. Use `sensor.f1_track_status` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

Current track status from live or replay timing. Outside an active data window the entity can become unavailable; do not interpret a previous `CLEAR` value as confirmation that a session is running.

**State (enum)**
  - One of: `CLEAR`, `YELLOW`, `VSC`, `SC`, `RED`.

**Example**
```text
CLEAR
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| (none) |  | No extra attributes |


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
