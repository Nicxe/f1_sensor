---
id: f1tv-auth
title: Data availability and F1TV access
description: Compare public live timing with authenticated live, archive media and Replay Mode before connecting F1TV access.
---

F1 Sensor works with public live timing without a Formula 1 account token. Connecting a free or paid account can add access, but token validity, account permissions and the data published for a session are separate checks.

## Availability matrix

The live columns describe F1 Sensor's current behavior and the accounts tested during United States FP1 on 23 October and sampled race windows on 25 October 2026. They are observations rather than guaranteed subscription tiers; every live feature also needs Formula 1 to publish suitable data. The tests used separate observation windows, not an uninterrupted recording of every feed for the whole race.

| Feature or data | Without an account token | Free account with accepted token | Paid account with accepted token |
| --- | --- | --- | --- |
| Session state, Track Status, Safety Car, Race Control, weather | Public live timing | Public live timing | Public live timing |
| Driver classification, timing and tyres | Public live timing | Public live timing | Public live timing |
| Confirmed incident detection | Uses public live timing | Uses public live timing | Uses public live timing |
| Live Track Map and incident location context | Not available live | Position data not received by the tested account | Fresh position data verified with the tested account |
| Car telemetry for earlier incident candidates and formation-start refinement | Not available live | Car telemetry not received by the tested account | Fresh car telemetry verified; each feature still needs a suitable session |
| Team Radio | Connect access to enable it in F1 Sensor | Live clip metadata verified | Published clip metadata received |
| Pit counts | Public source counts can exist, but the Pit Stops entity and card dataset require connected access | Count updates verified through Home Assistant | Count updates verified through Home Assistant |
| Pit-lane duration | Connect access to enable Pit Stops in F1 Sensor | Alternative duration feed not tested with this account | One live duration record verified; broad coverage remains unverified |
| Stationary pit-stop time | Connect access to enable Pit Stops in F1 Sensor | No live `PitStopSeries` details observed | No live `PitStopSeries` details observed |
| Championship Prediction | Connect access to enable it in F1 Sensor | No feed observed in the sampled race comparison | Prediction data received during the race |

Replay Mode uses archived data separately. A free account has accessed the tested replay resources, including archived telemetry and radio; playback still depends on the selected session's available files.

### What the live checks establish

Public timing delivered fresh updates without a token and with both accounts during practice and the race. Sequential free/paid comparisons received live car telemetry (`CarData.z`) and positions (`Position.z`) only with the tested paid account. During the race, that account also received fresh driver race information (`DriverRaceInfo`) and prediction data (`ChampionshipPrediction`). This supports observed access differences for these accounts and windows; it does not establish a rule for every paid plan or a change introduced on that date.

Team Radio metadata also arrived with the free account. Anonymous live radio metadata was not tested, and the integration continues to request this feed only with connected access. A separate audio-file check succeeded without an account token and with both accounts; that does not establish anonymous access to live radio metadata. Playback through Home Assistant still requires Home Assistant authentication.

Pit counts advanced during the race, but no `PitStopSeries` detail payload was received in the saved comparison windows with either account. This distinction is separate from token health: a count does not establish a stop's lap, stationary time or pit-lane time. The cause of the missing live detail feed remains unverified. See [Pit Stops](/entities/pit-stops) for count semantics and the available fields.

A separate paid-account diagnostic received one `PitLaneTimeCollection` record containing a pit-lane duration and lap. Its duration matched the same event in the later detail archive, but contained no stationary time. Checks across 57 archived stops support that distinction. F1 Sensor uses this feed as a best-effort live [pit-lane-time fallback](/entities/pit-stops#pit-lane-time-during-live-sessions), retaining the observations it receives. The single captured live event does not prove complete live coverage or access with a free or anonymous account.

## How F1TV Auth changes live timing

There are three useful access situations to consider:

| Access situation | What to expect |
| --- | --- |
| No account token | Public live timing, schedules, standings and confirmed incident alerts continue to work. Formula 1 archive discovery and downloads need connected access. |
| Free Formula 1 account | Public timing remains available. The tested account also received live radio metadata and accessed published archive resources, but did not receive live car telemetry or positions. |
| Paid Formula 1 access | Public timing remains available. The tested account also received live car telemetry and positions. Other feeds still depend on account permissions and session publication. |

F1TV Auth is optional for public live timing. If a token is missing, expired, invalid or rejected, F1 Sensor falls back to public live timing. Replay discovery, replay downloads, archive telemetry and archive team radio media need accepted account access.

## What works without F1TV Auth

Public live timing covers the normal live features most dashboards and automations use:

| Public live data | Examples |
| --- | --- |
| Session state | Current session, session status, session clocks, lap count |
| Track and race control | Track status, Safety Car, Race Control messages, track limits, investigations |
| Weather | Live trackside weather during active sessions |
| Driver timing | Driver list, classification, timing app data, tyres, tyre statistics, top three |
| Incident detection | Confirmed likely stopped-car or on-track incident alerts from public timing, Track Status, and Race Control context |

The public stream classification is unchanged. Publication varies by session: for example, no lap-count feed was observed during the FP1 checks. A quiet event-driven feed does not by itself mean authentication has failed.

## What F1TV Auth can add during live sessions

Connected access lets F1 Sensor request additional live feeds for Track Map, Pit Stops, Team Radio, Championship Prediction, formation-start refinement and earlier incident candidates. An accepted token does not guarantee all these features: your account must receive the required feed, and Formula 1 must publish relevant updates during the session.

## Account and access requirements {/* #subscription-requirement */}

Connect your Formula 1 account through the [F1TV Token Helper](/help/f1tv-token-helper). On 21 October 2026, both a free account and a paid account accessed the archive index and the same 18 tested timing streams; the anonymous archive-index request returned 401. A paid subscription was not required for those verified archive resources.

This is archived timing data, not F1 TV video replay access. It does not guarantee every file for every session: individual post-session `PitStopSeries` requests on 23 and 25 October returned 403, which was inconclusive about publication timing or access. The saved Singapore and United States race detail archives were available for later parser checks on 26 October. This does not identify when they became available or change the earlier live observations. Live feeds and archive files need separate checks. Formula 1 can change access or publication on its unofficial timing API.

:::info
A locally valid token is not proof that Formula 1 accepts it. An accepted token is not proof of every account permission, and a permitted feed can remain quiet when no relevant data is published.
Public live timing continues if connected access is missing, expired, invalid or rejected.
:::

## Token Helper and renewal

The recommended way to connect F1TV Auth is the [F1TV Token Helper](/help/f1tv-token-helper). The helper reads a short-lived live timing token from your own browser session and sends it to your own Home Assistant pairing callback.

Home Assistant does not ask for your Formula 1 password. When your token contains a usable Formula 1 session, F1 Sensor automatically requests a replacement as the token enters its final 24 hours. Temporary connection failures are retried automatically. Your browser does not need to stay open. Renewal is best effort and does not guarantee permanent sign-in or uninterrupted access.

The underlying session has an observed lifetime of about 30 days from the original Formula 1 sign-in. Replacing the short-lived token does not extend that session. Formula 1 can also revoke it earlier. When the session can no longer renew access, Home Assistant shows a repair that leads you back to Token Helper. Tokens without a usable session continue to use manual pairing.

The integration can check locally that a JWT is well-formed and unexpired. This does not prove that the token is authentic. F1TV access is confirmed only after Formula 1 accepts it during an upstream request; receiving a particular live feed is a further check.

For the practical setup workflow, see [F1TV Auth Setup](/help/f1tv-auth-setup).

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
