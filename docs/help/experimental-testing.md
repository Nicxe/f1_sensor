---
id: experimental-testing
title: F1TV Auth Testing
---

F1TV Auth testing lets you validate authenticated live timing data with your own Formula 1 browser session.
Use this page when you are testing the F1TV Token Helper pairing flow, token expiry handling, and the fallback to public live timing.

:::danger[Test environment recommended]
Beta features can change quickly and may not be stable.
Use a separate Home Assistant test instance, development container, VM, or secondary setup when you test new F1TV Auth behavior.
:::

## What you are testing

F1 Sensor works without F1TV authentication by using public live timing streams.
F1TV Auth adds a short-lived live timing authorization value so the integration can test extra F1TV-authenticated streams during an active Formula 1 session.

The current beta flow uses Home Assistant pairing:

1. Install or update F1 Sensor `v4.3.0-beta.4` or later in Home Assistant.
2. Install **F1TV Token Helper BETA** from the [Chrome Web Store](https://chromewebstore.google.com/detail/f1tv-token-helper-beta/bbpgdcjohdjcechlffloekhpgdbjoafh).
3. Start **Connect F1TV access with Token Helper** in Home Assistant.
4. Open the pairing page from Home Assistant.
5. Open the helper extension, sign in to Formula 1 if needed, select **Fetch**, then select **Send to Home Assistant**.
6. Verify that public live timing still works and that F1TV-only live data is enabled when the token is valid.

:::info
This flow does not ask Home Assistant for your F1TV username or password.
The token is extracted from your own browser session by the separate helper and sent only to your own Home Assistant pairing callback.
:::

## Current limitations

This is still beta testing.
The feature is intended for users who are comfortable reading Home Assistant logs, reporting clear issues, and replacing short-lived tokens when needed.

| Area | Expected behavior |
| --- | --- |
| Public live timing | Continues to work without any token |
| F1TV token | Optional and sent through Home Assistant pairing |
| Token lifetime | Short-lived and must be replaced when expired |
| Token renewal | Not automatic |
| F1TV password | Never entered into Home Assistant |
| Helper | Separate Chrome or Chromium extension |
| Chrome Web Store | Published as an unlisted beta |
| Auth failure | Downgrades to public live timing |
| Auth-gated live data | Requires a valid token during live sessions |

The first authentication beta is intended to test these auth-gated live streams:

```text
CarData.z
Position.z
DriverRaceInfo
ChampionshipPrediction
PitStopSeries
```

In **Live Mode**, these streams should not be expected to update with public live timing alone.
They should be tested live only after you add a valid F1TV token.

Some auth-gated features also have replay support.
For example, Championship Prediction and Pit Stops can use the recorded session archive in **Replay Mode**, but they require F1TV authentication when you test them during a real live session.

If the token is missing, expired, or rejected, auth-gated live data should become unavailable or stop receiving F1TV-only updates while public live timing continues.

`Position.z` is auth-gated and is used by the Track Map pipeline. It can also provide optional location context for incident events, but raw X/Y/Z samples are not exposed as normal Home Assistant state attributes.

## Incident detection and F1TV Auth

Likely on-track incident detection works with public live timing and does not require F1TV Auth.

Experimental F1TV Auth can also test early-warning `candidate` signals from `CarData.z`, such as very low speed before a car is officially marked as stopped. These signals are correlated with flag or Safety Car context and should be treated as candidates, not proof of a crash. Public live timing must continue to work if the token is missing, expired, or rejected.

When `Position.z` and Track Map are active, incident events may include a compact `location` summary such as position status, sector, geometry source, and stale state. Location context can improve confidence or suppress obvious pit-lane false positives, but incident detection must still work without F1TV Auth.

## Prerequisites

Before you start, make sure you have:

1. A non-production Home Assistant instance.
2. F1 Sensor `v4.3.0-beta.4` or later installed.
3. Access to Home Assistant logs.
4. A Formula 1 account with the required F1TV access for live timing.
5. Chrome or another Chromium-based browser.
6. The [F1TV Token Helper BETA](https://chromewebstore.google.com/detail/f1tv-token-helper-beta/bbpgdcjohdjcechlffloekhpgdbjoafh) extension installed.

Enable debug logging before testing if you plan to report issues.
See [Debug Logging and Logs](/help/debug-logging) for the recommended logging setup and log collection steps.

## Step 1 - Install the beta version

Install F1 Sensor `v4.3.0-beta.4` or later through HACS.

1. Open **HACS** in Home Assistant.
2. Open **F1 Sensor**.
3. Select the three-dot menu.
4. Select **Redownload**.
5. Choose the latest beta version.
6. Restart Home Assistant after the installation completes.

After Home Assistant restarts, verify that the installed version is `v4.3.0-beta.4` or later.

## Step 2 - Install the helper from Chrome Web Store

Install **F1TV Token Helper BETA** from the Chrome Web Store:

```text
https://chromewebstore.google.com/detail/f1tv-token-helper-beta/bbpgdcjohdjcechlffloekhpgdbjoafh
```

The Chrome Web Store version is the recommended testing path.
You do not need to enable Chrome developer mode or load an unpacked extension for normal beta testing.

:::tip
Use the local developer installation only if you are working on the helper extension itself or testing an unpublished helper build.
The extension repository keeps that workflow documented in its README.
:::

## Step 3 - Start pairing from Home Assistant

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

## Step 4 - Send F1TV access to Home Assistant

Use the helper from the same browser where you sign in to Formula 1:

1. Keep the pairing page as the active tab.
2. Open the **F1TV Token Helper** extension popup.
3. If the helper says no token is available, select **Sign in** and sign in to Formula 1.
4. Return to the helper and select **Fetch**.
5. When the helper is ready, select **Send to Home Assistant**.

The helper stores only the Home Assistant pairing session temporarily while you sign in.
It does not store the F1TV token permanently.

Home Assistant should finish the pairing, save the live timing authorization value, and reload the integration.

## Step 5 - Understand token lifetime

F1TV tokens are short-lived.
They are usually valid for only a few days, so you should expect to repeat the helper flow and replace the saved token when it expires.

The integration exposes two helper sensors so you can monitor token health from Home Assistant:

```text
sensor.f1_f1tv_token_status
sensor.f1_f1tv_token_expires_at
```

Use `sensor.f1_f1tv_token_status` to see whether the token is valid, expiring soon, expired, invalid, or rejected.
Use `sensor.f1_f1tv_token_expires_at` to see when the current token expires.

The integration also exposes two helper buttons when experimental F1TV access is available:

```text
button.f1_refresh_f1tv_access
button.f1_clear_f1tv_access
```

Use `button.f1_refresh_f1tv_access` to start a new Token Helper pairing from Home Assistant. Use `button.f1_clear_f1tv_access` to remove the saved token and return to public live timing only.

When the token expires or is rejected, public live timing should continue to work.
Only the F1TV-authenticated live data needs a fresh token.

## Step 6 - Verify public fallback first

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

Make sure you are using F1 Sensor `v4.3.0-beta.4` or later and that you started **Connect F1TV access with Token Helper** from Home Assistant.
Older beta builds did not include the normal pairing flow.

### Home Assistant rejects the pairing

Start a new pairing session in Home Assistant.
The old session may have expired, already been used, or been created before Home Assistant was restarted.

### Public live timing stops working

That is a bug.
F1TV auth failure should downgrade only the extra F1TV-authenticated streams.
Public live timing should continue without a token.
