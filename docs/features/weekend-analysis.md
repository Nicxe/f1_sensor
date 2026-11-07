---
id: weekend-analysis
title: Analyse a Formula 1 session
description: Use timeline, strategy, battles and replay telemetry modules to understand a live or recorded session.
---

import {Figure, FlowSteps} from '@site/src/components/Docs';

Combine analysis modules in the [F1 Sensor card](/cards/cards-overview) to move from a session overview to the events, pace and battles behind it. The modules can share the same session, driver and team focus.

<FlowSteps label="Session analysis workflow" steps={[
  {title: 'Connect', description: 'Follow a live session or load an archived replay.'},
  {title: 'Focus', description: 'Choose a driver, team or gap reference.'},
  {title: 'Explore', description: 'Read the timeline, strategy, battles or recorded telemetry.'},
  {title: 'Verify', description: 'Use Race Control and published results for official outcomes.'}
]} />

## Build an analysis card

1. Add an **F1 Sensor** card with **Build your own**, or edit an existing card.
2. Add **Overview** for session and track status. Use the [Timing guide](/cards/timing) when you also want live sectors, push laps or driver details.
3. Add the analysis modules that answer your questions: **Session timeline**, **Strategy analysis**, **Battles and position changes**, **Lap history chart**, **Track map** or **Replay telemetry**.
4. Add **Race Control** for official messages and **Results** for published classifications.
5. Under **Layout and shared focus**, choose the source and an optional driver or team.

For live use, enable the relevant timing features in the F1 Sensor integration. For recorded use, add **Replay**, load a session and start playback so analysis can receive its timing.

<Figure src="/img/cards/f1-sensor-replay-session.png" alt="F1 Sensor card following Abu Dhabi Practice 1 replay with session overview and Race Control events" caption="A running Replay Mode session shown through F1 Sensor modules." />

Public timing supplies session context. Optional [F1TV Auth](/features/f1tv-auth) can add live streams, while replay depends on the data published in that session's archive. Replay telemetry needs a loaded replay with usable samples for the selected laps.

## Read the session timeline

**Session timeline** combines observed session, track-status, Race Control, investigation, lap, pit, weather, radio, position, battle and classification events. Filter categories, search text, choose order and limit the number of events.

Event times follow the time zone and 12/24-hour format in your Home Assistant profile. The timeline and selected-event detail show the same local time as **Race Control** for the same message. Sorting uses the underlying event time, so changing the display time zone does not change the order.

An event without a verified time shows no clock value. This also applies to older data whose time zone cannot be established. Events without a time appear after timed events; use category filters or **Show all** to find them when the row limit hides them.

An analysis event is an interpretation of observed timing. Its evidence score is not the same as an official Race Control decision. Missing radio, pit or weather data means those events may be absent.

## Understand strategy estimates

**Strategy analysis** can show recorded stints, compound comparisons, teammate pace, estimated compound crossovers and observed pit-cycle outcomes. The module separates recorded values from estimates and includes evidence or sample counts where available.

Matched comparisons require laps eligible for pace analysis. Pit laps, deleted times, incomplete or inconsistent timing, unknown track status and identified interruptions do not qualify. There is no fuel-load or traffic correction. A comparison can therefore wait for usable completed laps even after timing has started.

Open **Method and supporting laps** to see the method, used laps and exclusions. The content, compound, evidence-score and clean-lap filters control the displayed rows; a driver filter does not change the session-wide compound aggregates.

### Compare matched teammate laps

**Paired pace difference** uses the median of individual lap-time differences, with the first listed driver minus the second. Drivers are ordered by racing number so sorting or focus does not reverse the sign. Negative values mean the first driver recorded shorter times in the matched sample; an exact zero is a tie. It requires at least three pairs with the same lap number, tyre compound and observed green phase. The recorded tyre ages at the start of each lap may differ by at most two laps.

For example, times of `[90, 91, 100]` seconds against `[91, 99, 101]` give differences of `[-1, -8, -1]` and a median of **−1 second**. Subtracting the two separate medians would give **−8 seconds**, which answers a different question.

The displayed **Spread (Q1–Q3)** describes those paired differences. Quartiles use linear interpolation at index `(n − 1) × p`, with `p` equal to 0.25 or 0.75. This is a description of the sample, not a confidence interval. Possible pairs count every lap number observed for either driver. A missing observation or failed matching rule excludes that lap once, with one primary reason. Possible pairs therefore equal used pairs plus excluded pairs; fewer than three usable pairs produce no comparison or winner.

Descriptive median pace by driver and compound summaries remain available. They can cover different running periods and do not establish which tyre compound is inherently faster. Older integration data without matching metadata remains descriptive and does not produce a paired winner.

### Read trends and stint-change estimates

**Observed lap-time trend** fits a straight line to lap duration against known tyre age at the start of each lap. It uses the latest observed green phase within one recorded stint, with at least five eligible laps spanning at least four laps of tyre age. If the latest phase has insufficient samples, an older phase's trend is not substituted. A value of `+0.2 s/lap` describes increasing recorded lap times; it is not a measurement of physical tyre degradation. Unknown tyre age stays unknown, including when recording starts partway through a stint.

**Estimated stint-change loss** subtracts the previous stint's eligible-lap median from the observed transition-lap duration. The baseline uses all eligible laps in that stint's last observed green phase. It requires an observed physical tyre change, that transition lap with consistent timing, and at least three eligible baseline laps. The supporting details list the transition and baseline laps. Zero and negative estimates are valid arithmetic results and are displayed as recorded.

This estimate is separate from stationary stop time, pit-lane time and the **Estimated lap loss** shown by **Pit stops**, which has its own reference-lap method. An initial snapshot after a tyre change does not prove where that change occurred. Incomplete evidence leaves the new estimate unavailable. Existing card configuration continues to work; older backend trend and loss fields are not substituted for these stricter values.

## Understand battles and position changes

**Battles and position changes** shows current battles, battle history or detected position exchanges. Use the driver or team focus to narrow the view and filter by evidence score.

A timing-position change alone does not prove an on-track overtake. Pit stops, penalties, lapping and track status can also change the order. Read the supporting signals and use **Race Control** or **Results** before treating an important incident or classification as official.

## Compare replay laps

**Replay telemetry** compares up to four selected driver/lap pairs from the loaded replay. It can show recorded speed traces and a data table for the same samples.

Use the replay session selector first, then choose only laps that exist in the telemetry catalogue. Live telemetry comparison and inferred corner annotations are not available. An archive classification does not imply that telemetry or complete sector data exists.

This is retrospective analysis of the complete loaded recording, so you can select laps beyond the current playback position. No Spoiler Mode still protects access to the view.

Lap windows use the recorded observations of each driver's completed-lap count. They are approximate timing windows, not verified finish-line crossing times. A later lap-time or sector update does not move an earlier observation. A late-start recording cannot supply a missing preceding lap boundary; the first lap also requires a recorded session start. Safety Car periods and red-flag pauses remain in the observed window without an invented time adjustment. Gaps in telemetry remain gaps, and distance estimates are withheld when recorded coverage is insufficient.

## Choose the right module after a session

| Question | Module |
| --- | --- |
| What was the published classification? | Results or Historical archive |
| How did positions or lap times change? | Lap history chart or Historical archive |
| How has the championship developed? | Season progression |
| What happened during a recorded session? | Replay with Session timeline, Strategy analysis or Battles and position changes |
| What did officials publish? | Race Control or FIA documents |

Classification, lap progression, analysis and telemetry have separate coverage. A published result does not guarantee a lap chart or replay telemetry.

## Spoilers and empty modules

Keep [No Spoiler Mode](/features/no-spoiler-mode) active until you want to reveal results. The card's local spoiler choice can add hiding but cannot override integration-wide protection.

An empty module can mean no matching focused events, too few clean laps, a replay without the required samples or a source that has not published the data. Use the module's explanation to choose the next check. For a connection error, verify the selected integration and resource using [card loading checks](/cards/installation#card-loading-checks).
