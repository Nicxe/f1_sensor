---
id: release-channels
title: Release Channels
---

F1 Sensor uses separate release channels so you can choose between stable releases, beta testing, and active development builds.
Most users should stay on the stable channel.

## Channel overview

| Channel | Best for | What to expect |
| --- | --- | --- |
| Stable | Normal Home Assistant installations | Tested releases promoted from beta |
| Beta | Test systems and users helping validate the next release | Pre-release builds that should be close to stable but may still contain bugs |
| Dev | Maintainers and development testing | All new unreleased changes from the active development branch |

:::warning
Do not use beta or dev builds as your only production Home Assistant installation. Use a separate test instance when you are validating new behavior.
:::

## Stable channel

Stable releases are published from the `main` branch.
This is the recommended channel for daily use, dashboards, automations, and household routines that need predictable behavior.

Install stable releases through [HACS](/getting-started/installation) or from the latest non-pre-release package on the GitHub releases page.

## Beta channel

Beta releases are published from the `beta` branch after changes have been promoted from `dev`.
Use beta when you want to validate the next release before it becomes stable.

Beta builds can include new features, changed behavior, and fixes that need real Home Assistant testing. Read the release notes before updating, and be ready to collect logs or switch back to stable if something affects your setup.

To install or update to beta through HACS:

1. Open **HACS** in Home Assistant.
2. Go to **Integrations**.
3. Open **F1 Sensor**.
4. Open the three-dot menu.
5. Select **Redownload**.
6. Enable **Show beta versions** if the beta release is not visible.
7. Select the latest beta version.
8. Restart Home Assistant after installation.

For testing guidance, see [Beta Testing](/help/beta-tester).

## Dev channel

The `dev` branch contains all active development work before it is promoted to beta.
It is where the newest changes land first.

Dev builds can change quickly, include incomplete behavior, or require maintainer instructions that do not apply to normal releases. Use dev only when you are developing the integration locally or when the maintainer explicitly asks you to test a specific unreleased change.

Normal users should not install directly from `dev`. Wait for a beta release if you want to help test new behavior with a safer upgrade path.

## Switch back to stable

If a beta or dev build causes problems, switch back to the latest stable release.

1. Open **HACS** in Home Assistant.
2. Go to **Integrations**.
3. Open **F1 Sensor**.
4. Select **Redownload**.
5. Choose the latest stable version instead of a beta version.
6. Restart Home Assistant.

If you installed files manually from a branch, replace them with the latest stable release archive from GitHub and restart Home Assistant.

## Reporting issues

When you report a problem, always include which release channel you are using.
For beta and dev testing, include the exact F1 Sensor version, Home Assistant version, whether F1TV Auth is configured, and whether the issue happens during live timing, Replay Mode, or normal static data updates.

See [Debug Logging and Logs](/help/debug-logging) before opening an issue.
