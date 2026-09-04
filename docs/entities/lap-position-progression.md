---
id: lap-position-progression
title: "Lap Position Progression"
description: "Post-race lap position progression \u2014 state, attributes, and examples for F1 Sensor."
---

Post-race lap position progression. Use `sensor.f1_lap_position_progression` in dashboards, templates, and automations.

This reference covers the state and attributes. For setup, see [Configuration](/getting-started/add-integration).

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`sensor.f1_lap_position_progression` - Lightweight post-race session metadata for the bundled lap position chart.

**State**

  - Integer: number of sessions included in the attributes. This includes race sessions that can be loaded on demand and sprint sessions that are explicitly marked `unsupported`.

**Example**
```text
18
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| source | string | Data source, currently `jolpica` |
| updated_at | string | Last coordinator update time as an ISO-8601 timestamp |
| data_mode | string | `metadata`; chart data is loaded on demand instead of stored in state attributes |
| session_data_api | string | `websocket` |
| session_data_type | string | WebSocket command type used by the bundled card: `f1_sensor/lap_position/session` |
| sessions | list | Race and sprint session metadata for the current season |

Each entry in `sessions` contains:

| Field | Type | Description |
| --- | --- | --- |
| key | string | Stable session key such as `race:2026:1` or `sprint:2026:5` |
| type | string | `race` or `sprint` |
| status | string | Metadata status. Main races with classification data use `available`; sprint sessions without lap data use `unsupported` |
| source | string | Source detail such as `jolpica_laps` or `jolpica_sprint_results` |
| reason | string | Explanation for `unsupported` sessions |
| season | string | Season year |
| round | string | Round number |
| race_name | string | Grand Prix name |
| date | string | Session date (YYYY-MM-DD) |
| total_laps | number | `null` in metadata; populated only in the on-demand chart payload |
| driver_count | number | Number of classified drivers when available from results metadata |

Main race lap positions come from Jolpica race lap timing data, but they are not stored in this sensor's attributes. The bundled card asks the integration backend for one selected race at a time through Home Assistant's WebSocket API, so Home Assistant does not have to broadcast an entire season of lap-by-lap positions in `hass.states`.

Sprint sessions can appear in the model so the dashboard selector matches the season, but they are marked `unsupported` because Jolpica exposes sprint classification results, not sprint lap-by-lap positions.

:::info[Recorder behavior]
The `sessions` attribute is intentionally metadata-only and is excluded from Home Assistant Recorder by the integration. Chart-ready driver positions are delivered on demand to the bundled card and are not stored as entity state attributes.
:::

:::tip[Lap position card]
Use this entity with the bundled [F1 Lap Position Progression Card](/cards/lap-position-progression) to show a native post-race lap position chart without installing another chart card.
:::


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
