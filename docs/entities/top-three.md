---
id: top-three
title: "Top Three"
description: "Dedicated sensors for current P1, P2 and P3 \u2014 state, attributes, and examples for F1 Sensor."
---

Dedicated sensors for current P1, P2 and P3. Use `sensor.f1_top_three_p1`, `sensor.f1_top_three_p2`, and `sensor.f1_top_three_p3` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

Three dedicated sensors for the current P1, P2, and P3 positions: `sensor.f1_top_three_p1`, `sensor.f1_top_three_p2`, and `sensor.f1_top_three_p3`.

**State**
- Driver TLA code (e.g., "VER", "HAM", "NOR"), or `unknown` when data is withheld or unavailable.

**Example**
```text
VER
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| withheld | boolean | Whether the position is currently withheld by broadcast rules |
| position | number | Position in the standings (1, 2, or 3) |
| racing_number | string | Car number |
| tla | string | Three-letter abbreviation (driver code) |
| broadcast_name | string | Name as shown on broadcast |
| full_name | string | Driver's full name |
| first_name | string | Driver's first name |
| last_name | string | Driver's last name |
| team | string | Team name |
| team_color | string | Team color as hex code (e.g., "#3671C6") |
| team_color_rgb | list | Team color as RGB values (e.g., `[54, 113, 198]`) |
| lap_time | string | Current lap time when available |
| overall_fastest | boolean | Whether this is the overall fastest lap |
| personal_fastest | boolean | Whether this is the driver's personal best |
| last_update_ts | string | ISO‑8601 timestamp of the last update |
:::info[INFO]
Available during qualifying, sprint, and race sessions. When the broadcast withholds position data (common at session start), the `withheld` attribute will be `true` and the state will be `unknown`.
:::


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
