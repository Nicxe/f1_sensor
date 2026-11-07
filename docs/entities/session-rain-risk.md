---
id: session-rain-risk
title: "Session Rain Risk"
description: "The rain-risk percentage published by Race Control for the current Formula 1 session."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Show the rain-risk percentage published by Race Control for a specific session, such as Practice 3 or the race.

<EntityMeta id="session-rain-risk" />

<span id="state-and-attributes"></span>

This assessment is separate from the weather provider's [forecast](/entities/weather-summary) and the [Track Weather](/entities/track-weather) rain indicator. A percentage does not mean that rain has been detected at the circuit.

## State

- Number: rain risk from `0` to `100`, in percent.
- `unknown` while the source is active but no valid assessment is available for the identified session; `unavailable` while the source is inactive.

Missing data does not mean `0 %`; an explicitly published `0 %` is valid information.

**Example**

```text
30
```

For example, `RISK OF RAIN FOR F1 FREE PRACTICE 3 IS 30%` provides a value of `30` for Practice 3.

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| percentage | number | Published rain risk, matching the sensor state |
| session_key | string | F1 session key identifying the assessment's session |
| meeting_key | string | F1 meeting key identifying the event |
| session_name | string | Session name from the source, such as `Practice 3` |
| utc | string | ISO-8601 timestamp of the Race Control message |
| message | string | Original Race Control message |
| source | string | `race_control` |

Unknown attribute values use `null`. Known session metadata can remain present while no percentage is available.

## Availability and session changes

The value requires an identified session and a matching F1 Race Control rain-risk message. It can appear before the session starts and remains available through unrelated messages, red-flag interruptions and breaks between qualifying parts. A newer assessment replaces it; the session ending or changing clears it.

[Live Delay](/features/live-delay) and [No Spoiler Mode](/features/no-spoiler-mode) apply. During replay, the value comes from messages played up to the current position. Seeking to a point before the message removes the later assessment.

After a restart, the integration can restore a saved assessment only for the same identified session and only after its message time is behind your delayed viewing time. A live assessment is never reused as replay data. If neither the source nor matching saved data supplies an assessment, the value remains unknown.

## Show it on a dashboard

The F1 Sensor card offers **Session rain risk** in its [Overview and Weather modules](/cards/cards-overview#overview-module). The field is hidden while no valid percentage is available. It does not require a separate Race Control module or an enabled sensor entity.

Select **Session rain risk** under **Configure → Enabled sensors** when you want to use the percentage in standard Home Assistant cards, templates or automations. See [card data and sensor selection](/features/card-data-and-sensors).

## Related references

<span id="next-steps"></span>

<RelatedReferences id="session-rain-risk" />
