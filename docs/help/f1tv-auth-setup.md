---
id: f1tv-auth-setup
title: F1TV Auth Setup
---

F1TV Auth connects optional Formula 1 live timing access to F1 Sensor through the F1TV Token Helper.
Use this page when you want live Track Map, Pit Stops, Championship Prediction, formation start refinements, or earlier incident candidates during an active Formula 1 session.

## How it works

F1 Sensor works without F1TV Auth by using public live timing.
F1TV Auth adds a short-lived live timing authorization value so extra F1TV-authenticated features can update when Formula 1 publishes the needed data.

The normal pairing flow uses Home Assistant and the F1TV Token Helper:

1. Install or update F1 Sensor in Home Assistant.
2. Install **F1TV Token Helper** from the [Chrome Web Store](https://chromewebstore.google.com/detail/f1tv-token-helper-beta/bbpgdcjohdjcechlffloekhpgdbjoafh).
3. Start **Connect F1TV access with Token Helper** in Home Assistant.
4. Open the pairing page from Home Assistant.
5. Open the helper extension, sign in to Formula 1 if needed, select **Fetch**, then select **Send to Home Assistant**.
6. Verify that public live timing still works and that F1TV live data is available when the token is valid.

:::info
This flow does not ask Home Assistant for your F1TV username or password.
The token is extracted from your own browser session by the separate helper and sent only to your own Home Assistant pairing callback.
:::

## Availability

| Area | Expected behavior |
| --- | --- |
| Public live timing | Continues to work without any token |
| F1TV token | Optional and sent through Home Assistant pairing |
| Token lifetime | Short-lived and must be replaced when expired |
| Token renewal | Not automatic |
| F1TV password | Never entered into Home Assistant |
| Helper | Separate Chrome or Chromium extension |
| Auth failure | Downgrades to public live timing |
| Extra live data | Requires a valid token during live sessions |

F1TV Auth can add live features such as:

```text
Live Track Map
Pit Stops during live sessions
Championship Prediction during live sessions
Formation start improvements
Earlier incident candidates
```

In **Live Mode**, these features should not be expected to update with public live timing alone.
They can update during live sessions after you add a valid F1TV token and Formula 1 publishes the required data.

Some F1TV Auth features also have replay support.
For example, Championship Prediction and Pit Stops can use the recorded session archive in **Replay Mode**, but they require F1TV Auth during a real live session.

If the token is missing, expired, or rejected, extra live data becomes unavailable or stops receiving F1TV-only updates while public live timing continues.

## Incident detection and F1TV Auth

Likely on-track incident detection works with public live timing and does not require F1TV Auth.

F1TV Auth can add early-warning `candidate` signals from extra live car data, such as very low speed before a car is officially marked as stopped.
These signals are correlated with flag or Safety Car context and should be treated as candidates, not proof of a crash.
Public live timing must continue to work if the token is missing, expired, or rejected.

When Track Map is active, incident events may include a compact `location` summary such as position status, sector, and stale state.
Location context can improve confidence or suppress obvious pit-lane false positives, but incident detection must still work without F1TV Auth.

## Prerequisites

Before you start, make sure you have:

1. F1 Sensor installed in Home Assistant.
2. Access to Home Assistant logs if you need to troubleshoot.
3. A Formula 1 account with the required F1TV access for live timing.
4. Chrome or another Chromium-based browser.
5. The [F1TV Token Helper](https://chromewebstore.google.com/detail/f1tv-token-helper-beta/bbpgdcjohdjcechlffloekhpgdbjoafh) extension installed.

Enable debug logging before reporting issues.
See [Debug Logging and Logs](/help/debug-logging) for the recommended logging setup and log collection steps.

## Step 1 - Start pairing from Home Assistant

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

## Step 2 - Send F1TV access to Home Assistant

Use the helper from the same browser where you sign in to Formula 1:

1. Keep the pairing page as the active tab.
2. Open the **F1TV Token Helper** extension popup.
3. If the helper says no token is available, select **Sign in** and sign in to Formula 1.
4. Return to the helper and select **Fetch**.
5. When the helper is ready, select **Send to Home Assistant**.

The helper stores only the Home Assistant pairing session temporarily while you sign in.
It does not store the F1TV token permanently.

Home Assistant should finish the pairing, save the live timing authorization value, and reload the integration.

## Step 3 - Understand token lifetime

F1TV tokens are short-lived.
They are usually valid for only a few days, so you should expect to repeat the helper flow and replace the saved token when it expires.

The integration exposes two helper sensors so you can monitor token health from Home Assistant:

```text
sensor.f1_f1tv_token_status
sensor.f1_f1tv_token_expires_at
```

Use `sensor.f1_f1tv_token_status` to see whether the token is valid, expiring soon, expired, invalid, or rejected.
Use `sensor.f1_f1tv_token_expires_at` to see when the current token expires.

The integration also exposes two helper buttons when F1TV access is available:

```text
button.f1_refresh_f1tv_access
button.f1_clear_f1tv_access
```

Use `button.f1_refresh_f1tv_access` to start a new Token Helper pairing from Home Assistant.
Use `button.f1_clear_f1tv_access` to remove the saved token and return to public live timing only.

When the token expires or is rejected, public live timing should continue to work.
Only the F1TV-authenticated live data needs a fresh token.

## Step 4 - Verify public fallback first

Before relying on auth-only behavior, confirm that public live timing still works.

During an active or upcoming Formula 1 session, check that public live entities continue to update, such as:

```text
sensor.f1_track_status
sensor.f1_session_status
sensor.f1_race_control
sensor.f1_driver_positions
```

Then confirm that F1TV-only data becomes available after a valid helper pairing.

## Troubleshooting

### The helper does not show Home Assistant pairing

Keep the pairing page as the active tab and open the helper again.
If that does not work, copy the full browser URL from the pairing page, open **Pairing link** in the helper, paste the URL, and select **Connect**.

### The helper opens but only manual export is available

Make sure you started **Connect F1TV access with Token Helper** from Home Assistant before opening the helper.

### Home Assistant rejects the pairing

Start a new pairing session in Home Assistant.
The old session may have expired, already been used, or been created before Home Assistant was restarted.

### Public live timing stops working

That is a bug.
F1TV auth failure should downgrade only the extra F1TV-authenticated live features.
Public live timing should continue without a token.
