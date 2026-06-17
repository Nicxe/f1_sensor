---
id: track-map
title: Track Map
---

Track Map shows car markers on a circuit map during live or replay sessions. It is designed for dashboards where you want a quick visual view of where cars are on track.

![Track Map card showing car markers on a circuit map](/img/track_map_card.gif)

## Availability

| Mode | Availability |
| --- | --- |
| Public live timing | Not available during live sessions |
| F1TV Auth live timing | Available when a valid token unlocks live car position data and the session publishes usable data |
| Replay Mode | Best effort when the replay archive contains car position data |

Live Track Map depends on [F1TV Auth](/features/f1tv-auth). Replay Track Map is separate from live auth and can work later from archived replay data when the session archive contains car positions.

During live sessions, Track Map follows the configured [Live Delay](/features/live-delay). This keeps car markers aligned with the rest of the Live Data Cards and with delayed TV or streaming broadcasts. Replay Track Map is not delayed.

## What to expect

The card shows a circuit outline, driver markers, optional lap progress, and track status context. If the session does not provide usable car positions, the card waits instead of showing misleading locations.

If Formula 1 publishes an invalid position frame, for example a frame that places every on-track car at the same zero coordinates, the card marks position data as unavailable and keeps the last usable markers stale instead of moving every car to the wrong place. It automatically recovers when valid positions return.

Supported circuits can show a map quickly. For newer or unsupported circuits, replay data may need enough usable position updates before the map can be drawn.

## Add the Track Map card

Add the bundled card from the Home Assistant dashboard editor, or use YAML:

```yaml
type: custom:f1-track-map-card
title: F1 Track Map
entry_id: auto
lap_count_entity: auto
track_status_entity: auto
```

The card is bundled with F1 Sensor and is registered with the other [Live Data Cards](/cards/cards-overview).

## Card options

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme. Use `dark`, `light`, or `auto` |
| `title` | `F1 Track Map` | Card title |
| `entry_id` | `auto` | F1 Sensor config entry to use. `auto` works for most installations |
| `throttle_ms` | `100` | Minimum time between snapshot updates in milliseconds |
| `interpolation_ms` | `auto` | Driver marker interpolation timing |
| `invert_y` | `true` | Invert the Y axis for the map projection |
| `show_header` | `true` | Show the card header |
| `show_footer` | `true` | Show source and status details at the bottom |
| `show_session_info` | `true` | Show meeting and session text |
| `show_driver_count` | `true` | Show the number of drivers currently displayed |
| `driver_label_mode` | `tla` | Use `tla`, `number`, or `off` for driver labels |
| `show_lap_progress` | `true` | Show lap progress when a lap count entity is available |
| `lap_count_entity` | `auto` | Lap count entity. Empty disables lap progress context |
| `show_track_status` | `true` | Show track status context when available |
| `track_status_entity` | `auto` | Track status entity. Empty disables track status context |
| `track_status_line_mode` | `accent` | Use `accent`, `full`, or `off` for track status line coloring |
| `layout_mode` | `auto` | Use `auto`, `compact`, or `full` layout |

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

- Live Track Map cannot be fully verified without an active F1 session and working F1TV Auth.
- Replay Track Map is best effort and depends on the archived session data.
- The map outline may be unavailable for unknown circuits until enough replay data exists.
- Track Map is a dashboard card feature, not a normal Home Assistant entity.

## Related pages

- [F1TV Auth](/features/f1tv-auth)
- [Replay Mode](/features/replay-mode)
- [Incident Detection](/features/incident-detection)
- [Live Data Cards](/cards/cards-overview)
- [Diagnostics](/entities/diagnostics)
