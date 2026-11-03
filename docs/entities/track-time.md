---
id: track-time
title: "Track Time"
description: "Current local time at the next race circuit \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Current local time at the next race circuit.

<EntityMeta id="track-time" />

<span id="state-and-attributes"></span>

`sensor.f1_track_time` - Current local time at the next race circuit.

## State

- String: local time at the circuit, formatted as `HH:MM`, or `unknown`.

**Example**
```text
14:05
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| timezone | string | Circuit timezone (IANA, best effort) |
| utc_offset | string | UTC offset at the circuit, formatted as `+HHMM` |
| offset_from_home | string | Difference between circuit time and Home Assistant time (best effort) |
| circuit_name | string | Circuit name |
| circuit_locality | string | City/area |
| circuit_country | string | Country |

## Related references

<span id="next-steps"></span>

<RelatedReferences id="track-time" />
