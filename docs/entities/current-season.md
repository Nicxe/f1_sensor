---
id: current-season
title: "Current Season"
description: "Full race schedule \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Full race schedule.

<EntityMeta id="current-season" />

<span id="state-and-attributes"></span>

`sensor.f1_current_season` - Number of races in the current season.

## State

  - Integer: count of races in the season.

**Example**
```text
24
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| races | list | Enriched races array for the season |

Each entry in `races` contains the standard Ergast race data plus:

| Field | Type | Description |
| --- | --- | --- |
| country_code | string | ISO country code (e.g., "GB", "IT", "US") |
| country_flag_url | string | URL to country flag image |
| circuit_map_url | string | URL to official circuit map image |
| circuit_outline_url | string | URL to circuit outline image when available |
| scheduled_laps | number | Planned race laps, when available from Jolpica's alpha session data |

On sprint weekends, the nested `Sprint` object also includes `scheduled_laps` when Jolpica provides it. These planned counts can differ from the laps actually completed.

## Related references

<span id="next-steps"></span>

<RelatedReferences id="current-season" />
