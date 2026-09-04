---
id: formation-start
title: "Formation Start"
description: "Indicates when formation start procedure is ready (Replay Mode or F1TV Auth live timing) \u2014 state, attributes, and examples for F1 Sensor."
---

Indicates when formation start procedure is ready (Replay Mode or F1TV Auth live timing). Use `binary_sensor.f1_formation_start` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

:::info[Replay Mode or F1TV Auth live timing]
This entity stays registered in Home Assistant. It updates in [Replay Mode](/features/replay-mode) and can update during live sessions when [F1TV Auth](/features/f1tv-auth) is paired with a valid token and the required extra live data is available.
:::

Indicates when the formation start procedure is ready. Useful for triggering automations at race start during replay or authenticated live sessions.

**State (on/off)**
- `on` when formation start procedure is ready; otherwise `off`.

**Example**
```text
on
```

**Attributes**

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


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
