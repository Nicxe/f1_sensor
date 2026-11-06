---
id: card-data-api
title: Card data protocol
description: Entry-scoped discovery, versioned direct-data subscriptions, protection rules and lifecycle guarantees for F1 Sensor card clients.
---

This reference describes the modular card's direct data transport. Sensor states and attributes remain available when their entities are selected. [Card data](/features/card-data-and-sensors) is automatic and independent of sensor exposure. Module subscriptions acquire the shared data sources they need.

## Discover support

Send `f1_sensor/entities` through Home Assistant's authenticated WebSocket API. Each entry includes its existing entity mappings and additive `data_api` metadata: `protocol_version`, `supported`, `enabled`, `automatic`, `race_control_event`, `lap_history_version` and `configuration_required`. Current backends set `automatic: true`, list all supported generic areas in `enabled` and set `configuration_required: false`. Availability is reported separately for each data area; advertising a dataset does not grant live or authenticated access.

A client on an older backend without `data_api` uses existing entity discovery. A client with direct support chooses transport per data area. An error, protection block or missing response from an advertised direct transport does not authorize silent fallback to entity attributes.

## Subscribe

```json
{
  "id": 10,
  "type": "f1_sensor/data/subscribe",
  "entry_id": "YOUR_CONFIG_ENTRY_ID",
  "protocol_version": 1,
  "data_keys": ["driver_standings", "constructor_standings"]
}
```

The command acknowledges the subscription, sends its own initial snapshot for every requested area, then sends changed requested areas. There is no separate initial GET. Unsubscribe using Home Assistant's standard `unsubscribe_events` command. Unknown entries, unsupported areas, unloaded runtime return explicit errors. There is no upgrade-acknowledgement error in the automatic backend.

## Read envelopes

Every snapshot includes `protocol_version`, `entry_id`, `dataset`, `source`, `context`, `generation`, `revision`, `status`, `reason`, `timestamps` and `payload`. `payload` contains processed `state` and `attributes`. Status is `ready`, `stale`, `loading`, `unavailable`, `blocked`, `unsupported` or `closed`.

Source is `static`, `live` or `replay`. Live context identifies the session, replay generation, live delay and qualifying part. Qualifying context arrives immediately; clients hide timing from an earlier part until its matching update arrives. No Spoiler Mode hides the part metadata while protection is active. Static context includes known season and round. Timestamps distinguish known observation time from receipt time; unknown observation time is `null`. Clients must not label receipt time as source freshness.

Replay source and session identity follow the active input, including catch-up before transport playback starts. Selecting another session in the replay controls does not relabel data from the transport still running. When replay owns the input but its index is unknown, session-bound data waits for a verified identity.

A generation retires earlier work after reload, session changes or replay rebuilds. Revision orders changes within the generation. Clients discard older revisions and retired generations, and stop using data after `closed`. Do not combine live areas from different generations.

Static areas publish on change. General live data is limited to one publication per second per area. Context and protection changes are delivered immediately. No Spoiler Mode and Live Delay apply to initial snapshots, caches and reconnects as well as later updates.

Use explicit `status` and `reason` values when describing availability. `source_inactive` alone does not prove ordinary session downtime. `source_update_failed` marks a stale source update; the age of a rarely changing message does not. A `ready` payload can contain unknown individual values without making its other fields unavailable.

Championship prediction attributes include `session_key`, `session_type` and `prediction_status` (`waiting_for_session`, `not_applicable`, `waiting_for_prediction` or `ready`). Prediction data requires an identified Race or Sprint. Older payloads can lack these additive attributes and retain their existing availability handling.

Replay status attributes include `download_error_code` and `archive_identity`. Known load codes are `archive_identity_conflict` and `cache_normalization_incompatible`; an unknown code keeps the generic load-error presentation. Archive identity status `missing` means there was insufficient evidence to verify the recording, not a known conflict. Both fields are also available on the existing replay status sensor.

## Lap history for Race Trace

Race Trace uses the existing `driver_positions` and `session_context` direct subscriptions. Discovery advertises `data_api.lap_history_version: 1`; the `driver_positions` payload also includes `attributes.lap_history_version: 1` and `attributes.lap_history_session_type`. The latter is the known session type, such as `Race` or `Sprint`, or `null` while unknown. This additive lap-history version is separate from the envelope's `protocol_version`.

Each driver keeps the existing `laps` and `completed_laps` fields and adds `lap_metadata`, keyed by lap number. For example, part of the `driver_positions` attributes can contain:

```json
{
  "lap_history_version": 1,
  "lap_history_session_type": "Race",
  "drivers": [
    {
      "racing_number": "4",
      "completed_laps": 12,
      "laps": { "12": "1:30.000" },
      "lap_metadata": {
        "12": { "association": "confirmed", "reason": null }
      }
    }
  ]
}
```

| Association | Meaning | Reason |
| --- | --- | --- |
| `confirmed` | The lap number and recorded time were explicitly paired in the same timing observation. | `null` |
| `inferred` | The accumulator used a retained lap number or derived a number because the update did not provide one. | `retained_lap_number` or `missing_lap_number` |
| `ambiguous` | A merged snapshot does not establish the pairing, or a changed time cannot be safely associated with that lap. | `snapshot_unverified` or `ambiguous_correction` |

A confirmed pair can come from `NumberOfLaps` and `LastLapTime.Value` in the same raw `TimingData` row, or `LapNumber` and `LapTime` in the same raw `TimingAppData` stint update. A merged initial snapshot alone does not prove that those fields arrived together. Live and replay use the same association rules.

Metadata belongs to the currently stored `laps` value. An unchanged restored value can retain its previous evidence; a changed value cannot inherit confirmation from an older time. Confirmation establishes the association, not official validity, sector consistency or suitability for pace analysis. The separate strategy quality fields keep those meanings.

Race Trace accepts only confirmed, positive, finite durations at lap numbers no greater than the driver's known `completed_laps`, capped at lap 500. Missing metadata remains uncertain. Only lap numbers with recognised association metadata establish the observed range; retained legacy times without that evidence cannot extend the axis after a viewing-context reset. Inferred and ambiguous observations can extend that range as gaps. Normalised duplicate lap keys count once when their times agree; conflicting aliases without a revision order break the cumulative series. An accepted replacement snapshot recalculates the series rather than adding another lap.

Clients require matching entry, source, session, generation and delay context across the direct timing and session envelopes, and apply their revision and spoiler checks before calculation. Race Trace is available only for an identified Race or Sprint. Unknown session type waits; a known different type is not applicable. An older backend without the advertised contract is unsupported for this measure. Temporarily absent data on a supported backend is pending and must not trigger fallback to entity history.

The card calculates integer-millisecond differences from its fixed anchor before formatting seconds or cropping the displayed lap range. It does not use strategy pace filters, infer a simultaneous race gap or request an additional upstream feed. See [Lap history chart](/cards/cards-overview#lap-chart-module) for the formula, selection and gap behavior.

### Optional event markers

The Lap history chart option `event_markers` defaults to `[]`. Supported values are `pit`, `sc`, `vsc` and `red_flag`. Enabling a marker type acquires the existing shared analysis subscription for that entry. It does not open another upstream F1 connection. When no enabled module needs analysis, the card releases its subscription. Existing source access requirements still apply, including authenticated live `PitStopSeries` data.

Markers have a separate additive contract. The direct `driver_positions` attributes include `race_trace_observation`; the analysis response includes `race_trace_markers`. Both contain `version: 1`, `status`, `reason` and `context`. Timing uses `timing_as_of`; markers use `as_of` and an `events` array, limited to 500 events. Missing marker support leaves the cumulative lap-time graph usable.

Markers are projected from the existing shared timeline, whose 500-event retention limit counts **all** event categories, including each driver's completed laps. This is not a separate allocation of 500 marker events. Eviction can remove earlier pit stops and flag transitions before the race ends while the independent lap-history accumulator still contains those laps. The marker snapshot must not be described as complete race history.

The shared observation context contains:

| Field | Meaning |
| --- | --- |
| `token` | Opaque identity of the consumed viewing context. |
| `entry_id`, `source`, `session_id` | Installation, live/replay source and session identity. |
| `source_epoch` | Source or replay-rebuild epoch. |
| `delay_epoch` | Delay-change epoch; returning to the same delay value does not reuse an older context. |
| `delay_seconds` | Delay associated with those observations. |

Observation cursors contain a positive integer `sequence`, a non-negative integer `source_time_ms` and `time_domain`, either `utc` or `replay_offset`. Sequence describes shared raw-frame observation order, not an analysis revision or a publication count. Source time is UTC epoch milliseconds or replay-offset milliseconds according to its domain. An example timing observation is:

```json
{
  "version": 1,
  "status": "ready",
  "reason": null,
  "context": {
    "token": "context-token",
    "entry_id": "entry-one",
    "source": "replay",
    "session_id": "session-one",
    "source_epoch": "rebuild-two",
    "delay_epoch": 2,
    "delay_seconds": 0
  },
  "timing_as_of": {
    "sequence": 120,
    "source_time_ms": 12000,
    "time_domain": "replay_offset"
  }
}
```

The timing barrier comes from actually consumed raw timing input. Merged initial snapshots, the current replay position, receipt time and publication revisions do not establish that proof. Clients require matching observation contexts as well as the base chart's direct-data context and spoiler checks.

The entire marker snapshot waits when its `as_of` is ahead of `timing_as_of` in sequence or source time, or the time domains differ. Each event carries `context_token` and `observation_cursor`, bounded by the snapshot's `as_of`. Each reference-driver anchor has its own `observation_cursor`, bounded by the event's cursor. A backdated event cannot borrow a later completion observation. Products retain independent revisions; comparing their revision numbers is not a substitute for these checks.

Each normalized event has a stable `event_id`, a positive integer `revision`, `kind`, `phase`, `source` and optional `description`:

| Kind | Required anchor | Phases |
| --- | --- | --- |
| `pit` | `driver_number`, integer `lap_number`, `anchor_type: "driver_lap"`; source `PitStopSeries`. | `point` |
| `sc`, `vsc`, `red_flag` | `reference_anchors[driver_number]` with integer `lap_number`, `basis: "confirmed_completed"` and its observation cursor; source `TrackStatus`. | `start`, `ending`, `end` |

Lap numbers must be within 1–500. Global markers select only the chart's explicit reference driver and mean **after that driver's observed completed lap**. They do not use the leader's lap, infer a crossing time or describe whole-lap exposure. The `ending` phase is an announcement, not an observed clear condition. Missing anchors remain unplotted; missing endpoints are not inferred. The client displays separate event points rather than constructing intervals or `end_lap` values.

For each event identity, the newest revision replaces the previous event before selection and display-range filtering. An unsafe correction must not leave an older point visible. Conflicting candidates at the same revision are ambiguous, and invalid event provenance vetoes that identity rather than reviving an older revision. Marker projection does not modify cumulative values, fill timing gaps or apply strategy pace filters. A point can appear in the separate event strip at a lap with a missing delta, without inventing a vertical value.

Waiting for the timing barrier can be prolonged when a flag or pit event arrives during an interruption or after the last raw timing update. Report this as pending marker data while preserving the base graph. Delay changes, source changes, rewind, disconnect and unknown or active spoiler protection must clear unsafe markers and their details; retained or frozen views do not bypass these rules.

## Shared ownership and special transports

Runtime owns neutral calculation models, coordinator listeners, persisted session accumulators and time-dependent updates. Existing providers, HTTP caches, storage and the shared LiveBus perform collection. No hidden sensor entities are created for card data. Multiple clients share each data area and underlying coordinator demand; removing the final client releases its on-demand listeners. Necessary incremental history retains background demand within existing session windows when live timing is enabled. Static sources warm lazily, with parent sources ready before derived forecasts, documents or circuit history. Closing a card releases on-demand polling and dependency listeners; an active sensor retains its own demand.

Automatic backends advertise `race_control_event: "f1_sensor_race_control_data"` for entry-addressed live log updates. This card channel does not opt an installation into public automation events. Public `f1_sensor_race_control_event` delivery retains its previous sensor/legacy demand. Older backends without this field use the existing event path.

Map, analysis, minisectors, archive and telemetry retain their specialized APIs. Race Control log reads and the `clear_race_control_log` action accept `entry_id` for sensor-free use, or the existing `entity_id`. Supply one address.

## Upgrade metadata

Config-entry schema 4.4 preserves sensor configuration and does not require an upgrade choice. `card_data_notice_version` in entry data records that one-time information was shown. It never controls operation. New installations start with this information already acknowledged.

Old `card_data_features` and `data_choice_version` values are retained as inert metadata when present; neither restricts card access nor blocks setup. `exposed_sensor_keys`, when present, remains the authoritative sensor allowlist. Existing legacy sensor-selection semantics are preserved when that allowlist is absent. Voluntary sensor reductions require review before registry entries are removed.

Older backends without `data_api` use the entity path. Older direct backends can still advertise restricted data or `configuration_required`; clients keep their existing fail-closed handling for those versions. New backend operation does not depend on that legacy state.
