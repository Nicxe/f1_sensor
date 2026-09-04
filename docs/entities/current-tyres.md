---
id: current-tyres
title: "Current Tyres"
description: "Current tyre compound per driver \u2014 state, attributes, and examples for F1 Sensor."
---

See the tyre compound currently fitted to each driver’s car. Use `sensor.f1_current_tyres` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

Shows the current tyre compound for each driver in the active session.

**State**
- Integer: number of drivers with tyre information available.

**Example**
```text
20
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| drivers | list | List of driver tyre information, sorted by car number |

Each entry in `drivers` contains:

| Field | Type | Description |
| --- | --- | --- |
| racing_number | string | Car number |
| tla | string | Three-letter abbreviation (driver code) |
| team_color | string | Team color as hex code (e.g., "#3671C6") |
| team_color_rgb | list | Team color as RGB values (e.g., `[54, 113, 198]`) |
| position | string | Current position in the session |
| compound | string | Tyre compound name (e.g., "SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET") |
| compound_short | string | Single-letter abbreviation ("S", "M", "H", "I", "W") |
| compound_color | string | Hex color code for the compound (e.g., "#FF0000" for soft) |
| compound_color_rgb | list | Compound color as RGB values (e.g., `[255, 0, 0]` for soft) |
| new | boolean | Whether the tyres are brand new |
| stint_laps | number | Number of laps on the current set |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "drivers": [
    {
      "racing_number": "1",
      "tla": "VER",
      "team_color": "#3671C6",
      "team_color_rgb": [54, 113, 198],
      "position": "1",
      "compound": "MEDIUM",
      "compound_short": "M",
      "compound_color": "#FFFF00",
      "compound_color_rgb": [255, 255, 0],
      "new": false,
      "stint_laps": 15
    },
    {
      "racing_number": "44",
      "tla": "HAM",
      "team_color": "#ED1131",
      "team_color_rgb": [237, 17, 49],
      "position": "2",
      "compound": "HARD",
      "compound_short": "H",
      "compound_color": "#FFFFFF",
      "compound_color_rgb": [255, 255, 255],
      "new": true,
      "stint_laps": 3
    },
    {
      "racing_number": "4",
      "tla": "NOR",
      "team_color": "#FF8000",
      "team_color_rgb": [255, 128, 0],
      "position": "3",
      "compound": "SOFT",
      "compound_short": "S",
      "compound_color": "#FF0000",
      "compound_color_rgb": [255, 0, 0],
      "new": true,
      "stint_laps": 1
    }
  ]
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get a driver's current tyre:**
```jinja2
{% set drivers = state_attr('sensor.f1_current_tyres', 'drivers') %}
{% set ver = drivers | selectattr('tla', 'eq', 'VER') | first %}
{% if ver %}
  VER on {{ ver.compound }} ({{ ver.stint_laps }} laps{% if ver.new %}, NEW{% endif %})
{% endif %}
```

**Count drivers on each compound:**
```jinja2
{% set drivers = state_attr('sensor.f1_current_tyres', 'drivers') %}
{% if drivers %}
  SOFT: {{ drivers | selectattr('compound', 'eq', 'SOFT') | list | length }}
  MEDIUM: {{ drivers | selectattr('compound', 'eq', 'MEDIUM') | list | length }}
  HARD: {{ drivers | selectattr('compound', 'eq', 'HARD') | list | length }}
{% endif %}
```

**List drivers on fresh tyres:**
```jinja2
{% set drivers = state_attr('sensor.f1_current_tyres', 'drivers') %}
{% for d in drivers if d.new %}
  {{ d.tla }} - fresh {{ d.compound }}
{% endfor %}
```

**Find driver with most laps on current stint:**
```jinja2
{% set drivers = state_attr('sensor.f1_current_tyres', 'drivers') %}
{% if drivers %}
  {% set longest = drivers | sort(attribute='stint_laps', reverse=true) | first %}
  {{ longest.tla }} has {{ longest.stint_laps }} laps on {{ longest.compound }}
{% endif %}
```

**Create a tyre summary with colors:**
```jinja2
{% set drivers = state_attr('sensor.f1_current_tyres', 'drivers') %}
{% for d in drivers | sort(attribute='position') %}
  P{{ d.position }} {{ d.tla }}: {{ d.compound_short }} ({{ d.stint_laps }} laps)
{% endfor %}
```

</details>


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
