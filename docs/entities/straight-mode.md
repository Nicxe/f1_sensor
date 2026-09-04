---
id: straight-mode
title: "Straight Mode"
description: "Active aerodynamic straight mode state (2026 regulation, experimental) \u2014 state, attributes, and examples for F1 Sensor."
---

Active aerodynamic straight mode state (2026 regulation, experimental). Use `sensor.f1_straight_mode` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

:::warning[Experimental — 2026 regulation]
This sensor is based on data observed during 2026 pre-season testing. It should be considered experimental until confirmed against live race conditions. The exact message format from Formula 1 may be adjusted in a future update once the first race weekend has been evaluated.
:::

`sensor.f1_straight_mode` - Shows the track-wide active aerodynamic permission for straight sections, broadcasted via Race Control messages. This is a 2026 Formula 1 regulation feature where the car's aerodynamic profile on designated straight sections of the circuit is regulated by the FIA.

**State (enum)**
- One of: `normal_grip`, `low_grip`, `disabled`.

| Value | Description |
| --- | --- |
| `normal_grip` | Normal aerodynamic configuration permitted on straight sections |
| `low_grip` | Restricted aerodynamic configuration on straight sections |
| `disabled` | Straight mode system is not active |

**Example**
```text
normal_grip
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| overtake_enabled | boolean | Whether overtake mode is currently enabled |
| restored | boolean | True if the state was restored from history after a Home Assistant restart |
:::info[INFO]
Active only during sessions where the 2026 straight mode regulation applies. The state is restored from history when Home Assistant restarts during an active session.
:::

## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
