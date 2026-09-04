---
id: device-triggers
title: Device triggers
description: Choose F1 Sensor device triggers for race state, flags, incidents, team radio, and your favorite driver.
---

Device triggers let you build automations in Home Assistant without entering entity IDs manually. Choose the F1 Sensor device that owns the data, then select the event or state change you want.

## Choose a device

The easiest way to build automations is through the Home Assistant UI using device triggers. Go to **Settings > Devices & Services > Devices**, select any F1 Sensor sub-device, and choose **Automations > Add trigger** to see the available triggers without writing any YAML.
:::info
Device triggers are the recommended starting point. Home Assistant stores the selected device and entity references. For ready-to-use YAML, see [Automation recipes](/automation#yaml-examples).
:::

Triggers are organized per sub-device. Only triggers whose backing entity is enabled will appear.

## Race device

| Trigger | Trigger type | Fires when |
| --- | --- | --- |
| Race week started | `race_week_started` | The race week indicator turns on |
| Race week ended | `race_week_ended` | The race week indicator turns off |

## Session device

| Trigger | Trigger type | Fires when |
| --- | --- | --- |
| Safety car deployed | `safety_car_deployed` | Safety car or Virtual Safety Car becomes active |
| Safety car cleared | `safety_car_cleared` | Safety car or Virtual Safety Car is cleared |
| Formation start ready | `formation_start_ready` | Formation start procedure is ready |
| Overtake mode enabled | `overtake_mode_enabled` | Track-wide overtake mode is enabled (2026 regulation) |
| Overtake mode disabled | `overtake_mode_disabled` | Track-wide overtake mode is disabled (2026 regulation) |
| Session live | `session_live` | Session status changes to `live` |
| Track status: CLEAR | `track_status_clear` | Track status becomes CLEAR |
| Track status: YELLOW | `track_status_yellow` | Track status becomes YELLOW |
| Track status: Safety Car | `track_status_safety_car` | Track status becomes SC |
| Track status: VSC | `track_status_vsc` | Track status becomes VSC |
| Track status: Red Flag | `track_status_red_flag` | Track status becomes RED |
| Possible on-track incident detected | `possible_on_track_incident_detected` | An incident event has phase `candidate` or `confirmed` for this F1 Sensor entry |
| Possible on-track incident cleared | `possible_on_track_incident_cleared` | No possible incident remains active |
| On-track incident detected | `on_track_incident_detected` | An incident event has phase `confirmed` for this F1 Sensor entry |
| On-track incident cleared | `on_track_incident_cleared` | No confirmed incident remains active |

## Officials device

| Trigger | Trigger type | Fires when |
| --- | --- | --- |
| New race control message | `new_race_control_message` | A new race control message is received |
| New FIA document | `new_fia_document` | A new FIA document is published |
| Investigation changed | `investigation_changed` | An investigation or penalty status changes |

## Drivers device

| Trigger | Trigger type | Fires when |
| --- | --- | --- |
| New team radio message | `new_team_radio` | A new Team Radio clip is published |
| Favorite driver gained a position | `favorite_driver_position_gained` | The selected driver’s position number decreases |
| Favorite driver lost a position | `favorite_driver_position_lost` | The selected driver’s position number increases |
| Favorite driver entered the pits | `favorite_driver_entered_pits` | The selected driver changes from outside the pit lane to in the pits |
| Favorite driver exited the pits | `favorite_driver_exited_pits` | The selected driver changes from in the pits to outside the pit lane |
| Favorite driver retired | `favorite_driver_retired` | The selected driver changes to retired |

Choose a driver with `select.f1_favorite_driver` and enable **Favorite driver** in the integration options before using these five triggers. They follow changes in the selected driver’s timing data; a position change does not, by itself, prove an on-track overtake. See the [Favorite Driver reference](/entities/favorite-driver).

## System device

| Trigger | Trigger type | Fires when |
| --- | --- | --- |
| Live timing online | `live_timing_online` | The live timing connectivity entity changes to `on`, including during replay |
| Live timing offline | `live_timing_offline` | The live timing connectivity entity changes to `off` |

---

## Incident triggers and event payloads

The two **detected** incident triggers react to matching incident events, scoped to the selected F1 Sensor entry. They can fire for another incident while an incident binary sensor is already on. **Cleared** triggers follow the corresponding binary sensor turning off when no matching incident remains active.

Use the [`f1_sensor_incident` event](/entities/events#on-track-incident) directly when you need to filter `updated` events, confidence, or session type. Favorite Driver device triggers also follow events for the selected entry. These event-based triggers do not offer a **For** duration; ordinary state-based device triggers can.

## Timing and replay

[Live Delay](/features/live-delay) aligns live updates with the broadcast. Replay can repeat historical state changes when you rewind, so replay-driven automations may run again. Test notification and light behavior with this in mind.

## Next steps

- [Build your first automation](/automation)
- [Browse states and entity attributes](/reference/overview)
- [Use event payloads](/entities/events)
