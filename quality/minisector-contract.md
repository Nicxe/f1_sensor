# Minisector data and protocol contract

**Date:** 2026-10-09  
**Status:** Steps 1–5 complete locally; implementation, documentation and local validation finished  
**Scope:** F1 Sensor integration and the modular `custom:f1-sensor-card`. Legacy cards are excluded.

This contract is the implementation boundary for issue #702. It adds no entity and
keeps minisector status outside Home Assistant state. Steps 2–4 provide the bounded
source, shared WebSocket transport and optional modular-card presentation.

The machine-readable source is
`custom_components/f1_sensor/tests/fixtures/minisectors/contract.json`. Reduced
archive cases are in the same directory in `cases.json` and `lap_transition.json`.

## Data meaning

The F1 `TimingData` stream contains a `Status` value for each segment. The checked
archives do not contain a time for each segment. The product must therefore show
status blocks and must never calculate or imply a minisector time.

Combined fields use the existing S1, S2 or S3 time from `driver_positions`. The
blocks below that time come from the minisector stream. The two values keep their
own source and timestamp meaning.

Raw source indexes are zero-based and are part of the contract:

- sector keys `0`, `1`, `2` map to S1, S2, S3;
- segment keys are retained exactly, including gaps;
- list payloads use their list position as the raw index;
- indexed-object payloads use their numeric key as the raw index;
- sorting an indexed object must never renumber its entries.

The initial source frame is commonly a list. Later frames are usually sparse
indexed objects. One source frame is applied atomically across all drivers. This
is required when a purple status moves from one driver to another in the same
frame.

## Status semantics

| Raw status | Product meaning | Visual token | Certainty |
| ---: | --- | --- | --- |
| `0` | Not set, reset or not yet driven | Neutral | Known |
| `2048` | Recorded without a personal or overall best status | Yellow | Known for this visualization |
| `2049` | Personal best | Green | Known |
| `2051` | Overall best | Purple | Known |
| `2064` | Special source status | Neutral with a non-color marker | Meaning not yet verified |
| Any other value, including `2050`, `2052` and `2068` | Unknown source status | Neutral with an unknown marker | Unknown |

Every stored and transmitted segment retains `raw_status`. Unknown values are not
mapped to yellow, green or purple. `2064` is not called a pit status and does not
receive the blue color from the inspiration image until its meaning is verified
against sufficient source evidence.

Yellow means the provider supplied the ordinary recorded status. It does not prove
that a segment was slower than the same driver's preceding lap.

## Bounded state

State is scoped by integration entry, selected source, session identity and an
opaque generation. Within a generation it is keyed by driver number, raw sector
index and raw segment index.

The version 1 limits are:

| Limit | Value |
| --- | ---: |
| Drivers | 32 |
| Sectors per driver | 3 |
| Segments per sector | 32 |
| Encoded event | 32 KiB |
| Shared UI deltas | 4 per second |
| Rolling per-client traffic | 16 KiB/s over 10 seconds |

The archive baseline observed at most 26 segments over a lap. The per-sector bound
of 32 leaves room for other circuits while keeping snapshots finite. Data outside
the bounds is rejected or reported unavailable; it is never silently assigned to
another index.

Current-lap state is retained. A growing history of completed laps is outside the
first version.

### Lap boundary

`NumberOfLaps` is metadata and must not clear a driver's strip. Archive evidence from
Monza, Baku and Bahrain shows that the counter advances about four seconds before the
segment reset frame. The completed strip remains visible during that interval.

The later source frame updates the full segment layout atomically. Its zero statuses
clear the completed lap and any non-zero S1 segment in the same frame already belongs
to the new lap. The store merges that exact frame without discarding the new value.

## WebSocket protocol version 1

The implemented command is `f1_sensor/minisectors/subscribe`. It uses the existing Home
Assistant authenticated connection and the integration's existing live/replay
source. It must not create a second F1 connection or polling loop.

A subscription request contains:

```json
{
  "id": 24,
  "type": "f1_sensor/minisectors/subscribe",
  "protocol_version": 1,
  "entry_id": "config-entry-id",
  "source": "live",
  "session_key": "opaque-session-key"
}
```

`source` and `session_key` must match a session the card is allowed to select. The
server validates them against the integration entry, spoiler state, Live Delay and
replay ownership. A locked archive selection without a supported segment source is
unavailable and never falls back to live.

### Common event envelope

Every event contains:

- `protocol_version`;
- `type` (`snapshot`, `delta`, `reset` or `unavailable`);
- `entry_id` and session identity;
- opaque `generation`;
- integer `sequence`;
- `generated_at`;
- `stream_timestamp`, which may be `null` when the source supplies no trustworthy
  timestamp.

HA receipt time is transport metadata and must not be presented as the source
measurement time.

### Snapshot

The first event is always a complete `snapshot` with sequence `0`. It contains all
bounded drivers, sectors, segment indexes and raw statuses currently known. Starting
mid-session, reconnecting and resubscribing after a gap use the same snapshot path.

### Delta

A `delta` contains a sparse `drivers` mapping with only changed
`(driver, sector, segment)` tuples, but all changes
from one source frame are published atomically. Its sequence is exactly the previous
sequence plus one. Coalescing may combine several consecutive source frames as long
as final state and atomic purple handoffs are preserved.

### Reset

A `reset` has a reason and explicit scope. Version 1 reasons are `new_lap`,
`session_part`, `session_change`, `seek`, `source_restart` and `unknown`. A scoped
reset replaces a driver only when source indexes were actually removed. Session,
qualifying-part, seek and source resets create a new generation and a complete
snapshot, so old colors cannot survive.

Large zero-valued source frames and partial zero-valued object deltas retain their
exact indexes. They are atomic status deltas rather than inferred removals. A partial
reset changes only supplied indexes. A forward `NumberOfLaps` update produces no
minisector event when no segment status changed.

### Unavailable

`unavailable` includes a stable reason and no segment state. Expected reasons include
`capability_missing`, `session_unavailable`, `spoiler_protected`, `source_inactive`,
`invalid_payload` and `bounds_exceeded`. An unavailable event cannot borrow data from
another session or source.

### Ordering, reconnect and resync

- Clients ignore events from an older generation.
- A sequence gap invalidates the affected generation.
- Resync means unsubscribe and subscribe again; every new subscription begins with a
  full snapshot. There is no separate mutable resync command.
- Replay seek backwards, replay-session change, session change, qualifying-part
  change, Live Delay change, integration reload and source restart create a new
  generation.
- A new generation clears retained and frozen minisector state before it can render.

## Availability and card lifecycle

| Context | Result |
| --- | --- |
| Matching active live session | Available after the first valid snapshot |
| Matching replay session | Available after the replay snapshot |
| No segment frame yet | Loading, then honest neutral/empty state |
| Spoiler protection active | Blocked; no retained sensitive segment state |
| Live Delay changed | New generation from the delayed stream |
| Replay seek or session changed | Discard generation, then require snapshot |
| Locked archive session | Unavailable without live fallback |
| Older backend without capability | Only minisector fields/module are unavailable |
| Module hidden or last consumer removed | Release the shared subscription |

Previewing a module or choosing a session in the editor must not start live collection,
replay or another integration action. Two visible module instances share transport only
when entry, source and session identity match. Their field order, driver/team filters,
visibility and presentation remain independent.

## Field catalog entries

The machine-readable contract contains complete ordinary metadata for these six
fields:

| Field | Type | Source path | Unit | Sortable |
| --- | --- | --- | --- | --- |
| `minisector_1` | Status strip | `drivers.*.sectors.0.segments` | None | No |
| `minisector_2` | Status strip | `drivers.*.sectors.1.segments` | None | No |
| `minisector_3` | Status strip | `drivers.*.sectors.2.segments` | None | No |
| `sector_1_with_minisectors` | Existing sector time plus strip | S1 time + sector `0` statuses | Seconds for the existing sector time | Yes |
| `sector_2_with_minisectors` | Existing sector time plus strip | S2 time + sector `1` statuses | Seconds for the existing sector time | Yes |
| `sector_3_with_minisectors` | Existing sector time plus strip | S3 time + sector `2` statuses | Seconds for the existing sector time | Yes |

All six entries declare labels in English and Swedish, type, unit, source, path,
capability, modes, sessions, identity, generation, timestamps, freshness, spoiler
handling, sorting, filtering, mobile priority, presentations, estimation and
comparison meaning.

They support live and replay for practice, qualifying, sprint qualifying, sprint and
race. They are spoiler-sensitive, never estimated and identify segment as part of the
value identity. The standalone fields have no unit. Combined fields have seconds only
because they also display the existing sector time.

Step 4 registers these exact entries after the bounded source and transport exist.
The generated field-catalog artifacts include the same metadata. Existing timing
profiles remain unchanged, so saved and default cards do not opt in automatically.

## Archive fixtures

| Fixture | Archive evidence |
| --- | --- |
| Initial list | Bahrain qualifying, `00:00:15.427`, 5/6/9 segments |
| Sparse object | Monza FP2, `00:13:50.952`, raw S1 index `1` |
| Purple handoff | Bahrain qualifying, `00:13:30.958`, drivers 31 and 87 at the same raw index |
| Unknown code | Monza FP2, `00:20:15.966`, raw `2050` at S2 index `6` |
| Large reset | Monza FP2, `00:00:10.453`, one exact 6/7/9 driver slice from the 22-driver frame |
| Partial reset | Bahrain FP1, `00:15:36.026`, S1 index `0` retained while supplied later indexes reset |
| Lap transition | Monza race, `00:58:24.556` counter update followed by the atomic segment reset at `00:58:28.733` |
| Seek generation | Monza race around red flag `01:01:07` and restart `01:32:24` |

Tests use the checked-in reduced copies and never depend on `/Volumes/Data` or a
network connection.

## Step 2 internal state implementation

`minisectors.py` now consumes the existing delayed `TimingData` path inside
`LiveDriversCoordinator`. It does not subscribe, poll, perform I/O or call
`async_set_updated_data`. Its bounded state is separate from `driver_positions` and
is available only as an isolated internal snapshot for step 3.

List payloads replace the addressed sector's segment collection. Indexed-object
payloads merge only supplied raw indexes. Forward lap-count changes update metadata
without clearing the completed strip; the source's later zero-valued segment frame
performs the visible lap transition atomically. Session parts, session identity,
replay rewind, source changes, Live Delay and spoiler protection start clean
generations. Track disruption clears current segment status inside the generation.
Replay reset, source unavailability and unload discard retained state.

The provider-neutral history normalizer also retains sparse raw sector and segment
indexes. This closes the two step 2 regression gaps without exposing the six future
catalog fields.

## Regression gates

Step 1 began with three strict expected failures:

1. live driver state does not retain segment-only source frames;
2. the history normalizer renumbers sparse raw indexes;
3. the production modular field catalog does not yet contain the six fields.

Step 2 closed the first two gates. Step 4 registers the six fields and closes the
last gate as a normal passing assertion. No minisector contract test remains marked
as an expected failure.

The seek, reset and measured lap-transition fixtures exercise the intended generation
and sequence rules with a small reference reducer. Runtime WebSocket tests replace
that reference path in step 3.

## Step 3 entry criteria

Step 3 may expose the internal snapshot through the versioned subscription contract.
It must retain the store's generation boundaries, coalesce only after atomic source
frames, enforce event and traffic bounds, resync after gaps and release every
subscription. No public field or standalone module is enabled until the backing
subscription passes lifecycle and load tests.

## Step 3 WebSocket implementation

Protocol version 1 is implemented by `f1_sensor/minisectors/subscribe`. Requests
must provide a non-empty integration entry ID, `live` or `replay` source and the
actual selected session key. The backend resolves the active live SessionInfo key
or replay-controller selection before exposing state. A different entry, source or
session receives `unavailable` without segment data; no active-session fallback is
performed.

One entry-owned broadcast hub listens to the bounded store while at least one
consumer exists. It applies a 250 ms shared coalescing interval after complete source
frames. Each client retains its own generation and sequence cursor. A new
subscription starts with sequence 0 and a full snapshot, ordinary changes use sparse
deltas, same-generation removals use a scoped reset with the complete replacement
for affected drivers, and generation changes use a fresh snapshot. Unsubscribe and
subscribe is the version 1 resync operation.

The transport validates global spoiler state, live availability, source and session
identity on every delivery. Store resets also publish stable unavailability reasons.
Encoded events are capped at 32 KiB and each client has a ten-second rolling 160 KiB
budget. Crossing either bound sends a small `bounds_exceeded` event when the budget
allows and pauses that client for the rest of the window. The normal integer-status
snapshot at the declared 32-driver, three-sector and 32-segment bounds is covered by
a strict 32 KiB regression test.

Automated lifecycle coverage includes starting mid-session, reconnect/resubscribe,
one and ten consumers, dense coalescing, atomic purple handoff, exact final state,
measured lap-counter/reset ordering, generation replacement, live/replay isolation,
different entries and session selections, global spoiler protection, source
inactivity, oversize failure, last-consumer cleanup and integration-store close.
Freeze and retain remain local card behavior: the backend receives no command and
generation changes still force a new snapshot before state can be shown again.

The checked-in transport profile uses 22 drivers, ten clients and forty UI updates
representing four deliveries per second for ten seconds. It measured a 7,420-byte
initial snapshot, 488-byte largest delta, 11,215 bytes per client over ten seconds
and 3.504 ms dispatch p95. Re-sending the complete equivalent status payload as a
simple sensor prototype required 288,440 bytes over the same updates. This is a
payload-only comparison and excludes Home Assistant's additional state-event
envelope, so it is conservative in favour of the sensor prototype. The WebSocket
path was 96.1 percent smaller and creates no additional Home Assistant state writes.

## Step 4 modular-card implementation

The modular field catalog exposes three status-only strips and three combined fields
that pair the existing S1, S2 or S3 time with its strip. A separate `minisectors`
module starts with driver plus the three strips. All six fields and the module use
the existing field ordering, duplication, module width, visibility, session and
driver/team focus controls. Two module instances retain independent UI choices.

The card opens one shared frontend subscription for each exact connection, entry,
source and session context while a visible module needs minisectors. The last
consumer releases it. Preview data never opens the live subscription. Sequence gaps
invalidate the local generation and use unsubscribe/resubscribe for a new snapshot;
unavailable minisectors do not prevent ordinary timing data from rendering.

Rendering preserves sparse source order and the observed segment count instead of
assuming one circuit length. Purple, green and yellow are accompanied by diamond,
circle and square markers. Reset, special, missing and unknown status stay neutral;
unknown labels retain the raw code. The legend states that the provider supplies
status only and that no minisector times are available or estimated. The inspiration
image's blue meaning is not copied.

## Step 5 delivery validation

The user guide documents all three presentations, known and neutral status
semantics, missing data, accessibility and the reason for keeping fast segment
updates outside Home Assistant sensor state. The modular configuration contract
and the earlier assessment now describe the implemented behavior.

Local validation covers the bounded source and WebSocket lifecycle, replay resets,
frontend reconnect and cleanup, visual editor choices, browser presentation,
generated catalog, documentation build, full Python suite and source-copy parity.
Legacy cards and entity-based automation data remain outside the feature diff.
Physical-device screen readers, a full real race weekend, external beta, published
CI and release are tracked in the manual handoff and are not claimed as local test
results.

The final local run passed 51 focused Python tests, 18 focused frontend unit tests,
15 focused Chromium flows, all 242 frontend unit tests, 44 Python and 50 Node
automation checks, Ruff, four documentation structure tests, 15 documentation
browser flows and all 1,644 integration tests in 388.83 seconds. HAdev reloaded the
integration with 66 entities, loaded and played the 2025 Abu Dhabi Grand Prix Race,
and restored the running modular dashboard after a full browser reload without
console warnings. Replay was stopped after the check and the Home Assistant log
reported no new issues. Eleven changed card assets match byte for byte across the
primary HAdev source, bundled HAdev integration and Git checkout.

The 2026-10-09 lap-boundary correction then passed 52 focused Python tests, all 242
frontend unit tests, Ruff, `git diff --check`, four documentation structure tests,
15 documentation browser flows and all 1,645 integration tests in 388.44 seconds.
HAdev reloaded the integration, played the 2025 Abu Dhabi race through the modular
card without browser warnings and returned replay to idle with year 2026 selected.
