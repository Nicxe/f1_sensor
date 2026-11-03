---
id: safety-car
title: "Safety Car"
description: "Safety Car (SC) or Virtual Safety Car (VSC) is active \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Safety Car (SC) or Virtual Safety Car (VSC) is active.

<EntityMeta id="safety-car" />

<span id="state-and-attributes"></span>

On while the Safety Car or Virtual Safety Car is in effect.

## State

State type: on/off.
- `on` when track status is `SC` or `VSC`; otherwise `off`.

**Example**
```text
on
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| track_status | string | Normalized track status (`CLEAR`, `YELLOW`, `VSC`, `SC`, `RED`) |

## Related references

<span id="next-steps"></span>

<RelatedReferences id="safety-car" />
