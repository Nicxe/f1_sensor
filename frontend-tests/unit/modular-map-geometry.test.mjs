import assert from 'node:assert/strict';
import test from 'node:test';
import { displayTrack } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/map-geometry.js';

const point = (a, b, c, d, t) => a.map((value, axis) => (1 - t) ** 3 * value + 3 * (1 - t) ** 2 * t * b[axis] + 3 * (1 - t) * t ** 2 * c[axis] + t ** 3 * d[axis]);
const distance = (p, a, b) => {
  const dx = b[0] - a[0], dy = b[1] - a[1], length = dx * dx + dy * dy;
  const t = length ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length)) : 0;
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
};
const curves = path => [...path.matchAll(/C([^CML]+)/g)].map(match => {
  const values = match[1].trim().split(/[\s,]+/).map(Number);
  return [values.slice(0, 2), values.slice(2, 4), values.slice(4, 6)];
});

test('sparse static outlines use smooth curves through every source point while ordinary paths remain linear', () => {
  const points = [[5, 50], [35, 15], [55, 65], [95, 50]];
  const copy = structuredClone(points), linear = displayTrack(points), smooth = displayTrack(points, true);
  assert.equal(linear.path, 'M5,50 L35,15 L55,65 L95,50');
  assert.deepEqual(linear.segments, [[points[0], points[1]], [points[1], points[2]], [points[2], points[3]]]);
  const actual = curves(smooth.path);
  assert.equal(actual.length, points.length - 1);
  assert.deepEqual(actual.map(curve => curve[2]), points.slice(1));
  assert.ok(actual.some(([control], index) => distance(control, points[index], points[index + 1]) > .01));
  assert.deepEqual(points, copy);
});

test('collision segments follow the visible curves and smoothing stays inside the normal track stroke', () => {
  const points = [[5, 50], [35, 15], [35.01, 15.01], [55, 65], [95, 50]];
  const result = displayTrack(points, true), actual = curves(result.path);
  assert.equal(actual.length, points.length - 1);
  assert.ok(result.segments.length > points.length - 1);
  for (let index = 0; index < actual.length; index++) {
    const [b, c, d] = actual[index], a = points[index];
    for (let step = 0; step <= 100; step++) {
      const sample = point(a, b, c, d, step / 100);
      assert.ok(distance(sample, a, d) <= .351, 'curve must stay close to the original centreline');
      assert.ok(Math.min(...result.segments.map(([p, q]) => distance(sample, p, q))) <= .04, 'collision geometry must follow the rendered curve');
      const dx = d[0] - a[0], dy = d[1] - a[1], along = (sample[0] - a[0]) * dx + (sample[1] - a[1]) * dy;
      assert.ok(along >= -1e-8 && along <= dx * dx + dy * dy + 1e-8, 'curve must not extend beyond either endpoint');
    }
  }
});

test('closed circuits retain their closing point and a continuous direction through the join', () => {
  const points = [[10, 10], [80, 10], [80, 80], [10, 80], [10, 10]];
  const result = displayTrack(points, true), actual = curves(result.path);
  assert.deepEqual(actual.at(-1)[2], points[0]);
  const first = actual[0][0].map((value, axis) => value - points[0][axis]);
  const last = points[0].map((value, axis) => value - actual.at(-1)[1][axis]);
  assert.ok(first[0] * last[0] + first[1] * last[1] > 0);
  assert.ok(Math.abs(first[0] * last[1] - first[1] * last[0]) < 1e-6);
});

test('near-closed open paths preserve the actual final endpoint instead of snapping it to the first', () => {
  const points = [[10, 10], [80, 10], [80, 80], [10.1, 10.1]];
  const result = displayTrack(points, true);
  assert.deepEqual(curves(result.path).at(-1)[2], points.at(-1));
  assert.deepEqual(result.segments.at(-1)[1], points.at(-1));
});

test('null and malformed geometry split paths without adding a connection over missing data', () => {
  const points = [[0, 0], [10, 0], [10, 10], null, [70, 70], [80, 70], [80, 80], [NaN, 1], [90, 90]];
  for (const smooth of [false, true]) {
    const result = displayTrack(points, smooth);
    assert.equal((result.path.match(/M/g) ?? []).length, 3);
    assert.ok(result.segments.every(([a, b]) => a.every(Number.isFinite) && b.every(Number.isFinite)));
    assert.ok(result.segments.every(([a, b]) => Math.hypot(b[0] - a[0], b[1] - a[1]) <= 15));
  }
});

for (const points of [null, [], [null], [[1, 1]], [[1, 1], [1, 1]], [[1, 1], [1, 1], [2, 2]], [[1, 1], [2, 2]]]) {
  test(`short or repeated geometry remains finite: ${JSON.stringify(points)}`, () => {
    const result = displayTrack(points, true);
    assert.ok(!/NaN|Infinity|undefined/.test(result.path));
    assert.ok(result.segments.every(([a, b]) => a.every(Number.isFinite) && b.every(Number.isFinite)));
  });
}
