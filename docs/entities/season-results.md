---
id: season-results
title: "Season Results"
description: "All season race results \u2014 state, attributes, and examples for F1 Sensor."
---

All season race results. Use `sensor.f1_season_results` in dashboards, templates, and automations.

This reference covers the state and attributes. For setup, see [Configuration](/getting-started/add-integration).

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`sensor.f1_season_results` - All results across the current season.

**State**

  - Integer: number of races with results.

**Example**
```text
22
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| races | list | For each race: `{round, race_name, results:[...]}` where each result has the same shape as in [Last Race Results](/entities/last-race-results), including the `grid` field |
:::warning[Known Issue]
`sensor.f1_season_results` may trigger a warning in the Home Assistant logs:

```text
Logger: homeassistant.components.recorder.db_schema
Source: components/recorder/db_schema.py:663
Integration: Recorder
State attributes for sensor.f1_season_results exceed maximum size of 16384 bytes. This can cause database performance issues; Attributes will not be stored
```

Despite the warning, the sensor should still work fine for display in the frontend. However, to avoid any database load/performance issues, it is recommended to **exclude this sensor from being recorded** in your `recorder:` config:

```yaml
recorder:
  exclude:
    entities:
      - sensor.f1_season_results
```
:::

## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
