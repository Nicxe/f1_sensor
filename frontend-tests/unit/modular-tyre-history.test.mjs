import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig, exportConfig, importConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { moduleTitle, fieldDefinition, moduleFields, MODULES } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js';
import { RetainedSources } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';
import { tyresModel } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/session-data.js';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';

const module = (options = {}, extra = {}) => normalizeConfig({ modules: [{ type: 'tyres', options: { content: 'history', ...options }, ...extra }] }).modules[0];
const stint = (overrides = {}) => ({ stint_index: 0, compound: 'MEDIUM', new: true, first_lap: 1, last_lap: 20, stint_laps: 20, tyre_age_at_start: 0, total_laps: 20, is_current: false, coverage: 'complete', ...overrides });
const driver = (overrides = {}) => ({ racing_number: '4', position: 1, compound: 'HARD', new: false, stint_laps: 17, completed_laps: 34, stint_history_complete: true,
  stints: [stint(), stint({ stint_index: 1, compound: 'HARD', new: false, first_lap: 21, last_lap: 34, stint_laps: 14, tyre_age_at_start: 3, total_laps: 17, is_current: true })], ...overrides });
function fixture(drivers = [driver()]) {
  const demo = makeDemo(), entry = demo.preview.entries[0], attrs = demo.hass.states[entry.entities.current_tyres].attributes;
  Object.assign(attrs, { drivers, lap_current: 35, lap_total: 56 });
  return { ...demo, entry, attrs, read(options = {}, extra = {}, focus = {}) { return tyresModel(this.hass, entry, module(options, extra), focus); } };
}

test('tyre history is optional and its compound legend survives configuration transfers', () => {
  const original = normalizeConfig({ modules: [{ type: 'tyres' }] }).modules[0];
  assert.equal(original.options.content, 'current');
  const config = normalizeConfig({ modules: [{ type: 'tyres', options: { content: 'history', show_legend: false } }] });
  assert.equal(module().options.show_legend, true);
  assert.equal(config.modules[0].options.show_legend, false);
  assert.deepEqual(importConfig(exportConfig(config)), config);
  assert.deepEqual(module().fields, ['position', 'driver', 'tyre_age']);
  assert.deepEqual(moduleFields(module()), ['position', 'driver', 'tyre_age']);
  assert.equal(moduleTitle(module()), 'Tyre history');
  assert.equal(moduleTitle(module({}, { title: 'My tyre chart' })), 'My tyre chart');
  assert.match(fieldDefinition(module(), 'tyre_age').path, /stints.*total_laps/);
  assert.throws(() => module({ show_legend: 'false' }), /show_legend/);
});

test('used tyres keep race stint distance separate from total tyre age and pre-use', () => {
  const d = fixture(), model = d.read(), row = model.rows[0];
  assert.equal(model.history, true); assert.equal(model.statistics, false);
  assert.equal(row.driver, 'NOR'); assert.equal(row.tyre_age, 17);
  assert.deepEqual(row.stints.map(({ stint_laps, start_age, total_age }) => [stint_laps, start_age, total_age]), [[20, 0, 20], [14, 3, 17]]);
  assert.deepEqual(row.stints.map(({ first_lap, last_lap, status }) => [first_lap, last_lap, status]), [[1, 20, 'completed'], [21, 34, 'current']]);
  assert.equal(row.completed_laps, 34); assert.equal(row.history_complete, true);
  assert.deepEqual(model.axis, { min: 0, max: 56, current: 35, total: 56 });
});

test('editor sample history follows the existing session laps and includes a used fitted set', () => {
  const demo = makeDemo(), entry = demo.preview.entries[0];
  const model = tyresModel(demo.hass, entry, module());
  assert.deepEqual(model.axis, { min: 0, max: 53, current: 12, total: 53 });
  assert.equal(model.rows.length, 5);
  for (const row of model.rows) {
    assert.equal(row.stints.length, 2);
    assert.equal(row.stints.at(-1).last_lap, 12);
    assert.equal(row.stints.reduce((sum, stint) => sum + stint.stint_laps, 0), 12);
    assert.equal(row.tyre_age, row.stints.at(-1).total_age);
  }
  const used = model.rows.find(row => row.number === '1').stints.at(-1);
  assert.equal(used.start_age, 3); assert.equal(used.total_age, used.stint_laps + 3);
});

test('same-compound changes remain distinct chronological stints and corrections replace their values', () => {
  const d = fixture([driver({ stints: [stint({ stint_index: 1, first_lap: 21, last_lap: 34, stint_laps: 14, is_current: true }), stint()] })]);
  let row = d.read().rows[0];
  assert.deepEqual(row.stints.map(s => s.id), ['4:0', '4:1']);
  assert.deepEqual(row.stints.map(s => s.tyre), ['MEDIUM', 'MEDIUM']);
  d.attrs.drivers[0].stints.push(stint({ stint_index: 1, first_lap: 21, last_lap: 35, stint_laps: 15, total_laps: 18, is_current: true }));
  row = d.read().rows[0];
  assert.equal(row.stints.length, 2); assert.equal(row.stints[1].last_lap, 35); assert.equal(row.tyre_age, 18);
  d.attrs.drivers[0].stints = [stint({ last_lap: 10, stint_laps: 10, total_laps: 10, is_current: true })];
  assert.deepEqual(d.read().rows[0].stints.map(s => s.id), ['4:0'], 'replay rewinds cannot retain future stints');
});

test('physical set numbers do not reuse sparse feed indexes or guess missing earlier stints', () => {
  const d = fixture([driver({ stints: [stint(), stint({ stint_index: 2, first_lap: 21, last_lap: 34, is_current: true })] })]);
  assert.deepEqual(d.read().rows[0].stints.map(s => [s.id, s.stint_number]), [['4:0', 1], ['4:2', 2]]);
  d.attrs.drivers[0].stint_history_complete = false;
  assert.deepEqual(d.read().rows[0].stints.map(s => s.stint_number), [null, null]);
  d.attrs.drivers[0].stint_history_complete = true;
  d.attrs.drivers[0].stints = [stint({ stint_index: 2, first_lap: 21, last_lap: 34, is_current: true })];
  assert.equal(d.read().rows[0].stints[0].stint_number, null, 'a partial session cannot establish the physical set ordinal');
});

test('unknown ages and unverified ranges stay unknown rather than becoming zero or invented bars', () => {
  const d = fixture([driver({ stint_history_complete: false, stints: [stint({ compound: 'EXPERIMENTAL', new: false, first_lap: null, last_lap: null, stint_laps: 8, tyre_age_at_start: null, total_laps: null, is_current: true, coverage: 'partial' })] })]);
  const row = d.read().rows[0], s = row.stints[0];
  assert.equal(row.tyre_age, null); assert.equal(row.history_complete, false);
  assert.equal(s.start_age, null); assert.equal(s.total_age, null); assert.equal(s.tyre_new, false);
  assert.equal(s.tyre, 'EXPERIMENTAL'); assert.equal(s.drawable, false); assert.equal(s.coverage, 'partial');
  assert.equal(d.read({ compounds: ['UNKNOWN'] }).rows.length, 1);
});

test('a just-fitted set preserves confirmed zero without drawing a completed lap', () => {
  const d = fixture([driver({ stints: [stint({ first_lap: 21, last_lap: 20, stint_laps: 0, tyre_age_at_start: 0, total_laps: 0, is_current: true })] })]);
  const row = d.read().rows[0];
  assert.equal(row.tyre_age, 0); assert.equal(row.stints[0].start_age, 0);
  assert.equal(row.stints[0].drawable, false);
});

test('the lap axis is shared before filtering and never extends a lapped driver to the leader', () => {
  const d = fixture([driver(), driver({ racing_number: '16', position: 2, completed_laps: 32, stints: [stint({ last_lap: 32, stint_laps: 32, total_laps: 32, is_current: true })] })]);
  d.attrs.lap_total = null;
  const focused = d.read({}, {}, { driver: '16' });
  assert.equal(focused.rows.length, 1); assert.equal(focused.rows[0].stints[0].last_lap, 32);
  assert.equal(focused.axis.max, 34); assert.equal(focused.axis.total, null);
  assert.equal(d.read({ rows: 1 }).axis.max, 34);
  const compound = d.read({ compounds: ['HARD'] });
  assert.equal(compound.rows.length, 1); assert.equal(compound.rows[0].stints.length, 2, 'compound filtering preserves the selected driver full timeline');
  assert.equal(d.read({}, { team: 'Ferrari' }).rows[0].number, '16');
});

test('session completion marks the final known stint completed', () => {
  const d = fixture();
  d.hass.states[d.entry.entities.current_session].attributes.active = false;
  d.hass.states[d.entry.entities.session_status].state = 'finished';
  assert.deepEqual(d.read().rows[0].stints.map(s => s.status), ['completed', 'completed']);
});

test('a retired driver keeps their own final lap and ends the fitted stint while the race continues', () => {
  const d = fixture([driver({ retired: true, in_pit: false, completed_laps: 27, stints: [stint({ last_lap: 27, stint_laps: 27, total_laps: 27, is_current: true })] })]);
  const row = d.read().rows[0];
  assert.equal(row.retired, true); assert.equal(row.in_pit, false);
  assert.equal(row.stints[0].is_current, true, 'the mounted set identity remains unchanged');
  assert.equal(row.stints[0].status, 'completed');
  assert.equal(row.stints[0].last_lap, 27);
  assert.equal(d.read().axis.max, 56);
});

test('missing and malformed history stays inspectable without synthetic stints', () => {
  const d = fixture([driver({ stints: [null, false, {}, stint({ stint_index: -1 })] })]);
  assert.deepEqual(d.read().rows[0].stints, []);
  d.attrs.lap_current = null; d.attrs.lap_total = null; d.attrs.drivers[0].completed_laps = null;
  assert.deepEqual(d.read().axis, { min: 0, max: null, current: null, total: null });
});

test('an unavailable tyre source cannot expose stale history attributes', () => {
  const d = fixture();
  d.hass.states[d.entry.entities.current_tyres].state = 'unavailable';
  assert.deepEqual(d.read().rows, []);
  assert.equal(d.read().axis.max, null);
});

for (const boundary of ['session', 'spoiler']) {
  test(`retained tyre history uses one snapshot and is removed at a ${boundary} boundary`, () => {
    const d = fixture(), config = normalizeConfig({ modules: [{ type: 'tyres', options: { content: 'history' }, unavailable: 'retain' }] });
    const store = new RetainedSources(), m = config.modules[0];
    const read = () => { store.update(d.hass, d.entry, config); return store.select(d.hass, d.entry, m, MODULES.tyres); };
    assert.equal(read().retained, false);
    d.hass = { ...d.hass, connection: { connected: false } };
    d.hass.states[d.entry.entities.current_tyres] = { state: 'unavailable', attributes: {} };
    const retained = read();
    assert.equal(retained.retained, true);
    assert.equal(tyresModel(retained.hass, d.entry, m).rows[0].stints[1].total_age, 17);
    if (boundary === 'session') d.hass.states[d.entry.entities.current_session] = { ...d.hass.states[d.entry.entities.current_session], attributes: { ...d.hass.states[d.entry.entities.current_session].attributes, start: '2026-09-14T13:00:00Z' } };
    else d.hass.states[d.entry.global_entities.no_spoiler_mode] = { state: 'on', attributes: {} };
    assert.equal(read().retained, false);
    assert.equal(store.snapshots.size, 0);
  });
}
