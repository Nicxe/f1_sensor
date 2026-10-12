# 2026 upcoming Track Map annotation baseline QA

Baseline reviewed 2026-10-11; follow-up checklist updated 2026-10-12. This
prepares five of the remaining 2026 venues with stable map markings before
their race weekends, using 2025 FIA event maps and the available circuit
position references. The data is a previous-season baseline, not a claim that
each annotation has already been confirmed against 2026 event telemetry.

## Prepared coverage

| 2026 venue | Circuit key | FIA map source | Sector lines and speed trap | Included |
| --- | --- | --- | --- | --- |
| United States, Austin | `9` | [2025 United States Grand Prix event map](https://www.fia.com/system/files/decision-document/2025_united_states_grand_prix_-_event_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_quarantine_zone_map_red_zones_map.pdf) | S1 55 m before T7; S2 65 m before T13; trap 180 m before T12 | Start/finish, turns 1–20, S1/S2, speed trap |
| Mexico City | `65` | [2025 Mexico City Grand Prix event map](https://www.fia.com/system/files/decision-document/2025_mexico_city_grand_prix_-_event_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_quarantine_zone_area.pdf) | S1 136 m before T4; S2 242 m before T12; trap 234 m before T1 | Start/finish, turns 1–17, S1/S2, speed trap |
| São Paulo, Interlagos | `14` | [2025 São Paulo Grand Prix event map](https://www.fia.com/system/files/decision-document/2025_sao_paulo_grand_prix_-_event_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_quarantine_zone_and_red_zones_map.pdf) | S1 168 m before T4; S2 85 m before T12; trap 90 m before T1 | Start/finish, turns 1–15, S1/S2, speed trap |
| Qatar, Lusail | `150` | [2025 Qatar Grand Prix event map](https://www.fia.com/system/files/decision-document/2025_qatar_grand_prix_-_event_notes_-_circuit_map._pit_lane_drawing_emergency_exits_map_ers_battery_containment_area_red_zones_map.pdf) | S1 80 m before T6; S2 75 m before T12; trap 205 m before T1 | Start/finish, turns 1–16, S1/S2, speed trap |
| Abu Dhabi, Yas Marina | `70` | [2025 Abu Dhabi Grand Prix event map](https://www.fia.com/system/files/decision-document/2025_abu_dhabi_grand_prix_-_event_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_quarantine_zone_and_red_zones.pdf) | S1 205 m before T5; S2 100 m before T9; trap 150 m before T6 | Start/finish, turns 1–16, S1/S2, speed trap |

For each venue, FIA-published sector and speed-trap offsets are projected from
their named corner onto the 2025 position-data circuit line. Start/finish and
corner references are projected onto the same simplified line. The largest
corner-reference gap is under 500 raw coordinate units (50 m); this is a
placement tolerance, not survey accuracy. The coordinate provider reports
2021 references for Austin, Mexico City, and Abu Dhabi, and 2023 references
for Interlagos and Lusail, despite the requested 2025 endpoint. Those source
years are retained in the catalog and snapshot so the age is auditable.

## Known gaps and handling

| Missing or uncertain item | Why | Handling |
| --- | --- | --- |
| 2026-specific Overtake and Straight Mode marks for the five baselines | 2025 DRS points do not prove 2026 Overtake or Straight Mode locations. | Keep the layer absent. Add points only from a 2026 FIA map with measurable positions; do not translate DRS labels or offsets. |
| Las Vegas turn annotations | Available provider corner numbering conflicts with the FIA 2025 event map, so the turn sequence cannot be bound confidently to the map line. | Keep the outline and car positions available, but omit its annotation catalog until the numbering is reconciled against a reliable circuit source. |
| Static pit-lane marker | Event maps show the pit lane, but no reviewed coordinate anchor places pit entry/exit accurately on the simplified centreline. | Continue using live/replay pit status in the driver list; do not add a guessed fixed marker. |
| 2026 event-specific confirmation | At review time, no event-map and position-stream pair for these upcoming weekends was available locally. | Show the card's previous-season baseline note. Recheck once FIA maps/streams arrive and collect corrections for a planned catalog update. |

The card marks these five circuits as using a previous-season baseline. Users
can use the outline, corners, sectors, and speed trap before a race starts, and
should report a visible mismatch with a screenshot and circuit/session details.
Any confirmed corrections can be grouped into a catalog release, avoiding a
release for every weekend. If a current FIA source does not give a measurable
point, that point remains unavailable until one does.

## Checklist for when 2026 data is available

Complete the relevant circuit checklist from the official 2026 event map and
that event's `Position.z` stream. Keep the current baseline active until the
2026 comparison is complete. A 2026 event map alone does not verify positions
on the telemetry geometry, and a position stream alone does not establish FIA
sector or detection/activation definitions.

### United States, Austin — circuit key `9`

- [ ] Save the 2026 FIA event map and record its revision/date.
- [ ] Obtain the 2026 event `Position.z` stream and compare its circuit line and
  start/finish point with the 2025 geometry.
- [ ] Reconcile all 20 corner numbers in sequence. Replace the 2021 provider
  references with 2026 positions where the stream supports it.
- [ ] Verify S1 (55 m before T7), S2 (65 m before T13), and the speed trap
  (180 m before T12) against the 2026 map. Record changed offsets instead of
  carrying 2025 values forward.
- [ ] Add only 2026 FIA Overtake/Straight Mode points with measurable offsets.
  Do not infer Overtake positions from DRS.
- [ ] Check whether pit entry/exit can be tied to the telemetry centreline with a measured source.
- [ ] Render the annotations over the 2026 geometry and record the visual review result.

### Mexico City — circuit key `65`

- [ ] Save the 2026 FIA event map and record its revision/date.
- [ ] Obtain the 2026 event `Position.z` stream and compare its circuit line and
  start/finish point with the 2025 geometry.
- [ ] Reconcile all 17 corner numbers in sequence. Replace the 2021 provider
  references with 2026 positions where the stream supports it.
- [ ] Verify S1 (136 m before T4), S2 (242 m before T12), and the speed trap
  (234 m before T1) against the 2026 map. Record changed offsets instead of
  carrying 2025 values forward.
- [ ] Add only 2026 FIA Overtake/Straight Mode points with measurable offsets.
  Do not infer Overtake positions from DRS.
- [ ] Check whether pit entry/exit can be tied to the telemetry centreline with a measured source.
- [ ] Render the annotations over the 2026 geometry and record the visual review result.

### São Paulo, Interlagos — circuit key `14`

- [ ] Save the 2026 FIA event map and record its revision/date.
- [ ] Obtain the 2026 event `Position.z` stream and compare its circuit line and
  start/finish point with the 2025 geometry.
- [ ] Reconcile all 15 corner numbers in sequence. Replace the 2023 provider
  references with 2026 positions where the stream supports it.
- [ ] Verify S1 (168 m before T4), S2 (85 m before T12), and the speed trap
  (90 m before T1) against the 2026 map. Record changed offsets instead of
  carrying 2025 values forward.
- [ ] Add only 2026 FIA Overtake/Straight Mode points with measurable offsets.
  Do not infer Overtake positions from DRS.
- [ ] Check whether pit entry/exit can be tied to the telemetry centreline with a measured source.
- [ ] Render the annotations over the 2026 geometry and record the visual review result.

### Qatar, Lusail — circuit key `150`

- [ ] Save the 2026 FIA event map and record its revision/date.
- [ ] Obtain the 2026 event `Position.z` stream and compare its circuit line and
  start/finish point with the 2025 geometry.
- [ ] Reconcile all 16 corner numbers in sequence. Replace the 2023 provider
  references with 2026 positions where the stream supports it.
- [ ] Verify S1 (80 m before T6), S2 (75 m before T12), and the speed trap
  (205 m before T1) against the 2026 map. Record changed offsets instead of
  carrying 2025 values forward.
- [ ] Add only 2026 FIA Overtake/Straight Mode points with measurable offsets.
  Do not infer Overtake positions from DRS.
- [ ] Check whether pit entry/exit can be tied to the telemetry centreline with a measured source.
- [ ] Render the annotations over the 2026 geometry and record the visual review result.

### Abu Dhabi, Yas Marina — circuit key `70`

- [ ] Save the 2026 FIA event map and record its revision/date.
- [ ] Obtain the 2026 event `Position.z` stream and compare its circuit line and
  start/finish point with the 2025 geometry.
- [ ] Reconcile all 16 corner numbers in sequence. Replace the 2021 provider
  references with 2026 positions where the stream supports it.
- [ ] Verify S1 (205 m before T5), S2 (100 m before T9), and the speed trap
  (150 m before T6) against the 2026 map. Record changed offsets instead of
  carrying 2025 values forward.
- [ ] Add only 2026 FIA Overtake/Straight Mode points with measurable offsets.
  Do not infer Overtake positions from DRS.
- [ ] Check whether pit entry/exit can be tied to the telemetry centreline with a measured source.
- [ ] Render the annotations over the 2026 geometry and record the visual review result.

### Las Vegas — circuit key `152` (currently unannotated)

- [ ] Obtain the 2026 FIA event map and 2026 event `Position.z` stream.
- [ ] Resolve the disagreement between provider corner numbering and FIA's
  published map with the 2026 sources. Record the one-to-one turn sequence
  before adding labels.
- [ ] If the turn sequence and line cannot be reconciled, keep corner
  annotations unavailable and record evidence of the remaining mismatch.
- [ ] Once reconciled, add start/finish, corners, sectors, speed trap, and any
  measurable FIA Overtake/Straight Mode marks. Apply the same source and visual
  review checks as for the other circuits.
- [ ] Check whether pit entry/exit can be tied to the telemetry centreline with a measured source.

### Close-out checklist for a grouped catalog update

- [ ] Bind each completed circuit to its verified 2026 layout and geometry
  fingerprint. Remove `baseline_season: 2025` only from layers confirmed using
  2026 sources.
- [ ] Keep any point without measurable 2026 evidence absent and note the reason in this report.
- [ ] Update source links and dates, coordinate-reference year, turn counts,
  offsets, coverage table, and user-facing baseline wording.
- [ ] Add or update tests for source provenance, turn order, sector and speed
  trap offsets, layout binding, and unavailable layers.
- [ ] Review each changed map, then run Ruff, integration and frontend tests,
  documentation tests, and copy-parity checks.
- [ ] Group completed corrections into a planned catalog release. Release
  sooner only if a correction is needed to prevent misleading map data.

## Reproduction and checks

The frozen coordinate inputs are in
`quality/track_map_2025_coordinate_baseline_snapshot.json`. Regenerate the
catalog with:

```sh
python3.14 quality/track_map_annotation_expansion.py
```

`custom_components/f1_sensor/tests/test_track_map_annotation_catalog.py`
checks the five layout bindings, the four included layers, turn counts,
coordinate provenance, and geometry proximity. The optional user notice is
covered by `frontend-tests/unit/modular-map.test.mjs`.
