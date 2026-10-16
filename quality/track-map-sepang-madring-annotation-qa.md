# Sepang and Madring 2026 annotation QA

Reviewed 2026-10-11. This extends the 2026 annotation catalog to the two
circuits that had 2026 `Position.z` geometry and FIA event maps but no
Multiviewer corner-coordinate response.

## Sources and method

Sepang uses the FIA's 2026 Bahrain Grand Prix in Malaysia circuit map and the
Sepang centreline from the [TUM racetrack database](https://github.com/TUMFTM/racetrack-database/blob/master/tracks/Sepang.csv).
Madring uses the FIA's [2026 Spanish Grand Prix circuit map](https://www.fia.com/system/files/decision-document/2026_spanish_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_and_emergency_exits_map.pdf)
and the [Madrid City Geoportal circuit dataset](https://geoportal.madrid.es/IDEAM_WBGEOPORTAL/dataset.iam?id=SPA_28079_CIRCUITO_F1_MADRING).
The 2026 `Position.z` geometry remains the map and driver-position coordinate
system. The two external centrelines were aligned to that geometry as offline
QA inputs; neither source is fetched by Home Assistant.

Closed-loop shape alignment had a 6.3 raw-unit RMS residual for Sepang and 6.6
for Madring. The FIA map establishes each turn's sequence and names the
sector, speed-trap, Overtake, and Straight Mode distances. Numbered turn
anchors are sampled from the ordered centreline at those map-identified turns.
Madrid T7 and T16 were cross-checked against the FIA intermediate points: S1
is 85 m before T7 and S2 is 40 m before T16. After snapping the sampled points
to the integration's simplified geometry, the largest corner-anchor gap is
under 500 raw units (50 m).

These are centreline reference points suitable for the optional, Experimental
map annotations; they are not surveyed apex coordinates. The original FIA map
artwork and external centreline files are not bundled in the annotation
catalog. Distribution of the derived annotations was approved by the project
owner on 2026-10-10; the catalog uses `rights_status=cleared`.

## Included marks

Sepang has start/finish, turns 1–15, two sector boundaries, one speed trap,
Overtake detection and activation, and normal/low-grip Straight Mode
activation points for zones A1–A4. Madring has start/finish, turns 1–22, two
sector boundaries, one speed trap, Overtake activation, and normal/low-grip
Straight Mode activation points for zones A1–A2. Madring's Overtake detection
is omitted because the FIA identifies it only as “Entry T22”, without a
measured distance that can be placed on the simplified centreline.

## Rebuild and checks

Run `python3.14 quality/track_map_annotation_expansion.py` from the Git
checkout to regenerate the deterministic catalog from the checked-in
coordinate snapshot. Catalog tests verify both geometry/year bindings, turn
counts and order, all five layers, source metadata, and the published distance
offsets for sectors and speed traps. Review renders are saved locally as
`/tmp/annotations-12.png` and `/tmp/annotations-153.png`; they contain only
the project's circuit geometry and derived annotations.
