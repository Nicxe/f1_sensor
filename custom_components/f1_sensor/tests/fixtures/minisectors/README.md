# Minisector contract fixtures

These fixtures lock the data boundary for issue #702. They contain reduced structural
slices from the local 2026 timing archives. Unrelated drivers and timing fields were
removed; the retained sector keys, segment keys and status values are unchanged.

`cases.json` covers:

- the initial list form;
- sparse indexed-object deltas;
- an atomic purple handoff between two drivers;
- unknown status code `2050`;
- a full driver reset and a partial object reset;
- replay seek generation replacement and a sequence gap requiring resync.

`contract.json` is the machine-readable version 1 contract. It defines protocol event
types, bounds, raw status handling, the six future field definitions and availability
decisions. The step 2 internal store and the planned steps 3–4 transport/UI use this
same contract; the fixtures are not a second runtime implementation.

`lap_transition.json` preserves one reduced Monza race transition where
`NumberOfLaps` advances at `00:58:24.556` and the driver's complete segment reset
frame follows 4.177 seconds later. The reset frame also contains the new lap's
non-zero S1 segment, so tests must apply the frame atomically and retain that value.

Tests must stay offline and must not read the original archive location. If a fixture is
updated, record the source session and timestamp and keep the reduced payload small.
