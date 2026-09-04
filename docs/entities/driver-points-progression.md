---
id: driver-points-progression
title: "Driver Points Progression"
description: "Drivers Point Progression \u2014 state, attributes, and examples for F1 Sensor."
---

Follow driver championship points across race rounds. Use `sensor.f1_driver_points_progression` in dashboards, templates, and automations.

This reference covers the state and attributes. For setup, see [Configuration](/getting-started/add-integration).

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`sensor.f1_driver_points_progression` - Per‑round driver points (including sprint) with cumulative series, suitable for charts.

**State**

  - Integer: number of rounds covered.

**Example**
```text
12
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| rounds | list | List of rounds with metadata |
| drivers | object | Map of driver codes to their progression data |
| series | object | Progression series data for charts |

Each entry in `rounds` contains:

| Field | Type | Description |
| --- | --- | --- |
| round | string | Round number |
| race_name | string | Grand Prix name |
| date | string | Race date (YYYY-MM-DD) |

Each entry in `drivers` (keyed by driver code) contains:

| Field | Type | Description |
| --- | --- | --- |
| name | string | Driver's full name |
| code | string | Three-letter driver code |
| driverId | string | Driver identifier |
| points_by_round | list | Points scored in each round |
| cumulative_points | list | Running total of points after each round |
| wins_by_round | list | Wins per round (1 or 0) |
| totals | object | `{ points, wins }` - season totals |

The `series` object contains:

| Field | Type | Description |
| --- | --- | --- |
| labels | list | Round labels for chart X-axis (e.g., ["R1", "R2", ...]) |
| series | list | Array of series objects for charting |

Each entry in `series.series` contains:

| Field | Type | Description |
| --- | --- | --- |
| key | string | Driver code |
| name | string | Driver's full name |
| data | list | Points per round |
| cumulative | list | Cumulative points per round |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "season": "2025",
  "rounds": [
    { "round": "1", "race_name": "Bahrain Grand Prix", "date": "2025-03-02" },
    { "round": "2", "race_name": "Saudi Arabian Grand Prix", "date": "2025-03-09" },
    { "round": "3", "race_name": "Australian Grand Prix", "date": "2025-03-23" }
  ],
  "drivers": {
    "VER": {
      "name": "Max Verstappen",
      "code": "VER",
      "driverId": "max_verstappen",
      "points_by_round": [25, 18, 25],
      "cumulative_points": [25, 43, 68],
      "wins_by_round": [1, 0, 1],
      "totals": {
        "points": 68,
        "wins": 2
      }
    },
    "HAM": {
      "name": "Lewis Hamilton",
      "code": "HAM",
      "driverId": "lewis_hamilton",
      "points_by_round": [18, 25, 15],
      "cumulative_points": [18, 43, 58],
      "wins_by_round": [0, 1, 0],
      "totals": {
        "points": 58,
        "wins": 1
      }
    }
  },
  "series": {
    "labels": ["R1", "R2", "R3"],
    "series": [
      {
        "key": "VER",
        "name": "Max Verstappen",
        "data": [25, 18, 25],
        "cumulative": [25, 43, 68]
      },
      {
        "key": "HAM",
        "name": "Lewis Hamilton",
        "data": [18, 25, 15],
        "cumulative": [18, 43, 58]
      }
    ]
  }
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get a driver's total points:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_points_progression', 'drivers') %}
{% if drivers and drivers.VER %}
  VER total: {{ drivers.VER.totals.points }} points, {{ drivers.VER.totals.wins }} wins
{% endif %}
```

**Get points scored in the last round:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_points_progression', 'drivers') %}
{% if drivers and drivers.VER %}
  {% set pts = drivers.VER.points_by_round %}
  Last round: {{ pts[-1] if pts else 0 }} points
{% endif %}
```

**List rounds with names:**
```jinja2
{% set rounds = state_attr('sensor.f1_driver_points_progression', 'rounds') %}
{% for r in rounds %}
  R{{ r.round }}: {{ r.race_name }} ({{ r.date }})
{% endfor %}
```

**Calculate points gained in last 3 rounds:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_points_progression', 'drivers') %}
{% set ver = drivers.VER %}
{% if ver %}
  {% set last_3 = ver.points_by_round[-3:] | sum %}
  VER last 3 rounds: {{ last_3 }} points
{% endif %}
```

**Get driver with most wins:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_points_progression', 'drivers') %}
{% set winner = drivers.values() | sort(attribute='totals.wins', reverse=true) | first %}
{% if winner %}
  Most wins: {{ winner.code }} with {{ winner.totals.wins }}
{% endif %}
```

</details>
:::tip[Season progression card]
Use this entity with the bundled [F1 Season Progression Card](/cards/season-progression) to show driver championship point progression without installing another chart card.
:::


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
