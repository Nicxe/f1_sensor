# Legacy card deprecation decision

Decision date: 2026-09-17.

## Decision

Keep all existing F1 Sensor card types registered, selectable, loadable and
supported throughout the modular card's development and beta period. Do not hide,
deprecate or remove any legacy card in this delivery, and do not rewrite saved
dashboards automatically.

The modular card is currently an additional choice. Its conversion flow may create
a reviewable copy and preserve the exact original configuration, but that does not
make the modular result a verified replacement for every real dashboard.

## Reason

The coverage map has an explicit agent-verified status for all 23 registered cards
and the archive alias. Each has an implemented modular destination and automated
conversion evidence. Human semantic comparison, physical-device and
assistive-technology checks, real-session coverage, long-running multi-client
behavior and beta feedback are maintained separately in the external handoff
report and are not part of the completed agent goal.

Removing or hiding legacy choices before those checks would make the automated
migration sample carry more meaning than it proves and would reduce the safe
fallback available to existing users.

## Conditions for reconsideration

Reconsider deprecation only after handoff checks H1–H9 are documented against the
same release candidate, including:

- Representative real dashboards, custom sources and values outside the generated
  migration probe domains have been compared semantically.
- Device, accessibility, runtime, live-weekend and multi-client checks pass.
- A beta has collected enough real-installation feedback to identify unsupported
  configurations and recovery problems.
- Release documentation identifies any behavior that cannot be preserved and gives
  users a tested migration and rollback path.

## Future change classification

Hiding legacy cards from new selection while continuing to load and edit saved
cards would require its own documented product decision and beta validation.
Removing a registered type, stopping its resource delivery or making an existing
saved dashboard fail would be a breaking change and require explicit user
instructions and the corresponding major-release classification.

This decision can be revised later; it authorizes no removal in the current work.
