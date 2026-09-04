---
id: season-calendar
title: "Season Calendar"
description: "Full season calendar with all sessions \u2014 state, attributes, and examples for F1 Sensor."
---

Full season calendar with all sessions. Use `calendar.f1_season_calendar` in dashboards, templates, and automations.

This reference covers the state and attributes. For setup, see [Configuration](/getting-started/add-integration).

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`calendar.f1_season_calendar` - Native Home Assistant calendar showing every session of the current Formula 1 season.

The calendar appears in the Home Assistant calendar panel and shows each session as a separate event: Practice 1, Practice 2, Practice 3, Qualifying, Sprint Qualifying, Sprint, and Race. On sprint weekends, Practice 3 is replaced by Sprint Qualifying and Sprint.

**State**
- `on` when a session is currently in progress; otherwise `off`.

**Event fields**

| Field | Description |
| --- | --- |
| summary | Session name, e.g. "Monaco Grand Prix - Qualifying" |
| description | Round context, e.g. "Round 7 of the 2025 Formula 1 Season" |
| location | Circuit name, city, and country |
| start | Session start time (UTC) |
| end | Estimated session end time (UTC) |

**Estimated session durations**

| Session | Duration |
| --- | --- |
| Practice 1 | 60 min |
| Practice 2 | 60 min |
| Practice 3 | 60 min |
| Qualifying | 60 min |
| Sprint Qualifying | 45 min |
| Sprint | 35 min |
| Race | 120 min |
:::info
Session end times are estimated based on standard session lengths. Actual sessions may run shorter or longer due to red flags or delays.
:::

**Automation example**

Trigger an automation 30 minutes before any F1 session starts:

```yaml
alias: F1 - Session Starting Soon
description: Notify before any F1 session begins
trigger:
  - platform: calendar
    event: start
    entity_id: calendar.f1_season_calendar
    offset: "-00:30:00"
action:
  - service: notify.persistent_notification
    data:
      title: "F1 Session Starting Soon"
      message: "{{ trigger.calendar_event.summary }} starts in 30 minutes"
mode: single
```
:::tip
The calendar entity complements `sensor.f1_current_season`. Use the sensor when you need race data in templates and attributes. Use the calendar when you want a visual schedule or calendar-based automations.
:::

## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
