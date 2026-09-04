---
id: team-radio
title: "Team Radio"
description: "Latest team radio clip and rolling history (Replay Mode or F1TV Auth live timing) \u2014 state, attributes, and examples for F1 Sensor."
---

Latest team radio clip and rolling history (Replay Mode or F1TV Auth live timing). Use `sensor.f1_team_radio` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

:::info[Replay Mode or F1TV Auth live timing]
This entity stays registered in Home Assistant. It updates in [Replay Mode](/features/replay-mode) and can update during live sessions when [F1TV Auth](/features/f1tv-auth) is paired with a valid token and live team radio data is available.
:::

Latest curated team radio clip with a rolling history. This is not the full raw driver radio feed; it follows the Team Radio clips Formula 1 publishes for the session.

**State**
- ISO-8601 timestamp of the most recent radio clip, or `unknown` when none are available.

**Example**
```text
2026-07-05T14:01:01+00:00
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| utc | string | ISO-8601 timestamp of the radio clip |
| received_at | string | ISO-8601 timestamp when Home Assistant received the message |
| racing_number | string | Car number for the driver |
| path | string | Relative path to the audio file |
| clip_url | string | Full URL to the audio clip when available |
| sequence | number | Message counter for deduplication |
| raw_message | object | Raw team radio capture from the timing feed |
| history | list | Rolling list of recent radio clips, up to 20 items |

Each entry in `history` contains:

| Field | Type | Description |
| --- | --- | --- |
| utc | string | ISO-8601 timestamp of the radio clip |
| racing_number | string | Car number for the driver |
| path | string | Relative path to the audio file |
| clip_url | string | Full URL to the audio clip when available |


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
