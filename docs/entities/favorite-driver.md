---
id: favorite-driver
title: "Favorite Driver"
description: "Live position and timing details for a driver selected in select.f1_favorite_driver \u2014 state, attributes, and examples for F1 Sensor."
---

Live position and timing details for a driver selected in select.f1_favorite_driver. Use `sensor.f1_favorite_driver` and `select.f1_favorite_driver` in dashboards, templates, and automations.

See [live data availability](/entities/live-data#availability-model) for session and data-source requirements. The details below describe any additional conditions for this entity.

:::info[Find your entity]
These are standard entity IDs. If Home Assistant assigned a different ID, or you renamed an entity, use your existing ID in the examples.
:::

## State and attributes

`select.f1_favorite_driver` lets you choose a driver by their three-letter abbreviation. The selection is saved for this F1 Sensor configuration entry and is restored after Home Assistant restarts.

Enable **Favorite driver** in the integration options first. It is disabled by default for both new and existing configurations.

`sensor.f1_favorite_driver` exposes that driver's current position as its state. Its attributes include the driver name, team color in hex and RGB formats, racing number, grid position, gap, interval, lap times, pit state, retirement state, and tyre information. The sensor is unavailable until the selected driver appears in live timing. The RGB value can be passed directly to compatible Home Assistant lights.

The Drivers device also provides triggers for the selected driver gaining or losing a position, entering or exiting the pits, and retiring. These triggers respect the integration's configured [Live Delay](/features/live-delay).


## State

`sensor.f1_favorite_driver` has the selected driver’s position as its numeric state, or no value if the available timing has no position. It is unavailable when the selected driver has no snapshot or the timing source is unavailable.

```text
4
```

## Attributes

Fields taken from timing can be null when upstream data is incomplete. Boolean pit and retirement fields describe the latest normalized timing data.

| Attribute | Type | Description |
| --- | --- | --- |
| `selected` | string | Saved three-letter driver abbreviation, or null |
| `racing_number` | string | Driver’s racing number |
| `tla` | string | Three-letter driver abbreviation |
| `name` | string | Driver’s name |
| `team` | string | Team name |
| `team_color` | string | Hex color including `#`, when available |
| `team_color_rgb` | list | Red, green, and blue values, when a valid hex color is available |
| `position` | number | Current position |
| `grid_position` | number | Grid position from lap history, when available |
| `gap_to_leader` | string | Gap to the leader from timing data |
| `interval_to_position_ahead` | string | Interval to the driver ahead |
| `last_lap` | string | Latest lap time |
| `best_lap` | string | Best lap time |
| `in_pit` | boolean | Whether the driver is in the pit lane |
| `pit_out` | boolean | Whether timing marks the driver as leaving the pits |
| `pit_stops` | number | Pit stop count |
| `retired` | boolean | Whether timing marks the driver as retired |
| `stopped` | boolean | Whether timing marks the car as stopped |
| `status_code` | number or string | Status value supplied by timing data |
| `compound` | string | Current tyre compound |
| `stint_laps` | number or string | Current tyre stint laps; numeric strings are converted when possible |
| `new_tyres` | boolean | Whether the tyres were new at the start of the stint |

## Select a driver

`select.f1_favorite_driver` offers the available three-letter abbreviations and **No driver** to clear the selection. The selected abbreviation remains saved across restarts and can remain in the list while that driver has no current timing data.

```yaml
action: select.select_option
target:
  entity_id: select.f1_favorite_driver
data:
  option: NOR
```

## Automation events

The [Drivers device](/reference/device-triggers#drivers-device) offers five triggers for position gains/losses, pit entry/exit, and retirement. Advanced automations can use the [Favorite Driver event payload](/entities/events#favorite-driver). A change in position does not prove that an overtake occurred on track.

## Next steps

- [Browse the entity reference](/reference/overview)
- [Build an automation](/automation)
- [Choose a dashboard card](/cards/cards-overview)
