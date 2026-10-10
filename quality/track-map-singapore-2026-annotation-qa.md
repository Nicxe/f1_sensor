# Singapore 2026 Track Map annotation review

Issue #787 follow-up, reviewed 2026-10-10. The five Singapore 2026 layers are tied to circuit `61`, the reviewed post-2023 Marina Bay layout, season 2026, and the existing static geometry fingerprint. They contain 33 marks: start/finish, turns 1–19, S1 and S2, one speed trap, one Overtake activation point, and nine Straight Mode activation points.

## Sources and method

The [FIA Singapore 2026 circuit map V2](https://www.fia.com/system/files/decision-document/2026_singapore_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_and_emergency_exits_map.pdf), issued 7 October 2026 and enclosed in FIA document 7 on 8 October, supplies the 19 corner numbers, start/control line distinction, S1 at 150 m before T7, S2 at 140 m before T14, and the speed trap at 150 m before T1. It also supplies the 2026 Overtake and Straight Mode activation offsets. No 2025 DRS point is assigned to 2026.

The [2026 Singapore coordinate endpoint](https://api.multiviewer.app/api/v1/circuits/61/2026) returned 19 corners and 544 X/Y samples. Its `corners`, `rotation`, `x`, and `y` fields were byte-equivalent after normalized JSON encoding to the [2025 endpoint](https://api.multiviewer.app/api/v1/circuits/61/2025), with SHA-256 `509e4a519dca755aa981e31f0879b6680ee5fde8a6d75367c1733816f63f5c79`. Both endpoints report canonical geometry year `2023`; the season-specific FIA maps establish that this layout remains in use in 2026. The integration's 91-point static centreline is a simplification of that same raw coordinate space.

`quality/track_map_annotation_expansion.py` projects the 2026 corner coordinates independently onto the static centreline. All 19 generated corner anchors are within 50 raw coordinate units of their coordinate-source positions. The start line, sector boundaries, and speed trap share the 2025 geometry positions only after checking them against the 2026 FIA map. Each measured activation offset is scaled by the published 4.927 km lap length and placed in forward lap order. The [local review rendering](/Users/niklas/GitHub/F1_SENSOR_MODULAR_BANKARTA_SINGAPORE_2026_EVIDENS_2026-10-10/review.png) shows all generated marks on the static centreline; it contains no FIA map artwork.

## 2026 activation points

| Mark | Published FIA location |
| --- | --- |
| OT A | 30 m after T17 |
| SM A1 N / L | 30 m / 90 m after T19 |
| SM A2 N | 50 m after T5 |
| SM A3 N / L | 70 m / 120 m after T9 |
| SM A4 N / L | 115 m / 165 m after T13 |
| SM A5 N / L | 70 m / 90 m after T15 |

`N` is the FIA's normal-grip activation and `L` is its low-grip activation. The FIA locates Overtake detection only at “Entry T17”, without a measured offset that can be placed confidently on the simplified centreline; it is omitted. The FIA lists no low-grip A2 activation. The catalog shows point locations, not complete Straight Mode or Overtake zones. Distribution of derived annotation data was approved by the project owner on 2026-10-10; the catalog does not copy FIA artwork.

## Validation and scope

The Python catalog tests check the year and geometry binding, all five layers, T4/T6 corner calibration, the 2026 activation offsets, and absence of DRS points. The frontend unit test checks 2026 rendering and rejection of a later unmatched season. Run `python3.14 quality/track_map_annotation_expansion.py` from the checkout to rebuild the catalog deterministically. The source PDFs and coordinate endpoint are QA inputs only; Home Assistant does not fetch them to render a card.

The compact 2026 annotation payload is 3,631 JSON bytes for 33 marks (compared with 3,290 bytes for 29 Singapore 2025 marks). Subsequent position deltas continue to omit static annotations.

The older Singapore 2025 pilot corner anchors remain unchanged in this follow-up. Comparing them to the now-checked coordinate source exposed T4 and T6 positions more than 900 raw units from the named corner coordinates; that separate 2025 calibration issue needs its own correction and QA update. The 2026 anchors use the corrected coordinate mapping.

After a Home Assistant Core restart, an unsaved **Actual data** editor preview of the live Singapore 2026 Sprint showed the track, 22 driver positions, all five selected annotation layers, and a **Track markings · 33** list. The expanded list contained turns 1–19, S1/S2, the speed trap, OT A, and all nine SM activations; the previous “No verified markings” notice was absent. The dashboard edit was cancelled without saving. The Home Assistant Core log view reported “There are no new issues!” after the restart and preview.

Local checks passed: `./scripts/run_ruff.sh`, the full `./scripts/run_tests.sh` suite (1,738 tests), `npm run test:frontend:unit` (249 tests), `npm run test:frontend` (224 tests), `npm run test:docs` (4 build checks and 15 browser tests), `npm run test:field-catalog`, and `npm run test:automation`. The changed card files are byte-identical across the primary HAdev file, the HAdev integration bundle, and the local Git copy; the catalog and contract are byte-identical between HAdev and Git. No commit or push was made.
