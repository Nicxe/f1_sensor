---
id: overtake-mode
title: "Overtake Mode"
description: "ON when track-wide overtake mode is enabled (2026 regulation, experimental) \u2014 state, attributes, and examples for F1 Sensor."
---

Check whether track-wide overtake mode is enabled. This 2026 feature is experimental. Use `binary_sensor.f1_overtake_mode` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

:::warning[Experimental — 2026 regulation]
This sensor is based on data observed during 2026 pre-season testing. It should be considered experimental until confirmed against live race conditions. The exact message format from Formula 1 may be adjusted in a future update once the first race weekend has been evaluated.
:::

`binary_sensor.f1_overtake_mode` - Indicates whether the track-wide overtake mode is currently enabled. This is a 2026 Formula 1 regulation feature that allows a driver who was within one second of the car ahead at the final corner detection point to deploy an additional 0.5 MJ of electrical energy on the following straight.

**State (on/off)**
- `on` when overtake mode is enabled track-wide; otherwise `off`.

**Example**
```text
on
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| straight_mode | string | Current straight mode state (`normal_grip`, `low_grip`, or `disabled`) |
| restored | boolean | True if the state was restored from history after a Home Assistant restart |
:::info[INFO]
Active only during sessions where the 2026 overtake mode regulation applies. The state is restored from history when Home Assistant restarts during an active session.
:::


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
