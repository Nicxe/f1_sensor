# Tyre data investigation: 2026 Chinese Grand Prix

This maintainer note records an investigation into missing tyre compounds during the 2026 Chinese Grand Prix. The observations below are historical evidence; they do not establish the state of a later live session. No follow-up race result is recorded in this note.

For user-facing behavior and attributes, see the [Current Tyres reference](https://nicxe.github.io/f1_sensor/entities/current-tyres).

## Background

Issue [#427](https://github.com/Nicxe/f1_sensor/issues/427) reported that tyre data was missing during the 2026 Chinese Grand Prix race while other live sensors continued to update.

The main question was whether the problem was caused by:

- missing or delayed tyre data on the live SignalR feed
- a parsing or routing problem inside the integration

## Analysis Performed

The following evidence was collected during the investigation:

- Home Assistant runtime data showed that the live session itself was active and other live sensors continued to update normally during the race
- `sensor.f1_current_tyres` existed and included drivers, but `compound`, `new`, and `stint_laps` were initially `null`
- later in the same race, the same tyre sensor started showing real compound values without any code changes or reload
- the archived race stream dumps for `CurrentTyres` and `TimingAppData` both started with missing tyre compound information and only later contained meaningful tyre values
- the live integration now reads tyre state directly from `TimingAppData`, which has proven to be the more reliable live feed

Based on that evidence, the most likely explanation is that the upstream live feed did not include usable tyre compounds at the start of the race. At the time of writing, this points more strongly to delayed upstream data inside `TimingAppData` than to a general integration bug.

## Instrumentation Added

To make the next race easier to diagnose, targeted observability was added in the live tyre merge path.

### First meaningful tyre data log

The coordinator now logs a single informational message the first time `TimingAppData` contains at least one meaningful tyre `Compound` during a live session.

This gives us:

- the elapsed live time before tyre compounds first appeared
- the number of drivers with detected compound data
- a small sample of driver and compound pairs

### Delayed tyre warning

The coordinator now logs a single warning if a live session has been active for 5 minutes and `TimingAppData` frames are still arriving without any meaningful tyre compounds.

This lets us quickly distinguish between:

- no live stream at all
- a live stream that is active but still empty for tyre compounds
- a stream that eventually starts sending usable tyre data

## Follow-up verification procedure

When a maintainer investigates a similar live session:

1. If requested by the maintainer, use a build with live timing diagnostics enabled. Keep the timing source in Live mode when investigating a live feed; Developer mode with a replay dump is a separate workflow.
2. Watch the tyre sensor and the live timing diagnostic attributes during the live race window
3. Capture the relevant integration debug logs around the first laps of the race

Expected interpretations:

- If the new warning appears after 5 minutes and tyre values are still empty, the upstream feed is active but still not sending usable tyre compounds
- If the informational log appears later in the session and tyre values start populating at the same time, that confirms delayed upstream tyre data
- If the diagnostic stream telemetry shows `TimingAppData` is not arriving at all, the problem shifts toward stream delivery rather than payload content
- If tyre compounds arrive in the stream telemetry but the sensor still stays empty, we need to revisit coordinator merge logic

Useful evidence to capture after the session:

- the live timing diagnostic sensor attributes
- the first new tyre observability log lines
- a short time window of debug logs around race start
- the saved `TimingAppData` stream dump if available

## Temporary Changes And Cleanup

The tyre observability logs were introduced as investigation support. Their first-compound and delayed-compound checks are still present in the code at this documentation review; that code check does not substitute for a new live-session observation.

Use follow-up live evidence to decide whether to keep or remove them:

- Keep them if they continue to help separate upstream live feed delays from integration bugs
- Remove or reduce them if the issue proves isolated and the extra logging no longer adds support value

The most likely cleanup candidates are the single warning for delayed compounds and the single first-compound info log. If they provide clear value across multiple race weekends, they may still be worth keeping because they are low-volume and directly tied to live feed diagnosis.
