import assert from 'node:assert/strict';
import test from 'node:test';
import { TrackMapState, trackProjection, mapFreshness, mapExpiry, mapModel } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/map-data.js';
const full = (seq = 1, extra = {}) => ({ protocol_version: 2, type: 'snapshot', entry_id: 'one', sequence: seq, geometry_revision: 1, snapshot: { entry_id: 'one', drivers: [{ racing_number: '16', x: 0, y: 1 }], ...extra } });
const delta = (seq, base, extra = {}) => ({ protocol_version: 2, type: 'delta', entry_id: 'one', sequence: seq, base_sequence: base, changes: {}, removed: [], patch: {}, ...extra });

test('map applies coalesced deltas and removals atomically, detects gaps and ignores duplicates or another entry', () => {
  const state = new TrackMapState('one'); assert.equal(state.accept(full()), 'updated');
  assert.equal(state.accept(delta(5, 1, { changes: { 4: { racing_number: '4', x: 2, y: 3 } }, removed: ['16'], patch: { status: 'active' } })), 'updated');
  assert.deepEqual(state.snapshot.drivers.map(driver => driver.racing_number), ['4']);
  assert.equal(state.accept(delta(5, 1)), 'ignored'); assert.equal(state.accept(delta(8, 7)), 'resync'); assert.equal(state.sequence, 5);
  assert.equal(state.accept({ ...full(9), entry_id: 'other' }), 'ignored');
  assert.equal(state.accept(full(9)), 'updated'); assert.equal(state.sequence, 9);
  assert.equal(state.accept(delta(10, 9, { changes: { 99: { racing_number: '16' } } })), 'resync');
  assert.equal(state.sequence, 9); assert.equal(state.snapshot.drivers.length, 1);
});

test('map session replacement discards previous drivers and only a new subscription resets sequence', () => {
  const state = new TrackMapState('one'); state.accept(full(10, { session: { session_key: 'first' } }));
  assert.equal(state.accept(full(11, { session: { session_key: 'second' }, drivers: [] })), 'updated');
  assert.deepEqual(state.snapshot.drivers, []); assert.equal(state.accept(full(0)), 'ignored');
  assert.equal(state.accept({ entry_id: 'one', status: 'closed' }), 'closed');
  assert.equal(new TrackMapState('one').accept(full(0)), 'updated');
});

test('projection accepts zero coordinates, retains geometry gaps and rejects degenerate or missing data', () => {
  const projection = trackProjection({ points: [[0, 0], [100, 0], null, [100, 50]], rotation: 0 });
  assert.ok(projection); assert.equal(projection.points[2], null); assert.deepEqual(projection.project(0, 0), [5, 72.5]);
  assert.equal(projection.project(null, 0), null);
  assert.equal(trackProjection({ points: [[1, 1], [1, 1]] }), null);
  assert.equal(trackProjection(null), null);
  const rotated = trackProjection({ points: [[0, 0], [100, 0]], rotation: 90 });
  assert.ok(Math.abs(rotated.points[0][0] - rotated.points[1][0]) < .00001);
});

test('map age distinguishes a paused recorded replay from a stale live feed', () => {
  const snapshot = { stream_timestamp: '2026-09-13T13:00:00Z', stale_after_seconds: 10, source: 'live', stale: false };
  const now = Date.parse('2026-09-13T13:00:11Z');
  assert.equal(mapFreshness(snapshot, now).stale, true);
  assert.equal(mapFreshness({ ...snapshot, source: 'replay', replay_state: 'paused' }, now).stale, false);
  assert.equal(mapFreshness({ ...snapshot, source: 'replay', stale: true }, now).stale, true);
  assert.equal(mapFreshness({ ...snapshot, stream_timestamp: null }, now).age, null);
});

test('a delta carrying a new session cannot retain previous-session drivers when no replacement is supplied', () => {
  const state = new TrackMapState('one'); state.accept(full(1, { session: { session_key: 101 } }));
  assert.equal(state.accept(delta(2, 1, { patch: { session: { session_key: 102 } } })), 'updated');
  assert.deepEqual(state.snapshot.drivers, []);
});

test('rotated asymmetric geometry stays centered within its drawing bounds', () => {
  const projection = trackProjection({ points: [[0, 0], [100, 0], [100, 50]], rotation: 45 });
  for (const point of projection.points) for (const coordinate of point) assert.ok(coordinate >= 5 - 1e-8 && coordinate <= 95 + 1e-8);
  assert.equal(trackProjection({ points: [[-1e308, -1e308], [1e308, 1e308]] }), null);
});

test('map focus intersects driver and team, retains malformed positions in the list and reuses geometry', () => {
  const snapshot = { source: 'replay', session: { session_key: 1 }, track: { points: [[0, 0], [100, 100]] }, drivers: [
    { racing_number: '16', tla: 'LEC', team_name: 'Ferrari', x: 0, y: 0 },
    { racing_number: '4', tla: 'NOR', team_name: 'McLaren', x: null, y: 2 },
  ] };
  const module = { options: { focus: 'highlight', orientation: 'source', vertical: 'flipped' } };
  const all = mapModel(snapshot, module, { driver: 'LEC', team: 'Ferrari' });
  assert.deepEqual(all.rows.map(row => row.id), ['4', '16']);
  assert.equal(all.rows[0].point, null); assert.equal(all.rows[1].selected, true);
  assert.strictEqual(mapModel(snapshot, module).points, all.points);
  assert.equal(mapModel(snapshot, { ...module, driver: '16', team: 'McLaren', options: { ...module.options, focus: 'filter' } }).rows.length, 0);
  assert.equal(mapModel(null, module).pending, true);
});

test('map removes drivers declared out by timing even when Position.z retains an on-track coordinate', () => {
  const snapshot = { source: 'replay', track: { points: [[0, 0], [100, 100]] }, drivers: [
    { racing_number: '41', tla: 'LIN', x: 20, y: 20, status: 'OnTrack' },
    { racing_number: '16', tla: 'LEC', x: 80, y: 80, status: 'OnTrack' },
  ] };
  const module = { options: { focus: 'highlight', orientation: 'source', vertical: 'flipped' } };
  const rows = mapModel(snapshot, module, {}, Date.now(), [
    { racing_number: '41', tla: 'LIN', status: 'out', stopped: true },
  ]).rows;
  assert.deepEqual(rows.map(row => row.id), ['16']);
});

test('freshness expiry is absolute and does not schedule replay or already stale positions', () => {
  const snapshot = { source: 'live', stream_timestamp: '2026-09-13T13:00:00Z', stale_after_seconds: 10 };
  const expiry = Date.parse('2026-09-13T13:00:10Z');
  assert.equal(mapExpiry(snapshot), expiry);
  assert.equal(mapFreshness(snapshot, expiry - 1).stale, false);
  assert.equal(mapFreshness(snapshot, expiry).stale, true);
  for (const extra of [{ source: 'replay' }, { stale: true }, { status: 'stale' }, { stale_after_seconds: -1 }, { stream_timestamp: null }]) assert.equal(mapExpiry({ ...snapshot, ...extra }), null);
});

test('session changes without a geometry decision require a full snapshot instead of relabeling the previous track', () => {
  const state = new TrackMapState('one');
  state.accept(full(1, { session: { session_key: 101 }, track: { points: [[0, 0], [5, 5]] } }));
  assert.equal(state.accept(delta(2, 1, { patch: { session: { session_key: 102 } } })), 'resync');
  assert.equal(state.sequence, 1); assert.equal(state.snapshot.session.session_key, 101);
  assert.equal(state.accept(delta(2, 1, { patch: { session: { session_key: 102 }, track: null } })), 'updated');
  assert.equal(state.snapshot.track, null); assert.deepEqual(state.snapshot.drivers, []);
});
