---
id: driver-positions
title: "Driver Positions"
description: "Driver positions and lap times \u2014 state, attributes, and examples for F1 Sensor."
---

Driver positions and lap times. Use `sensor.f1_driver_positions` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`sensor.f1_driver_positions` - Live driver positions and lap-by-lap timing data for all drivers in the session.

**State**
- Integer: current lap number (leader's lap), or `unknown` when not available.

**Example**
```text
45
```

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| drivers | list | List of drivers, sorted by position when available |
| total_laps | number | Total race distance in laps, when known |
| fastest_lap | object | Fastest lap details during races and sprints; `null` in other session types |
| current_qualifying_part | number | Active qualifying segment (1, 2, or 3); `null` outside qualifying sessions |

Each entry in `drivers` contains:

| Field | Type | Description |
| --- | --- | --- |
| racing_number | string | Car number |
| tla | string | Three-letter abbreviation (driver code) |
| name | string | Driver's full name |
| team | string | Team name |
| team_color | string | Team color as hex code (e.g., "#3671C6") |
| team_color_rgb | list | Team color as RGB values (e.g., `[54, 113, 198]`) |
| grid_position | string | Starting grid position |
| current_position | string | Current position in the session |
| laps | object | Map of lap numbers to lap times (e.g., `{"1": "1:32.456", "2": "1:31.789"}`) |
| completed_laps | number | Number of laps completed by this driver |
| status | string | Driver status: `on_track`, `pit_in`, `pit_out`, or `out` |
| gap_to_leader | string | Public live timing gap to the session leader when available |
| interval_to_position_ahead | string | Public live timing interval to the car directly ahead when available |
| in_pit | boolean | Whether driver is currently in pit lane |
| pit_out | boolean | Whether driver just exited pits |
| retired | boolean | Whether driver has retired from the session |
| stopped | boolean | Whether driver has stopped on track |
| fastest_lap | boolean | True if this driver currently holds fastest lap (race/sprint only) |
| fastest_lap_time | string | Fastest lap time (race/sprint only) |
| fastest_lap_time_secs | number | Fastest lap time in seconds (race/sprint only) |
| fastest_lap_lap | number | Lap number of the fastest lap (race/sprint only) |
| sector_1 | number | Current sector 1 time in seconds; `null` while sector has not been completed this lap |
| sector_2 | number | Current sector 2 time in seconds; `null` while not yet completed |
| sector_3 | number | Current sector 3 time in seconds; `null` while not yet completed |
| sector_1_lap | number | Lap number associated with the current sector 1 value |
| sector_2_lap | number | Lap number associated with the current sector 2 value |
| sector_3_lap | number | Lap number associated with the current sector 3 value |
| sector_1_source | string | Source used for the current sector 1 value |
| sector_2_source | string | Source used for the current sector 2 value |
| sector_3_source | string | Source used for the current sector 3 value |
| sector_1_overall_fastest | boolean | True if the current sector 1 time is the fastest by any driver this session |
| sector_1_personal_fastest | boolean | True if the current sector 1 time is this driver's personal best |
| sector_2_overall_fastest | boolean | True if the current sector 2 time is the overall fastest |
| sector_2_personal_fastest | boolean | True if the current sector 2 time is this driver's personal best |
| sector_3_overall_fastest | boolean | True if the current sector 3 time is the overall fastest |
| sector_3_personal_fastest | boolean | True if the current sector 3 time is this driver's personal best |
| best_sector_1 | number | Driver's personal best sector 1 time this session (or segment, in qualifying) |
| best_sector_2 | number | Driver's personal best sector 2 time this session (or segment, in qualifying) |
| best_sector_3 | number | Driver's personal best sector 3 time this session (or segment, in qualifying) |
| best_sector_1_lap | number | Lap number for the driver's personal best sector 1 |
| best_sector_2_lap | number | Lap number for the driver's personal best sector 2 |
| best_sector_3_lap | number | Lap number for the driver's personal best sector 3 |
| best_sector_1_session_part | string | Qualifying segment/session part for the best sector 1 value |
| best_sector_2_session_part | string | Qualifying segment/session part for the best sector 2 value |
| best_sector_3_session_part | string | Qualifying segment/session part for the best sector 3 value |
| sector_state | string | Current sector tracking state for the driver |
| sector_current_lap | number | Lap currently being tracked for sector timing |
| last_completed_sector | number | Last completed sector number |
| sectors | object | Structured sector details with `current` and `personal_best` sector objects |
| q1_time | string | Best lap time set in Q1; `null` if no time was set or outside qualifying |
| q1_knocked_out | boolean | True if the driver did not advance past Q1; `null` outside qualifying |
| q1_position | number | Finishing rank in Q1 based on best lap time; `null` if no time was set |
| q2_time | string | Best lap time set in Q2; `null` if did not participate or no time set |
| q2_knocked_out | boolean | True if the driver did not advance past Q2; `null` outside qualifying |
| q2_position | number | Finishing rank in Q2; `null` if no time was set |
| q3_time | string | Best lap time set in Q3; `null` if did not participate |
| q3_knocked_out | boolean | Always `false` (Q3 is the final segment); `null` outside qualifying |
| q3_position | number | Finishing rank in Q3; `null` if no time was set |

<details>
<summary>JSON Structure Example — Race</summary>

```json
{
  "drivers": [
    {
      "racing_number": "1",
      "tla": "VER",
      "name": "Max Verstappen",
      "team": "Red Bull Racing",
      "team_color": "#3671C6",
      "team_color_rgb": [54, 113, 198],
      "grid_position": "1",
      "current_position": "1",
      "laps": {
        "1": "1:32.456",
        "2": "1:31.789",
        "3": "1:31.234"
      },
      "completed_laps": 45,
      "status": "on_track",
      "in_pit": false,
      "pit_out": false,
      "retired": false,
      "stopped": false,
      "fastest_lap": true,
      "fastest_lap_time": "1:29.123",
      "fastest_lap_time_secs": 89.123,
      "fastest_lap_lap": 42,
      "sector_1": 28.123,
      "sector_2": null,
      "sector_3": null,
      "sector_1_overall_fastest": true,
      "sector_1_personal_fastest": true,
      "sector_2_overall_fastest": null,
      "sector_2_personal_fastest": null,
      "sector_3_overall_fastest": null,
      "sector_3_personal_fastest": null,
      "best_sector_1": 27.891,
      "best_sector_2": 31.456,
      "best_sector_3": 29.776,
      "q1_time": null,
      "q1_knocked_out": null,
      "q1_position": null,
      "q2_time": null,
      "q2_knocked_out": null,
      "q2_position": null,
      "q3_time": null,
      "q3_knocked_out": null,
      "q3_position": null
    }
  ],
  "total_laps": 70,
  "fastest_lap": {
    "racing_number": "1",
    "tla": "VER",
    "name": "Max Verstappen",
    "team": "Red Bull Racing",
    "team_color": "#3671C6",
    "team_color_rgb": [54, 113, 198],
    "lap": 42,
    "time": "1:29.123",
    "time_secs": 89.123
  },
  "current_qualifying_part": null
}
```

</details>

<details>
<summary>JSON Structure Example — Qualifying</summary>

```json
{
  "drivers": [
    {
      "racing_number": "1",
      "tla": "VER",
      "name": "Max Verstappen",
      "team": "Red Bull Racing",
      "team_color": "#3671C6",
      "team_color_rgb": [54, 113, 198],
      "grid_position": "1",
      "current_position": "1",
      "laps": {},
      "completed_laps": 6,
      "status": "on_track",
      "in_pit": false,
      "pit_out": false,
      "retired": false,
      "stopped": false,
      "fastest_lap": false,
      "fastest_lap_time": null,
      "fastest_lap_time_secs": null,
      "fastest_lap_lap": null,
      "sector_1": 16.911,
      "sector_2": null,
      "sector_3": null,
      "sector_1_overall_fastest": true,
      "sector_1_personal_fastest": true,
      "sector_2_overall_fastest": null,
      "sector_2_personal_fastest": null,
      "sector_3_overall_fastest": null,
      "sector_3_personal_fastest": null,
      "best_sector_1": 16.802,
      "best_sector_2": 44.213,
      "best_sector_3": 22.087,
      "q1_time": "1:23.100",
      "q1_knocked_out": false,
      "q1_position": 3,
      "q2_time": "1:22.500",
      "q2_knocked_out": false,
      "q2_position": 2,
      "q3_time": "1:21.987",
      "q3_knocked_out": false,
      "q3_position": 1
    },
    {
      "racing_number": "10",
      "tla": "GAS",
      "name": "Pierre Gasly",
      "team": "Alpine",
      "team_color": "#FF87BC",
      "grid_position": "16",
      "current_position": "16",
      "laps": {},
      "completed_laps": 4,
      "status": "on_track",
      "in_pit": false,
      "pit_out": false,
      "retired": false,
      "stopped": false,
      "fastest_lap": false,
      "fastest_lap_time": null,
      "fastest_lap_time_secs": null,
      "fastest_lap_lap": null,
      "sector_1": null,
      "sector_2": null,
      "sector_3": null,
      "sector_1_overall_fastest": null,
      "sector_1_personal_fastest": null,
      "sector_2_overall_fastest": null,
      "sector_2_personal_fastest": null,
      "sector_3_overall_fastest": null,
      "sector_3_personal_fastest": null,
      "best_sector_1": null,
      "best_sector_2": null,
      "best_sector_3": null,
      "q1_time": "1:24.892",
      "q1_knocked_out": true,
      "q1_position": 16,
      "q2_time": null,
      "q2_knocked_out": false,
      "q2_position": null,
      "q3_time": null,
      "q3_knocked_out": false,
      "q3_position": null
    }
  ],
  "total_laps": null,
  "fastest_lap": null,
  "current_qualifying_part": 3
}
```

</details>

<details>
<summary>Jinja2 Template Examples</summary>

**Get the race leader:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% if drivers %}
  {% set leader = drivers | selectattr('current_position', 'eq', '1') | first %}
  {% if leader %}
    Leader: {{ leader.tla }} ({{ leader.name }})
  {% endif %}
{% endif %}
```

**Get a specific driver by number:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% set driver = drivers | selectattr('racing_number', 'eq', '44') | first %}
{% if driver %}
  {{ driver.name }} is in P{{ driver.current_position }}
{% endif %}
```

**Get driver's last lap time:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% set driver = drivers | selectattr('racing_number', 'eq', '1') | first %}
{% if driver and driver.laps %}
  {% set last_lap = driver.completed_laps | string %}
  Last lap: {{ driver.laps.get(last_lap, 'N/A') }}
{% endif %}
```

**List all drivers in pit lane:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% for d in drivers if d.status == 'pit_in' %}
  {{ d.tla }} is in the pits
{% endfor %}
```

**Show race progress:**
```jinja2
{% set current = states('sensor.f1_driver_positions') %}
{% set total = state_attr('sensor.f1_driver_positions', 'total_laps') %}
{% if current != 'unknown' and total %}
  Lap {{ current }} of {{ total }}
{% endif %}
```

**Get position changes from grid:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% for d in drivers %}
  {% set change = d.grid_position | int - d.current_position | int %}
  {{ d.tla }}: {% if change > 0 %}+{% endif %}{{ change }}
{% endfor %}
```

**Get Q3 qualifying results sorted by position:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% set q3 = drivers | selectattr('q3_time', 'ne', None) | sort(attribute='q3_position') %}
{% for d in q3 %}
  P{{ d.q3_position }}: {{ d.tla }} — {{ d.q3_time }}
{% endfor %}
```

**List drivers knocked out in Q1:**
```jinja2
{% set drivers = state_attr('sensor.f1_driver_positions', 'drivers') %}
{% for d in drivers if d.q1_knocked_out %}
  {{ d.tla }} eliminated in Q1 ({{ d.q1_time or 'no time' }})
{% endfor %}
```

**Show active qualifying segment:**
```jinja2
{% set part = state_attr('sensor.f1_driver_positions', 'current_qualifying_part') %}
{% if part %}
  Q{{ part }} in progress
{% endif %}
```

</details>
:::info
Fastest lap details are only exposed during races and sprints. In practice and qualifying, `fastest_lap` is `null` and each driver has `fastest_lap: false`.
:::
:::info
Sector times (`sector_1`, `sector_2`, `sector_3`) update live as drivers complete each sector during a lap. The companion `sector_*_lap` and `sector_*_source` fields identify which lap and timing source produced the value. The `sectors` object exposes the same data in a structured shape with `current.sector_1`, `current.sector_2`, `current.sector_3`, and matching `personal_best` sector objects.
:::
:::info
Gap data (`gap_to_leader` and `interval_to_position_ahead`) comes from public live timing when available. These fields may be `null` or blank outside race/sprint running, at the start of a session, or when the broadcast feed withholds intervals.
:::
:::info
Qualifying segment data (`q1_time`, `q2_time`, `q3_time` and their associated `_knocked_out` and `_position` fields) is only populated during qualifying and sprint shootout sessions. In all other session types these fields are `null`. All 20 drivers are always present regardless of whether they set a time. `q1_knocked_out: true` means the driver did not advance to Q2, and `q2_knocked_out: true` means the driver did not reach Q3.
:::


## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
