# Incident detection fixture baseline

This directory contains the Fas 0 baseline for stopped/on-track incident detection.

The goal is to keep a small, reproducible set of local fixture candidates that can drive the pure detector work in Fas 1 without committing full F1 Live Timing raw dumps. The MVP scope is stopped/on-track incident detection, not crash detection. Fixtures must describe what the public live streams show: stopped timing state, track status, Race Control context, pit state, and session metadata.

## Write scope

All files for this baseline live under `/Volumes/config/custom_components/f1_sensor`. The report also mentions docs under `/Users/niklas/GitHub/f1_sensor/docs`, but that path is outside the write scope for this task and was not changed.

## Fixture policy

Use reduced scenario fixtures, not complete sessions. Each scenario should document:

- source directory under `/Users/niklas/Desktop/import_requests/Streams`
- session type, session name, and time window
- driver numbers and names needed for the scenario
- included streams: `TimingData`, `TrackStatus`, `RaceControlMessages`, `SessionInfo`, and `DriverList`
- optional streams, especially `CarData.z`, only when the scenario explicitly validates auth-gated early-warning behavior
- expected detector behavior in user terms

Do not commit large raw dumps. Keep each scenario small enough to inspect in review, preferably under 100 KB unless a later replay test has a concrete reason to exceed that.

## Fas 0 baseline

`fixture_manifest.json` contains four extracted reduced scenarios, one each for race, sprint, qualifying, and practice.

The extracted scenarios are:

- Australian GP qualifying, `00:22:45-00:24:55`, where Race Control reports double yellow and red flag before `TimingData` marks car 3 as stopped.
- Miami GP race, `01:04:45-01:11:00`, where yellow and safety car context precede stopped timing state for cars 6 and 10.
- Chinese GP sprint, `01:07:00-01:10:00`, where yellow and safety car context precede stopped timing state for car 27.
- Chinese GP practice 1, `00:27:00-00:28:30`, where yellow and VSC context precede stopped timing state for car 41.

The manifest also lists optional future candidates for broader replay validation, but the Fas 0 gate is satisfied by the four reduced public-stream scenarios above.

## Fas 2 replay validation

`custom_components/f1_sensor/tests/incident_replay.py` replays the reduced manifest cases directly into the pure `IncidentDetector`. It does not use Home Assistant runtime, `LiveBus`, SignalR, replay downloads, auth-gated streams, or real-time sleeps.

Run the manual timeline helper from `/Volumes/config`:

```bash
/opt/homebrew/bin/python3.14 -m custom_components.f1_sensor.tests.incident_replay
```

Observed baseline order:

| Case | Public-stream order | Expected replay result |
| --- | --- | --- |
| Australian GP qualifying | `TrackStatus` yellow, `RaceControlMessages` double yellow, Race Control red flag, `TrackStatus` red, Race Control clear, then `TimingData.Stopped` for car 3 | One `confirmed` `high` incident for VER |
| Miami GP race | `TrackStatus` yellow, Race Control double yellow, Race Control Safety Car, `TrackStatus` Safety Car, then `TimingData.Stopped` for cars 6 and 10 | One `confirmed` `high` incident each for HAD and GAS |
| Chinese GP sprint | `TrackStatus` yellow, Race Control yellow, Race Control Safety Car, `TrackStatus` Safety Car, then `TimingData.Stopped` for car 27 | One `confirmed` `high` incident for HUL |
| Chinese GP practice 1 | `TrackStatus` yellow, Race Control double yellow, `TrackStatus` VSC, Race Control VSC, then `TimingData.Stopped` for car 41 | One `confirmed` `high` incident for LIN |

The replay tests also derive a practice weak-signal variant by removing flag and VSC context from the practice case. That variant must stay `medium`, not `high`, so practice-only stopped timing does not look more certain than the available evidence supports.

## Expected wording

Use neutral language:

- "Car stopped on track"
- "Possible on-track incident"
- "Driver stopped"
- "Incident cleared"

Avoid overclaiming:

- do not describe the feature as crash detection
- do not infer accident, mechanical failure, or off-track state unless Race Control or a later location signal supports it
- do not treat the fixture data as safety-critical or guaranteed real-time alerting
