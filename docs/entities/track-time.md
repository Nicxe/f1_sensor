---
id: track-time
title: "Track Time"
description: "Current local time at the next race circuit \u2014 state, attributes, and examples for F1 Sensor."
---

Current local time at the next race circuit. Use `sensor.f1_track_time` in dashboards, templates, and automations.

This reference covers the state and attributes. For setup, see [Configuration](/getting-started/add-integration).

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`sensor.f1_track_time` - Current local time at the next race circuit.

**State**
- String: local time at the circuit, formatted as `HH:MM`, or `unknown`.

**Example**
```text
14:05
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| timezone | string | Circuit timezone (IANA, best effort) |
| utc_offset | string | UTC offset at the circuit, formatted as `+HHMM` |
| offset_from_home | string | Difference between circuit time and Home Assistant time (best effort) |
| circuit_name | string | Circuit name |
| circuit_locality | string | City/area |
| circuit_country | string | Country |


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
