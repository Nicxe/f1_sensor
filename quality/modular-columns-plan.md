# Modular card column layout

## Agreed behavior

Add a third layout, Columns, to the existing card. The card supports a maximum
of two, three or four equal columns. Each module spans one to four columns or
the full card width. A three-column card therefore supports a two-column Timing
module beside a one-column Track Map, followed by full-width Race Control.

Home Assistant owns the outer layout: widen the containing section and enable
Full width card in HA's Layout tab. The card owns only its internal module grid.
Do not change saved dashboard layouts or depend on HA's private DOM.

## Implementation

1. Extend configuration with `layout: columns`, `columns: 2..4` (default 2),
   and per-module `column_span: 1..4 | full` (default 1). Preserve values when
   switching layouts, reordering, duplicating, undoing and importing/exporting.
   Keep version 3: these are additive options; older cards explicitly reject
   the new layout value instead of silently displaying it incorrectly.
2. Use a named CSS container and normal row-first CSS Grid placement. Respect
   source order; do not backfill gaps by moving later modules ahead of earlier
   ones. Clamp spans to available columns; full always fills a row. At narrow
   widths use one column. Remove hidden modules from placement as before.
3. Add English/Swedish visual editor controls and width labels on module rows.
   Explain the distinction between HA section width and internal columns, and
   offer a preview wide enough to inspect four columns.
4. Retain the existing measured height contract for Sections and Masonry.
   Author runtime changes in HAdev's primary www directory and synchronize all
   three copies immediately after each completed edit.

## Verification

- Configuration validation and round trips, including HA grid_options.
- Browser geometry: 2, 3 and 4 columns; 2+1; full width; wrap without reordering;
  oversized spans; container-only resize and mobile reflow; hidden modules;
  switching layouts; editor persistence, keyboard controls and accessibility.
- Sections height regression after responsive reflow.
- Full frontend unit/browser suites; focused Firefox/WebKit regressions;
  required Ruff and full HA integration suite; documentation and packaging.
- Inspect the real HAdev editor and wide/narrow rendered cards. Do not save
  temporary dashboard configuration. Record results in the development log.

## References

- https://developers.home-assistant.io/docs/frontend/custom-ui/custom-card/
- https://www.home-assistant.io/dashboards/cards/#resizing-a-card
- https://www.home-assistant.io/blog/2024/09/04/release-20249/#wider-sections

The official custom-card sizing and Sections documentation was consulted using
Context7 in this task before implementation.

## Outcome — 2026-09-19

Implemented and verified locally. The real HAdev visual editor measured Timing
at 663.33 px beside a 318.66 px Track map in its 1050 px demo preview, with a
1007.98 px full-width Race Control row below both. At 360 px, all three modules
stacked at 318 px content width while retaining their saved spans. The temporary
card was cancelled without saving dashboard configuration. Console warnings and
errors were empty. Physical-device follow-up is in the manual handover.

Validation details and final counts are recorded in `modular-card-development.md`.
