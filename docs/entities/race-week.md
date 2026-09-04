---
id: race-week
title: "Race Week"
description: "on during race week \u2014 state, attributes, and examples for F1 Sensor."
---

on during race week. Use `binary_sensor.f1_race_week` in dashboards, templates, and automations.

This reference covers the state and attributes. For setup, see [Configuration](/getting-started/add-integration).

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`binary_sensor.f1_race_week` - True when the next race is scheduled in the current calendar week.

**State (on/off)**
- `on` during weeks containing the next race date; otherwise `off`.

**Example**
```text
on
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| days_until_next_race | number | Days from today to the next race date |
| next_race_name | string | Grand Prix name of the next race |


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
