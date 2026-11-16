# Circuit geometry for the precipitation map

Reviewed 2026-11-10. This dataset is used only by the modular radar view.

`modular/radar-circuits.js` bundles centerlines from
[bacinger/f1-circuits](https://github.com/bacinger/f1-circuits), pinned to
[`8094e957b8d6aa8b9f4510c93968556cccd30e02`](https://github.com/bacinger/f1-circuits/tree/8094e957b8d6aa8b9f4510c93968556cccd30e02).
The upstream MIT copyright and permission notice are included in that runtime
file. No external geometry request is needed while viewing the card.

The source's WGS84 `[longitude, latitude]` coordinates are preserved, including
closed start/end points. Bounds are derived from those coordinates. The radar
view projects both outlines and weather tiles using Web Mercator and centers on
the outline bounds; Jolpica's single location point is a fallback, not a track
survey. These are unofficial community-mapped centerlines, not certified track
limits, lane widths, or survey-grade positioning.

## Calendar mapping

The 2026 calendar supplied 23 circuits when checked. All have bundled geometry.
A circuit newly added to the calendar must use a location marker until its
georeferenced outline is supplied; an arbitrary normalized SVG must not be
positioned on the map as if it contained geographic coordinates.

| Calendar ID | Source feature ID |
| --- | --- |
| albert_park | au-1953 |
| shanghai | cn-2004 |
| suzuka | jp-1962 |
| miami | us-2022 |
| villeneuve | ca-1978 |
| monaco | mc-1929 |
| catalunya | es-1991 |
| red_bull_ring | at-1969 |
| silverstone | gb-1948 |
| spa | be-1925 |
| hungaroring | hu-1986 |
| zandvoort | nl-1948 |
| monza | it-1922 |
| madring | es-2026 |
| baku | az-2016 |
| sepang | my-1999 |
| marina_bay | sg-2008 |
| americas | us-2012 |
| rodriguez | mx-1962 |
| interlagos | br-1940 |
| vegas | us-2023 |
| losail | qa-2004 |
| yas_marina | ae-2009 |

## Layout freshness and uncertainty

- Albert Park's source file was updated on 2023-09-07 and reports 5,278 m,
  consistent with [Formula 1's post-2022 layout](https://www.formula1.com/en/racing/2022/australia).
  The bundled polyline measures approximately 5,273 m geodesically.
- Yas Marina's source file was updated on 2024-01-16 and reports 5,281 m,
  consistent with [Formula 1's revised 2021 layout](https://www.formula1.com/en/racing/2021/united-arab-emirates).
  The bundled polyline measures approximately 5,293 m.
- Madring's source file was last updated on 2025-06-11, before the circuit opened.
  Its metadata reports 5,474 m; [Formula 1's 2026 circuit guide](https://www.formula1.com/en/latest/article/circuit-guide-everything-you-need-to-know-about-the-madring.NF7Mh3iag3w9GUPlihwJA.NF7Mh3iag3w9GUPlihwJA)
  reports 5,414 m. The polyline itself measures about 5,430 m, so the metadata
  difference alone does not establish where the shape differs. It has not been
  independently checked against the final layout and is explicitly marked
  `provisional: true`; the UI must distinguish it with a dashed line and label.

The bundled validation checks all 23 coordinate ranges, closed paths and local
bounds. Five independent circuit-location anchors and plausible lap-length
ranges catch latitude/longitude reversal and gross scale or placement errors.
Those checks do not certify the geographic accuracy of every vertex. A precise
outline also does not increase LibreWXR's weather resolution or update frequency.
