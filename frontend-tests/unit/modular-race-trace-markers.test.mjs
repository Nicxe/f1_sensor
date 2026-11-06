import assert from 'node:assert/strict';
import test from 'node:test';
import { raceTraceMarkers } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/race-trace-markers.js';

const trace = () => ({ status: 'ready', referenceDriver: '1', anchorLap: 1,
  rounds: [1, 2, 3, 4].map(id => ({ id })),
  series: [{ id: '1', values: [0, 0, 0, 0].map((delta_ms, index) => ({ round: index + 1, delta_ms })) },
    { id: '4', values: [0, -500, 500, 20500].map((delta_ms, index) => ({ round: index + 1, delta_ms })) }] });
const pit = (extra = {}) => ({ event_id: 'pit:4:stop1', revision: 1, kind: 'pit', phase: 'point',
  driver_number: 4, lap_number: 2, anchor_type: 'driver_lap', source: 'PitStopSeries', ...extra });
const flag = (extra = {}) => ({ event_id: 'track:vsc:start1', revision: 1, kind: 'vsc', phase: 'start', source: 'TrackStatus',
  reference_anchors: { 1: { lap_number: 2, basis: 'confirmed_completed' }, 4: { lap_number: 3, basis: 'confirmed_completed' } }, ...extra });
const snapshot = events => ({ status: 'ready', reason: null, events });
const markers = (events, model = trace(), kinds = ['pit', 'sc', 'vsc', 'red_flag']) => raceTraceMarkers(model, snapshot(events), kinds);
const freeze = value => { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); } return value; };

test('explicit pit lap produces one driver marker without changing hand-calculated deltas', () => {
  const model = freeze(trace()), before = structuredClone(model);
  const result = markers([pit()], model);
  assert.deepEqual(result, { status: 'ready', reason: null, events: [{ id: 'pit:4:stop1', revision: 1,
    kind: 'pit', phase: 'point', driver: '4', lap: 2, anchor_type: 'driver_lap', source: 'PitStopSeries', description: null }] });
  assert.deepEqual(model.series[1].values.map(point => point.delta_ms), [0, -500, 500, 20500]);
  assert.deepEqual(model, before);
});

test('pit points require the explicit selected driver, supported source and completed-lap anchor type', () => {
  const events = [pit({ driver_number: null }), pit({ driver_number: 'NOR' }), pit({ driver_number: 16 }),
    pit({ anchor_type: 'leader_lap' }), pit({ source: 'RaceControlMessages' })];
  for (const event of events) assert.deepEqual(markers([event]).events, []);
  assert.equal(markers([pit({ driver_number: '04' })]).events[0].driver, '4');
});

for (const lap of [null, 0, -1, 1.5, 501, '2', NaN, Infinity, true]) {
  test(`invalid normalized marker lap ${String(lap)} is not plotted`, () => {
    assert.deepEqual(markers([pit({ lap_number: lap })]).events, []);
    assert.deepEqual(markers([flag({ reference_anchors: { 1: { lap_number: lap, basis: 'confirmed_completed' } } })]).events, []);
  });
}

test('global markers use only the explicitly selected reference and confirmed observation', () => {
  assert.deepEqual(markers([flag()]).events.map(event => [event.driver, event.lap, event.anchor_type]), [['1', 2, 'reference_driver_lap']]);
  assert.deepEqual(markers([flag()], { ...trace(), referenceDriver: '4' }).events.map(event => [event.driver, event.lap]), [['4', 3]]);
  assert.deepEqual(markers([flag()], { ...trace(), referenceDriver: '81' }).events, []);
  assert.deepEqual(markers([flag({ lap_number: 2, reference_anchors: {} })]).events, []);
  for (const basis of [null, 'inferred', 'completed_count', 'leader_lap']) {
    assert.deepEqual(markers([flag({ reference_anchors: { 1: { lap_number: 2, basis } } })]).events, []);
  }
  assert.deepEqual(markers([flag({ reference_anchors: { 1: { lap_number: 2, basis: 'confirmed_completed' }, '01': { lap_number: 3, basis: 'confirmed_completed' } } })]).events, []);
});

test('each neutralisation keeps separate start, ending and observed end points without synthesising an interval', () => {
  const model = { ...trace(), rounds: [4, 5, 6, 7].map(id => ({ id })) };
  const events = [flag({ reference_anchors: { 1: { lap_number: 4, basis: 'confirmed_completed' } } }),
    flag({ event_id: 'track:vsc:ending1', phase: 'ending', reference_anchors: { 1: { lap_number: 6, basis: 'confirmed_completed' } } })];
  assert.deepEqual(markers(events, model).events.map(event => [event.phase, event.lap]), [['start', 4], ['ending', 6]]);
  events.push(flag({ event_id: 'track:vsc:end1', phase: 'end', reference_anchors: { 1: { lap_number: 6, basis: 'confirmed_completed' } } }));
  const result = markers(events, model);
  assert.deepEqual(result.events.map(event => [event.phase, event.lap]), [['start', 4], ['ending', 6], ['end', 6]]);
  assert.equal(result.events.some(event => 'end_lap' in event), false);
  for (const kind of ['sc', 'red_flag']) assert.equal(markers([flag({ kind })]).events[0].kind, kind);
});

test('unknown first-lap evidence stays unplotted instead of borrowing a later reference anchor', () => {
  const event = flag({ reference_anchors: {}, lap_number: 1 });
  assert.deepEqual(markers([event]).events, []);
  const updated = trace(); updated.series[0].values.push({ round: 5, delta_ms: 0 }); updated.rounds.push({ id: 5 });
  assert.deepEqual(markers([event], updated).events, []);
});

test('newest event revision replaces the prior point even when its corrected anchor is unsafe', () => {
  for (const events of [[pit(), pit({ revision: 2, lap_number: 3 })], [pit({ revision: 2, lap_number: 3 }), pit()]]) {
    assert.deepEqual(markers(events).events.map(event => [event.id, event.revision, event.lap]), [['pit:4:stop1', 2, 3]]);
  }
  for (const correction of [pit({ revision: 2, lap_number: null }), pit({ revision: 2, driver_number: null }), pit({ revision: 2, kind: 'unknown' })]) {
    assert.deepEqual(markers([pit(), correction]).events, []);
  }
});

test('equal-revision contradictions and unknown revisions cannot revive an older marker', () => {
  assert.equal(markers([pit(), pit()]).events.length, 1);
  assert.deepEqual(markers([pit(), pit({ lap_number: 3 })]).events, []);
  assert.deepEqual(markers([pit(), pit({ revision: null })]).events, []);
  assert.equal(markers([pit(), pit({ lap_number: 3 }), pit({ revision: 2 })]).events.length, 1);
});

test('marker range follows displayed laps, permits missing deltas, and never clamps an event to a boundary', () => {
  const model = trace(); model.rounds = [{ id: 2 }, { id: 3 }]; model.series[1].values[1].delta_ms = null;
  const result = markers([pit(), pit({ event_id: 'outside', lap_number: 1 }), pit({ event_id: 'after', lap_number: 4 })], model);
  assert.deepEqual(result.events.map(event => event.lap), [2]);
  assert.equal('delta_ms' in result.events[0], false);
  assert.deepEqual(markers([pit()], { ...model, rounds: [{ id: 3 }] }).events, []);
  assert.equal(markers([pit({ lap_number: 500 })], { ...trace(), rounds: [{ id: 500 }] }).events[0].lap, 500);
});

test('marker options and unavailable input never block or mutate the base trace', () => {
  const model = freeze(trace()), before = structuredClone(model);
  assert.deepEqual(markers([pit(), flag()], model, ['pit']).events.map(event => event.kind), ['pit']);
  assert.deepEqual(markers([pit()], model, []), { status: 'disabled', reason: null, events: [] });
  for (const status of ['pending', 'unavailable', 'blocked']) {
    assert.deepEqual(raceTraceMarkers(model, { status, reason: 'context_mismatch', events: [pit()] }, ['pit']), { status, reason: 'context_mismatch', events: [] });
  }
  assert.deepEqual(raceTraceMarkers(model, null, ['pit']), { status: 'unavailable', reason: 'marker_data_unavailable', events: [] });
  assert.deepEqual(raceTraceMarkers(model, { status: 'ready', events: null }, ['pit']), { status: 'unavailable', reason: 'invalid_events', events: [] });
  assert.deepEqual(markers([pit()], { ...trace(), status: 'pending' }), { status: 'pending', reason: 'waiting_for_trace', events: [] });
  assert.deepEqual(model, before);
});

test('snapshots are immutable and marker ordering is deterministic across event delivery order', () => {
  const events = freeze([pit(), flag(), flag({ event_id: 'sc', kind: 'sc' })]), before = structuredClone(events);
  assert.deepEqual(markers(events), markers([...events].reverse()));
  assert.deepEqual(events, before);
});
