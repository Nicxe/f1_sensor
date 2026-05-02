---
id: experimental-testing
title: Experimental Testing
---

Experimental testing is for power users who want to validate F1TV authenticated live timing before it is made available as a normal user-facing feature.
Use this page when you are testing the development-gated authentication flow, the F1TV Token Helper, token expiry handling, and the fallback to public live timing.
:::danger[Test environment only]
Do not test F1TV authentication in your production Home Assistant instance.
Use a separate Home Assistant test instance, development container, VM, or secondary setup where restarts, broken entities, and temporary configuration changes are acceptable.
:::

## What you are testing

F1 Sensor works without F1TV authentication by using public live timing streams.
The experimental authentication flow adds a short-lived F1TV live timing authorization value so the integration can test extra live timing streams during an active Formula 1 session.

The current manual testing flow is:

1. Enable the development-gated controls in the integration code
2. Install or update the test copy of F1 Sensor in Home Assistant
3. Install the separate [F1TV Token Helper](https://github.com/Nicxe/f1tv-token-helper) repository as a local browser extension
4. Sign in to Formula 1 in your browser
5. Copy the `Bearer <JWT>` value from the helper
6. Paste the value into F1 Sensor
7. Verify that public live timing still works and that F1TV-only live data is enabled when the token is valid
:::info
This flow does not ask Home Assistant for your F1TV username or password.
The token is extracted from your own browser session by the separate helper and pasted manually into the integration.
:::

## Current limitations

This is not normal beta testing.
It is a development-gated authentication test path for advanced users who are comfortable editing local integration files, reading Home Assistant logs, and replacing short-lived tokens.

The current experimental scope is:

| Area | Expected behavior |
| --- | --- |
| Public live timing | Continues to work without any token |
| F1TV token | Optional and manually pasted as `Bearer <JWT>` |
| Token lifetime | Short-lived and must be replaced when expired |
| Token renewal | Not automatic |
| F1TV password | Never entered into Home Assistant |
| Helper | Separate local repository and browser extension |
| Auth failure | Downgrades to public live timing |
| Auth-gated live data | Requires a valid token during live sessions |

The first authentication MVP is intended to test these auth-gated live streams:

```text
CarData.z
DriverRaceInfo
ChampionshipPrediction
TeamRadio
PitStopSeries
```

In **Live Mode**, these streams should not be expected to update with public live timing alone.
They should be tested live only after you add a valid F1TV token.

Some auth-gated features also have replay support.
For example, Championship Prediction, Team Radio, and Pit Stops can use the recorded session archive in **Replay Mode**, but they require F1TV authentication when you test them during a real live session.

If the token is missing, expired, or rejected, auth-gated live data should become unavailable or stop receiving F1TV-only updates while public live timing continues.

`Position.z` has been observed as auth-gated, but it is intentionally excluded from the first test build because it is high frequency and the integration does not currently use it.

## Prerequisites

Before you start, make sure you have:

1. A non-production Home Assistant instance
2. F1 Sensor `4.3.0-beta.1` or later installed
3. Access to Home Assistant logs
4. A Formula 1 account with the required F1TV access for live timing
5. Chrome or another Chromium-based browser for the helper extension
6. Node.js 22 or newer for building the helper
7. The [F1TV Token Helper](https://github.com/Nicxe/f1tv-token-helper) repository cloned or unpacked locally

The helper can be stored anywhere on your computer.
In the examples below, replace this path with the folder where you cloned or unpacked the repository:

```text
/path/to/f1tv-token-helper
```

The integration test copy may be in your Home Assistant custom components directory, for example:

```text
/Volumes/config/custom_components/f1_sensor
```

Adjust the paths if your test environment uses different locations.

## Step 1 - Enable the development gate

F1TV authentication is hidden behind the development UI gate.
The test build must expose development controls before the auth field appears in setup or reconfigure.

Open the integration `const.py` file in the Home Assistant test copy:

```text
custom_components/f1_sensor/const.py
```

Set the development gate to `True`:

```python
ENABLE_DEVELOPMENT_MODE_UI = True
```

Save the file and restart Home Assistant.
:::warning
Released builds should keep this gate disabled.
For normal users, `ENABLE_DEVELOPMENT_MODE_UI` should be `False` so the experimental auth UI and runtime behavior stay hidden.
:::

## Step 2 - Confirm the integration exposes auth controls

After Home Assistant restarts:

1. Open **Settings**
2. Go to **Devices & services**
3. Open **F1 Sensor**
4. Select **Reconfigure**
5. Confirm that the live timing authorization field is visible

The field may be named **Live timing authorization value**.
It expects a value in this exact format:

```text
Bearer <JWT>
```

Do not include the `Authorization:` prefix in this field.

Leave the field empty if you want to keep using public live timing only.

## Step 3 - Enable debug logging

Enable debug logging before testing so you can verify connection behavior and report useful issues.

Add this to `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.f1_sensor: debug
```

Restart Home Assistant after changing the logger configuration.

When you collect logs, use **Settings** → **System** → **Logs**, then select **Show raw logs** from the menu.
:::warning
Never share a raw token, a full `Authorization` header, cookies, or browser session data in an issue, screenshot, log excerpt, or discussion post.
Redact secrets before sharing logs.
:::

## Step 4 - Build the F1TV Token Helper

The token helper is a separate local tool.
It does not write directly to Home Assistant and does not send your token to a project server.
Use the [F1TV Token Helper repository](https://github.com/Nicxe/f1tv-token-helper) for the latest setup instructions and source code.

From the helper repository:

```bash
cd /path/to/f1tv-token-helper
npm ci
npm run build
```

The built extension is created in the `dist/` folder inside your local helper folder:

```text
/path/to/f1tv-token-helper/dist
```

## Step 5 - Load the helper in Chrome

Load the helper as a local unpacked extension:

1. Open Chrome
2. Go to `chrome://extensions`
3. Select **Load unpacked**
4. Select the local `dist/` folder inside your F1TV Token Helper repository

## Step 6 - Fetch a token

Use the helper from the same browser where you sign in to Formula 1:

1. Sign in to the official Formula 1 site in Chrome
2. Open the **F1TV Token Helper** extension popup
3. Select **Fetch**
4. Confirm that the helper shows a valid token status and expiry
5. Select **Copy HA value**

The copied value should look like this:

```text
Bearer <JWT>
```

The helper may also support downloading a text file containing the full header:

```text
Authorization: Bearer <JWT>
```

Use only the `Bearer <JWT>` part in Home Assistant.

## Step 7 - Add the token to F1 Sensor

In Home Assistant:

1. Open **Settings**
2. Go to **Devices & services**
3. Open **F1 Sensor**
4. Select **Reconfigure**
5. Paste the copied `Bearer <JWT>` value into **Live timing authorization value**
6. Keep **Operation mode** set to **Live** when testing real live timing
7. Submit the form

Restart Home Assistant if your test build does not reload the integration automatically.

The integration should store the token as an authorization value and use it only when the development gate allows auth transport.

## Step 8 - Understand token lifetime

F1TV tokens are short-lived.
They are usually valid for only a few days, so you should expect to repeat the helper flow and replace the saved token when it expires.

The integration should tell you when the saved token needs attention.
It also exposes two helper sensors so you can monitor token health from Home Assistant:

```text
sensor.f1_f1tv_token_status
sensor.f1_f1tv_token_expires_at
```

Use `sensor.f1_f1tv_token_status` to see whether the token is valid, expiring soon, expired, invalid, or rejected.
Use `sensor.f1_f1tv_token_expires_at` to see when the current token expires.

When the token expires or is rejected, public live timing should continue to work.
Only the F1TV-authenticated live data needs a fresh token.

## Step 9 - Verify public fallback first

Before relying on auth-only behavior, confirm that public live timing still works.

During an active or upcoming Formula 1 session, check that public live entities continue to update, such as:

```text
sensor.f1_track_status
sensor.f1_session_status
sensor.f1_race_control
sensor.f1_driver_positions
sensor.f1_current_tyres
```

Public live timing must keep working even when:

1. No token is configured
2. The token expires
3. The token is rejected by the live timing server

This fallback behavior is the most important part of the test.

## Step 10 - Verify auth behavior

With a valid token configured and `ENABLE_DEVELOPMENT_MODE_UI = True`, start live timing during a real session and check for these behaviors:

1. The integration connects to live timing without logging the token
2. The connection uses the saved `Bearer <JWT>` value internally
3. Public live entities continue to update
4. F1TV-only live data becomes available where the current build supports it
5. The token status entity or diagnostics show only safe metadata, such as status and expiry

Depending on the test build, useful entities may include:

```text
sensor.f1_f1tv_token_status
sensor.f1_f1tv_token_expires_at
sensor.f1_championship_prediction_drivers
sensor.f1_championship_prediction_teams
sensor.f1_team_radio
sensor.f1_pitstops
binary_sensor.f1_formation_start
```

Entity IDs can differ if your installation already has renamed entities.
Search for the `f1_` suffix or the documented entity name in **Settings** → **Devices & services** → **Entities**.

For auth-gated entities, verify three states separately:

1. They are unavailable in public live timing without a valid token
2. Replay-capable entities can update during Replay Mode
3. They can update during auth-enabled live timing when Formula 1 provides the streams

## Step 11 - Test token replacement

Tokens are short-lived.
When Home Assistant reports that the token is expiring soon, expired, invalid, or rejected, generate a new one with the helper and replace the old value.

1. Sign in to Formula 1 again if needed
2. Open the helper popup
3. Select **Fetch**
4. Select **Copy HA value**
5. Open **F1 Sensor** → **Reconfigure**
6. Paste the new `Bearer <JWT>` value
7. Submit the form

The integration should accept a valid replacement token and continue without requiring a full reinstall.

If the token is expired, malformed, missing an expiry, or too close to expiry, the form should reject it with a clear error.

## Step 12 - Test clearing auth

Clearing the token should return the integration to public live timing.

1. Open **F1 Sensor** → **Reconfigure**
2. Select **Clear live timing authorization value**
3. Submit the form
4. Restart or reload the integration if needed
5. Confirm that public live timing still works

After clearing the token, F1TV-only live data should become unavailable, but normal public live timing should continue.

## Step 13 - Test auth failure handling

Use this only in a disposable test setup.
The goal is to confirm that broken auth does not break public live timing.

You can test with:

1. An expired token
2. A malformed `Bearer` value
3. A valid-looking token that the live timing server rejects

Expected behavior:

| Failure | Expected result |
| --- | --- |
| Missing token | Public live timing only |
| Malformed token | Form error or invalid token status |
| Expired token | Repair or reauth prompt, public live timing continues |
| Server rejects token | Downgrade to public live timing and request token refresh |

When auth fails, auth-gated live entities such as Championship Prediction, Team Radio, and Pit Stops should become unavailable or stop receiving F1TV-only updates, while public live timing continues.
The integration must not retry aggressively, spam repairs, or make the full integration unavailable because auth fails.

## Step 14 - Review diagnostics safely

Diagnostics are useful for testing, but they must not expose secrets.

When you download diagnostics or copy debug information, confirm that the output does not contain:

```text
Bearer
Authorization
subscriptionToken
login-session
JWT payload that identifies you
F1TV email or account identity
```

Safe diagnostics may include:

```text
auth_configured: true
status: valid
status: expired
expires_at: 2026-04-23T12:34:56+00:00
used_for_live_timing: true
```

If diagnostics expose the token or any browser session value, stop testing and report it privately.

## Good test report format

When reporting experimental auth results, include:

1. F1 Sensor version or branch
2. Home Assistant version
3. Whether `ENABLE_DEVELOPMENT_MODE_UI` was `True` or `False`
4. Whether you used Live mode or Development replay mode
5. Whether the token was valid, expired, rejected, or cleared
6. Which entities updated and which stayed unavailable
7. Relevant redacted log lines
8. The exact session you tested, such as race, qualifying, sprint, or practice

Do not include the token, full auth header, cookies, screenshots of the helper showing secrets, or unredacted diagnostics.

## What must always remain true

Use this checklist before you mark an auth test as successful:

1. F1 Sensor still works without F1TV authentication
2. Public live timing still updates without a token
3. A valid token enables only the supported F1TV-auth test behavior
4. An expired or rejected token downgrades to public live timing
5. No token appears in logs, diagnostics, entities, repairs, or issue reports
6. The helper does not store the token permanently or send it to a project server
7. Home Assistant never asks for your F1TV password

For broader beta participation, see [BETA-test](/help/beta-tester).
For replay-based testing without F1TV authentication, see [Replay Mode](/features/replay-mode).
