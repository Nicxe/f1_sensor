# Precipitation radar beta verification

This record applies only to the modular `radar` module in
`custom:f1-sensor-card`. It preserves the observed desktop stability results and
the checks needed for a beta candidate. It is not a release announcement or a
claim of verified precipitation accuracy.

The [data contract](radar-prototype.md) defines image interpretation, external
requests and provider limits. The [circuit geometry review](radar-circuit-sources.md)
defines the bundled outlines and their uncertainty. The user guide is the
**Precipitation radar module** section in `docs/cards/overview.md`.

## Two-hour HAdev stability run

The run took place on **12 November 2026, 09:38:27–11:38:44 UTC**:
2 hours and 18 seconds of wall-clock time. It used four visible cards at zoom 13:
Monaco twice, Spa and Monza. The dashboard was already loaded, with normal HTTP
caching enabled. Live weather was explicitly allowed for the viewing context.

The client was Codex IAB on an Apple M4 with 10 logical CPUs and 16 GiB RAM,
running macOS 27.2.1. HAdev ran Home Assistant 2026.11.1 and reported two online
CPUs. The collection contained 1,112 browser samples, 119 HA Core samples and
238 OS process samples. Browser sampling used cumulative CPU counters and
JavaScript heap readings, normally every five seconds after the initial setup.
HA Core sampling began approximately three minutes after the browser series.

The tested runtime files had these SHA-256 hashes. Later edits need their own
focused verification; the stability run must not be presented as a run of a
different candidate without checking the source differences.

| File under the card's `modular/` directory | SHA-256 |
| --- | --- |
| `radar-circuits.js` | `a96ed32388e03123d641b90bcc45eed0b66d82f801f81dedd79760cc9d8fcd8b` |
| `radar-data.js` | `16ae9d86a1a4ae0849cf8c2291dd26ba8805c98c2679b58d613c96f046a487cf` |
| `radar-view.js` | `25a869513ad33a03e1e21f5ef899f5e4b860bbc733263a5b7674e6eb0e95cd36` |

### Scenarios and observed behavior

| Scenario | Observation |
| --- | --- |
| Four-card playback | All four continued changing frames through automatic catalog updates; no new network failures occurred during the final continuous playback phase. |
| LibreWXR blocked for more than six minutes | All four stopped and offered **Try again**. Once all were in the error state, 382 seconds of intact measurement showed no further image or metadata requests. |
| Cards outside the visible area for more than six minutes | All four stopped, released their displayed images and made no requests during 365 seconds of intact measurement. |
| Test tab offline for more than six minutes | Cached images initially continued playing. Two catalog requests then failed with `ERR_INTERNET_DISCONNECTED`; all four offered **Try again**. A further 106 seconds in that state had no requests. |
| Manual recovery after both network failures | All four returned to complete maps through **Try again**, and resumed animation after **Play**. No dashboard reload was needed. |
| One card playing, three paused | The cards remained mounted, permitting a comparison with four simultaneous animations. |
| Final pause | All four had complete maps, no pending requests and no captured console errors. |

### Resource results

| Measurement | Result |
| --- | --- |
| Renderer CPU, four-card playback | 7.98% of one logical CPU, time-weighted mean |
| Renderer CPU, one playing card | 3.00% |
| Renderer CPU, final pause | 0.29% |
| JavaScript heap during continuous final playback | 21.15–23.20 MiB |
| First / last complete five-minute heap minimum in that phase | 21.15 / 21.32 MiB |
| HA Core CPU over its separate sampling period | 1.42%, time-weighted mean |
| HA Core container memory | 745.5–846.8 MiB; final sample 784.2 MiB |
| Intact network coverage during comparable four-card playback | 79.9% of the sampled intervals |
| Radar HTTP cache hits within those intact intervals | 97.87% of requests |
| Encoded radar bytes within those intact intervals | 1,011.6 bytes per second |
| Observed external encoded-byte total | At least 4.743 MiB; a lower bound, not an extrapolated total |

The combined playback figures use intervals whose two adjacent samples belong
to the same one of these phases: initial playback, recovery after the provider
block, recovery after returning to view, recovery after offline mode and final
continuous playback. Pauses, the offline/block phases and the one-card control
are excluded. CPU is `100 × delta ProcessTime / delta Timestamp` for the renderer
and cumulative container CPU usage over elapsed time for HA Core. Network
intervals additionally require an unchanged event-truncation counter.

JavaScript heap minima levelled off in the continuous final playback phase;
DOM-node and event-listener baselines did not accumulate. HA Core had brief CPU
peaks even while the radar was stopped, and its values describe the whole
container, not an isolated radar cost. The test did not establish a sustained
resource increase caused by the module.

There were 10 intentionally blocked radar requests and two offline metadata
failures. Of 51 interrupted base-map requests around lifecycle transitions,
28 had a recorded `ERR_ABORTED` with `canceled=true`. The first 23 did not have a
saved error reason; their cause remains unconfirmed. They received HTTP 200 and
were followed by 36 completed base-map requests and complete rendered maps.
They must not be relabelled as proven intentional cancellations.

### Measurement limits

- This was a desktop run with an existing HTTP cache. It did not measure a
  first install, a cold browser cache or sustained load on a mobile device.
- IAB did not expose a genuine `document.hidden` transition when put in the
  background. The observed visibility stop was an offscreen
  `IntersectionObserver` transition. Synthetic browser tests of
  `visibilitychange` are separate evidence from a real background-tab test.
- JavaScript heap excludes native image buffers and GPU memory. OS RSS covered
  multiple app/browser processes and could include shared pages; it could not
  be attributed to the test tab.
- Network events were lost in some gaps between tool calls. Only the intact
  intervals support the reported transfer rate and cache ratio. The raw total
  is a lower bound. CDP `encodedDataLength` excludes packet overhead and HA
  WebSocket message traffic.
- The initial background sampler could not run without its tool context and
  was replaced by bounded sampling calls. That instrumentation failure was
  not a card runtime failure. Cumulative CPU counters remained usable across
  sampling gaps.
- Two hours cannot rule out slower memory leaks, different behavior on other
  clients or failures in the weather provider during a race weekend.

The temporary dashboard view, network overrides and viewport override were
removed after the run. The original dashboard and pre-existing browser tab were
preserved. HAdev remained running; its system log contained no F1 errors from
the run. No source edits, GitHub writes or release publication were part of this
stability test.

Raw samples, screenshots and analysis scripts were retained locally under
`test-results/radar-soak/20261112/`, which is intentionally Git-ignored. This
document preserves the material setup, results, source fingerprints and limits
without requiring those local artifacts to be present in a checkout.

## Beta preparation checks

After the stability run, beta preparation changed the module label to
**Precipitation radar (beta)** and placed mandatory OpenStreetMap attribution
inside the map, with wrapping and sizing for narrow cards. These presentation
changes did not alter the metadata refresh interval, request timeouts, playback
cadence or cancellation logic. The two-hour figures above remain a dated source
baseline; the updated view received the focused runtime checks below.

The updated `radar-view.js` SHA-256 is
`168d90c2a61a403381c7309128a302b917dde462092d0545627f10d065bb4d0f`.
`radar-data.js` and `radar-circuits.js` retained the stability-run hashes above.
All 421 corresponding integration files matched between HAdev and the local
Git checkout. Active and bundled card assets matched apart from the generated
`localization/available-locales.json` runtime file.

The focused radar browser suite passed **48/48 cases in Chromium** and
**48/48 cases in WebKit**, including 15 additional regression cases added during
beta preparation. These mocked browser tests are separate from both the live
HAdev checks and the complete local release preflight required below.

On Home Assistant 2026.11.1, reloading the integration returned the config entry
to its loaded state and updated the served card-asset version to
`993f7aa0659c`. The rendered
module showed the beta label. In Chrome with a **360 × 900** viewport, the map was
314 pixels wide and the OpenStreetMap credit stayed entirely within it. All 13
displayed image tiles were decoded at their expected 256-pixel source width.
With explanatory text disabled, the quality notice and intensity legend stayed
visible. **Latest**, **Play** and **Pause** worked, with no captured console error.
This was a mobile-sized desktop browser check, not a physical-phone endurance
test.

Chrome automation continued reporting `document.hidden=false` and
`visibilityState=visible` when another tab was activated, including through
`Page.bringToFront`. Actual background-tab behavior therefore remains an
environmental verification limit, separate from the observed offscreen stop
and automated visibility-handler tests. The viewport was restored and both
newly created test tabs were closed. No dashboard configuration was changed by
these preparation checks.

## Candidate verification and release boundary

For a beta candidate, verify the shipped source rather than relying on the
historical run above:

1. Check the radar data, circuit, view, context and timeout tests, with external
   requests mocked. Cover cancellation of shared requests, error/retry and
   stale metadata as well as successful imagery.
2. Check mobile-sized layouts, keyboard/touch controls, editor persistence,
   circuit selection and English fallback for new strings. Target-language
   translations continue through Weblate.
3. Exercise the candidate in HAdev. Distinguish actual hidden-tab and offscreen
   behavior from simulated visibility in automated tests, and document any
   unavailable client/device checks.
4. Verify card-asset delivery and complete integration-tree parity. The
   generated runtime `localization/available-locales.json` is the documented
   active-asset exception, not a source file to copy back into the package.
5. Run the repository's applicable focused checks and
   `npm run verify:release -- --target beta` on a frozen source snapshot. Its
   local receipt, source fingerprint and unavailable remote gates are separate
   from HAdev runtime evidence.

The desktop stability result supported continued beta preparation for this
scenario. It did not establish verified global ground-radar coverage. Local
checks and HAdev tests do not establish GitHub CI, a merged beta promotion or a
published beta; those require their own evidence and authorization.
