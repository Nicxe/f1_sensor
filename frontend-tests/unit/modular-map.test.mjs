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

test('existing v2 decoder accepts optional annotation metadata and atomic removal', () => {
  const state = new TrackMapState('one');
  const annotations = { schema_version: 1, binding: { session_generation: 7 }, layers: [] };
  const track = { points: [[0, 0], [10, 10]], geometry_fingerprint: 'sha256:fixture' };
  assert.equal(state.accept(full(1, { session: { session_key: 101 }, track, annotations })), 'updated');
  assert.equal(state.accept(delta(2, 1, { changes: { 4: { racing_number: '4', x: 2, y: 3 } } })), 'updated');
  assert.deepEqual(state.snapshot.annotations, annotations);
  assert.equal(state.accept(delta(3, 2, { patch: { session: { session_key: 102 }, track: null, annotations: null } })), 'updated');
  assert.equal(state.snapshot.annotations, null);
  assert.equal(state.snapshot.track, null);
});

test('reviewed annotations follow each map instance and disappear on a mismatched session, geometry or seek', () => {
  const binding = { entry_id: 'one', source: 'replay', session_key: 'race', session_generation: 7, circuit_key: '61', season: 2025, layout_key: 'marina_bay_post_2023', geometry_fingerprint: 'sha256:fixture' };
  const source = { url: 'https://example.test/approved-circuit-map' };
  const annotations = { schema_version: 1, binding, layers: [
    { layer: 'start_finish', source, columns: ['id', 'kind', 'start', 'end', 'label'], items: [['start_finish', 'line', [0, 0], [10, 0], 'Start/finish']] },
    { layer: 'corners', source, columns: ['id', 'kind', 'anchor', 'label', 'label_offset'], items: [['turn_01', 'point', [20, 20], '1', [3, -4]]] },
  ] };
  const snapshot = { entry_id: 'one', source: 'replay', replay_state: 'paused', session: { session_key: 'race', circuit_key: '61', path: '2025/Singapore/Race', start_date: '2025-10-05' }, track: { circuit_key: '61', geometry_fingerprint: 'sha256:fixture', points: [[0, 0], [100, 0], [100, 100]], rotation: 90 }, drivers: [{ racing_number: '16', tla: 'LEC', team_name: 'Ferrari', x: 20, y: 20 }], annotations };
  const first = { fields: ['track_map', 'map_start_finish'], options: { orientation: 'source', vertical: 'flipped', focus: 'highlight' } };
  const second = { fields: ['track_map', 'map_corners'], options: { orientation: 'raw', vertical: 'flipped', focus: 'filter' }, driver: '4' };
  const a = mapModel(snapshot, first);
  const b = mapModel(snapshot, second);
  assert.equal(a.annotations.lines.length, 1); assert.equal(a.annotations.corners.length, 0);
  assert.equal(b.annotations.lines.length, 0); assert.equal(b.annotations.corners.length, 1);
  assert.notDeepEqual(a.points, b.points);
  assert.deepEqual(b.rows, []); // Focus filters cars, not circuit markings.
  for (const invalid of [
    { session: { ...snapshot.session, session_key: 'practice' } },
    { track: { ...snapshot.track, geometry_fingerprint: 'sha256:changed' } },
    { replay_state: 'seeking' },
    { source: 'live' },
    { annotations: null },
  ]) {
    const model = mapModel({ ...snapshot, ...invalid }, first);
    assert.deepEqual(model.annotations.lines, []);
    assert.deepEqual(model.annotations.unavailable, ['map_start_finish']);
  }
  const state = new TrackMapState('one');
  state.accept(full(1, snapshot));
  state.accept(delta(2, 1, { patch: { annotations: null, replay_state: 'seeking' } }));
  assert.equal(mapModel(state.snapshot, first).annotations.lines.length, 0);
  const missedRemoval = new TrackMapState('one');
  missedRemoval.accept(full(1, snapshot));
  missedRemoval.accept(delta(2, 1, { patch: { replay_state: 'seeking' } }));
  assert.equal(missedRemoval.snapshot.annotations, null);
  assert.equal(new TrackMapState('one').accept(full(1, { ...snapshot, annotations: null })), 'updated');
});

test('Silverstone 2025 renders verified sectors and point marks while partial layers stay independent', () => {
  const source = { url: 'https://www.fia.com/example.pdf' };
  const binding = { entry_id: 'one', source: 'replay', session_key: 'british-race', session_generation: 4, circuit_key: '2', season: 2025, layout_key: 'silverstone_2025', geometry_fingerprint: 'sha256:silverstone' };
  const layer = (name, columns, items) => ({ layer: name, source, columns, items });
  const base = {
    entry_id: 'one', source: 'replay', replay_state: 'paused',
    session: { session_key: 'british-race', circuit_key: '2', path: '2025/British_Grand_Prix/Race', start_date: '2025-07-06' },
    track: { circuit_key: '2', geometry_fingerprint: 'sha256:silverstone', points: [[0, 0], [100, 0], [100, 100]], rotation: 0 },
    drivers: [],
    annotations: { schema_version: 1, binding, layers: [
      layer('start_finish', ['id', 'kind', 'start', 'end', 'label'], [['start_finish', 'line', [10, 0], [10, 10], 'Start/finish']]),
      layer('corners', ['id', 'kind', 'anchor', 'label', 'label_offset'], [['turn_01', 'point', [30, 0], '1', [3, -4]]]),
      layer('sectors', ['id', 'kind', 'start', 'end', 'label'], [['s1', 'line', [40, 0], [40, 10], 'S1'], ['s2', 'line', [70, 0], [70, 10], 'S2']]),
      layer('speed_traps', ['id', 'kind', 'anchor', 'label', 'label_offset'], [['speed_trap', 'point', [80, 0], 'Speed trap', [3, -4]]]),
      layer('detection_zones', ['id', 'kind', 'anchor', 'label', 'label_offset'], [['drs_d1', 'point', [20, 0], 'DRS D1', [3, -4]], ['drs_a1', 'point', [50, 0], 'DRS A1', [3, -4]]]),
    ] },
  };
  const module = { fields: ['map_start_finish', 'map_corners', 'map_sectors', 'map_speed_traps', 'map_detection_zones'], options: { orientation: 'raw', vertical: 'flipped' } };
  const fullMap = mapModel(base, module).annotations;
  assert.deepEqual(fullMap.unavailable, []);
  assert.deepEqual(fullMap.lines.map(item => item.label), ['Start/finish', 'S1', 'S2']);
  assert.deepEqual(fullMap.points.map(item => item.label), ['Speed trap', 'DRS D1', 'DRS A1']);
  const partial = mapModel({ ...base, annotations: { ...base.annotations, layers: base.annotations.layers.slice(0, 2) } }, module).annotations;
  assert.equal(partial.lines.length, 1);
  assert.equal(partial.corners.length, 1);
  assert.deepEqual(partial.unavailable, ['map_sectors', 'map_speed_traps', 'map_detection_zones']);
  const wrongYear = mapModel({ ...base, session: { ...base.session, path: '2024/British_Grand_Prix/Race', start_date: '2024-07-07' } }, module).annotations;
  assert.equal(wrongYear.lines.length, 0);
  assert.deepEqual(wrongYear.unavailable, module.fields);
  const malformed = mapModel({ ...base, annotations: { ...base.annotations, layers: base.annotations.layers.map(item => item.layer === 'sectors'
    ? { ...item, items: [['s1', 'line', [40, 0], [40, 10], 'S1'], ['s2', 'line', [70, 0], [70, 10], 'S4']] } : item) } }, module).annotations;
  assert.equal(malformed.lines.length, 1);
  assert.deepEqual(malformed.unavailable, ['map_sectors']);
});

test('Singapore 2026 renders reviewed overtake and straight-mode points only for that season', () => {
  const binding = { entry_id: 'one', source: 'live', session_key: 'sprint', session_generation: 9,
    circuit_key: '61', season: 2026, layout_key: 'marina_bay_post_2023', geometry_fingerprint: 'sha256:singapore' };
  const base = { entry_id: 'one', source: 'live', replay_state: null,
    session: { session_key: 'sprint', circuit_key: '61', path: '2026/Singapore/Sprint', start_date: '2026-10-10' },
    track: { circuit_key: '61', geometry_fingerprint: 'sha256:singapore', points: [[0, 0], [100, 0], [100, 100]], rotation: 0 },
    drivers: [], annotations: { schema_version: 1, binding, layers: [{ layer: 'detection_zones',
      source: { url: 'https://www.fia.com/2026-map.pdf' }, columns: ['id', 'kind', 'anchor', 'label', 'label_offset'],
      items: [['ot_a', 'point', [30, 0], 'OT A', [3, -4]], ['sm_a1_n', 'point', [60, 0], 'SM A1 N', [3, -4]]] }] } };
  const module = { fields: ['map_detection_zones'], options: { orientation: 'raw', vertical: 'flipped' } };
  assert.deepEqual(mapModel(base, module).annotations.points.map(point => point.label), ['OT A', 'SM A1 N']);
  assert.deepEqual(mapModel({ ...base, session: { ...base.session, path: '2027/Singapore/Sprint', start_date: '2027-10-10' } }, module).annotations.unavailable,
    ['map_detection_zones']);
  assert.deepEqual(mapModel({ ...base, annotations: { ...base.annotations, layers: [{ ...base.annotations.layers[0],
    items: [['drs_d1', 'point', [30, 0], 'DRS D1', [3, -4]], ['invalid', 'point', [60, 0], 'SM A6 N', [3, -4]]] }] } }, module).annotations.points, []);
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
