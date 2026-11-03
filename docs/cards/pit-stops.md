---
id: pit-stops
title: Show pit visits and stop times
description: Configure the Pit stops module and distinguish reported visits, stationary time and pit-lane time.
toc_max_heading_level: 3
---

Add **Pit stops** to the [F1 Sensor card](/cards/modular) when you want reported visits and the available timing records for the selected session.

## Read counts and details

These readings answer different questions. Unknown timing fields stay `null` in the underlying data and appear as unavailable in the card.

| Reading | What it tells you | Important limit |
| --- | --- | --- |
| **Reported pit visits** (`count`) | The driver’s reported pit count, or the number of retained detail records if larger | A count does not establish the lap or duration of an individual stop, or prove a stationary service. Counts and detail records can differ. |
| **Stationary time** (`pit_stop_time`) | Time spent stationary during a stop, in seconds | Missing stationary time remains `null`; pit-lane time cannot fill it. |
| **Pit lane time** (`pit_lane_time`) | Time for the full passage through the pit lane, in seconds | A live duration can arrive with a lap but no stationary time or event timestamp. Missing duration remains `null`. |
| **Estimated lap loss** (`pit_delta`) | A lap-time estimate of the time lost around a stop, in seconds | It needs usable lap history, can arrive later or remain `null`, and is affected by traffic, tyres and Safety Car conditions. |

Add **Pit stops** to follow reported pit visits and any timed stop records available for the current session. The module distinguishes counts from details: an available count does not establish the lap or duration of an individual stop.

When a driver has a reported count but no detailed stop records, **Reported pit visits** shows the driver, current status and count separately. In a session with mixed coverage, this summary appears alongside genuine detailed stop rows. **All stops** and **Latest stop** apply to the detailed records; summary rows do not become invented stop events.

Select **Stationary time** for the stationary part of a stop, **Pit lane time** for the full passage through the pit lane and **Estimated lap loss** for a lap-time estimate. Unknown times remain unavailable. A driver's **Current status** describes their present state, not their state at an earlier stop. Driver and team selections still filter the module's data.

An observed live pit-lane duration can provide a detail row with a lap and lane time while stationary time and event time remain unknown. The card explains this partial timing coverage. It does not present a lane duration as a stationary service time.

Live counts can arrive while times are missing, and the module explains this partial coverage. The same selected session, live delay and No Spoiler rules apply to counts and details. Connecting access or loading an archive does not guarantee every field. See [Pit Stops](/entities/pit-stops) for field definitions and [F1TV access and data coverage](/features/f1tv-auth) for the tested account differences.

## Continue

- [Exact pit-stop attributes and count semantics](/entities/pit-stops)
- [Check account and feed availability](/features/f1tv-auth)
- [Compare strategy and tyre stints](/features/weekend-analysis#understand-strategy-estimates)
