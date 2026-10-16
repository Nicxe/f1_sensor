# Track Map annotations: step 6 local validation and handoff

Issue #787, checked locally on 2026-10-10. The working checkout is `dev` at
`62a846e`, with the uncommitted work from steps 0–5 and this step. It is nine
commits behind `origin/dev`; no merge, commit, push, issue update, PR or release
was performed. This record separates observed HAdev behavior from automated and
future external checks.

## Local gates

| Check | Result |
| --- | --- |
| Focused annotation catalog, binding, WebSocket and replay adapter tests | 77 passed |
| `./scripts/run_ruff.sh` from `/Volumes/config` | Passed; 229 files unchanged |
| Full `./scripts/run_tests.sh` from `/Volumes/config` | 1,736 passed in 398.17 s |
| `npm run test:frontend:unit` | 248 passed |
| `npm run test:frontend` | 224 Chromium flows passed |
| `npm run build:field-catalog` and `npm run test:field-catalog` | Passed; generated catalog accepted by the checker |
| `npm run test:automation` | 46 Python and 50 Node checks passed |
| `npm run test:docs` after guide edits | Production build, 4 structure checks and 15 browser flows passed |
| `git diff --check` | Passed |

The relevant frontend unit and browser suites include module-local layer choices,
old saved configuration defaults, wrong year/layout/geometry, partial and missing
layers, seek/session/reconnect clearing, mobile labels, editor behavior, spoiler
and visibility regressions. These are automated assertions, not physical-device
or assistive-technology observations. `./scripts/run_ruff_ci.sh` is reserved for
a separately requested push or PR and was not required in this local-only step.

## Observed HAdev behavior

The running HAdev Core served a newly opened Chrome frontend instance. The saved
F1 Map dashboard first showed live Singapore Grand Prix 2026 Sprint with 22
drivers and no selected annotations. In unsaved **Actual data** editor previews,
the five optional fields showed the following:

| Session | Cars | Marks in complete text list | Visible labels | DOM rectangle overlaps |
| --- | ---: | ---: | ---: | --- |
| Singapore 2025 Race, 417 px map | 20 | 29 | 21 | 0 label-to-car, 0 label-to-label |
| Singapore 2025 Race, 305 px map in 390 px viewport | 20 | 29 | 20 | 0 label-to-car, 0 label-to-label |
| Silverstone 2025 Race, 417 px map | 20 | 26 | 20 | 0 label-to-car, 0 label-to-label |

Both 2025 maps were visually inspected with start/finish, corners, real S1/S2
boundaries, speed trap and DRS points in their reviewed positions. Hidden SVG
labels remained in the complete text list. After switching back to live Singapore
2026 Sprint, selecting all five layers in another unsaved preview kept the
track and 22 cars and displayed the text notice that no verified markings are
available for this session; no 2025 mark appeared. Every editor preview was
cancelled and the dashboard was left unchanged.

The Singapore replay was paused at 4 seconds, sought to 34 seconds, then a full
browser reload reconnected to the same paused replay and 20-car map without a
browser console warning or error. Stopping it restored live Singapore Sprint.
A separate Silverstone 2025 Race replay then loaded, played and was stopped;
the view again returned to live Singapore. These observations cover two sessions,
one seek and one browser reconnect. Broader session, network and long-duration
combinations are covered by tests or the manual handoff, not by this UI sample.

For the integration lifecycle, the F1 entry was disabled in HAdev, visibly
reported **Disabled by user**, enabled again, and reloaded with Home Assistant's
**The integration was reloaded** confirmation. The entry again exposed 66
entities, the saved map received 22 live car positions, and the replay year
returned to 2026. The Home Assistant Core log view reported **There are no new
issues!** and the Chrome console had no warning or error entries in this check.

## Coverage, parity and limits

The catalog has ten verified, distribution-cleared records: five layers each
for Singapore and Silverstone 2025, bound to reviewed layout and geometry.
Singapore supplies 29 marks and omits DRS A4 because the simplified geometry
cannot place it confidently. Silverstone supplies 26 marks. Other seasons and
layouts have no verified marks; the circuit outline and cars remain independent.
S3 ends at start/finish. Speed traps and DRS points are locations, not speed
values or full zone spans. The source and calibration method are recorded in
[the step 5 expansion review](track-map-2025-annotation-expansion-qa.md).

All six changed card files (three locales and `modular/catalog.js`,
`modular/map-data.js`, `modular/map-view.js`) were byte-identical between the
primary HAdev source, HAdev integration and Git checkout. The annotation catalog
and four changed integration Python files were byte-identical between HAdev and
Git. Field-catalog JSON and Markdown were regenerated and passed their parity
checker.

Step 5 measured a 3,437-byte larger Singapore snapshot than the same snapshot
without annotations, no resend in position-only deltas, and fewer than 12,000
bytes in the ten-record catalog. The earlier Singapore pilot fixture measured
0.9 ms p95 for a 20-annotation map update and 32,256 transferred bytes for
map-related JavaScript versus 22,190 bytes at step 0 (+10,066). These are
prior local Chromium measurements, not new full-catalog network or device
benchmarks; this step changed documentation only.
Label collision handling can hide a visual tag, so the text list is necessary
for complete access. The sampled real replay frames do not establish every
frame, browser, theme or assistive technology. No external beta, physical
device, full race weekend or published CI was run. Concrete steps and acceptance
criteria are in H12 of the [manual handoff](/Users/niklas/GitHub/F1_SENSOR_MANUELL_OVERLAMNING_2026-09-17.md).
