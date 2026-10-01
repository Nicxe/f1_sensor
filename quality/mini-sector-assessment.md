# Mini-sector assessment for issue #702

Date: 2026-09-15

Mini-sectors are not part of the modular card release scope. The integration
already retains segment information in its history model, but it does not expose
a supported live mini-sector stream to dashboard cards.

The issue evidence confirms that `TimingData` sends per-driver segment status as
incremental data. A supported Home Assistant contract must preserve ordering,
merge snapshot and keyed delta shapes, identify lap resets before the delayed lap
counter update, recover after reconnects and avoid pushing a full-grid payload for
every small change. Status `2052` also remains intentionally unknown rather than
being assigned a guessed presentation.

The modular timing module therefore continues to show the three supported macro
sectors only. It does not render an empty or inferred mini-sector strip and does
not expose undocumented raw values. Adding mini-sectors later requires a separate
backend data contract, deterministic archive regressions for snapshot/delta/lap
transitions and reconnects, update-volume measurements, frontend semantics for
known and unknown status values, and real-session acceptance.

This is an explicit deferral, not a claim that the received data is unavailable.
It keeps the current card contract stable while issue #702 remains the feature
tracking point.
