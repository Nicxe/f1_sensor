# Documentation card previews

Run `npm run capture:docs-cards` to recreate the complete `static/img/cards/` set. The script starts a temporary loopback server, closes it on completion and processes assets in batches of at most three. Use `node docs-tests/capture-cards.cjs --only=track-map,race-weather` for a focused refresh.

Five previously missing or incorrect previews are rendered from the integration's actual bundled custom elements with Playwright: Weekend Hub, Race Weather, Season Progression, Lap Position Progression and Track Map. `cards-preview.js` supplies illustrative deterministic entity/WebSocket data; it does not connect to Home Assistant, F1TV, an external timing API or an account. The example values are not real classifications. The sample circuit geometry is intentionally not attributed to a real circuit.

The host supplies the minimal Home Assistant element shell needed by these cards. All card layout, tables, charts, styles and map drawing come from the bundled integration components. Weather icons are official Material Design Icons from Pictogrammers/Templarian, embedded locally so capture needs no remote asset request. Their Apache-2.0 license is in `cards-icons-license.txt`; source: <https://github.com/Templarian/MaterialDesign/tree/master/svg>.

The remaining 18 previews reuse the repository's existing screenshots byte-for-byte. The original `placeholder_` names described their filenames, not empty image content. Keeping them preserves real card examples while the five missing previews gain reproducible captures. These retained screenshots can show an earlier display configuration; they are not regenerated from the illustrative fixture.

| New filename | Provenance |
| --- | --- |
| `weekend-hub.png` | Actual component rendered by `cards-preview.js` |
| `race-weather.png` | Actual component rendered by `cards-preview.js` |
| `season-progression.png` | Actual component rendered by `cards-preview.js` |
| `lap-position-progression.png` | Actual component rendered by `cards-preview.js`; replaces the previously incorrect Race Lap image |
| `track-map.png` | Actual component rendered by `cards-preview.js` |
| `live-session.png` | `static/img/placeholder_card_live_session.png` |
| `next-race.png` | `static/img/placeholder_card_next_race.png` |
| `season-calendar.png` | `static/img/placeholder_card_season_calendar.png` |
| `race-control.png` | `static/img/placeholder_card_race_control.png` |
| `fia-documents.png` | `static/img/placeholder_card_fia_documents.png` |
| `qualifying-timing.png` | `static/img/placeholder_card_qualifying_timing.png` |
| `practice-timing.png` | `static/img/placeholder_card_practice_timing.png` |
| `race-lap.png` | `static/img/placeholder_card_race_lap.png` |
| `starting-grid.png` | `static/img/placeholder_card_starting_grid.png` |
| `results.png` | `static/img/placeholder_card_last_race_results.png` |
| `tyre-statistics.png` | `static/img/placeholder_card_tyres.png` |
| `pit-stops.png` | `static/img/placeholder_card_pitstops.png` |
| `driver-lap-times.png` | `static/img/placeholder_card_lap_times.png` |
| `investigations.png` | `static/img/placeholder_card_investigations.png` |
| `track-limits.png` | `static/img/placeholder_card_track_limits.png` |
| `championship-drivers.png` | `static/img/placeholder_card_prediction_drivers.png` |
| `championship-teams.png` | `static/img/placeholder_card_prediction_teams.png` |
| `replay-control.png` | `static/img/placeholder_card_replay_control.png` |
