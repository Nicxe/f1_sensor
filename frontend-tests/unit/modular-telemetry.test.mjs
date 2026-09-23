import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig, exportConfig, importConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { telemetryModel, telemetryPlan, telemetrySegments, canonicalSelections } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/telemetry-data.js';
import { replayModel } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';
const module = (options = {}) => normalizeConfig({ modules: [{ type: 'telemetry', options: { session_id: 'demo-replay', selected: ['16:2', '4:2'], ...options } }] }).modules[0];
const demo = makeDemo('replay'), entry = demo.preview.entries[0], read = demo.preview.telemetry;

test('telemetry configuration bounds selections and preserves channels, presentation and replay identity on export', () => {
  for (const selected of [['0:1'], ['100:1'], ['1:501'], ['1:0'], ['1:1', '1:2', '1:3', '1:4', '1:5']]) assert.throws(() => module({ selected }));
  const config = normalizeConfig({ modules: [{ ...module(), fields: ['telemetry_gear', 'telemetry_delta_s'], options: { ...module().options, axis: 'distance', presentation: 'both' } }] });
  assert.deepEqual(importConfig(exportConfig(config)), config);
  assert.deepEqual(canonicalSelections(['16:2', '4:3', '4:2']), [{ driver_number: 4, lap_number: 2 }, { driver_number: 4, lap_number: 3 }, { driver_number: 16, lap_number: 2 }]);
});

test('telemetry only plans a local catalogue before an explicit valid comparison and rejects changed replay selections', () => {
  const replay = replayModel(demo.hass, entry), plan = telemetryPlan(module(), entry, replay, read);
  assert.equal(plan.requests.length, 1); assert.ok(plan.requests[0].type.endsWith('telemetry_catalog'));
  assert.equal(plan.canCompare, true);
  assert.equal(telemetryPlan(module(), entry, replay, read, plan.compareQuery).requests.length, 2);
  assert.equal(telemetryPlan(module({ selected: ['16:40'] }), entry, replay, read).canCompare, false);
  const different = telemetryPlan(module({ session_id: 'another-session' }), entry, replay, read, plan.compareQuery);
  assert.equal(different.selectionChanged, true); assert.equal(different.activeCompare, null);
  const idle = telemetryPlan(module(), entry, { ...replay, loaded: false, sessionId: null }, read, plan.compareQuery);
  assert.deepEqual(idle.requests, []); assert.equal(idle.selectionChanged, false); assert.deepEqual(idle.missing, []);
});

test('telemetry models preserve zero signals and per-sample time coordinates, rejecting stale or mismatched responses', () => {
  const config = module(), query = telemetryPlan(config, entry, replayModel(demo.hass, entry), read).compareQuery;
  const model = telemetryModel(demo.hass, entry, config, read, query);
  assert.equal(model.compared, true); assert.equal(model.reference, '4:2');
  assert.equal(model.series[0].samples[0].time_s, 0); assert.equal(model.series[0].samples[0].throttle, 0); assert.equal(model.series[0].samples[0].delta_s, 0);
  const wrong = query => { const state = read(query); if (query.type.endsWith('compare')) state.data.payload.session_id = 'wrong'; return state; };
  assert.equal(telemetryModel(demo.hass, entry, config, wrong, query).compareError, true);
  assert.deepEqual(telemetryModel(demo.hass, entry, config, wrong, query).series, []);
  const foreign = query => { const state = read(query); if (query.type.endsWith('compare')) state.data.payload.series[0].driver_number = 99; return state; };
  assert.equal(telemetryModel(demo.hass, entry, config, foreign, query).compareError, true);
  const offline = query => ({ ...read(query), status: 'disconnected' });
  assert.equal(telemetryModel(demo.hass, entry, config, offline, query).compared, false);
});

test('telemetry paths break at missing values, large time gaps, nonmonotonic coordinates and recorded downsampling gaps', () => {
  const samples = [
    { time_s: 0, distance: 0, speed: 100 }, { time_s: .3, distance: 10, speed: 110 },
    { time_s: .5, distance: 20, speed: null }, { time_s: 1, distance: 30, speed: 120 },
    { time_s: 8, distance: 100, speed: 150 }, { time_s: 8.2, distance: 110, speed: 160, gap_before: true },
  ];
  assert.deepEqual(telemetrySegments(samples, 'speed').map(segment => segment.map(point => point.x)), [[0, .3], [1], [8], [8.2]]);
  assert.deepEqual(telemetrySegments(samples, 'speed', 'distance')[0], [{ x: 0, y: 100 }, { x: 10, y: 110 }]);
  assert.deepEqual(telemetrySegments([{ time_s: 0, distance: null, delta_s: null }], 'delta_s', 'distance'), []);
});
