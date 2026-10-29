import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig, duplicateModule } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { timingRows } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';
import { SectorStore } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/semantics.js';

const entry = { entry_id: 'push-fixture', entities: { driver_positions: 'sensor.positions' } };
const context = { key: 'qualifying:1', name: 'Qualifying' };
const attempt = (state, progress, extra = {}) => ({ state, active: ['push', 'probable_push'].includes(state), progress, lap: 5, ...extra });
const driver = (id, position, push, team = 'Team') => ({ racing_number: String(id), tla: `D${id}`, current_position: position, team, push_lap: push });
const fixture = (drivers, status = 'available') => ({ states: { 'sensor.positions': { state: 'unknown', attributes: { drivers, push_laps_status: status, current_qualifying_part: 1 } } } });
const moduleFor = (options = {}, extra = {}) => normalizeConfig({ modules: [{ id: 'timing', type: 'timing', options, ...extra }] }).modules[0];
const read = (hass, options = {}, extra = {}, order = null, selected = context) => timingRows(hass, entry, selected, new SectorStore(), moduleFor(options, extra), {}, null, order);

test('push display defaults off and duplicate Timing modules keep independent choices', () => {
  const config = normalizeConfig({ modules: [{ id: 'timing', type: 'timing' }] });
  assert.equal(config.modules[0].options.push_laps, 'off');
  config.modules[0].options.push_laps = 'only';
  const duplicated = duplicateModule(config, 'timing');
  duplicated.modules[1].options.push_laps = 'first';
  assert.equal(duplicated.modules[0].options.push_laps, 'only');
  assert.throws(() => moduleFor({ push_laps: 'automatic' }), /choose off, first, only/);
});

test('push attempts precede the row cap and follow track progress, preserving classification positions', () => {
  const hass = fixture([driver(1, 1, attempt('outlap', .9)), driver(4, 2, attempt('push', .4)), driver(63, 20, attempt('probable_push', .8))]);
  const normal = read(hass, { rows: 2 });
  assert.deepEqual(normal.rows.map(row => row.id), ['1', '4']);
  const result = read(hass, { push_laps: 'first', rows: 2 });
  assert.deepEqual(result.rows.map(row => row.id), ['63', '4']);
  assert.deepEqual(result.rows.map(row => row.position), [20, 2]);
  assert.equal(result.pushCount, 2);
  assert.ok(result.rows.every(row => row.push_group === 'active'));
});

test('only mode keeps a completed result separate and rejects contradictory or inactive push labels', () => {
  const hass = fixture([
    driver(1, 1, attempt('outlap', .9, { active: true })),
    driver(4, 2, attempt('push', .4)),
    driver(63, 3, attempt('push', .7, { active: false })),
    driver(16, 4, attempt('completed', 1, { last_lap_time: 80.12, completed_at: '2026-10-24T12:00:00Z' })),
  ]);
  const result = read(hass, { push_laps: 'only' });
  assert.deepEqual(result.rows.map(row => [row.id, row.push_group]), [['4', 'active'], ['16', 'completed']]);
  assert.equal(result.pushCount, 1);
  assert.equal(result.rows[1].push_lap.last_lap_time, 80.12);
});

test('ties retain the previous physical order and missing progress never outranks known progress', () => {
  const orders = new Map();
  const drivers = [driver(4, 1, attempt('push', .3)), driver(63, 2, attempt('push', .8)), driver(16, 3, attempt('push', null))];
  const hass = fixture(drivers);
  assert.deepEqual(read(hass, { push_laps: 'only' }, {}, orders).rows.map(row => row.id), ['63', '4', '16']);
  drivers[0].push_lap.progress = .8;
  assert.deepEqual(read(hass, { push_laps: 'only' }, {}, orders).rows.map(row => row.id), ['63', '4', '16']);
  drivers[2].push_lap.progress = 8;
  assert.equal(read(hass, { push_laps: 'only' }, {}, orders).rows[2].push_lap.progress, null);
});

test('waiting, unavailable, unsupported sessions and missing payloads cannot invent active attempts', () => {
  const drivers = [driver(4, 1, attempt('push', .4))];
  for (const status of ['waiting', 'unavailable', 'unsupported']) {
    const hass = fixture(drivers, status);
    const result = read(hass, { push_laps: 'only' });
    assert.equal(result.pushStatus, status);
    assert.equal(result.rows.length, 0);
    assert.equal(read(hass, { push_laps: 'first' }).rows[0].push_lap.active, false);
  }
  const hass = fixture(drivers);
  delete hass.states['sensor.positions'].attributes.push_laps_status;
  assert.equal(read(hass, { push_laps: 'only' }).pushStatus, 'waiting');
  const race = { key: 'race', name: 'Race' };
  assert.equal(read(fixture(drivers), { push_laps: 'only' }, {}, null, race).pushStatus, 'unsupported');
  assert.equal(read(fixture(drivers), { push_laps: 'first' }, {}, null, race).rows.length, 1);
});

test('no active attempts remains an ordinary table in first mode and an empty result in only mode', () => {
  const hass = fixture([driver(1, 1, attempt('cooldown', .5))]);
  assert.equal(read(hass, { push_laps: 'first' }).rows[0].push_group, undefined);
  assert.equal(read(hass, { push_laps: 'only' }).rows.length, 0);
});

test('push selection respects driver and team filters before ordering', () => {
  const hass = fixture([driver(4, 1, attempt('push', .4), 'A'), driver(63, 2, attempt('push', .8), 'B')]);
  assert.deepEqual(read(hass, { push_laps: 'only' }, { driver: '4' }).rows.map(row => row.id), ['4']);
  assert.deepEqual(read(hass, { push_laps: 'only' }, { team: 'B' }).rows.map(row => row.id), ['63']);
});

test('retained or disconnected sources cannot present saved push attempts as active', () => {
  const hass = fixture([driver(4, 1, attempt('push', .4))]);
  assert.equal(read(hass, { push_laps: 'only' }, {}, null, { ...context, retained: true }).pushStatus, 'unavailable');
  hass.connection = { connected: false };
  const result = read(hass, { push_laps: 'only' });
  assert.equal(result.pushStatus, 'unavailable');
  assert.equal(result.rows.length, 0);
});

test('a highlighted attempt cannot inherit future coherent sectors after a backwards seek', () => {
  const store = new SectorStore();
  const later = driver(63, 1, attempt('push', .9));
  later.sector_current_lap = 4;
  later.sectors = { state: 's2_done', current: Object.fromEntries([41.486, 48.138, 48.47].map((time, index) => [`sector_${index + 1}`, { time, lap: 4, source: 'current' }])) };
  const model = (value, mode) => timingRows(fixture([value]), entry, context, store, moduleFor({ push_laps: mode }));
  model(later, 'off');
  const earlier = driver(63, 1, attempt('probable_push', .125));
  earlier.sectors = { state: 'awaiting_s1', current: Object.fromEntries([1, 2, 3].map(index => [`sector_${index}`, { time: null, lap: null, source: null }])) };
  assert.deepEqual(model(earlier, 'off').rows[0].sector_1.time, 41.486, 'the existing ordinary coherent view remains unchanged');
  for (const mode of ['first', 'only']) {
    const row = model(earlier, mode).rows[0];
    assert.deepEqual([row.sector_1.time, row.sector_2.time, row.sector_3.time], [null, null, null]);
  }
});

test('highlighted sectors follow current projected lap identity and completed progress, not the classifier lap number', () => {
  const current = driver(63, 1, attempt('push', .4, { lap: 2 }));
  current.sector_current_lap = 3;
  current.sectors = { current: {
    sector_1: { time: 25.54, lap: 3, source: 'current' },
    sector_2: { time: 39.1, lap: 3, source: 'current' },
    sector_3: { time: 31.2, lap: 2, source: 'previous_lap' },
  } };
  let row = read(fixture([current]), { push_laps: 'only' }).rows[0];
  assert.deepEqual([row.sector_1.time, row.sector_2.time, row.sector_3.time], [25.54, null, null]);
  current.push_lap.progress = .8;
  row = read(fixture([current]), { push_laps: 'only' }).rows[0];
  assert.deepEqual([row.sector_1.time, row.sector_2.time, row.sector_3.time], [25.54, 39.1, null]);
  current.sectors.current.sector_1.lap = 2;
  current.sectors.current.sector_2.source = 'previous_lap';
  row = read(fixture([current]), { push_laps: 'only' }).rows[0];
  assert.deepEqual([row.sector_1.time, row.sector_2.time, row.sector_3.time], [null, null, null]);
});

test('active minisector strips retain the observed prefix and clear later portions of the lap', () => {
  const current = driver(63, 1, attempt('push', .375));
  const minisectors = { status: 'ready', drivers: { '63': { sectors: Object.fromEntries([0, 1, 2].map(sector => [sector, { segments: Object.fromEntries(Array.from({ length: 8 }, (_, index) => [index, 2051])) }])) } } };
  const result = timingRows(fixture([current]), entry, context, new SectorStore(), moduleFor({ push_laps: 'only' }), {}, minisectors);
  const row = result.rows[0];
  assert.deepEqual(row.minisector_1.map(item => item.raw), Array(8).fill(2051));
  assert.deepEqual(row.minisector_2.map(item => item.raw), [2051, 0, 0, 0, 0, 0, 0, 0]);
  assert.deepEqual(row.minisector_3.map(item => item.raw), Array(8).fill(0));
  assert.deepEqual(row.sector_2_with_minisectors.segments, row.minisector_2);
});
