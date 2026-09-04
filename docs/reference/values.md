---
id: values
title: "State values and terminology"
description: "Look up F1 Sensor track flags, session phases, tyre compounds, and timing modes."
---

Use this section to understand the possible values for enum-type states and attributes across all live data sensors.

<details>
<summary>Tyre Compounds</summary>

| Value | Short | Color | Description |
| --- | --- | --- | --- |
| `SOFT` | S | `#FF0000` (red) | Soft compound - fastest, least durable |
| `MEDIUM` | M | `#FFFF00` (yellow) | Medium compound - balanced performance |
| `HARD` | H | `#FFFFFF` (white) | Hard compound - slowest, most durable |
| `INTERMEDIATE` | I | `#00FF00` (green) | Intermediate - light rain conditions |
| `WET` | W | `#0000FF` (blue) | Full wet - heavy rain conditions |

</details>

<details>
<summary>Track Status</summary>

| Value | Description |
| --- | --- |
| `CLEAR` | Normal racing conditions, green flag |
| `YELLOW` | Yellow flag - caution, hazard on track |
| `VSC` | Virtual Safety Car deployed |
| `SC` | Safety Car deployed |
| `RED` | Red flag - session stopped |

</details>

<details>
<summary>Session Status</summary>

| Value | Description |
| --- | --- |
| `pre` | Pre-session, typically 60-15 minutes before start |
| `live` | Session is active (lights out for race) |
| `suspended` | Session temporarily halted |
| `break` | Break between session segments |
| `finished` | Session has finished |
| `finalised` | Results have been finalised |
| `ended` | Session has ended |

**Typical transition flow:** `pre` → `live` → `suspended` ↔ `live` → `finished` → `finalised` → `ended`

</details>

<details>
<summary>Current Session Types</summary>

| Value | Description |
| --- | --- |
| `Practice 1` | First practice session |
| `Practice 2` | Second practice session |
| `Practice 3` | Third practice session |
| `Qualifying` | Qualifying session |
| `Sprint Qualifying` | Sprint qualifying/shootout |
| `Sprint` | Sprint race |
| `Race` | Main race |
| `unknown` | Session type not determined |

</details>

<details>
<summary>Live Timing Mode</summary>

| Value | Description |
| --- | --- |
| `idle` | No active session, connection inactive |
| `live` | Connected to live F1 timing feed |
| `replay` | Playing back recorded session data |

</details>

<details>
<summary>Driver Status (in driver_positions)</summary>

| Value | Description |
| --- | --- |
| `on_track` | Driver is currently on track |
| `pit_in` | Driver is in the pit lane |
| `pit_out` | Driver has just exited pits |
| `out` | Driver has retired or stopped |

</details>

<details>
<summary>Straight Mode (2026 regulation)</summary>

| Value | Description |
| --- | --- |
| `normal_grip` | Normal aerodynamic configuration permitted on straight sections |
| `low_grip` | Restricted aerodynamic configuration on straight sections |
| `disabled` | Straight mode system is not active |

</details>


## Related references

- [Live data entities](/entities/live-data)
- [Device triggers](/reference/device-triggers)
