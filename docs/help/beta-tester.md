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
7. Choose the latest beta version from the version list.
8. Confirm and complete the installation.
9. Restart Home Assistant.

After installation, verify the installed version under the integration details.
Enable debug logging if you plan to report issues.

:::warning
Always read the release notes before updating to a beta release.
Beta releases may include unfinished behavior, temporary limitations, or changes that need extra validation.
:::

## Enable debug logging

Debug logs are often required when you report beta issues.
Follow [Debug Logging and Logs](/help/debug-logging) before reproducing the problem.

## Test Development replay mode

Development replay mode lets you run the integration with recorded live timing data.
This is useful for testing dashboards, automations, and entity behavior without waiting for an active Formula 1 session.

### About replay dumps

A replay dump is a real-time recording of a live session.
Timing between events is preserved, so a full replay can take up to three hours to complete.

The replay usually starts with a `pre` session phase where weather and session metadata update continuously.
When the session goes `live`, cars begin running and other sensors such as tyres, laps, and timing become active.

:::tip[Replay dumps]
You can find replay dumps in the [F1 Sensor repository](https://github.com/Nicxe/f1_sensor/tree/develop/replay_dumps).
:::

### Step 1 - Enable replay mode

1. Open **Home Assistant**.
2. Go to **Settings**.
3. Open **Devices & services**.
4. Select **F1 Sensor**.
5. Select **Configure**.
6. Set **Operation mode** to **Development**.
7. Enter the absolute file path to your replay dump in **Replay dump path**.
8. Submit the form.

The integration reloads immediately.

![Development mode](/img/dev_mode.png)

### Step 2 - Verify replay mode

Check the logs for this message:

```text
Starting F1 Sensor in development replay mode
```

If the replay dump path is missing, invalid, or unreadable, the integration falls back to the live SignalR connection.

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
3. Whether you are running Live mode or Development replay mode.
4. Whether you are using a beta release or F1TV Auth.
5. A clear description of the problem.
6. What you expected to happen.
7. What actually happened.
8. Relevant debug logs from [Debug Logging and Logs](/help/debug-logging).

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
7. Whether Live Delay, Replay Mode, No Spoiler Mode, or experimental F1TV Auth was active.

Use neutral language in reports. The feature is intended to detect likely stopped cars and on-track incidents, not guaranteed crashes.
