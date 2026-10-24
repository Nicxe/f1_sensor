import assert from 'node:assert/strict';
import test from 'node:test';
import { FIELDS, TIMING_PROFILES } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { sessionContext, timingRows } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';
import { SectorStore } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/semantics.js';
import { moduleView } from './card-module.mjs';

const entry = { entry_id: 'practice-gap', entities: { driver_positions: 'sensor.positions' } };
const driver = (id, best, extra = {}) => ({ racing_number: id, tla: `D${id}`, current_position: Number(id), best_lap_time: best, best_lap_time_source: 'official', ...extra });
const fixture = drivers => ({ states: { 'sensor.positions': { state: 'unknown', attributes: { drivers, current_qualifying_part: 1 } } } });
const moduleConfig = (options = {}) => normalizeConfig({ modules: [{ type: 'timing', fields: ['driver', 'best_lap_gap'], options }] }).modules[0];
const model = (hass, { name = 'Practice 1', key = name, options = {}, focus = {}, store = new SectorStore() } = {}) => timingRows(hass, entry, { key, name }, store, moduleConfig(options), focus);
const gaps = result => Object.fromEntries(result.rows.map(row => [row.id, row.best_lap_gap]));

test('best lap gap is an optional practice field without changing existing column profiles', () => {
  assert.equal(FIELDS.best_lap_gap.type, 'seconds_delta');
  assert.equal(FIELDS.best_lap_gap.unit, 's');
  assert.deepEqual(FIELDS.best_lap_gap.sessions, ['practice']);
  assert.equal(FIELDS.best_lap_gap.comparison, 'fastest_official_session_best');
  assert.ok(!normalizeConfig({ modules: [{ type: 'timing' }] }).modules[0].fields.includes('best_lap_gap'));
  assert.ok(Object.values(TIMING_PROFILES).every(fields => !fields.includes('best_lap_gap')));
});

test('native practice gaps take precedence over a local calculation, including an exact zero', () => {
  const result = model(fixture([
    driver('1', '1:20.000', { best_lap_gap: 0 }),
    driver('2', '1:21.000', { best_lap_gap: 0.432 }),
  ]));
  assert.deepEqual(gaps(result), { 1: 0, 2: 0.432 });
});

test('practice sample data supplies official bests and native gaps that survive driver focus', () => {
  const demo = makeDemo('practice'), demoEntry = demo.preview.entries[0];
  const read = focus => timingRows(demo.hass, demoEntry, sessionContext(demo.hass, demoEntry), new SectorStore(), moduleConfig(), focus);
  const result = read();
  assert.deepEqual(result.fields, ['driver', 'best_lap_gap']);
  assert.deepEqual(result.rows.map(row => row.best_lap_gap), [0, 0.23, 0.46, 0.69, 0.92]);
  assert.deepEqual(gaps(read({ driver: '4' })), { 4: 0.23 });
  assert.ok(demo.hass.states[demoEntry.entities.driver_positions].attributes.drivers.every(row => row.best_lap_time_source === 'official'));
  for (const scene of ['qualifying', 'sprint_qualifying', 'sprint', 'race']) {
    const other = makeDemo(scene), otherEntry = other.preview.entries[0];
    assert.ok(other.hass.states[otherEntry.entities.driver_positions].attributes.drivers.every(row => row.best_lap_gap === null), scene);
  }
});

test('calculated practice gaps keep the session reference across driver, team and row selection', () => {
  const hass = fixture([
    driver('1', '1:20.000', { team: 'Ferrari' }),
    driver('2', '1:21.000', { team: 'McLaren' }),
    driver('3', '1:21.500', { team: 'McLaren' }),
  ]);
  assert.deepEqual(gaps(model(hass, { focus: { driver: '2' } })), { 2: 1 });
  assert.deepEqual(gaps(model(hass, { focus: { team: 'McLaren' } })), { 2: 1, 3: 1.5 });
  assert.deepEqual(gaps(model(hass, { options: { sort: 'best_lap', direction: 'desc', rows: 1 } })), { 3: 1.5 });
  assert.equal(model(hass).rows[1].gap, null);
  assert.equal(model(hass).rows[1].interval, null);
  assert.equal(model(hass).rows[1].qualifying_gap, null);
});

test('absent or invalid native gaps fall back to the official session best', () => {
  for (const native of [undefined, null, -1, NaN, Infinity, '0.250', true, {}]) {
    const hass = fixture([driver('1', 80), driver('2', 81, { best_lap_gap: native })]);
    assert.equal(model(hass).rows[1].best_lap_gap, 1, `native value ${String(native)}`);
  }
});

test('observed, missing, malformed and explicitly deleted official bests cannot become gap references', () => {
  const hass = fixture([
    driver('1', 80),
    driver('2', 79, { best_lap_time_source: 'observed', best_lap_gap: 0, laps: { 1: '1:19.000' } }),
    driver('3', null, { best_lap_time_source: null, best_lap_gap: 0, laps: { 1: '1:18.000' } }),
    driver('4', 'invalid', { best_lap_gap: 0 }),
    { racing_number: '5', best_lap_gap: 0, laps: { 1: '1:17.000' } },
    driver('6', 76, { best_lap_time_source: undefined, best_lap_gap: 0 }),
    driver('7', 81),
  ]);
  const result = model(hass);
  assert.deepEqual(gaps(result), { 1: 0, 2: null, 3: null, 4: null, 5: null, 6: null, 7: 1 });
  assert.equal(result.rows.find(row => row.id === '3').best_lap.time, null);
  assert.equal(result.rows.find(row => row.id === '5').best_lap.time, 77);
});

test('ties remain zero and a session without valid official laps has no gap', () => {
  assert.deepEqual(gaps(model(fixture([driver('1', 80), driver('2', 80)]))), { 1: 0, 2: 0 });
  assert.deepEqual(gaps(model(fixture([driver('1', null), driver('2', 0), driver('3', -1)]))), { 1: null, 2: null, 3: null });
});

test('new fastest laps and slower or cleared corrections recompute every calculated gap', () => {
  const drivers = [driver('1', 80), driver('2', 81)];
  const hass = fixture(drivers);
  assert.deepEqual(gaps(model(hass)), { 1: 0, 2: 1 });
  drivers[1].best_lap_time = 79;
  assert.deepEqual(gaps(model(hass)), { 1: 1, 2: 0 });
  drivers[1].best_lap_time = 82;
  assert.deepEqual(gaps(model(hass)), { 1: 0, 2: 2 });
  drivers[0].best_lap_time = null;
  drivers[0].laps = { 1: '1:20.000' };
  assert.deepEqual(gaps(model(hass)), { 1: null, 2: 0 });
});

test('session changes and backwards replay seeks do not retain an old fastest reference', () => {
  const hass = fixture([driver('1', 80), driver('2', 81)]), store = new SectorStore();
  assert.deepEqual(gaps(model(hass, { store, key: 'practice-1' })), { 1: 0, 2: 1 });
  hass.states['sensor.positions'].attributes.drivers = [driver('1', 90), driver('2', 92)];
  assert.deepEqual(gaps(model(hass, { store, key: 'practice-2', name: 'Practice 2' })), { 1: 0, 2: 2 });
  hass.states['sensor.positions'].attributes.drivers = [driver('1', 95), driver('2', null)];
  assert.deepEqual(gaps(model(hass, { store, key: 'practice-2', name: 'Practice 2' })), { 1: 0, 2: null });
});

test('practice best lap gaps never replace race gaps or current qualifying part gaps', () => {
  const hass = fixture([
    driver('1', 80, { best_lap_gap: 0, q1_time: 90, gap_to_leader: '', interval_to_position_ahead: '' }),
    driver('2', 81, { best_lap_gap: 1, q1_time: 92, gap_to_leader: '+12.300', interval_to_position_ahead: '+4.500' }),
  ]);
  for (const name of ['Qualifying', 'Sprint Qualifying', 'Sprint', 'Race', 'unknown']) {
    const result = model(hass, { name });
    assert.deepEqual(gaps(result), { 1: null, 2: null }, name);
    assert.equal(result.rows[1].gap, '+12.300');
    assert.equal(result.rows[1].interval, '+4.500');
    assert.equal(result.rows[1].qualifying_gap, name.includes('Qualifying') ? 2 : null);
  }
});

test('best lap gaps render at millisecond precision with a zero leader and missing placeholder', async () => {
  const view = await moduleView();
  view.module = { type: 'timing', options: {}, fields: ['best_lap_gap'] };
  view.model = { sessionKind: 'practice' };
  assert.equal(view.cell({ best_lap_gap: 82.847 - 82.631 }, 'best_lap_gap'), '<span class="time">+0.216</span>');
  assert.equal(view.cell({ best_lap_gap: 0 }, 'best_lap_gap'), '<span class="time">0.000</span>');
  assert.equal(view.cell({ best_lap_gap: null }, 'best_lap_gap'), '—');
});
