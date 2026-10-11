# 2025 Track Map annotation expansion: source and QA record

Issue #787, step 5, reviewed 2026-10-10. The catalog contains five optional annotation layers for each of the reviewed Singapore and Silverstone 2025 layouts. Its records are bound to the exact circuit, layout, season, and static-geometry fingerprint. They do not bind to earlier or later races merely because the circuit name is the same.

## Source and placement method

| Circuit | Event map | Coordinate source | Verified layers |
| --- | --- | --- | --- |
| Singapore 2025 | [FIA event map](https://www.fia.com/system/files/decision-document/2025_singapore_grand_prix_-_event_notes_-_circuit_map_pit_lane_emergency_exits_map_and_quarantine_zone.pdf) | [MultiViewer 2025 circuit coordinates](https://api.multiviewer.app/api/v1/circuits/61/2025) | Start/finish, turns 1–19, S1/S2, speed trap, DRS D1–D3 and A1–A3 |
| Silverstone 2025 | [FIA event map](https://www.fia.com/system/files/decision-document/2025_british_grand_prix_-_event_notes_-_circuit_map_v2.pdf) | [MultiViewer 2025 circuit coordinates](https://api.multiviewer.app/api/v1/circuits/2/2025) | Start/finish, turns 1–18, S1/S2, speed trap, DRS D1–D2 and A1–A2 |

The FIA maps identify the turn numbers and measured distances from turns to sector boundaries, speed traps, and DRS points. `quality/track_map_annotation_expansion.py` snaps season-specific turn coordinates to the ordered static centreline, converts each published metre offset using the official lap length, and places each mark on that directed path. Sector lines are perpendicular to it. The first Singapore start/finish and corner records remain those from the separately reviewed [pilot calibration](track-map-singapore-2025-annotation-qa.md). Silverstone's start marker was checked against the map's M18.7 start position, distinct from its M18.1 control line.

Singapore's fourth DRS activation mark is absent: the FIA map says only “Exit T19”, which does not give a safe distance on this simplified centreline. The card therefore exposes the six positionable DRS points without inventing A4. S1 and S2 are actual published boundaries; start/finish closes S3. The speed trap point describes where speed is measured, not the measured speed. DRS points do not claim to draw the full zone.

These are map annotations on a sampled centreline, not survey-grade apex or track-edge coordinates. The catalog stores derived coordinates and source references, not FIA artwork. The project owner approved distribution of these derived annotations on 2026-10-10; all reviewed records use `rights_status=cleared`.

## Reproducibility and visual review

From the Git checkout, run `python3.14 quality/track_map_annotation_expansion.py`, then compare the generated catalog with the HAdev integration copy. The script uses fixed source anchors and does not call either source API at runtime. Its output is deterministic. The [combined review image](/Users/niklas/GitHub/F1_SENSOR_MODULAR_BANKARTA_STEG5_EVIDENS_2026-10-10/review-expanded.png) shows both layouts with marks and labels against their static geometry. The source maps were inspected alongside that image; the rendered marks follow the FIA turn sequence and published upstream/downstream relationships.

The catalog tests check five layers per reviewed circuit, season and geometry fingerprints, ordered corners, directed sector/trap distances, missing A4, and rejection of an old season or wrong circuit. Frontend tests check complete and partial layer coverage, invalid item labels, and clearing annotations on a mismatched session, seek, or geometry. A selected layer without a valid catalog record appears as unavailable while other valid layers remain visible. Unknown circuits and old replay seasons do not borrow 2025 marks.

HAdev's actual-data editor preview was checked without saving the dashboard. The 2025 British Grand Prix Race replay showed 20 cars and 26 listed marks. The 2025 Singapore Grand Prix Race replay showed 20 cars and 29 listed marks. The initial Singapore view exposed overlapping mark labels. The card now gives sector/start tags priority, then corner labels, then speed-trap/DRS labels; a conflicting label is hidden visually and remains in the complete text list. After the managed card resource received its new cache version and the Singapore replay was reloaded, a DOM rectangle check at the editor's 422 px map width found 22 visible labels, zero visible label-to-label overlaps, and zero visible label-to-car overlaps in that paused frame. This is one real replay frame, not a guarantee for every frame or device.

## Validation and remaining scope

The expanded Singapore WebSocket snapshot adds 3,437 JSON bytes compared with a snapshot without annotations; subsequent position deltas omit static annotations. The regression limit is 4,096 bytes for this reviewed layout. Catalog JSON remains below 12,000 bytes for all ten records.

Local gates passed on 2026-10-10: `./scripts/run_ruff.sh`, all 1,736 Python tests, 248 frontend unit tests, 224 frontend browser tests, `npm run test:field-catalog`, `npm run test:automation`, `npm run test:docs` (build checks and 15 browser tests), and `git diff --check`. The changed modular map files are byte-identical across the HAdev primary source, HAdev integration bundle, and Git checkout; the catalog is byte-identical between HAdev and Git. HAdev loaded the current managed frontend resource after an integration reload. The visible Home Assistant Core log showed no F1 Sensor warnings or errors; its sole warning was an invalid-authentication response to the local unauthenticated `/api/` probe used during this review. The replay was stopped, the year restored to 2026, and the editor preview cancelled.

The user guide lists the two 2025 layouts and the omitted Singapore A4. Other circuit seasons have no verified layer records yet. Manual physical-device and assistive-technology checks, a full race weekend, external beta, and published CI are later validation and delivery work; this record does not claim those results.
