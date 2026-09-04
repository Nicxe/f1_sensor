---
id: championship-prediction-teams
title: "Championship Prediction (Teams)"
description: "Constructors championship prediction (P1 and list) (Replay Mode or F1TV Auth live timing) \u2014 state, attributes, and examples for F1 Sensor."
---

Constructors championship prediction (P1 and list) (Replay Mode or F1TV Auth live timing). Use `sensor.f1_championship_prediction_teams` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

:::info[Replay Mode or F1TV Auth live timing]
This entity stays registered in Home Assistant. It updates in [Replay Mode](/features/replay-mode) and can update during live sessions when [F1TV Auth](/features/f1tv-auth) is paired with a valid token and live prediction data is available.
:::

Predicted Constructors Championship winner and points table.

**State**
- Predicted P1 team name, or `unknown` when not available.

**Example**
```text
Red Bull Racing
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| predicted_team_p1 | object | The team currently predicted to lead the constructors' championship |
| teams | object | Map of all teams keyed by team key |
| last_update | string | ISO-8601 timestamp of the last prediction update |

The `predicted_team_p1` object contains:

| Field | Type | Description |
| --- | --- | --- |
| team_key | string | Team identifier |
| team_name | string | Team display name |
| points | number | Predicted final points |
| entry | object | Full entry data from the feed |

Each entry in `teams` (keyed by team key) contains:

| Field | Type | Description |
| --- | --- | --- |
| TeamKey | string | Team identifier |
| TeamName | string | Team display name |
| CurrentPosition | number | Current championship position |
| PredictedPosition | number | Predicted final position |
| CurrentPoints | number | Current points total |
| PredictedPoints | number | Predicted final points |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "predicted_team_p1": {
    "team_key": "red_bull",
    "team_name": "Red Bull Racing",
    "points": 850,
    "entry": {
      "TeamKey": "red_bull",
      "TeamName": "Red Bull Racing",
      "CurrentPosition": 1,
      "PredictedPosition": 1,
      "CurrentPoints": 650,
      "PredictedPoints": 850
    }
  },
  "teams": {
    "red_bull": {
      "TeamKey": "red_bull",
      "TeamName": "Red Bull Racing",
      "CurrentPosition": 1,
      "PredictedPosition": 1,
      "CurrentPoints": 650,
      "PredictedPoints": 850
    },
    "ferrari": {
      "TeamKey": "ferrari",
      "TeamName": "Ferrari",
      "CurrentPosition": 2,
      "PredictedPosition": 2,
      "CurrentPoints": 520,
      "PredictedPoints": 700
    },
    "mclaren": {
      "TeamKey": "mclaren",
      "TeamName": "McLaren",
      "CurrentPosition": 3,
      "PredictedPosition": 3,
      "CurrentPoints": 480,
      "PredictedPoints": 650
    }
  },
  "last_update": "2025-06-15T14:32:45Z"
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get predicted constructors champion:**
```jinja2
{% set p1 = state_attr('sensor.f1_championship_prediction_teams', 'predicted_team_p1') %}
{% if p1 %}
  Predicted constructors champion: {{ p1.team_name }}
{% endif %}
```

**Compare two teams:**
```jinja2
{% set teams = state_attr('sensor.f1_championship_prediction_teams', 'teams') %}
{% set rb = teams.get('red_bull') %}
{% set ferrari = teams.get('ferrari') %}
{% if rb and ferrari %}
  Gap: {{ rb.PredictedPoints - ferrari.PredictedPoints }} points
{% endif %}
```

**List teams by predicted finish:**
```jinja2
{% set teams = state_attr('sensor.f1_championship_prediction_teams', 'teams') %}
{% for key, t in teams.items() | sort(attribute='1.PredictedPosition') %}
  P{{ t.PredictedPosition }}: {{ t.TeamName }} ({{ t.PredictedPoints }} pts)
{% endfor %}
```

**Show teams predicted to change position:**
```jinja2
{% set teams = state_attr('sensor.f1_championship_prediction_teams', 'teams') %}
{% for key, t in teams.items() if t.PredictedPosition != t.CurrentPosition %}
  {{ t.TeamName }}: P{{ t.CurrentPosition }} -> P{{ t.PredictedPosition }}
{% endfor %}
```

</details>


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
