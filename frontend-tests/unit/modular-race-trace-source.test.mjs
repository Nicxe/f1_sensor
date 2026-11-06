import assert from 'node:assert/strict';
import test from 'node:test';
import { raceTraceSource, raceTraceSelectionKey } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/race-trace-source.js';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';

function fixture() {
  const entry = { entry_id: 'one', data_api: { lap_history_version: 1, enabled: ['driver_positions', 'session_context'] }, card_data: {} };
  for (const dataset of entry.data_api.enabled) entry.card_data[dataset] = { status: 'ready', data: {
    protocol_version: 1, entry_id: 'one', dataset, generation: 'first', revision: 1,
    source: 'replay', status: 'ready', context: { session_id: 'race-1', replay_generation: 2, delay_seconds: 50 },
    payload: { state: 'replay', attributes: dataset === 'session_context' ? { no_spoiler: false } : {
      lap_history_version: 1, lap_history_session_type: 'Race', drivers: [{ racing_number: '4', completed_laps: 2, laps: { 2: 90 }, lap_metadata: { 2: { association: 'confirmed', reason: null } } }],
    } },
  } };
  return entry;
}

test('Race Trace accepts only the advertised direct contract and its observed session type', () => {
  const entry = fixture();
  assert.equal(raceTraceSource(entry).status, 'ready');
  assert.equal(raceTraceSource(entry).drivers[0].racing_number, '4');
  const attributes = entry.card_data.driver_positions.data.payload.attributes;
  for (const type of [null, '', 'unknown']) {
    attributes.lap_history_session_type = type;
    assert.equal(raceTraceSource(entry).status, 'pending');
    assert.deepEqual(raceTraceSource(entry).drivers, []);
  }
  for (const type of ['Qualifying', 'Practice', 'Sprint Qualifying']) {
    attributes.lap_history_session_type = type;
    assert.equal(raceTraceSource(entry).status, 'not_applicable');
  }
  attributes.lap_history_session_type = 'Sprint';
  assert.equal(raceTraceSource(entry).status, 'ready');
  delete entry.data_api.lap_history_version;
  assert.equal(raceTraceSource(entry).status, 'unsupported');
  delete entry.data_api;
  entry.entities = { driver_positions: 'sensor.old' };
  assert.equal(raceTraceSource(entry).status, 'unsupported');
});

test('supported backend with missing observations waits without inventing an unsupported backend', () => {
  for (const change of [
    entry => delete entry.card_data.driver_positions,
    entry => { entry.card_data.driver_positions.data.payload = null; },
    entry => { entry.card_data.driver_positions.data.status = 'loading'; },
    entry => { entry.card_data.driver_positions.data.payload.attributes.drivers = null; },
    entry => { entry.card_data.driver_positions.data.payload.attributes.lap_history_version = null; },
  ]) {
    const entry = fixture(); change(entry);
    assert.equal(raceTraceSource(entry).status, 'pending');
    assert.deepEqual(raceTraceSource(entry).drivers, []);
  }
});

test('wrong entry, dataset, source, generation and lifecycle context never expose laps', () => {
  for (const [field, value] of [
    ['entry_id', 'two'], ['dataset', 'current_session'], ['source', 'live'], ['generation', 'old'], ['generation', null], ['protocol_version', 2], ['revision', 0],
  ]) {
    const entry = fixture(); entry.card_data.driver_positions.data[field] = value;
    assert.notEqual(raceTraceSource(entry).status, 'ready', field);
    assert.deepEqual(raceTraceSource(entry).drivers, [], field);
  }
  for (const [field, value] of [['session_id', 'other'], ['replay_generation', 1], ['delay_seconds', 0], ['session_id', null]]) {
    const entry = fixture(); entry.card_data.driver_positions.data.context[field] = value;
    assert.equal(raceTraceSource(entry).status, 'pending', field);
    assert.deepEqual(raceTraceSource(entry).drivers, []);
  }
});

test('unknown or active protection and blocked direct data cannot fall back to old entity attributes', () => {
  for (const protectedValue of [true, null, undefined, 'false']) {
    const entry = fixture();
    entry.card_data.session_context.data.payload.attributes.no_spoiler = protectedValue;
    entry.entities = { driver_positions: 'sensor.old' };
    assert.equal(raceTraceSource(entry).status, 'blocked');
    assert.deepEqual(raceTraceSource(entry).drivers, []);
  }
  const entry = fixture(); entry.card_data.driver_positions.data.status = 'blocked';
  assert.equal(raceTraceSource(entry).status, 'blocked');
  assert.deepEqual(raceTraceSource(entry).drivers, []);
});

test('disconnect and incomplete reconnect hide values but retain a same-context anchor identity', () => {
  const entry = fixture(), key = raceTraceSource(entry).contextKey;
  for (const status of ['disconnected', 'refreshing', 'error', 'loading']) {
    entry.card_data.driver_positions.status = status;
    const result = raceTraceSource(entry);
    assert.equal(result.status, 'pending');
    assert.equal(result.contextKey, key);
    assert.deepEqual(result.drivers, []);
  }
  entry.card_data.driver_positions.status = 'ready';
  assert.equal(raceTraceSource(entry, false).status, 'pending');
  assert.equal(raceTraceSource(entry).status, 'ready');
});

test('anchor identity changes for entry/session/generation/source/delay but not revision or display zoom', () => {
  const entry = fixture(), options = { reference_driver: '4', selected: ['81', '16'], start_lap: 1, end_lap: 500, anchor_lap: 0 };
  const initial = raceTraceSelectionKey(raceTraceSource(entry).contextKey, options);
  entry.card_data.driver_positions.data.revision++;
  assert.equal(raceTraceSelectionKey(raceTraceSource(entry).contextKey, { ...options, selected: ['16', '81'], start_lap: 20, end_lap: 30 }), initial);
  assert.notEqual(raceTraceSelectionKey(raceTraceSource(entry).contextKey, { ...options, reference_driver: '81' }), initial);
  assert.notEqual(raceTraceSelectionKey(raceTraceSource(entry).contextKey, { ...options, selected: ['16'] }), initial);
  assert.notEqual(raceTraceSelectionKey(raceTraceSource(entry).contextKey, { ...options, anchor_lap: 10 }), initial);
  for (const field of ['generation', 'source', 'session_id', 'replay_generation', 'delay_seconds', 'entry_id']) {
    const changed = fixture();
    for (const resource of Object.values(changed.card_data)) {
      if (field === 'generation') resource.data.generation = 'second';
      else if (field === 'source') resource.data.source = 'live';
      else if (field === 'entry_id') resource.data.entry_id = 'two';
      else resource.data.context[field] = field === 'session_id' ? 'race-2' : 3;
    }
    if (field === 'entry_id') changed.entry_id = 'two';
    assert.notEqual(raceTraceSelectionKey(raceTraceSource(changed).contextKey, options), initial, field);
  }
});

test('validation does not mutate an accepted source snapshot', () => {
  const entry = fixture(), before = structuredClone(entry);
  assert.deepEqual(raceTraceSource(entry), raceTraceSource(entry));
  assert.deepEqual(entry, before);
});

test('labelled sample preview supplies the same contract without adding a real-backend fallback', () => {
  const demo = makeDemo('race');
  assert.equal(raceTraceSource(demo.preview.raceTrace()).status, 'ready');
  assert.equal(raceTraceSource(demo.preview.entries[0]).status, 'unsupported');
  demo.hass.states[demo.preview.entries[0].global_entities.no_spoiler_mode].state = 'on';
  assert.equal(raceTraceSource(demo.preview.raceTrace()).status, 'blocked');
  assert.equal(raceTraceSource(makeDemo('qualifying').preview.raceTrace()).status, 'not_applicable');
  assert.equal(raceTraceSource(makeDemo('missing').preview.raceTrace()).status, 'pending');
});
