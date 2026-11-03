---
id: constructor-points-progression
title: "Constructor Points Progression"
description: "Constructors Point Progression \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Follow constructor championship points across race rounds.

<EntityMeta id="constructor-points-progression" />

<span id="state-and-attributes"></span>

`sensor.f1_constructor_points_progression` - Per‑round constructor points (including sprint) with cumulative series, suitable for charts.

## State

  - Integer: number of rounds covered.

**Example**
```text
12
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| rounds | list | List of rounds with metadata |
| constructors | object | Map of constructor IDs to their progression data |
| series | object | Progression series data for charts |

### `rounds` entries

| Field | Type | Description |
| --- | --- | --- |
| round | string | Round number |
| race_name | string | Grand Prix name |
| date | string | Race date (YYYY-MM-DD) |

### `constructors` entries (keyed by constructor ID)

| Field | Type | Description |
| --- | --- | --- |
| name | string | Team name |
| constructorId | string | Constructor identifier |
| points_by_round | list | Points scored in each round |
| cumulative_points | list | Running total of points after each round |
| wins_by_round | list | Wins per round |
| totals | object | `{ points, wins }` - season totals |

### `series` object

| Field | Type | Description |
| --- | --- | --- |
| labels | list | Round labels for chart X-axis (e.g., ["R1", "R2", ...]) |
| series | list | Array of series objects for charting |

### `series.series` entries

| Field | Type | Description |
| --- | --- | --- |
| key | string | Constructor ID |
| name | string | Team name |
| data | list | Points per round |
| cumulative | list | Cumulative points per round |

## Examples

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
  "constructors": {
    "red_bull": {
      "name": "Red Bull Racing",
      "constructorId": "red_bull",
      "points_by_round": [44, 33, 40],
      "cumulative_points": [44, 77, 117],
      "wins_by_round": [1, 0, 1],
      "totals": {
        "points": 117,
        "wins": 2
      }
    },
    "ferrari": {
      "name": "Ferrari",
      "constructorId": "ferrari",
      "points_by_round": [33, 44, 28],
      "cumulative_points": [33, 77, 105],
      "wins_by_round": [0, 1, 0],
      "totals": {
        "points": 105,
        "wins": 1
      }
    },
    "mclaren": {
      "name": "McLaren",
      "constructorId": "mclaren",
      "points_by_round": [28, 25, 33],
      "cumulative_points": [28, 53, 86],
      "wins_by_round": [0, 0, 0],
      "totals": {
        "points": 86,
        "wins": 0
      }
    }
  },
  "series": {
    "labels": ["R1", "R2", "R3"],
    "series": [
      {
        "key": "red_bull",
        "name": "Red Bull Racing",
        "data": [44, 33, 40],
        "cumulative": [44, 77, 117]
      },
      {
        "key": "ferrari",
        "name": "Ferrari",
        "data": [33, 44, 28],
        "cumulative": [33, 77, 105]
      }
    ]
  }
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get a team's total points:**
```jinja2
{% set constructors = state_attr('sensor.f1_constructor_points_progression', 'constructors') or {} %}
{% if constructors.get('red_bull') %}
  Red Bull total: {{ constructors.red_bull.totals.points }} points
{% endif %}
```

**Get points scored in the last round:**
```jinja2
{% set constructors = state_attr('sensor.f1_constructor_points_progression', 'constructors') or {} %}
{% set ferrari = constructors.get('ferrari') %}
{% if ferrari %}
  {% set pts = ferrari.points_by_round %}
  Ferrari last round: {{ pts[-1] if pts else 0 }} points
{% endif %}
```

**Calculate gap between two teams:**
```jinja2
{% set c = state_attr('sensor.f1_constructor_points_progression', 'constructors') or {} %}
{% if c.get('red_bull') and c.get('ferrari') %}
  {% set gap = c.red_bull.totals.points - c.ferrari.totals.points %}
  Red Bull leads Ferrari by {{ gap }} points
{% endif %}
```

**Get team with most wins:**
```jinja2
{% set constructors = state_attr('sensor.f1_constructor_points_progression', 'constructors') or {} %}
{% set winner = constructors.values() | sort(attribute='totals.wins', reverse=true) | first | default(none) %}
{% if winner %}
  Most wins: {{ winner.name }} with {{ winner.totals.wins }}
{% endif %}
```

**List all teams by points:**
```jinja2
{% set constructors = state_attr('sensor.f1_constructor_points_progression', 'constructors') or {} %}
{% for c in constructors.values() | sort(attribute='totals.points', reverse=true) %}
  {{ c.name }}: {{ c.totals.points }} pts
{% endfor %}
```

</details>
:::tip[Season progression]
Use the **Season progression** module in the [F1 Sensor card](/cards/cards-overview) to show constructor championship point progression without installing another chart card.
:::

## Related references

<span id="next-steps"></span>

<RelatedReferences id="constructor-points-progression" />
