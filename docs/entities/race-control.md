---
id: race-control
title: "Race Control"
description: "Race Control messages feed (flags, incidents, key updates) \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Race Control messages feed (flags, incidents, key updates).

<EntityMeta id="race-control" />

<span id="state-and-attributes"></span>

Feed-style sensor exposing Race Control messages such as flags, incidents, and key session updates. This data is also sent on the [event bus](/entities/events).

## State

- The latest Race Control message text (max 255 characters), or `unknown` when none are available.

**Example**
```text
YELLOW FLAG IN TURN 4
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| utc | string | ISO‑8601 timestamp when the message was issued |
| received_at | string | ISO‑8601 timestamp when Home Assistant received it |
| category | string | Type of message (e.g., "Flag", "SafetyCar", "Other") |
| flag | string | Flag type when applicable (e.g., "YELLOW", "GREEN", "RED") |
| scope | string | Scope of the message (e.g., "Track", "Sector") |
| sector | string | Track sector affected, if applicable |
| car_number | string | Car number involved, if applicable |
| message | string | Full message text |
| event_id | string | Composite ID for deduplication |
| sequence | number | Message counter |
| history | list | Rolling list of recent messages (up to 5), each with `event_id`, `utc`, `category`, `flag`, and `message` |
| raw_message | object | Full source message details |

## Related references

<span id="next-steps"></span>

<RelatedReferences id="race-control" />
