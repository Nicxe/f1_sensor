# Legacy card deprecation decision

Decision date: 2026-09-17.

Current project entry point:
[`F1_SENSOR_NYA_KORT_START_HAR.md`](/Users/niklas/GitHub/F1_SENSOR_NYA_KORT_START_HAR.md).

## Decision

Deprecate the existing single-purpose F1 Sensor card types for new dashboards and
direct new documentation and product development to `custom:f1-sensor-card`.
Keep every existing type registered, selectable and loadable throughout the
modular card's development and migration period so saved dashboards continue to
work. Do not remove a legacy type or rewrite a saved dashboard automatically.

The modular conversion flow creates a reviewable draft and preserves the exact
original configuration. Deprecation communicates the intended direction; it does
not claim that every real dashboard has already completed manual semantic
comparison or remove the user's safe fallback.

## Reason

The coverage map has an explicit agent-verified status for all 23 registered cards
and the archive alias. Each has an implemented modular destination and automated
conversion evidence. Human semantic comparison, physical-device and
assistive-technology checks, real-session coverage, long-running multi-client
behavior and beta feedback are maintained separately in the external handoff
report and are not part of the completed agent goal.

Removing legacy choices before those checks would make the automated migration
sample carry more meaning than it proves and would reduce the safe fallback
available to existing users. Deprecation itself does not remove that fallback.

## Conditions for reconsideration

Reconsider removal or hiding of legacy choices only after handoff checks H1–H9 are
documented against the same release candidate, including:

- Representative real dashboards, custom sources and values outside the generated
  migration probe domains have been compared semantically.
- Device, accessibility, runtime, live-weekend and multi-client checks pass.
- A beta has collected enough real-installation feedback to identify unsupported
  configurations and recovery problems.
- Release documentation identifies any behavior that cannot be preserved and gives
  users a tested migration and rollback path.

## Future change classification

Hiding deprecated cards from new selection while continuing to load and edit saved
cards requires its own documented product decision and beta validation. Removing
a registered type, stopping its resource delivery or making an existing saved
dashboard fail is a breaking change and requires explicit user instructions and
the corresponding major-release classification.

This decision can be revised later; deprecation authorizes no removal in the
current work.
