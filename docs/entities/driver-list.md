---
id: driver-list
title: "Driver List"
description: "Show list and details on all drivers, including team color, headshot URL etc \u2014 state, attributes, and examples for F1 Sensor."
---

Look up drivers, team colors, and headshots for your dashboard. Use `sensor.f1_driver_list` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

Live roster of drivers with identity and team information for the session.

**State**
- Integer: number of drivers in the list.

**Example**
```text
20
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| drivers | list | List of driver information, sorted by car number |

Each entry in `drivers` contains:

| Field | Type | Description |
| --- | --- | --- |
| racing_number | string | Car number |
| tla | string | Three-letter abbreviation (driver code) |
| name | string | Full name |
| first_name | string | First name |
| last_name | string | Last name |
| team | string | Team name |
| team_color | string | Team color as hex code (e.g., "#3671C6") |
| team_color_rgb | list | Team color as RGB values (e.g., `[54, 113, 198]`) |
| headshot_small | string | URL to small driver headshot image |
| headshot_large | string | URL to large driver headshot image |
| reference | string | External reference URL or ID |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "drivers": [
    {
      "racing_number": "1",
      "tla": "VER",
      "name": "Max VERSTAPPEN",
      "first_name": "Max",
      "last_name": "Verstappen",
      "team": "Red Bull Racing",
      "team_color": "#3671C6",
      "team_color_rgb": [54, 113, 198],
      "headshot_small": "https://media.formula1.com/content/dam/fom-website/drivers/M/MAXVER01_Max_Verstappen/maxver01.png",
      "headshot_large": "https://media.formula1.com/content/dam/fom-website/drivers/M/MAXVER01_Max_Verstappen/maxver01-large.png",
      "reference": "max_verstappen"
    },
    {
      "racing_number": "44",
      "tla": "HAM",
      "name": "Lewis HAMILTON",
      "first_name": "Lewis",
      "last_name": "Hamilton",
      "team": "Ferrari",
      "team_color": "#ED1131",
      "team_color_rgb": [237, 17, 49],
      "headshot_small": "https://media.formula1.com/content/dam/fom-website/drivers/L/LEWHAM01_Lewis_Hamilton/lewham01.png",
      "headshot_large": "https://media.formula1.com/content/dam/fom-website/drivers/L/LEWHAM01_Lewis_Hamilton/lewham01-large.png",
      "reference": "lewis_hamilton"
    }
  ]
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get a driver's headshot URL:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_list', 'drivers') %}
{% set ver = drivers | selectattr('tla', 'eq', 'VER') | first %}
{% if ver %}
  {{ ver.headshot_large }}
{% endif %}
```

**Get team color for styling:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_list', 'drivers') %}
{% set driver = drivers | selectattr('racing_number', 'eq', '44') | first %}
{% if driver %}
  background-color: {{ driver.team_color }};
{% endif %}
```

**Set a light to a driver's team color:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_list', 'drivers') %}
{% set ver = drivers | selectattr('tla', 'eq', 'VER') | first %}
{% if ver and ver.team_color_rgb %}
service: light.turn_on
data:
  entity_id: light.living_room
  rgb_color: {{ ver.team_color_rgb }}
{% endif %}
```

**List all drivers for a team:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_list', 'drivers') %}
{% for d in drivers if d.team == 'Ferrari' %}
  {{ d.name }} (#{{ d.racing_number }})
{% endfor %}
```

**Create a driver lookup by TLA:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_list', 'drivers') %}
{% set lookup = dict.from_keys(drivers | map(attribute='tla') | list, drivers) %}
{{ lookup.VER.name }} drives for {{ lookup.VER.team }}
```

**Generate image elements for all drivers:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_list', 'drivers') %}
{% for d in drivers %}
  <img src="{{ d.headshot_small }}" alt="{{ d.name }}" style="border: 2px solid {{ d.team_color }}">
{% endfor %}
```

</details>
:::tip[Headshot Images]
The headshot URLs are provided by F1 and may change between sessions. This sensor retains its last known state between sessions to support dashboard graphics even when no session is active.
:::


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
