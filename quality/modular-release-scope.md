# Modular card release scope

This document defines the user-facing scope for a future beta release of the
modular F1 Sensor live data card. It is a local release draft, not evidence that
a beta or stable release has been published.

## Proposed semantic-release text

`feat: **Add a modular live data card for tailored F1 dashboards**`

The live data card can now build focused F1 views from presets and selectable
modules, with a visual editor, accessible timing signals, replay-aware controls
and exact recovery of the original configuration during migration. Existing
card types remain supported, and conversion creates a reviewable copy instead
of rewriting dashboards automatically. This development version is not yet a
full replacement: physical-device and screen-reader checks, manual migration
parity, extended live-session testing and beta feedback are still required.

## Included development scope

- One `custom:f1-sensor-card` type with presets for a race weekend, session,
  selected driver, weather, results and an empty custom layout.
- Selectable modules for overview, calendar, timing, Race Control, tyres, pit
  stops, incidents, weather, results, standings, progression, archive, replay,
  documents, map, timeline, strategy, battles and recorded-lap telemetry.
- Visual editing of modules, order, fields, profiles, filters, focus, session
  context, style, density, typography, logos, flags, tyres and timing signals.
- Explicit missing, stale, disconnected, retained, frozen, estimated and
  spoiler-protected data states.
- Shared Live Delay and spoiler controls that respect the integration boundary;
  previews do not start data, replay or integrations actions.
- Conversion of the 23 registered legacy cards and the archive alias to a
  reviewable modular copy, while retaining the exact original configuration for
  restoration.
- Local user, accessibility and migration guides for development builds.

## Not yet accepted for release

- Manual keyboard, enlarged-text, mobile and relevant screen-reader checks on
  representative physical devices.
- Manual semantic comparison of legacy behavior for custom sources and values
  outside the generated migration domains.
- Full real-data acceptance for tyres, pit stops, weather, FIA documents,
  investigations and track limits.
- A complete practice, qualifying, sprint and race weekend, plus long-running
  reconnect, replay, focus and multi-client checks.
- CI attached to the future published commit, external beta feedback, final
  release-package/cache verification and the stable-release decision.

## Explicit exclusions

The release does not rewrite existing dashboards automatically, remove or hide
the legacy cards, add independent replay engines per card, expose new live
mini-sector data, or support arbitrary external data sources. Deprecation of
legacy cards requires a separate decision after the open acceptance work.

The public modular-card guides deliberately describe development builds and the
same remaining limitations. The release text above must be revised if the
delivered scope changes before a beta is published.
