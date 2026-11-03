---
id: formation-start
title: "Formation Start"
description: "Indicates when formation start procedure is ready (Replay Mode or F1TV Auth live timing) \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Indicates when formation start procedure is ready (Replay Mode or F1TV Auth live timing).

<EntityMeta id="formation-start" />

<span id="state-and-attributes"></span>

:::info[Replay Mode or F1TV Auth live timing]
This entity stays registered in Home Assistant. It updates in [Replay Mode](/features/replay-mode) and can update live when your [F1TV Auth account](/features/f1tv-auth) receives the required car telemetry. A valid token alone does not guarantee that feed. Live telemetry arrived only with the tested paid account during the 23 October 2026 FP1 comparison; the race or sprint formation-start behavior still needs its own session-specific verification.
:::

Indicates when the formation start procedure is ready. Useful for triggering automations at race start during replay or authenticated live sessions.

## State

State type: on/off.
- `on` when formation start procedure is ready; otherwise `off`.

**Example**
```text
on
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| status | string | Current status (e.g., "ready", "waiting", "active") |
| scheduled_start | string | ISO‑8601 scheduled start time |
| formation_start | string | ISO‑8601 timestamp when formation start actually happened |
| delta_seconds | number | Seconds between scheduled and actual start |
| source | string | How the data was derived |
| session_type | string | Type of session (e.g., "Race", "Sprint") |
| session_name | string | Name of the session |
| error | string | Error message if any issue occurred |
:::info[INFO]
Available during race and sprint sessions in Replay Mode, and during live F1TV Auth timing when the required extra live data is available.
:::

## Related references

<span id="next-steps"></span>

<RelatedReferences id="formation-start" />
