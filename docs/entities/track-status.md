---
id: track-status
title: "Track Status"
description: "Current track status \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Current track status.

<EntityMeta id="track-status" />

<span id="state-and-attributes"></span>

Current track status from live or replay timing. Outside an active data window the entity can become unavailable; do not interpret a previous `CLEAR` value as confirmation that a session is running.

## State

State type: enum.
  - One of: `CLEAR`, `YELLOW`, `VSC`, `SC`, `RED`.

**Example**
```text
CLEAR
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| (none) |  | No extra attributes |

## Related references

<span id="next-steps"></span>

<RelatedReferences id="track-status" />
