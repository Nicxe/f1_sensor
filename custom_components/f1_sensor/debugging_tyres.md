# Tyre Data Live Debugging

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

## How To Verify After The Next Race

During the next live race session:

1. Enable development mode so the existing live timing diagnostic sensor is available in Home Assistant
2. Watch the tyre sensor and the live timing diagnostic attributes during the live race window
3. Capture the relevant integration debug logs around the first laps of the race

Expected interpretations:

- If the new warning appears after 5 minutes and tyre values are still empty, the upstream feed is active but still not sending usable tyre compounds
- If the informational log appears later in the session and tyre values start populating at the same time, that confirms delayed upstream tyre data
- If the diagnostic stream telemetry shows `TimingAppData` is not arriving at all, the problem shifts toward stream delivery rather than payload content
- If tyre compounds arrive in the stream telemetry but the sensor still stays empty, we need to revisit coordinator merge logic

Useful things to capture after the session:

- the live timing diagnostic sensor attributes
- the first new tyre observability log lines
- a short time window of debug logs around race start
- the saved `TimingAppData` stream dump if available

## Temporary Changes And Cleanup

The new tyre observability logs are temporary investigation support.

After one or more upcoming race weekends, we should decide whether to keep or remove them:

- Keep them if they continue to help separate upstream live feed delays from integration bugs
- Remove or reduce them if the issue proves isolated and the extra logging no longer adds support value

The most likely cleanup candidates are the single warning for delayed compounds and the single first-compound info log. If they provide clear value across multiple race weekends, they may still be worth keeping because they are low-volume and directly tied to live feed diagnosis.
