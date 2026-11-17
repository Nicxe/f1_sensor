---
id: overtake-mode
title: "Overtake Mode"
description: "Track-wide permission to use Overtake Mode during live sessions and replays."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Use `binary_sensor.f1_overtake_mode` to see when Race Control permits Overtake Mode across the track. Each driver’s eligibility and use of the extra electrical power are separate decisions.

<EntityMeta id="overtake-mode" />

<span id="state-and-attributes"></span>

## State

| Value | When you see it |
| --- | --- |
| `on` | Race Control has enabled Overtake. |
| `off` | Race Control has disabled Overtake, a physical Safety Car has been deployed during a race or sprint, or an official low-grip declaration disables Overtake under the rules for that session. |
| `unavailable` | The session has ended or the integration has no confirmed state for the current session. |

After a physical Safety Car, the sensor waits for a new `OVERTAKE ENABLED` message. A green flag or a return to normal grip alone does not grant permission. A Virtual Safety Car alone leaves the last confirmed Overtake state in place. For 2026 sessions, the low-grip restriction applies from the Austrian Grand Prix onward. [FIA sporting regulations, article B7.2.2](https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_b_sporting_-_iss_07_-_2026-06-25.pdf)

**Example**

During the 2026 Chinese Grand Prix, the Safety Car came out on lap 10. The sensor shows `off` until Race Control enables Overtake on lap 14.

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| `straight_mode` | string or null | Confirmed [Straight Mode](/entities/straight-mode) permission for the same session, when known. |
| `restored` | boolean | Present and true when the sensor uses a value restored for the same session. |

After a restart, the integration waits for the session identity before using saved live data. Changing sessions clears the previous value.

Replay follows the session’s recorded messages and applicable rules. A gap in the archive can leave a change unreported.

## Related references

<span id="next-steps"></span>

<RelatedReferences id="overtake-mode" />
