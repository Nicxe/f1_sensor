# Mini-sector assessment for issue #702

Date: 2026-10-09

Issue #702 is implemented locally for the modular card as status blocks without
minisector times. This changes the earlier 2026-09-15 deferral after the required
backend contract, bounded state, shared delivery and frontend semantics were added.
It does not by itself place the feature in a published release scope.

The issue evidence confirms that `TimingData` sends per-driver segment status as
incremental data. The supported contract preserves source indexes, merges initial
lists and sparse keyed changes, clears stale state at lap and session boundaries,
recovers after reconnects and avoids a full-grid update for every segment change.

The corrected lap-transition evidence shows that `NumberOfLaps` advances about four
seconds before the atomic segment reset. The implementation therefore retains the
completed strip across the counter update and changes it only when the source supplies
the reset statuses, including any first segment already recorded for the new lap.

The modular Timing module offers three status-only fields and three fields that
combine an existing sector time with its minisector strip. A separate Minisectors
module uses the same fields and delivery resource. All choices are optional and
per module; existing sector fields and automatic profiles remain unchanged.

The supported status meanings are 2051 overall best, 2049 personal best and 2048
recorded. Purple, green and yellow are paired with diamond, circle and square
markers. Yellow is not described as slower than the previous lap. Reset, 2064 and
unknown codes stay neutral, with raw unknown codes retained for diagnosis.

The implementation uses the existing TimingData input, keeps current-lap state
within strict bounds and publishes sparse session-scoped WebSocket changes only to
visible modular-card consumers. It creates no minisector sensor and no additional
Home Assistant state or Recorder history. The measured transport profile and full
contract are recorded in [minisector-contract.md](./minisector-contract.md).

Local implementation and automated validation are complete through step 5 of the
minisector plan. Physical-device accessibility checks, full real-weekend coverage,
external beta, published CI and release remain manual or external acceptance work.
