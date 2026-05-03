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

The current testing flow uses Home Assistant pairing:

1. Enable the development-gated controls in the integration code.
2. Install or update F1 Sensor `v4.3.0-beta.2` or later in Home Assistant.
3. Install the separate [F1TV Token Helper](https://github.com/Nicxe/f1tv-token-helper) as a local browser extension while the Chrome Web Store beta is under review.
4. Start **Connect F1TV access with Token Helper** in Home Assistant.
5. Open the pairing page from Home Assistant.
6. Open the helper extension, sign in to Formula 1 if needed, select **Fetch**, then select **Send to Home Assistant**.
7. Verify that public live timing still works and that F1TV-only live data is enabled when the token is valid.

:::info
This flow does not ask Home Assistant for your F1TV username or password.
The token is extracted from your own browser session by the separate helper and sent only to your own Home Assistant pairing callback.
:::

## Current limitations

This is not normal beta testing.
It is a development-gated authentication test path for advanced users who are comfortable editing local integration files, reading Home Assistant logs, and replacing short-lived tokens.

The current experimental scope is:

| Area | Expected behavior |
| --- | --- |
| Public live timing | Continues to work without any token |
| F1TV token | Optional and sent through Home Assistant pairing |
| Token lifetime | Short-lived and must be replaced when expired |
| Token renewal | Not automatic |
| F1TV password | Never entered into Home Assistant |
| Helper | Separate Chrome or Chromium extension |
| Chrome Web Store | Submitted for unlisted beta review, not available until approved |
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

1. A non-production Home Assistant instance.
2. F1 Sensor `v4.3.0-beta.2` or later installed.
3. Access to Home Assistant logs.
4. A Formula 1 account with the required F1TV access for live timing.
5. Chrome or another Chromium-based browser for the helper extension.
6. Node.js 22 or newer for local helper builds while the Chrome Web Store beta is under review.
7. The [F1TV Token Helper](https://github.com/Nicxe/f1tv-token-helper) repository cloned or unpacked locally.

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
The test build must expose development controls before the pairing option appears in setup or reconfigure.

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

## Step 2 - Confirm the integration exposes pairing controls

After Home Assistant restarts:

1. Open **Settings**.
2. Go to **Devices & services**.
3. Open **F1 Sensor**.
4. Select **Reconfigure**.
5. Confirm that **Connect F1TV access with Token Helper** is available.

Manual `Bearer <JWT>` paste remains available only as an advanced fallback in development-gated builds.
The normal test flow should use the helper pairing option.

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
Never share a raw token, a full `Authorization` header, cookies, nonce values, callback bodies, or browser session data in an issue, screenshot, log excerpt, or discussion post.
Redact secrets before sharing logs.
:::

## Step 4 - Build the F1TV Token Helper

The token helper is a separate local extension while the Chrome Web Store beta is under review.
It sends your token only to the Home Assistant callback URL created by the pairing flow and does not send your token to a project server.

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

1. Open Chrome.
2. Go to `chrome://extensions`.
3. Enable **Developer mode**.
4. Select **Load unpacked**.
5. Select the local `dist/` folder inside your F1TV Token Helper repository.

After the Chrome Web Store beta is approved, install the helper from the store link instead of using **Load unpacked**.

## Step 6 - Start pairing from Home Assistant

In Home Assistant:

1. Open **Settings**.
2. Go to **Devices & services**.
3. Open **F1 Sensor**.
4. Select **Reconfigure**.
5. Select **Connect F1TV access with Token Helper**.
6. Select **Open website** when Home Assistant shows the external step.

Home Assistant opens the [F1TV Token Helper pairing page](/help/f1tv-token-helper).
Keep that tab open and active before opening the extension.

Pairing sessions are short-lived.
If the helper says the pairing expired, return to Home Assistant and start the pairing again.

## Step 7 - Send F1TV access to Home Assistant

Use the helper from the same browser where you sign in to Formula 1:

1. Keep the pairing page as the active tab.
2. Open the **F1TV Token Helper** extension popup.
3. If the helper says no token is available, select **Sign in** and sign in to Formula 1.
4. Return to the helper and select **Fetch**.
5. When the helper is ready, select **Send to Home Assistant**.

The helper stores only the Home Assistant pairing session temporarily while you sign in.
It does not store the F1TV token permanently.

Home Assistant should finish the pairing, save the live timing authorization value, and reload the integration.

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
```

Then confirm that F1TV-only data becomes available only after a valid helper pairing.

## Troubleshooting

### The helper does not show Home Assistant pairing

Keep the pairing page as the active tab and open the helper again.
If that does not work, copy the full browser URL from the pairing page, open **Pairing link** in the helper, paste the URL, and select **Connect**.

### The helper opens but only manual export is available

Make sure you are using F1 Sensor `v4.3.0-beta.2` or later and that you started **Connect F1TV access with Token Helper** from Home Assistant.
Older beta builds did not include the pairing callback flow.

### Home Assistant rejects the pairing

Start a new pairing session in Home Assistant.
The old session may have expired, already been used, or been created before Home Assistant was restarted.

### Public live timing stops working

That is a bug.
F1TV auth failure should downgrade only the extra F1TV-authenticated streams.
Public live timing should continue without a token.
