---
id: track-map
title: Follow cars on Track Map
description: Understand Track Map availability, add the card, and resolve waiting or stale position data.
---

The **Track map** module shows car markers on a circuit map during live or replay sessions. Add it to the [F1 Sensor card](/cards/cards-overview) when you want a quick visual view of where cars are on track.

## Availability

| Mode | Availability |
| --- | --- |
| Public live timing | Not available during live sessions |
| F1TV Auth live timing | Available when a valid token unlocks live car position data and the session publishes usable data |
| Replay Mode | Best effort when the replay archive contains car position data |

Live Track Map depends on [F1TV Auth](/features/f1tv-auth). Replay Track Map is separate from live auth and can work later from archived replay data when the session archive contains car positions.

During live sessions, Track Map follows the configured [Live Delay](/features/live-delay). This keeps car markers aligned with the other modules and with delayed TV or streaming broadcasts. Replay Track Map is not delayed.

## What to expect

The card shows a circuit outline, driver markers, optional lap progress, and track status context. If the session does not provide usable car positions, the card waits instead of showing misleading locations.

If Formula 1 publishes an invalid position frame, for example a frame that places every on-track car at the same zero coordinates, the card marks position data as unavailable and keeps the last usable markers stale instead of moving every car to the wrong place. It automatically recovers when valid positions return.

Supported circuits can show a map quickly. For newer or unsupported circuits, replay data may need enough usable position updates before the map can be drawn.

## Optional circuit markings

In the modular card editor, select the start/finish line, corner numbers, sector boundaries, speed trap, and detection and activation points separately. Markings are available only when the session year, circuit layout, and map geometry match a reviewed source. The card lists selected markings below the map, including labels hidden behind moving cars. It says when a selected marking has no verified position for the session.

These choices belong to each Track map module. Clear **Show car markers** under
**Module options** to show the circuit without cars, and add **Driver positions
list** if you still want the car statuses in text. Existing cards keep their
current car-marker behavior and gain no markings until you select a layer.

| Circuit and season | Reviewed markings | Coverage note |
| --- | --- | --- |
| Singapore, 2025 | Start/finish, turns 1–19, S1 and S2 boundaries, speed trap, three DRS detection points, three DRS activation points | The fourth DRS activation point is omitted because its position cannot be placed confidently on the simplified map. |
| Silverstone, 2025 | Start/finish, turns 1–18, S1 and S2 boundaries, speed trap, two DRS detection points, two DRS activation points | All listed 2025 map points are included. |
| Singapore, 2026 | Start/finish, turns 1–19, S1 and S2 boundaries, speed trap, one Overtake activation point, and nine Straight Mode activation points | The Overtake detection point is omitted because the FIA map specifies only “Entry T17”. Straight Mode A2 has no low-grip activation point. |

The start/finish line also marks the end of sector 3. Sector boundaries follow the published locations; they are not equal thirds of the lap. Speed trap markers show the measurement location, not a measured speed. DRS, Overtake and Straight Mode markers show individual detection or activation points, not full zones. For 2026 Straight Mode labels, **N** means normal grip and **L** means low grip. These markings do not change timing or incident calculations.

The positions were checked against the FIA circuit maps for [Singapore 2025](https://www.fia.com/system/files/decision-document/2025_singapore_grand_prix_-_event_notes_-_circuit_map_pit_lane_emergency_exits_map_and_quarantine_zone.pdf), [Silverstone 2025](https://www.fia.com/system/files/decision-document/2025_british_grand_prix_-_event_notes_-_circuit_map_v2.pdf), and [Singapore 2026](https://www.fia.com/system/files/decision-document/2026_singapore_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_and_emergency_exits_map.pdf). Circuit coordinates were checked against the corresponding [Singapore 2025](https://api.multiviewer.app/api/v1/circuits/61/2025), [Silverstone 2025](https://api.multiviewer.app/api/v1/circuits/2/2025), and [Singapore 2026](https://api.multiviewer.app/api/v1/circuits/61/2026) data. Other years and layouts remain unmarked until they are reviewed separately. Car positions and the circuit outline can still appear when some or all markings are unavailable.

<span id="add-the-track-map-card" />
<span id="card-options" />

## Add the Track map module

Edit an **F1 Sensor** card and select **Add module > Track map**. Start with automatic entry selection, then adjust driver labels, focus, map orientation, lap progress and track-status presentation under **Module options**.

For a card containing only the map:

```yaml
type: custom:f1-sensor-card
version: 3
title: F1 Track Map
modules:
  - type: map
    id: map-1
```

The module uses the F1 Sensor installation selected for the card. It can inherit the shared driver focus or use an independent focus.

## Status messages

| Status | Meaning |
| --- | --- |
| `Live` | The card is receiving live Track Map data |
| `Replay` | Replay Mode is playing Track Map data |
| `Waiting` | A session is loaded but no car positions are available yet |
| `Stale` | The latest live position data is too old to trust |
| `No position data` | Replay position data is unavailable at this point in the loaded session |
| `No geometry` | Car positions exist but the map outline is not ready |
| `No session` | No live or replay session is loaded for Track Map |
| `Not loaded` | The card has not received a Track Map snapshot yet |

If car position data is missing, stale, or incomplete, the card waits instead of showing misleading car positions.

## Incident location context

When Track Map data is fresh enough, [Incident Detection](/features/incident-detection) can use it as optional location context. This can add a neutral location summary to `f1_sensor_incident` events, such as on-track status, sector, stale state, or pit-lane context.

Track Map is not required for incident detection. Public confirmed incident alerts continue to work without F1TV Auth and without Track Map.

## Troubleshooting

### Cars do not show during a live session

Live Track Map requires [F1TV Auth](/features/f1tv-auth) and live car position data. Check `sensor.f1_f1tv_token_status`, then check the Track Map card status. If the diagnostic entity is present, `sensor.f1_live_timing_mode` can also help confirm that live timing is active.

### Replay shows a map but live does not

Replay Mode can use archived car position data after the session. That does not mean the same data is available from public live timing. Live Track Map still needs F1TV Auth.

### The card says Stale

The last live position update is older than the Track Map freshness window. This can happen when Formula 1 stops publishing position updates, the session is inactive, or the saved token stops working.

### The card says No geometry

The card has car position data but cannot yet draw the map outline. This is more likely on newer or unsupported circuits, especially before enough replay data is available.

## Limitations

- Live Track Map requires an active F1 session with usable position data and working F1TV Auth.
- Replay Track Map is best effort and depends on the archived session data.
- The map outline may be unavailable for unknown circuits until enough replay data exists.
- Track Map is a module in the F1 Sensor dashboard card, not a normal Home Assistant entity.
- Circuit markings are currently limited to Singapore 2025 and 2026, and Silverstone 2025. Other seasons and layouts have no verified marks, even if their map outline and car positions are available.

## Optional demonstration

[Open the existing Track Map animation](/img/track_map_card.gif) if you want to see marker movement. The image above and the written instructions cover the setup without animation.

## Related pages

- [F1TV Auth](/features/f1tv-auth)
- [Replay Mode](/features/replay-mode)
- [Incident Detection](/features/incident-detection)
- [F1 Sensor card](/cards/cards-overview)
- [Diagnostics](/entities/diagnostics)
