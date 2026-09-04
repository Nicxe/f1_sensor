---
id: possible-on-track-incident
title: "Possible On-track Incident"
description: "Possible stopped car or on-track incident candidate is active \u2014 state, attributes, and examples for F1 Sensor."
---

Possible stopped car or on-track incident candidate is active. Use `binary_sensor.f1_possible_on_track_incident` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`binary_sensor.f1_possible_on_track_incident` - On while F1 Sensor has a possible or confirmed likely stopped car or on-track incident for the active session.

This entity includes early `candidate` incidents. Candidates can come from public timing and Race Control context, and can also come from optional F1TV Auth car movement data when it is correlated with yellow flag, Virtual Safety Car, Safety Car, or red flag context. Track Map can add optional location context when available, but it is not required for this entity to work.

:::warning[Use candidates carefully]
Candidate incidents are earlier and less certain than confirmed incidents. Use this entity for advanced automations, dashboard indicators, or opt-in alerts. For conservative notifications, use `binary_sensor.f1_on_track_incident` or the incident notification blueprint defaults.
:::

**State (on/off)**
- `on` when at least one `candidate`, `confirmed`, or `updated` incident is active.
- `off` when no possible or confirmed incident is active.
- `unavailable` when live or replay data is not available enough to report a reliable state.

**Example**
```text
on
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| active_count | number | Number of possible or confirmed active incidents |
| highest_confidence | string | Highest active confidence: `low`, `medium`, or `high` |
| latest_incident_id | string | Stable identifier for the most recent incident update |
| latest_driver_number | string | Car number for the latest incident update |
| latest_driver_tla | string | Driver abbreviation for the latest incident update |
| latest_reason | string | Neutral reason code for the latest update |
| latest_phase | string | Latest phase: `candidate`, `confirmed`, `updated`, or `cleared` |
| session_type | string | Lowercase session type, such as `race`, `sprint`, `qualifying`, or `practice` |
| session_name | string | Human-readable session name |
| data_quality | string | Data source quality, such as `live`, `replay`, `stale`, or `bootstrap` |

Detailed car movement samples are not exposed as state attributes.

For conservative notifications, use [Incident Detection](/features/incident-detection) and the [Incident Notifications blueprint](/blueprints/incident-notifications).


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
