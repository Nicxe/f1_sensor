import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { archiveModel, archivePlan } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/season-data.js';
import { HistoryResources, connectionDiagnostics } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/connection.js';
import { fieldDefinition, moduleFields } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';
const module = (options = {}, extra = {}) => normalizeConfig({ modules: [{ type: 'archive', options: { year: 2024, ...options }, ...extra }] }).modules[0];
const demo = makeDemo('race'), read = demo.preview.history;
const turn = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; };

test('archive selection uses past supported sessions and never substitutes an explicitly missing selection', () => {
  const plan = archivePlan(module(), 'one', read, Date.parse('2024-02-13T14:00:00Z'));
  assert.equal(plan.meeting.round, 2); assert.equal(plan.session.kind, 'qualifying');
  assert.equal(plan.requests.length, 2); assert.ok(plan.requests.every(query => query.entry_id === 'one'));
  assert.equal(archivePlan(module({ round: '99' }), 'one', read).session, null);
  assert.equal(archivePlan(module({ round: '1', session_key: 'demo:2024:2:race' }), 'one', read).requests.length, 1);
  assert.equal(archivePlan(module({ round: '1', session_key: 'demo:2024:1:practice' }), 'one', read).unsupported, true);
  const chart = archivePlan(module({ content: 'lap_position' }), 'one', read, Date.parse('2024-02-13T14:00:00Z'));
  assert.equal(chart.meeting.round, 1); assert.equal(chart.session.kind, 'race'); assert.equal(chart.requests.length, 3);
  assert.equal(archivePlan(module(), 'one', read, Date.parse('2023-12-31T23:00:00Z')).requests.length, 1);
});

test('pinned archive identity resolves through catalogue keys without parsing display names', () => {
  const selection = { mode: 'pinned', source: 'archive', season: 2024, meeting_key: 'jolpica:2024:1', session_key: 'demo:2024:1:race' };
  const plan = archivePlan(module({}, { selection }), 'one', read);
  assert.equal(plan.year, 2024);
  assert.equal(plan.meeting.round, 1);
  assert.equal(plan.session.kind, 'race');
  assert.equal(plan.requests.length, 2);
  const missing = archivePlan(module({}, { selection: { ...selection, meeting_key: 'other' } }), 'one', read);
  assert.equal(missing.meeting, null);
  assert.equal(missing.session, null);
  assert.equal(missing.requests.length, 1);
});

test('archive field contracts and classifications preserve published IDs, zero values and qualifying gaps', () => {
  const config = module(), model = archiveModel(config, 'one', read);
  assert.equal(model.rows[0].id, 'demo-driver-16'); assert.equal(model.rows.at(-1).points, 0);
  assert.equal(model.rows.at(-1).grid_position, 0); assert.equal(model.rows.at(-1).position_change, null);
  assert.equal(model.rows[0].q1_time, 82.123); assert.equal(model.rows.at(-1).q2_time, null);
  assert.deepEqual(module({ content: 'lap_time' }).fields, ['lap_series']);
  assert.deepEqual(archiveModel(module({ round: '1', session_key: 'demo:2024:1:qualifying' }), 'one', read).fields, ['result_position', 'driver', 'team', 'q1_time', 'q2_time', 'q3_time']);
  assert.deepEqual(archiveModel(module({}, { fields: ['driver', 'points'] }), 'one', read).fields, ['driver', 'points']);
  assert.equal(fieldDefinition(config, 'driver').source, 'history/results');
  assert.deepEqual(fieldDefinition(config, 'driver').modes, ['history']);
  assert.ok(!moduleFields(module({ content: 'lap_time' })).includes('q1_time'));
  const filtered = archiveModel(module({ selected: ['driver-from-another-year'] }), 'one', read);
  assert.equal(filtered.rows.length, 0); assert.equal(filtered.filtered, true);
});

test('archive lap charts retain lap numbers and gaps, reject wrong-session responses and do not join reused driver numbers', () => {
  const config = module({ content: 'lap_time', start_lap: 4, end_lap: 8, selected: ['demo-driver-16'] });
  const model = archiveModel(config, 'one', read);
  assert.deepEqual(model.rounds.map(item => item.id), ['4', '5', '6', '7', '8']);
  assert.equal(model.series.length, 1); assert.equal(model.series[0].values[2].value, null);
  const modified = query => {
    const state = read(query);
    if (query.type.endsWith('/results')) state.data.payload.results = [{ driver_name: 'Different historic driver', driver_number: '16', position: 1, constructor_name: 'Historic Team' }];
    return state;
  };
  const oldBackend = archiveModel(config, 'one', modified);
  assert.equal(oldBackend.series[0].name, 'demo-driver-16'); assert.notEqual(oldBackend.series[0].name, oldBackend.allRows[0].name);
  const wrong = query => { const state = read(query); if (query.type.endsWith('/laps')) state.data.payload.round = 99; return state; };
  const rejected = archiveModel(config, 'one', wrong);
  assert.equal(rejected.invalidIdentity, true); assert.ok(rejected.series.every(item => item.values.every(point => point.value === null)));
  assert.equal(archiveModel(module({ content: 'lap_time', start_lap: 9, end_lap: 2 }), 'one', read).invalidRange, true);
});

test('ten history consumers share requests, recover only on explicit retry or reconnect, and clean up', async () => {
  const listeners = new Map(); let requests = 0, fail = true;
  const connection = { addEventListener(type, cb) { if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(cb); }, removeEventListener(type, cb) { listeners.get(type)?.delete(cb); } };
  const hass = { connection, async callWS() { requests++; if (fail) throw new Error('offline'); return { year: 2024 }; }, callService() { assert.fail('History must never control replay'); } };
  const query = { type: 'f1_sensor/history/catalog', entry_id: 'one', year: 2024 };
  const stores = Array.from({ length: 10 }, () => new HistoryResources(() => {}));
  stores.forEach(store => store.sync(hass, [query])); await turn();
  assert.equal(requests, 1); assert.equal(stores[0].read(query).data.failed, true);
  await new Promise(resolve => setTimeout(resolve, 1100)); assert.equal(requests, 1);
  fail = false; stores[0].retry([query]); stores[1].retry([query]); await turn();
  assert.equal(requests, 2); assert.equal(stores[9].read(query).data.payload.year, 2024);
  for (const cb of listeners.get('disconnected')) cb();
  assert.equal(stores[0].read(query).status, 'disconnected');
  for (const cb of listeners.get('ready')) cb(); await turn(); assert.equal(requests, 3);
  stores.forEach(store => store.close());
  assert.deepEqual(connectionDiagnostics(connection), { resources: 0, consumers: 0, groups: 0 });
  assert.ok([...listeners.values()].every(set => set.size === 0));
});

test('history detaches obsolete session queries before their responses arrive', async () => {
  const pending = deferred(), store = new HistoryResources(() => {});
  const a = { type: 'f1_sensor/history/results', entry_id: 'one', year: 2024, round: 1, session_type: 'race', session_key: 'one' }, b = { ...a, round: 2, session_key: 'two' };
  const hass = { connection: {}, callWS: query => query.round === 1 ? pending.promise : Promise.resolve({ results: [{ driver_id: 'correct-driver' }] }) };
  store.sync(hass, [a]); await turn(); store.sync(hass, [b]); await turn();
  pending.resolve({ results: [{ driver_id: 'obsolete-driver' }] }); await turn();
  assert.equal(store.read(a).data, null); assert.equal(store.read(b).data.payload.results[0].driver_id, 'correct-driver');
  store.close();
});
