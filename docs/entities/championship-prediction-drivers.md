---
id: championship-prediction-drivers
title: "Championship Prediction (Drivers)"
description: "Drivers championship prediction (P1 and list) (Replay Mode or F1TV Auth live timing) \u2014 state, attributes, and examples for F1 Sensor."
---

Drivers championship prediction (P1 and list) (Replay Mode or F1TV Auth live timing). Use `sensor.f1_championship_prediction_drivers` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

:::info[Replay Mode or F1TV Auth live timing]
This entity stays registered in Home Assistant. It updates in [Replay Mode](/features/replay-mode) and can update during live sessions when [F1TV Auth](/features/f1tv-auth) is paired with a valid token and live prediction data is available.
:::

Predicted Drivers Championship winner and points table.

**State**
- Predicted P1 driver TLA, or `unknown` when not available.

**Example**
```text
VER
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| predicted_driver_p1 | object | The driver currently predicted to lead the championship |
| drivers | object | Map of all drivers keyed by racing number |
| last_update | string | ISO-8601 timestamp of the last prediction update |

The `predicted_driver_p1` object contains:

| Field | Type | Description |
| --- | --- | --- |
| racing_number | string | Car number |
| tla | string | Three-letter abbreviation |
| points | number | Predicted final points |
| entry | object | Full entry data from the feed |

Each entry in `drivers` (keyed by racing number) contains:

| Field | Type | Description |
| --- | --- | --- |
| RacingNumber | string | Car number |
| CurrentPosition | number | Current championship position |
| PredictedPosition | number | Predicted final position |
| CurrentPoints | number | Current points total |
| PredictedPoints | number | Predicted final points |

<details>
<summary>JSON Structure Example</summary>

```json
{
  "predicted_driver_p1": {
    "racing_number": "1",
    "tla": "VER",
    "points": 450,
    "entry": {
      "RacingNumber": "1",
      "CurrentPosition": 1,
      "PredictedPosition": 1,
      "CurrentPoints": 350,
      "PredictedPoints": 450
    }
  },
  "drivers": {
    "1": {
      "RacingNumber": "1",
      "CurrentPosition": 1,
      "PredictedPosition": 1,
      "CurrentPoints": 350,
      "PredictedPoints": 450
    },
    "44": {
      "RacingNumber": "44",
      "CurrentPosition": 2,
      "PredictedPosition": 2,
      "CurrentPoints": 280,
      "PredictedPoints": 380
    },
    "4": {
      "RacingNumber": "4",
      "CurrentPosition": 3,
      "PredictedPosition": 3,
      "CurrentPoints": 260,
      "PredictedPoints": 350
    }
  },
  "last_update": "2025-06-15T14:32:45Z"
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get predicted champion:**
```jinja2
{% set p1 = state_attr('sensor.f1_championship_prediction_drivers', 'predicted_driver_p1') %}
{% if p1 %}
  Predicted champion: {{ p1.tla }} with {{ p1.points }} points
{% endif %}
```

**Show points gain prediction for a driver:**
```jinja2
{% set drivers = state_attr('sensor.f1_championship_prediction_drivers', 'drivers') %}
{% set ver = drivers.get('1') %}
{% if ver %}
  {% set gain = ver.PredictedPoints - ver.CurrentPoints %}
  VER: {{ ver.CurrentPoints }} -> {{ ver.PredictedPoints }} (+{{ gain }})
{% endif %}
```

**List drivers predicted to gain positions:**
```jinja2
{% set drivers = state_attr('sensor.f1_championship_prediction_drivers', 'drivers') %}
{% for num, d in drivers.items() if d.PredictedPosition < d.CurrentPosition %}
  #{{ num }}: P{{ d.CurrentPosition }} -> P{{ d.PredictedPosition }}
{% endfor %}
```

**Calculate predicted gap to leader:**
```jinja2
{% set p1 = state_attr('sensor.f1_championship_prediction_drivers', 'predicted_driver_p1') %}
{% set drivers = state_attr('sensor.f1_championship_prediction_drivers', 'drivers') %}
{% set ham = drivers.get('44') %}
{% if p1 and ham %}
  Gap to leader: {{ p1.points - ham.PredictedPoints }} points
{% endif %}
```

</details>


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
