---
id: race-week
title: "Race Week"
description: "on during race week \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

on during race week.

<EntityMeta id="race-week" />

<span id="state-and-attributes"></span>

`binary_sensor.f1_race_week` - True when the next race is scheduled in the current calendar week.

## State

State type: on/off.
- `on` during weeks containing the next race date; otherwise `off`.

**Example**
```text
on
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| days_until_next_race | number | Days from today to the next race date |
| next_race_name | string | Grand Prix name of the next race |
| schedule_source | string or null | `jolpica` for API data, `official_calendar_fallback` for the temporary 2027 opener, or `null` when no next race is available |
| race_start_estimated | boolean | `true` for the fallback or when Jolpica has not supplied a race start time; otherwise `false` |
| schedule_source_url | string or null | Official calendar source for the fallback; otherwise `null` |

## Between seasons

If the temporary [2027 opener fallback](/entities/next-race#between-the-2026-and-2027-seasons) is active, `days_until_next_race` counts down to the Bahrain Grand Prix on 14 March 2027. The sensor remains `off` until that race's calendar week. The source attributes identify the fallback and its provisional start time; an upcoming Jolpica race takes priority when the schedule refresh supplies it.

## Related references

<span id="next-steps"></span>

<RelatedReferences id="race-week" />
