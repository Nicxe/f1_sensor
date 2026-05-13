---
id: diagnostics
title: Diagnostics
---

Diagnostic entities are intended for troubleshooting and advanced automations. Some entities are only created when the corresponding feature is enabled during configuration.

Downloaded diagnostics from **Settings > Devices & Services > F1 Sensor > Diagnostics** include a small runtime summary for live timing and incident detection. The diagnostics output is intended for support and does not include raw high-frequency telemetry, authorization headers, cookies, or tokens.

## Entities Summary

| Entity | Info |
| --- | --- |
| [sensor.f1_live_timing_mode](#live-timing-mode) | Current live timing mode (`idle`, `live`, `replay`) |
| [binary_sensor.f1_live_timing_online](#live-timing-online) | Live timing connectivity indicator |
| [sensor.f1_replay_status](#replay-status) | Replay state and progress |
| [sensor.f1_f1tv_token_status](#f1tv-token-status) | Redacted F1TV token health status |
| [sensor.f1_f1tv_token_expires_at](#f1tv-token-expires-at) | Expiry time for the saved F1TV live timing token |

---

## Incident Detection Diagnostics

When incident detection is available, the downloaded diagnostics file includes an `incident_detection` runtime summary.

**Fields**

| Field | Type | Description |
| --- | --- | --- |
| active_count | number | Number of currently active incident records |
| highest_confidence | string | Highest active confidence, such as `medium` or `high` |
| latest_incident_id | string | Stable identifier for the most recent incident update |
| latest_driver_number | string | Car number for the latest incident update |
| latest_driver_tla | string | Driver abbreviation for the latest incident update |
| latest_reason | string | Neutral reason code for the latest update |
| latest_phase | string | Latest incident phase |
| session_type | string | Lowercase session type, such as `race`, `sprint`, `qualifying`, or `practice` |
| session_name | string | Human-readable session name |
| data_quality | string | Data source quality, such as `live`, `replay`, or `bootstrap` |
| available | boolean | Whether the incident coordinator is currently available |

:::info
Diagnostics intentionally show counts and latest metadata only. Use the [`f1_sensor_incident` event](/entities/events#on-track-incident) when you need the full event payload for automations or troubleshooting.
:::

---

## Live Timing Mode

`sensor.f1_live_timing_mode` - Diagnostic sensor showing which mode the integration is currently using.

**State (enum)**
- One of: `idle`, `live`, `replay`.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| reason | string | Why the current live timing state is active (best effort) |
| window | string | Current live timing window label (best effort) |
| schedule_source | string | How the live schedule was resolved (best effort) |
| index_http_status | number | HTTP status code of the last schedule index fetch (best effort) |
| fallback_active | boolean | True if the schedule is using a fallback source (best effort) |
| last_schedule_error | string | Error details from the last schedule fetch attempt (best effort) |
| heartbeat_age_s | number | Seconds since last heartbeat frame (best effort) |
| activity_age_s | number | Seconds since last stream activity (best effort) |

---

## Live Timing Online

`binary_sensor.f1_live_timing_online` - Diagnostic connectivity indicator for the live timing transport.

**State (on/off)**
- `on` when replay is active, or when a live timing window is active and recent stream activity is detected.
- `off` when outside the live timing window or when the stream appears idle.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| mode | string | One of `idle`, `live`, `replay` |
| reason | string | Why the current live timing state is active (best effort) |
| online_threshold_s | number | Maximum age in seconds before the stream is considered offline |
| heartbeat_age_s | number | Seconds since last heartbeat frame (best effort) |
| activity_age_s | number | Seconds since last stream activity (best effort) |
| effective_age_s | number | Age value used for the online check (best effort) |

---

## Replay Status

`sensor.f1_replay_status` - Replay Mode status and progress.

**State (enum)**
- One of: `idle`, `selected`, `loading`, `ready`, `playing`, `paused`, `seeking`.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| selected_session | string | Name of the selected session |
| download_progress | number | Download progress percentage from 0 to 100 |
| download_error | string | Error message if download failed |
| playback_position_s | number | Current playback position in seconds, relative to the chosen start reference |
| playback_position_formatted | string | Current position as `HH:MM:SS` |
| playback_total_s | number | Total playback duration in seconds, relative to the chosen start reference |
| playback_total_formatted | string | Total duration as `HH:MM:SS` |
| session_start_offset_s | number | Start offset in seconds from the underlying session archive (best effort) |
| paused | boolean | True when playback is paused |
| sessions_available | number | Number of sessions available for the selected year |
| selected_year | number | Currently selected year |
| index_year | number | Year that the session index was loaded from (best effort) |
| index_status | string | Index status such as `ok`, `no_data`, or `error` (best effort) |
| index_error | string | Error details when index fetch fails (best effort) |

---

## F1TV Token Status

`sensor.f1_f1tv_token_status` - Redacted status for the optional F1TV live timing token.

:::warning[Experimental feature]
F1TV access is optional and experimental. Public live timing continues to work without a token. Only auth-gated live timing streams depend on this status.
:::

**State (enum)**
- One of: `not_configured`, `valid`, `expiring_soon`, `expired`, `invalid`, `rejected`.

| Value | Description |
| --- | --- |
| `not_configured` | No F1TV live timing token has been paired |
| `valid` | A token is saved and can be used for auth-gated live timing |
| `expiring_soon` | The saved token is still usable but should be replaced soon |
| `expired` | The saved token has expired |
| `invalid` | The saved token could not be parsed or validated |
| `rejected` | Formula 1 rejected the saved token |

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| auth_configured | boolean | True when a token is saved |
| used_for_live_timing | boolean | True when the token is currently being used for auth-gated live timing |
| expires_at | string | ISO-8601 expiry timestamp, or `null` |
| reason | string | Redacted reason when the token is invalid, expired, or rejected |

---

## F1TV Token Expires At

`sensor.f1_f1tv_token_expires_at` - Timestamp sensor showing when the saved F1TV live timing token expires.

**State**
- Timestamp, or `unknown` when no valid expiry is available.

**Attributes**

This sensor exposes the same redacted attributes as [F1TV Token Status](#f1tv-token-status): `auth_configured`, `used_for_live_timing`, `expires_at`, and `reason`.

:::tip
Use `sensor.f1_f1tv_token_status` for automations that need to detect invalid or rejected tokens. Use this timestamp sensor when you want reminders before the token expires.
:::
