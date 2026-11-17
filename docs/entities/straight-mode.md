---
id: straight-mode
title: "Straight Mode"
description: "Active-aero permission in the circuit’s designated Straight Mode zones."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Use `sensor.f1_straight_mode` to see which active-aero setting is permitted in the designated zones for the current session. The state describes permission. Individual drivers choose when to activate their wings.

<EntityMeta id="straight-mode" />

<span id="state-and-attributes"></span>

## State

| Value | When you see it |
| --- | --- |
| `normal_grip` | Normal-grip Straight Mode is permitted in the designated zones. |
| `low_grip` | Only partial activation is permitted in the designated low-grip zones. |
| `disabled` | Straight Mode is explicitly disabled or the integration has confirmed that the event has no activation zones. |
| `unavailable` | The session has ended or the available timing and zone data are insufficient to determine permission. |

An explicit Straight Mode announcement sets the state directly, including in pre-season replays. Otherwise the sensor uses verified zones for that event together with Race Control’s declared grip. Zone coverage is specific to the event and season. With no confirmed grip declaration or suitable map, a dry track alone leaves permission unconfirmed. For the grip declaration itself, see the [Session Status](/entities/session-status) attribute `track_grip`.

**Example**

At the 2026 Monaco Grand Prix, the sensor shows `disabled` because the event had no Straight Mode zones. Overtake Mode could still be enabled. [Formula 1’s Monaco explanation](https://www.formula1.com/en/latest/article/explained-why-active-aero-will-not-be-used-at-the-monaco-grand-prix.4nLtpjM9ZTUbPBQLmeAbj4)

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| `overtake_enabled` | boolean or null | [Overtake Mode](/entities/overtake-mode) permission for the same session, when known. |
| `restored` | boolean | Present and true when the sensor uses a value restored for the same session. |

## Related references

<span id="next-steps"></span>

<RelatedReferences id="straight-mode" />
