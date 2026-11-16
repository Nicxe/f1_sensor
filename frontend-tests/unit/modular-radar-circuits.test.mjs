import assert from 'node:assert/strict';
import test from 'node:test';
import { RADAR_CIRCUITS } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/radar-circuits.js';

const calendarIds = ['albert_park', 'shanghai', 'suzuka', 'miami', 'villeneuve', 'monaco', 'catalunya', 'red_bull_ring', 'silverstone', 'spa', 'hungaroring', 'zandvoort', 'monza', 'madring', 'baku', 'sepang', 'marina_bay', 'americas', 'rodriguez', 'interlagos', 'vegas', 'losail', 'yas_marina'];
const distance = ([lon1, lat1], [lon2, lat2]) => {
  const radians = value => value * Math.PI / 180;
  const angle = Math.sin(radians(lat2 - lat1) / 2) ** 2
    + Math.cos(radians(lat1)) * Math.cos(radians(lat2)) * Math.sin(radians(lon2 - lon1) / 2) ** 2;
  return 6371008.8 * 2 * Math.atan2(Math.sqrt(angle), Math.sqrt(1 - angle));
};

test('bundled WGS84 centerlines cover the 2026 calendar and stay within plausible circuit bounds', () => {
  assert.deepEqual(Object.keys(RADAR_CIRCUITS).sort(), [...calendarIds].sort());
  for (const [id, circuit] of Object.entries(RADAR_CIRCUITS)) {
    const { coordinates, bounds } = circuit;
    assert.ok(coordinates.length >= 30 && coordinates.length <= 1000, id);
    assert.deepEqual(coordinates[0], coordinates.at(-1), `${id} is closed`);
    for (const point of coordinates) {
      assert.equal(point.length, 2, id);
      assert.ok(point.every(Number.isFinite), id);
      assert.ok(Math.abs(point[0]) <= 180 && Math.abs(point[1]) <= 85, id);
    }
    const longitude = coordinates.map(point => point[0]), latitude = coordinates.map(point => point[1]);
    assert.deepEqual(bounds, [Math.min(...longitude), Math.min(...latitude), Math.max(...longitude), Math.max(...latitude)]);
    const length = coordinates.slice(1).reduce((sum, point, index) => sum + distance(coordinates[index], point), 0);
    assert.ok(length > 3000 && length < 7500, `${id}: plausible lap length ${length}`);
    assert.ok(bounds[2] - bounds[0] < 0.1 && bounds[3] - bounds[1] < 0.1, `${id}: local geometry`);
    assert.equal(circuit.license, 'MIT');
    assert.match(circuit.sourceUrl, /^https:\/\/github\.com\/bacinger\/f1-circuits\/blob\/[a-f0-9]{40}\/circuits\/[a-z]{2}-\d{4}\.geojson$/);
  }
});

for (const [id, anchor, minLength, maxLength] of [
  ['baku', [49.8533, 40.3725], 5800, 6200],
  ['shanghai', [121.22, 31.3389], 5300, 5600],
  ['albert_park', [144.968, -37.8497], 5150, 5400],
  ['losail', [51.4542, 25.49], 5250, 5550],
  ['yas_marina', [54.6031, 24.4672], 5150, 5400],
]) {
  test(`${id} is aligned with an independently published circuit location and modern lap scale`, () => {
    const { coordinates, bounds, provisional } = RADAR_CIRCUITS[id];
    assert.ok(anchor[0] >= bounds[0] && anchor[0] <= bounds[2], 'longitude includes circuit location');
    assert.ok(anchor[1] >= bounds[1] && anchor[1] <= bounds[3], 'latitude includes circuit location');
    const length = coordinates.slice(1).reduce((sum, point, index) => sum + distance(coordinates[index], point), 0);
    assert.ok(length > minLength && length < maxLength, `lap length ${length}m`);
    assert.equal(provisional, false);
  });
}

test('Madrid retains explicit pre-opening provenance instead of claiming a verified 2026 layout', () => {
  const madrid = RADAR_CIRCUITS.madring;
  assert.equal(madrid.provisional, true);
  assert.equal(madrid.sourceDate, '2025-06-11');
  assert.equal(madrid.sourceLengthMeters, 5474);
  assert.equal(madrid.currentPublishedLengthMeters, 5414);
});
