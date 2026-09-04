---
id: race-lap
title: "Race Lap"
description: "Current race lap number \u2014 state, attributes, and examples for F1 Sensor."
---

Current race lap number. Use `sensor.f1_race_lap_count` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

Current lap and total laps during the race.

**State**
  - Integer: current lap, or `unknown` if none available or stale cleared.

**Example**
```text
23
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| total_laps | number | Total laps when known; preserved across updates |
:::info[Info]
This sensor is active only during sprint and race sessions.
:::

## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
