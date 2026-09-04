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


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
