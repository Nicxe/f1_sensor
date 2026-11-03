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

## What to expect

The card shows a circuit outline, driver markers, optional lap progress, and track status context. If the session does not provide usable car positions, the card waits instead of showing misleading locations.

If Formula 1 publishes an invalid position frame, for example a frame that places every on-track car at the same zero coordinates, the card marks position data as unavailable and keeps the last usable markers stale instead of moving every car to the wrong place. It automatically recovers when valid positions return.

Supported circuits can show a map quickly. For newer or unsupported circuits, replay data may need enough usable position updates before the map can be drawn.

## Optional circuit markings

Optionally show start/finish, corners, sectors, speed trap and reviewed activation or detection points. These layers are experimental and depend on the circuit, season and geometry. Existing cards gain no markings until you select a layer.

[Choose layers and read the complete coverage and source catalog](/features/track-map-markings).

<span id="add-the-track-map-card" />
<span id="card-options" />


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
- Circuit markings are available for Singapore and Silverstone in 2025; 17 circuits have reviewed 2026 event-map data, and five more have a clearly labelled 2025 baseline. Las Vegas is not annotated until its conflicting turn references can be reconciled. Madring's FIA Overtake detection point is listed only as “Entry T22” without a measured offset, so it is omitted. Other seasons and layouts have no reviewed markings, even if their map outline and car positions are available. See [the complete marking catalog and sources](/features/track-map-markings).

## Optional demonstration

[Watch Track Map in the introduction on YouTube (00:48)](https://www.youtube.com/watch?v=R72LXKdiNxA&t=48s).

[Open the existing Track Map animation](/img/track_map_card.gif) if you want to see marker movement. The written instructions cover the setup without animation.

## Related pages

- [F1TV Auth](/features/f1tv-auth)
- [Replay Mode](/features/replay-mode)
- [Incident Detection](/features/incident-detection)
- [F1 Sensor card](/cards/cards-overview)
- [Diagnostics](/entities/diagnostics)
