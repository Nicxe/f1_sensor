---
id: track-limits
title: "Track Limits"
description: "Track limits violations per driver (deletions, warnings, penalties) \u2014 state, attributes, and examples for F1 Sensor."
---

Track limits violations per driver (deletions, warnings, penalties). Use `sensor.f1_track_limits` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`sensor.f1_track_limits` - Aggregated track limits violations per driver, including deleted lap times, black and white flag warnings, and penalties.

**State**
- Integer: total number of track limit violations (deletions + warnings) in this session.

**Example**
```text
12
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| by_driver | object | Map of driver TLAs to their violation data |
| total_deletions | number | Total count of deleted times/laps across all drivers |
| total_warnings | number | Count of BLACK AND WHITE flags issued for track limits |
| total_penalties | number | Count of track limits penalties issued |
| last_update | string | ISO-8601 timestamp of last update |

Each entry in `by_driver` (keyed by driver TLA) contains:

| Field | Type | Description |
| --- | --- | --- |
| racing_number | string | Car number |
| deletions | number | Number of times/laps deleted for this driver |
| warning | boolean | Whether a BLACK AND WHITE flag has been shown |
| penalty | string | Penalty text if issued (e.g., "5 SECOND TIME PENALTY"), or null |
| violations | list | Detailed list of all violations |

Each entry in `violations` contains:

| Field | Type | Description |
| --- | --- | --- |
| utc | string | ISO-8601 timestamp of the violation |
| lap | number | Lap number when violation occurred |
| turn | number | Turn number where violation occurred (for deletions) |
| type | string | Violation type: `time_deleted`, `warning`, or `penalty` |
| penalty | string | Penalty text (only present when type is `penalty`) |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "by_driver": {
    "HAM": {
      "racing_number": "44",
      "deletions": 3,
      "warning": true,
      "penalty": null,
      "violations": [
        { "utc": "2025-12-07T13:09:47Z", "lap": 5, "turn": 1, "type": "time_deleted" },
        { "utc": "2025-12-07T13:40:05Z", "lap": 25, "turn": 1, "type": "time_deleted" },
        { "utc": "2025-12-07T13:43:05Z", "lap": 27, "turn": 1, "type": "time_deleted" },
        { "utc": "2025-12-07T13:48:58Z", "lap": 31, "turn": null, "type": "warning" }
      ]
    },
    "GAS": {
      "racing_number": "10",
      "deletions": 4,
      "warning": true,
      "penalty": "5 SECOND TIME PENALTY",
      "violations": [
        { "utc": "2025-12-07T13:11:44Z", "lap": 6, "turn": 6, "type": "time_deleted" },
        { "utc": "2025-12-07T13:38:57Z", "lap": 24, "turn": 4, "type": "time_deleted" },
        { "utc": "2025-12-07T13:49:07Z", "lap": 31, "turn": null, "type": "warning" },
        { "utc": "2025-12-07T14:09:18Z", "lap": 44, "turn": 4, "type": "time_deleted" },
        { "utc": "2025-12-07T14:11:25Z", "lap": 46, "turn": null, "type": "penalty", "penalty": "5 SECOND TIME PENALTY" }
      ]
    },
    "LAW": {
      "racing_number": "30",
      "deletions": 4,
      "warning": true,
      "penalty": null,
      "violations": [
        { "utc": "2025-12-07T13:10:33Z", "lap": 5, "turn": 1, "type": "time_deleted" },
        { "utc": "2025-12-07T13:14:11Z", "lap": 8, "turn": 1, "type": "time_deleted" },
        { "utc": "2025-12-07T13:34:40Z", "lap": 21, "turn": 7, "type": "time_deleted" },
        { "utc": "2025-12-07T13:37:38Z", "lap": 23, "turn": null, "type": "warning" }
      ]
    }
  },
  "total_deletions": 11,
  "total_warnings": 3,
  "total_penalties": 1,
  "last_update": "2025-12-07T14:11:25Z"
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get a driver's track limits count:**
```jinja2
{% set by_driver = state_attr('sensor.f1_track_limits', 'by_driver') %}
{% set ham = by_driver.get('HAM') %}
{% if ham %}
  HAM: {{ ham.deletions }} deletions{% if ham.warning %}, WARNING{% endif %}
{% endif %}
```

**List drivers with warnings:**
```jinja2
{% set by_driver = state_attr('sensor.f1_track_limits', 'by_driver') %}
{% for tla, data in by_driver.items() if data.warning %}
  {{ tla }} (#{{ data.racing_number }}) - {{ data.deletions }} deletions
{% endfor %}
```

**Find drivers at risk (3+ deletions, no warning yet):**
```jinja2
{% set by_driver = state_attr('sensor.f1_track_limits', 'by_driver') %}
{% for tla, data in by_driver.items() if data.deletions >= 3 and not data.warning %}
  {{ tla }}: {{ data.deletions }} deletions - at risk!
{% endfor %}
```

**Get total session track limits:**
```jinja2
{% set deletions = state_attr('sensor.f1_track_limits', 'total_deletions') %}
{% set warnings = state_attr('sensor.f1_track_limits', 'total_warnings') %}
{% set penalties = state_attr('sensor.f1_track_limits', 'total_penalties') %}
Deletions: {{ deletions }}, Warnings: {{ warnings }}, Penalties: {{ penalties }}
```

**List drivers with penalties:**
```jinja2
{% set by_driver = state_attr('sensor.f1_track_limits', 'by_driver') %}
{% for tla, data in by_driver.items() if data.penalty %}
  {{ tla }}: {{ data.penalty }}
{% endfor %}
```

</details>
:::tip[Track Limits Progression]
The typical track limits progression is: 3 deleted lap times → BLACK AND WHITE flag warning → penalty on the next violation. Use the `deletions` count and `warning` flag to identify drivers at risk.
:::


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
