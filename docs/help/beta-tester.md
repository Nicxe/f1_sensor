---
id: beta-tester
title: Test a beta release
description: Test a prerelease in a separate Home Assistant setup and report useful results.
---

Beta testing lets you try new F1 Sensor behavior before it is part of a stable release.
Use this page if you want to test beta versions, report problems clearly, or help validate fixes.

:::danger[Important recommendations]
Beta versions are not guaranteed to be stable.
Do not install beta versions in your production Home Assistant instance.
Use a separate test environment, development instance, or secondary Home Assistant setup where restarts and temporary issues are acceptable.
:::

For the difference between stable, beta, and dev builds, see [Release Channels](/getting-started/release-channels).

## What it means to be a beta tester

As a beta tester, you help by:

1. Testing new features before they are officially released.
2. Identifying bugs, regressions, or unexpected behavior.
3. Providing feedback and improvement suggestions.
4. Creating clear and well-described GitHub issues.
5. Following up on reported issues and retesting fixes when needed.

You do not need to be a developer, but it helps if you have basic Home Assistant knowledge, can read logs, and can describe problems with enough context to reproduce them.

## Install a beta version

Follow the [beta installation steps](/getting-started/release-channels#beta-channel), restart Home Assistant, then verify the installed version. Read the release notes to choose what to test and enable debug logging before reproducing an issue.

## Beta vs dev

Beta is the normal prerelease testing channel. Dev contains active unreleased work and should be used only for development or a specific maintainer-led test. Follow [release channels](/getting-started/release-channels) for the full distinction and [switching back to stable](/getting-started/release-channels#switch-back-to-stable) for a reliable fallback.

## What to test

When validating a beta release, focus on the changed areas listed in its release notes and the behavior that affects real dashboards, automations, and update flows:

1. Installing and updating beta releases through Marketplace or HACS, and restoring a backup when returning to stable.
2. Public live timing without F1TV Auth.
3. Optional F1TV Auth setup and renewal through the Token Helper.
4. Track Map behavior in live sessions and Replay Mode.
5. Incident Detection wording, confidence, and notification timing.
6. Replay Mode controls, including the seek bar and 30-second buttons.
7. The bundled F1 Sensor card after restart and browser reload.

## Enable debug logging

Debug logs are often required when you report beta issues.
Follow [Debug Logging and Logs](/help/debug-logging) before reproducing the problem.

## Developer mode testing

Developer mode lets maintainers run the integration with a local recording of live timing data. It is useful for repeatable testing without waiting for an active Formula 1 session.

:::warning[Development builds only]
Developer mode is not part of the normal beta testing path. Its configuration fields are hidden unless the installed build enables the developer interface.

Use normal [Replay Mode](/features/replay-mode) when you want to watch a completed session. Use [Developer Mode with Replay Dumps](/help/developer-mode) only when you are developing F1 Sensor or the maintainer asks you to test a specific dump.
:::

The Developer mode guide explains when to use this mode, why it is useful for regression testing, how local dump timing behaves, and how to return the integration to Live mode.

## Report issues and feedback

Clear issue reports are essential for improving the integration.
Use GitHub Issues for bugs, errors, and broken functionality:

```text
https://github.com/Nicxe/f1_sensor/issues
```

Use GitHub Discussions for questions, ideas, and general feedback:

```text
https://github.com/Nicxe/f1_sensor/discussions/190
```

:::info
Using the correct channel helps keep development focused and easier to follow.
:::

## Write a useful issue

Include the exact F1 Sensor and Home Assistant versions, release channel, public/authenticated live or replay/developer mode, steps to reproduce, expected behavior and actual behavior. Add token health, live timing diagnostics and Track Map status when relevant. The [complete log and report checklist](/help/debug-logging#what-to-include-in-an-issue) lists the fields and redaction requirements.

Screenshots, screen recordings or dashboard examples help when they show sensor states, timing or a visual problem. Follow up when the maintainer asks you to retest a fix or provide more detail.

## Test incident detection

Use neutral wording and record the alert phase, confidence, driver, session and timing context. Follow the [complete beta incident checklist](/help/debug-logging#beta-incident-checks) when collecting logs; it includes pit-lane and Track Map context and the incident event payload.
