import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig, duplicateModule } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { timingRows } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';
import { SectorStore } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/semantics.js';
import { moduleView } from './card-module.mjs';

const entry = { entry_id: 'checkpoint-fixture', entities: { driver_positions: 'sensor.positions', driver_list: 'sensor.roster' } };
const context = { key: 'qualifying:1', name: 'Qualifying' };
const comparison = extra => ({ status: 'available', lap: 2, session_part: 1,
  reference: { racing_number: '16', lap: 2, time: 95.2 },
  sector_1: -.008, sector_2: .357, sector_3: 1.041, latest_sector: 3, ...extra });
const fixture = (extra = {}) => ({ states: {
  'sensor.roster': { state: '2', attributes: { drivers: [{ racing_number: '16', tla: 'LEC' }] } },
  'sensor.positions': { state: 'unknown', attributes: { push_laps_status: 'available', current_qualifying_part: 1,
    drivers: [{ racing_number: '63', tla: 'RUS', current_position: 4,
      push_lap: { state: 'push', active: true, lap: 2, progress: .8 },
      push_lap_delta: comparison(), ...extra }] } },
} });
const moduleFor = options => normalizeConfig({ modules: [{ id: 'timing', type: 'timing', options: { push_laps: 'only', push_lap_deltas: true, ...options } }] }).modules[0];
const read = (hass = fixture(), options = {}, selected = context) => timingRows(hass, entry, selected, new SectorStore(), moduleFor(options));

test('checkpoint comparison defaults off and remains an independent choice when duplicated', () => {
  const config = normalizeConfig({ modules: [{ id: 'timing', type: 'timing' }] });
  assert.equal(config.modules[0].options.push_lap_deltas, false);
  config.modules[0].options.push_lap_deltas = true;
  const copy = duplicateModule(config, 'timing');
  copy.modules[1].options.push_lap_deltas = false;
  assert.equal(copy.modules[0].options.push_lap_deltas, true);
  assert.equal(copy.modules[1].options.push_lap_deltas, false);
});

test('current push checkpoints keep their cumulative signs, reference and physical order', () => {
  const result = read();
  const delta = result.rows[0].push_lap_delta;
  assert.equal(delta.reference.driver, 'LEC');
  assert.equal(delta.reference.time, 95.2);
  assert.deepEqual([delta.sector_1, delta.sector_2, delta.sector_3], [-.008, .357, null]);
  assert.equal(delta.latest_sector, 2);
  assert.equal(result.rows[0].position, 4);
  assert.equal(result.rows[0].push_group, 'active');
  const filtered = timingRows(fixture(), entry, context, new SectorStore(), { ...moduleFor(), driver: '63' });
  assert.equal(filtered.rows[0].push_lap_delta.reference.driver, 'LEC');
});

test('the held completed attempt retains the final comparison against its earlier reference', () => {
  const result = read(fixture({ push_lap: { state: 'completed', active: false, lap: 2, progress: 1, last_lap_time: 96.241 } }));
  assert.equal(result.rows[0].push_group, 'completed');
  assert.equal(result.rows[0].push_lap_delta.sector_3, 1.041);
  assert.equal(result.rows[0].push_lap_delta.latest_sector, 3);
});

test('deltas require opt-in, enabled push presentation and a qualifying session', () => {
  assert.equal(read(fixture(), { push_lap_deltas: false }).rows[0].push_lap_delta, null);
  assert.equal(read(fixture(), { push_laps: 'off' }).rows[0].push_lap_delta, null);
  for (const name of ['Practice 1', 'Race', 'Sprint']) {
    const model = read(fixture(), { push_laps: 'first' }, { ...context, name });
    assert.equal(model.pushDeltas, false);
    assert.equal(model.rows[0].push_lap_delta, null);
  }
  assert.equal(read(fixture(), {}, { ...context, name: 'Sprint Qualifying' }).rows[0].push_lap_delta.sector_1, -.008);
});

test('missing, corrected, wrong-lap and wrong-part comparisons remain unknown rather than zero', () => {
  for (const supplied of [undefined, comparison({ status: 'waiting' }), comparison({ status: 'unavailable' }), comparison({ lap: 3 }), comparison({ session_part: 2 }), comparison({ reference: null }), comparison({ reference: { racing_number: '16', time: null } })]) {
    const delta = read(fixture({ push_lap_delta: supplied })).rows[0].push_lap_delta;
    assert.equal(delta.reference, null);
    assert.deepEqual([delta.sector_1, delta.sector_2, delta.sector_3], [null, null, null]);
  }
  const validZero = read(fixture({ push_lap_delta: comparison({ sector_1: 0 }) })).rows[0].push_lap_delta;
  assert.equal(validZero.sector_1, 0);
  const missing = read(fixture({ push_lap_delta: comparison({ sector_1: null, sector_2: true }) })).rows[0].push_lap_delta;
  assert.equal(missing.sector_1, null);
  assert.equal(missing.sector_2, null);
});

test('retained, disconnected and stale direct sources cannot expose saved checkpoint differences', () => {
  const retained = read(fixture(), { push_laps: 'first' }, { ...context, retained: true });
  assert.equal(retained.rows[0].push_lap_delta, null);
  const hass = fixture(); hass.connection = { connected: false };
  assert.equal(read(hass, { push_laps: 'first' }).rows[0].push_lap_delta, null);
  const directEntry = { ...entry, data_api: { enabled: ['driver_positions'] }, card_data: {
    driver_positions: { status: 'ready', data: { status: 'stale', payload: { state: 'unknown', attributes: fixture().states['sensor.positions'].attributes } } },
  } };
  const stale = timingRows(fixture(), directEntry, context, new SectorStore(), moduleFor({ push_laps: 'first' }));
  assert.equal(stale.rows[0].push_lap_delta, null);
});

test('active checkpoint visibility follows actual completed progress and clears after a replay lap change', () => {
  for (const [progress, expected] of [[.1, [null, null, null]], [.4, [-.008, null, null]], [.8, [-.008, .357, null]]]) {
    const delta = read(fixture({ push_lap: { state: 'push', active: true, lap: 2, progress } })).rows[0].push_lap_delta;
    assert.deepEqual([delta.sector_1, delta.sector_2, delta.sector_3], expected);
  }
  const delta = read(fixture({ push_lap: { state: 'push', active: true, lap: 1, progress: .4 } })).rows[0].push_lap_delta;
  assert.equal(delta.sector_1, null);
});

test('sector rendering keeps cumulative differences distinct from sector status and explains unknowns', async () => {
  const view = await moduleView();
  view.module = moduleFor(); view.model = read();
  view.settings = { mode: 'dark', appearance: { palette: {} }, accessibility: { signals: 'shape' } };
  const row = view.model.rows[0];
  const s1 = view.cell(row, 'sector_1');
  assert.match(s1, /Δ -0\.008/);
  assert.match(s1, /Cumulative difference after S1: -0\.008 s/);
  assert.match(view.cell(row, 'sector_2_with_minisectors'), /Δ \+0\.357/);
  assert.match(view.cell(row, 'sector_3'), /Cumulative difference after S3 unavailable/);
  assert.match(view.pushLapMarker(row), /Against LEC 1:35\.200 · Q1/);
  assert.doesNotMatch(view.cell(row, 'best_sector_1'), /push-delta/);
});
