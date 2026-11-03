---
id: session-status
title: "Session Status"
description: "Current session phase \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences, FlowSteps} from '@site/src/components/Docs';

Current session phase.

<EntityMeta id="session-status" />

<span id="state-and-attributes"></span>

Semantic session lifecycle based on the live Session Status. The `pre` state usually occurs 60–15 minutes before a session begins. The sensor goes `live` when the session officially starts, for races, this means lights out, not the beginning of the formation lap.

## State

State type: enum.
- One of: `pre`, `live`, `suspended`, `break`, `finished`, `finalised`, `ended`.

**Example**
```text
live
```

### Typical session flow

This is an overview, not an exhaustive state machine. Qualifying and Sprint Qualifying can also use `break` between segments.

<FlowSteps label="Typical session phases" steps={[
  {title: 'Before the session', description: 'The pre phase precedes the official start.'},
  {title: 'Running and interruptions', description: 'Live running can be suspended and resumed, or break between qualifying segments.'},
  {title: 'After the finish', description: 'Finished, finalised and ended describe the closing phases.'},
]} />

**Typical transitions**
`pre → live → suspended ↔ live → finished → finalised → ended`
After finalised or ended, logic resets and next session begins at **pre**.

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| meeting_name | string | Meeting name (e.g., "Monaco Grand Prix") |
| meeting_location | string | Meeting location (e.g., "Monte Carlo") |
| meeting_country | string | Meeting country (e.g., "Monaco") |
| circuit_short_name | string | Circuit short name (e.g., "Monaco") |
| gmt_offset | string | Event GMT offset |
| start | string | Session start ISO‑8601 |
| end | string | Session end ISO‑8601 |
| track_grip | string | Track grip state from Race Control, when available (best effort) |

## Related references

<span id="next-steps"></span>

<RelatedReferences id="session-status" />
