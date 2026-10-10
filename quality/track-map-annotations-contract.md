# Track Map annotation contract (issue #787, step 1)

Status: contract and network-free gates defined on 2026-10-09. The geometry-reviewed Singapore 2025 pilot catalog was approved for distribution by the project owner on 2026-10-10. Its start/finish and corner layers now have `rights_status=cleared`; WebSocket v2 and the modular card can show them when the full binding matches. The implementation plan is [the separate step plan](/Users/niklas/GitHub/F1_SENSOR_MODULAR_BANKARTA_ANNOTATIONER_ANALYS_OCH_PLAN_2026-10-09.md).

## Identity and layout resolution

An annotation layer is valid only when **all** of these match the current map generation: `entry_id`, source (`live`/`replay`), `session_key`, `session_generation`, `circuit_key`, season, reviewed `layout_key`, and `geometry_fingerprint`. `session_generation` increases on a session replacement, replay seek, source switch, or reconnect that discards the old map. The existing WebSocket `geometry_revision` is a per-hub sequence counter; it is **not** the stable geometry identity.

The season comes from the first four digits of `SessionInfo.Path`. If `StartDate` is available, its year must agree. A selected replay year must also agree with the path. Active sessions use their own `SessionInfo`, never the next-race sensor or current calendar year. `circuit_key` comes from `SessionInfo.Meeting.Circuit.Key`, must equal the geometry's circuit key, and never resolves from a display name. Missing or conflicting identity yields no annotations.

The v2 map snapshot carries `session.start_date` and the binding carries `session_generation`. The selected replay year is taken from the replay controller and checked against the session path; no inference from the browser's clock is used. V1 remains unchanged.
The `live`/`replay` source is the selected transport mode, not a test for whether any car positions have arrived; static layers may remain available with verified geometry while car positions are missing.

`layout_key` is looked up from an explicit reviewed circuit/season registry. The initial registry distinguishes Singapore 2025 (`marina_bay_post_2023`), Singapore 2022 (`marina_bay_pre_2023`), and Silverstone 2025 (`silverstone_2025`). Only Singapore 2025 is a positive pilot candidate. The older Singapore layout and Silverstone have no annotation catalog entries. Other years, including Singapore 2026, stay unknown until reviewed. A future season cannot inherit 2025 data just because its circuit key is `61`.

`geometry_fingerprint` is `sha256:` plus the SHA-256 of compact JSON `[circuit_key, rotation, points]`. Rotation and every raw X/Y point must match. This binds an anchor to the exact geometry against which it was calibrated, including when the source changes from static catalog to a generated track. The transport puts the fingerprint on the v2 track and annotation binding. The frontend will compare both before drawing in step 4.

With the current static catalog, Singapore `61` yields `sha256:7fcbc8eecbacafcb486b7d899bb360f9d61d5eb3bc139a0fcafea9e3688a513d`. This is a geometry identity only; it does not approve any annotation coordinates.

## Layer record, v1

Each record describes **one layer** for one circuit/layout/geometry combination. This permits partial coverage: verified corners can be shown while sectors remain unavailable. There is at most one approved record per layer and compatible context; duplicates fail closed. The following is an illustrative test shape, not a coordinate for Singapore:

```json
{
  "schema_version": 1,
  "layer": "corners",
  "circuit_key": "61",
  "layout_key": "marina_bay_post_2023",
  "valid_from_season": 2025,
  "valid_to_season": 2025,
  "geometry_fingerprint": "sha256:<64 hexadecimal digits>",
  "qa_status": "verified",
  "rights_status": "cleared",
  "source": {
    "url": "https://example.test/source-map",
    "checked_on": "2026-10-09"
  },
  "items": [
    {
      "id": "turn_1",
      "kind": "point",
      "anchor": [100, 0],
      "label": "1",
      "label_offset": [2, -2]
    }
  ]
}
```

`valid_from_season` and `valid_to_season` are inclusive. The source applies to every item in the record; records with different sources or validity periods must remain separate, and selection of two records for the same layer fails closed until the catalog is reconciled. `qa_status` must be `verified` after source and visual checks, and `rights_status` must be `cleared` after the project distribution decision. Candidate or pending records are unavailable. The source URL must be HTTPS and include a checked date. No source image is delivered to the browser.

Items have unique stable lowercase IDs within a record, a nonempty label of at most 32 characters, and one of these shapes:

| Kind | Required geometry | Intended layers |
| --- | --- | --- |
| `point` | `anchor: [x, y]` in raw Track Map coordinates and `label_offset: [dx, dy]` in projected SVG units, each offset within ±10 | `corners`, `speed_traps`, `detection_zones` |
| `line` | Distinct raw endpoints `start: [x, y]` and `end: [x, y]` | `start_finish`, `sectors` |
| `interval` | `start` and `end` each have `segment_index` and `fraction` (0–1) on the ordered raw geometry; `direction: "forward"`; explicit `wraps_start_finish` | `sectors`, `detection_zones` |

An interval's segment index must exist in the bound geometry. `wraps_start_finish` must agree with the ordered start/end positions. Intervals need verified lap direction; calculated thirds of a lap are not official sector boundaries. A layer with an incomplete item, repeated item ID, more than 64 items, invalid coordinate, or unsupported kind is wholly unavailable. [Pilot QA](track-map-singapore-2025-annotation-qa.md) checks the Singapore start line and turn placements, source provenance, and visual review before marking their geometry QA `verified`; the project owner's distribution approval changed rights to `cleared` on 2026-10-10.

## Wire envelope and absence behavior

The optional `annotations` property in the existing v2 **full map snapshot** is bound to the same track and map generation. It is `null` when no layer passes validation or rights clearance. Geometry/session changes carry a replacement or `null` in the existing v2 patch. Position-only deltas carry no annotation metadata. Older clients may ignore the property. A full snapshot or resync replaces the complete annotation envelope atomically; merging item arrays across generations is prohibited.

The wire envelope retains `schema_version`, the full `binding`, and `layers`. Each transmitted layer has `layer`, `source`, `columns`, and `items`. `columns` lists item field names in order; each row of `items` has values in that order. This compact representation is applied only after validating the full catalog record, including provenance, geometry, QA, and rights. It preserves the item's ID, kind, coordinates, label, and offset while keeping the Singapore pilot below the 2,048-byte snapshot allowance. The approved Singapore 2025 records are available when their full binding matches.

| Situation | Map and cars | Selected annotation layer |
| --- | --- | --- |
| Unknown circuit, season, layout, or mismatched geometry | Keep the current valid base map and cars | Hide that layer; show one compact unavailable status with the reason |
| Missing geometry | Use the existing no-geometry map message; do not infer a layout | Hide all layers |
| Incomplete, unapproved, rights-pending, or duplicate catalog record | Keep valid base content and any other valid layers | Hide the entire affected layer and explain unavailability |
| No usable car positions | Keep verified geometry and static annotations | Show no car markers; the driver list states that positions are unavailable |
| Spoiler protection | Existing spoiler gate hides the entire map module | Do not expose layer names or circuit identity through its status |
| Stale live position or frozen/retained frame | Keep the last frame only under its saved session/layout label | Only retain layers whose binding matches that saved frame; never call them current |
| Transport interruption or v2 sequence gap | Existing reconnect/resync path handles the base map | Hide annotation metadata until a new complete, matching snapshot arrives |
| New entry/session, replay seek, layout switch, or geometry replacement | Replace or clear the previous base frame according to existing map lifecycle | Increment generation, clear old annotations, then bind approved layers to the new complete frame |

The module status is shown only for explicitly selected layers that have no valid data. It is outside the SVG, in accessible text, and does not block the base map. No status is shown for an unselected layer.

## Saved card configuration and field metadata

The stable per-instance field IDs are `map_start_finish`, `map_corners`, `map_sectors`, `map_speed_traps`, and `map_detection_zones`. All are opt-in and will enter the modular field catalog in step 4. They require the `track_map` source, live/replay session identity, matching circuit/layout/geometry, and a verified catalog record. They are spoiler-sensitive, valid for the matched map generation rather than a timed polling interval, and have SVG and text presentations. Static location data never implies a speed measurement. The visible labels and translations will be added with the fields in step 4.

| Field ID | User-visible meaning | Required record / presentation |
| --- | --- | --- |
| `map_start_finish` | Verified start/finish line, distinct from any control line | `start_finish` / line and text; crossing direction checked in step 2 |
| `map_corners` | Numbered turns in the reviewed layout | `corners` / labelled points and ordered text list |
| `map_sectors` | Official sector boundaries, not estimated thirds | `sectors` / lines or directed intervals and text |
| `map_speed_traps` | Location of speed measurement points, not measured speeds | `speed_traps` / points and text |
| `map_detection_zones` | Season-valid detection/activation positions or intervals | `detection_zones` / points or directed intervals and text |

`track_map` keeps its existing meaning: it displays the track and, by default, car markers. A new per-instance boolean `show_car_markers` defaults to `true`; setting it to `false` hides only the SVG car markers. `map_drivers` controls the driver-position list when the map is absent, and when explicitly selected alongside a map with hidden car markers. With the existing default `track_map` and visible cars, the accessible driver list stays as it is today. Selecting an annotation field alone implies showing the base map, but does not turn on car markers. Annotations and car markers are independent of each map instance's other instances, orientation, focus, and visibility conditions. Saved empty or custom field lists remain intact; no overlay is added by migration or preset.

The frontend's field normalizer retains per-module lists and options. A network-free two-module fixture locks distinct selections through a JSON export/import round trip. The new field IDs are registered in the modular catalog and can be selected independently in the visual editor.

## Test boundary

`test_track_map_annotation_contract.py` exercises pilot, wrong circuit, wrong layout year, incomplete/uncleared source, geometry changes, new session/entry, and replay seek with a small synthetic geometry. `test_track_map_annotation_catalog.py` guards the Singapore records, including the approved pilot and a pending negative case, and a captured replay crossing. `test_track_map_websocket.py` covers delivery and generation changes. Frontend tests cover independent map modules, rendering, and collision handling. The real Singapore 2025 Race replay was also checked in HAdev on 2026-10-10; see `track-map-singapore-2025-annotation-qa.md` for the observed sample and limitations.
