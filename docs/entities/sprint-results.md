---
id: sprint-results
title: "Sprint Results"
description: "Sprint classification results \u2014 state, attributes, and examples for F1 Sensor."
---

Sprint classification results. Use `sensor.f1_sprint_results` in dashboards, templates, and automations.

This reference covers the state and attributes. For setup, see [Configuration](/getting-started/add-integration).

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

Classification results for all sprint sessions in the current season.

**State**
- Integer: number of sprint races with results, or `0` when none are available.

**Example**
```text
6
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| races | list | List of sprint races with results |

Each entry in `races` contains:

| Field | Type | Description |
| --- | --- | --- |
| round | string | Round number |
| race_name | string | Grand Prix name |
| results | list | List of classification results |

Each entry in `results` contains:

| Field | Type | Description |
| --- | --- | --- |
| number | string | Car number |
| grid | string | Sprint starting grid position |
| position | string | Final position |
| laps | string | Completed laps |
| time | string | Total time or gap supplied by Jolpica |
| points | string | Points awarded |
| status | string | Finish status |
| driver | object | `{ permanentNumber, code, givenName, familyName }` |
| constructor | object | `{ name }` |


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
