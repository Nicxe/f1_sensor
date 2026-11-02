---
id: next-race
title: "Next Race"
description: "Next race info \u2014 state, attributes, and examples for F1 Sensor."
---

Next race info. Use `sensor.f1_next_race` in dashboards, templates, and automations.

This reference covers the state and attributes. For setup, see [Configuration](/getting-started/add-integration).

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`sensor.f1_next_race` - Schedule for the next race; state is the race start timestamp (ISO‑8601).

**State**
  - ISO‑8601 timestamp (UTC) of the race start, or `unknown` if not available.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| season | string | Season year |
| round | string | Round number |
| race_name | string | Grand Prix name |
| schedule_source | string | `jolpica` for API data or `official_calendar_fallback` for the temporary 2027 opener |
| race_start_estimated | boolean | `true` for the fallback or when Jolpica has not supplied a race start time; otherwise `false` |
| schedule_source_url | string or null | Official calendar source for the fallback; otherwise `null` |
| scheduled_laps | number or null | Planned race laps; `null` when Jolpica has no value or its alpha data is unavailable |
| sprint_scheduled_laps | number or null | Planned sprint laps; `null` when there is no sprint or no alpha value is available |
| race_url | string | Ergast race URL |
| circuit_id | string | Circuit identifier |
| circuit_name | string | Circuit name |
| circuit_url | string | Circuit URL |
| circuit_lat | string | Latitude |
| circuit_long | string | Longitude |
| circuit_locality | string | City/area |
| circuit_country | string | Country |
| country_code | string | ISO country code (e.g., "GB", "IT", "US") |
| country_flag_url | string | URL to country flag image |
| circuit_map_url | string | URL to official circuit map image |
| circuit_outline_url | string | URL to circuit outline image when available |
| circuit_timezone | string | Local timezone (best effort) |
| race_start_utc | string | Race start (UTC ISO‑8601) |
| race_start | string | Race start in Home Assistant local time |
| race_start_local | string | Race start in circuit local time |
| first_practice_start_utc | string | FP1 start (UTC ISO‑8601) |
| first_practice_start | string | FP1 start in Home Assistant local time |
| first_practice_start_local | string | FP1 start in circuit local time |
| second_practice_start_utc | string | FP2 start (UTC ISO‑8601) |
| second_practice_start | string | FP2 start in Home Assistant local time |
| second_practice_start_local | string | FP2 start in circuit local time |
| third_practice_start_utc | string | FP3 start (UTC ISO‑8601) |
| third_practice_start | string | FP3 start in Home Assistant local time |
| third_practice_start_local | string | FP3 start in circuit local time |
| qualifying_start_utc | string | Qualifying start (UTC ISO‑8601) |
| qualifying_start | string | Qualifying start in Home Assistant local time |
| qualifying_start_local | string | Qualifying start in circuit local time |
| sprint_qualifying_start_utc | string | Sprint Qualifying/Shootout start (UTC ISO‑8601) |
| sprint_qualifying_start | string | Sprint Qualifying/Shootout start in Home Assistant local time |
| sprint_qualifying_start_local | string | Sprint Qualifying/Shootout start in circuit local time |
| sprint_start_utc | string | Sprint start (UTC ISO‑8601) |
| sprint_start | string | Sprint start in Home Assistant local time |
| sprint_start_local | string | Sprint start in circuit local time |

The planned lap counts come from Jolpica's alpha session data. They describe the scheduled distance, which can differ from the number of laps actually completed.

## Between the 2026 and 2027 seasons

When the known 2026 schedule has no remaining races and Jolpica has not yet supplied an upcoming race, F1 Sensor temporarily uses the 2027 season opener. If the final 2026 race has no start time, the fallback waits until three hours after that race's UTC date has ended. This fallback also covers an empty 2027 calendar after New Year. A failed API request alone does not activate it.

The fallback identifies the **Bahrain Grand Prix at Bahrain International Circuit, Sakhir, Bahrain, on 14 March 2027**. Formula 1 published the [official 2027 calendar](https://www.formula1.com/en/latest/article/formula-1-reveals-calendar-for-2027-season-with-10-sprint-events.5J8ePLyjRuMyWEIDNUKgY4) on 16 September 2026.

:::warning[Provisional start time]
The fallback uses **15:00 UTC on 14 March 2027**, or **18:00 in Bahrain**, to keep timestamp-based dashboards and countdowns working. This is a provisional time chosen by the integration. Formula 1's [Bahrain schedule](https://www.formula1.com/en/racing/2027/bahrain) lists the race time as **TBC** as of 1 November 2026. Check `race_start_estimated` before using this timestamp in an automation that needs an exact start time.
:::

While the fallback is active, `schedule_source` is `official_calendar_fallback` and `race_start_estimated` is `true`. The date, location, race timestamp, track time, and [Race Week](/entities/race-week) countdown remain available. Session times and planned lap counts remain unknown until supplied by Jolpica.

An upcoming race from Jolpica takes priority as soon as it arrives through the normal schedule refresh. The schedule cache can retain data for up to 24 hours; the fallback adds no extra API polling. It expires three hours after its provisional race start and does not provide a full 2027 season calendar, results, or live timing.

If Jolpica supplies the Bahrain opener on 14 March 2027 without a start time, the sensor keeps the provisional 15:00 UTC timestamp. Its `schedule_source` becomes `jolpica` and `schedule_source_url` becomes `null`, while `race_start_estimated` remains `true`. A start time supplied by Jolpica replaces the provisional time and clears the estimated flag. Other races with a date but no API start time retain the default of 00:00 UTC and also set `race_start_estimated` to `true`.


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
