---
id: investigations
title: "Investigations"
description: "Active steward investigations and pending penalties \u2014 state, attributes, and examples for F1 Sensor."
---

Active steward investigations and pending penalties. Use `sensor.f1_investigations` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`sensor.f1_investigations` - Active steward investigations and pending penalties. Shows only currently relevant information with automatic lifecycle management.

**State**
- Integer: count of actionable items (noted incidents + under investigation + pending penalties).

**Example**
```text
3
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| noted | list | Incidents noted but not yet under investigation |
| under_investigation | list | Active steward investigations |
| no_further_action | list | Recent NFI decisions (auto-expire after 5 minutes) |
| penalties | list | Penalties issued but not yet served |
| last_update | string | ISO-8601 timestamp of last update |

Each entry in `noted` and `under_investigation` contains:

| Field | Type | Description |
| --- | --- | --- |
| utc | string | ISO-8601 timestamp when the incident was noted |
| lap | number | Lap number when the incident occurred |
| drivers | list | Driver TLAs involved (sorted alphabetically) |
| racing_numbers | list | Car numbers involved |
| location | string | Location such as "TURN 7", "PIT LANE" (or null) |
| reason | string | Reason such as "CAUSING A COLLISION", "LEAVING THE TRACK AND GAINING AN ADVANTAGE" (or null) |
| after_race | boolean | Whether the investigation will happen after the race (only in `under_investigation`) |

Each entry in `no_further_action` contains the same fields plus:

| Field | Type | Description |
| --- | --- | --- |
| nfi_utc | string | ISO-8601 timestamp when NFI was decided (used for auto-expiry) |

Each entry in `penalties` contains:

| Field | Type | Description |
| --- | --- | --- |
| driver | string | Driver TLA who received the penalty |
| racing_number | string | Car number |
| penalty | string | Penalty type (e.g., "5 SECOND TIME PENALTY", "DRIVE THROUGH PENALTY") |
| reason | string | Reason for the penalty |
| utc | string | ISO-8601 timestamp when penalty was issued |
| lap | number | Lap number when penalty was issued |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "noted": [
    {
      "utc": "2025-12-07T13:30:57Z",
      "lap": 19,
      "drivers": ["LEC", "RUS"],
      "racing_numbers": ["16", "63"],
      "location": "TURN 9",
      "reason": "MOVING UNDER BRAKING"
    }
  ],
  "under_investigation": [
    {
      "utc": "2025-12-07T13:40:46Z",
      "lap": 25,
      "drivers": ["NOR", "TSU"],
      "racing_numbers": ["4", "22"],
      "location": "TURN 5",
      "reason": "FORCING ANOTHER DRIVER OFF THE TRACK",
      "after_race": false
    }
  ],
  "no_further_action": [
    {
      "utc": "2025-12-07T13:06:50Z",
      "lap": 3,
      "drivers": ["ALB", "HAM"],
      "racing_numbers": ["23", "44"],
      "location": "TURN 7",
      "reason": "LEAVING THE TRACK AND GAINING AN ADVANTAGE",
      "nfi_utc": "2025-12-07T13:12:53Z"
    }
  ],
  "penalties": [
    {
      "driver": "TSU",
      "racing_number": "22",
      "penalty": "5 SECOND TIME PENALTY",
      "reason": "MORE THAN ONE CHANGE OF DIRECTION",
      "utc": "2025-12-07T13:46:38Z",
      "lap": 29
    },
    {
      "driver": "ALB",
      "racing_number": "23",
      "penalty": "5 SECOND TIME PENALTY",
      "reason": "SPEEDING IN THE PIT LANE",
      "utc": "2025-12-07T14:00:05Z",
      "lap": 38
    }
  ],
  "last_update": "2025-12-07T14:00:05Z"
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Check if a driver is under investigation:**
```jinja2
{% set investigations = state_attr('sensor.f1_investigations', 'under_investigation') %}
{% set ver_involved = investigations | selectattr('drivers', 'contains', 'VER') | list %}
{% if ver_involved | length > 0 %}
  VER is under investigation!
{% endif %}
```

**List all pending penalties:**
```jinja2
{% set penalties = state_attr('sensor.f1_investigations', 'penalties') %}
{% for p in penalties %}
  {{ p.driver }}: {{ p.penalty }} ({{ p.reason }})
{% endfor %}
```

**Count active investigations:**
```jinja2
{% set noted = state_attr('sensor.f1_investigations', 'noted') | length %}
{% set investigating = state_attr('sensor.f1_investigations', 'under_investigation') | length %}
Noted: {{ noted }}, Under Investigation: {{ investigating }}
```

**Get post-race investigations:**
```jinja2
{% set investigations = state_attr('sensor.f1_investigations', 'under_investigation') %}
{% for inv in investigations if inv.after_race %}
  {{ inv.drivers | join(' vs ') }} - {{ inv.reason }} (after race)
{% endfor %}
```

**Show recent NFI decisions:**
```jinja2
{% set nfi = state_attr('sensor.f1_investigations', 'no_further_action') %}
{% for item in nfi %}
  {{ item.drivers | join('/') }}: No Further Action ({{ item.reason }})
{% endfor %}
```

**Create investigation summary:**
```jinja2
{% set sensor = 'sensor.f1_investigations' %}
{% set total = states(sensor) | int %}
{% if total > 0 %}
  {{ total }} active matter{{ 's' if total > 1 else '' }}:
  {% set penalties = state_attr(sensor, 'penalties') %}
  {% for p in penalties %}
    - {{ p.driver }}: {{ p.penalty }}
  {% endfor %}
{% else %}
  No active investigations
{% endif %}
```

</details>
:::info[Incident Lifecycle]
- **NOTED** → Stays until escalated to UNDER INVESTIGATION, resolved as NFI, or penalized
- **UNDER INVESTIGATION** → Stays until resolved as NFI or penalty issued
- **NO FURTHER ACTION** → Auto-expires after 5 minutes of session time
- **PENALTY** → Stays until PENALTY SERVED message received
:::


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
