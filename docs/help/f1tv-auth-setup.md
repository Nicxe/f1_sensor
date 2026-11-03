---
id: f1tv-auth-setup
title: Connect optional F1TV access
description: Pair the Token Helper with Home Assistant, verify access, and renew an expiring live timing token.
---

F1TV Auth connects optional Formula 1 live timing access to F1 Sensor through the F1TV Token Helper.
Use it for Replay Mode and Formula 1 timing archives, or for extra live features such as Track Map, Pit Stops, Team Radio, Championship Prediction, formation start refinements and earlier incident candidates.

## Prerequisites

Before you start, make sure you have:

1. F1 Sensor installed in Home Assistant.
2. Access to Home Assistant logs if you need to troubleshoot.
3. A Formula 1 account. A free account has accessed the tested Replay Mode resources and live radio metadata; live car telemetry and positions were received only with the tested paid account. Check [current availability](/features/f1tv-auth#subscription-requirement) before choosing a feature.
4. Chrome or another Chromium-based browser.
5. The [F1TV Token Helper](https://chromewebstore.google.com/detail/f1tv-token-helper-beta/bbpgdcjohdjcechlffloekhpgdbjoafh) extension installed.


Enable debug logging before reporting issues.
See [Debug Logging and Logs](/help/debug-logging) for the recommended logging setup and log collection steps.

## How it works

Public live timing works without pairing. The Token Helper reads a short-lived authorization value from your own Formula 1 browser session and sends it only to your own Home Assistant pairing callback. Home Assistant does not ask for your Formula 1 username or password.

Extra live features need suitable account permissions and published data; pairing does not unlock every feed. After setup, verify public timing, token health and the particular feature you want.

## Availability

Use [data availability](/features/f1tv-auth#availability-matrix) to choose a feature. A free account has accessed the tested replay resources and live radio metadata. Live car telemetry and positions were received with the tested paid account, not the tested free account. These are observations, not guarantees for every paid plan. The [complete dated evidence](/features/f1tv-access-evidence) preserves the test windows and limitations.

Local token health, upstream acceptance, account permission and current publication are separate checks. Replay uses archive files separately from live feeds.

## Incident detection and F1TV Auth

Confirmed alerts work with public live timing. Authenticated car data can improve earlier candidate signals, and Track Map can add location context. See [Incident Detection](/features/incident-detection) before enabling early alerts.


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
4. Return to the original pairing tab, reopen the helper and select **Fetch**.
5. When the helper is ready, select **Send to Home Assistant**.

The helper stores only the Home Assistant pairing session temporarily while you sign in.
It does not store the F1TV token permanently.

Home Assistant should finish the pairing, save the live timing authorization value, and reload the integration.

## Step 3 - Understand token lifetime

F1TV tokens are short-lived.
They are usually valid for only a few days. F1 Sensor automatically tries to renew them during their final 24 hours, using the session already contained in the saved token. Home Assistant also attempts renewal if it starts with an expired token and a usable session. You can close your browser after pairing. Renewal is best effort; it does not guarantee permanent sign-in or uninterrupted access.

The underlying Formula 1 session has an observed lifetime of about 30 days from the original sign-in. Automatic token renewal does not extend that deadline, and Formula 1 can revoke the session earlier. When the session expires or is rejected, use the Home Assistant repair or Token Helper to sign in again and reconnect. Tokens without a usable session require manual renewal.

Temporary connection failures are retried with increasing delays. Token expiry monitoring continues while Home Assistant retries, so a failed request does not hide an expired token.

The integration exposes two helper sensors so you can monitor token health from Home Assistant:

```text
sensor.f1_f1tv_token_status
sensor.f1_f1tv_token_expires_at
```

Use `sensor.f1_f1tv_token_status` to see whether the token is locally well-formed and unexpired, expiring soon, expired, invalid, or rejected. A locally well-formed token is not proven authentic until Formula 1 accepts it during an upstream request. A valid status does not confirm every account permission or prove that a particular live feed is publishing data.
Use `sensor.f1_f1tv_token_expires_at` to see when the current token expires.

The integration also exposes two helper buttons when F1TV access is available:

```text
button.f1_refresh_f1tv_access
button.f1_clear_f1tv_access
```

Use `button.f1_refresh_f1tv_access` to request renewal. If a new browser sign-in is needed, it opens the existing Token Helper pairing notification. Temporary failures are retried automatically without asking you to sign in again.
Use `button.f1_clear_f1tv_access` to remove the saved token and return to public live timing. Replay Mode and Formula 1 archive media remain unavailable until access is connected again.

The saved token is part of the Home Assistant config entry and normally follows it into Home Assistant backups. Treat shared backups as credentials. If you suspect exposure, clear the saved token and revoke the Formula 1 browser session before pairing again.

When the token expires or is rejected, public live timing should continue to work.
Replay Mode and Formula 1 archive media need accepted account access. Additional live data also needs suitable account permissions and published updates.

## Step 4 - Verify public fallback first

Before relying on additional account access, confirm that public live timing still works.

During an active Formula 1 session, check that relevant public live entities receive current updates, such as:

```text
sensor.f1_track_status
sensor.f1_session_status
sensor.f1_race_control
sensor.f1_driver_positions
```

Then check the token-status sensor and your chosen additional feature. For Track Map, look for fresh car positions during track activity; an accepted token alone is not enough. Some feeds publish only when an event occurs or during a suitable session, so a quiet practice feed is not proof of an authentication problem.

## Troubleshooting

### The helper does not show Home Assistant pairing

Keep the pairing page as the active tab and open the helper again.
If that does not work, copy the full browser URL from the pairing page, open **Pairing link** in the helper, paste the URL, and select **Connect**.

### The helper opens but only manual export is available

Make sure you started **Connect F1TV access with Token Helper** from Home Assistant before opening the helper.

### Home Assistant rejects the pairing

Start a new pairing session in Home Assistant.
The old session may have expired, already been used, or been created before Home Assistant was restarted.

### The token is valid but an extra feature has no data

A valid token status checks local token health. Formula 1 must also accept the token, your account must have access to the required feed, and that feed must publish data for the session.

Compare the feature with the [availability matrix](/features/f1tv-auth#availability-matrix). Live car telemetry and positions were absent with the tested free account even while public timing and live radio metadata worked. The [dated live comparison](/features/f1tv-access-evidence#what-the-live-checks-establish) records the received prediction data and missing `PitStopSeries` details.

For Pit Stops, check counts and detail records separately. A reported count can update while stop times remain unknown; tyre stints do not fill those missing times. A later archive can contain detail records even when live delivery did not. See [Pit Stops](/entities/pit-stops) before treating missing detail as a token failure. An archive request failing also does not establish whether a live feed is available.

### Public live timing stops working

That is a bug.
F1TV auth failure should downgrade only the extra F1TV-authenticated live features.
Public live timing should continue without a token.
