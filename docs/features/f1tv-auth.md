---
id: f1tv-auth
title: F1TV Auth
---

F1 Sensor works without F1TV Auth. Optional F1TV Auth can unlock extra live timing features during an active Formula 1 session while public live timing continues to work without a token.

## How F1TV Auth changes live timing

F1 Sensor uses three separate timing modes:

| Mode | What it means | What to expect |
| --- | --- | --- |
| Public live timing | Standard live mode without a token | Core live entities, dashboards, and conservative incident alerts continue to work |
| F1TV Auth live timing | Optional live mode with a paired F1TV token | Extra live features can become available when Formula 1 provides the data |
| Replay Mode | Historical playback from Formula 1's session archive | Some live-auth features can be replayed later from archived session data |

F1TV Auth is not required for the integration, schedules, static data, race control, public live timing, or Replay Mode. If a token is missing, expired, invalid, or rejected, F1 Sensor should fall back to public live timing and only the extra live-auth features should stop updating.

## What works without F1TV Auth

Public live timing covers the normal live features most dashboards and automations use:

| Public live data | Examples |
| --- | --- |
| Session state | Current session, session status, session clocks, lap count |
| Track and race control | Track status, Safety Car, Race Control messages, track limits, investigations |
| Weather | Live trackside weather during active sessions |
| Driver timing | Driver list, positions, timing app data, tyres, tyre statistics, top three |
| Incident detection | Confirmed likely stopped-car or on-track incident alerts from public timing, Track Status, and Race Control context |

## What F1TV Auth can add during live sessions

F1TV Auth can support live features such as Track Map, Pit Stops, Championship Prediction, formation start refinement, and earlier incident candidate signals. These features still depend on what Formula 1 publishes for each session, so a valid token does not guarantee that every extra feature is available every time.

## Subscription requirement

F1TV Auth requires a signed-in Formula 1 account with an active F1 TV subscription that includes Essential Live Timing. You do not need F1 TV Pro or F1 TV Premium just to pair F1TV Auth; F1 TV Access is enough in regions where Formula 1 offers it.

F1 controls subscription names, availability, and prices. As a rough guide, F1 TV Access has been shown around EUR 3.49 per month and F1 TV Pro around EUR 17.99 per month, but check the F1 TV subscription page for your country before subscribing.

:::info
F1TV tokens are short-lived, and Formula 1 can vary which extra live data is published from session to session.
Public live timing continues to work if F1TV access is missing, expired, invalid, or rejected.
:::

## Availability matrix

| Feature or data | Without F1TV Auth live | With F1TV Auth live | Replay Mode |
| --- | --- | --- | --- |
| Track status, Safety Car, Race Control, weather | Works | Works | Works when replayed |
| Driver positions and timing | Works | Works | Works when replayed |
| Confirmed incident detection | Works | Works | Works when replayed |
| Early incident candidates from car movement | Not available | Can improve when live car movement data is available | Works when replay contains the needed data |
| Track Map | Not available live | Requires F1TV Auth and live car position data | Works when replay contains car position data |
| Incident location context | Not available from live position | Can improve when Track Map has fresh location data | Works when replay contains car position data |
| Pit Stops | Not available live | Can work when Formula 1 publishes live pit stop data | Works when replay contains pit stop data |
| Championship Prediction | Not available live | Can work when Formula 1 publishes live prediction data | Works when replay contains prediction data |
| Formation Start | Public fallback only where available | Can improve when extra live timing data is available | Works in Replay Mode |

## Token Helper and renewal

The recommended way to connect F1TV Auth is the [F1TV Token Helper](/help/f1tv-token-helper). The helper reads a short-lived live timing token from your own browser session and sends it to your own Home Assistant pairing callback.

Home Assistant does not ask for your Formula 1 password. Tokens are short-lived, so expect to renew access when `sensor.f1_f1tv_token_status` reports `expiring_soon`, `expired`, `invalid`, or `rejected`.

For the practical setup workflow, see [F1TV Auth Setup](/help/f1tv-auth-setup).

## Privacy and safety

F1 Sensor stores only the authorization value needed for live timing. Diagnostics and public issue reports should never include tokens, full `Authorization` headers, cookies, callback URLs, nonce values, or browser session data.

Downloaded diagnostics can include redacted token health and live timing activity. They should not include secrets or high-frequency telemetry.

## Limitations

- F1TV Auth is optional.
- Tokens are short-lived and renewal is not automatic.
- Extra live features are available only during suitable live sessions when Formula 1 publishes the needed data.
- Live Track Map cannot be fully verified without an active session and a working token.
- Replay Mode is separate from live auth and can show archived data later when the replay archive contains it.

## Related pages

- [Track Map](/features/track-map)
- [Incident Detection](/features/incident-detection)
- [Replay Mode](/features/replay-mode)
- [F1TV Token Helper](/help/f1tv-token-helper)
- [F1TV Auth Setup](/help/f1tv-auth-setup)
- [Diagnostics](/entities/diagnostics)
