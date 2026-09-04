---
id: current-season
title: "Current Season"
description: "Full race schedule \u2014 state, attributes, and examples for F1 Sensor."
---

Full race schedule. Use `sensor.f1_current_season` in dashboards, templates, and automations.

This reference covers the state and attributes. For setup, see [Configuration](/getting-started/add-integration).

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`sensor.f1_current_season` - Number of races in the current season.

**State**

  - Integer: count of races in the season.

**Example**
```text
24
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| races | list | Enriched races array for the season |

Each entry in `races` contains the standard Ergast race data plus:

| Field | Type | Description |
| --- | --- | --- |
| country_code | string | ISO country code (e.g., "GB", "IT", "US") |
| country_flag_url | string | URL to country flag image |
| circuit_map_url | string | URL to official circuit map image |
| circuit_outline_url | string | URL to circuit outline image when available |


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
