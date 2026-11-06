import assert from 'node:assert/strict';
import test from 'node:test';
import { raceTraceSource, raceTraceMarkerSource } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/race-trace-source.js';
import { raceTraceMarkers } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/race-trace-markers.js';

function fixture() {
  const context = { token: 'token-1', entry_id: 'one', source: 'replay', session_id: 'race-1', source_epoch: 'source-1', delay_epoch: 0, delay_seconds: 50 };
  const cursor = sequence => ({ sequence, source_time_ms: sequence * 1000, time_domain: 'replay_offset' });
  const entry = { entry_id: 'one', data_api: { lap_history_version: 1, enabled: ['driver_positions', 'session_context'] }, card_data: {} };
  for (const dataset of entry.data_api.enabled) entry.card_data[dataset] = { status: 'ready', data: {
    protocol_version: 1, entry_id: 'one', dataset, generation: 'first', revision: 1, source: 'replay', status: 'ready',
    context: { session_id: 'race-1', replay_generation: 2, delay_seconds: 50 },
    payload: { attributes: dataset === 'session_context' ? { no_spoiler: false } : {
      lap_history_version: 1, lap_history_session_type: 'Race', drivers: [],
      race_trace_observation: { version: 1, status: 'ready', context, timing_as_of: cursor(100) },
    } },
  } };
  const event = { event_id: 'pit-1', revision: 1, kind: 'pit', phase: 'point', driver_number: 4, lap_number: 2,
    anchor_type: 'driver_lap', source: 'PitStopSeries', context_token: context.token, observation_cursor: cursor(90) };
  const snapshot = { version: 1, status: 'ready', reason: null, context: structuredClone(context), as_of: cursor(95), events: [event] };
  const analysis = { status: 'ready', data: { protocol_version: 1, status: 'ready', race_trace_markers: snapshot } };
  const observation = entry.card_data.driver_positions.data.payload.attributes.race_trace_observation;
  return { entry, analysis, observation, snapshot, cursor, event };
}

test('markers use a shared observed cursor, independent of the products publication revisions', () => {
  const { entry, analysis, snapshot } = fixture();
  entry.card_data.driver_positions.data.revision = 1;
  analysis.data.revision = 9999;
  const result = raceTraceMarkerSource(entry, analysis);
  assert.equal(result.status, 'ready');
  assert.deepEqual(result.events, snapshot.events);
  assert.equal(raceTraceSource(entry).status, 'ready');
});

test('old and malformed marker contracts leave the base Race Trace available', () => {
  for (const change of [
    f => delete f.entry.card_data.driver_positions.data.payload.attributes.race_trace_observation,
    f => delete f.analysis.data.race_trace_markers,
    f => { f.snapshot.version = 2; }, f => { f.observation.version = 2; },
    f => { f.analysis.data.protocol_version = 2; }, f => { f.snapshot.events = null; },
    f => { f.snapshot.events = Array(501).fill(f.event); },
  ]) {
    const f = fixture(); change(f);
    assert.notEqual(raceTraceMarkerSource(f.entry, f.analysis).status, 'ready');
    assert.equal(raceTraceSource(f.entry).status, 'ready');
  }
});

test('every ownership dimension must match timing and the direct entry envelope', () => {
  for (const [key, value] of [['token', 'old'], ['entry_id', 'two'], ['source', 'live'], ['session_id', 'race-2'], ['source_epoch', 'old'], ['delay_epoch', 2], ['delay_seconds', 0]]) {
    const f = fixture(); f.snapshot.context[key] = value;
    assert.equal(raceTraceMarkerSource(f.entry, f.analysis).status, 'pending', key);
  }
  for (const [key, value] of [['entry_id', 'two'], ['source', 'live'], ['session_id', 'race-2'], ['delay_seconds', 0], ['token', ''], ['source_epoch', null], ['delay_epoch', -1]]) {
    const f = fixture(); f.snapshot.context[key] = value; f.observation.context[key] = value;
    assert.notEqual(raceTraceMarkerSource(f.entry, f.analysis).status, 'ready', key);
  }
});

test('future analysis waits as a whole so an earlier correction can never resurface', () => {
  const f = fixture();
  f.snapshot.events.push({ ...f.event, revision: 2, lap_number: 3, observation_cursor: f.cursor(108) });
  f.snapshot.as_of = f.cursor(110);
  const pending = raceTraceMarkerSource(f.entry, f.analysis);
  assert.equal(pending.status, 'pending');
  assert.deepEqual(pending.events, []);
  f.observation.timing_as_of = f.cursor(110);
  const ready = raceTraceMarkerSource(f.entry, f.analysis);
  const trace = { status: 'ready', referenceDriver: '4', series: [{ id: '4' }], rounds: [{ id: 2 }, { id: 3 }] };
  assert.deepEqual(raceTraceMarkers(trace, ready, ['pit']).events.map(event => event.lap), [3]);
});

test('unknown and incompatible observation clocks never use publication time as a substitute', () => {
  for (const change of [
    f => { f.snapshot.as_of = null; }, f => { f.observation.timing_as_of = null; },
    f => { f.snapshot.as_of.time_domain = 'utc'; }, f => { f.snapshot.as_of.sequence = 0; },
    f => { f.snapshot.as_of.source_time_ms = null; }, f => { f.snapshot.as_of.source_time_ms = 1.5; }, f => { f.snapshot.as_of.source_time_ms = 100001; },
    f => { f.observation.timing_as_of.source_time_ms = Infinity; },
    f => { f.observation.timing_as_of.time_domain = f.snapshot.as_of.time_domain = 'utc'; }, f => { f.observation.status = 'pending'; },
    f => { f.snapshot.status = 'unavailable'; },
  ]) {
    const f = fixture(); f.analysis.data.generated_at = new Date().toISOString(); change(f);
    assert.notEqual(raceTraceMarkerSource(f.entry, f.analysis).status, 'ready');
    assert.deepEqual(raceTraceMarkerSource(f.entry, f.analysis).events, []);
  }
});

test('invalid event provenance invalidates all its revisions without hiding independent valid events', () => {
  for (const change of [
    event => { event.context_token = 'old'; }, event => { event.observation_cursor = null; },
    event => { event.observation_cursor.sequence = 96; }, event => { event.observation_cursor.time_domain = 'utc'; },
    event => { event.observation_cursor.source_time_ms = 95001; },
  ]) {
    const f = fixture(); f.event.event_id = ' pit-1 ';
    const correction = structuredClone(f.event); correction.revision = 2; change(correction);
    f.snapshot.events.push(correction, { ...f.event, event_id: 'safe' });
    assert.deepEqual(raceTraceMarkerSource(f.entry, f.analysis).events.map(event => event.event_id), ['safe']);
  }
});

test('a reference anchor must predate its actual event in the same observed clock', () => {
  const f = fixture();
  const event = { ...f.event, kind: 'vsc', phase: 'start', source: 'TrackStatus', reference_anchors: {
    4: { lap_number: 2, basis: 'confirmed_completed', observation_cursor: f.cursor(80) },
    81: { lap_number: 3, basis: 'confirmed_completed', observation_cursor: f.cursor(91) },
    16: { lap_number: 2, basis: 'confirmed_completed', observation_cursor: { ...f.cursor(80), source_time_ms: 90001 } },
  } };
  f.snapshot.events = [event];
  const result = raceTraceMarkerSource(f.entry, f.analysis);
  assert.equal(result.status, 'ready');
  assert.deepEqual(result.events[0].reference_anchors['4'], event.reference_anchors['4']);
  assert.equal(result.events[0].reference_anchors['81'], null);
  assert.equal(result.events[0].reference_anchors['16'], null);
  event.reference_anchors['04'] = event.reference_anchors['81'];
  const trace = { status: 'ready', referenceDriver: '4', series: [{ id: '4' }], rounds: [{ id: 2 }, { id: 3 }] };
  assert.deepEqual(raceTraceMarkers(trace, raceTraceMarkerSource(f.entry, f.analysis), ['vsc']).events, []);
  delete event.reference_anchors['04'];
  assert.deepEqual(Object.keys(event.reference_anchors), ['4', '16', '81']);
});

test('delay 0→30→0 never accepts a previous delay epoch and data remains immutable', () => {
  const f = fixture(); f.observation.context.delay_epoch = 2; f.observation.context.token = 'token-3';
  const before = JSON.stringify(f);
  assert.equal(raceTraceMarkerSource(f.entry, f.analysis).status, 'pending');
  assert.equal(JSON.stringify(f), before);
});

test('No Spoiler, unknown protection, disconnect and analysis reconnect all fail closed', () => {
  for (const protection of [true, null, undefined]) {
    const f = fixture(); f.entry.card_data.session_context.data.payload.attributes.no_spoiler = protection;
    assert.deepEqual(raceTraceMarkerSource(f.entry, f.analysis).events, []);
  }
  for (const status of ['loading', 'refreshing', 'disconnected', 'error']) {
    const f = fixture(); f.analysis.status = status;
    assert.deepEqual(raceTraceMarkerSource(f.entry, f.analysis).events, []);
  }
  const f = fixture(); assert.deepEqual(raceTraceMarkerSource(f.entry, f.analysis, false).events, []);
});
