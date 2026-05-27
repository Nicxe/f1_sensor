---
id: debug-logging
title: Debug Logging and Logs
---

Debug logging helps you collect useful information when F1 Sensor does not behave as expected.
Use this page when you are asked to provide logs for a GitHub issue, beta test, replay test, or F1TV Auth problem.

:::warning
Never share F1TV tokens, full `Authorization` headers, cookies, callback URLs, nonce values, or browser session data in an issue, screenshot, log excerpt, or discussion post.
Redact secrets before sharing logs.
:::

## Enable debug logging

Home Assistant can enable debug logging for an integration from the UI.
Use this flow first when you are collecting logs for an issue:

1. Open **Settings**.
2. Go to **Devices & services**.
3. Open **F1 Sensor**.
4. Select the three-dot menu.
5. Select **Enable debug logging**.

After debug logging is enabled, reproduce the issue before you disable it again.

:::tip
When you disable debug logging from the same menu, Home Assistant downloads a debug log file automatically.
Attach that file to the issue after you remove any secrets.
:::

## Enable debug logging with YAML

Use YAML only if the UI option is not available, if you need debug logging to start during Home Assistant startup, or if you are asked to keep debug logging enabled across a restart.

Add this to your Home Assistant `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.f1_sensor: debug
```

Restart Home Assistant after changing the logger configuration.

:::tip
Enable debug logging before you reproduce the issue.
Logs are most useful when they include the full sequence from setup, reload, or the failing action.
:::

## Reproduce the problem

After Home Assistant restarts:

1. Reproduce the issue you are testing or reporting.
2. Note the approximate time when it happened.
3. Note the installed F1 Sensor version.
4. Note whether the integration is running in **Live** mode or **Development** replay mode.
5. Note whether F1TV Auth was connected, expired, rejected, or not configured.

These details make it easier to match log entries to the behavior you saw.

## Incident detection reports

For false positive or missing on-track incident reports, include the same basic log package plus:

1. Session type and session name.
2. Driver or car number involved.
3. Approximate real-world time and, if relevant, broadcast time.
4. Current `sensor.f1_track_status` state.
5. Latest Race Control message around the incident.
6. The `f1_sensor_incident` event payload, if one fired.
7. Whether Live Delay, Replay Mode, No Spoiler Mode, or experimental F1TV Auth was active.
8. Whether Track Map showed live or replay `Position.z` data and whether `location.stale` was `true` or `false`.

Do not include raw F1TV tokens, authorization headers, browser session data, or large telemetry dumps.

## Find raw logs

Use Home Assistant raw logs if you need to copy a smaller log excerpt manually.

1. Open **Settings**.
2. Go to **System**.
3. Open **Logs**.
4. Select the three-dot menu in the top right corner.
5. Select **Show raw logs**.
6. Copy the relevant entries around the time the issue happened.

![Show raw logs](/img/raw_logs.png)

## What to include in an issue

When you create a GitHub issue, include:

1. The F1 Sensor version.
2. Your Home Assistant version.
3. Whether you are using a beta release.
4. Whether you are using Live mode, Development replay mode, or F1TV Auth.
5. What you expected to happen.
6. What actually happened.
7. Relevant debug log output with secrets removed.

Logs are often the key to understanding setup failures, token problems, replay behavior, and unexpected entity updates.

## Disable debug logging

Debug logging can generate a lot of log data.
Disable it when you are done testing.

If you enabled debug logging from the UI, return to **Settings** → **Devices & services**, open **F1 Sensor**, select the three-dot menu, and select **Disable debug logging**.
Home Assistant downloads the debug log file when debug logging is disabled.

If you enabled debug logging with YAML, remove the `custom_components.f1_sensor: debug` entry from `configuration.yaml`, then restart Home Assistant.
