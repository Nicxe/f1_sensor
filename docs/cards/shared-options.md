---
id: shared-options
title: Shared card options
description: Choose F1 Sensor data sources, themes, typography, spoiler protection and dashboard actions.
---

Use these options to keep your F1 dashboard consistent. Each [card reference](/cards/cards-overview) lists its own data sources and display controls; this page explains the behavior shared across cards.

## Entity selection

Bundled cards discover the entity IDs created by F1 Sensor, including renamed IDs and suffixes such as `_2`. With one integration entry, empty and standard default data sources connect automatically to that entry.

In the visual editor, open **Data Sources** and select the matching F1 Sensor entity. Its display name may be translated; the YAML key and entity ID are separate from that label.

The source option is specific to the card. For example, Next Race uses `next_race_entity`, while Results uses `entity`:

```yaml
type: custom:f1-next-race-card
next_race_entity: sensor.f1_next_race
```

Keep your existing entity IDs after an upgrade. Do not rename an entity just to match an example.

### Multiple entries

Select one source entity from the intended F1 Sensor entry. The card uses that selection to connect its other standard sources to the same entry. Explicit custom selections remain in place.

| Option | Default | Use |
| --- | --- | --- |
| `f1_entry_id` | Automatically selected | Advanced override for the integration entry used by automatic entity selection. Prefer choosing a source in the editor. |
| `entry_id` | Card-specific | Used by Track Map and Weekend Hub for their direct connection. Their references explain `auto` and explicit entry selection. |
| `history_entry_id` | `auto` | Used by Results for Archive requests. |

An entry ID identifies an integration setup, not an entity. If you need an explicit ID, use the F1 Sensor entry you intend to display; do not paste a sensor ID into an entry field.

## Appearance

| Option | Values | Default |
| --- | --- | --- |
| `theme_mode` | `dark`, `light`, `auto` | `dark` on most cards; `auto` on the progression charts |
| `show_header` | `true`, `false` | Card-specific |
| `show_table_header` | `true`, `false` | Card-specific |
| `show_full_name` | `true`, `false` | Usually `false` |
| `show_team_logo` | `true`, `false` | Card-specific |
| `team_logo_style` | `color`, `white` | `color` where supported |

Use `theme_mode: auto` to follow Home Assistant. Header and column switches are available only where the card reference lists them. Replay Control uses `show_title` for its heading.

Home Assistant’s dashboard editor controls the card’s grid placement and available width. The cards adapt to that space. On a phone, begin with fewer optional columns, compact driver names and a short lap-history limit.

## Typography

All bundled cards support `font_style`:

| Value | Appearance |
| --- | --- |
| `wide` | Original F1 Sensor typography; the default. |
| `balanced` | F1-inspired typography with less wide lettering in dense or mobile text. |
| `system` | Home Assistant or system font. |

```yaml
type: custom:f1-next-race-card
next_race_entity: sensor.f1_next_race
theme_mode: auto
font_style: balanced
```

Dates, times and supported measurements follow the relevant Home Assistant locale and unit settings. This is separate from the card’s font or visual theme.

## Language and time preferences

Supported card and editor text follows Home Assistant's selected language. English and Swedish text is supplied; untranslated text falls back to English. Changing `theme_mode` or `font_style` does not change the language.

Dates and times use Home Assistant's locale and timezone where supported. Race Control timestamps also respect the profile's 12/24-hour preference. If a time looks wrong, check the Home Assistant profile and timezone settings before changing card YAML.

## Dashboard context

Weekend Hub shares **Focus driver**, **Gap reference** and the dashboard spoiler selection with supported cards in the browser. Driver Lap Times highlights the selected driver and uses the shared **Ahead**, **Leader** or **Off** gap reference.

These preferences are remembered in that browser. They do not set the integration's Favorite Driver selector or synchronize a television. Selecting a Results Archive event does not start a replay. Use [Favorite Driver](/features/favorite-driver) for persistent driver entities and automations, and [Replay Control](/cards/replay-control) to load historical timing.

## Spoiler protection

Cards that show spoiler-sensitive live or results data can use `no_spoiler_entity`. The usual default is `switch.f1_no_spoiler_mode`; Weekend Hub’s default helper differs and is listed on its reference page.

When protection is active, supported cards display an overlay or mask sensitive values. Do not hide or bypass that overlay to diagnose missing data. See [No Spoiler Mode](/features/no-spoiler-mode) for the integration’s behavior and the correct viewing workflow.

Weekend Hub also shares a spoiler selection with supported cards. This dashboard context is separate from the integration's No Spoiler switch.

Weekend Hub defaults to `input_boolean.f1_no_spoiler_mode`. If you use that helper, create it in Home Assistant; the card does not create it. **Hide analysis** / **Reveal analysis** can toggle a configured `input_boolean` as well as the browser's shared spoiler setting. To have the card also respect the integration switch, configure `no_spoiler_entity: switch.f1_no_spoiler_mode` instead. A configured switch must be changed in Home Assistant: the card's reveal button does not turn it off. An active source still keeps the card hidden even when the browser setting is cleared.

## Data availability notices

| Option | Default | Use |
| --- | --- | --- |
| `auth_status_entity` | `sensor.f1_f1tv_token_status` | Token status for cards with F1TV enhanced data. |
| `show_availability_notice` | `true` | Show informational notices explaining enhanced-data availability. |

Setting `show_availability_notice: false` hides informational notices only. Warnings about expired, invalid or rejected F1TV access remain visible because they require attention.

A card may combine public data with optional enhanced fields. Missing enhanced data does not necessarily mean that the entire card is unusable. Check the card’s **Availability** section and the [F1TV Auth guide](/features/f1tv-auth).

## Card actions

All bundled cards accept Home Assistant action objects:

| Option | Default | Gesture |
| --- | --- | --- |
| `tap_action` | More-info when an action entity is available; otherwise none | Tap or keyboard activation |
| `hold_action` | None | Hold |
| `double_tap_action` | None | Double-tap |

The card’s own buttons, selectors, links and chart controls keep their normal behavior. A tap action does not replace those controls.

Example: disable the background tap action while leaving card controls available.

```yaml
type: custom:f1-driver-lap-times-card
positions_entity: sensor.f1_driver_positions
tap_action:
  action: none
```

For configured actions, use Home Assistant’s action fields. The bundled cards also accept the older `call-service` form and translate it to `perform-action`.

## Related

- [Dashboard card catalog](/cards/cards-overview)
- [Card installation and updates](/cards/installation)
- [No Spoiler Mode](/features/no-spoiler-mode)
- [F1TV Auth](/features/f1tv-auth)
