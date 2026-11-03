---
id: sprint-results
title: "Sprint Results"
description: "Sprint classification results \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Sprint classification results.

<EntityMeta id="sprint-results" />

<span id="state-and-attributes"></span>

Classification results for all sprint sessions in the current season.

## State

- Integer: number of sprint races with results, or `0` when none are available.

**Example**
```text
6
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| races | list | List of sprint races with results |

### `races` entries

| Field | Type | Description |
| --- | --- | --- |
| round | string | Round number |
| race_name | string | Grand Prix name |
| results | list | List of classification results |

### `results` entries

| Field | Type | Description |
| --- | --- | --- |
| number | string | Car number |
| grid | string | Sprint starting grid position |
| position | string | Final position |
| laps | string | Completed laps |
| time | string | Total time or gap supplied by Jolpica |
| points | string | Points awarded |
| status | string | Finish status |
| driver | object | `{ permanentNumber, code, givenName, familyName }` |
| constructor | object | `{ name }` |

## Related references

<span id="next-steps"></span>

<RelatedReferences id="sprint-results" />
