---
id: diagnostics
title: Diagnostics
description: Check connection, replay, and F1TV token health, and understand the downloaded diagnostic summary.
---

Use diagnostics to understand why data is waiting, unavailable, or failing to update. Start with the symptom below, then inspect the relevant entity or download the integration’s diagnostic summary.

## Start with the symptom

| Symptom | Check first |
| --- | --- |
| Live entities are unavailable | Is a session active, and is live data enabled? See [live availability](/entities/live-data#availability-model) |
| Extra F1TV data stopped | [Token status](#f1tv-token-status), then [F1TV setup](/help/f1tv-auth-setup) |
| Replay is loading or stalled | [Replay status](#replay-status) and its `download_error` or `index_error` |
| Track Map has no cars | [Track Map diagnostics](#track-map-diagnostics) and the card’s visible status |
| An incident alert was unexpected | [Incident diagnostics](#incident-detection-diagnostics), session time, and the relevant event |

## Download diagnostics

Open **Settings > Devices & services > F1 Sensor**, then use the integration entry’s menu to download diagnostics. The file contains a compact runtime summary; it is different from the entity attributes below.

Some diagnostic entities are only created when a feature or development interface is enabled. If an entity is absent, use the downloaded diagnostics and [debug logs](/help/debug-logging).

Diagnostics should exclude tokens, authorization headers, cookies, pairing URLs, nonce values, and detailed car movement data. Check the file before sharing it in an issue.

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

When incident detection is available, the downloaded diagnostics file includes a `runtime.incident_detection` summary.

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

`sensor.f1_replay_status` reports `idle`, `selected`, `loading`, `ready`, `playing`, `paused`, or `seeking`. Inspect `download_error` when a load fails and `index_error` when the session list cannot be loaded.

The complete state and attribute table is in [Replay controls](/reference/replay-controls#replay-status-sensor). Playback position and duration are relative to the selected playback start reference.

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
| `valid` | The saved token is locally well-formed and unexpired; upstream acceptance is not yet proven by this state alone |
| `expiring_soon` | The saved token has not expired but should be replaced soon; upstream access still depends on Formula 1 |
| `expired` | The saved token has expired |
| `invalid` | The saved token could not be parsed or validated |
| `rejected` | Formula 1 rejected the saved token |

The local token check does not verify authenticity. Formula 1 must accept the token during a request before authenticated live data can be used. Public live timing remains available without it.

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
