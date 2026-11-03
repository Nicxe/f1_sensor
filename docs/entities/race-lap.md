---
id: race-lap
title: "Race Lap"
description: "Current race lap number \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Current race lap number.

<EntityMeta id="race-lap" />

<span id="state-and-attributes"></span>

Current lap and total laps during the race.

## State

  - Integer: current lap, or `unknown` if none available or stale cleared.

**Example**
```text
23
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| total_laps | number | Total laps when known; preserved across updates |
:::info[Info]
This sensor is active only during sprint and race sessions.
:::

## Related references

<span id="next-steps"></span>

<RelatedReferences id="race-lap" />
