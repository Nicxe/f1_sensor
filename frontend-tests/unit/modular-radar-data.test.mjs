import assert from 'node:assert/strict';
import test from 'node:test';
import { radarMetadata, radarCircuit, radarTiles, radarTileUrl, createRadarMetadataCache, RADAR_REFRESH_MS, radarMapPoint, radarTrackPath, radarScale, RADAR_NATIVE_ZOOM } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/radar-data.js';

import { RADAR_CIRCUITS } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/radar-circuits.js';

const now = Date.parse('2026-11-10T12:00:00Z');
const time = now / 1000;
const payload = () => ({ host: 'https://api.librewxr.net', generated: time,
  radar: { past: [time - 600, time].map(time => ({ time, path: `/v2/radar/${time}` })),
    nowcast: [{ time: time + 600, path: `/v2/radar/${time + 600}` }] } });
const response = () => ({ ok: true, json: async () => payload() });

test('metadata preserves recent and forecast frames without claiming radar coverage', () => {
  const data = radarMetadata(payload(), now);
  assert.deepEqual(data.frames.map(frame => [frame.time, frame.type]), [[time - 600, 'observed'], [time, 'observed'], [time + 600, 'forecast']]);
  assert.ok(Object.isFrozen(data.frames));
  assert.equal('coverage' in data, false);
});

test('metadata rejects stale, empty, unbounded and foreign-host frame lists', () => {
  const invalid = [
    { ...payload(), host: 'https://example.com' },
    { ...payload(), generated: time - 1801 },
    { ...payload(), generated: time + 301 },
    { ...payload(), radar: { past: [], nowcast: [] } },
    { ...payload(), radar: { past: [{ time, path: '//example.com/tile' }], nowcast: [] } },
    { ...payload(), radar: { past: Array(37).fill(payload().radar.past[0]), nowcast: [] } },
  ];
  for (const item of invalid) assert.throws(() => radarMetadata(item, now));
});

test('circuit validation and geographically centered bounded tiles include the requested circuits', () => {
  const circuits = [
    { id: 'baku', name: 'Baku', lat: 40.3725, lon: 49.8533 },
    { id: 'shanghai', name: 'Shanghai', lat: 31.3389, lon: 121.22 },
    { id: 'albert_park', name: 'Melbourne', lat: -37.8497, lon: 144.968 },
    { id: 'losail', name: 'Qatar', lat: 25.49, lon: 51.4542 },
    { id: 'yas_marina', name: 'Abu Dhabi', lat: 24.4672, lon: 54.6031 },
  ];
  for (const circuit of circuits) {
    assert.equal(radarCircuit(circuits, circuit.id).selected, circuit);
    const tiles = radarTiles(circuit, 7);
    assert.equal(tiles.length, 9);
    assert.equal(new Set(tiles.map(tile => `${tile.x}/${tile.y}`)).size, 9);
    // The circuit marker at 50%,50% falls within the center tile, with exact fractional positioning.
    const center = tiles[4];
    assert.ok(center.left <= 50 && center.left + 50 > 50);
    assert.ok(center.top <= 50 && center.top + 256 / 384 * 100 > 50);
    assert.match(radarTileUrl(payload().radar.past[0], center), /^https:\/\/api\.librewxr\.net\/v2\/radar\/\d+\/256\/7\/\d+\/\d+\/2\/1_0\.png$/);
  }
  assert.equal(radarTiles(circuits[0], 20)[0].z, 14);
  assert.equal(radarTiles(circuits[0], -1)[0].z, 5);
  assert.equal(radarCircuit([{ id: 'bad', name: 'Bad', lat: null, lon: 0 }]).selected, null);
  const dateline = radarTiles({ lat: 0, lon: 180 }, 5);
  assert.ok(dateline.every(tile => tile.x >= 0 && tile.x < 32));
});

test('visible consumers share a metadata request and a five-minute cache', async () => {
  let requests = 0, clock = now;
  let resolve;
  const cache = createRadarMetadataCache({ now: () => clock, fetcher: async () => { requests++; return await new Promise(done => { resolve = done; }); } });
  const first = cache.acquire(), second = cache.acquire();
  assert.equal(requests, 1);
  assert.equal(first.promise, second.promise);
  first.release();
  resolve(response());
  await second.promise;
  second.release();
  await cache.acquire().promise;
  assert.equal(requests, 1);
  clock += RADAR_REFRESH_MS;
  const next = cache.acquire();
  assert.equal(requests, 2);
  resolve(response());
  await next.promise;
  next.release();
});

test('only the last disappearing consumer cancels a shared request and a new consumer can retry', async () => {
  const signals = [];
  const cache = createRadarMetadataCache({ now: () => now, fetcher: (_url, { signal }) => {
    signals.push(signal);
    return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true }));
  } });
  const first = cache.acquire(), second = cache.acquire();
  const failed = assert.rejects(first.promise, { name: 'AbortError' });
  first.release(); first.release();
  assert.equal(signals[0].aborted, false);
  second.release();
  assert.equal(signals[0].aborted, true);
  await failed;
  const retry = cache.acquire();
  assert.equal(signals.length, 2);
  const retried = assert.rejects(retry.promise, { name: 'AbortError' });
  retry.release();
  await retried;
});

test('HTTP failures are not cached as dry weather', async () => {
  let requests = 0;
  const cache = createRadarMetadataCache({ now: () => now, fetcher: async () => { requests++; return { ok: false }; } });
  for (let index = 0; index < 2; index++) {
    const lease = cache.acquire();
    await assert.rejects(lease.promise, /unavailable/);
    lease.release();
  }
  assert.equal(requests, 2);
});

for (const phase of ['response', 'body']) {
  test(`a metadata ${phase} timeout fails all consumers and permits a fresh request`, async context => {
    context.mock.timers.enable({ apis: ['setTimeout'] });
    let requests = 0, started;
    const pending = new Promise(resolve => { started = resolve; });
    const cache = createRadarMetadataCache({ now: () => now, fetcher: async (_url, { signal }) => {
      requests++;
      if (requests > 1) return response();
      const stalled = () => new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
        started();
      });
      return phase === 'response' ? stalled() : { ok: true, json: stalled };
    } });
    const first = cache.acquire(), second = cache.acquire();
    assert.equal(first.promise, second.promise);
    const rejected = assert.rejects(first.promise, error => {
      assert.notEqual(error.name, 'AbortError');
      assert.match(error.message, /timed out/);
      return true;
    });
    await pending;
    context.mock.timers.tick(15000);
    await rejected;
    first.release(); second.release();
    assert.equal(requests, 1);
    const retry = cache.acquire();
    assert.equal((await retry.promise).latestTime, time);
    retry.release();
    assert.equal(requests, 2);
  });
}


test('near timeline keeps actual observations and forecasts within thirty minutes of latest data', () => {
  const frame = time => ({ time, path: `/v2/radar/${time}` });
  const data = radarMetadata({ ...payload(), radar: {
    past: Array.from({ length: 12 }, (_, index) => frame(time - (11 - index) * 600)),
    nowcast: Array.from({ length: 6 }, (_, index) => frame(time + (index + 1) * 600)),
  } }, now);
  assert.equal(data.latestTime, time);
  assert.equal(data.intervalMinutes, 10);
  assert.deepEqual(data.frames.map(frame => frame.time - time), [-1800, -1200, -600, 0, 600, 1200, 1800]);
  assert.deepEqual(data.frames.map(frame => frame.type), ['observed', 'observed', 'observed', 'observed', 'forecast', 'forecast', 'forecast']);
  const irregular = payload(); irregular.radar.past[0] = frame(time - 300);
  assert.equal(radarMetadata(irregular, now).intervalMinutes, null);
});

test('geographic outlines center the map and share the exact projection with map coordinates', () => {
  const calendar = [{ id: 'track', name: 'Track', lat: 50, lon: 3 }];
  const outline = { coordinates: [[3.1, 50.01], [3.12, 50.01], [3.12, 50.02], [3.1, 50.01]], sourceName: 'Fixture' };
  const selected = radarCircuit(calendar, 'track', { track: outline }).selected;
  assert.ok(Math.abs(selected.lon - 3.11) < 1e-12);
  assert.ok(Math.abs(selected.lat - 50.015) < 1e-12);
  assert.equal(selected.outline, outline);
  assert.deepEqual(radarMapPoint(selected, [selected.lon, selected.lat], 12), { x: 256, y: 192 });
  const west = radarMapPoint(selected, outline.coordinates[0], 12);
  const east = radarMapPoint(selected, outline.coordinates[1], 12);
  const north = radarMapPoint(selected, outline.coordinates[2], 12);
  assert.ok(west.x < 256 && east.x > 256 && north.y < 192);
  const close = radarMapPoint(selected, outline.coordinates[0], 13);
  assert.ok(Math.abs((close.x - 256) - 2 * (west.x - 256)) < 1e-8);
  assert.ok(Math.abs((close.y - 192) - 2 * (west.y - 192)) < 1e-8);
  assert.equal((radarTrackPath(selected, 12).match(/L/g) || []).length, 3);
  assert.equal(radarTrackPath(calendar[0]), '');
  assert.equal(radarCircuit(calendar, 'track', { track: { coordinates: [[NaN, 50], [3, 50], [3, 50]] } }).selected, calendar[0]);
  assert.ok(radarScale(selected, 12).meters >= 1000 && radarScale(selected, 12).meters <= 5000);
  assert.ok(radarScale(selected, 12).width > 0 && radarScale(selected, 12).width <= 25);
});

test('close views overzoom only native weather parent tiles without gaps or duplicate requests', () => {
  for (const circuit of [{ lat: 40.3725, lon: 49.8533 }, { lat: -37.8497, lon: 144.968 }, { lat: 0, lon: 0 }]) {
    for (const zoom of [13, 14]) {
      const weather = radarTiles(circuit, zoom, RADAR_NATIVE_ZOOM);
      assert.ok(weather.length >= 1 && weather.length <= 4);
      assert.equal(new Set(weather.map(tile => radarTileUrl(payload().radar.past[0], tile))).size, weather.length);
      assert.ok(weather.every(tile => tile.z === 12));
      for (const [x, y] of [[0, 0], [0, 99.999], [99.999, 0], [99.999, 99.999], [50, 50]]) {
        assert.ok(weather.some(tile => x >= tile.left && x < tile.left + tile.width && y >= tile.top && y < tile.top + tile.height));
      }
      assert.ok(radarTiles(circuit, zoom).every(tile => tile.z === zoom));
    }
  }
});


test('every bundled calendar outline remains fully visible at the close default zoom', () => {
  assert.ok(Object.keys(RADAR_CIRCUITS).length > 0);
  for (const [id, outline] of Object.entries(RADAR_CIRCUITS)) {
    const circuit = radarCircuit([{ id, name: id, lat: 0, lon: 0 }], id, RADAR_CIRCUITS).selected;
    assert.equal(circuit.outline, outline, id);
    for (const coordinate of outline.coordinates) {
      const point = radarMapPoint(circuit, coordinate);
      assert.ok(point.x >= 0 && point.x <= 512 && point.y >= 0 && point.y <= 384, `${id} is clipped at the default zoom`);
    }
  }
});
