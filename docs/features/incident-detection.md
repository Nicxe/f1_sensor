---
id: incident-detection
title: Incident Detection
---

Incident Detection identifies likely stopped cars and on-track incidents from live or replayed timing context. It is designed for neutral alerts, dashboard indicators, and automations that should react when a session may have a caution-relevant event.

:::warning[Not crash detection]
Incident Detection does not prove that a crash happened. Use neutral wording such as "possible on-track incident" or "driver may have stopped on track" unless Race Control explicitly says more.
:::

## What it detects

F1 Sensor looks for stopped-car and on-track incident signals from public timing, Track Status, Race Control messages, and optional authenticated car data. The same alert can represent a stopped car, spin, technical failure, red flag stop, or another neutral on-track situation.

Confirmed incident detection works without F1TV Auth. Optional [F1TV Auth](/features/f1tv-auth) can improve earlier candidate signals when extra live car data is available, and [Track Map](/features/track-map) can add optional location context when it has fresh position data.

## What it does not detect

Incident Detection does not classify crash severity, medical response, damage, blame, or penalties. It also does not replace official Race Control messages.

Practice sessions naturally include slow running, pit work, installation laps, and test procedures, so practice alerts should stay conservative.

## Confidence and phases

| Phase | Meaning |
| --- | --- |
| `candidate` | Early possible incident. Useful for advanced dashboards or opt-in alerts |
| `confirmed` | Strong enough evidence for a normal user-facing alert |
| `updated` | New information for the same `incident_id`, such as higher confidence |
| `cleared` | The incident appears to be over |

| Confidence | Meaning |
| --- | --- |
| `low` | Weak or early signal, normally not user-facing |
| `medium` | Reasonable stopped-car or incident candidate |
| `high` | Strong context from stopped timing, Track Status, Safety Car, red flag, Race Control, or fresh Track Map support |

## Entities and events

| Surface | Purpose |
| --- | --- |
| `binary_sensor.f1_on_track_incident` | Turns on while at least one confirmed incident is active |
| `binary_sensor.f1_possible_on_track_incident` | Turns on for candidate, confirmed, or updated incidents |
| `f1_sensor_incident` event | Full lifecycle event for notifications and automations |
| Device triggers | UI-friendly triggers for possible and confirmed incident changes |

Device triggers include:

- `possible_on_track_incident_detected`
- `possible_on_track_incident_cleared`
- `on_track_incident_detected`
- `on_track_incident_cleared`

Use the [`f1_sensor_incident` event](/entities/events#on-track-incident) when you need one notification per incident update. Use the binary sensors when you only need an active state for dashboards, lights, or simple conditions.

## Public live behavior without F1TV Auth

Without F1TV Auth, F1 Sensor can still detect confirmed likely stopped-car and on-track incident alerts from public live timing. This uses public timing state, Track Status, and Race Control context.

This is the recommended base behavior for most users because it does not depend on tokens or extra live-auth data.

## Improvements with F1TV Auth

When F1TV Auth is configured and extra live car data is available, F1 Sensor can create earlier `candidate` signals from low-speed or stationary car movement. These candidates are correlated with yellow flag, Virtual Safety Car, Safety Car, or red flag context.

Candidates are earlier and less certain than confirmed alerts. Keep candidate notifications opt-in and conservative, especially for practice sessions.

## Track Map location context

When live or replay Track Map data is available, incident events can include optional location context such as a short location description, sector, pit-lane status, and whether the location is fresh or stale.

Location context can improve confidence or suppress obvious pit-lane false positives when the data is fresh enough. It is not required for incident detection.

## Notification blueprint

The [Incident Notifications blueprint](/blueprints/incident-notifications) is the recommended starting point for notifications. Its defaults are conservative:

- Phases: `confirmed` and `updated`
- Confidence: `medium` and `high`
- Sessions: Race, Sprint, and Qualifying
- Practice: excluded by default
- Candidate alerts: excluded by default

Enable candidate or practice notifications only when you understand the higher noise risk.

## Good automation wording

Use neutral wording in automations:

```text
Possible on-track incident: GAS may have stopped
```

Avoid wording that claims a crash unless Race Control explicitly uses that term.

## Limitations

- Incident Detection is best-effort and depends on upstream live timing or replay data.
- It can miss incidents if timing or Race Control data is delayed or incomplete.
- It can produce false positives during slow running, pit sequences, red flags, testing, or replay seeking.
- Candidate alerts from extra live car data require F1TV Auth during live sessions.
- Location context requires fresh Track Map data, either live with F1TV Auth or from Replay Mode when archived data exists.

## Related pages

- [Incident events](/entities/events#on-track-incident)
- [Live Data entities](/entities/live-data#on-track-incident)
- [Incident Notifications blueprint](/blueprints/incident-notifications)
- [Automation examples](/automation#possible-on-track-incident-notification)
- [F1TV Auth](/features/f1tv-auth)
- [Track Map](/features/track-map)
