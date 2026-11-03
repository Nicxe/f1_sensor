---
id: team-radio
title: "Team Radio"
description: "Latest team radio clip and rolling history (Replay Mode or F1TV Auth live timing) \u2014 state, attributes, and examples for F1 Sensor."
---

import {EntityMeta, RelatedReferences} from '@site/src/components/Docs';

Latest team radio clip and rolling history (Replay Mode or F1TV Auth live timing).

:::warning[Experimental transcription]
Team radio transcription is experimental. It is tested with a Google Gemini AI Task entity, may change without notice, and sends audio to the AI provider only when you manually run the action. You are responsible for the provider API key, its terms, and any charges.
:::

<EntityMeta id="team-radio" />

<span id="state-and-attributes"></span>

:::info[Replay Mode or F1TV Auth live timing]
This entity stays registered in Home Assistant. It updates in [Replay Mode](/features/replay-mode) and can update during live sessions when [F1TV Auth](/features/f1tv-auth) is paired with a valid token and live team radio data is available.
:::

Latest curated team radio clip with a rolling history. This is not the full raw driver radio feed; it follows the Team Radio clips Formula 1 publishes for the session.

## State

- ISO-8601 timestamp of the most recent radio clip, or `unknown` when none are available.

**Example**
```text
2026-07-05T14:01:01+00:00
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| utc | string | ISO-8601 timestamp of the radio clip |
| received_at | string | ISO-8601 timestamp when Home Assistant received the message |
| racing_number | string | Car number for the driver |
| driver_tla | string | Three-letter driver code, such as `NOR` or `HAM` |
| driver_name | string | Full driver name from the live timing feed |
| team_name | string | Team name from the live timing feed |
| team_color | string | Team color as a hexadecimal value beginning with `#` |
| path | string | Relative path to the audio file |
| clip_url | string | Full URL to the audio clip when available |
| sequence | number | Message counter for deduplication |
| transcription_status | string | `processing`, `completed`, or `failed` after the transcription action is used |
| transcription_text | string | Complete English transcript when available |
| transcription_segments | list | Spoken turns labeled anonymously as speaker `A`, `B`, or `unknown` |
| transcription_ai_task_entity_id | string | AI Task entity that produced the transcript |
| transcription_generated_at | string | ISO-8601 timestamp when transcription completed or failed |
| transcription_error | string | Short error message when transcription failed |
| raw_message | object | Raw team radio capture from the timing feed |
| history | list | Rolling list of recent radio clips, up to 20 items |

### `history` entries

| Field | Type | Description |
| --- | --- | --- |
| utc | string | ISO-8601 timestamp of the radio clip |
| racing_number | string | Car number for the driver |
| driver_tla | string | Three-letter driver code |
| driver_name | string | Full driver name |
| team_name | string | Team name |
| team_color | string | Team color as a hexadecimal value beginning with `#` |
| path | string | Relative path to the audio file |
| clip_url | string | Full URL to the audio clip when available |

You can use `racing_number`, `driver_tla`, or `team_name` in templates and automations to select messages from a specific driver or team. The driver code can be read from the audio file name when driver details arrive late. Other identity fields remain `null` when Formula 1 does not provide them.

<span id="experimental-transcription"></span>
<span id="before-you-start"></span>
<span id="transcribe-the-latest-clip"></span>
<span id="view-the-result"></span>
<span id="cost-privacy-and-limitations"></span>
<span id="troubleshooting"></span>

## Transcription guide

Use [Transcribe a team radio clip](/features/team-radio-transcription) for the complete setup, action examples, speaker-turn display, cost, privacy, cache behavior and troubleshooting. The experimental action accepts only the latest published clip and requires the Team Radio entity and a supported AI Task entity.

## Related references

<span id="next-steps"></span>

<RelatedReferences id="team-radio" />
