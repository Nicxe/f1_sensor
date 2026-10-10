# Singapore 2025 Track Map annotation pilot: calibration and QA

Issue #787, step 2, reviewed 2026-10-09. The pilot contains one start/finish line and turns 1–19. It contains no sector, speed-trap, or detection-zone coordinates.

## Sources and coordinate method

- Geometry and movement: the existing 91-point `circuit_key=61` static geometry and the local Singapore 2025 Race `Position.z` replay dump. Both use the same raw X/Y coordinate system. The geometry fingerprint is `sha256:7fcbc8eecbacafcb486b7d899bb360f9d61d5eb3bc139a0fcafea9e3688a513d`.
- Turn identity and start/control distinction: [FIA 2025 Singapore Grand Prix circuit map, document 7, map issued 1 October 2025](https://www.fia.com/system/files/decision-document/2025_singapore_grand_prix_-_event_notes_-_circuit_map_pit_lane_emergency_exits_map_and_quarantine_zone.pdf), page 4. The source shows 19 numbered turns, a black start-line marker at M0.0, and a separate checkered control-line marker lower on the straight. The PDF states © 2025 Formula One World Championship Limited. No source image or vector artwork is stored in the catalog or review output.

`quality/track_map_annotation_calibration.py` records the raw geometry index chosen for each turn in lap order and a label offset in the card's 0–100 SVG coordinates. It derives the actual raw X/Y anchors from the current geometry catalog, constructs a line perpendicular to the ordered path at point 47 for the start line, and exports the two v1 catalog records. The script mirrors the card's `trackProjection` math for both `source`/`raw` rotation and `flipped`/`normal` vertical axis. It does not infer raw coordinates directly from PDF pixels, which would be unsafe because the FIA map is schematic and has no supplied image-to-X/Y transform.

The reviewed index sequence for turns 1–19 is `50, 52, 54, 60, 63, 68, 74, 79, 84, 0, 3, 6, 10, 21, 27, 33, 36, 41, 43`. It crosses the closed-polyline seam once between turns 9 and 10. Every anchor is exactly on the raw catalog geometry, and the sequence follows the direction seen in the replay. The start line is centred on raw point 47. A first draft at point 45 was rejected because the FIA map places that lower section near the distinct control line.

A local parity check projected turns 1 and 10 and the start-line endpoint through both the offline script and the card's current `trackProjection` for all four orientation variants. The maximum numeric difference was 0 in SVG coordinates. The compact JSON representation of both records is 2,786 bytes before transport shaping; the step-0 target of at most 2,048 additional snapshot bytes must be checked when step 3 defines the wire envelope.

## Visual and replay review

The [four-orientation review](/Users/niklas/GitHub/F1_SENSOR_MODULAR_BANKARTA_STEG2_EVIDENS_2026-10-09/orientations.png) and [four replay frames](/Users/niklas/GitHub/F1_SENSOR_MODULAR_BANKARTA_STEG2_EVIDENS_2026-10-09/replay-frames.png) were generated from the same catalog. The replay frames are lines 2500, 4500, 6500, and 8500 of the local Race `Position.z` dump; each yielded 20 moving cars. The labels and start-line position were inspected in all four orientation variants and against these frames. Initial offsets for turns 2 and 10–12 put text on or too near the track; they were moved before the catalog received `qa_status=verified`.

With point-centre measurements in the card's 0–100 coordinates, the smallest distance in the four orientation variants is 3.64 units from a label centre to the path and 6.21 units between label centres. In the four replay frames, the smallest label-centre to car-centre distance is 3.56 units. All label centres stay within X 5.2–93.3 and Y 15.6–84.4. These measurements support the offline anchor review; they are **not** a claim of zero rendered text overlap at mobile size. Font metrics, 360 px rendering, and dynamic car labels were checked later in the real HAdev replay.

On 2026-10-10, HAdev Core was restarted after the rights gate changed, and the real Singapore 2025 Race replay was loaded and paused five seconds after its start. The modular card editor's unsaved **Actual data** preview showed 20 cars, the start/finish line, and turns 1–19 from the WebSocket stream. The first rendered preview exposed collisions between annotation labels and cars at the crowded grid. The card now hides an annotation label or corner glyph while it collides with a car marker or driver label; the start/finish line remains visible, and the complete 20-item text list remains available.

After this correction, DOM rectangle checks in the real replay found **zero visible annotation-to-car collisions** at both 422 px and a forced 360 px map width. At 360 px, 17 labels remained visible, two corner glyphs and the S/F tag were hidden, and the text list still reported all 20 markings. A browser regression covers the collision and text alternatives. This is a paused start-grid sample, not a claim that every replay frame, physical device, or assistive technology was manually checked. The editor preview was cancelled without saving the HAdev dashboard.

The final local gates passed on 2026-10-10: Ruff, all 1,732 Python tests, 247 frontend unit tests, 224 browser tests, catalog regeneration with byte parity, and `git diff --check`. The six changed frontend files are byte-identical across the primary HAdev source, HAdev integration bundle, and Git checkout. No commit, push, release, or permanent HAdev dashboard edit is part of this pilot check.

The replay also confirms forward motion across the chosen start line. For car 1, sample positions at 2025-10-05 11:24:21.874 UTC (`[661, 1112]`) and 11:24:26.414 UTC (`[551, 1893]`) lie on opposite sides of its perpendicular line, while the nearest geometry index advances from 47 to 48. This checks direction only; it does not equate the FIA start line with the separate control line used for timing.

## Catalog gates and limitations

The versioned catalog is `custom_components/f1_sensor/track_map_annotation_catalog.json`. Its two records have `qa_status=verified` for the geometry and visual review. On 2026-10-10 the project owner approved distribution for this pilot, so both records now have `rights_status=cleared`. The binder makes them available only for Singapore 2025 and the exact geometry fingerprint. The WebSocket v2 stream and modular card consume the catalog; a pending test copy still binds to no layer.

The FIA PDF is a review reference, not a license grant. `rights_status=cleared` records the project owner's explicit distribution decision; it does not claim a license was supplied by the FIA or Formula One World Championship Limited. The visual review also cannot prove sub-metre physical apex placement: the raw geometry is a sampled driving line and the FIA schematic lacks an exact transform. If a later source or replay contradicts an index, change the record and rerun the review rather than reusing its `verified` status.

## Reproduction

From the Git checkout, with Python 3.14 and Pillow available:

```bash
python3.14 quality/track_map_annotation_calibration.py \
  --qa-status verified \
  --rights-status cleared \
  --catalog-out /tmp/singapore-2025-annotations.json \
  --review-out /tmp/singapore-2025-orientations.png

python3.14 quality/track_map_annotation_calibration.py \
  --qa-status verified \
  --review-out /tmp/singapore-2025-replay.png \
  --replay-dump '/Volumes/Data/F1 Live Timing API - Dumps/2025/GrandPrix/2025-10-03_Singapore_Grand_Prix/Race/2025_2025-10-05_Singapore_Grand_Prix_2025-10-05_Race_Position.z.txt'
```

The first JSON output matches the Singapore start/finish and corners subset of the versioned catalog. Step 5 added other layers and Silverstone 2025; see `quality/track-map-2025-annotation-expansion-qa.md`. The script reads only local geometry and replay files; its review PNGs contain our geometry, annotation labels, and moving-car positions, without FIA map pixels. The pytest catalog gates check identities, point count and order, source metadata, maximum JSON size, start-line direction, geometry fingerprint, rights gating, and rejection of an older layout or changed geometry.
