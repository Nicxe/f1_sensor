---
id: cards-overview
title: Live Data Cards
---

# F1 Sensor Live Data Cards

A collection of custom Lovelace cards built specifically for the F1 Sensor integration. The cards are bundled with F1 Sensor and follow the entity structure exposed by the integration.

:::info[Bundled with F1 Sensor]
The live data cards are included with F1 Sensor. Home Assistant registers the bundled dashboard resource automatically when the integration starts.

They require the F1 Sensor integration. Cards that use live-only or F1TV Auth enhanced entities need those entities enabled in the integration.
:::

Public live timing works without F1TV Auth. Cards that show live Track Map, Pit Stops, or Championship Prediction can need optional [F1TV Auth](/features/f1tv-auth) during live sessions, while [Replay Mode](/features/replay-mode) can show archived data later when the replay contains it.

![Placeholder - F1 Sensor dashboard with multiple cards](/img/placeholder_cards_overview.png)

---

## Available Cards

| Card | Custom element | What it shows |
| --- | --- | --- |
| [F1 Live Session](#f1-live-session-card) | `custom:f1-live-session-card` | Session status, track condition, weather, and lap counter |
| [F1 Next Race](#f1-next-race-card) | `custom:f1-next-race-card` | Next race countdown, schedule, circuit map, weather, and track time |
| [F1 Season Calendar](#f1-season-calendar-card) | `custom:f1-season-calendar-card` | Season schedule with past and upcoming races |
| [F1 Race Control](#f1-race-control-card) | `custom:f1-race-control-card` | Race Control messages and flags |
| [F1 FIA Documents](#f1-fia-documents-card) | `custom:f1-fia-documents-card` | FIA documents and decision PDFs for the current weekend |
| [F1 Qualifying Timing](#f1-qualifying-timing-card) | `custom:f1-qualifying-timing-card` | Qualifying order, sector timing, and Q1/Q2/Q3 data |
| [F1 Practice Timing](#f1-practice-timing-card) | `custom:f1-practice-timing-card` | Practice order, tyre age, lap times, and timing indicators |
| [F1 Race Lap](#f1-race-lap-card) | `custom:f1-race-lap-card` | Race or sprint order with gaps, tyres, pit stops, and lap times |
| [F1 Starting Grid](#f1-starting-grid-card) | `custom:f1-starting-grid-card` | Provisional or confirmed Sprint and Race starting grid |
| [F1 Last Race Results](#f1-last-race-results-card) | `custom:f1-last-race-results-card` | Race and sprint classifications with grid, delta, points, and status |
| [F1 Lap Position Progression](#f1-lap-position-progression-card) | `custom:f1-lap-position-progression-card` | Post-race lap-by-lap position chart for completed main races |
| [F1 Tyre Statistics](#f1-tyre-statistics-card) | `custom:f1-sensor-live-data-card` | Tyre compounds, stint history, and best lap times per driver |
| [F1 Pit Stop Overview](#f1-pit-stop-overview-card) | `custom:f1-pitstop-overview-card` | Pit stop timeline with tyre changes and pit times |
| [F1 Driver Lap Times](#f1-driver-lap-times-card) | `custom:f1-driver-lap-times-card` | Live lap times, gaps, positions, and optional lap history |
| [F1 Investigations](#f1-investigations-card) | `custom:f1-investigations-card` | Steward investigations and penalties |
| [F1 Track Limits](#f1-track-limits-card) | `custom:f1-track-limits-card` | Track limit deletions, warnings, and penalties per driver |
| [F1 Championship Prediction Drivers](#f1-championship-prediction-drivers-card) | `custom:f1-championship-prediction-drivers-card` | Driver standings with predicted points |
| [F1 Championship Prediction Teams](#f1-championship-prediction-teams-card) | `custom:f1-championship-prediction-teams-card` | Constructor standings with predicted points |
| [F1 Season Progression](#f1-season-progression-card) | `custom:f1-season-progression-card` | Driver and constructor championship point progression across race rounds |
| [F1 Replay Control](#f1-replay-control-card) | `custom:f1-replay-control-card` | Replay Mode selectors, playback controls, drag-to-seek playbar, and progress |
| [F1 Track Map](#f1-track-map-card) | `custom:f1-track-map-card` | Live and replay circuit map with car positions |

---

## Installation

### Bundled installation

Install or update [F1 Sensor](/getting-started/installation), then restart Home Assistant. The integration copies the bundled card assets to Home Assistant and registers the Lovelace resource as a JavaScript module.

You do not need to add `f1-sensor-live-data-card` as a separate HACS dashboard repository for the bundled cards.

:::tip
If you updated from the old standalone card, restart Home Assistant and reload your browser so the dashboard loads the latest bundled card assets.
:::

### Migrating from the old standalone card

Existing dashboard card types do not change. Keep using the same `custom:f1-...` card types in your dashboards.

After you confirm the bundled card loads correctly, you can remove the old standalone HACS dashboard repository:

1. Open **HACS** in Home Assistant.
2. Find **F1 Sensor Live Data Card** in the dashboard or frontend section.
3. Remove the standalone card repository.
4. Restart Home Assistant.
5. Reload your browser or clear the Home Assistant frontend cache.

If you previously added a manual dashboard resource, open **Settings > Dashboards**, open the three-dot menu, select **Resources**, and remove old standalone entries such as `/local/f1-sensor-live-data-card.js` or `/hacsfiles/f1-sensor-live-data-card/...`.

:::info[Automatic resource registration]
F1 Sensor manages the bundled resource at `/local/f1-sensor-live-data-card/f1-sensor-live-data-card.js?v=...` with type **JavaScript Module**. If your installation had one old resource entry, F1 Sensor updates it. If it had multiple old entries, remove the extra stale entries manually after confirming the bundled card works.
:::

:::warning[Stale resource repair]
Home Assistant Repairs may show **Old standalone F1 live data card resources detected** when old standalone resource URLs are still configured. Confirm the bundled cards work first, then remove the old standalone HACS dashboard repository and stale dashboard resources. Restart Home Assistant or reload Lovelace resources, then hard refresh the browser if the old card UI remains.
:::

<details>
<summary>Manual fallback</summary>

Use this only if automatic resource registration is unavailable in your Home Assistant setup.

1. Copy the files from `custom_components/f1_sensor/www/f1-sensor-live-data-card/` to `config/www/f1-sensor-live-data-card/`.
2. Register the resource in Home Assistant.

**Via the UI**: Go to **Settings > Dashboards**, open the three-dot menu, select **Resources**, then **Add Resource**. Set the URL to `/local/f1-sensor-live-data-card/f1-sensor-live-data-card.js` and the type to **JavaScript Module**.

**Via YAML**:

```yaml
lovelace:
  resources:
    - url: /local/f1-sensor-live-data-card/f1-sensor-live-data-card.js
      type: module
```

</details>

---

## Adding Cards

1. Open your dashboard and select **Edit Dashboard**.
2. Select **Add card**.
3. Search for **F1**.
4. Select a card and configure it in the visual editor.

Each card has a visual editor with **Data Sources** for entity selection and **Display Options** for columns, theme, labels, logos, and layout.

:::info[Entity IDs]
The defaults use the standard F1 Sensor entity IDs, such as `sensor.f1_driver_positions`. Older installations may have existing registry IDs from earlier releases. Select the correct entities in the visual editor if your IDs differ.
:::

---

## Shared Options

Many cards expose the same display options.

| Option | Values | Description |
| --- | --- | --- |
| `theme_mode` | `dark`, `light`, `auto` | Visual theme. `dark` keeps the original F1 card look, `light` uses a light palette, and `auto` follows the Home Assistant theme. |
| `show_header` | `true`, `false` | Show the card title/header area. |
| `show_table_header` | `true`, `false` | Show column labels above table-style cards. |
| `show_full_name` | `true`, `false` | Show full driver names instead of TLA codes where supported. |
| `show_team_logo` | `true`, `false` | Show team logos where supported. |
| `team_logo_style` | `color`, `white` | Use colored team logos or white logos. |
| `auth_status_entity` | entity ID | Optional F1TV token status entity used by cards that display F1TV Auth enhanced data. |
| `show_availability_notice` | `true`, `false` | Show a notice when a card depends on data that is unavailable, replay-only, or requires F1TV Auth live. |

---

## Card Reference

### F1 Live Session Card

`custom:f1-live-session-card`

Displays an at-a-glance overview of the current session, including session name, session status, track condition, weather, lap progress, and optional session clocks.

![Placeholder - F1 Live Session card screenshot](/img/placeholder_card_live_session.png)

**Required entities:** `sensor.f1_current_session`, `sensor.f1_session_status`, `sensor.f1_race_lap_count`, `sensor.f1_track_status`, `sensor.f1_track_weather`, `sensor.f1_next_race`

**Optional entities:** `binary_sensor.f1_formation_start`, `sensor.f1_session_time_elapsed`, `sensor.f1_session_time_remaining`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `show_flag` | `true` | Show the track status flag indicator |
| `show_lap_progress` | `true` | Show the lap progress bar |
| `show_track_status` | `true` | Show the current track status label |
| `show_weather` | `true` | Show live track weather |
| `show_time_remaining` | `false` | Show session time remaining when available |
| `show_time_elapsed` | `false` | Show session time elapsed when available |

---

### F1 Next Race Card

`custom:f1-next-race-card`

Shows the next race, countdown, weekend schedule, circuit map, track time, weather, and optional historical context. It can prefer live track weather during an active session and fall back to the normal next-race weather forecast.

![Placeholder - F1 Next Race card screenshot](/img/placeholder_card_next_race.png)

**Required entity:** `sensor.f1_next_race`

**Optional entities:** `sensor.f1_weather`, `sensor.f1_track_weather`, `sensor.f1_current_session`, `sensor.f1_session_status`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `show_header` | `true` | Show the card header |
| `show_countdown` | `true` | Show countdown to the race |
| `show_overview` | `true` | Show the main race overview |
| `show_schedule` | `true` | Show session schedule |
| `show_track_time` | `true` | Show local circuit time |
| `show_map` | `true` | Show circuit image when available |
| `show_weather` | `true` | Show weather information |
| `show_history` | `true` | Show race history when available |
| `prefer_live_weather` | `true` | Prefer `sensor.f1_track_weather` during live sessions |

---

### F1 Season Calendar Card

`custom:f1-season-calendar-card`

Displays the current season schedule as a compact race list. Past races can be dimmed or hidden, and the next race can be highlighted.

![Placeholder - F1 Season Calendar card screenshot](/img/placeholder_card_season_calendar.png)

**Required entity:** `sensor.f1_current_season`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `show_header` | `true` | Show the card header |
| `show_round` | `true` | Show round number |
| `show_country_flag` | `true` | Show country flag |
| `show_circuit_name` | `false` | Show circuit name |
| `show_location` | `false` | Show locality and country |
| `highlight_next_race` | `true` | Highlight the next race |
| `dim_past_races` | `true` | Visually dim completed races |
| `hide_past_races` | `false` | Hide completed races |

---

### F1 Race Control Card

`custom:f1-race-control-card`

Shows Race Control messages with category, flag state, and optional FIA branding. It can display only the latest message or a scrollable message list.

![Placeholder - F1 Race Control card screenshot](/img/placeholder_card_race_control.png)

**Required entity:** `sensor.f1_race_control`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `display_mode` | `latest` | Use `latest` for a compact card or `list` for a feed view |
| `show_fia_logo` | `true` | Show the FIA logo in the header |
| `hide_blue_flags` | `false` | Hide blue flag messages |
| `min_display_time` | `0` | Minimum time in milliseconds before rotating to a newer message |
| `list_max_height` | `600` | Maximum list height in pixels when using list mode |
| `show_clear_button` | `true` | Show the clear button in list mode |

---

### F1 FIA Documents Card

`custom:f1-fia-documents-card`

Lists FIA decision documents and official PDFs for the current race weekend. It can show the latest document only or a full document list with race context.

![Placeholder - F1 FIA Documents card screenshot](/img/placeholder_card_fia_documents.png)

**Required entity:** `sensor.f1_fia_documents`

**Optional entity:** `sensor.f1_last_race_results`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `display_mode` | `list` | Use `list` or `latest` |
| `sort_order` | `newest` | Sort documents newest first |
| `show_header` | `true` | Show the card header |
| `show_fia_logo` | `true` | Show FIA branding |
| `show_race_context` | `true` | Show race/weekend context |
| `show_count` | `true` | Show document count |
| `show_pdf_icon` | `true` | Show PDF icon |
| `show_document_number` | `true` | Show document number |
| `show_document_type` | `true` | Show document type styling |
| `show_document_coloring` | `true` | Use document category coloring |
| `show_published` | `true` | Show published time |
| `show_latest_badge` | `true` | Mark the latest document |
| `visible_rows` | `8` | Number of rows to show before scrolling |
| `list_max_height` | `0` | Optional fixed list height in pixels. `0` lets the card size itself. |
| `open_in_new_tab` | `true` | Open PDFs in a new browser tab |

---

### F1 Qualifying Timing Card

`custom:f1-qualifying-timing-card`

Shows qualifying performance in a table: position, driver, live sectors, last lap, segment bests, and optional timing color indicators. Drivers eliminated from a segment are visually dimmed.

:::info[Session availability]
This card is designed for Qualifying and Sprint Qualifying. Outside those sessions it shows an unavailable message instead of stale timing.
:::

![Placeholder - F1 Qualifying Timing card screenshot](/img/placeholder_card_qualifying_timing.png)

**Required entity:** `sensor.f1_driver_positions`

**Optional entities:** `sensor.f1_current_tyres`, `sensor.f1_driver_list`, `sensor.f1_current_session`, `sensor.f1_session_status`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `title` | `Qualifying` | Card title |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels |
| `show_team_logo` | `true` | Show team logo |
| `show_full_name` | `false` | Show full driver names |
| `show_delta` | `true` | Show timing delta when available |
| `show_timing_indicators` | `false` | Highlight overall fastest, personal fastest, and timed sector states |
| `sector_display_mode` | `current` | Sector display mode used by the visual editor |
| `team_logo_style` | `color` | Logo appearance |
| `color_overall_fastest` | card default | Color for overall fastest timing cells |
| `color_personal_fastest` | card default | Color for personal best timing cells |
| `color_timed` | card default | Color for normally timed cells |

---

### F1 Practice Timing Card

`custom:f1-practice-timing-card`

Shows practice order with driver status, tyres, tyre age, last lap, fastest lap, and optional timing indicators.

![Placeholder - F1 Practice Timing card screenshot](/img/placeholder_card_practice_timing.png)

**Required entity:** `sensor.f1_driver_positions`

**Optional entities:** `sensor.f1_current_session`, `sensor.f1_session_status`, `sensor.f1_driver_list`, `sensor.f1_current_tyres`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `title` | `Free Practice` | Card title |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels |
| `show_position` | `true` | Show current position |
| `show_team_logo` | `true` | Show team logo |
| `show_full_name` | `false` | Show full driver names |
| `show_status` | `true` | Show driver status |
| `show_tyre` | `true` | Show tyre compound |
| `show_tyre_age` | `true` | Show tyre stint age |
| `show_last_lap` | `true` | Show last lap |
| `show_fastest_lap` | `true` | Show personal fastest lap |
| `show_timing_indicators` | `false` | Highlight timing states |
| `team_logo_style` | `color` | Logo appearance |

---

### F1 Race Lap Card

`custom:f1-race-lap-card`

Displays race or sprint order with driver gaps, tyre compound, tyre age, pit count, last lap, and personal fastest lap. Gap mode can show the gap to the leader or interval to the car ahead.

:::info[Session availability]
This card is designed for Race and Sprint sessions. Some columns depend on data that is only available during live or authenticated/replay timing.
:::

![Placeholder - F1 Race Lap card screenshot](/img/placeholder_card_race_lap.png)

**Required entities:** `sensor.f1_driver_positions`, `sensor.f1_current_session`

**Optional entities:** `sensor.f1_race_lap_count`, `sensor.f1_session_status`, `sensor.f1_driver_list`, `sensor.f1_current_tyres`, `sensor.f1_pitstops`, `sensor.f1_f1tv_token_status`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `title` | `Race Lap` | Card title |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels |
| `show_position` | `true` | Show current position |
| `show_team_logo` | `true` | Show team logo |
| `show_full_name` | `false` | Show full driver names |
| `show_status` | `true` | Show inline driver status |
| `show_gap` | `true` | Show gap or interval |
| `gap_mode` | `ahead` | Gap mode. `ahead` shows interval to the car ahead; use the editor to switch mode where available. |
| `show_gap_toggle` | `true` | Show the gap mode toggle |
| `show_tyre` | `true` | Show tyre compound |
| `show_tyre_age` | `true` | Show tyre stint age |
| `show_pit_count` | `true` | Show number of pit stops |
| `show_last_lap` | `true` | Show last lap time |
| `show_fastest_lap` | `true` | Show personal fastest lap |
| `show_timing_indicators` | `false` | Highlight timing states |
| `team_logo_style` | `color` | Logo appearance |
| `show_availability_notice` | `true` | Show notices for unavailable F1TV Auth enhanced data |

---

### F1 Starting Grid Card

`custom:f1-starting-grid-card`

Shows the currently relevant starting grid for the weekend. Sprint weekends use Sprint Qualifying for the Sprint grid and Qualifying for the Race grid. Normal weekends use Qualifying for the Race grid.

![Placeholder - F1 Starting Grid card screenshot](/img/placeholder_card_starting_grid.png)

**Required entity:** `sensor.f1_starting_grid`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `title` | `Starting Grid` | Card title |
| `display_mode` | `grid` | Use `grid` or `table` layout |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels in table mode |
| `show_team_logo` | `true` | Show team logo |
| `show_full_name` | `false` | Show full driver names |
| `show_qualifying_position` | `true` | Show original qualifying position |
| `show_qualifying_time` | `true` | Show qualifying lap time |
| `show_qualifying_delta` | `false` | Show delta to the reference qualifying time |
| `show_qualifying_segment` | `true` | Show Q/SQ segment |
| `show_grid_delta` | `true` | Show movement from qualifying position to grid position |
| `show_status_badge` | `true` | Show provisional/confirmed status |
| `show_source_badge` | `true` | Show data source badge |
| `show_metadata` | `true` | Show source session and target session metadata |
| `team_logo_style` | `color` | Logo appearance |

---

### F1 Last Race Results Card

`custom:f1-last-race-results-card`

Shows the latest race result, season race results, or sprint results with a session selector. It supports grid position, position delta, points, status, team logos, and No Spoiler Mode.

![Placeholder - F1 Last Race Results card screenshot](/img/placeholder_card_last_race_results.png)

**Required entity:** `sensor.f1_last_race_results`

**Optional entities:** `sensor.f1_season_results`, `sensor.f1_sprint_results`, `sensor.f1_driver_list`, `switch.f1_no_spoiler_mode`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `show_header` | `true` | Show the card header |
| `show_session_selector` | `true` | Allow switching between race and sprint classifications |
| `show_session_type_badge` | `true` | Show session type badge |
| `show_table_header` | `true` | Show column labels |
| `show_position` | `true` | Show final position |
| `show_grid` | `true` | Show starting grid position |
| `show_tla` | `true` | Show driver TLA |
| `show_full_name` | `false` | Show full driver names |
| `show_team_logo` | `true` | Show team logo |
| `driver_image_type` | `team_logo` | Driver image source used by the card |
| `team_logo_style` | `color` | Logo appearance |
| `show_delta` | `true` | Show movement from grid to finish |
| `show_points` | `true` | Show awarded points |
| `show_status` | `true` | Show finish status |
| `top_limit` | `0` | Limit rows to top N. `0` shows all |

---

### F1 Lap Position Progression Card

`custom:f1-lap-position-progression-card`

Displays a native SVG post-race lap position chart for completed main races. The card reads lightweight session metadata from `sensor.f1_lap_position_progression`, then asks the F1 Sensor backend for the selected race through Home Assistant's WebSocket API. This keeps full lap-by-lap position arrays out of entity state attributes.

![Placeholder - F1 Lap Position Progression card screenshot](/img/placeholder_card_race_lap.png)

**Required entity:** `sensor.f1_lap_position_progression`

**Optional entities:** `sensor.f1_driver_list`, `switch.f1_no_spoiler_mode`

**Example:**

```yaml
type: custom:f1-lap-position-progression-card
entity: sensor.f1_lap_position_progression
drivers_entity: sensor.f1_driver_list
no_spoiler_entity: switch.f1_no_spoiler_mode
title: Lap Position Progression
theme_mode: auto
top_limit: 10
```

| Option | Default | Description |
| --- | --- | --- |
| `entity` | `sensor.f1_lap_position_progression` | Sensor that provides race and sprint session metadata |
| `drivers_entity` | `sensor.f1_driver_list` | Driver list sensor used for team metadata and logos |
| `no_spoiler_entity` | `switch.f1_no_spoiler_mode` | No Spoiler Mode switch used by the overlay behavior |
| `theme_mode` | `auto` | Card theme. Use `dark`, `light`, or `auto` |
| `title` | `Lap Position Progression` | Card title |
| `show_header` | `true` | Show the card header |
| `show_session_selector` | `true` | Allow switching between race and sprint entries |
| `show_full_name` | `false` | Show full driver names instead of compact labels |
| `team_logo_style` | `color` | Logo appearance |
| `show_points` | `true` | Show point markers on the chart |
| `show_round_labels` | `true` | Show lap labels on the x-axis |
| `top_limit` | `0` | Limit visible entries by final position. `0` shows all drivers |
| `chart_height` | `420` | Chart height in pixels |

The chart places P1 at the top and lap number on the x-axis. Driver labels on the left show the starting order, while the right side shows the current final order for completed races. Select a driver label on either side to hide or show that driver's progression line. Drivers that have classification metadata but no lap timing rows are still listed in the side labels, but they do not draw a progression line. Hover or focus a chart point to see driver, lap, position, race name, and grid-to-finish context when available. Jolpica data is loaded for one selected race at a time and reused from the integration cache where possible.

:::info[Sprint limitation]
Sprint sessions can appear in the selector so the season context is complete, but Jolpica currently exposes sprint classification results rather than sprint lap-by-lap positions. Those sprint entries render an unsupported state instead of a chart.
:::

When No Spoiler Mode is enabled, the card uses the same overlay behavior as other bundled spoiler-sensitive cards and does not reveal newly fetched post-race position data until spoilers are allowed.

---

### F1 Tyre Statistics Card

`custom:f1-sensor-live-data-card`

Displays the current tyre compound for each driver, stint history, compound statistics, and best lap times per compound.

![Placeholder - F1 Tyre Statistics card screenshot](/img/placeholder_card_tyres.png)

**Required entities:** `sensor.f1_tyre_statistics`, `sensor.f1_driver_list`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `title` | `Tyres Statistics` | Card title |
| `show_header` | `true` | Show the card header |
| `show_best_times` | `true` | Show best lap times per compound |
| `show_stats` | `true` | Show compound usage statistics |
| `show_delta` | `true` | Show delta values |
| `show_tyre_image` | `true` | Show tyre compound images |
| `show_compound_name` | `true` | Show compound name |
| `show_full_name` | `false` | Show full driver names |
| `show_team_logo` | `false` | Show team logo |
| `team_logo_style` | `color` | Logo appearance |
| `max_best_times` | `3` | Maximum number of best times to show |

---

### F1 Pit Stop Overview Card

`custom:f1-pitstop-overview-card`

Shows pit stop history for all drivers: stop count, tyre fitted, tyre age, pit time, pit lane time, and delta to fastest stop.

![Placeholder - F1 Pit Stop Overview card screenshot](/img/placeholder_card_pitstops.png)

**Required entities:** `sensor.f1_pitstops`, `sensor.f1_current_tyres`, `sensor.f1_driver_positions`, `sensor.f1_driver_list`

**Optional entity:** `sensor.f1_f1tv_token_status`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `title` | `Pit Stops & Tyres` | Card title |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels |
| `show_tla` | `true` | Show driver TLA |
| `show_full_name` | `false` | Show full driver names |
| `show_team_logo` | `false` | Show team logo |
| `team_logo_style` | `color` | Logo appearance |
| `show_status` | `true` | Show pit stop status |
| `show_tyre` | `true` | Show tyre compound |
| `show_tyre_laps` | `false` | Show laps completed on the current tyre |
| `show_pit_count` | `true` | Show number of stops |
| `show_pit_time` | `true` | Show pit stop duration |
| `show_pit_lane_time` | `true` | Show total pit lane time |
| `show_pit_delta` | `true` | Show delta to fastest stop |
| `show_availability_notice` | `true` | Show notices for unavailable F1TV Auth enhanced data |

---

### F1 Driver Lap Times Card

`custom:f1-driver-lap-times-card`

Displays live lap timing, driver positions, gap/interval data, personal best laps, status, and optional lap history with trend indicators.

![Placeholder - F1 Driver Lap Times card screenshot](/img/placeholder_card_lap_times.png)

**Required entities:** `sensor.f1_driver_positions`, `sensor.f1_driver_list`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `title` | `Driver Lap Times` | Card title |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels |
| `show_position` | `true` | Show current position |
| `show_team_logo` | `true` | Show team logo |
| `show_tla` | `true` | Show driver TLA |
| `show_full_name` | `false` | Show full driver names |
| `show_status` | `true` | Show driver status |
| `show_gap` | `true` | Show gap or interval |
| `gap_mode` | `ahead` | Gap mode. `ahead` shows interval to the car ahead. |
| `show_gap_toggle` | `true` | Show the gap mode toggle |
| `show_last_lap` | `true` | Show last lap time |
| `show_best_lap` | `true` | Show personal best lap time |
| `show_lap_history` | `false` | Show lap-by-lap history columns |
| `lap_history_limit` | `0` | Number of recent lap columns. `0` shows all laps. |
| `show_lap_trend` | `true` | Show faster/slower trend indicators |
| `team_logo_style` | `color` | Logo appearance |

---

### F1 Investigations Card

`custom:f1-investigations-card`

Lists steward investigations and penalties for the current session. It can show only affected drivers or all drivers.

![Placeholder - F1 Investigations card screenshot](/img/placeholder_card_investigations.png)

**Required entities:** `sensor.f1_investigations`, `sensor.f1_driver_list`, `sensor.f1_driver_positions`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `title` | `Investigations & Penalties` | Card title |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels |
| `show_team_logo` | `false` | Show team logo |
| `show_full_name` | `false` | Show full driver names |
| `team_logo_style` | `color` | Logo appearance |
| `show_all_drivers` | `false` | Show all drivers, not only affected drivers |

---

### F1 Track Limits Card

`custom:f1-track-limits-card`

Shows track limit violations per driver, including deleted lap times, black and white flag warnings, and penalties.

![Placeholder - F1 Track Limits card screenshot](/img/placeholder_card_track_limits.png)

**Required entities:** `sensor.f1_track_limits`, `sensor.f1_driver_list`, `sensor.f1_driver_positions`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `title` | `Track Limits` | Card title |
| `show_header` | `true` | Show the card header |
| `show_table_header` | `true` | Show column labels |
| `show_team_logo` | `false` | Show team logo |
| `show_full_name` | `false` | Show full driver names |
| `team_logo_style` | `color` | Logo appearance |
| `show_all_drivers` | `false` | Show all drivers, not only drivers with violations |

---

### F1 Championship Prediction Drivers Card

`custom:f1-championship-prediction-drivers-card`

Displays current driver standings beside predicted final standings, predicted points, current points, and delta.

![Placeholder - F1 Championship Prediction Drivers card screenshot](/img/placeholder_card_prediction_drivers.png)

**Required entities:** `sensor.f1_driver_standings`, `sensor.f1_championship_prediction_drivers`, `sensor.f1_driver_list`

**Optional entities:** `sensor.f1_current_session`, `sensor.f1_session_status`, `switch.f1_no_spoiler_mode`, `sensor.f1_f1tv_token_status`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `title` | `Driver Championship` | Card title |
| `show_header` | `true` | Show the card header |
| `show_mode_badge` | `true` | Show live/replay/no-spoiler mode badge |
| `show_table_header` | `true` | Show column labels |
| `show_position` | `true` | Show championship position |
| `show_tla` | `true` | Show driver TLA |
| `show_full_name` | `false` | Show full driver names |
| `show_team_logo` | `true` | Show team logo |
| `driver_image_type` | `team_logo` | Driver image source used by the card |
| `team_logo_style` | `color` | Logo appearance |
| `show_predicted_points` | `true` | Show predicted final points |
| `show_current_points` | `true` | Show current points |
| `show_delta` | `true` | Show predicted points delta |
| `show_availability_notice` | `true` | Show notices for unavailable F1TV Auth enhanced data |
| `top_limit` | `0` | Limit rows to top N. `0` shows all. |

---

### F1 Championship Prediction Teams Card

`custom:f1-championship-prediction-teams-card`

Displays current constructor standings beside predicted final standings, predicted points, current points, and delta.

![Placeholder - F1 Championship Prediction Teams card screenshot](/img/placeholder_card_prediction_teams.png)

**Required entities:** `sensor.f1_constructor_standings`, `sensor.f1_championship_prediction_teams`

**Optional entities:** `sensor.f1_current_session`, `sensor.f1_session_status`, `switch.f1_no_spoiler_mode`, `sensor.f1_f1tv_token_status`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `title` | `Constructor Championship` | Card title |
| `show_header` | `true` | Show the card header |
| `show_mode_badge` | `true` | Show live/replay/no-spoiler mode badge |
| `show_table_header` | `true` | Show column labels |
| `show_position` | `true` | Show championship position |
| `show_team_name` | `true` | Show team name |
| `show_team_logo` | `true` | Show team logo |
| `team_logo_style` | `color` | Logo appearance |
| `show_predicted_points` | `true` | Show predicted final points |
| `show_current_points` | `true` | Show current points |
| `show_delta` | `true` | Show predicted points delta |
| `show_availability_notice` | `true` | Show notices for unavailable F1TV Auth enhanced data |
| `top_limit` | `0` | Limit rows to top N. `0` shows all. |

---

### F1 Season Progression Card

`custom:f1-season-progression-card`

Displays driver or constructor championship point progression as a native bundled chart. Add one card with `mode: drivers` for the Drivers' Championship and another card with `mode: constructors` for the Constructors' Championship.

**Required entity:** `sensor.f1_driver_points_progression` or `sensor.f1_constructor_points_progression`

**Optional entities:** `sensor.f1_current_season`, `sensor.f1_driver_list`

**Driver progression example:**

```yaml
type: custom:f1-season-progression-card
mode: drivers
entity: sensor.f1_driver_points_progression
calendar_entity: sensor.f1_current_season
driver_list_entity: sensor.f1_driver_list
title: Season progression - drivers points
theme_mode: auto
legend_position: bottom
show_future_rounds: true
```

**Constructor progression example:**

```yaml
type: custom:f1-season-progression-card
mode: constructors
entity: sensor.f1_constructor_points_progression
calendar_entity: sensor.f1_current_season
title: Season progression - constructors points
theme_mode: auto
legend_position: bottom
show_future_rounds: true
```

| Option | Default | Description |
| --- | --- | --- |
| `mode` | `drivers` | Use `drivers` or `constructors` |
| `entity` | Mode-specific | Progression sensor used by the chart |
| `calendar_entity` | `sensor.f1_current_season` | Season calendar sensor used to show future rounds on the x-axis |
| `driver_list_entity` | `sensor.f1_driver_list` | Driver list sensor used for tooltip headshots in driver mode |
| `theme_mode` | `auto` | Card theme. Use `dark`, `light`, or `auto` |
| `title` | Mode-specific | Card title |
| `show_header` | `true` | Show the card header |
| `show_legend` | `true` | Show the legend |
| `legend_position` | `bottom` | Place the legend at `bottom`, `left`, or `right` |
| `show_legend_points` | `true` | Show latest points in the legend |
| `show_full_name` | `false` | Show full names instead of compact labels |
| `show_points` | `true` | Show point markers on the chart |
| `show_round_labels` | `true` | Show round labels on the x-axis |
| `show_future_rounds` | `true` | Keep future calendar rounds visible before points are available |
| `top_limit` | `0` | Limit visible entries to the top N. `0` shows all |
| `chart_height` | `320` | Chart height in pixels |

The legend is interactive. Select a driver or team in the legend to hide or show that line. Hover or focus a chart point to see the round, race name, points, and available driver or team image.

---

### F1 Replay Control Card

`custom:f1-replay-control-card`

Provides a purpose-built Replay Mode dashboard control. It combines season and session selectors, start reference selection, load/play/pause/stop controls, a drag-to-seek playbar, 30-second seek buttons, refresh, status details, and progress.

The playbar appears when the replay media player supports seek. Drag the handle to preview a new position, then release it to send one `media_player.media_seek` command. The card does not send seek commands continuously while you drag.

![Placeholder - F1 Replay Control card screenshot](/img/placeholder_card_replay_control.png)

**Required entities:** `sensor.f1_replay_status`, `select.f1_replay_year`, `select.f1_replay_session`, `button.f1_replay_load`, `button.f1_replay_play`, `button.f1_replay_pause`, `button.f1_replay_stop`, `media_player.f1_replay_player`

**Optional entities:** `select.f1_replay_start_reference`, `button.f1_replay_back_30`, `button.f1_replay_forward_30`, `button.f1_replay_refresh`

| Option | Default | Description |
| --- | --- | --- |
| `theme_mode` | `dark` | Card theme |
| `title` | `Replay Control` | Card title |
| `display_mode` | `full` | Use `full` or `compact` layout |
| `show_title` | `true` | Show card title |
| `show_status_details` | `true` | Show replay status metadata |
| `show_secondary_selects` | `true` | Show secondary selectors |
| `show_start_reference` | `true` | Show start reference selector |
| `show_seek_controls` | `true` | Show back/forward 30-second controls |
| `show_refresh` | `true` | Show refresh control |
| `show_progress` | `true` | Show playback progress and the seek playbar when supported |
| `show_button_labels` | `true` | Show text labels on playback buttons |

---

### F1 Track Map Card

`custom:f1-track-map-card`

Shows a circuit map with driver markers, optional lap progress, and track status context. Live Track Map requires optional [F1TV Auth](/features/f1tv-auth) because public live timing does not include the needed car position data. Replay Track Map is best effort and works when the replay archive contains that data.

:::info[Availability]
The card needs the F1 Sensor integration, an active live or replay session, and usable Track Map data. During live sessions, car positions require F1TV Auth. During Replay Mode, car positions require archived position data for the loaded session.
:::

**Required setup:** F1 Sensor integration with live data or Replay Mode enabled

**Optional context entities:** `sensor.f1_race_lap_count`, `sensor.f1_track_status`

```yaml
type: custom:f1-track-map-card
title: F1 Track Map
entry_id: auto
lap_count_entity: auto
track_status_entity: auto
```

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

For status messages and troubleshooting, see [Track Map](/features/track-map).

---

## Related

- [Live Data entities](/entities/live-data)
- [Static Data entities](/entities/static-data)
- [Replay Mode](/features/replay-mode)
- [F1TV Auth](/features/f1tv-auth)
- [Track Map](/features/track-map)
- [Live Delay](/features/live-delay)
