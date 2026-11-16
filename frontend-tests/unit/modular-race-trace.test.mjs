import assert from 'node:assert/strict';
import test from 'node:test';
import { raceTraceModel, clipRaceTrace } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/race-trace-data.js';

const driver = (id, times, extra = {}) => {
  const laps = Array.isArray(times) ? Object.fromEntries(times.map((time, i) => [i + 1, time])) : times;
  return { racing_number: id, tla: `D${id}`, full_name: `Driver ${id}`, completed_laps: Math.max(0, ...Object.keys(laps).map(Number)), laps,
    lap_metadata: Object.fromEntries(Object.keys(laps).map(lap => [lap, { association: 'confirmed', reason: null }])), ...extra };
};
const fixture = () => [driver('1', [90, 90, 91, 90]), driver('4', [91, 89.5, 92, 110]), driver('16', [88, 90.25, 90.75, 89.5]), driver('81', [92, 89, 90, 91])];
const model = (drivers = fixture(), options = {}) => raceTraceModel(drivers, { reference_driver: '1', selected: ['4'], ...options });
const ms = (result, id = '4') => result.series.find(item => item.id === id)?.values.map(point => point.delta_ms);
const freeze = value => { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); } return value; };

test('four drivers use the same anchor and hand-calculated integer deltas including pit time', () => {
  const result = model(fixture(), { selected: ['4', '16', '81'] });
  assert.equal(result.status, 'ready'); assert.equal(result.anchorLap, 1);
  assert.equal(result.metric, 'cumulative_lap_delta'); assert.equal(result.axisKind, 'lap');
  assert.deepEqual(ms(result, '1'), [0, 0, 0, 0]);
  assert.deepEqual(ms(result), [0, -500, 500, 20500]);
  assert.deepEqual(ms(result, '16'), [0, 250, 0, -500]);
  assert.deepEqual(ms(result, '81'), [0, -1000, -2000, -1000]);
  assert.deepEqual(result.series[1].values.map(point => point.value), [0, -.5, .5, 20.5]);
  assert.equal(result.series[0].isReference, true);
  assert.deepEqual(ms(model(fixture(), { selected: ['4', '16'] }), '16'), [0, 250, 0, -500]);
});

test('milliseconds remain exact for decimal and formatted times and long sums', () => {
  const result = model([driver('1', [90, 90.001, 90.002, 90.003]), driver('4', [91, '1:30.002', '1:30.001', '1:30.004'])]);
  assert.deepEqual(ms(result), [0, 1, 0, 1]);
  const long = model([driver('1', Array(500).fill('1:30.000')), driver('4', Array(500).fill('1:30.001'))]);
  assert.equal(ms(long).at(-1), 499);
});

test('a missing lap breaks only its series suffix and a later snapshot repairs it', () => {
  const drivers = fixture(); delete drivers[1].laps['3'];
  assert.deepEqual(ms(model(drivers)), [0, -500, null, null]);
  assert.deepEqual(ms(model(drivers), '1'), [0, 0, 0, 0]);
  drivers[1].laps['3'] = 92;
  assert.deepEqual(ms(model(drivers)), [0, -500, 500, 20500]);
  drivers[1].laps['2'] = 89.25;
  assert.deepEqual(ms(model(drivers)), [0, -750, 250, 20250]);
});

test('a missing reference lap breaks every suffix without inventing DNF or lapping', () => {
  const drivers = fixture(); delete drivers[0].laps['3']; delete drivers[0].laps['4']; drivers[0].completed_laps = 2;
  const result = model(drivers);
  assert.deepEqual(ms(result, '1'), [0, 0, null, null]);
  assert.deepEqual(ms(result), [0, -500, null, null]);
  assert.equal(JSON.stringify(result).includes('DNF'), false);
});

test('reference changes reverse the comparison and never borrow group focus', () => {
  const result = model(fixture(), { reference_driver: '4', selected: ['1'], driver: '16' });
  assert.deepEqual(ms(result, '1'), [0, 500, -500, -20500]);
  assert.deepEqual(result.series.map(item => item.id), ['4', '1']);
});

test('late starts use the first common observed lap and locked anchors do not move', () => {
  const drivers = [driver('1', { 24: 90, 25: 90 }), driver('4', { 24: 91, 25: 89.5 })];
  assert.equal(model(drivers).anchorLap, 24);
  for (const item of drivers) { item.laps['23'] = 88; item.lap_metadata['23'] = { association: 'confirmed' }; }
  const result = model(drivers, { lockedAnchor: 24 });
  assert.equal(result.anchorLap, 24); assert.deepEqual(ms(result), [null, 0, -500]);
});

test('a locked anchor disappearing or losing certainty stays locked until restored', () => {
  const drivers = fixture(); delete drivers[1].laps['1'];
  let result = model(drivers, { lockedAnchor: 1 });
  assert.equal(result.status, 'pending'); assert.equal(result.reason, 'anchor_unavailable');
  assert.equal(result.anchorLap, 1); assert.deepEqual(result.series, []);
  drivers[1].laps['1'] = 91; drivers[1].lap_metadata['1'].association = 'ambiguous';
  assert.equal(model(drivers, { lockedAnchor: 1 }).status, 'pending');
  drivers[1].lap_metadata['1'].association = 'confirmed';
  assert.deepEqual(ms(model(drivers, { lockedAnchor: 1 })), [0, -500, 500, 20500]);
});

test('explicit reset after a gap is separate from display zoom and overrides the old lock', () => {
  const drivers = fixture(); delete drivers[1].laps['2'];
  const reset = model(drivers, { anchor_lap: 3, lockedAnchor: 1 });
  assert.equal(reset.anchorLap, 3); assert.deepEqual(ms(reset), [null, null, 0, 20000]);
  const full = model(); const clipped = clipRaceTrace(full, 3, 4);
  assert.equal(clipped.anchorLap, 1); assert.deepEqual(ms(clipped), [500, 20500]);
  assert.deepEqual(ms(full), [0, -500, 500, 20500]);
});

test('normalised identical lap aliases count once and conflicting aliases break the suffix', () => {
  const drivers = fixture(); drivers[1].laps['02'] = 89.5; drivers[1].lap_metadata['02'] = { association: 'confirmed' };
  assert.deepEqual(ms(model(drivers)), [0, -500, 500, 20500]);
  drivers[1].laps['02'] = 90;
  const result = model(drivers);
  assert.deepEqual(ms(result), [0, null, null, null]);
  assert.equal(result.series[1].values[1].reason, 'ambiguous_lap');
  drivers[1].laps['02'] = 89.5001;
  assert.deepEqual(ms(model(drivers)), [0, null, null, null], 'rounding must not hide conflicting aliases');
  drivers[1].lap_metadata['02'] = {};
  assert.deepEqual(ms(model(drivers)), [0, null, null, null], 'an unconfirmed conflicting alias cannot be discarded for an observed lap');
});

for (const time of [0, -1, NaN, Infinity, -Infinity, '', 'bad', true, {}, 1e308]) {
  test(`invalid duration ${String(time)} never becomes a zero-filled delta`, () => {
    const drivers = fixture(); drivers[1].laps['2'] = time;
    assert.deepEqual(ms(model(drivers)), [0, null, null, null]);
  });
}

for (const association of ['inferred', 'ambiguous', undefined]) {
  test(`lap association ${association} is not made safe by completion count`, () => {
    const drivers = fixture(); drivers[1].lap_metadata['2'] = { association };
    assert.deepEqual(ms(model(drivers)), [0, null, null, null]);
  });
}

test('missing completion or metadata cannot establish an anchor', () => {
  const drivers = fixture(); drivers[1].completed_laps = null;
  assert.equal(model(drivers).reason, 'completion_unknown');
  drivers[1].completed_laps = 4; delete drivers[1].lap_metadata;
  assert.equal(model(drivers).reason, 'no_common_anchor');
});

test('cleared evidence keeps retained legacy history pending without exposing its lap range', () => {
  const drivers = [driver('1', { 1: 90, 2: 90, 500: 90 }), driver('4', { 1: 91, 2: 89.5, 500: 91 })];
  for (const item of drivers) item.lap_metadata = {};
  const result = model(drivers);
  assert.equal(result.status, 'pending'); assert.equal(result.reason, 'no_common_anchor');
  assert.deepEqual(result.rounds, []); assert.deepEqual(result.series, []);
  assert.deepEqual(clipRaceTrace(result, 1, 500).rounds, []);
});

test('new evidence defines the visible range without exposing retained past or future raw laps', () => {
  const drivers = [driver('1', { 1: 90, 2: 90, 3: 91, 500: 90 }), driver('4', { 1: 91, 2: 89.5, 3: 92, 500: 91 })];
  for (const item of drivers) item.lap_metadata = { 1: null, 2: { association: 'confirmed' }, 3: {}, 500: { association: 'invalid' } };
  const result = model(drivers);
  assert.equal(result.anchorLap, 2);
  assert.deepEqual(result.rounds, [{ id: 2 }]);
  assert.deepEqual(ms(result), [0]);
  assert.deepEqual(ms(result, '1'), [0]);
});

for (const association of ['inferred', 'ambiguous']) {
  test(`observed ${association} laps extend the range as gaps without exposing later raw history`, () => {
    const drivers = [driver('1', [90, 90, 91, 90]), driver('4', [91, 89.5, 92, 110])];
    for (const item of drivers) item.lap_metadata = { 1: { association: 'confirmed' }, 3: { association } };
    const result = model(drivers);
    assert.deepEqual(result.rounds, [{ id: 1 }, { id: 2 }, { id: 3 }]);
    assert.deepEqual(ms(result), [0, null, null]);
    assert.equal(result.series[1].values[1].reason, 'missing_lap');
    for (const item of drivers) item.lap_metadata['3'] = { association: 'confirmed' };
    assert.deepEqual(ms(model(drivers)), [0, null, null], 'later confirmation cannot bridge an unobserved lap');
    for (const item of drivers) item.lap_metadata['2'] = { association: 'confirmed' };
    assert.deepEqual(ms(model(drivers)), [0, -500, 500]);
  });
}

test('uncompleted future laps and lap 501 are excluded, while lap 500 is valid', () => {
  const drivers = [driver('1', { 499: 90, 500: 90, 501: 90 }), driver('4', { 499: 91, 500: 91, 501: 91 })];
  const result = model(drivers);
  assert.deepEqual(result.rounds, [{ id: 499 }, { id: 500 }]); assert.deepEqual(ms(result), [0, 1000]);
  drivers[1].completed_laps = 499;
  assert.deepEqual(ms(model(drivers)), [0, null]);
});

test('pit, safety car, red flag and official deletion do not remove observed elapsed time', () => {
  const drivers = fixture();
  Object.assign(drivers[1], { deleted: true, track_status: '5', quality: { pace_suitability: 'excluded' } });
  Object.assign(drivers[1].lap_metadata['4'], { deleted: true, pit: true, red_flag: true });
  assert.deepEqual(ms(model(drivers)), [0, -500, 500, 20500]);
});

test('selections are explicit, canonical and capped without silent replacement', () => {
  assert.deepEqual(model(fixture(), { selected: [] }).series.map(item => item.id), ['1']);
  assert.deepEqual(model(fixture(), { reference_driver: '01', selected: ['1', '04', '4'] }).series.map(item => item.id), ['1', '4']);
  assert.equal(model(fixture(), { selected: ['4', '16', '81', '44'] }).reason, 'too_many_drivers');
  assert.equal(model(fixture(), { reference_driver: '' }).reason, 'reference_required');
  assert.equal(model(fixture(), { reference_driver: '99' }).reason, 'reference_missing');
  assert.equal(model(fixture(), { selected: ['44'] }).reason, 'driver_missing');
  assert.equal(model(fixture(), { selected: ['NOR'] }).status, 'invalid_selection');
  assert.equal(model(fixture(), { anchor_lap: 501 }).reason, 'invalid_anchor');
  assert.equal(model(fixture(), { anchor_lap: 'bad' }).anchorLap, null);
  assert.equal(model(fixture(), { anchor_lap: 5 }).reason, 'anchor_unavailable');
  assert.equal(model([...fixture(), driver('01', [90])]).reason, 'ambiguous_driver');
});

test('accumulated sums must remain safe integers even if each individual duration is safe', () => {
  const result = model([driver('1', [1, 1, 1]), driver('4', [1, 6000000000000, 6000000000000])]);
  assert.equal(result.series[1].values[2].delta_ms, null);
  assert.equal(result.series[1].values[2].reason, 'unsafe_sum');
});

test('subtracting an equal large pair does not round an already safe cumulative sum', () => {
  const result = model([driver('1', [.001, .001, 8000000000000]), driver('4', [.001, 8000000000000, 8000000000000])]);
  assert.deepEqual(ms(result), [0, 7999999999999999, 7999999999999999]);
});

test('clipping preserves missing values, supports isolated samples and rejects reversed ranges', () => {
  const full = model();
  assert.deepEqual(ms(clipRaceTrace(full, 4, 4)), [20500]);
  assert.deepEqual(ms(clipRaceTrace(full, 3, 6)), [500, 20500, null, null]);
  assert.equal(clipRaceTrace(full, 4, 2).invalidRange, true);
  assert.deepEqual(clipRaceTrace(full, 0, 0).rounds, full.rounds);
  assert.deepEqual(clipRaceTrace(model(fixture(), { selected: ['99'] }), 0, 0).series, []);
  assert.equal(clipRaceTrace(model(fixture(), { selected: ['99'] }), 3, 0).invalidRange, false);
});

test('identical snapshots are idempotent and neither calculation nor clipping mutates inputs', () => {
  const input = freeze(fixture()), options = freeze({ reference_driver: '1', selected: ['4'], anchor_lap: 0, lockedAnchor: null });
  const before = structuredClone(input), first = freeze(raceTraceModel(input, options));
  assert.deepEqual(raceTraceModel(input, options), first);
  clipRaceTrace(first, 2, 4);
  assert.deepEqual(input, before);
});
