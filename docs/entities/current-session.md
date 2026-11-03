---
id: current-session
title: "Current Session"
description: "Current ongoing session, like Practice 1, Qualification, Race \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Identify the session currently being followed, such as practice, qualifying, or the race.

<EntityMeta id="current-session" />

<span id="state-and-attributes"></span>

Human-readable label for the session being followed. Practice, Sprint, and Race labels are shown while the mapped session status is `live`. Qualifying and Sprint Qualifying retain their label between segments until the session ends.

## State

State type: enum/string.
- `Practice 1`, `Practice 2`, `Practice 3`, `Qualifying`, `Sprint Qualifying`, `Sprint`, `Race`, or `unknown` when there is no current label. The entity can be `unavailable` outside its data window.

**Example**
```text
Qualifying
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| type | string | Raw `Type` from feed (Practice/Qualifying/Race) |
| name | string | Raw `Name` (may carry “Sprint”/“Sprint Qualifying”) |
| number | number | Session number (e.g., 1/2/3 for practice) |
| session_part | number | Detected session part (e.g., 1/2/3 for Q1/Q2/Q3) when available |
| meeting_key | number | Meeting key |
| meeting_name | string | Meeting name |
| meeting_location | string | Location |
| meeting_country | string | Country |
| circuit_short_name | string | Circuit short name |
| gmt_offset | string | Event GMT offset |
| start | string | Session start ISO‑8601 |
| end | string | Session end ISO‑8601 |
| live_status | string | Raw `SessionStatus` message (`Started`, `Finished`, etc.) |
| active | boolean | True when live running is active |
| last_label | string | Last resolved label when not active |

## Related references

<span id="next-steps"></span>

<RelatedReferences id="current-session" />
