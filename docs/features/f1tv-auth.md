---
id: f1tv-auth
title: Data availability and F1TV access
description: Compare public live timing with authenticated live, archive media and Replay Mode before connecting F1TV access.
---

F1 Sensor works with public live timing without a Formula 1 account token. Connecting a free or paid account can add access, but token validity, account permissions and the data published for a session are separate checks.

## Availability matrix

| You want | Account access | What to expect |
| --- | --- | --- |
| Schedules, standings and public live timing | No token | Session status, flags, Race Control, weather, driver timing, tyres and confirmed incident alerts |
| Extra live features | Connected access plus permission for the feed | Track Map, Pit Stops, Team Radio, Championship Prediction and extra telemetry depend on the account and published session data |
| Recorded timing with Replay Mode | Accepted Formula 1 account access | A free account worked for the tested archive resources; files and coverage vary by session |
| Published historical classifications | No F1TV Auth | Use [Historical archive](/features/historical-results); it does not start Replay Mode |

For the complete feature-by-feature free/paid comparison, read the [dated availability matrix](/features/f1tv-access-evidence#availability-matrix). Live positions and telemetry were received with the tested paid account and not the tested free account; this is not a guarantee for every paid plan. Pit counts, pit-lane duration and stationary time have separate coverage.

### What the live checks establish

[Read the full live observations](/features/f1tv-access-evidence#what-the-live-checks-establish), including quiet feeds, tested windows, radio metadata and partial pit timing. An accepted token alone never proves that a particular feed is available.

## How F1TV Auth changes live timing

Public live timing continues when access is missing, expired, invalid or rejected. Connected access adds requests for extra live feeds and for Formula 1 archive discovery, downloads, telemetry and Team Radio media. Your account still needs permission and the session must publish suitable data.

## What works without F1TV Auth

Public live timing covers the normal live features most dashboards and automations use:

| Public live data | Examples |
| --- | --- |
| Session state | Current session, session status, session clocks, lap count |
| Track and race control | Track status, Safety Car, Race Control messages, track limits, investigations |
| Weather | Live trackside weather during active sessions |
| Driver timing | Driver list, classification, timing app data, tyres, tyre statistics, top three |
| Incident detection | Confirmed likely stopped-car or on-track incident alerts from public timing, Track Status, and Race Control context |

A quiet event-driven feed does not by itself mean authentication has failed. See the [public-feed observations](/features/f1tv-access-evidence#public-feed-observations) for the tested session limits.

## What F1TV Auth can add during live sessions

Connected access lets F1 Sensor request additional live feeds for Track Map, Pit Stops, Team Radio, Championship Prediction, formation-start refinement and earlier incident candidates. An accepted token does not guarantee all these features: your account must receive the required feed, and Formula 1 must publish relevant updates during the session.

## Account and access requirements {/* #subscription-requirement */}

A free Formula 1 account accessed the tested timing archives, including Replay Mode resources. Live car positions and telemetry arrived only with the tested paid account. These findings do not establish every subscription plan or guarantee every archive file. [Read the dated account and archive checks](/features/f1tv-access-evidence#archive-access-checks).

Timing archives do not provide F1 TV video replay access. Formula 1 can change permissions or publication on its unofficial timing API.

:::info[Three separate checks]
A locally valid token is not proof that Formula 1 accepts it. An accepted token is not proof of every account permission, and a permitted feed can remain quiet when no relevant data is published. Public live timing continues if connected access is missing, expired, invalid or rejected.
:::

## Token Helper and renewal

[Connect optional F1TV access](/help/f1tv-auth-setup) using the Token Helper. It reads a short-lived token from your own browser session and sends it to your own Home Assistant pairing callback; Home Assistant does not ask for your Formula 1 password.

F1 Sensor attempts renewal during the token's final 24 hours while its saved session is usable. Temporary connection failures are retried and your browser can be closed. Renewal is best effort: the observed underlying session lifetime is about 30 days from sign-in and can be revoked earlier. Tokens without a usable session need manual pairing.

See [token lifetime, status and renewal controls](/help/f1tv-auth-setup#step-3---understand-token-lifetime) for the complete workflow and authenticity checks.

## Privacy and safety

F1 Sensor stores only the authorization value needed for live timing. Diagnostics and public issue reports should never include tokens, full `Authorization` headers, cookies, callback URLs, nonce values, or browser session data.

The saved authorization value is part of the Home Assistant config entry and normally follows that entry into Home Assistant backups. Before sharing a backup, treat it as containing credentials. Use `button.f1_clear_f1tv_access` to remove the saved value and revoke the Formula 1 browser session if you suspect exposure.

Downloaded diagnostics can include redacted token health and live timing activity. They should not include secrets or high-frequency telemetry.

## Limitations

- Replay Mode and archive access require accepted Formula 1 account access. A free account worked for the tested archive resources; individual files can still be unavailable or rejected.
- Automatic renewal requires a usable session in the saved token. You still need Token Helper when that session expires or is revoked.
- Live car telemetry and positions were verified with the tested paid account, not every subscription plan. They were absent with the tested free account.
- Live driver race information and prediction data were received with the tested paid account during the race. A prediction snapshot does not by itself prove continuously changing predictions.
- Detailed Pit Stops depend on the fields actually received. Reported counts, pit-lane duration and stationary time have separate coverage; live stationary time remains unverified.
- Replay Mode uses the same saved authorization as authenticated live features, but archive access does not prove live-feed access.

## Related pages

- [Track Map](/features/track-map)
- [Incident Detection](/features/incident-detection)
- [Replay Mode](/features/replay-mode)
- [F1TV Token Helper](/help/f1tv-token-helper)
- [F1TV Auth Setup](/help/f1tv-auth-setup)
- [Diagnostics](/entities/diagnostics)
