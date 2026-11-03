---
id: f1tv-access-evidence
title: F1TV access checks and evidence
description: Read the dated account comparisons, live-feed observations and archive limits behind the F1 Sensor availability guide.
toc_max_heading_level: 3
---

These are observations from particular accounts and session windows, not guaranteed subscription tiers. Use the [data availability guide](/features/f1tv-auth) to choose a feature or [connect access](/help/f1tv-auth-setup).

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


## What the live checks establish

Public timing delivered fresh updates without a token and with both accounts during practice and the race. Sequential free/paid comparisons received live car telemetry (`CarData.z`) and positions (`Position.z`) only with the tested paid account. During the race, that account also received fresh driver race information (`DriverRaceInfo`) and prediction data (`ChampionshipPrediction`). This supports observed access differences for these accounts and windows; it does not establish a rule for every paid plan or a change introduced on that date.

Team Radio metadata also arrived with the free account. Anonymous live radio metadata was not tested, and the integration continues to request this feed only with connected access. A separate audio-file check succeeded without an account token and with both accounts; that does not establish anonymous access to live radio metadata. Playback through Home Assistant still requires Home Assistant authentication.

Pit counts advanced during the race, but no `PitStopSeries` detail payload was received in the saved comparison windows with either account. This distinction is separate from token health: a count does not establish a stop's lap, stationary time or pit-lane time. The cause of the missing live detail feed remains unverified. See [Pit Stops](/entities/pit-stops) for count semantics and the available fields.

A separate paid-account diagnostic received one `PitLaneTimeCollection` record containing a pit-lane duration and lap. Its duration matched the same event in the later detail archive, but contained no stationary time. Checks across 57 archived stops support that distinction. F1 Sensor uses this feed as a best-effort live [pit-lane-time fallback](/entities/pit-stops#pit-lane-time-during-live-sessions), retaining the observations it receives. The single captured live event does not prove complete live coverage or access with a free or anonymous account.

## Public-feed observations

The public stream classification is unchanged. Publication varies by session: for example, no lap-count feed was observed during the FP1 checks. A quiet event-driven feed does not by itself mean authentication has failed.

## Archive access checks

Connect your Formula 1 account through the [F1TV Token Helper](/help/f1tv-token-helper). On 21 October 2026, both a free account and a paid account accessed the archive index and the same 18 tested timing streams; the anonymous archive-index request returned 401. A paid subscription was not required for those verified archive resources.

This is archived timing data, not F1 TV video replay access. It does not guarantee every file for every session: individual post-session `PitStopSeries` requests on 23 and 25 October returned 403, which was inconclusive about publication timing or access. The saved Singapore and United States race detail archives were available for later parser checks on 26 October. This does not identify when they became available or change the earlier live observations. Live feeds and archive files need separate checks. Formula 1 can change access or publication on its unofficial timing API.


## Interpreting the result

A locally well-formed, unexpired token does not establish authenticity. Upstream acceptance does not establish every feed permission. A permitted feed may still be quiet when no relevant data is published.

The saved observations do not establish complete live coverage, the requirements of every paid plan or the exact publication time of later archive files.
