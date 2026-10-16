---
id: team-radio
title: "Team Radio"
description: "Latest team radio clip and rolling history (Replay Mode or F1TV Auth live timing) \u2014 state, attributes, and examples for F1 Sensor."
---

Latest team radio clip and rolling history (Replay Mode or F1TV Auth live timing). Use `sensor.f1_team_radio` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::warning[Experimental transcription]
Team radio transcription is experimental. It is tested with a Google Gemini AI Task entity, may change without notice, and sends audio to the AI provider only when you manually run the action. You are responsible for the provider API key, its terms, and any charges.
:::

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

Each entry in `history` contains:

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

## Experimental transcription

The experimental `f1_sensor.transcribe_team_radio` action sends the latest published clip to an AI Task entity. It keeps the original English language and separates distinct voices into anonymous speakers `A` and `B`. It does not identify the driver or engineer.

### Before you start

1. Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/app/apikey).
2. In Home Assistant, open **Settings** > **Devices & services** > **Add integration** and add **Google Gemini**.
3. Keep the recommended setup or create an **AI Task** subentry. Home Assistant then creates an entity similar to `ai_task.google_ai_task`.
4. Wait for a live or replay team radio clip. Your team radio entity must have a `clip_url` attribute before it can be transcribed.

Only Google Gemini AI Task is supported for this experimental implementation. Other AI Task providers can be selected in the interface, but they have not been validated for MP3 transcription.

### Transcribe the latest clip

Open **Developer Tools** > **Actions**, select **Experimental: Transcribe team radio**, and enter your own entity IDs:

```yaml
action: f1_sensor.transcribe_team_radio
data:
  entity_id: sensor.f1_team_radio
  ai_task_entity_id: ai_task.google_ai_task
```

The status changes to `processing` while the request runs and then to `completed` or `failed`. If it fails, read `transcription_error` on the team radio entity.

The experimental Team Radio module in the modular F1 Sensor card can run the
same action. Select your **AI Task entity for transcription** in the module
options, then press the small **Transcribe** button beside **Play** on the latest
untranscribed message. The card does not request forced retranscription, and it
does not offer the button for older history items because the action accepts
only the latest published clip.

### View the result

The complete transcript is stored in `transcription_text`. Individual speaker turns are available in `transcription_segments`, where speakers are labeled `A`, `B`, or `unknown`.

The structured speaker turns can be displayed in a Markdown card:

```yaml
type: markdown
content: |-
  {% for segment in state_attr('sensor.f1_team_radio', 'transcription_segments') or [] %}
  **{{ segment.speaker }}:** {{ segment.text }}

  {% endfor %}
```

### Cost, privacy, and limitations

The action is manual. F1 Sensor never sends team radio audio to an AI provider automatically. When you run it, the MP3 file is sent to the selected provider and may incur charges. Temporary local audio files are removed after the request.

A completed result is cached for the current clip while F1 Sensor remains loaded. Running the action again with `force: false` does not create another AI request for that clip. `force: true` deliberately sends a new request. The cache resets when the integration reloads or Home Assistant restarts.

### Troubleshooting

- **No team radio clip is currently available**: wait for a new live or replay radio clip and confirm that `clip_url` is present.
- **Select an AI Task entity**: choose the Google Gemini AI Task entity, not its conversation or speech-to-text entity.
- **Transcription failed**: check `transcription_error`, then confirm that the Gemini API key is valid and that the configured account can use the selected model.

## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
