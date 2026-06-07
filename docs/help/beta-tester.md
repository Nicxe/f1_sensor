---
id: beta-tester
title: Beta Testing
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

To test the latest beta version, install it through HACS by redownloading the integration and selecting the beta release.

1. Open **Home Assistant**.
2. Open **HACS**.
3. Go to **Integrations**.
4. Open **F1 Sensor**.
5. Select the three-dot menu in the top right corner.
6. Select **Redownload**.
7. Enable **Show beta versions** if the beta release is not visible.
8. Choose the latest beta version from the version list.
9. Confirm and complete the installation.
10. Restart Home Assistant.

After installation, verify the installed version under the integration details.
Enable debug logging if you plan to report issues.

:::warning
Always read the release notes before updating to a beta release.
Beta releases may include unfinished behavior, temporary limitations, or changes that need extra validation.
:::

## Beta vs dev

The beta channel contains changes that have been promoted from `dev` for pre-release testing.
This is the preferred channel for normal beta testers.

The `dev` branch contains all active unreleased work. It can include changes that have not yet been prepared for beta and may require maintainer-specific instructions. Use dev only when you are developing F1 Sensor locally or when the maintainer asks you to test a specific unreleased change.

If you need a reliable fallback, switch back to the latest stable release through HACS by using **Redownload** and selecting the latest non-beta version.

## What to test

When validating a beta release, focus on the changed areas listed in its release notes and the behavior that affects real dashboards, automations, and update flows:

1. Installing and switching between stable and beta through HACS.
2. Public live timing without F1TV Auth.
3. Optional F1TV Auth setup and renewal through the Token Helper.
4. Track Map behavior in live sessions and Replay Mode.
5. Incident Detection wording, confidence, and notification timing.
6. Replay Mode controls, including the seek bar and 30-second buttons.
7. Bundled Live Data Cards after restart and browser reload.

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

When creating an issue, include:

1. The exact F1 Sensor version.
2. Your Home Assistant version.
3. Whether you are running public live timing, F1TV Auth live timing, Replay Mode, or Developer mode with a replay dump.
4. Whether you are using a beta release.
5. A clear description of the problem.
6. What you expected to happen.
7. What actually happened.
8. The state of `sensor.f1_f1tv_token_status` if live auth is involved.
9. The `sensor.f1_live_timing_mode` attributes if live timing is involved and the diagnostic entity is present.
10. Track Map status, source, and stale state if the issue involves Track Map or incident location.
11. Relevant debug logs from [Debug Logging and Logs](/help/debug-logging).

Screenshots, screen recordings, or dashboard examples are helpful when they show sensor states, timing behavior, or visual problems.

As a beta tester, you may be asked to test a proposed fix, verify a new release, or provide more details.
Following up on your own issues helps close them faster.

## Test incident detection

When testing likely on-track incident detection, focus on whether the wording, confidence, and timing make sense from a user perspective.

For each report, note:

1. Session type: Race, Sprint, Qualifying, Practice, or Testing.
2. Driver or car number.
3. Whether the alert was `candidate`, `confirmed`, `updated`, or `cleared`.
4. Confidence value: `low`, `medium`, or `high`.
5. Track Status and Race Control context at the time.
6. Whether the driver was in pit lane, leaving the pit lane, or stopped on track.
7. Whether Live Delay, Replay Mode, No Spoiler Mode, or F1TV Auth was active.
8. Whether Track Map had live or replay car positions.
9. The Track Map status, source, and stale state if visible.
10. The `f1_sensor_incident` event payload for the relevant `incident_id`, including `location` when present.

Use neutral language in reports. The feature is intended to detect likely stopped cars and on-track incidents, not guaranteed crashes.
