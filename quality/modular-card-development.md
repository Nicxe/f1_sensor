# Modular F1 Sensor card development

Implementation of `F1_SENSOR_NY_KORTPLATTFORM_PLAN_2026-09-13.md`, on the local
`feat/modular-f1-card` branch. No commits, pushes, published beta, or release are
authorized for this work. Existing card types remain supported.

## Source and delivery contract

Author frontend modules in `/Volumes/config/www/f1-sensor-live-data-card/modular/`.
Use native ES modules and the bundled Lit runtime. Do not introduce a CDN runtime,
a second Lit copy, or a build output that differs from tested source. A module
must forward its `v` query parameter to every relative dynamic import.

After each completed edit, copy changed files to
`/Volumes/config/custom_components/f1_sensor/www/f1-sensor-live-data-card/`,
compare bytes, and copy those same files to this repository's bundled directory.
Before editing existing files, compare all three copies and preserve differences.
The initial 15 files were identical on 2026-09-13. Add new delivered files to
`LIVE_DATA_CARD_ASSET_FILENAMES` in `frontend.py` before enabling registration.
Tests must exercise that same delivered module graph.

The existing Lit asset retains its deployed versions (Lit 3.3.2,
lit-html 3.3.3, lit-element 4.2.2, reactive-element 2.1.2). Its public `repeat`
directive is bundled with that same runtime for keyed rows and event lists.
`quality/lit-vendor/package-lock.json` pins the build tool and dependencies;
run `npm ci --prefix quality/lit-vendor`, then `node quality/lit-vendor/build.mjs
--write /Volumes/config/www/f1-sensor-live-data-card/f1-lit-3.3.2.js` and immediately
sync the asset. `--check` verifies reproducibility without writing a file.

Frontend source belongs in small modules: catalogue, configuration, semantic
formatting, source adapters, connection/context, components, editor, card shell,
and optional feature renderers. Each visible module receives a normalized model;
it does not independently interpret raw integration data. Legacy cards are not
nested inside the new card.

## Configuration and interaction contract

The new type is `custom:f1-sensor-card`, with `version: 1`. Persistent preferences
belong in the Lovelace configuration. Stable module IDs are independent of array
order. Content presets expand to copied module configurations; applying a style
only changes appearance. Unknown properties survive normalization, editing and
export; unsupported versions and modules produce an explicit error, never silent
loss. Import and migration retain a recoverable original.

The editor groups content, appearance, behaviour and accessibility. Module
settings use the same catalogue as rendering. Presets can be saved immediately;
advanced fields appear only for the selected module. Replacing content requires
an in-editor comparison and a cancel/apply choice. All reorder operations have
buttons, retain focus, and support undo. Preview uses the real renderer with
isolated, labelled demonstration data and cannot issue integration actions.

Local driver focus and freeze do not change integration selectors, Live Delay,
spoiler state, or replay. Optional groups are scoped to connection, entry,
dashboard, view and explicit group name. No global localStorage context. Shared
subscriptions are reference counted; unsubscribe is a frontend operation and
must never stop backend replay. Snapshot/event races and stale asynchronous
results require tests.

## Visual and semantic contract

F1, Home Assistant and Minimal are separate appearance presets. Automatic, light
and dark modes use the same content. F1 uses restrained team accents, tabular
timing numerals and a bundled Barlow Condensed heading font (SIL OFL, license
shipped beside the font). No external font service is required. Decorative accents and timing
statuses have separate palettes. Image dimensions are reserved and names remain
readable when a logo or flag is absent. Country flags never indicate track state.

Timing semantics: overall fastest = purple + diamond; personal best = green +
circle; recorded time = yellow + square. Yellow says nothing about the previous
lap. Previous-lap values use neutral styling and explicit lap provenance. Deleted
and invalid times remain distinguishable. Faster lap = negative delta + down
triangle; slower lap = positive delta + up triangle (#530). Position gain uses
an upward arrow and its own comparison basis. Missing or invalid data is not zero.

Default sectors show a coherent lap. Retain the completed lap until the next S1,
then clear unmatched later sectors. Mixed latest sectors are opt-in and label
every sector's lap. Session changes, corrections and replay seeks invalidate
cached sectors. Summed personal-best sectors are explicitly theoretical.

Every meaningful state has shape/text, accessible names and a semantic table or
list. Keyboard targets aim for 44 CSS pixels. Include forced colors, reduced
motion, high contrast, 200% text and 400% reflow; test colour vision variants and
screen readers separately. Automated axe is necessary, not an AA certification.
Freeze means a labelled local reading snapshot, with polite status announcements
instead of an aria-live announcement for every changing timing cell.

## Verification and progress

Existing budgets: gallery rendering 2500 ms, longest task 50 ms. New scenarios:
one weekend card, full-field timing/event card and ten cards sharing a connection.
Measure subscriptions and requests as well as rendering. Pin fixture date; do not
change baselines solely to make snapshots pass.

Run repository frontend unit/browser/quality tests, runtime Ruff and full
integration scripts, relevant docs build/browser checks, packaging/cache tests,
and actual Home Assistant UI verification. Record fixture/replay/live evidence
separately. Public beta, exact-commit remote CI and stable release remain future
publication activities under the user's local-only instruction; do not imply
they have happened.

| Plan stage | Current evidence | Remaining gate |
| --- | --- | --- |
| A: contracts and inventory | Executable catalogue for twenty modules, versioned configuration, semantic/data/connection tests; static inventory of 23 legacy cards and 336 setting accesses; measured simple, detailed and ten-card browser scenarios | Review computed/shared legacy settings, finish full catalogue and migration mapping; extend memory and real-session measurements |
| B: design and usability | Real initial renderer/editor; three presets; six style/theme combinations; narrow viewport, keyboard focus, forced colors and enlarged text in browser fixtures | Broader manual accessibility/usability evaluation, full field/profile design, refined mobile column priorities |
| C: complete initial implementation | Overview, schedule, weather, timing and Race Control renderers; editor, serialized preferences, scoped focus and shared subscriptions; initial assets packaged | Remaining capability/age details, full field profiles, live/replay proof and performance budgets |
| D: season and session breadth | Results/grid, standings, documents, season/lap charts, historical classifications and race lap/position charts, current/aggregate tyres, pit history, incident/track-limit views and separate weather sources implemented | Remaining field/profile coverage, archive native verification, documentation and live/replay evidence |
| E: map, analysis and replay | Map, timeline, battles, stint graphics, strategy and replay telemetry; shared subscriptions, revision/session filtering, real replay comparisons and reconnect/cleanup tests | Full lifecycle/live-session coverage and remaining shared controls |
| F: migration and verification | Conversion review, demonstration preview, recoverable original and restoration; valid starting profiles for 23 legacy cards and the archive alias; real HA save/reload/restore proof | Full per-setting and default-behavior parity across all legacy cards, documentation, complete manual matrix and release preparation |

Runtime observation on 2026-09-13: next-race, season and weather entities contain
data; current-session, driver-position, tyre and race-control entities are
unavailable. This is evidence for the off-session UI only, not live acceptance.

### Local implementation checkpoint

The new card and editor are registered alongside all 23 legacy cards. Native
Home Assistant in the authenticated HAdev browser rendered the card, edited its
title, style and fields, saved it, reloaded the whole dashboard and reopened the
editor with those choices intact. This used an isolated dashboard,
`f1-modular-development`; existing dashboards were not changed. Native HA action
selectors were also inspected. The HA boolean `preview` property remains separate
from injected `previewData`, and preview actions are inert. Container queries keep
the editor usable inside HA's narrow editor column. Keyed Lit rows, fields and
module controls preserve identity during reorder.

Home Assistant development was restarted once to load entity discovery changes.
The F1 entry loaded, global spoiler discovery worked, and the integration refreshed
its managed resource hash. Actual off-session UI displayed explicit unavailable
data states. The MCP screenshot service returned configuration errors, whereas
the authenticated Zen browser rendered correctly; the screenshot-service failure
has not been diagnosed and is not counted as verification.

Latest broad checks before the session-module additions: 1,551 integration tests,
47 browser tests, 89 frontend unit tests, Ruff 0.15.4 and the deterministic release
with 97 runtime files passed. Later result-count and chart-axis refinements passed
18 modular browser tests and 39 modular unit tests. Session-module changes add
further checks; their current results are recorded below. These counts describe
specific checkpoints, not an assertion that all subsequent work has passed.

`scripts/inventory_card_options.cjs` generates `quality/legacy-card-options.json`
from the actual legacy card and registry AST. Its `not_reviewed` labels are
intentional: finding a setting is not evidence that conversion preserves it.
The archive compatibility alias is listed separately. Generated source line
references must be refreshed when the legacy source moves.

Entity discovery now includes renamed global spoiler controls and disabled source
IDs. The new frontend fails closed when spoiler state cannot be verified. The updated API is loaded in the development Home Assistant process.

Frontend unit coverage at this checkpoint includes configuration round trips,
official best-lap corrections, sector provenance/seek/session reset, lap arrows,
palette contrast, snapshot/event overlap, late unsubscribe, partial failure,
reconnect and group isolation. Browser fixtures cover content/style persistence,
three presets, six style/theme variants, accessible timing signals, module focus,
local freeze, spoiler activation while frozen and forced colors/enlarged text.
HA persistence has separate native UI evidence; these fixtures do not prove real
live timing, VoiceOver, NVDA or iOS Companion behavior.

The existing Python timing-layout harness depended on logo helpers being inside
the monolithic file. It has been updated to read the actual delivered shared
`platform/branding.js`; the behavioral assertions remain unchanged. Use Ruff
**0.15.4**, pinned by this repository's `requirements-dev.txt`, explicitly when
running the runtime scripts (their default is currently 0.15.12).

Next completion work: complete remaining fields, session profiles, data-age and
availability behavior, public versus authenticated capabilities and preview
controls; finish stage D coverage, implement stage E modules and stage F migration/documentation.
Do not equate this checkpoint with a completed stage C or the full plan.

### Season and shared graphics implementation contract

Keep result and championship values in source-defined categories. A result time
can be elapsed time, a gap or laps behind; never pass it through a lap-time best
indicator. Starting grid position and classified finishing position stay distinct.
Historical rows use the identities supplied by that result, not today's roster.
Championship prediction is explicitly labelled and cannot silently replace an
unavailable official table. Document links use a safe URL policy and preserve
publication provenance. All spoiler-sensitive sources use the same fail-closed
protection as timing.

Tyres have a compound letter/name even when graphics or colour are unavailable.
Use the existing packaged tyre assets, reserve image dimensions and retain a
text fallback. Track status uses its own symbol/text and official colour, separate
from customizable timing colours and decorative national flags.


### Season and session checkpoint

The native Home Assistant card picker created the new Results and championship
preset on the isolated development dashboard. Its title and five-row limits were
edited in the native editor, saved, and verified after a complete dashboard reload.
The actual Italian GP result, published 2026 championship and season progression
rendered from HA entities. This verifies real static-source rendering and native
persistence; it does not prove live timing or replay.

The catalogue now has sixteen modules. `session-data.js` adapts `current_tyres`,
`tyre_statistics`, `pitstops`, `investigations` and `track_limits`. Pit stationary
time, pit lane time and estimated lap loss remain separate. The latter is the
backend's longer in/out lap minus median reference, with explanatory text; the
frontend never substitutes one time for another. Aggregate compound statistics
explicitly combine all drivers and cannot be misleadingly filtered to one driver.
Unknown compounds, age zero, new versus used sets and missing laps remain distinct.

Incident decisions use the backend's interpreted objects, including NFI decision
time and after-race status. The card does not parse Race Control messages again,
expire decisions itself, or accumulate obsolete states. Every status has text and
a symbol. Event lists, tables and compound records use keyboard-scrollable regions
and readable names. All these modules share spoiler protection and local freeze.
Content-dependent starter fields and editor choices reduce irrelevant columns;
custom selections survive view changes and are explicitly marked when unused.

The archive checkpoint passes 141 frontend unit tests, 76 browser tests,
40 Python CI checks, 38 Node automation checks and deterministic packaging with
101 runtime files. Ruff 0.15.4 and its CI profile pass. The full runtime integration
suite passed all 1,551 tests in 381.30 seconds after the additive historical-ID
change. Forty-six of the browser cases target the
new modular card; no legacy screenshot baselines were changed.

The managed frontend resource refreshed to `c63e64d984d0` before the latest field
refinements. Subsequent native browser verification was blocked because the Mac
was locked; it is not counted as runtime proof of the three new modules. The
updated Python manifest has not yet been loaded by another HA core restart.
All delivered files are synchronized in the runtime primary, runtime bundle and
repository bundle; the manifest now contains 34 frontend assets (101 release files).


### Timing profiles and initial analysis

Timing now offers automatic, practice, qualifying, sprint qualifying, sprint and
race column profiles, with custom columns as the backward-compatible local default.
Editing a profile's selected columns copies the visible field set into a persistent
custom choice. Automatic profiles follow the session. Qualifying values never
populate race rows; SQ labels remain distinct. Personal-best sectors retain each
lap and qualifying part. A theoretical sum is labelled as such, and qualifying
sums require all three sectors to belong to the current qualifying part.

The timeline module consumes the version-1 analysis subscription, one shared
frontend subscription per connection/entry. It uses the server's initial push,
not a racing parallel GET. Reconnect and late cleanup cannot resurrect previous
generations; unsubscribe never calls backend replay services. Snapshot replacement
handles rewinds and event removals. Event revisions are deduplicated and other-session
events are rejected. Derived exchanges/battles retain a visible estimate label,
including table mode. Evidence scores are explicitly not calibrated probabilities.

A read-only call to the actual HAdev `f1_sensor/analysis/get` returned protocol 1,
status ready, provider `f1_live`, phase before, no current session, no timeline
items and waiting-for-clean-laps strategy. This proves the current backend contract
is loaded and waiting; it does not prove an active-session analysis rendering.
The Mac was subsequently unlocked. Native HA verification resumed as recorded below;
active-session and replay rendering still need separate evidence.

Immediate remaining work includes telemetry, native archive verification,
source age/session/replay coherence, full field coverage and mobile
priority, complete presets/context controls, migration of all
23 legacy types plus alias, user documentation, extended performance coverage and the
remaining manual accessibility/live acceptance work. The plan is not complete.


### Native session-module and strategy verification

The isolated HAdev dashboard now also contains `Däck, depå och analys`, with tyre,
pit, incident, timeline and strategy modules. This card was added by a hash-guarded
storage transform and rendered in the authenticated native browser after a hard
reload. Tyres/incidents explained unavailable session data, pit timing explained
its source requirement, the timeline reported no events, and strategy showed zero
session coverage without inventing pace values. The existing results table opened
all 22 classified drivers via Show all, then returned to its saved five-row limit
after a hard reload. Published standings and the readable 0/100/200/300 chart axis
were also visually inspected. Existing user dashboards were untouched.

Strategy uses backend stint and compound aggregates without recalculating its
analysis model. Clean pace, raw pace, excluded laps, degradation, evidence score
and stint-change loss have separate fields. All-driver session coverage is labelled
separately from a driver-filtered table. Compound aggregates cannot inherit a driver
filter. Stint graphics, teammate/crossover/undercut views and local quality filters
were subsequently added, as recorded below. Active-session strategy acceptance
is still pending.

The real track-map GET returned no_session, no geometry and no driver positions.
The v2 snapshot/delta/resync protocol, geometry points/rotation and driver snapshot
contract have been inspected. The map decoder, shared subscription, renderer and
editor module are now registered and tested with representative demo data.


The v2 map decoder rejects other entries, ignores duplicate sequences, detects
missing delta ranges, discards previous-session drivers and applies changes/removals
atomically. The shared subscription buffers up to 128 frames during a bounded
resync, handles coalesced deltas and unloads, and never issues replay services.
Projection preserves zero coordinates and source gaps, rotates geometry and rejects
degenerate/non-finite spans. Replay freshness is independent of wall-clock age.
Nine pure map tests and the shared-resync test pass. Three browser cases cover
map graphics, keyboard focus, text alternatives, forced colors, bounded labels,
editor options, spoiler protection, local freeze, stale deadlines and stream
cleanup. The synthetic mobile map was visually inspected; its shape is explicitly
demonstration geometry. Text alternatives remain available in map-only mode and
the user's expanded/collapsed choice survives updates. Geometry projections are
cached by immutable source geometry. Stale live snapshots schedule one deadline
timer; paused replay does not age against the wall clock.

The map module was appended to the isolated development card through a hash-guarded
dashboard transform, verified at storage hash `e441e92b38800f63`. Native runtime
rendering of this module is pending because the Mac is currently locked. No active
map geometry or position delivery is claimed from the empty off-session GET.

### Battles and strategy comparisons

The battles module offers active observations, start/end history and position
exchanges. Both drivers can be used as a filter. History keeps start and end as
distinct events, labels the backend classification and never invents event times.
Position exchanges retain before/after positions and their supporting signals;
they are not automatically presented as on-track overtakes. The module shares
the existing analysis subscription and never controls replay.

Strategy now includes teammate medians, compound crossover indications and
observed teammate pit-cycle outcomes. These values are mapped from the backend,
not recomputed. Equal medians have no declared faster driver. Crossover ages
outside the observed range are withheld; aggregate comparisons cannot inherit
a driver/team pin. Minimum evidence and clean-lap filters are local, preserve
unknown versus zero, and are shown only where the source supports them.

The optional stint graphic shows first/last observed lap, starting tyre age,
compound and recorded/clean/excluded counts. A missing range stays textual.
Bars explicitly describe observed extents rather than continuous complete laps.
Text values remain visible without color, with an optional customizable table.
The mobile map, strategy comparisons and forced-color stint view were visually
inspected. The map-edge label clipping and duplicate default analysis landmark
names found by those checks were corrected. Long analysis explanations are now
behind a keyboard-accessible disclosure; estimate labels, coverage and evidence
semantics stay visible. Native HA verification of these later additions remains
pending while the Mac is locked.

### Source filtering and clock coverage

Unavailable roster or tyre attributes no longer relabel current timing rows.
Qualifying personal-best sectors cannot form a theoretical race lap. Race Control
accepts number/code focus through the available roster, offers a compact latest
matching message view and exposes a separate choice for global session messages.

Overview clocks expose elapsed time, remaining time and the three-hour race limit
independently. Values come from the backend, without a second frontend stopwatch.
Zero, pause and missing values remain distinct; mismatched session names or known
qualifying parts are rejected. The race cap is race-only and explains that session
interruptions are included, rather than inheriting the official clock's pause label.
Clock fields obey spoiler protection even within a nonsensitive weekend overview.

After the broad checkpoint, an additional map regression verifies that a new
session without an explicit geometry decision triggers a full resync. The shared
resource is marked refreshing while recovery is pending, so default views cannot
silently show previous geometry as current. The focused map suite passes 20 unit
cases (including shared connection cases) and three browser cases. This regression is included in the current full frontend test checkpoint.


### Weather, track-limit summaries and lap charts

Weather now has separate current-circuit, near-race-start forecast and track
observation views, plus the original mixed overview. Each view has appropriate
fields and an optional compact definition list. The editor preserves custom fields
when a source changes and marks inactive fields. Temperature, humidity, cloud
cover, visibility, wind/gusts/bearing, forecast precipitation/probability, track
temperature, pressure and rain detection keep their source meanings. Zero and
missing values remain different. The live rain indicator is a strict 0/1 value,
not millimetres or a claim about surface moisture; this matches the primary
[FastF1 WeatherData parser](https://raw.githubusercontent.com/theOehrly/Fast-F1/master/fastf1/_api.py).
The legacy backend rainfall unit is unchanged. Measurement timestamps and the
precipitation interval are not exposed in these sensor attributes, so the card
states that limitation and labels HA update times as received times. Track
observations obey spoiler protection. Weather symbols supplement text, and the
wind arrow points toward the explicitly labelled source bearing.

Read-only HAdev inspection confirmed the actual discovered weather/track-weather
entity IDs. The current source exposed 22.7 °C, the race forecast 27.3 °C and 12%
rain probability for Baku; track weather was unavailable. This confirms attribute
mapping at this checkpoint, not a live weather acceptance test. Native rendering
of the new weather choices remains pending while the Mac is locked.

Track-limit summaries use the sensor's per-driver deletion count, warning flag
and latest penalty. They do not infer counts from the retained violation list or
invent zero records for absent drivers. A missing warning/penalty field remains
unknown; explicit false/null is shown as no recorded warning/penalty. Driver/team,
text and relevant status filters, source corrections, ordering and editor round
trips are covered. The existing incident event view remains available.

The lap-history module uses completed laps exposed by driver_positions. Users
select drivers, lap bounds, lap time versus change from the preceding lap, and a
chart/table presentation. Each point keeps its real lap number. Missing or future
laps are never filled; a lap change requires the immediately preceding recorded
lap for that same driver, including when the reference lap is outside the displayed
range. This view is not claimed as full historical archive or cleaned pace analysis.
It explains that pit laps, neutralisations and qualifying parts can be present.

The existing chart component now supports lap labels and duration/delta formatting.
Duration axes use a bounded scale; season points retain their zero baseline. Lines
retain every valid point and gap, while marker density is reduced for long histories.
Isolated samples next to gaps still receive markers. The accessible table retains
all selected values. Weather and lap-chart mobile captures were visually inspected;
forced-color track-limit and automated accessibility checks pass. This does not
replace the pending manual screen-reader, iOS or real live-session checks.


### Replay control checkpoint (2026-09-14)

The replay module exposes the existing year/session/start-reference selectors,
manual session-list refresh/load and media-player play/pause/stop/seek services.
Entity IDs come from installation discovery. No mounting, styling, moving,
unmounting, previewing or reading a card sends a replay command. Preview and local
freeze disable both UI controls and the parent command handler. The scope text
states that replay changes affect the installation's dashboards and automation
data. Loading is a separate user action from selecting a session.

Controls validate the current installation, rendered session context, enabled
fields, source availability and backend replay state before each service call.
Year/session/reference changes require idle or selected state; users stop a loaded
replay first. The media-player's session identity/state must agree with replay
status before play or seek. Progress uses its media-relative seconds directly,
without a second offset calculation or client stopwatch. Slider movement selects
a local destination; a separate button sends one seek command. Zero is a valid
seek target. Backend updates remain authoritative.

A pending service request disables repeated controls in the card. Errors remain
visible without automatic retry. Unmounting discards pending UI bookkeeping and
never stops the backend. A button entity that has never been pressed can have an
unknown state while still being usable; the load/refresh capability check preserves
that distinction. Empty session-list placeholders are not selectable sessions.

Four pure replay tests and two browser cases cover these boundaries, including
renamed entities, stale selection rejection, matching progress, preview/freeze,
keyboard seek, service failure and remount without implicit playback actions. A
mobile control capture was visually inspected. The broad checkpoint passes 136
frontend units and 73 browser cases with the same 101-file deterministic package;
a subsequent availability message for disabled/missing players is checked with
the focused replay suite. Full-bundle byte parity covers all 34 delivered files.

Read-only HAdev inspection found replay idle, no loaded session, an empty session
list and start reference Session live. No real replay service was invoked for this
checkpoint. Manual native verification and active replay/seek integration evidence
remain outstanding while the Mac is locked.

### Historical archive checkpoint (2026-09-14)

The archive module uses the existing catalogue, results and historical-lap
WebSocket commands. Users choose a year, Grand Prix and session in the card or
editor. Editor choices are persistent; card choices are local. Changing the year
or event clears dependent selections. An explicitly unavailable saved event or
session never falls back to another one. Automatic selection chooses the latest
started session supported by the selected content; a scheduled start does not
prove a final result. Unsupported practice/sprint-qualifying results and non-race
lap histories have explicit coverage messages.

Classification, lap-time and lap-position views share the existing table and
chart components. Automatic classification columns use Q1–Q3 for qualifying.
Changing columns selects a custom profile; explicit imported fields also remain
custom unless an automatic profile was requested. The user can choose historical
drivers, lap bounds, series limits and chart/table presentation. Position one is
at the top of the chart. Positions refer to each driver's completed lap, not
simultaneous track location or detected overtakes. Missing laps remain gaps, and
historical lap times are not described as clean pace or sector telemetry.

Historical results now expose additive `driver_id` and `constructor_id` fields
from Jolpica. These allow exact historical identity joins. Older backends can
still display classifications, but their missing IDs never cause a join through
current driver names, reused start numbers or current team logos. The regression
first failed for the two missing keys, then passed with the additive change.
Ruff 0.15.4, its CI profile and 1,551 integration tests passed at that point.
An integration reload alone did not replace imported Python modules. The later
Core restart and fresh identity verification are recorded below.

One shared history resource serves each exact installation/query across cards
and editors. Only selected catalogue/session data is requested, through the
existing backend cache. There is no frontend polling or forced cache bypass.
Failures require explicit retry or reconnection. Closing the last consumer or
changing the selection invalidates late responses. Spoiler protection removes
archive consumers and hides results, controls and chart data. No archive action
loads or starts backend replay.

Five pure tests and three browser cases cover selection, historical identity,
zero values, lap gaps, wrong-session responses, ten shared consumers, cleanup,
retry, keyboard/editor round trips and spoilers. The broad Chromium checkpoint
passed 141 frontend units and 76 browser cases. WebKit exposed a forced-color defect: system-colored text remained on a
fixed dark surface. Shared card/module tokens now set both text and surfaces to
the system palette. All 46 modular browser cases then passed in WebKit and in
Firefox; the complete 76-case Chromium suite also passed again. This is
browser-engine evidence, not manual iOS or screen-reader acceptance.
The final WebKit forced-color stint capture was visually inspected: the shared
surface and text use a consistent white/black system palette, while names,
compound letters, recorded ranges and missing-range messages remain readable.

A related strategy regression now withholds both crossover age and pace when the
estimate lies outside the observed tyre-age range. Age zero remains valid when
included in that range. It passed the focused 11-case analysis suite after first
reproducing the misleading pace value.

Read-only HAdev requests returned the 2024 catalogue, 20 Bahrain classifications
and 1,129 historical lap records. The existing runtime response omitted the new
identity fields, as expected before a Core restart. Frontend delivery was
reloaded successfully and the managed resource changed to `d019d88dbe6d` before
the final forced-color fix. Fresh setup logs show successful coordinator loading
and idle live timing. All 34 frontend files and both edited history Python/test
files were byte-identical across their required copies before that reload.
Native UI verification remains pending because the Mac was still locked.

### Browser performance checkpoint

`frontend-tests/modular-performance.spec.js` exercises a simple overview/weather
card, a detailed timing/lap-history/Race Control card, and ten timing/Race Control
cards sharing one connection. The synthetic field contains 32 drivers with 100
recorded laps each; it deliberately exceeds the observed 22-driver runtime roster.
Twenty timing updates change actual values in each scenario. Tests check the full
field remains visible, shared request/subscription counts, and cleanup without any
service calls. Long tasks are observed across animation frames, including delivery
of observer records after rendering, rather than disconnecting immediately after
an update promise.

The first measurement missed long tasks beginning just before a scenario's start
timestamp. Counting all overlapping tasks revealed an 84 ms ten-card block in an
isolated run (94 ms alongside integration tests). The browser test was corrected
without relaxing the 50 ms threshold. Each card now schedules its pending Lit
update in a browser task, allowing input between cards instead of processing all
dirty cards in one microtask. This runs only when an update is pending; it is not
a polling interval.

After that change, the corrected isolated Chromium test passed. Render durations
were approximately 63 ms, 66 ms and 117 ms. The 95th-percentile update measurement
was approximately 33 ms, including two animation-frame waits. No task above 50 ms
was recorded. Each scenario stayed within the existing 2,500 ms browser render
budget. Ten cards shared two reads and three event subscriptions; after removal,
resource, consumer and handler counts were zero. These are local fixture
measurements, not live-weekend or slow-device
performance claims. Browser heap values were coarsened to 10 MB and do not establish
absence of memory leaks; more precise heap/lifecycle analysis remains outstanding.

### Final archive verification in the development instance

After the update-scheduling change, the broad check again passed 141 frontend
units, 76 Chromium browser cases, 46 modular WebKit cases and 46 modular Firefox
cases. The corrected isolated performance test also passed. The full integration
suite passed 1,551 tests in 381.30 seconds before the final frontend scheduling
change; the scheduling change is covered by the subsequent browser runs.

A configuration-validated Core restart then activated the historical-ID fields.
The F1 entry reported `loaded`. A fresh Bahrain 2024 results request returned 20
driver identities with constructor IDs, and all 1,129 previously fetched lap
records matched those historical driver IDs. No replay action was sent. The
managed frontend resource is now
`/local/f1-sensor-live-data-card/register.js?v=94cb0916e950`. The bounded F1 error
log check contained only two earlier FIA retrieval errors from September 13,
before this restart. This proves backend activation and resource delivery; manual
native card verification remains pending while the Mac is locked.

### Replay telemetry module (2026-09-14)

The twentieth module, `telemetry`, has a shared visual lap picker in the card and
editor. Up to four driver/lap selections are bound to the saved replay session
ID. Changing the loaded replay never silently applies those selections to another
recording. Persistent selections, curve order, time/distance axis and chart/table
presentation round-trip through the existing configuration editor. Card-local
choices remain local. A comparison requires an explicit button action. Opening a
card or editor only reads the lap catalogue; neither starts playback nor downloads
CarData. Demonstration curves are explicitly labelled and use isolated fixtures.

The new additive `f1_sensor/analysis/telemetry_catalog` endpoint scans the local
loaded recording in an executor. It returns bounded driver identities and laps
with recorded start/end boundaries. A catalogue entry does not promise telemetry
coverage. Comparisons accept an optional expected replay session ID, validate it
before and after asynchronous work, and invalidate caches on index replacement or
close. Existing callers remain supported. The catalogue shares one cached scan
per loaded index; card/editor queries share the existing reference-counted query
resources, manual error retry and late-response guards.

Backend regressions first reproduced three misleading calculations: a late lap
could start at the session boundary, distance interpolation extrapolated outside
the reference lap, and speed integration bridged unrecorded intervals. Lap two
and later now require the preceding lap boundary. Delta interpolation is limited
to recorded distance overlap. Distance and delta are withheld for a late first
sample (over two seconds after the boundary), missing speed or a time gap over
two seconds. This is a conservative estimate, not measured track distance. Gap
markers survive final downsampling. Telemetry coverage reflects actual values
instead of always claiming availability. Raw telemetry remains outside HA states.

Speed, throttle, brake signal, gear, raw DRS code, RPM and estimated delta are
individually selectable. Plots use each sample's actual elapsed time or estimated
distance, retain gaps and use distinct line patterns in every palette. Gear,
brake and DRS use steps. A bounded, keyboard-scrollable table shows the same
samples, units and gaps. Forced colors use system foreground and background.
The reference is the first driver/lap in canonical numeric order; the explanation
states delta direction, estimated distance, missing coverage and signal meaning.
Lap controls and explanations collapse after comparison to keep the curves clear.

Verification at this checkpoint: 145 frontend unit tests, 79 Chromium browser
cases, 49 modular WebKit cases and 49 modular Firefox cases passed. The three new
browser cases cover mobile/axe, forced colors, manual comparison and retry, stale
replay responses, spoilers and editor persistence without sample requests. The
release builder produced identical 103-file runtime archives. All 36 frontend
assets match across the primary, bundled and Git copies. The 11 focused Python
telemetry cases and Ruff 0.15.4/CI checks passed; full-suite and running-backend
activation evidence follow when complete.

The development dashboard now includes the separate `recorded-analysis` view
with replay controls, telemetry and 2024 Bahrain classifications/lap charts.
A fresh dashboard API read confirmed hash `0ec5b3b05b9a6ff4`. Native Mac interaction
is still unavailable while locked. The HA screenshot engine is available, but
its initial render of the existing overview returned configuration-error tiles
and `frontend_context_confirmed: false`; it is not evidence of visual acceptance.
The served telemetry data module returned HTTP 200 and matched the primary file.
The resource/runtime investigation remains open at this checkpoint.

### Telemetry activation and native HA verification

The full integration command passed **1,557 tests in 387.26 seconds**. A validated
Core restart activated the new catalogue endpoint; the F1 entry reported loaded.
The endpoint correctly rejected a request with no loaded replay. The final
frontend-only adjustments preserved native disclosure markers, gave WebKit
selects a verified 44 px minimum height, and stopped idle replay from falsely
labelling saved choices as belonging to a different loaded session. That idle
regression failed first and then passed. All 145 frontend units and the three
telemetry browser cases passed again in Chromium, WebKit and Firefox. The final
103-file deterministic package SHA-256 is
`dc83d09cfda68d0f4b07d24a9e067a973f8f630826fcf5e444fe49be8c84e60f`.

The in-app browser became available as an independent surface despite the locked
Mac. It opened the actual authenticated HAdev dashboard successfully. The
ordinary frontend displayed the replay module, telemetry empty state and all
20 Bahrain 2024 classifications. The screenshot engine's configuration-error
tiles did not reproduce there; its own frontend-context flag remained false.
Use the working in-app browser for further native acceptance work. Its tab was
retained for the next turn and the temporary mobile viewport was reset.

Through the new replay module's UI, the session list was refreshed, **Spanish
Grand Prix - Practice 1** was selected and its already cached recording
`2026_1294_11362` loaded. Playback was never started. The catalogue exposed 22
recorded drivers with their own lap lists. Selecting Norris lap 2 and Leclerc
lap 2 and clicking Compare displayed real speed, throttle and brake curves.
A same-query backend read returned 457 and 473 samples, with observed maximum
speeds of 261 and 265 km/h. DRS was correctly unavailable. The last Leclerc delta
was null because its estimated distance exceeded the reference's recorded range.

The actual table and light-mode desktop rendering were inspected. The HA card
editor then saved Norris lap 2, the estimated-distance axis and the additional
gear curve, entirely through UI controls. A fresh dashboard API read confirmed
all four fields, the selected lap, axis and exact replay ID under hash
`e986e3f475b62940`. After a full browser reload the saved selection remained,
Compare was enabled and no plots appeared until it was pressed. Four real curves
then appeared. At a 390 px viewport the document was 379 px wide and the real
mobile view was visually inspected with no page overflow.

Stop replay was pressed through the module. The status and player both returned
to idle, media position zero, session identifiers cleared, and telemetry plots
were removed. An entry reload delivered the final frontend changes through the
managed resource `/local/f1-sensor-live-data-card/register.js?v=845a336ff7cb`.
The entry again reported loaded. A fresh browser reload showed the intended idle
explanation, no erroneous changed-session warning, no plots and no console errors.
The bounded F1 error-log check contained only the two older September 13 FIA
errors, before this work. The development dashboard retains the explicit saved
lap configuration for future replay tests; the backend is left idle.

This closes the local module implementation portion of E2 and the actual resource
packaging/delivery check C8. It does not close full migration, every data/session
profile, all replay seek/lifecycle scenarios, screen-reader/iOS acceptance,
long-run memory measurements or real live-weekend validation. No commit or push
has been made.


### Legacy conversion and exact restoration — 2026-09-14

Plan F1 is implemented. F2 remains open: a valid starting profile is not full
feature parity. `modular/migration.js` supplies pure conversion proposals for all
23 registered legacy types and `f1-session-archive-card`. It accounts for every
explicit source key as transferred, changed or requiring another choice. Unknown
settings, nested actions and extensions remain in the exact original configuration.
The original and its conversion report survive new-card editing and JSON export /
import. Only a supported version-1 backup with a known legacy type can be restored.

`modular/migration-editor.js` is offered through the documented Home Assistant
`getConfigElement` entry point. Existing card implementations and editors remain
registered. The wrapper shows the original editor until the user chooses Review
conversion. It uses labelled demonstration data for preview, an installation
selector, explicit differences, an acknowledgement, Apply and Cancel. Apply emits
a configuration change for the edited card; Home Assistant Save persists it.
Users who want both cards visible duplicate the card in HA before converting the
copy. No dashboard is rewritten on module registration or application startup.
The new editor exposes the exact original for read-only export and an explicit
restore/cancel choice. Restoring uses HA's normal card editor and Save flow.
See the [documented custom card/editor interface](https://developers.home-assistant.io/docs/frontend/custom-ui/custom-card/).

Transferred settings include semantic timing colors, light/dark/automatic mode,
logos, flags, names, selected columns, gap reference, supported sector modes,
history bounds, actions and HA grid/visibility configuration. Short hex and integer
RGB timing colors are normalized without changing their RGB values. Unsupported
CSS color expressions remain in the original and are identified for reselection.
Colors can still be contrast-adjusted by the renderer's accessibility settings.
Symbols/text remain enabled and the established lap-arrow meaning is retained.
A custom spoiler helper, including Weekend Hub's implicit helper, starts the
converted card with content hidden rather than silently discarding protection.
The global integration spoiler source is recognized separately from entry entities.

Known conversion differences remain explicit: hybrid sectors, old header/table
switches, custom per-field sources, legacy badges, shared transient browser context,
fonts, card-specific session visibility and next-race illustrations/history are
not all equivalent. Archive choices must be selected in the new editor; temporary
old-card choices were never in its saved configuration. Unlimited lap columns
become a disclosed last-30-lap history. The document limit bounds records rather
than merely limiting a scrolling viewport. These starting profiles must not be
advertised as a complete replacement for the legacy card family.

The source inventory now also recognizes `this._config` and literal editor
callback keys, including the previously missed timing-color options. It contains
336 direct card setting accesses and 61 editor setting accesses. Computed schema
keys, shared defaults and complete per-setting mapping still require review.

Regression tests first demonstrated key-order-dependent gap conversion, an
incorrectly empty installation select, and WebKit's black text on a dark
transparent review surface in forced-colors mode. Fixes make gap conversion
independent of key order, explicitly select generated native options, and apply
both Canvas background and CanvasText to the shared host in forced-colors mode.
No accessibility rules were suppressed and no visual baselines were replaced.

Verification for this checkpoint:

- Ten migration unit cases cover all 24 starting profiles, recovery after edits /
  serialization, unknown data, action objects, palette conversion, mixed sources,
  spoiler safety, key ordering, bounded history and sector meaning. All 155 frontend
  unit tests pass.
- `npm run test:quality` passes: 82 Chromium browser cases, 40 Python CI tests,
  38 Node automation tests, translations and deterministic packaging.
- The full modular and migration browser suites pass in WebKit (52 cases, 27.4 s)
  and Firefox (52 cases, 34.3 s). Migration includes Swedish, keyboard, 390 px,
  forced colors, axe and absence of integration actions.
- Runtime Ruff 0.15.4 and the CI-equivalent Ruff profile pass. The mandatory full
  runtime suite passes with 1,557 tests in 382.22 s.
- The deterministic release has 105 runtime files and SHA-256
  `02e7432465f43026058e66d5e113e32321cecdf9bd9afb35c5b0d2274077fb60`.
  All 38 delivered frontend assets match byte-for-byte across runtime, integration
  and repository copies. The changed frontend asset manifest also matches.

Native HAdev verification used a new `migration` view on the existing isolated
`f1-modular-development` dashboard. A Practice Timing test card specified light
mode, sectors and three custom timing colors, including blue for personal best.
The real editor reviewed and converted it, HA Save persisted the new card and its
original, and a full browser reload retained the recovery controls. Export original
showed the exact original JSON in a read-only field. Restore original card changed
the editor back to Practice Timing; Save restored the exact original configuration.
API readback matched every original key/value and both preceding dashboard views
were unchanged. The restored dashboard hash is `18c9d4185bdf1ffb`.

After the final resource reload, native UI confirmed F1 was automatically selected
in the conversion chooser. The preview was visually inspected in the light HA
editor and Cancel left the original in place. The browser reported no console
errors. The F1 entry is loaded and the managed resource is
`/local/f1-sensor-live-data-card/register.js?v=9b47b5667e5d`.
A bounded error-log read showed only the previously known September 13 FIA errors;
it does not establish absence of errors outside that window. Replay controls were
not used by this checkpoint.

Remaining next work: complete F2's per-setting/default audit, implement or clearly
bound remaining module fields and session profiles, source-age/context consistency,
shared Live Delay/spoiler controls, full product documentation and the still-open
manual/device/live-session tests. No commits, pushes, PRs or releases were made.

## 2026-09-14 — Independent typography, headings and density

The visual editor now offers a heading font choice independent of the graphic
style: follow the style, the bundled F1-inspired font, or Home Assistant. A font
change preserves the palette, content and layout. The card title and each module
title can be hidden independently. Module titles remain available for heading
navigation; session context, provenance and status badges stay visible. Hiding
the card title keeps focus and reading-pause controls and provides a tap-action
button alongside the existing hold/double-tap alternatives. Demo previews remain
inert.

Table-based modules have a visible column-header switch. The native `th` elements
and `scope="col"` relationships remain; only the text is visually clipped and the
header row spacing removed. Labels remain in all three tested browser
accessibility trees. Chart data tables keep their series labels visible. This
preserves the associations described in the [WAI table guidance](https://www.w3.org/WAI/tutorials/tables/one-header/);
it does not replace manual screen-reader testing.

Compact, Normal and Spacious share spacing across card sections, weather rows and
tables, including nested chart/telemetry tables. The saved `comfortable` value now
has the label Normal and keeps its existing spacing. Compact retains 44 px control
targets and does not reduce table text size. Typography remains local and uses the
already shipped licensed font.

Legacy `show_header`, `show_title`, `show_table_header` and the three supported
`font_style` values now produce explicit conversion choices. Wide and Balanced
become the new heading font with the difference stated; System no longer changes
the whole graphic style. Unsupported font values require review. Conflicting
header flags are evaluated independently of property order. The exact original
is retained for recovery. F2 remains open for complete per-card/default parity.

Verification at this checkpoint:

- All 157 frontend unit cases pass, including serialization, independent module
  visibility, invalid values, the font/style separation and exact original restore.
- All 86 Chromium cases pass through `npm run test:quality`. The modular,
  migration and appearance suites pass in WebKit (56 cases, 24.1 s) and Firefox
  (56 cases, 36.0 s). The new cases exercise actual editor changes/reload, native
  column names, keyboard actions, preview safety, three densities and nine
  font/style combinations, including a 360 px view and axe checks.
- Ruff 0.15.4 and the equivalent CI profile pass (217 files).
- The mandatory full runtime Python suite passes: 1,557 tests in 387.20 s.
- Packaging is deterministic: 105 runtime files, SHA-256
  `a5a52fdec6bca135268ea9fba7a7a422810b0ba96e824f6390a97efbf203b482`.
  All 38 frontend assets are byte-identical in the runtime, integration and repo;
  the frontend manifest is also identical.

The real HAdev Results and championship card was edited entirely in the UI:
Minimal style, Home Assistant heading font, Spacious density, hidden card title,
and hidden title/table header only in its Results module. Save, full reload and
reopening the editor retained all choices. Visual inspection showed the selected
layout with real result rows and logos. Reading pause and resume worked. The
Championship module retained its own visible title and table header. Saved
dashboard hash: `1db3e7fea1765c62`; the archive/replay and migration views are
unchanged. The example configuration is left on the isolated development dashboard.

F1 is loaded after entry reload. Managed resource:
`/local/f1-sensor-live-data-card/register.js?v=5ea369936937`.
No browser console errors were observed. A bounded backend log read showed setup
and idle-source lifecycle messages, with no errors in those returned lines; it is
not a statement about the complete log. No replay controls were used.

Remaining work includes the rest of the graphical controls (such as bounded logo
sizes and surface choices), F2's broader setting/default audit, source-age/context
consistency, Live Delay/spoiler UI, full product documentation and manual device,
screen-reader and live-session acceptance. No commits or remote writes were made.

## 2026-09-14 — Branding, surfaces and progressive appearance controls

Appearance now starts with Style, Theme and Density. Heading/font/surface details
and color/logo details are separate expandable groups. Timing palette overrides
have their own disclosure under accessibility, keeping the default editor shorter.
This is a concrete simplification; usability acceptance with an unfamiliar user
remains open.

Decorative accent choices are Follow style, Neutral, F1, Favorite team and Custom
color. Follow style preserves the previous accent behavior and saved color.
Explicit accents work across the three graphic styles. A team accent uses the
selected installation's driver roster, retains the team name separately from
driver focus, and uses neutral when its color is absent, invalid or conflicting.
The editor explains that fallback. Its demo preview uses the real selected accent
color while timing values remain labelled examples. Accent changes do not modify
semantic timing or track-status colors, focus, modules or columns.

Logos offer Small, Normal and Large frames (24, 32 and 40 px), with bounded image
requests, reserved dimensions and initials while unavailable. Normal retains the
previous image size. Monochrome uses the existing white-logo source and grayscale;
White remains supported for older configurations. A small shared image component
owns loading and fallback state. It resets when the source changes, ignores late
events from a replaced image, and keeps initials visible when a reused driver row
changes to an unknown team. Known historical team aliases still require a separate
season-identity audit; this checkpoint does not certify historical logo accuracy.

Surface choices are Follow style, Defined frame, Soft corners and alternating rows,
and Flat without a frame. Their coordinated corners, frame and row treatment work
with each graphic style, while module dividers and accessible signal text remain.
Timing colors use their own opaque background and readable ink, so alternating
rows cannot change the meaning or contrast of a timing signal. Individual timing
colors can be reset without clearing other overrides. Automatic color inputs now
show the light/dark palette actually used by the preview.

Evidence for B2 is the implemented F1/HA/Minimal rendering, the existing graphics
checks and the new matrix of all three styles with four surface choices in both
light and dark mode. Real HAdev visual inspection confirms the selected style in
the running dashboard. B2 is checked; the broader B-stage usability and manual
accessibility gates remain open.

Verification:

- `npm run test:quality` passes: 160 frontend unit cases, 90 Chromium browser cases,
  40 Python CI tests, 38 Node automation tests, translations and deterministic
  packaging. The focused graphical suites have eight browser cases.
- The modular/migration/appearance/branding suites pass in WebKit (60 cases,
  25.3 s) and Firefox (60 cases, 37.1 s). Added coverage includes progressive
  disclosure, saved choices, changing source colors in preview, independent
  palette reset, missing/conflicting source colors, image-load/fallback/late-event
  behavior, bounded logo sizes, 24 style/surface/theme combinations, eight axe
  surface/theme checks plus forced colors, and narrow-page overflow.
- Runtime Ruff and the CI-equivalent Ruff profile pass. The full mandatory
  runtime Python suite passes: 1,557 tests in 388.73 s.
- The deterministic release has 105 runtime files, SHA-256
  `cdfae09d513176ca140ea5a38106fc1d0bb66ebc55b50413827c0089e71c551f`.
  All 38 delivered frontend assets match byte-for-byte across all three copies.

In HAdev, the isolated Results and championship example was changed through the
visual editor to a McLaren accent, large monochrome logos, soft surface and Normal
density. McLaren is an example choice, not an inferred personal preference.
Two timing colors were entered through the UI; Reset Personal best restored only
that color and left Recorded time at `#775500`. Save, full reload, native visual
inspection and reopened editor all preserved the choices. The rendered decorative
accent was `#f47600`, supplied by the actual roster. Reading pause/resume remained
usable. API readback confirms unchanged modules and shared focus, as well as
unchanged archive/replay and migration views. Dashboard hash:
`6be60e0afecc2d37`.

The F1 entry is loaded and the managed resource is
`/local/f1-sensor-live-data-card/register.js?v=6a37aae1f758`. No browser console
errors were observed. A bounded backend error-log read returned only the two known
September 13 FIA errors, not new errors from this reload. No replay actions were taken, and the branch remains local
and uncommitted. Remaining work includes historical identity, full graphical and
color-vision acceptance, F2 parity, source/context consistency, shared controls,
product documentation and the outstanding device/live-session checks.

## 2026-09-14 — Optional Live Delay and global spoiler controls

The editor can now enable a compact Viewing settings disclosure on a card.
`context.viewing_controls` defaults to false, so existing cards retain their
layout. The closed disclosure shows the saved Live Delay and the actual global
protection state. The controls distinguish the selected installation's live
delivery and automations from the spoiler switch shared by every F1 entry.
Local card masking remains separate and is never overridden by global reveal.

Manual delay uses the discovered number entity and its minimum, maximum and
step. Typing does not write; submitting applies an explicit value, including
zero. A draft cannot overwrite an externally changed setting without first
returning to the current value. Manual writes are disabled during replay or
calibration and when those states cannot be verified. Global protection uses
explicit on/off services. Turning it off requires an inline review explaining
that current results and live delivery can resume across all installations.
Cancel and closing the disclosure leave protection unchanged.

Demo previews, HA's boolean preview, frozen views and disconnected cards cannot
write. Command validation rechecks current discovery and state immediately
before dispatch, and simultaneous cards share a pending lock for the target
entity. Failures leave the displayed HA state authoritative; no automatic retry
or optimistic protection state is introduced. Removing a card does not repeat
a pending action. The panel adds no polling or live-feed subscriptions.

Keyboard focus moves into review and returns after cancel or completion. A
WebKit regression revealed that disabling a pending button could discard focus.
The stable control section now holds focus during the request; completion only
moves it back when it is still in that section. Explicit review/cancel focus
takes precedence. The real HAdev keyboard flow confirms all four transitions.

Verification at this checkpoint:

- `npm run test:quality` passes: 165 frontend unit cases, 95 Chromium browser
  cases, 40 Python CI cases, 38 automation cases, translations and packaging.
- Five focused browser cases cover saved editor configuration, both preview
  modes, zero delay, stale drafts, calibration, global review/cancel/reveal,
  persistent local masking, permission errors, freezing, disconnect, pending
  calls, removal, keyboard focus, 360 px layout, both themes and forced colors.
  The corrected cases pass in WebKit (3.1 s) and Firefox (4.7 s), as well as
  Chromium through the final full quality run.
- Ruff 0.15.4 and the CI profile pass for 217 files. The mandatory runtime suite
  passes: 1,557 tests in 382.95 s. No Python behavior changed after this run;
  the subsequent focus correction was verified in the browsers.
- The release is deterministic: 106 runtime files, SHA-256
  `1e8d010e6438ec0be322cbd679ac9e9f6efb97b066cc618b1c1aa0ddd4f2c6b9`.
  All 39 frontend assets and the frontend manifest match the runtime and repo.

In HAdev, Viewing settings was enabled through the editor on Följ sessionen.
Save and full reload retained it; other cards and views are unchanged. The
editor also serialized existing default values. Dashboard hash:
`05500d58a65d91a6`. Live Delay was changed from 0 to 1, verified after reload,
then restored to 0. Global protection hid sensitive content across the other
cards; cancel kept it enabled, and explicit reveal restored the original off
state. Local freeze disabled the controls and resume restored them.

A Home Assistant restart was required to load the expanded Python asset list:
entry reload alone retained the old in-memory list and did not version changes
inside the new file. The final managed resource is
`/local/f1-sensor-live-data-card/register.js?v=61f218d23c14`, matching the digest
calculated from all 39 files. F1 is loaded after restart. Keyboard activation,
review, cancel and reveal were then verified again in the actual dashboard.
Live Delay is 0, global protection is off and replay remains idle.

Browser console reads were empty before restart. The final read contains one
generic `Object` error at 01:07 UTC during reconnection; the browser tool does not
expose its payload, so it cannot be classified from this evidence. No additional
console entry appeared during the subsequent keyboard validation. The bounded
backend log contains source failures: the FIA season page was unavailable at
02:48 and Open-Meteo returned HTTP 503 at 03:07 (local time). These reads do not
establish completely healthy sources or a clean full log. No identified
viewing-control error appeared in that window.

E4 remains open: guided calibration in this panel, complete delivery-time and
source-age consistency across modules/details/charts, and the full replay/spoiler
acceptance matrix remain to be completed. The rest of the plan, including F2
parity, historical identity, product documentation and manual device/live-session
acceptance, also remains open. The branch is local and uncommitted; no remote
writes were made.

## 2026-09-14 — Guided TV calibration in Viewing settings

The optional Viewing settings panel now contains a Calibrate with TV disclosure.
Users choose Session live or Lap sync through the discovered reference select,
start calibration, wait for the integration's reference and explicitly match
that moment on TV. Matching saves the measured installation-wide Live Delay;
cancel, timeout and session end keep the saved delay. Closing the panel or
navigating away does not cancel the integration's calibration.

The backend exposes a structured idle reason on the calibration switch and Live
Delay number: completed, cancelled, timeout, session_ended, replay or
unsupported_session. Rearming clears it. The switch now also exposes last_result,
so a new outcome and its corresponding saved result arrive in one state update.
The frontend does not parse notification strings or infer success from an older
number attribute. Last calibration includes its completion time. A regression
test covers a new switch result arriving before an older number mirror updates.
Session completion now stops every running calibration reference, including
Session live, which the previous conditional handling missed.

Reference and run identity are revalidated before every command. Stale references,
new attempts, replay selection, lost discovery and disconnected/frozen/preview
cards cannot issue a match. Lap sync requires an active race or sprint; lap zero
is valid and means start of lap 1. Global protection blocks start and match, and
local card protection hides elapsed time, the lap reference and the last result.
An active calibration can still be cancelled. Manual delay and calibration
commands share one installation lock across their separate helper entities.

The measured value follows the backend without browser extrapolation or new
polling. Timer ticks do not invalidate a current command or move keyboard focus.
Only the status is a live announcement; elapsed updates are outside aria-live.
Buttons retain visible focus through requests and completion. Failed reference
changes leave the confirmed selection authoritative.

Final verification after the coherent result update:

- Runtime Ruff 0.15.4 and its CI profile pass for 217 files.
- The mandatory full runtime suite passes: 1,561 tests in 380.96 s.
- Full repository quality passes: 171 frontend unit cases, 99 Chromium browser
  cases, 40 Python CI cases, 38 automation cases, translations and packaging.
- The nine focused viewing/calibration browser cases also pass in WebKit
  (3.8 s) and Firefox (5.4 s). They cover service failures, cancellation,
  timeout/session end, lap references, stale attempts, local/global protection,
  replay, preview/freeze, keyboard focus, 360 px layout, both themes, forced
  colors, axe and Swedish labels.
- The Docusaurus production build passes. Live Delay usage and the new helper
  attributes are documented in the existing feature/reference pages.
- The deterministic release contains 106 runtime files, SHA-256
  `173e3fa76254c3a322c425a88d7ae85f13fd7726be9e775f0f1d45ce553d1d90`.
  All 39 frontend assets and the changed Python files match runtime and repo.

HAdev was restarted to load the final switch metadata. F1 is loaded and its
managed resource is `/local/f1-sensor-live-data-card/register.js?v=a7a7faeb097c`,
matching the digest of all 39 assets. The actual dashboard verified reference
selection, the active-race requirement, keyboard start/wait/cancel and focus
return. Waiting survived a full page reload. Final-version start/cancel was
repeated after the restart; the switch and number both report cancelled/idle,
and Live Delay remains 0. Global protection is off, the reference is Session
live and replay is idle. Dashboard configuration hash remains
`05500d58a65d91a6`; no dashboard configuration changed during this step.

There was no active F1 session during the check, so real TV matching is still an
acceptance gap. Backend stream simulations and browser fixtures cover measurement
and explicit matching, but do not replace that live check. The bounded backend
error-log read contains only the earlier FIA/Open-Meteo source errors. The final
browser log read contains a generic Object error at 01:46:37 UTC during restart
and reconnection; its payload is unavailable through the tool, so it cannot be
classified or described as a clean console. No identified calibration error was
observed in the verified UI flow.

E4 remains open for complete delivery-time/source-age consistency and the full
replay/spoiler matrix. Other outstanding plan items remain open. The branch is
still local and uncommitted; no remote writes were made.

## 2026-09-14 — Timestamp origins, disconnected views and the first user guide

Entity adapters now call Home Assistant's last_updated an update time, rather
than a receipt or track observation. Module context carries the timestamp kind
through rendering: HA state update, browser response/subscription receipt, or
integration snapshot generation. Starting Grid's source_updated_at is generated
inside the integration, so its label is Snapshot generated. The mapping was
checked against starting_grid.py and Home Assistant's state-object documentation.

Timestamp labels include an absolute time and elapsed age. The age describes
that particular timestamp only; it does not classify the underlying observation
as fresh. Missing, invalid and timezone-less values stay unknown. Future values
show a clock-difference explanation rather than zero age. A missing explicit
source timestamp cannot fall back to an unrelated HA update. Timestamp kinds
also remain separate in the field catalogue: relative telemetry time and lap
numbers are positions, not UTC observations; analysis uses subscription receipt.

An explicit HA disconnection now produces a notice on every card, including
frozen cards. Normal modules honor Show explanation, Keep saved data with age
and Hide module. Existing archive/replay/telemetry connection controls remain
available with their own guarded behavior. Reconnecting does not reset module
configuration or silently reset retained values' age. The existing 30-second
render tick updates elapsed labels without adding polling or service calls.
Frozen models keep their captured age under the Reading snapshot notice;
new spoiler protection still invalidates their sensitive content.

The first modular card user guide is at docs/cards/modular.md, linked from the
card overview and sidebar. It covers presets, modules, appearance, accessible
timing meanings, time labels, unavailable-data choices, shared controls and
reviewed migration. It explicitly describes a development preview; it does not
claim complete migration or live/device acceptance or a published replacement.

Final verification:

- Ruff 0.15.4 and its CI profile pass; all 217 files were already formatted.
- Full runtime suite: 1,561 passed in 384.92 s. This step changes no Python code.
- Full repository quality: 175 frontend unit cases, 104 Chromium browser cases,
  40 Python CI cases, 38 automation cases, translations and deterministic packaging.
- Five new browser cases cover timestamp origins/age, missing timestamps,
  clock differences, all three disconnection policies, stable module DOM and
  configuration, frozen views, spoiler changes, Swedish labels, keyboard focus,
  320 px layout and axe with forced colors. They pass in WebKit (5.7 s) and
  Firefox (4.9 s), as well as the final Chromium quality run.
- Docusaurus production build, four documentation build checks and all 15
  documentation browser checks pass. The latter are the existing site navigation
  and presentation checks, not a full usability test of the new guide.
- Release: 106 runtime files, SHA-256
  `9202c2748ac0513b474e2a1a35d1ec06b604b111ede3746a5be3b5933f67fb9f`.
  The managed HA resource is
  `/local/f1-sensor-live-data-card/register.js?v=46bcbe98a850`.

In actual HAdev, the timestamp origins and ages appeared after a full reload.
A brief tab-only network-emulation attempt did not establish an HA socket
disconnection and was restored immediately; it is not counted as runtime proof.
A controlled HAdev restart did show the real disconnected notices and module
explanations while Följ sessionen retained its labelled frozen reading view.
Data returned after reconnection. All cards were in normal, unfrozen state at
the final read; no explicit Resume action was necessary. No dashboard settings
changed, and the dashboard hash remains `05500d58a65d91a6`. F1 is loaded;
Live Delay is 0, global protection is off, calibration is off and replay is idle.

The final browser error read contains one generic Object at 05:00:24 UTC during
restart/reconnection; the tool exposes no classifiable payload. The bounded
backend error-log read contains the previously recorded FIA and Open-Meteo
source failures. These reads do not prove a clean full console or log.

A1 and E4 remain open. Honest update labels do not establish per-field upstream
observation times, source-age thresholds, a common session/seek generation or
cross-entity consistency. A retained entity snapshot also needs further work
when the backend removes its attributes, beyond the verified socket-disconnection
case where HA retains the last states. The full replay/spoiler matrix and manual
live/device acceptance remain open. No new plan checkbox is marked complete.


## 2026-09-14 — Remove display clutter and follow Home Assistant clock preferences

The user's review supersedes the preceding checkpoint's visible update-label
policy. Automatic HA update timestamps, browser receipt labels, generated-snapshot
times and relative update ages are removed from every modular card. Automatic
provider/context credits and the archive attribution footer are removed too.
Meeting/session identity, selected event times, document publication times,
meaningful status notices and explicitly selected analysis evidence remain.
The editor now calls the retain policy Keep saved data. The plan and user guide
reflect this decision; internal timestamp provenance remains available.

The earlier addition made technical provenance too prominent for the requested
simple card experience. Future display work should keep that provenance in the
data contract and show only information that helps the viewer use the card.

All modular clock displays now use one formatter with the HA profile's 12-hour,
24-hour, language and system choices. Language and system behavior was checked
against Home Assistant's [useAmPm implementation](https://github.com/home-assistant/frontend/blob/dev/src/common/datetime/use_am_pm.ts).
The 24-hour cycle renders midnight as 00:00. Calendar times, Race Control and
incident times, documents, map observations, calibration and frozen-view clocks
share this behavior. Local/server/IANA time zones remain supported, including
a schedule's explicit circuit-time choice. Profile changes rerender clock text.

Regression checks reproduced the unwanted update rows and the frozen clock's
incorrect format/time zone before the fix. Seven browser cases now cover removal,
retained/offline/hidden states, frozen views, spoiler protection, narrow Swedish
layout, keyboard/forced colors, all clock formats, profile changes without reload,
midnight and time zones. Two existing overview selectors were scoped to their
region after removing metadata made matching titles appear in another module;
the result-context assertion now expects the context without the provider name.

Runtime verification: reloaded the F1 entry and then the actual HAdev dashboard.
The managed resource is `/local/f1-sensor-live-data-card/register.js?v=e2ebb654fb8b`.
F1 reports loaded. The existing profile is English with Use system locale and
local Europe/Stockholm time; it was inspected and left unchanged. The real
schedule shows 10:30, 14:00 and 13:00, and a temporary frozen view showed 09:06:09.
The card was resumed. Visual inspection confirms clean schedule and result
sections without automatic update/provider rows. No live session was active;
message/document/calibration clock formats were exercised with browser fixtures.
No dashboard configuration was written by this adjustment. The current dashboard
hash is `a03cef41020f9e65`; it differs from the preceding checkpoint and is not
claimed as an unchanged dashboard. A bounded backend error-log window had no
F1 ERROR matches; this is not a claim about all historical logs.

One intermediate quality rerun lost its shared fixture server when a separate
browser run finished. It was rerun with exclusive fixture-server ownership;
subsequent browser engines also run sequentially. This was test orchestration,
not a card failure.

Final verification for this adjustment:

- Ruff 0.15.4 and the CI lint/format profile pass; 217 files unchanged.
- Full runtime Python suite: 1,561 passed in 398.75 s.
- Final repository quality run passes: 175 frontend unit cases, 106 Chromium
  browser cases, 40 Python CI cases, 38 automation cases and translation parity.
- The seven focused browser cases also pass in WebKit (5.9 s) and Firefox (5.1 s).
- Documentation production build, four build checks and all 15 browser checks pass.
- Deterministic release: 106 runtime files, SHA-256
  `ae1a4477e27d568660956d65cfb05252e5e5068954365528804e825a85a071a5`.
- All 39 frontend assets match across the development, integration and repository
  copies after the reload; all modified runtime Python files match the repository.
- `git diff --check` passes. Branch remains `feat/modular-f1-card`, HEAD
  `16345a337b2d784ee156385ba62d4aeea90b5282`. No commit, push or publication.

These three requested adjustments are complete. They do not close the remaining
field-contract, migration, full live/device acceptance or release work in the plan.


## 2026-09-14 — Retain entity data after attributes disappear

The preceding goal turn made concrete progress by removing update/provider
clutter and fixing clock-format handling. This step addresses the confirmed
retention gap in the unavailable-data policy; E4 and E5 remain open.

Eleven entity-backed modules now use a per-card retained-source store: timing,
lap history, tyres/statistics, pit stops, investigations/track limits, weather,
calendar, documents, results/grid, standings and progression. A module with
Keep saved data captures its selected primary source plus the dependencies that
its adapter uses. An unavailable or unknown primary source can reuse that captured
set, so it does not join old timing with newly received driver/tyre values.
The adapter runs again with the current filters and presentation settings.
Driver focus can use the captured roster when the current roster is unavailable.

Available empty data supersedes earlier rows. Disabled or missing sources remain
blocked; switching data category cannot borrow another category's snapshot.
Changing installation/entity mapping, observed session, qualifying part, replay
selection/seek, Live Delay, next event or spoiler state invalidates snapshots.
An unchanged primary entity payload is not recaptured merely because the context
changed. Unknown session/replay identity prevents saved session-data reuse.
Spoiler handling also guards capture itself. Removing the card or replacing its HA connection releases local
resources; storage is in memory only and bounded by configured retain modules.
No HA entity state or service is changed by rendering. Only the selected data
category and relevant dependencies are copied, not every alternative season source.

Four browser regressions cover clearing attributes, continued driver filtering,
an unavailable roster, recovery with empty data, independent retain/explain/hide
policies, session changes, unknown spoiler status and Live Delay changes.
Seven unit tests exercise 18 source/category variants, captured dependency sets,
category changes, disabled/removed modules, qualifying-part changes, replay seek
and backward movement, installation changes and preview isolation.
The first browser regression failed before implementation with all timing rows
lost after attributes were cleared; it passes after the change.

Actual HAdev verification used the real card editor's preview without saving its
configuration. Weather was set to Keep saved data in that preview. In HA's state
tools, sensor.f1_race_f1_weather was temporarily set to unavailable with an empty
attribute dictionary; a connector read confirmed exactly that state. The preview
kept 27.1 degrees C, 47 percent and 3.8 m/s with the saved-data notice. Reloading
the F1 entry restored the actual entity to 27.1 with current_humidity 47 and
current_wind_speed 3.83. The editor was cancelled, edit mode exited and the state
tools tab closed. The dashboard hash is unchanged at a03cef41020f9e65. F1 is loaded.
The managed resource is /local/f1-sensor-live-data-card/register.js?v=9f2f4bd3e02c.

The existing performance fixture now includes ten retain-enabled timing cards,
32 drivers and 100 recorded laps each over 20 updates. That scenario rendered in
83.3 ms, with a measured p95 update duration of 35.2 ms and no recorded long task.
It still used two requests and three subscriptions shared across the cards,
made no service calls and released every snapshot and shared resource on removal.
The browser's rounded heap counters are not proof of an exact memory budget.

Scope still open: this captures a set received by the browser; it does not prove
that all upstream observations are simultaneous or carry a common backend
session/seek generation. A complete backend field contract remains necessary.
The mixed overview needs field-level unavailable handling; stream-based modules
retain their existing separate lifecycle behavior. The full replay/Live Delay/
spoiler matrix and real live/device acceptance are not complete. No plan checkbox
is marked complete solely on the strength of these entity-retention checks.

Final checks:

- Ruff 0.15.4 and its CI profile pass; 217 files left unchanged.
- Full runtime suite: 1,561 passed in 385.89 s.
- Repository quality passes: 182 frontend unit tests, 110 Chromium browser tests,
  40 Python CI cases, 38 automation cases, translations and deterministic packaging.
- Four retention browser cases pass in WebKit (2.9 s) and Firefox (2.7 s).
- The extended performance case passes with the existing budgets (3.6 s).
- Documentation production build, four build checks and 15 browser checks pass.
- Release package: 106 runtime files, SHA-256
  `6ffc17def0db16f62196f63ddb17803c6383cc9db5ca642b9ea3c978196b4a61`.
- All 39 frontend assets match across the three copies after runtime restoration;
  modified runtime Python files match the repository. `git diff --check` passes.
- Branch remains `feat/modular-f1-card`, HEAD
  `16345a337b2d784ee156385ba62d4aeea90b5282`. No commit, push or publication.


## 2026-09-14 — Configuration contract and unknown module isolation

The [configuration contract](modular-configuration-contract.md) specifies the
current v1 schema, module boundaries, appearance, accessibility, validation and
transient state. A separate target v2 specification covers pinned sessions,
phase conditions, context sharing and custom templates; these are not implemented.
A3 is complete as a specification. Other outstanding plan gates remain open.

The catalogue was checked against all 20 module definitions, 98 option rows,
normalized default fields, three JSON examples and relative links. Unknown
modules exposed a regression in retained-source selection: accessing the missing
definition stopped rendering. Optional access now preserves the warning and
configuration while supported modules continue rendering. Two browser regressions
cover rendering, editor changes and configuration round trips.

Checks pass: Ruff and Ruff CI (217 unchanged files), 1,561 runtime tests
(386.38 s), 182 frontend unit tests, 112 Chromium browser tests, 40 Python CI
cases, 38 automation cases, translations and deterministic packaging. The
106-file release package SHA-256 is
`5bdf0034a152c1430963cec5a249a0dd428640b8460be96510c26ab4ef329dc8`.

The actual HAdev editor preview displayed the unknown-module warning alongside
the real calendar. The unsaved edit was cancelled and dashboard edit mode exited.
The saved dashboard hash remains `a03cef41020f9e65`; F1 is loaded and the resource
is `/local/f1-sensor-live-data-card/register.js?v=3190ff315a81`. The normal
dashboard still displays 24-hour session times without update or provider rows.
No commit, push or publication.


## 2026-09-14 — Visual semantics specification (A4)

The [visual contract](modular-visual-semantics.md) fixes status priority,
sector/lap provenance, lap and position comparison meanings, flag identities,
tyre fallbacks and color-independent signals. Issues #404, #530 and #566 were
read directly, including comments, and checked against semantics.js, data.js,
view.js and the existing tests. The contract preserves the user's removal of
update/provider rows and HA clock-format preference.

A4 is marked complete as a specification. Concrete gaps remain explicit: the
full correction/deletion path through backend and retained/frozen/latest views,
all position-column consumers, a compact complete timing explanation and manual
accessibility/session/lifecycle acceptance. No other gate was marked complete.

The 27 existing semantics/data unit tests pass; local document links resolve.
This step changes only the plan and quality documentation, so runtime code and
its previous test results are unchanged. No commit, push or publication.

## 2026-09-14 — Expandable timing explanation

The timing view now has a collapsed-by-default explanation for all seven timing
statuses, their priority, the configured coherent/latest sector-lap mode, lap
arrows and theoretical laps. Native details/summary provides mouse, touch and
keyboard operation with a visible focus outline and a 44 px minimum target.
The existing symbols and accessible status labels remain in the timing cells.
The explanation is informational and makes no backend or dashboard writes.

Two new browser cases failed before implementation. They now pass and cover
Enter/Space, all statuses, focus and open-state retention during HA updates,
serious/critical axe violations, Swedish text, mixed-lap explanation and a
360 px viewport with forced colors. An older accessibility test was adapted
to open the explanation explicitly, retaining checks for symbols in the cells.
The visual contract and plan now reflect this implemented step; broad manual
accessibility acceptance remains open.

In actual HAdev, the F1 entry was reloaded and the dashboard refreshed. The
real card editor's Race demonstration showed the expanded explanation beneath
the timing table; its text and layout were inspected. The editor was cancelled
without saving, then dashboard edit mode exited. Saved configuration hash remains
`a03cef41020f9e65`, the integration is loaded and the resource is
`/local/f1-sensor-live-data-card/register.js?v=dd79dad7121f`.
A bounded scan of the latest 2,000 log lines found no matching F1 ERROR entries;
this is not a claim about the complete historical log or a real live session.

Final verification:

- Ruff 0.15.4 and the CI profile pass, with 217 files unchanged.
- Full runtime suite: 1,561 passed in 387.28 s.
- Repository quality: 182 frontend unit tests, 114 Chromium browser tests,
  40 Python CI cases, 38 automation cases, translations and packaging pass.
- Release package: 106 runtime files, deterministic SHA-256
  `4713e3819d93c8edf58c0081dec13863271d854388f4d62207d25a0c695ff107`.
- All 39 frontend assets match across primary, integration and repo copies;
  modified Python parity is verified and `git diff --check` passes.
- No commit, push or publication. Branch remains `feat/modular-f1-card`.


## 2026-09-14 — Control scope specification (A5)

The [control scope contract](modular-control-scope.md) specifies module/card/group
choices, transient versus saved state, entry-scoped Live Delay/calibration/replay,
global spoiler protection, configured HA actions and inert previews. It includes
priority rules, UI wording, isolation boundaries and the future v2 selection
contract without presenting unimplemented behavior as delivered.

Read current card, connection and viewing-control code, the global switch, and
existing connection/viewing/replay/calibration tests. All 26 corresponding unit
tests pass. Relative document links resolve and git diff --check passes. This
step changes documentation only; no runtime code or dashboard state was changed.

The audit identifies two concrete remaining lifecycle areas: frozen models may
need explicit invalidation on group/context transitions, and replay pending-state
protection is currently per card, not a shared command lock across replay cards.
Neither cross-device synchronization nor distributed command serialization is
claimed. A5 is checked as a specification; C6/C7, D5 and E3–E5 remain open.
No commit, push or publication.

## 2026-09-14 — Shared replay command lock

Replay commands now use the existing shared command helper with an entry-scoped
key on the current frontend connection. Concurrent requests from another card
are not queued or sent; the affected card reports why its command was not sent.
The lock releases on service completion or error, permitting an explicit retry.
Backend state still determines which actions are valid after the call returns.
This does not serialize commands across separate browsers or devices.

A new two-card browser regression reproduced two service calls before the fix.
The final case covers different entity targets (load and refresh), a visible
busy outcome, service failure, retry and successful completion. Existing replay
fixtures now provide a connected HA connection and entity discovery, matching
the real frontend contract. Three focused replay browser cases pass (1.9 s).
The scope contract and plan describe the implemented boundary and remaining
cross-device/full-lifecycle verification. No broader gate is marked complete.

HAdev was reloaded and the replay view inspected visually in its idle state.
No actual replay control was invoked: overlapping commands and failure recovery
were tested with controlled service promises in the browser fixture. F1 is
loaded; dashboard hash is unchanged at a03cef41020f9e65. The managed resource is
/local/f1-sensor-live-data-card/register.js?v=7ddf24a704d0. A bounded scan of the
latest 2,000 log lines found no matching F1 ERROR entries. All 39 frontend assets
and modified Python files match their runtime/repository copies.

Ruff and its CI profile pass (217 files unchanged). Repository quality passes:
182 frontend unit tests, 115 Chromium browser tests, 40 Python CI cases,
38 automation cases, translations and deterministic packaging. The 106-file
release artifact SHA-256 is
`feb2b095b455d72304ab9e10cf16e3619d59c39c1ff1ff589a685a673020461c`.

Full runtime suite: 1,561 passed in 382.63 s. `git diff --check` passes.
Branch remains `feat/modular-f1-card`; no commit, push or publication.

## 2026-09-14 — Coherent frozen group focus

Freezing a card now captures display focus and the driver roster alongside its
models. New group focus is received internally but cannot relabel the frozen
view. A notice explains that Resume follows the changed group focus. Explicit
local driver selection leaves the frozen view and publishes the new selection.
Ending source ownership clears frozen models, focus and roster, including card
removal and connection replacement.

The two-card regression first reproduced the selector switching to Norris while
the frozen timing rows still showed Leclerc. Extending the test to remove a
roster entry exposed an additional select/option update mismatch on Resume.
Driver options now retain identity through keyed rendering with explicit selected
state. The final regression passes (985 ms), covering shared focus, retained
roster, Resume, explicit local choice, removal/reinsertion and no service writes.
The existing frozen-view and HA clock-format cases remain covered by quality.

Actual HAdev verification used Resultat och mästerskap: selected Lando NORRIS,
froze the view, selected Charles LECLERC and observed both selector and results
change with freeze cleared. Restored All drivers afterward. No dashboard save or
integration control was performed. F1 is loaded and saved dashboard hash remains
a03cef41020f9e65. The resource is
/local/f1-sensor-live-data-card/register.js?v=442a7a1ee6b9. A bounded scan of the
latest 2,000 log lines contained no matching F1 ERROR entries. The two-card group
sequence was exercised in the controlled browser fixture, not represented as a
real multi-device test.

Ruff and CI profile pass (217 unchanged files). Repository quality passes with
182 frontend unit tests, 116 Chromium browser tests, 40 Python CI cases,
38 automation cases, translations and deterministic packaging. Release artifact:
106 runtime files, SHA-256
`5a2929a19e6ee447352c7d89efa80f1ce5c2e48b200fa370f272260992af9d55`.
All 39 frontend assets match across three copies; modified Python parity is
verified. Full C7/E5 session, entry and replay-generation acceptance remains open.

Full runtime suite: 1,561 passed in 386.48 s. Final `git diff --check` passes.
No commit, push or publication; branch remains `feat/modular-f1-card`.


## 2026-09-14 — API/version and performance baseline (A6)

Read the current frontend queries, backend schemas, HACS metadata and resource
hashing. The [platform baseline](modular-platform-baseline.md) records protocol
boundaries, missing compatibility proof, outstanding API needs and the test
method. Raw measurements and environment are retained in
[modular-performance-baseline.json](modular-performance-baseline.json).

Ran the existing four-scenario Chromium performance test three times, sequentially
and without retries or changed budgets. Runs 1 and 2 failed the 50 ms long-task
limit for ten shared cards, recording 56 and 55 ms. Run 3 passed. All runs
retained the expected shared request/subscription counts, 32 timing rows, zero
services and complete resource cleanup. The failure is not attributed to a
specific code change without profiling. A final passing run does not close it.

A6 is marked complete as a documented baseline. Performance acceptance remains
open: profile the repeatable threshold violation and fix confirmed card work.
HACS 2024.11.0 is metadata, not validated support for the new platform. No runtime
code changed during this step. JSON structure and relative links were checked;
git diff --check passes. No commit, push or publication.


## 2026-09-14 — Profiled ten-card rendering bottleneck

Two temporary instrumented performance runs captured CDP CPU profiles and traces.
The phase-marked trace places the longest main-thread task in the first rendering
of ten shared cards: 60.82 ms, including Layout 29.46 ms, UpdateLayoutTree 18.93 ms
and PrePaint 8.66 ms. Instrumentation overhead is explicitly distinguished from
the ordinary baseline. No specific source change is blamed without a comparison.

A compact profile artifact and analysis were added to quality documentation.
Temporary profiling test code was removed; runtime code and budgets are unchanged.
The next fix should target first-render layout/style work and retain UI geometry,
focus and accessibility behavior. Performance acceptance remains open.
No commit, push or publication.


## 2026-09-14 — Evaluated rendering optimizations

Four bounded, temporary fixture variants tested host containment, simplified time
cell layout, and card update batches of three/five per frame. Containment and
cell layout retained a 54 ms long task. Three-per-frame passed its one run but
increased ten-card p95 update time to about 100 ms. Five-per-frame reduced that
to about 67 ms but a detailed-view long task reached 58 ms. No candidate is
accepted as a production fix. All outcomes are retained in
modular-performance-experiments.json and the platform baseline.

Temporary test files were removed. Production code, budgets and ordinary tests
are unchanged. Performance acceptance stays open. No commit, push or publication.


## 2026-09-14 — First-layout batching verified

The production first-render queue releases at most three new cards per animation
frame. Existing module nodes retain ordinary update scheduling. Removing a
queued card cancels its slot and resolves the update promise; a dedicated
regression verifies removal and reattachment. Fixed table layout and lazy timing
legend experiments were rejected (50 and 52 ms); neither changed production.

Three ordinary performance runs passed unchanged budgets. Ten shared cards
rendered initially in 150.0/150.1/166.5 ms, with p95 updates 33.9/33.8/33.4 ms
and no recorded long task. Initial latency increases versus the original
116 ms baseline; ongoing update latency remains around 34 ms. Measurements
and limitations are in modular-performance-after-initial-batching.json and
modular-platform-baseline.md. Broader device and lifecycle gates remain open.

Ruff and Ruff CI passed with version 0.15.4. The same running full runtime suite
completed with 1561 tests passing in 391.40 seconds. Repository quality passed:
182 frontend unit, 117 Chromium, 40 Python CI and 38 automation tests, translation
validation and deterministic packaging of 106 runtime files. Release archive
SHA-256: a540daa17217e36fb77929d1e299df6b8b5b7d8c27dabb394acb9a180bebc91b.

HAdev was reloaded and all four saved modular cards visually checked. Entry
01KQQPEAVZ5PKT57H1WYFWEZXR was loaded; dashboard hash a03cef41020f9e65
remained unchanged. Resource version be7ed947dad7 was active. A bounded scan
of the latest 2000 log lines returned no matching F1 Sensor errors; this is
not a historical or live-weekend guarantee. Idle session waiting states were
expected. All 39 frontend assets were verified identical in development,
integration and repository copies. No dashboard save, replay service, commit
or push was performed.

## 2026-09-14 — Legacy option audit linked to coverage

Added a reproducible audit joining all 23 legacy cards and the archive alias to
their static card/editor settings and actual converter report targets. The
source inventory now also records the alias wrapper's own config accesses.
773 isolated representative input probes cover 377 card/key entries, preserving
the exact original in every conversion backup. 97 entries returned only review
for the sampled values. Detailed observations, Swedish explanations, source
lines and input hashes are retained in legacy-migration-audit.json; the Markdown
companion exposes the per-card review queue.

This is observed converter behavior, not semantic or complete value-domain
acceptance. Computed keys, shared helpers, implicit defaults, combinations and
real UI equivalence remain open under A2/F2. The plan links the audit and keeps
A2 unchecked. Generator reruns produced byte-identical artifacts; JSON and
relative links validated. All eleven migration unit tests passed again against the final
inventory, including the expanded alias metadata. No runtime
code changed in this audit step; no additional reload is required.


## 2026-09-14 — Indirect legacy configuration discovery

The source inventory now follows class-local method arguments to dynamic config
access and HA selector schemas, and records literal getStubConfig keys. Source
lines and extraction kinds are retained as indirect_evidence. This adds 47
card/key entries: the weather card now exposes six keys instead of one, the
live-session card 18 instead of seven, and replay controls 22 instead of ten.
The combined audit now covers 424 entries with 867 explicit probes; 122 entries
return only review for these probes. Counts include the results archive alias.

Three new parser regressions cover multi-hop propagation, selector/stub discovery,
recursive termination, argument positions and exclusion of labels/unrelated
receivers. Full automation checks passed (40 Python CI and 41 Node tests), plus
11 migration unit tests. Regeneration is byte-deterministic, all recorded source
hashes match and generated links resolve. git diff --check passed.

The parser is deliberately bounded: full lexical-binding analysis, shared
functions, runtime mutation, defaults and full value domains remain unverified.
Computed-access records stay visible even when known literal callers have been
identified. A2 remains open and its counts/link are updated in the plan. This
step changes only inventory tooling, tests and quality documentation; runtime
code is unchanged. Local branch feat/modular-f1-card; no commit or push.


## 2026-09-14 — Calendar detail and elapsed-start options

The Schedule module now exposes event details (round, circuit, location), past
start handling (show, mark, hide), and a next-session label in the visual editor.
The current simple defaults remain unchanged. Past means published start time
has passed, not that a session has ended. The comparison uses the card clock
(or demo time), with normal 30-second updates; frozen cards retain their picture.
Missing details are omitted. If filtering hides every selected session, the
empty state explains that fact instead of claiming no published times exist.

The legacy Season Calendar conversion now selects races only and preserves
round/circuit/location choices. Combined hide/dim/highlight choices are evaluated
together independent of object-key order. Text marking replaces opacity-based
dimming while retaining readable contrast, and the migration report discloses
that presentation change. All six former review-only display keys now have a
conversion path; the representative audit review count drops from 122 to 116.
This does not close full calendar or migration acceptance, including flag
rendering, shared defaults, date-only source records and the complete matrix.

A new data regression was observed failing before implementation. It now checks
exact-start boundaries, next-session selection, past filtering and circuit/location
source shapes. Migration regressions cover all boolean combinations in both
property orders and exact restoration. The browser test changes options in the
editor, reloads serialized configuration, verifies narrow layout, runs axe and
checks past/next/all-hidden states. Final quality passed: 184 frontend unit,
118 Chromium, 40 Python CI and 41 automation tests plus translations and a
deterministic 106-file release archive. SHA-256:
c1ecdc9ebe20ab2d12c2bed05a04c1470449c254d0dcecb19a43604998ce4bf3.

Ruff and Ruff CI passed with 0.15.4. The same full runtime test process
completed successfully: 1561 passed in 382.89s (0:06:22).

HAdev's real editor exposed all new choices. Unsaved preview displayed round 15,
Baku City Circuit, Baku/Azerbaijan and the next-session label; the internal demo
preview was also visually inspected. Changes were cancelled. After the final
resource reload, the normal dashboard was visually checked, entry
01KQQPEAVZ5PKT57H1WYFWEZXR was loaded, resource a7e7fce0f7cc was registered,
and saved dashboard hash a03cef41020f9e65 remained unchanged. The bounded
latest-2000-line log scan returned no matching F1 Sensor errors. All 39 frontend
assets match across development, integration and repository copies. No commit,
push, dashboard save or replay service was performed.


## 2026-09-14 — Calendar flags and image recovery

Calendar rows now render their already-validated flag URL when appearance.flags
is enabled. This closes the previously recorded mismatch where the legacy
show_country_flag choice was transferred but no calendar image was rendered.
Country names are image alternative text. A load failure hides the broken image
and displays the country name; a later successful source restores the image.
Disabling flags removes both the image and its fallback without removing times
or other chosen event details. Images retain explicit dimensions and lazy loading.

The new browser regression failed before implementation because no calendar
flag existed. It now verifies image loading, failure, source recovery, flags off,
320-pixel layout and axe with forced colors. Final repository quality passed:
184 frontend unit, 119 Chromium, 40 Python CI and 41 automation tests, translations
and deterministic release packaging (106 files). Release SHA-256:
655e1aa6ef5859dd68b1a1a3324c9fdf90e48cd3126819a1a480fd9f21f5fead.

HAdev's normal saved overview was reloaded and visually inspected with Azerbaijan
flags alongside all five weekend sessions. Entry 01KQQPEAVZ5PKT57H1WYFWEZXR is
loaded; resource ed3213f092ca is registered. Dashboard hash a03cef41020f9e65
is unchanged. No F1 Sensor errors matched the bounded latest-2000-line log scan.
All 39 assets are byte-identical across development, integration and repository.
The configuration contract and plan describe flag behavior. No dashboard changes,
commit, push or service actions beyond the integration reload were performed.
Ruff and Ruff CI passed with 0.15.4. The same runtime process completed:
1561 passed in 384.05s (0:06:24).


## 2026-09-14 — Published dates without start times

Schedule rows now retain valid published dates when a timezone-qualified start
is unavailable. The view shows the unchanged calendar date and an explicit
missing-start-time label; it does not display midnight or a fabricated timezone.
Invalid dates are excluded. Incoming valid start times replace the date-only
presentation and use the user's HA time format and timezone.

Date-only past filtering uses the circuit's local date when its zone is valid.
Without that zone it waits until the published day has ended worldwide (UTC−12).
Dates are sorted by day while their within-day order remains unknown. A next
label is suppressed if an unexpired untimed session could precede the earliest
known start: compare dates in its circuit zone, or conservatively use UTC+14
as the earliest global boundary. These internal bounds are never shown as times.

Two data regressions failed before implementation. Tests now cover invalid dates,
unknown order, circuit-midnight boundaries, missing/invalid timezone, date-only
start fields, naive timestamps and malformed non-string values. Browser coverage
checks that Los Angeles display does not shift a published date, contains no
clock/AM/PM before a time arrives, updates to HA 12-hour time after publication,
and restores the next label only when order is known. Axe passes.

Repository quality passed: 186 frontend unit, 120 Chromium, 40 Python CI and
41 automation tests, translations and deterministic packaging of 106 files.
The final additional malformed-value assertions passed in the 21-test data suite.
Archive SHA-256: e443b088e597111a5dc4b9796580e378ced118e9c0ebad7763a642860896b0c0.
Ruff and Ruff CI passed with 0.15.4. The same full runtime process completed:
1561 passed in 383.97s (0:06:23).

HAdev's normal calendar was visually checked after reload. The actual season
entity sensor.f1_race_f1_current_season contained 23 races and no published
date-only session records at inspection, so date-only rendering evidence is
from controlled browser fixtures, not a claimed live feed observation. The
integration is loaded, resource version 7b174d6e9523 is active, dashboard hash
a03cef41020f9e65 remains unchanged, and no matching F1 errors appeared in the
bounded latest-2000-line scan. All 39 assets are identical across three copies.
Plan and configuration contract are updated. No commit, push or dashboard save.


## 2026-09-14 — Shared legacy option provenance

The static inventory now associates explicit entity auto-binding registrations
with each card, including discovered f1_entry_id and literal source suffixes.
Function-valued bindings remain labelled dynamic for review. Shared font and
spoiler installers are traced through explicit arrays, including the existing
optional track-map registration; class-local calls to the shared theme/font
editor helpers supply their corresponding settings. The inherited archive alias
continues to include the parent evidence.

This identifies 82 more card/key entries. The audit now covers 506 entries with
1076 representative probes; 116 entries still return only review. All additional
entries have converter report paths for at least one sampled value, which is not
proof of rendered equivalence or full input-domain coverage. Source lines, helper
kind and binding suffixes are retained as shared_evidence. Source hashing now
also includes platform/entity-resolver.js. A2 remains open for unhandled helpers,
defaults, dynamic behavior and semantic verification.

The new parser regression checks installer scoping, optional class membership,
unrelated classes and dynamic binding disclosure. Full automation validation
passes with 40 Python CI and 42 Node tests; all 12 migration unit tests pass.
Regenerating the artifacts yields identical bytes; hashes and links validate.
Only inventory tooling, tests and quality documentation changed in this step;
runtime assets are unchanged. Plan counts and links are current. No commit or push.


## 2026-09-14 — Automatic weather source contract

Reviewed the old prefer_live_weather behavior against the new adapter, field
registry, spoiler gate and retained-source selection. The old card selects a
whole current-weather block independently of race forecast, including a special
missing-status fallback. The new manual source modes do not reproduce that
automatic behavior. A naive late overlay would bypass source-dependent snapshot
and spoiler decisions.

Added modular-weather-source-contract.md with a concrete implementation order:
a shared resolver before protection/snapshot selection, source-correct fields,
separate current and race-forecast module instances, clear replay/event identity,
source-change invalidation, explicit migration differences and a full acceptance
matrix. It also identifies the existing first-weather-module find() assumption:
show_weather must affect both weather blocks after conversion. Unknown status
should not infer active live weather; this deliberate difference must be reported.

The contract is expressly not implemented. D2 links it and remains open. Existing
data, migration and retained-source tests passed (40 tests); this confirms the
examined baseline, not acceptance of the proposed automatic mode. Relative links
and git diff --check passed. No runtime code changed, and no reload, commit or
push was performed.
# 2026-09-14 — Automatic weather source selection and disconnected snapshots

The local automatic weather profile now resolves the current block before spoiler
checks and retained-source selection. Confirmed active sessions with usable track
measurements use one track source; inactive/unknown sessions use current weather.
Unsupported or missing fields remain missing instead of borrowing forecast values.
Race-start forecast remains an independent module.

A new regression reproduced a silent switch to forecast on HA disconnection.
Source selection now checks the exposed entity availability separately from the
connection-dependent presentation status. The offline block can retain its track
snapshot without claiming live availability. Unit and browser regressions verify
that ending the session changes the source and prevents reusing that track snapshot
as current forecast data. Reconnection displays the newly selected source, and the
browser test records no service calls.

Validation: npm run test:quality passed (40 Python automation tests, 42 Node
automation tests, release checks, 188 frontend unit tests and 120 browser tests).
The subsequently added automatic-weather browser regression passed with all five
data-time browser cases. Migration inventory/audit artifacts were regenerated:
506 card/key entries, 1076 probes, 116 review-only. Runtime source copies were
checked for byte parity. No commit or push was made.

Still pending for this weather increment: full runtime Python/Ruff checks, HAdev
reload and visual verification, editor save/reload, source-switch freeze/spoiler
matrix, paired migration/templates and unit conversion comparison. This checkpoint
does not complete D2 or the overall implementation goal.


## 2026-09-14 — Paired weather migration and source protection

Weather and Next Race conversion now creates a current-weather module and a
separate race-start forecast module. Explicit false prefer_live_weather selects
current_conditions; true or the omitted default selects automatic_conditions.
The show_weather flag applies to both module IDs, which are listed in the report.
The report discloses the confirmed-active-session requirement, and the exact
original remains recoverable. Other legacy weather settings remain subject to
the migration audit; this is not a claim of full old-card parity.

Unit coverage exercises 36 combinations of card type, omitted/true/false settings
and property order. Browser coverage reviews the difference, applies conversion,
recreates the editor from serialized configuration and restores the exact original.
A separate browser case verifies frozen automatic source selection and removal of
frozen track observations under unknown spoiler protection while the forecast
remains visible. No service calls are issued by these tests.

Validation: quality passed with 40 Python automation, 42 Node automation, 189
frontend unit tests and 121 browser tests. The subsequently added migration and
weather-protection tests passed in their complete files (four and six cases).
Both Ruff workflows passed. Migration audit: 506 card/key entries, 1076 probes,
114 review-only entries. All 32 JavaScript assets matched across development,
integration and repository copies before reload. git diff --check passed.

HAdev: entry reload succeeded; entry reports loaded. The managed resource is
register.js?v=0db6c5b7b5ad. Browser reload restored the normal dashboard and visual
inspection confirmed existing weather/schedule content without update or provider
rows. No F1 ERROR matched the bounded latest-2000-line log window. No actual
active-session source switch or weather conversion was performed on the saved
dashboard; those paths are fixture-tested. The dashboard configuration was not
changed. Full runtime test result is recorded below when the running suite ends.

Remaining: paired new-card templates, conversion of units, automatic editor
round-trip with user field changes, broader source/generation/protection matrix
and actual weather-mode acceptance in HAdev. No commit or push.

Full runtime suite completed successfully: 1561 passed in 381.75s (0:06:21) (`/Volumes/config/./scripts/run_tests.sh`).


## 2026-09-14 — Weather templates, units and editable preview

The Weather comparison template and new Race weekend templates now contain an
automatic current block plus a separate race-start forecast. Existing saved
module configurations are not rewritten. Choosing a template in an empty editor
now selects its first module, matching the replacement flow and exposing its
settings immediately. A browser regression reproduced the missing selection.

Temperature and wind measurements convert from their field-specific raw units
to HA units. The existing sensor temperature override (unit_of_measurement) takes
precedence when it is Celsius, Fahrenheit or Kelvin. Supported conversions match
the legacy temperature/speed conversion families. Missing values and zero remain
distinct; unknown source/target units preserve raw values and labels rather than
relabeling unconverted values. Tests cover Celsius/Fahrenheit/Kelvin, m/s, mph,
km/h, source units, unknown units, automatic track selection and race forecasts.
Remaining speed aliases/Beaufort boundary coverage is not claimed by these cases.

Two new browser tests prove template selection, custom field/layout choices and
full serialized reload, plus dynamic HA unit changes in both weather blocks.
During actual HAdev preview, the source explanation was too prominent for the
requested simple display; it now lives under About the weather data. A short
Current weather/Track observations/Recorded replay badge identifies the selected
source. Forecast keeps its separate badge. No update/provider rows were added.

Validation: final quality passed (40 Python automation, 42 Node automation, 190
frontend unit tests, release checks, 125 browser tests). Both Ruff workflows pass.
Full runtime suite: 1561 passed in 377.41s. git diff --check and final JavaScript
byte parity across all three copies pass. Inventory/audit regenerated (506 keys,
1076 probes, 114 review-only). No commit or push.

HAdev: reload succeeded, entry loaded, resource register.js?v=42ddf51bb33e.
The actual card editor displayed the new template and automatic source selector.
Its real-data preview showed Azerbaijan current weather 27.7 degrees Celsius and
4.4 m/s, separately from race-start forecast 26 degrees Celsius and 3.7 m/s.
Screenshots confirmed both blocks and collapsed source details after final reload.
Both temporary edits were cancelled; the original Weather overview remained on
the saved dashboard. No F1 ERROR matched the latest bounded 2000-line log window.
Live/replay source changes and alternate HA unit settings remain fixture-tested.

Remaining weather work: full source/session/replay-generation/Live Delay matrix,
active-session and replay acceptance in HAdev, clearer distinct module names in
the editor (currently Weather appears twice), and any additional legacy display
settings still marked for review. This does not complete D2 or the full plan.


## 2026-09-14 — Content names and weather generation boundaries

The editor, template summaries, replacement review and move buttons now use the
same content-specific names as rendered modules. Weather overview, automatic
current weather and race-start forecast are distinguishable. Existing incident,
strategy and battle content titles share the same resolver. User-authored titles
take precedence. Browser tests cover custom titles across reload, Swedish names
and reordered weather modules. HAdev editor and screenshots verified the template
summaries and Weather overview module name; editing was cancelled.

A new browser regression reproduced old track weather being relabelled under a
new session before a weather update. A weather generation barrier now records the
previous source payload across session, replay and delay changes. Both automatic
and manual track modules wait for a new update, while separate forecast modules
continue. Recreated state objects with unchanged payload do not release the barrier.
Unit coverage includes session and delay changes, seek/backward movement, ordinary
forward playback, recreated states and new-payload recovery. Freeze behavior across
all replay/delay changes and initial-load freshness remain outside this proof.

Final quality passed: 40 Python automation, 42 Node automation, 190 frontend unit
tests and 128 browser tests. The subsequently added generation-boundary unit case
passed with all nine retained-source tests. Both Ruff workflows passed, and the
full runtime suite result is appended below when its live process ends. All JS
assets match across three copies, git diff --check passes, and migration audit
remains 506 keys / 1076 probes / 114 review-only after regeneration.

HAdev reload succeeded, entry loaded, resource register.js?v=4f1b5f9b25f0. The
normal dashboard returned after reload with current weather 27.7 degrees Celsius;
no saved dashboard configuration was changed. Sessions/replay discontinuities
were fixture-tested, not forced in the running integration. No commit or push.

Full runtime suite completed: 1561 passed in 377.73s (0:06:17).


## 2026-09-14 — Frozen context changes remain explicit

A frozen card now captures its view generation alongside the models, focus and
roster. A later session/replay/Live Delay generation change adds a notice inside
the frozen-state message. The frozen values and their original context remain
readable until Resume; this does not automatically resume updates or send an
integration action. Existing spoiler protection still overrides the snapshot.
Freeze refreshes the generation against the same current HA input before building
models, so a pending UI render cannot mismatch the captured data and generation.

Browser regressions first reproduced the missing session/delay notice. They now
verify original values and meeting identity, the notice, explicit Resume to new
data and zero service calls. Added replay-backward coverage also passes. The
complete data-time and frozen-focus files pass all 12 cases, including prior
spoiler, source-discontinuity, reconnect, group-focus and accessibility cases.

Quality passed with 40 Python automation, 42 Node automation, 191 frontend unit
tests and 130 browser tests before the additional replay case; the complete two
files passed again afterward. Both Ruff workflows pass. Full runtime result is
recorded below once the ongoing suite ends. JavaScript parity and diff checks
pass. No new files were added to the runtime bundle.

HAdev was reloaded. The ordinary overview was frozen and visually inspected: its
original context stayed visible and no false context-change notice appeared.
Resume restored normal viewing. Actual session/replay/delay settings were not
changed; these transition paths are fixture-tested. No dashboard save, commit
or push. Remaining acceptance includes broader mixed-module entry/connection
transitions and live/replay validation against the complete plan.

Runtime confirmation: F1 entry loaded with register.js?v=99e8b5764f42. No F1 ERROR matched the latest bounded 2000-line log window.

Full runtime suite completed: 1561 passed in 383.83s (0:06:23).


## 2026-09-14 — Independent module focus and bounded session completion

Modules can now inherit card focus or use independent driver/team selections.
Empty independent selections mean all competitors. Editor labels and an Own
selection notice explain the scope. Two browser regressions cover grouped cards,
conflicting selections, editor serialization and reload. The configuration unit
file also verifies defaults, duplication, import/export and invalid values.

Final quality run passed: 40 Python automation tests, 42 Node automation tests,
191 frontend unit tests and 133 browser tests. After adding one configuration
unit test, all nine tests in that file passed. Both Ruff workflows passed. The
full runtime suite passed 1561 tests in 378.39 seconds. JavaScript parity and
migration audit were checked: 506 keys, 1076 probes, 114 review-only probes.

HAdev was reloaded with register.js?v=2790fab22d8b. In the actual HA editor,
independent Results retained multiple competitors when card focus selected
Norris, while inherited Championship showed only Norris. The unsaved preview
was cancelled and the normal overview restored. The integration is loaded.
No F1 ERROR matched the latest inspected bounded 2000-line log window; this is
not an assertion about all historical logs.

The user explicitly narrowed the session goal to a working local version,
overall testing and an actionable remaining-work list. No further feature
expansion or repeated full suite is required for this documentation handoff.
The original plan now distinguishes completed session criteria from future
product/release acceptance. Remaining tests, development and release gates are
recorded in /Users/niklas/GitHub/F1_SENSOR_KVAR_ATT_GORA_2026-09-14.md.
The local v1 is delivered; complete legacy parity, real-device/live-weekend
acceptance and stable release are not claimed. All work remains uncommitted
on feat/modular-f1-card. No commit or push was performed.


## 2026-09-15 — Complete generated field catalog

The delivered module registry now gives every base field an explicit generation
boundary in addition to its source path, capability, modes, sessions, identity,
time provenance, freshness, unit and presentation. A deterministic generator
resolves content-dependent definitions for archive, weather, incidents, results,
standings, tyres, strategy and battles instead of documenting only their base
field definitions.

The generated Markdown and JSON catalog covers 129 field IDs, 20 modules,
41 module variants, 277 resolved field rows and 30 resolved sources. Automation
fails when a field is missing required contract metadata, is not exposed by any
module variant, references an unknown field, or the checked-in catalog is stale.
Focused catalog, configuration and time-provenance checks pass (15 tests), and
the three delivered catalog.js copies are byte-identical. The pre-change broad
quality baseline also passed 40 Python automation tests, 42 Node automation tests,
192 frontend unit tests and 133 browser tests. No commit or push was performed.


## 2026-09-15 — Reusable personal templates

The editor now exports a separately versioned, named F1 Sensor template instead
of treating raw card JSON as the only reuse mechanism. Pasted JSON and local JSON
files enter a review state that compares the current and incoming module content;
the card is unchanged until Apply. Applying uses the existing bounded undo history
and never saves the Home Assistant dashboard by itself.

A template that names an installation unavailable in the receiving system cannot
be applied until the user explicitly maps it to a discovered installation. The
saved ID is never silently replaced. Raw card JSON remains available in a separate
advanced section for compatibility. Focused validation passes 10 configuration
tests and two browser flows, including exact round trip, invalid formats, review,
undo and missing-installation mapping. The primary, runtime and repository copies
of config.js and editor.js are byte-identical. No commit or push was performed.


## 2026-09-15 — Configuration version 2 session identity and phase profiles

Configuration version 2 now adds typed card and module session selection, explicit
group sharing scope and per-module phase visibility. Existing version 1 cards are
normalized forward with automatic following, inherited module selection, all four
phases and focus-only sharing; their field selections are unchanged. Invalid union
members, identifiers, phases and future versions are rejected with a setting path.

Pinned live data is shown only when season, meeting and session keys match the
current integration state. Pinned replay also requires the exact loaded recording.
The current-session and replay entities now expose these identity components.
Archive pins resolve opaque meeting and session keys through the history catalogue;
an archive pin on another module is explained as unavailable instead of falling
back to current data. Selecting or pinning never loads replay or starts a live
source. A module pin wins over a card pin, a card pin wins over a shared temporary
selection, and group messages still cannot carry integration commands.

The visual editor offers source following, available live/replay/archive pins and
Before, Active or interrupted, Finished and Unknown phase switches. Hidden phases
remain saved and are excluded before missing-data policy and stream setup. Final
validation passes 52 focused backend identity tests, 198 frontend unit tests, 139
browser tests, 40 Python quality tests, 44 Node quality tests and the full 1,561-test
runtime suite. Docusaurus production build, four documentation structure tests and
15 documentation browser tests also pass. The 21 modular JavaScript files are
byte-identical in the primary, runtime and repository copies.

The 134 functional and accessibility browser flows that do not compare against
Chromium-specific reference images also pass in Firefox and WebKit. The four
excluded checks compare complete screenshots created by Chromium; an initial
Firefox run otherwise passed 134 tests and differed only in those four engine-
specific images. This cross-engine result does not replace physical Companion App
or screen-reader acceptance.

The integration was reloaded in HAdev. The native visual editor exposes card and
module session selection, all four phase controls and opt-in temporary session
sharing. The group option was enabled only in an editor draft to reveal its session
control, then Cancel was used and dashboard editing was closed without saving. No
dashboard configuration, replay state, commit or remote branch was changed.

The HAdev log view was checked after the reload. Filtering for F1 Sensor showed
only the two existing FIA-document availability entries from 2026-09-14 and no
new reload or configuration error on 2026-09-15. The filesystem fault log is empty
and last modified on 2026-09-14, so it is not treated as fresh runtime evidence.

Native replay acceptance then used the actual 2024 Abu Dhabi Grand Prix Practice
1 recording. The modular card downloaded the 1:06:40 session, reached Loaded,
started playback, advanced its authoritative position, moved forward 30 seconds,
paused and stopped. The card returned to No replay loaded; the replay year was
restored from the temporary 2024 selection to its original 2026 value. The same
native view rendered the real 2024 Bahrain Race classification with all 20 rows.
No dashboard configuration was edited or saved during this test.

A second cached run kept replay active while the overview was inspected. The map
rendered Abu Dhabi geometry, 20 labelled drivers and an accessible 20-row status
list with recorded times. The tyres module identified the same Practice 1 context,
and the timeline exposed replay-backed Race Control, radio, weather and lap events
with their source labels. The replay was stopped again and the year restored to
2026. This is one real recorded-session variant; it does not establish every
circuit, missing-position pattern or live-session transition.

Migration acceptance now also loads the actual `getStubConfig()` output from all
23 legacy custom elements and the archive alias. Each of those 24 standard
configurations converts without a configuration warning, accounts for every
source key and restores the exact original after review. The regression passes in
Chromium, Firefox and WebKit. Driver-column visibility, team-name visibility,
archive position change and FIA-document order now retain their supported legacy
meaning; focused migration browser runs pass all five cases again in Firefox and
WebKit. The first mapping pass reduced the audit from 114 to 106 review-only
settings. Replay Control now also retains twelve discovered entity bindings and
the supported full/compact, secondary choice, start-reference, seek, refresh and
scope-detail settings. Custom entity overrides remain review-only, and visible
button names remain available for accessibility. FIA Documents now also retains
the supported list/latest presentation, link target, race context, document count,
latest marker, bounded list height, type, color signal, FIA mark and PDF icon.
Starting Grid now retains its grid/table presentation, event/status visibility and
grid/qualifying comparison fields. Race Control retains blue-flag and track-limits
filters, FIA mark and effective list height. Its compact view retains each message
for the configured 0–30 second minimum. List mode clears the saved session log only
after a second explicit click and only through the discovered Race Control entity;
preview and frozen views remain read-only. The removed automatic source badge remains
an explicit review item. Season progression now retains legend visibility and placement,
legend totals, chart points, round labels, future-round visibility and bounded chart
height. Hiding future rounds removes only the unobserved tail and preserves missing
rounds inside the observed season. Historical lap-position charts retain their point,
lap-label and bounded-height choices. Result, archive and lap-position migrations
also retain whether their race or archive selectors are visible. The resulting
audit covers 506 keys with 1,074 representative probes and 52 review-only
settings. This closes the standard-default sample, but not semantic parity for
every dynamic legacy combination.

The final repository quality rerun passes 40 Python automation tests, 44 Node
automation tests, the deterministic 106-file release package, 206 frontend unit
tests and 147 Chromium browser tests. All 143 browser flows that do not depend on
Chromium-specific reference images also pass in Firefox and WebKit. No commit,
push, release or dashboard save was performed. HAdev's actually served visual
editor exposes both the minimum display time and clear-button settings for Race
Control. After reloading the integration it also exposed all new progression
legend, point, round, future-tail and height controls and the archive point,
lap-label and height controls. The actually served Results and Historical archive
module editors also expose `Show round selector` and `Show archive selectors`.
Both previews rendered real historical data. The
temporary drafts were cancelled and dashboard editing was closed without saving
or clearing the live log. The refreshed HA log view contained only the F1 Sensor
FIA-document request timeout from 03:32:17, the previous-day FIA availability
warning and a cancelled first entry setup attempt at 14:51:23 while its FIA request
was pending. A second uninterrupted reload loaded F1 and delivered
`register.js?v=dd2fa1cd46f0`; no later card, configuration or reload error appeared.

The next migration increment retains the Driver Lap Times and Race Lap live gap
control. Viewers can switch one accessible timing column between the car ahead and
the leader without changing the saved column configuration. The old Practice editor
offered the same setting even though its card never rendered a gap control; migration
now explains that no visible behavior is carried over. This reduces the audit from
55 to 52 review-only probes. The broad rerun passes 206 frontend units, 147 Chromium
flows and 143 flows in both Firefox and WebKit. HAdev reloaded F1 and delivered
`register.js?v=b9cdc145ac73`; its actually served Timing editor exposed and accepted
`Show live gap toggle`. The draft was cancelled, editing was closed without saving,
and the refreshed F1 Sensor log contained no error after the successful reload.

The Replay migration now also retains the legacy choice to hide button labels.
Hidden labels use compact symbols while every action keeps its accessible name and
tooltip; the default remains labelled. This reduces the audit from 52 to 51
review-only probes. The full rerun passes 40 Python and 44 Node automation tests,
the deterministic 106-file release package, 206 frontend unit tests, 148 Chromium
flows and 144 flows in both Firefox and WebKit. HAdev reloaded F1 and delivered
`register.js?v=79b2b733787a`. Its served Replay editor exposed and accepted
`Show button labels`; the icon-only preview retained the accessible action names.
The draft was cancelled, dashboard editing was closed without saving, and no new
F1 Sensor error appeared after the successful reload.

The Tyres Statistics migration now retains the legacy compound-name choice and
the maximum number of fastest recorded stints per compound. Image and name
combinations map independently, so hiding the visible name does not remove the
tyre image's accessible compound label. A legacy zero limit retains its effective
default of three; malformed non-numeric values remain review-only. The regenerated
audit covers 506 keys and 1,074 probes with 49 review-only results. The full quality
run passes 40 Python and 44 Node automation tests, the deterministic 106-file
release package, 207 frontend unit tests and 148 Chromium flows; all 144 non-
snapshot flows also pass in Firefox and WebKit. HAdev reloaded F1 and delivered
`register.js?v=c13ba4958077`. Its actually served Tyres editor exposed and accepted
compound statistics, `Show compound name`, `Fastest recorded stints` and a limit
of one stint. The draft was cancelled and dashboard editing was closed without
saving. The refreshed F1 Sensor log contained no new error after the successful
reload.

Weekend Hub migration now retains its configured opening view by placing the
matching module first in the converted tab layout. Unsupported values retain the
old Overview fallback. The shared analysis stream has a fixed 500 ms interval;
that effective legacy value is disclosed as retained, while other old per-card
intervals and the synchronized context-bar visibility remain explicit review
items. The audit now covers 506 keys and 1,076 probes with 47 review-only results.
The full quality run passes 40 Python and 44 Node automation tests, the
deterministic 106-file release package, 208 frontend unit tests and 149 Chromium
flows. All 145 non-snapshot flows pass in Firefox and WebKit. HAdev reloaded F1
and delivered `register.js?v=0aadac854a53`. In the actually served legacy editor,
Strategy was selected as the opening view; the conversion preview opened the
strategy module first and showed the 500 ms shared-subscription explanation. The
conversion and card draft were cancelled, dashboard editing was closed without
saving, and the refreshed F1 Sensor log contained no new error.

Pit Stops & Tyres migration now retains the legacy status-column and data-
availability-notice choices. The default F1TV status entity is tied to the
selected installation instead of being copied as a per-field override; a custom
unmatched override remains an explicit review item. Pit rows join their current
driver status from the same retained data generation, while an unavailable
positions source cannot leak a stale status. Authentication states that need
attention remain visible even when the ordinary availability explanation is
hidden. The regenerated audit covers 506 keys and 1,076 probes with 42 review-
only results. The full quality run passes 40 Python and 44 Node automation tests,
the deterministic 106-file release package, 210 frontend unit tests and 152
Chromium flows. All 148 non-snapshot flows pass in Firefox and WebKit. The three
modular runtime copies are byte-identical. HAdev reloaded F1 and delivered
`register.js?v=dd6272493634`. Its actually served legacy editor transferred
`show_availability_notice` and an enabled `show_status`, disclosed the installation-
bound `auth_status_entity` as changed source behavior, and previewed the Status
column with `On track` values. The conversion and draft were cancelled, dashboard
editing was closed without saving, and the refreshed F1 Sensor log contained no
new error after the successful reload.

## 2026-09-15 — Qualifying, grid, archive and map migration parity

Qualifying migration now maps the legacy delta choice to a current-part gap field.
The gap compares each driver's time in the active qualifying part with that part's
fastest time and stays unavailable outside qualifying or before usable part times
exist. Migration previews now select qualifying and practice demo data instead of
always rendering the race scene.

Starting-grid migration retains the source badge as an optional source line. The
session-archive alias reports its saved scope as retained while continuing to force
archive mode, including when an old value says current. Track Map migration retains
code, number or hidden driver labels and the driver-count choice. Hidden map labels
keep the accessible driver list and an explanatory SVG description. The former
per-card update and interpolation intervals are reported as changed because the new
shared map stream uses a fixed 500 ms cadence and no separate interpolation delay.

The regenerated audit covers 506 keys and 1,076 probes with 32 review-only results.
The generated field catalog covers 133 base field IDs, 41 module variants and 283
resolved field rows. The full quality run passes 40 Python and 44 Node automation
tests, the deterministic 106-file release package with SHA-256
`b891fb142e999c0b6eb37cff41d292c94ea41780a0c8f88c8bac3178bcda5279`, 213 frontend
unit tests and 153 Chromium flows. All 149 non-snapshot flows pass separately in
Firefox and WebKit. `git diff --check` passes.

The repository, integration runtime and `/Volumes/config/www` modular directories
are byte-identical with aggregate SHA-256
`35bcf8db8bf407ee4066fca52df3bc404bad20aba4e0d5bec83e477e3e9c0509`. HAdev returns
HTTP 200 for the synchronized registration, card, data, migration, map and view
files, and the served files contain the new behavior. An authenticated HAdev
resource reload and editor check remain pending because the current browser session
is not signed in to `hadev:8123`.

A browser target check found that an earlier 2026-09-15 UI verification described as
HAdev actually used production at `homeassistant.local`. The production F1 Sensor
entry was reloaded once, but no card, dashboard or configuration was saved or
changed. This checkpoint therefore does not use that UI visit as HAdev evidence.
No commit, push or release was performed.

## 2026-09-16 — Static migration queue closed and runtime synchronized

The remaining representative migration probes now have explicit behavior. Live
Session conversion retains flag visibility, lap progress and automatic, compact or
full layout. The map retains its session metadata, footer, lap progress, track
status, layout and accessible track-status line mode. Next Race retains the static
circuit illustration, the available circuit-history attributes and a parallel
circuit-time schedule alongside the selected home time. Current results and
standings can use current-season driver headshots with team-logo fallback; archive
identity remains historical and is not joined to a current roster.

The regenerated migration audit covers 24 card types, 506 statically inventoried
keys and 1,073 representative probes. No key is review-only in this probe set.
Every key pair is also exercised across its representative values: 25,267 combined
configurations have complete report rows, no modular configuration warnings and
exact restoration. The raw report retains 119 distinct context-dependent status or
target variations, including conflicting installation/source and visibility choices.
This does not establish exhaustive semantic parity for values outside the sampled
domains, custom sources or manual behavior comparison. The generated catalog now
covers 137 base field IDs, 41 module variants and 288 resolved field rows.

The source inventory now resolves all 26 observed computed configuration accesses.
It follows class-local literal call chains and bounded literal loops, and derives the
replay entity-key domain from the legacy card's own constants. Dynamic boundaries
remain visible instead of being guessed. Automation now checks both generated
inventory and audit artifacts against the current source, so a stale report fails the
quality run. This closes A2's inventory requirement; F2 remains open for semantic and
manual parity rather than static key discovery.

The shared protection boundary now has a catalogue-driven browser regression. It
covers all 16 sensitive module types plus track-condition weather, blocks every
module model before rows, details or chart series are built when protection is on
or unknown, and proves that history, telemetry, map, analysis and Race Control
resources remain closed. Clear protection starts the applicable resources; turning
protection on again closes them. Existing control tests cover explicit Live Delay
submission, installation scope, calibration, review-before-reveal, local masking,
preview/freeze/disconnect guards and retained-data invalidation. Together with the
previous authenticated HAdev control check, this closes E4. The broader seek,
interruption and reconnect paths are collected in
`quality/modular-lifecycle-matrix.md`. Browser, unit and backend regressions cover
data gaps, late starts and responses, seek/session generation changes, reconnect,
entry reload, cleanup and interrupted calibration. This closes E5 for the
implemented boundary. Long-running real clients and a live weekend remain C7/D2/F3.

The full quality run passes 40 Python tests, 47 Node automation tests, 221 frontend
unit tests and 159 Chromium browser flows. All 155 non-snapshot flows also pass in
Firefox and WebKit. The deterministic 106-file release package has SHA-256
`4d3412ff12e41b04fa89fc6e2e0973af69c2979f54ae5e810f66d43518479a34`, and
`git diff --check` passes.

The B1 editor journey now has one end-to-end browser acceptance flow. It creates
the Race weekend, Follow the session and My driver views from an empty card,
changes the title, pins driver 16 for the personal view, serializes each emitted
configuration and renders it as a card. A separate page then renders the same JSON
and reopens it in the editor with the same title, module order and driver focus.
This proves the no-YAML editor and cross-instance serialization path; an actual HA
dashboard save, usability judgement and a different physical device remain B6/C6.

The repository, integration runtime and `/Volumes/config/www` modular directories
contain 21 files and are byte-identical with aggregate SHA-256
`8f54deea4b308c49099afe1b7f293cdcebff9d70559e9403b136146139b27d0f`. HAdev
returns HTTP 200 for the synchronized catalog, card, view, map view, migration and
demo files, and the served sources contain the new behavior. The authenticated
resource reload and editor inspection remain pending because the browser is still
at the `hadev:8123` login screen. The tab was left open for user handoff. No commit,
push, release or dashboard save was performed.

## 2026-09-16 — Visual component prototype acceptance

B3 and B4 now have a coherent automated component matrix. Existing browser and
unit coverage verifies country flags with fallback and recovery, stable team-logo
frames and text alternatives, tyre graphics and names, coherent/latest sectors,
lap and position arrows, status precedence and comparison origins. Appearance
coverage exercises light and dark modes, custom palettes, symbol/text/both signal
modes, high contrast and forced colors.

A dedicated regression applies deliberately custom overall, personal and recorded
timing colors under grayscale and high contrast. Each state retains a unique shape,
visible status text and the timing legend's previous-completed-lap explanation;
axe reports no serious or critical violations. The flow passes in Chromium,
Firefox and WebKit. This closes the prototype/component scope of B3/B4. B5 remains
open for physical mobile, zoom and real screen-reader journeys, and B6 remains open
for usability-led simplification.

The final repository quality rerun passes 40 Python automation tests, 47 Node
automation tests, the deterministic 106-file release package, 221 frontend unit
tests and 160 Chromium browser flows. All 156 non-snapshot flows have current
passing evidence in Firefox and WebKit, including the editor journey and the new
grayscale regression. The release SHA-256 remains
`4d3412ff12e41b04fa89fc6e2e0973af69c2979f54ae5e810f66d43518479a34`.

The full-product checklist now reflects five other already-tested contracts instead
of leaving them falsely open: UI editing and serialized persistence, style changes
without content loss, inert preview/module lifecycle around replay, explicit
missing/stale/protected/estimated states, and reviewable exactly restorable
migration. Their broader physical-device, long-running, custom-source and semantic
acceptance boundaries remain assigned to C6/C7, F2 and F3.

## 2026-09-16 — Authenticated HAdev dashboard round trip

The authenticated `hadev:8123` editor exposes the delivered F1 Sensor picker and
visual editor. Three version-2 cards were added to the HAdev F1 view without YAML:
Race weekend with overview, schedule and two weather modules; Detailed timing with
overview, timing and Race Control; and My driver with the same session modules and
Charles Leclerc (`16`) as the saved default focus.

Each save produced Home Assistant's success confirmation. Leaving edit mode and
performing a full browser reload rendered all three titles and module sets again;
My driver reopened with Charles Leclerc selected. The authoritative HAdev storage
file confirms the same three titles, version, module order and driver context. This
closes B1's real Home Assistant save/reload portion and most of C6. Cross-device
rendering and usability-led simplification remain C6/B6. No production dashboard,
commit, push or release was changed.

## 2026-09-17 — Coverage status and release-scope alignment

Every row in the plan's legacy-card coverage map now has an explicit verified
status. All 23 registered legacy cards and the archive alias are marked partially
verified with their implemented modular counterpart, automated evidence and exact
remaining acceptance boundary. The map links the generated 506-key migration
inventory but does not treat representative conversion tests as manual semantic
parity; F2, F3 and the affected D2 checks remain open, and the product is not
described as a full replacement.

`quality/modular-release-scope.md` records the exact local beta scope in
user-facing language, including the proposed semantic-release summary and
description. It lists included modules and behavior, the outstanding physical
device, screen-reader, migration, real-data, live-weekend, multi-client and
published-CI gates, and explicit exclusions such as automatic dashboard rewrites,
legacy-card removal and new live mini-sector data. This aligns local documentation
and release information without claiming that F4 publication, F5 beta testing or
F6 distribution verification has happened. No commit, push, beta or release was
created.

F7 now has a separate decision record in
`quality/legacy-card-deprecation-decision.md`: all legacy card types remain
registered, selectable, loadable and supported through development and beta. The
decision lists the evidence required before reconsideration and classifies actual
removal as a separate breaking change. It changes no registration or runtime
behavior.

## 2026-09-17 — Agent completion boundary and external handoff

At the user's request, the plan now defines completion as all work the AI agent can
implement, document and verify locally without waiting for a person, physical
device, live race weekend, external beta installation or published release. Every
A–F item and the final agent-delivery checklist is closed against that boundary.
This is a scope correction, not a claim that human or release acceptance happened.

`F1_SENSOR_MANUELL_OVERLAMNING_2026-09-17.md` is the separate H1–H10 handoff for
cross-device usability, iOS/Android and Companion App, assistive technology, a live
weekend, long-running multi-client lifecycle, real map/archive/analysis data,
semantic migration of real dashboards, external beta, publication/CI/release and
any future legacy-card decision. Each section states prerequisites, steps and a
pass condition. None of these checks keeps the agent goal active.

The plan and final status report contain no unchecked goal boxes. The migration
audit remains current at 24 cards, 506 keys, 1,073 probes and 25,267 pairwise
configurations. Docusaurus builds successfully and the deterministic 106-file
release package retains SHA-256
`4d3412ff12e41b04fa89fc6e2e0973af69c2979f54ae5e810f66d43518479a34`.
`/Volumes/config` was not mounted during the final documentation-only repeat, so
the report dates the last byte-identical runtime proof to 2026-09-16 instead of
presenting historical evidence as a fresh check. No runtime source changed after
that proof, and no commit, push, beta or release was made.

## 2026-09-17 — Scoped custom CSS and stable styling contract

The modular card now accepts an optional root-level `styles` string. The visual
editor exposes it under **Appearance → Custom CSS (advanced)** with live preview
and a dedicated reset action; YAML users can use the same `styles: |` value.
Blank CSS is removed from the saved configuration, while non-string values,
stylesheets over 32,768 characters, JavaScript template interpolation, `@import`
and `url()` resources are rejected. The card never evaluates the value as
JavaScript and installs at most one reusable style element inside its own Shadow
DOM, so selectors cannot style the surrounding Home Assistant page.

Documented `--f1-*` variables override the calculated appearance defaults without
discarding the existing style, theme or density settings. Every module host now
has stable `data-module-type` and `data-module-id` attributes. The card shell and
module content expose public Shadow Parts for headings, toolbars, states, tables,
results, metrics, controls, maps, charts and telemetry. Private class names remain
outside the compatibility contract. The user guide is available at
`docs/cards/modular-styling.md`, is linked from the modular-card guide and sidebar,
and the configuration/release contracts describe the same boundary.

Validation passes with 225 frontend unit tests, 167 Chromium browser flows and
the full 1,569-test `/Volumes/config` integration suite. The two new CSS flows also
pass in Firefox and WebKit. Automation passes 40 Python and 47 Node tests after
regenerating the migration audit's source fingerprints. Documentation passes its
production build, four build checks and 15 browser checks. The deterministic
106-file release package has SHA-256
`c5a834142c2beba1b81fac5fdd147fc3c6569a25620c33ad7fdef1bf59a3ea0e`, and
`git diff --check` passes. All 32 delivered JavaScript files are byte-identical
between `/Volumes/config/www`, the bundled integration and the repository.

HAdev entry reload succeeded and registered managed resource
`/local/f1-sensor-live-data-card/register.js?v=ff37e89bfc78`. The authenticated
editor displayed the advanced CSS section, and a temporary 34 px radius with a
red border rendered immediately in the real card preview. The edit was cancelled;
the three saved modular dashboard cards still have no `styles` property. The
current Home Assistant log UI reports no issue for the search term `f1`. No commit,
push, release or persistent dashboard edit was made.

## 2026-09-17 — Card and module scope hierarchy in the visual editor

The editor now separates whole-card settings and module-only settings into two
named visual regions. The card region contains the title, installation, layout,
shared focus, appearance, accessibility, actions, recovery, templates and raw
configuration. The module region contains the ordered module picker, add control
and the selected module's title, visibility, content, appearance, behavior and
destructive actions. Each region has its own border, subtle surface tint, scope
label and explanatory text; the selected module also shows its position as
**Editing module X of Y**. Template starters are collapsed by default, and every
disclosure now has an explicit direction indicator.

Color is supplementary rather than the only scope signal. Region names, labels,
numbering and borders retain the hierarchy in forced-colors mode. An initial axe
run found insufficient contrast when F1 red was used for small scope text in some
Home Assistant themes; that text now follows the theme's primary text color while
the accent remains on borders and surfaces. The existing accessible name
**Selected module** is retained for compatibility.

The change adds a browser regression that proves card inputs do not appear in the
module region, the selected module changes from 1 of 2 to 2 of 2, and the pressed
state follows the selection. Template journeys now explicitly expand the new
starter disclosure. Validation passes with 225 frontend unit tests, 168 Chromium
browser flows and the full 1,569-test `/Volumes/config` integration suite. The new
scope regression and the full editor axe check also pass in Firefox and WebKit.
All 32 delivered JavaScript files are byte-identical between the primary HAdev
source, the bundled integration and the repository.

The authenticated HAdev editor displayed the new card and module regions on the
saved Race weekend card in the real light theme, including the collapsed starter,
four-module list and selected-module counter. Save remained disabled and the
editor was cancelled without changing the dashboard. No commit, push or release
was made.

## 2026-09-18 — Conditional visibility for individual modules

Every module now accepts an optional `visibility` list in configuration version 3.
The supported conditions follow Home Assistant's card-visibility concepts for
entity state, numeric state, screen media query, user, current-user location and
local time. Top-level conditions use AND semantics, while nested AND, OR and NOT
groups support more complex rules. State attributes, entity-backed comparison
values, weekday filters and time ranges across midnight are included. Visibility
only changes presentation; it is not an authorization boundary.

The visual editor exposes the rules under **Visibility conditions** for the
selected module. Users can add, remove and nest conditions without JSON or YAML,
pick entities from Home Assistant, use phone, tablet and desktop screen presets,
select the current user, and see an immediate **Visible now**, **Hidden now** or
**Always visible** result. A hidden module is removed from tab navigation, layout,
card-size calculation, model building and live-stream subscription until its
conditions match again. Screen and time conditions re-evaluate without requiring
a card reload.

The configuration validator limits rule depth and list size, rejects unsupported
or incomplete rules and migrates earlier configurations without changing their
visibility. User documentation distinguishes module visibility from Home
Assistant's whole-card Visibility tab and notes the layout and permission
boundaries. The generated field catalog and configuration contract now describe
version 3.

Validation passes with 230 frontend unit tests, 171 Chromium browser flows and
the full 1,569-test `/Volumes/config` integration suite. The three new visibility
browser flows also pass in Firefox and WebKit. Documentation passes its production
build, four build checks and 15 browser checks. Automation passes 40 Python and 47
Node tests after regenerating the migration audit's source fingerprints.
Field-catalog validation, deterministic release validation and `git diff --check`
pass. The deterministic
107-file release package has SHA-256
`ad5614e8f1b4c37a1f55092d1ddfc53f2b916f0125027bb60aa6ee68ee2ecd93`.
All 33 delivered JavaScript files are byte-identical between the primary HAdev
source, the bundled integration and the repository.

The authenticated HAdev editor loaded configuration version 3 and the new
visibility evaluator. A temporary entity-state condition changed the selected
module's status to **Hidden now** and removed only that module from the live
preview. The draft was cancelled, edit mode was closed without saving, and the
browser console contained no errors. No commit, push, release or persistent
dashboard edit was made.

## 2026-09-18 — Team colors and interactive season progression

Season progression now reuses the established driver and constructor colors from
the deprecated progression card. Valid colors supplied by the season source or
current driver roster remain available as fallbacks for unknown competitors. The
card-level **Team accents** choice controls whether these colors or the neutral
chart palette is used, and line patterns and marker shapes continue to provide a
non-color distinction.

Each progression legend entry is now a pressed-state button. Selecting the name
or its chart line hides that series, marks the legend name as crossed out and
removes its column from an open data table; selecting the legend entry again
restores it. The wider invisible line hit area does not change the visible line.
The temporary filter is local to the rendered card, is not saved in Lovelace and
is bypassed when the legend is disabled or the table-only presentation is used.

Validation passes with 231 frontend unit tests, 172 Chromium browser flows and
the full 1,569-test `/Volumes/config` integration suite. The focused color and
interaction flow also passes in Firefox and WebKit. Documentation passes its
production build, four build checks and 15 browser checks. Automation passes 40
Python and 47 Node tests, field-catalog validation passes, and the deterministic
107-file release package has SHA-256
`e43dfa845b1be75b678ad2ddab3fda05c74f4e3ea83cc03b23eb73e900c3301a`.

After a cache-bypassing reload, the authenticated HAdev dashboard exposed every
real progression line and legend entry as an accessible visible-series toggle.
Both the Charles Leclerc legend entry and the line itself removed that series and
changed the legend to **hidden. Show series.**; selecting the legend again
restored both the line and pressed state. All
delivered JavaScript files are byte-identical between the primary HAdev source,
the bundled integration and the repository. No dashboard configuration was
saved, and no commit, push or release was made.
