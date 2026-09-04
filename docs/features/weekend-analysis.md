---
id: weekend-analysis
title: Explore a weekend and its results
description: Use Weekend Hub to follow a timeline, read strategy estimates, compare replay laps and understand battles.
---

import {Figure, FlowSteps} from '@site/src/components/Docs';

Use [Weekend Hub](/cards/weekend-hub) to move from a session overview to the events, pace and battles behind it. Its five views share the same session. For published classifications from another season, use [Results Archive](/features/historical-results).

<FlowSteps label="Session analysis workflow" steps={[
  {title: 'Connect', description: 'Follow a live session or load an archived replay.'},
  {title: 'Focus', description: 'Choose a driver and the gap you want to follow.'},
  {title: 'Explore', description: 'Open the timeline, strategy or battles view.'},
  {title: 'Compare', description: 'Select replay laps for a telemetry comparison.'},
]} />

## Before you start

Update the integration and bundled cards, then add **F1 Weekend Hub**. For live use, enable live data and the relevant timing features in F1 Sensor's configuration. For replay, load the session with [Replay Control](/cards/replay-control) and start playback so the analysis can receive its timing.

Public timing supplies session context. Optional [F1TV Auth](/features/f1tv-auth) can add live streams, while replay depends on the data published in that session's archive. Telemetry comparison needs a loaded replay with usable samples for the selected laps. There is no separate Strategy or Telemetry card to install.

## Follow a session

1. Open **Overview** to check the session, timing state, analysis coverage and recent events.
2. Set **Focus driver**, or leave **All drivers** selected to see the wider session.
3. Choose **Ahead**, **Leader** or **Off** under **Gap reference**. A missing gap is shown as unavailable rather than inferred from a position.
4. Open **Timeline**, **Strategy** or **Battles** for the question you want to answer.

Supported cards share the dashboard focus and gap selection. For example, [Driver Lap Times](/cards/driver-lap-times) highlights the selected driver and follows the gap reference. This selection is stored in the browser; it does not change `select.f1_favorite_driver` or driver-specific automations. See [dashboard context](/cards/shared-options#dashboard-context).

## Read the timeline

**Timeline** combines the events available for the session: session and track-status changes, Race Control, laps, weather, pits, radio and analysis events. Selecting a driver narrows the view while retaining relevant session-wide events. The visible list shows recent events, with the newest first.

An analysis event is an interpretation of the observed timing. Its confidence is not the same as an official Race Control decision. Missing radio, pit or weather data means those events may be absent from the timeline.

<Figure src="/img/cards/weekend-hub-timeline.png" alt="Weekend Hub timeline filtered to Norris, with lap, weather, position and Race Control events" caption="Recent timeline events with Norris selected. Cropped from the running Dutch Grand Prix replay." />

## Understand strategy estimates

**Strategy** groups completed laps into stints and shows their tyre compound, median clean pace, degradation, sample counts and confidence. Compound comparisons and undercut/overcut indications appear when the observed data supports them.

| Readout | How to interpret it |
| --- | --- |
| Median clean pace | Median lap duration after unsuitable laps have been excluded. It is not a fuel-corrected or weather-normalized prediction. |
| Degradation in seconds per lap | Trend across the accepted laps. Traffic, changing conditions and small samples can affect it. |
| Clean / observed laps | How much of the observed stint was suitable for comparison. More observed laps do not necessarily mean more usable laps. |
| Confidence | A data-quality and sample-size indication. It does not certify the strategy or predict a future result. |
| Undercut / overcut | An inferred outcome around observed pit cycles, not proof of what caused the position change. |
| Compound crossover | An estimate from the available compound and tyre-age samples. It is not a guaranteed best pit lap. |

The clean-lap checks exclude deleted laps, pit-entry and pit-exit laps, inferred laps, missing lap or sector times, inconsistent sector totals, disrupted running under Safety Car/VSC/red flags, and the first lap after that disruption. A reinstated lap can become eligible again if it passes the other checks.

A panel can therefore say **waiting for clean completed laps** even after several laps have appeared in timing. Check the selected driver, coverage and excluded-lap reasons before assuming the card is broken. Starting to observe a session late can also leave gaps in the available history.

<Figure src="/img/cards/weekend-hub-strategy.png" alt="Weekend Hub strategy view showing Norris tyre stints, clean pace, confidence and compound comparisons" caption="Norris selected during the 2026 Dutch Grand Prix replay. Confidence and excluded laps are shown alongside the estimates." />

## Compare replay laps

1. Load the desired session in [Replay Mode](/features/replay-mode). A classification selected in Results Archive does not load replay timing.
2. Open Weekend Hub's **Telemetry** view.
3. Select a **Driver**, enter a **Lap** number and select **Add lap**.
4. Add up to four driver/lap combinations. Select an existing lap chip to remove it; adding a fifth keeps the four most recently added selections.
5. Select **Compare selected laps**.
6. Switch between **Speed**, **Throttle**, **Brake**, **Gear** and **Time delta** to inspect the selected traces.

The chart compares the selected laps over distance. Only the selected replay windows are requested; it does not fetch an entire season's telemetry. The first selected lap is the reference for time delta. If a lap has no usable telemetry, check another completed lap in the loaded session.

Live telemetry comparison and corner annotations are not available. Loading an archive classification does not imply that telemetry or complete sector data exists for it.

<Figure src="/img/cards/weekend-hub-telemetry.png" alt="Weekend Hub speed comparison for Norris and Piastri on lap 35" caption="Norris (car 1) and Piastri (car 81), lap 35 of the 2026 Dutch Grand Prix replay. The two traces come from the selected archived laps." />

## Understand battles

**Battles** shows active battles and detected position exchanges. Use the focus selector to narrow the view to a driver. The analysis distinguishes likely on-track changes from exchanges associated with pit stops, penalties, lapping or track status.

Treat confidence and explanatory labels as part of the result. A change in timing position alone does not prove an on-track overtake. Use [Race Control](/cards/race-control) and official results to check an important incident or final classification.

<Figure src="/img/cards/weekend-hub-battles.png" alt="Weekend Hub showing an active battle and position exchanges with confidence and pit context" caption="Active battles and recent position exchanges during replay. This cropped view preserves the confidence and context labels." />

## After the session

| Question | View |
| --- | --- |
| What was the classification? | [Results](/cards/results), including [historical Archive](/features/historical-results) |
| How did positions change lap by lap? | [Lap Position Progression](/cards/lap-position-progression) |
| How has the championship developed? | [Season Progression](/cards/season-progression) |
| What happened during a past session? | [Replay Control](/cards/replay-control), then Weekend Hub |

Classification, lap progression and replay telemetry have separate coverage. A published Sprint result does not guarantee a lap-position chart. Weekend Hub is a view of observed live or replay analysis, not a permanent archive of every session you have watched.

## Spoilers and empty views

Keep [No Spoiler Mode](/features/no-spoiler-mode) enabled until you want to reveal results. Weekend Hub's **Hide analysis** control also shares a dashboard spoiler setting; its configured helper and the integration's No Spoiler switch are separate controls. See [shared spoiler protection](/cards/shared-options#spoiler-protection).

An empty view may mean no matching driver events, too few clean laps or a replay without the required samples. Use the explanation in the panel to choose the next check. For a connection error, verify the integration entry and card version using [card loading checks](/cards/installation#card-loading-checks).
