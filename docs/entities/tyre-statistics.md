---
id: tyre-statistics
title: "Tyre Statistics"
description: "Aggregated tyre statistics per compound \u2014 state, attributes, and examples for F1 Sensor."
---

Aggregated tyre statistics per compound. Use `sensor.f1_tyre_statistics` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`sensor.f1_tyre_statistics` - Aggregated tyre performance statistics per compound, showing fastest times and usage across all drivers.

**State**
- String: name of the fastest compound (e.g., "SOFT"), or `unknown` when not available.

**Example**
```text
SOFT
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| fastest_time | string | Overall fastest lap time across all compounds |
| fastest_time_secs | number | Fastest lap time in seconds |
| deltas | object | Time delta to fastest for each compound (e.g., `{"MEDIUM": "+0.342", "HARD": "+0.891"}`) |
| start_compounds | list | List of compounds used at race start, one entry per driver with racing number and compound |
| compounds | object | Detailed statistics per compound |

Each entry in `compounds` (keyed by compound name) contains:

| Field | Type | Description |
| --- | --- | --- |
| best_times | list | Top 3 fastest lap times on this compound |
| total_laps | number | Total laps completed on this compound |
| sets_used | number | Number of new tyre sets used |
| sets_used_total | number | Total stints on this compound |
| compound_color | string | Hex color code for the compound |
| compound_color_rgb | list | Compound color as RGB values (e.g., `[255, 0, 0]` for soft) |

Each entry in `best_times` contains:

| Field | Type | Description |
| --- | --- | --- |
| time | string | Lap time (e.g., "1:31.234") |
| racing_number | string | Car number |
| tla | string | Driver code |

Each entry in `start_compounds` contains:

| Field | Type | Description |
| --- | --- | --- |
| racing_number | string | Car number |
| compound | string | Tyre compound used at race start |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "fastest_time": "1:31.234",
  "fastest_time_secs": 91.234,
  "deltas": {
    "SOFT": "+0.000",
    "MEDIUM": "+0.342",
    "HARD": "+0.891"
  },
  "start_compounds": [
    { "racing_number": "1", "compound": "MEDIUM" },
    { "racing_number": "44", "compound": "HARD" },
    { "racing_number": "4", "compound": "MEDIUM" }
  ],
  "compounds": {
    "SOFT": {
      "best_times": [
        { "time": "1:31.234", "racing_number": "1", "tla": "VER" },
        { "time": "1:31.456", "racing_number": "4", "tla": "NOR" },
        { "time": "1:31.567", "racing_number": "44", "tla": "HAM" }
      ],
      "total_laps": 45,
      "sets_used": 8,
      "sets_used_total": 12,
      "compound_color": "#FF0000",
      "compound_color_rgb": [255, 0, 0]
    },
    "MEDIUM": {
      "best_times": [
        { "time": "1:31.576", "racing_number": "1", "tla": "VER" },
        { "time": "1:31.789", "racing_number": "16", "tla": "LEC" }
      ],
      "total_laps": 120,
      "sets_used": 15,
      "sets_used_total": 20,
      "compound_color": "#FFFF00",
      "compound_color_rgb": [255, 255, 0]
    },
    "HARD": {
      "best_times": [
        { "time": "1:32.125", "racing_number": "63", "tla": "RUS" }
      ],
      "total_laps": 80,
      "sets_used": 6,
      "sets_used_total": 8,
      "compound_color": "#FFFFFF",
      "compound_color_rgb": [255, 255, 255]
    }
  }
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get the fastest compound:**
```jinja2
Fastest compound: {{ states('sensor.f1_tyre_statistics') }}
```

**Get fastest time on a specific compound:**
```jinja2
{% set compounds = state_attr('sensor.f1_tyre_statistics', 'compounds') %}
{% if compounds and compounds.SOFT %}
  {% set best = compounds.SOFT.best_times | first %}
  Fastest on SOFT: {{ best.time }} by {{ best.tla }}
{% endif %}
```

**Show delta between compounds:**
```jinja2
{% set deltas = state_attr('sensor.f1_tyre_statistics', 'deltas') %}
{% if deltas %}
  MEDIUM vs SOFT: {{ deltas.MEDIUM | default('N/A') }}
  HARD vs SOFT: {{ deltas.HARD | default('N/A') }}
{% endif %}
```

**Count drivers who started on each compound:**
```jinja2
{% set starts = state_attr('sensor.f1_tyre_statistics', 'start_compounds') %}
{% if starts %}
  {% set mediums = starts | selectattr('compound', 'eq', 'MEDIUM') | list | length %}
  {% set hards = starts | selectattr('compound', 'eq', 'HARD') | list | length %}
  Started on MEDIUM: {{ mediums }}
  Started on HARD: {{ hards }}
{% endif %}
```

**Get total laps on all compounds:**
```jinja2
{% set compounds = state_attr('sensor.f1_tyre_statistics', 'compounds') %}
{% if compounds %}
  {% set total = namespace(laps=0) %}
  {% for name, data in compounds.items() %}
    {% set total.laps = total.laps + (data.total_laps | default(0)) %}
  {% endfor %}
  Total tyre laps recorded: {{ total.laps }}
{% endif %}
```

</details>
:::tip[Compound Colors]
Use the `compound_color` field to style your dashboard elements. The colors match the official Pirelli tyre colors: SOFT (red), MEDIUM (yellow), HARD (white), INTERMEDIATE (green), WET (blue).
:::


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
