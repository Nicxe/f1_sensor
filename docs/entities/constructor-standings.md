---
id: constructor-standings
title: "Constructor Standings"
description: "Current constructor standings \u2014 state, attributes, and examples for F1 Sensor."
---

Current constructor standings. Use `sensor.f1_constructor_standings` in dashboards, templates, and automations.

This reference covers the state and attributes. For setup, see [Configuration](/getting-started/add-integration).

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`sensor.f1_constructor_standings` - Constructor standings snapshot from Ergast.

**State**

- Integer: number of constructors in the standings list.

**Example**
```text
10
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| round | string | Round of the standings snapshot |
| constructor_standings | list | Ergast “ConstructorStandings” array (positions, points, wins, constructor info) |

## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
