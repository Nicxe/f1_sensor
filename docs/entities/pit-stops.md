---
id: pit-stops
title: "Pit Stops"
description: "Reported pit counts, available stop times and their limits during live timing and Replay Mode."
---

Follow reported pit counts and available stop times for each car. Use `sensor.f1_pitstops` in dashboards, templates, and automations, or add the **Pit stops** module to the [F1 Sensor card](/cards/modular#show-pit-stops).

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

:::info[Replay Mode or F1TV Auth live timing]
This entity stays registered in Home Assistant. It updates in [Replay Mode](/features/replay-mode) and can update during live sessions when [F1TV Auth](/features/f1tv-auth) is paired with a valid token and live pit stop data is available.

Counts and detailed stops are separate. Public timing can contain per-driver pit counts while the detailed stop feed remains absent. The Pit Stops entity and card dataset still use the Replay Mode or authenticated-live availability rules; public source counts alone do not enable them without connected access. An accepted token does not guarantee every detail field. See the [account availability comparison](/features/f1tv-auth#availability-matrix).
:::

`sensor.f1_pitstops` - Reported pit counts and available stop records from F1 Live Timing, grouped by car.

**State**

- Integer: total reported pit count for the current session. A pit entry can increase this count before a timed stop record is available.
- `0`: no count or detail records have been accumulated in the ready dataset. This alone does not prove that no real pit visits occurred.
- `unavailable`: the live or replay source does not currently meet the entity's availability requirements.

**Example**
```text
7
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| cars | object | Map of racing numbers to reported counts and available stop records |
| last_update | string or null | ISO-8601 time when Home Assistant last delivered this dataset, including count-only updates; not the time of a pit event |

Each entry in `cars` (keyed by racing number) contains:

| Field | Type | Description |
| --- | --- | --- |
| tla | string or null | Driver code (TLA), when available |
| name | string or null | Driver name, when available |
| team | string or null | Team name, when available |
| count | number | Reported pit count, or the number of retained detail records if larger; not a count of verified stationary services |
| stops | list | Available stop records; at most the ten most recent records per car are retained |

Each entry in `stops` contains:

| Field | Type | Description |
| --- | --- | --- |
| lap | number or null | Stop lap supplied by the source; not inferred from the current lap or pit count |
| timestamp | string or null | Stop timestamp supplied by the source, when available |
| pit_stop_time | number or null | Stationary time in seconds, when supplied by the source |
| pit_lane_time | number or null | Total time through the pit lane in seconds, when available |
| pit_delta | number or null | Estimated lap-time loss in seconds, when enough lap history is available |
| source | string | `PitStopSeries` for a detailed source record, or `PitLaneTimeCollection` for the live pit-lane-time fallback |

## Counts without stop details

A positive count and an empty `stops` list are valid together. For example, a car can have `count: 2` and `stops: []` when timing reports two pit visits but no usable per-stop detail records have arrived. The count does not supply the missing laps or times.

Counts can also include a final visit to the pits that ends in retirement. During the United States race on 25 October 2026, the last ready dataset reported 34 pit visits while the later detail archive contained 32 timed stop records. Two cars had one additional pit entry each and remained in the pits as retired. The count and the detail total describe different source observations.

Tyre stints and Strategy analysis use separate timing data. A new stint or a known tyre compound does not establish a stop's stationary time.

## Pit-lane time during live sessions

When connected access is active, F1 Sensor also requests the live pit-lane duration feed through its existing shared connection. A usable record needs both a stop lap and a positive duration. It can add a stop record containing `lap` and `pit_lane_time` even when the detailed stop feed remains absent. Its `source` is `PitLaneTimeCollection`; `timestamp` and `pit_stop_time` remain `null` because that payload does not supply them.

The live feed removes its temporary rows shortly after publication. F1 Sensor keeps the observed stop record and ignores repeated delivery of the same car and lap. If a detailed `PitStopSeries` record later arrives for that car and lap, it takes precedence and supplies the fields it actually contains.

This fallback retains at most one best-effort observation per car and lap because the feed has no stable stop identifier. It cannot distinguish multiple visits on the same lap or recover earlier stops that were never observed. A reconnected feed is not a complete stop history. Normal Replay Mode uses the archived detailed stop records; it does not download this extra live feed to fill an incomplete archive.

## Understand the three time fields

**Stationary time** (`pit_stop_time`) measures the stationary part of the stop. **Pit-lane time** (`pit_lane_time`) covers the passage through the pit lane. Neither field is interchangeable with the other, and an unknown time remains `null` rather than `0`.

**Estimated loss** (`pit_delta`) compares the longer of the stop lap and the following lap with a reference lap time. The reference is the median of the available times from the three laps before the stop. If those times are absent, it uses the second through fourth laps after the stop. The calculation waits for the following lap and a usable reference, so it can arrive after the stop or remain `null`.

This estimate uses lap times rather than an official pit-loss measurement. Traffic, tyre performance and Safety Car conditions can affect it. Missing stop records cannot be reconstructed from the count alone.

## Live and replay coverage

During the sampled United States race windows on 25 October 2026, reported counts updated through Home Assistant while the subscribed `PitStopSeries` detail feed supplied no payloads. Both tested accounts received public timing, and other additional feeds worked with the paid account. This does not establish why the detail feed was absent or a subscription rule for all accounts.

The saved Singapore and United States race archives contain 25 and 32 detailed stop records respectively. Parser checks read all 57 records correctly without duplicates on repeated input. Archive data can therefore provide fields that were absent from the observed live delivery; it does not prove that those fields were available live or that every archive file will be accessible.


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
