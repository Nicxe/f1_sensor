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
| F1TV Auth live timing | Requires account permission for live car positions and usable position data from the active session |
| Replay Mode | Best effort when the replay archive contains car position data |

Live Track Map depends on [F1TV Auth](/features/f1tv-auth) and your account’s live-data permissions. During United States FP1 on 23 October 2026, live positions arrived with the tested paid account and did not arrive with the tested free account in five comparison windows. A valid token alone does not guarantee live positions. This observation does not establish the requirements for every subscription plan.

Replay Track Map can work with a free Formula 1 account when the completed-session archive contains usable car positions. Archive access and live position access are separate.

During live sessions, Track Map follows the configured [Live Delay](/features/live-delay). This keeps car markers aligned with the other modules and with delayed TV or streaming broadcasts. Replay Track Map is not delayed.

## What to expect

The card shows a circuit outline, driver markers, optional lap progress, and track status context. If the session does not provide usable car positions, the card waits instead of showing misleading locations.

If Formula 1 publishes an invalid position frame, for example a frame that places every on-track car at the same zero coordinates, the card marks position data as unavailable and keeps the last usable markers stale instead of moving every car to the wrong place. It automatically recovers when valid positions return.

Supported circuits can show a map quickly. For newer or unsupported circuits, replay data may need enough usable position updates before the map can be drawn.

## Optional circuit markings

:::warning Experimental circuit markings
The optional circuit markings are experimental in both beta and stable releases. Their positions may need corrections as more sessions and layouts are checked. If a marking looks wrong, [report it on GitHub](https://github.com/Nicxe/f1_sensor/issues/new) with the circuit, season, and a screenshot. The circuit outline and car positions are separate from these markings.
:::

In the modular card editor, select the start/finish line, corner numbers, sector boundaries, speed trap, and detection and activation points separately. Markings are available only when the session year, circuit layout, and map geometry match a reviewed source. The map uses a solid start/finish line, smaller dashed sector lines, compact corner numbers, and small ticks for speed and activation points. Markings remain visible when a car passes; the expandable list below the map gives their full descriptions. The card says when a selected marking has no verified position for the session.

These choices belong to each Track map module. Clear **Show car markers** under
**Module options** to show the circuit without cars, and add **Driver positions
list** if you still want the car statuses in text. Existing cards keep their
current car-marker behavior and gain no markings until you select a layer.

| Circuit and season | Reviewed markings | Coverage note |
| --- | --- | --- |
| Singapore, 2025 | Start/finish, turns 1–19, two sector boundaries, speed trap, three DRS detection points, three DRS activation points | The fourth DRS activation point is omitted because its position cannot be placed confidently on the simplified map. |
| Silverstone, 2025 | Start/finish, turns 1–18, two sector boundaries, speed trap, two DRS detection points, two DRS activation points | All listed 2025 map points are included. |
| 2026: Australia, China, Japan, Miami, Canada, Monaco, Barcelona-Catalunya, Austria, Britain, Belgium, Hungary, Netherlands, Italy, Azerbaijan, Singapore, Sepang, Madrid | Start/finish, numbered corners, two sector boundaries, speed trap, and FIA Overtake/Straight Mode points with measurable positions | These 17 circuits have reviewed 2026 circuit geometry and FIA event maps. Some points stated only as a corner entry, apex, or exit are omitted because the simplified map cannot place them precisely. |
| 2026: United States (Austin), Mexico City, São Paulo, Qatar, Abu Dhabi | Start/finish, numbered corners, two sector boundaries, and speed trap | Prepared from 2025 FIA event maps and prior position-coordinate references, displayed with a previous-season baseline notice. No Overtake or Straight Mode points are inferred from 2025 DRS data. |

Sepang uses the 2026 Bahrain Grand Prix in Malaysia map and its Sepang layout. Madrid uses the 2026 Spanish Grand Prix map and the Madring layout; it does not reuse Barcelona-Catalunya's geometry or annotations. The 2025 catalog remains limited to Singapore and Silverstone.

The five upcoming 2026 venues above have a pre-race baseline so their stable markings are available before the first 2026 session. The baseline uses each venue's 2025 FIA event map for published sectors and speed-trap offsets, then places corner and start/finish references on the matching 2025 `Position.z` circuit shape. Some coordinate references originate from older provider data, so the card identifies these markings as a previous-season baseline. Review them against the event-specific 2026 FIA map and position stream when those become available. Las Vegas is intentionally left without annotations because the available corner numbering conflicts with the 2025 FIA map and cannot yet be reconciled safely.

The baseline list is deliberately limited to stable, measured marks. The 2025 DRS positions do not establish the 2026 Overtake or Straight Mode locations, and no such marks are shown until a current FIA source provides usable positions. The FIA's event maps are also not enough to place a pit-lane anchor accurately on the simplified centreline, so static pit markers remain unavailable. Corrections can be collected across race weekends and shipped together as a catalog update rather than requiring a release for each event.

Sector 1 runs from the start/finish line to the first dashed boundary. The small **S2** and **S3** labels mark where those sectors begin; the start/finish line also marks the end of sector 3. Sector boundaries follow the published locations; they are not equal thirds of the lap. **SPD** is the speed measurement point, not a measured speed. **SM1–SM5** identify Straight Mode activation groups. Where both positions exist, **SM1 N/L** and similar labels refer to two nearby ticks: a solid tick for normal-grip activation (**N**) and a dashed tick for low-grip activation (**L**). **SM2 N** has only one tick because the published map has no low-grip A2 point. **OT** marks Overtake activation. The list below the map gives each point's full description. DRS, Overtake and Straight Mode marks show individual detection or activation points, not full zones. These markings do not change timing or incident calculations.

The FIA circuit drawings include pit lanes, but the reviewed annotation catalog does not contain a verified pit-lane anchor on the simplified map. Driver pit status can be shown in the driver list; a static pit location will need its own coordinate review before it can be marked on the circuit.

The positions are checked against each circuit's FIA 2026 map and a season-specific centreline source. Sepang's turn anchors use the public Sepang centreline aligned to the 2026 telemetry geometry. Madrid's anchors use the Madrid City Geoportal centreline aligned to the 2026 telemetry geometry. The catalog records these source links for each supported circuit. The 2025 positions remain tied to the separate Singapore and Silverstone sources listed above. Other years and layouts remain unmarked until reviewed separately. Car positions and the circuit outline can still appear when some or all markings are unavailable.

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

Live Track Map requires [F1TV Auth](/features/f1tv-auth), account permission for live positions, and published position data. Check `sensor.f1_f1tv_token_status`, then check the Track Map card status. A `valid` token can still belong to an account that does not receive live positions; repeated pairing alone is not a test of those permissions. If the diagnostic entity is present, `sensor.f1_live_timing_mode` can also help confirm that live timing is active.

### Replay shows a map but live does not

Replay Mode can use archived car position data after the session. That does not mean the same data is available from public live timing. Live Track Map still needs F1TV Auth and account permission for live positions.

### The card says Stale

The last live position update is older than the Track Map freshness window. This can happen when Formula 1 stops publishing position updates, the session is inactive, or the saved token stops working.

### The card says No geometry

The card has car position data but cannot yet draw the map outline. This is more likely on newer or unsupported circuits, especially before enough replay data is available.

## Limitations

- Live Track Map requires an active F1 session with usable position data, working F1TV Auth, and account permission for live positions.
- Replay Track Map is best effort and depends on the archived session data.
- The map outline may be unavailable for unknown circuits until enough replay data exists.
- Track Map is a module in the F1 Sensor dashboard card, not a normal Home Assistant entity.
- Circuit markings are available for Singapore and Silverstone in 2025; 17 circuits have reviewed 2026 event-map data, and five more have a clearly labelled 2025 baseline. Las Vegas is not annotated until its conflicting turn references can be reconciled. Madring's FIA Overtake detection point is listed only as “Entry T22” without a measured offset, so it is omitted. Other seasons and layouts have no reviewed markings, even if their map outline and car positions are available.

## Optional demonstration

[Open the existing Track Map animation](/img/track_map_card.gif) if you want to see marker movement. The image above and the written instructions cover the setup without animation.

## Related pages

- [F1TV Auth](/features/f1tv-auth)
- [Replay Mode](/features/replay-mode)
- [Incident Detection](/features/incident-detection)
- [F1 Sensor card](/cards/cards-overview)
- [Diagnostics](/entities/diagnostics)
