---
id: on-track-incident
title: "On-track Incident"
description: "Confirmed likely stopped car or on-track incident is active \u2014 state, attributes, and examples for F1 Sensor."
---

Confirmed likely stopped car or on-track incident is active. Use `binary_sensor.f1_on_track_incident` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`binary_sensor.f1_on_track_incident` - On while F1 Sensor has a confirmed likely stopped car or on-track incident for the active session.

:::warning[Not crash detection]
This entity detects likely stopped cars and on-track incidents from live timing, track status, and Race Control context. It does not prove that a crash happened, and it may also represent a technical failure, spin, red flag stop, or another neutral on-track situation.
:::

**State (on/off)**
- `on` when at least one confirmed incident is active.
- `off` when no confirmed incident is active.
- `unavailable` when live or replay data is not available enough to report a reliable state.

**Example**
```text
on
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| active_count | number | Number of confirmed active incidents |
| highest_confidence | string | Highest active confidence: `medium` or `high` |
| latest_incident_id | string | Stable identifier for the most recent incident update |
| latest_driver_number | string | Car number for the latest incident update |
| latest_driver_tla | string | Driver abbreviation for the latest incident update |
| latest_reason | string | Neutral reason code for the latest update |
| latest_phase | string | Latest phase: `candidate`, `confirmed`, `updated`, or `cleared` |
| session_type | string | Lowercase session type, such as `race`, `sprint`, `qualifying`, or `practice` |
| session_name | string | Human-readable session name |
| data_quality | string | Data source quality, such as `live`, `replay`, `stale`, or `bootstrap` |

The entity intentionally keeps attributes small and stable. Use the [`f1_sensor_incident` event](/entities/events#on-track-incident) for detailed automation triggers and notification text.

For the full behavior, confidence, and notification model, see [Incident Detection](/features/incident-detection).

:::info[Session support]
Incident detection is designed for race, sprint, qualifying, and practice sessions. Practice alerts are more conservative because practice sessions naturally contain more slow running, pit activity, and testing-style behavior.
:::


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
