---
id: safety-car
title: "Safety Car"
description: "Safety Car (SC) or Virtual Safety Car (VSC) is active \u2014 state, attributes, and examples for F1 Sensor."
---

Safety Car (SC) or Virtual Safety Car (VSC) is active. Use `binary_sensor.f1_safety_car` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

On while the Safety Car or Virtual Safety Car is in effect.

**State (on/off)**
- `on` when track status is `SC` or `VSC`; otherwise `off`.

**Example**
```text
on
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| track_status | string | Normalized track status (`CLEAR`, `YELLOW`, `VSC`, `SC`, `RED`) |


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
