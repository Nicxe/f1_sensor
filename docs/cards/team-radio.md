---
id: team-radio
title: Listen to Team Radio
description: Configure the experimental Team Radio module, playback, filters and manual transcripts.
toc_max_heading_level: 3
---

Add **Team Radio (experimental)** to the [F1 Sensor card](/cards/modular) to listen to published clips and optionally request a transcript.

## Set up the module

:::warning[Experimental feature]

The Team Radio module, audio playback and AI-generated transcript display are
experimental. Their behavior and saved options may change while the feature is
tested in beta. AI transcripts can contain errors, and speaker separation only
distinguishes different voices, not the driver or race engineer.

:::

The module shows the latest Team Radio clip published by Formula 1, or a recent
list of up to ten clips. Each message can include the racing number, driver,
team, team accent, team logo, message time, audio controls and transcript. The
card never starts audio or AI transcription automatically.

To set it up:

1. Enable [F1TV access](/features/f1tv-auth) for live Team Radio, or load a replay
   that contains radio clips.
2. Check that a clip is available. On a backend with [automatic card data](/features/card-data-and-sensors), the module can read clips without exposing the Team Radio sensor. Keep `sensor.f1_team_radio` enabled for the **Transcribe** action: that command still needs the Team Radio sensor entity, the latest clip and an AI Task entity. Showing clips through automatic card data does not require exposing the sensor.
3. Edit an **F1 Sensor** card and choose **Add module** >
   **Team Radio (experimental)**.
4. Select **Latest matching message** or **Recent messages**, then choose the
   fields and module options you want.
5. To show transcripts, follow [Team Radio transcription setup](/features/team-radio-transcription), then select that **AI Task entity for
   transcription** under the module options.

For the latest untranscribed clip, the module shows a small **Transcribe** button
beside **Play**. Pressing it manually runs `f1_sensor.transcribe_team_radio` with
the selected AI Task entity and never requests a forced retranscription. The
button is disabled in previews and frozen views. It is not shown for older
history items because the action accepts only the latest published clip. You can
hide the button in the module options.

The audio button uses F1 Sensor's signed local media URL. The Formula 1 access
token is not exposed to the browser. A signed URL can expire; reload the
dashboard after the integration refreshes the clip if playback no longer works.

Choose a driver or team in the card focus controls to show only matching clips.
You can also give the module its own driver or team selection under **Module
options**. **Recent messages** uses the Team Radio rolling history, so it can only
show clips that remain in that history.

When a genuinely new clip arrives, **Mark new messages** adds a **New Team
Radio** indicator. Adding or correcting a transcript for the same clip does not
mark it as new. The indicator belongs to the current card instance and clears
when the clip is played; reloading the dashboard starts with the latest clip as
the baseline.

Transcribed turns alternate between the left and right sides of the card to
separate the two anonymous voices without adding visible speaker labels. If the
provider returns a full transcript without usable speaker turns, the card shows
the text as one full-width passage. Driver and team details are taken from the
radio message and can fall back to Driver List data when the clip only
contains a racing number. The module only displays transcript data already
stored with the Team Radio data; it never calls the AI provider by itself. You
supply the Gemini API key and are responsible for provider usage and charges.
See [Team Radio](/entities/team-radio) for the complete setup, action YAML,
status attributes and troubleshooting.

## Continue

- [Watch Team Radio in the introduction on YouTube (01:18)](https://www.youtube.com/watch?v=R72LXKdiNxA&t=78s)
- [Set up manual transcription](/features/team-radio-transcription)
- [Look up clips, history and transcript fields](/entities/team-radio)
- [Check account and feed availability](/features/f1tv-auth)
