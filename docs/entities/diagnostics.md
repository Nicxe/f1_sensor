---
id: diagnostics
title: Diagnostics
---

Diagnostic entities are intended for troubleshooting and advanced automations. Some entities are created only when the corresponding feature is enabled during configuration, and some development diagnostics may be hidden in normal releases.

Downloaded diagnostics from **Settings > Devices & Services > F1 Sensor > Diagnostics** include a compact runtime summary for live timing, F1TV Auth, incident detection, and Track Map. Diagnostics are intended for support and should not include authorization headers, cookies, callback URLs, nonce values, tokens, or detailed car movement data.

## Entities Summary

| Entity | Info |
| --- | --- |
| [sensor.f1_live_timing_mode](#live-timing-mode) | Current live timing mode (`idle`, `live`, `replay`) and live data activity, if present |
| [binary_sensor.f1_live_timing_online](#live-timing-online) | Live timing connectivity indicator, if present |
| [sensor.f1_replay_status](#replay-status) | Replay state and progress |
| [sensor.f1_f1tv_token_status](#f1tv-token-status) | Redacted F1TV token health status |
| [sensor.f1_f1tv_token_expires_at](#f1tv-token-expires-at) | Expiry time for the saved F1TV live timing token |

---

## Live Timing Mode

`sensor.f1_live_timing_mode` - Diagnostic sensor showing which timing mode the integration is currently using. This entity may be hidden in normal releases.

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
| activity_age_s | number | Seconds since last live data activity (best effort) |
Normal users usually only need the sensor state, token status, and whether public live timing still works. Maintainers may ask for additional advanced attributes when troubleshooting a specific issue.

---

## Live Timing Online

`binary_sensor.f1_live_timing_online` - Diagnostic connectivity indicator for the live timing transport. This entity may be hidden in normal releases.

**State (on/off)**
- `on` when replay is active, or when a live timing window is active and recent live data activity is detected.
- `off` when outside the live timing window or when live data appears idle.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| mode | string | One of `idle`, `live`, `replay` |
| reason | string | Why the current live timing state is active (best effort) |
| online_threshold_s | number | Maximum age in seconds before live timing is considered offline |
| heartbeat_age_s | number | Seconds since last heartbeat frame (best effort) |
| activity_age_s | number | Seconds since last live data activity (best effort) |
| effective_age_s | number | Age value used for the online check (best effort) |

---

## Track Map Diagnostics

Downloaded diagnostics include `runtime.track_map` when Track Map runtime data exists.

| Field | Type | Description |
| --- | --- | --- |
| source | string | Current source, such as `live` or `replay` |
| status | string | Runtime status, such as `active`, `no_session`, `no_position_data`, `stale`, or `closed` |
| replay_state | string | Replay state, when Replay Mode is active |
| circuit_short_name | string | Human-readable circuit short name, when known |
| circuit_id | string | Circuit identifier used by F1 Sensor, when matched |
| point_count | number | Number of map points available |
| rotation | number | Map rotation in degrees, when available |
| approval_status | string | Map approval status, when known |
| driver_count | number | Number of drivers currently present in the Track Map snapshot |
| stale | boolean | True when live position data is older than the Track Map freshness window |

These fields help explain why the [Track Map](/features/track-map) card shows `Live`, `Replay`, `Waiting`, `Stale`, `No geometry`, `No session`, or `Not loaded`.

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
| latest_location | object | Optional latest Track Map location summary |
| available | boolean | Whether the incident coordinator is currently available |

:::info
Diagnostics intentionally show counts and latest metadata only. Use the [`f1_sensor_incident` event](/entities/events#on-track-incident) when you need the full event data for automations or troubleshooting.
:::

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
| session_start_offset_s | number | Start offset in seconds from the session archive (best effort) |
| paused | boolean | True when playback is paused |
| sessions_available | number | Number of sessions available for the selected year |
| selected_year | number | Currently selected year |
| index_year | number | Year that the session index was loaded from (best effort) |
| index_status | string | Index status such as `ok`, `no_data`, or `error` (best effort) |
| index_error | string | Error details when index fetch fails (best effort) |

---

## F1TV Token Status

`sensor.f1_f1tv_token_status` - Redacted status for the optional F1TV live timing token.

:::info
F1TV Auth is optional. Public live timing continues to work without a token. Only extra live-auth features depend on this status.
:::

**State (enum)**
- One of: `not_configured`, `valid`, `expiring_soon`, `expired`, `invalid`, `rejected`.

| Value | Description |
| --- | --- |
| `not_configured` | No F1TV live timing token has been paired |
| `valid` | A token is saved and can be used for extra live-auth features |
| `expiring_soon` | The saved token is still usable but should be replaced soon |
| `expired` | The saved token has expired |
| `invalid` | The saved token could not be parsed or validated |
| `rejected` | Formula 1 rejected the saved token |

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| auth_configured | boolean | True when a token is saved |
| used_for_live_timing | boolean | True when the token is currently being used for extra live-auth features |
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
