# Modular precipitation radar data contract

Technical note, updated 2026-11-12. Applies only to the modular `custom:f1-sensor-card`.
The module is labelled **Precipitation radar (beta)**. Its beta status does not
certify precipitation accuracy or global ground-radar coverage. The
[beta verification record](radar-beta-readiness.md) separates runtime evidence,
remaining environment limits and release gates from the provider contract below.

## Module and data contract

The `radar` module overlays LibreWXR precipitation on OpenStreetMap base tiles,
with a geographical circuit outline, timestamps, playback and a timeline. Circuit
choices come from the integration's Jolpica season calendar. Bundled WGS84 circuit
coordinates come from the MIT-licensed [F1 Circuits dataset][circuit-source], pinned
to commit `8094e957b8d6aa8b9f4510c93968556cccd30e02`. The map centers on the outline's
bounds when available, otherwise it uses the calendar location and explains the
missing outline. Community outlines are not surveyed boundaries or certified
race-weekend layouts. Madrid is explicitly provisional: the bundled drawing
predates the 2026 event and has not been verified against the final layout.
The UI draws it dashed and explains that the current layout may differ; see the
[circuit source review](radar-circuit-sources.md) for the evidence and its limits.
No LibreWXR implementation or additional library code is copied.

```yaml
type: custom:f1-sensor-card
modules:
  - type: radar
    options:
      zoom: 13
      show_circuit_selector: false
      show_explanation: false
```

The map initially selects the next race from the selected integration's
`next_race` source. The season calendar supplies the available circuit choices.
An unresolved next circuit remains unselected rather than falling back to the
first calendar race. A visible selector allows a temporary user choice; a change
to the next circuit resets that choice. Hiding the selector also returns the map
to the next race. There is no fixed-circuit pin option.

The editor exposes `options.zoom` from 5 through 14, defaulting to 13, and
`options.show_circuit_selector`, defaulting to `true`. The map's zoom buttons
adjust the current view; a distance scale remains visible.
The shared `options.show_explanation` setting, defaulting to `true`, hides the
general footer and timeline explanations when disabled. It retains timestamps,
image age, playback, attribution, the intensity legend, data-quality information,
and current status or circuit-layout notices.
The public LibreWXR endpoint accepts tiles through zoom 12; views at 13 and 14
reuse correctly positioned parent tiles. Enlarging the raster does not create
finer weather resolution. RRQPE's documented stored grid is 0.04°, several
kilometres per cell at these circuits.

The displayed timeline is limited to the 30 minutes before and after the latest
available image time, using only provider-supplied frames. Image age and
actual frame interval stay visible. Current frames are ten minutes apart; the
card does not interpolate minute-by-minute imagery or estimate rain arrival time.

Weather is current-only: recent images and near-term forecasts from the
provider's current catalog. It is not historical session weather and does not
follow the F1 replay clock. Replay or Live Delay requires an explicit action to
show current weather. Global spoiler protection and frozen, hidden or detached
views stop fetching and playback; opting into current weather does not bypass
those gates. Metadata is shared and cached; requests are scoped to active views.
An initial or periodic metadata request that exceeds the 15-second timeout enters
the error state and offers **Try again**. The map clears outdated imagery rather
than remaining in a loading state or silently stopping its refresh cycle.
Cancelling a request because the view becomes inactive remains a normal lifecycle
operation and does not show an error. Retrying after a network failure uses the
same request lifecycle; there is no rapid automatic retry loop.

Pausing playback does not disable a visible map's five-minute metadata refresh.
Leaving the visible area, hiding the document or disconnecting the view stops
playback and refresh timers, releases pending metadata leases, cancels its image
requests and revokes its blob URLs. Returning loads the map in a paused state.
The last metadata consumer cancels an unfinished shared request; one departing
consumer must not interrupt another visible card.

## External requests and attribution

The browser calls the public LibreWXR frame catalog and tile API directly, and
loads base tiles from `https://tile.openstreetmap.org`. These requests need no
weather API key and use `credentials: 'omit'`; the card does not add Home Assistant
or F1 TV authentication. Requested tile coordinates identify the circuit area,
not a device's geolocation. The services receive the viewer's network address.
For OpenStreetMap, the request explicitly uses
`strict-origin-when-cross-origin`, sending the Home Assistant site's origin as
the browser Referer without its dashboard path or query string. Circuit geometry
is bundled and requires no runtime request to its upstream repository.

The module preserves ordinary HTTP caching. It fetches tiles for the current
view and selected image, not a bulk offline archive. Metadata is cached and
deduplicated within the page; image caching follows the browser and the
providers' response headers. Polling is not user-configurable.

The public LibreWXR instance is a best-effort community service. Show timestamps,
forecast labels and loading/failure states. Preserve visible OpenStreetMap,
LibreWXR and upstream source attribution. API output is CC BY 4.0, with CC BY-SA
4.0 applying to tiles containing Italian DPC radar; see the provider's [terms].

The public instance's terms were reviewed on **12 November 2026**; the page is
dated **20 June 2026**. They allow personal projects and normal interactive map
use, including animation, and encourage caching. They prohibit bulk archives,
mirroring, bypassing limits and reselling the hosted endpoint as a separate API.
Higher-volume use needs another arrangement or a self-hosted instance. There is
no guaranteed service level or permanent quota; the endpoint may be changed,
limited or withdrawn. A successful four-card test does not establish permission
for unlimited volume, and the data license is separate from hosted-service use.

The [OpenStreetMap tile policy][osm-tiles] requires normal browser identification,
a valid web referrer, HTTP caching and visible map attribution. Keep
**© OpenStreetMap contributors** visible on the map, with a link to the copyright
page; the detailed source footer must also remain available. Do not introduce
bulk prefetching, offline tile downloads or cache-bypassing requests.

External requests are not anonymous merely because credentials are omitted.
LibreWXR's terms describe IP/rate handling and Cloudflare at the edge.
[OpenStreetMap's privacy policy][osm-privacy] describes access information such
as IP address, browser details, referrer and request time. The card's network
behavior and these provider policies should stay visible in the user guide.

## Data quality and image legend

The map keeps its data-quality information visible when explanatory text is
hidden. LibreWXR can combine ground radar, satellite estimates and weather models.
The card does not identify any circuit as verified ground-radar coverage: the
public metadata supplies frame times, but not the contributing source, coverage
or original observation time at each location. `/health` reports global service
information and per-region frame counts; it does not establish local data quality.
The card therefore adds no health polling and states that local coverage is
unverified. A clear map does not confirm dry weather. Displayed image age is the
age of the provider's frame timestamp, not verified local observation age.
The source label reads **Radar / satellite / model** for recent frames and
**Extrapolation / model** for forecasts. Expanding the quality notice explains
the missing local source and observation time; the coverage and clear-map warning
stays visible when collapsed.

The compact legend uses **Universal Blue**, LibreWXR palette 2, with labelled
dBZ image-intensity samples. The ten swatches are reference samples, not interval
bands or an interpolated gradient. The legend is displayed whenever a map is
ready, independently of `show_explanation`. Its expandable title explains the
units and the shared scale for all precipitation:

| Image intensity | Colour |
| --- | --- |
| 0 dBZ | `#92887188` |
| 5 dBZ | `#cec087cc` |
| 10 dBZ | `#88ddee` |
| 20 dBZ | `#0077aa` |
| 30 dBZ | `#ffee00` |
| 40 dBZ | `#ff7700` |
| 50 dBZ | `#ee0000` |
| 60 dBZ | `#ffaaff` |
| 70 dBZ | `#ff44ff` |
| 80+ dBZ | `#aa00aa` |

The scale represents provider image intensity, not an independently measured
rainfall rate in mm/h. Satellite/model values can include display calibration;
in particular, RRQPE has a configurable dBZ display offset. The card therefore
does not convert the colours to rainfall amounts or rain-arrival estimates.
Tile URLs use `/2/1_0.png`: smoothing remains enabled, while separate snow colours
are disabled so the same intensity scale applies to all precipitation. This
changes the presentation of snow, not the underlying precipitation data.
The provider's palette lookup does not interpolate between colour entries;
tile smoothing and map opacity can still change their appearance on the map.

The palette contract was checked on 12 November 2026 against LibreWXR commit
`c917725f5cabf62aaeb8e87978498f8be9719761`. Public `/health` reported built-in
colour-table version `00affff8694d`, matching the SHA-256 prefix of that commit's
CSV. This is a dated source-contract check, not evidence of future server parity.

## Five-circuit live probe

Checked **2026-11-10 09:55 UTC**, against public LibreWXR version 0.9.0.
The catalog contained 12 past frames and six forecast frames, ten minutes apart.
Point-centered 256×256 PNGs used zoom 7, palette 2, no smoothing or snow coloring,
and times 09:40, 09:50 and forecast 10:00 UTC.

| Circuit | Calendar coordinates | Image results | Ground radar in current source stack |
| --- | --- | --- | --- |
| Baku | 40.3725, 49.8533 | 3/3 HTTP 200; transparent | No; beyond OPERA's 45°E boundary |
| Shanghai | 31.3389, 121.22 | 3/3 HTTP 200; transparent | No; outside Japan and Taiwan regions |
| Melbourne | -37.8497, 144.968 | 3/3 HTTP 200; transparent | No Australian source |
| Qatar / Lusail | 25.49, 51.4542 | 3/3 HTTP 200; transparent | No Gulf source |
| Abu Dhabi / Yas Marina | 24.4672, 54.6031 | 3/3 HTTP 200; transparent | No Gulf source |

All five lie within the expected NOAA RRQPE satellite precipitation domain.
RRQPE had 12 loaded frames. This source assignment is inferred from the current
source geometry and available fields; individual image responses do not expose
pixel provenance. Future frames extrapolate precipitation and blend weather models.

A wider Melbourne control at zoom 4, checked at 09:56:34 UTC, contained visible
precipitation in 1.543% and 1.440% of pixels at 09:40 and 09:50 respectively, with
different image hashes. This establishes changing image content in the wider
region. It does not establish rain movement over any of the five circuit points.

## Interpretation limits

- A transparent image proves neither missing coverage nor dry weather. Rendering
  thresholds and some missing-data cases can produce the same empty image.
- `/v2/coverage/…` colors positive stored field values; it is not a dependable
  ground-radar availability mask. Do not use it to classify circuit coverage.
- MCP `source: "radar"` also includes satellite RRQPE. The five point samples
  returned `in_range`, null dBZ and 0 mm/h, which do not independently verify dryness.
- `radar.past` can mix ground radar, satellite estimates and model fallback.
  Describe the module as precipitation from radar, satellite and models.
- These probes verify API delivery and source-domain reasoning, not precipitation
  accuracy, season-long reliability, local automated tests or HAdev runtime behavior.

## Primary references

The 10 November probe used commit `8c281b936c6a93c18afc6f8740618bd302cbdef0`.
The 12 November palette and quality-contract review used
`c917725f5cabf62aaeb8e87978498f8be9719761`; the live server's exact commit is unknown.

- [Source coverage and resolution](https://github.com/JoshuaKimsey/LibreWXR/blob/8c281b936c6a93c18afc6f8740618bd302cbdef0/docs/coverage.md)
- [Tile API and frame catalog](https://github.com/JoshuaKimsey/LibreWXR/blob/8c281b936c6a93c18afc6f8740618bd302cbdef0/docs/web-integration-guide.md)
- [Coverage rendering](https://github.com/JoshuaKimsey/LibreWXR/blob/8c281b936c6a93c18afc6f8740618bd302cbdef0/src/librewxr/tiles/renderer.py#L646) and [MCP source classification](https://github.com/JoshuaKimsey/LibreWXR/blob/8c281b936c6a93c18afc6f8740618bd302cbdef0/src/librewxr/mcp/tools.py#L35)
- [Upstream attribution](https://github.com/JoshuaKimsey/LibreWXR#data-sources), [live health](https://api.librewxr.net/health), [Jolpica calendar](https://api.jolpi.ca/ergast/f1/2026.json?limit=100)
- [Palette values](https://github.com/JoshuaKimsey/LibreWXR/blob/c917725f5cabf62aaeb8e87978498f8be9719761/src/librewxr/colors/color_table.csv) and [palette indexing](https://github.com/JoshuaKimsey/LibreWXR/blob/c917725f5cabf62aaeb8e87978498f8be9719761/src/librewxr/colors/schemes.py#L85)
- [Snow colouring and tile presentation](https://github.com/JoshuaKimsey/LibreWXR/blob/c917725f5cabf62aaeb8e87978498f8be9719761/src/librewxr/tiles/renderer.py#L259), [RRQPE display calibration](https://github.com/JoshuaKimsey/LibreWXR/blob/c917725f5cabf62aaeb8e87978498f8be9719761/src/librewxr/config.py#L328), and [MCP source classification](https://github.com/JoshuaKimsey/LibreWXR/blob/c917725f5cabf62aaeb8e87978498f8be9719761/src/librewxr/mcp/tools.py#L35)

[terms]: https://librewxr.net/terms.html

[osm-tiles]: https://operations.osmfoundation.org/policies/tiles/

[osm-privacy]: https://osmfoundation.org/wiki/Privacy_Policy

[circuit-source]: https://github.com/bacinger/f1-circuits/tree/8094e957b8d6aa8b9f4510c93968556cccd30e02
