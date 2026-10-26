import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { pitStopsModel } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/session-data.js';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';

const module = (options = {}, extra = {}) => normalizeConfig({ modules: [{ type: 'pit_stops', options, ...extra }] }).modules[0];
const fixture = () => {
  const demo = makeDemo(), entry = demo.preview.entries[0];
  const pit = demo.hass.states[entry.entities.pitstops];
  pit.state = '25'; pit.attributes.cars = { 16: { count: 25, stops: [] } };
  return { ...demo, entry, pit };
};

test('reported pit counts are useful without pretending that counts are individual stop records', () => {
  for (const content of ['all_stops', 'latest_stop']) {
    const d = fixture(), model = pitStopsModel(d.hass, d.entry, module({ content }));
    assert.equal(model.rows.length, 0);
    assert.equal(model.countRows.length, 1);
    assert.equal(model.countRows[0].driver, 'LEC');
    assert.equal(model.countRows[0].pit_count, 25);
    for (const field of ['stop_lap', 'stop_time', 'lane_time', 'pit_delta', 'event_time']) assert.equal(Object.hasOwn(model.countRows[0], field), false);
    assert.equal(model.reportedTotal, 25);
    assert.equal(model.context.source, 'TimingData / DriverRaceInfo');
  }
});

test('pit count summaries preserve zero and filter by the same driver or team as details', () => {
  const d = fixture(); d.pit.attributes.cars[4] = { count: 0, stops: [] }; d.pit.attributes.cars[44] = { count: null, stops: [] };
  let model = pitStopsModel(d.hass, d.entry, module({}, { driver: 'NOR' }));
  assert.equal(model.countRows.length, 1); assert.equal(model.countRows[0].pit_count, 0);
  model = pitStopsModel(d.hass, d.entry, module({}, { team: 'Ferrari' }));
  assert.deepEqual(model.countRows.map(row => row.number), ['16']);
  model = pitStopsModel(d.hass, d.entry, module({}, { driver: '44' }));
  assert.equal(model.countRows.length, 0); assert.equal(model.filtered, true);
});

test('pit summaries and detail rows recognize the actual backend pit_in status', () => {
  const d = fixture(), positions = d.hass.states[d.entry.entities.driver_positions].attributes.drivers;
  const driver = positions.find(row => row.racing_number === '16');
  driver.status = 'pit_in';
  assert.equal(pitStopsModel(d.hass, d.entry, module()).countRows[0].status, 'in_pit');
  d.pit.attributes.cars[16].stops = [{ lap: 18, pit_lane_time: 23.7 }];
  assert.equal(pitStopsModel(d.hass, d.entry, module()).rows[0].status, 'in_pit');
  for (const status of ['in_pit', 'pit_out', 'out', 'retired', 'stopped', 'on_track']) {
    driver.status = status;
    assert.equal(pitStopsModel(d.hass, d.entry, module()).rows[0].status, status);
  }
});

test('mixed pit data retains real detail rows and separately summarizes drivers without records', () => {
  const d = fixture();
  d.pit.attributes.cars[4] = { count: 2, stops: [{ lap: 13, timestamp: '2026-09-13T13:20:00Z', pit_stop_time: 2.3, pit_lane_time: 23.793 }] };
  let model = pitStopsModel(d.hass, d.entry, module({ content: 'all_stops' }));
  assert.equal(model.rows.length, 1); assert.equal(model.rows[0].number, '4');
  assert.equal(model.rows[0].stop_time, 2.3); assert.equal(model.countRows.length, 1);
  assert.equal(model.countRows[0].number, '16'); assert.equal(model.partialDetails, true);
  d.pit.attributes.cars[16].stops = [{ lap: 18 }];
  model = pitStopsModel(d.hass, d.entry, module({ content: 'all_stops' }));
  assert.equal(model.rows.length, 2); assert.equal(model.countRows.length, 0);
  assert.equal(model.rows.find(row => row.number === '16').stop_time, null);
});

test('pit lane-only details retain their provenance and cannot masquerade as stationary timing', () => {
  const d = fixture(); d.pit.attributes.cars[16] = { count: 1, stops: [{ lap: 18, timestamp: null, pit_stop_time: null, pit_lane_time: 23.7, source: 'PitLaneTimeCollection' }] };
  const model = pitStopsModel(d.hass, d.entry, module());
  assert.equal(model.rows[0].stop_time, null); assert.equal(model.rows[0].lane_time, 23.7);
  assert.equal(model.rows[0].source, 'PitLaneTimeCollection'); assert.equal(model.laneOnly, true);
  assert.equal(model.context.source, 'PitLaneTimeCollection');
});

test('pit counts and records disappear with source unavailability or a new empty session', () => {
  const d = fixture();
  d.pit.state = 'unavailable';
  let model = pitStopsModel(d.hass, d.entry, module());
  assert.equal(model.countRows.length, 0); assert.equal(model.rows.length, 0); assert.equal(model.reportedTotal, null);
  d.pit.state = 'unknown'; model = pitStopsModel(d.hass, d.entry, module());
  assert.equal(model.countRows.length, 0);
  d.pit.state = '0'; d.pit.attributes.cars = {};
  model = pitStopsModel(d.hass, d.entry, module());
  assert.equal(model.countRows.length, 0); assert.equal(model.rows.length, 0); assert.equal(model.reportedTotal, 0);
});

test('direct pit summaries obey current live or replay generation and never fall back to retained entities', () => {
  for (const source of ['live', 'replay']) {
    const d = fixture();
    d.entry.data_api = { enabled: ['pitstops'] };
    const direct = { status: 'ready', source, generation: 'old-session', context: { delay_seconds: 50 },
      payload: { state: 25, attributes: d.pit.attributes } };
    d.entry.card_data = {
      pitstops: { status: 'ready', data: direct },
      session_context: { status: 'ready', data: { generation: 'current-session' } },
    };
    assert.equal(pitStopsModel(d.hass, d.entry, module()).countRows.length, 0);
    direct.generation = 'current-session';
    assert.equal(pitStopsModel(d.hass, d.entry, module()).countRows[0].pit_count, 25);
    direct.status = 'unavailable'; direct.reason = 'no_spoiler';
    assert.equal(pitStopsModel(d.hass, d.entry, module()).countRows.length, 0);
  }
});
