---
id: team-radio-transcription
title: Transcribe a team radio clip
description: Manually transcribe the latest Team Radio clip with a Google Gemini AI Task entity, including setup, cost, privacy, and troubleshooting.
---

Turn the latest published Team Radio clip into an English transcript with anonymous speaker labels. This experimental action is manual and sends audio to your selected AI provider only when you run it.

:::warning[Experimental transcription]
Team radio transcription is experimental. It is tested with a Google Gemini AI Task entity, may change without notice, and sends audio to the AI provider only when you manually run the action. You are responsible for the provider API key, its terms, and any charges.
:::

## Experimental transcription

The experimental `f1_sensor.transcribe_team_radio` action sends the latest published clip to an AI Task entity. It keeps the original English language and separates distinct voices into anonymous speakers `A` and `B`. It does not identify the driver or engineer.

### Before you start

Enable the **Team Radio** sensor in the integration options for transcription. Automatic card data can display clips without this sensor, but the current transcription action and the card’s **Transcribe** command address a sensor entity.

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

## Related references

- [Team Radio state, attributes and clip history](/entities/team-radio)
- [Set up the Team Radio dashboard module](/cards/team-radio)
- [Account and live feed availability](/features/f1tv-auth)
