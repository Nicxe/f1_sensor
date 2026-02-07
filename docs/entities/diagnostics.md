---
id: diagnostics
title: Diagnostics
---

Diagnostic entities are intended for troubleshooting and advanced automations. Some of them are only created when you enable the corresponding options during configuration.

## Entities Summary

| Entity | Info |
| --- | --- |
| [sensor.f1_live_timing_mode](#live-timing-mode) | Current live timing mode (`idle`, `live`, `replay`) |
| [binary_sensor.f1_live_timing_online](#live-timing-online) | Live timing connectivity indicator |
| [sensor.f1_replay_status](#replay-status) | Replay state and progress (Replay Mode) |

---

## Live Timing Mode
`sensor.f1_live_timing_mode` - Diagnostic sensor showing which mode the integration is currently in.

**State (enum)**
- One of: `idle`, `live`, `replay`.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| reason | string | Why the current live timing state is active (best effort) |
| window | string | Current live timing window label (best effort) |
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
| online_threshold_s | number | Maximum age (seconds) before the stream is considered offline |
| heartbeat_age_s | number | Seconds since last heartbeat frame (best effort) |
| activity_age_s | number | Seconds since last stream activity (best effort) |
| effective_age_s | number | The age value used for the online check (best effort) |

---

## Replay Status
`sensor.f1_replay_status` - Replay Mode status and progress.

**State (enum)**
- One of: `idle`, `selected`, `loading`, `ready`, `playing`, `paused`.

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| selected_session | string | Name of the selected session |
| download_progress | number | Download progress percentage (0–100) |
| download_error | string | Error message if download failed |
| playback_position_s | number | Current playback position in seconds (relative to chosen start reference) |
| playback_position_formatted | string | Current position as `HH:MM:SS` |
| playback_total_s | number | Total playback duration in seconds (relative to chosen start reference) |
| playback_total_formatted | string | Total duration as `HH:MM:SS` |
| session_start_offset_s | number | Start offset in seconds from the underlying session archive (best effort) |
| paused | boolean | True when playback is paused |
| sessions_available | number | Number of sessions available for the selected year |
| selected_year | number | Currently selected year |
| index_year | number | Year that the session index was loaded from (best effort) |
| index_status | string | Index status such as `ok`, `no_data`, or `error` (best effort) |
| index_error | string | Error details when index fetch fails (best effort) |

