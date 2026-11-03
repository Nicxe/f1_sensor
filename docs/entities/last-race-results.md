---
id: last-race-results
title: "Last Race Results"
description: "Most recent race results \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Most recent race results.

<EntityMeta id="last-race-results" />

<span id="state-and-attributes"></span>

`sensor.f1_last_race_results` - Results of the most recent race; state is the winner’s family name.

## State

  - String: winner surname, or `unknown`.

**Example**
```text
Verstappen
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| round | string | Round number |
| race_name | string | Grand Prix name |
| race_url | string | Ergast URL |
| circuit_id | string | Circuit identifier |
| circuit_name | string | Circuit name |
| circuit_url | string | Circuit URL |
| circuit_lat | string | Latitude |
| circuit_long | string | Longitude |
| circuit_locality | string | City/area |
| circuit_country | string | Country |
| circuit_timezone | string | Local timezone (best effort) |
| race_start_utc | string | Race start (UTC ISO‑8601) |
| race_start | string | Race start in Home Assistant local time |
| race_start_local | string | Race start in circuit local time |
| results | list | Cleaned results array: `{number, grid, position, laps, time, points, status, driver{permanentNumber, code, givenName, familyName}, constructor{constructorId, name}}`. `time` contains the total time or gap supplied by Jolpica |

## Related references

<span id="next-steps"></span>

<RelatedReferences id="last-race-results" />
