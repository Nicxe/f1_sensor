import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { sessionPhase, selectionState } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';
import { tyresModel, pitStopsModel, incidentsModel } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/session-data.js';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';
const module = (type, options = {}, extra = {}) => normalizeConfig({ modules: [{ type, options, ...extra }] }).modules[0];
const fixture = () => { const demo = makeDemo(); return { ...demo, entry: demo.preview.entries[0] }; };
const attrs = (demo, key) => demo.hass.states[demo.entry.entities[key]].attributes;

test('session phases include interruptions and pinned identities never fall back to another session', () => {
  for (const [scene, phase] of [['before', 'before'], ['race', 'active'], ['ended', 'finished'], ['missing', 'unknown']]) {
    const demo = makeDemo(scene), entry = demo.preview.entries[0];
    assert.equal(sessionPhase(demo.hass, entry), phase);
  }
  const d = fixture(), pinned = { mode: 'pinned', source: 'live', season: 2026, meeting_key: 'demo-meeting', session_key: 'demo-session' };
  assert.equal(selectionState(d.hass, d.entry, pinned).available, true);
  assert.equal(selectionState(d.hass, d.entry, { ...pinned, session_key: 'other' }).available, false);
  d.hass.states[d.entry.entities.session_status].state = 'suspended';
  attrs(d, 'current_session').active = false;
  assert.equal(sessionPhase(d.hass, d.entry), 'active');
  const replay = makeDemo('replay'), replayEntry = replay.preview.entries[0];
  assert.equal(selectionState(replay.hass, replayEntry, { ...pinned, source: 'replay' }).available, true);
  assert.equal(selectionState(replay.hass, replayEntry, { mode: 'follow', source: 'live' }).available, false);
});

test('current tyres preserve zero age, used/new distinction and unknown compound without inventing position', () => {
  const d = fixture(); attrs(d, 'current_tyres').drivers = [{ racing_number: '16', new: false, stint_laps: 0, compound: 'EXPERIMENTAL', position: 0 }];
  const model = tyresModel(d.hass, d.entry, module('tyres'));
  assert.equal(model.rows[0].tyre_age, 0); assert.equal(model.rows[0].tyre_new, false);
  assert.equal(model.rows[0].tyre, 'EXPERIMENTAL'); assert.equal(model.rows[0].position, null);
  assert.equal(tyresModel(d.hass, d.entry, module('tyres', { compounds: ['UNKNOWN'] })).rows.length, 1);
  assert.equal(tyresModel(d.hass, d.entry, module('tyres', { compounds: ['SOFT'] })).rows.length, 0);
  attrs(d, 'current_tyres').drivers[0].stint_laps = null;
  assert.equal(tyresModel(d.hass, d.entry, module('tyres')).rows[0].tyre_age, null);
});

test('compound statistics do not pretend to be driver-filtered and distinguish sets from stints', () => {
  const d = fixture(), m = module('tyres', { content: 'statistics' }, { driver: '16' });
  const result = tyresModel(d.hass, d.entry, m, { team: 'Ferrari' });
  assert.equal(result.rows.length, 3); assert.ok(m.fields.includes('compound_best')); assert.ok(!m.fields.includes('driver'));
  assert.equal(result.rows[0].compound_gap, 0); assert.equal(result.rows[0].new_sets, 2); assert.equal(result.rows[0].total_stints, 4);
  attrs(d, 'tyre_statistics').compounds.SOFT.best_times = [null, { time_secs: 0 }, { time_secs: 81 }, { time_secs: 80.5 }];
  assert.equal(tyresModel(d.hass, d.entry, m).rows[0].compound_best, 80.5);
  attrs(d, 'tyre_statistics').status = 'waiting_for_compound_data'; attrs(d, 'tyre_statistics').compounds = {};
  assert.equal(tyresModel(d.hass, d.entry, m).waiting, true); assert.equal(tyresModel(d.hass, d.entry, m).rows.length, 0);
});

test('pit history keeps different time meanings, incomplete stops and source corrections with stable identities', () => {
  const d = fixture(), m = module('pit_stops', { content: 'all_stops' }, { driver: '16' });
  let result = pitStopsModel(d.hass, d.entry, m);
  assert.equal(result.rows.length, 2); assert.equal(result.rows[0].pit_delta, null); assert.equal(result.rows[0].stop_time, 2.17); assert.equal(result.rows[0].lane_time, 22.9);
  const id = result.rows[0].id;
  attrs(d, 'pitstops').cars[16].stops.push({ ...attrs(d, 'pitstops').cars[16].stops[1], pit_stop_time: 2.22, pit_delta: -1.25 });
  result = pitStopsModel(d.hass, d.entry, m);
  assert.equal(result.rows.length, 2); assert.equal(result.rows[0].id, id); assert.equal(result.rows[0].stop_time, 2.22); assert.equal(result.rows[0].pit_delta, -1.25);
  assert.equal(pitStopsModel(d.hass, d.entry, module('pit_stops', {}, { driver: 'LEC' })).rows.length, 1);
  assert.equal(pitStopsModel(d.hass, d.entry, module('pit_stops', {}, { team: 'Ferrari' })).rows[0].number, '16');
});

test('pit history uses the current session driver status without reading unavailable positions', () => {
  const d = fixture();
  const positions = attrs(d, 'driver_positions').drivers;
  positions.find(driver => driver.racing_number === '16').status = 'in_pit';
  let rows = pitStopsModel(d.hass, d.entry, module('pit_stops')).rows;
  assert.equal(rows.find(row => row.number === '16').status, 'in_pit');
  assert.equal(rows.find(row => row.number === '4').status, 'on_track');
  d.hass.states[d.entry.entities.driver_positions].state = 'unavailable';
  rows = pitStopsModel(d.hass, d.entry, module('pit_stops')).rows;
  assert.equal(rows.find(row => row.number === '16').status, null);
});

test('unavailable roster cannot relabel retained pit records with stale identities', () => {
  const d = fixture(); d.hass.states[d.entry.entities.driver_list].state = 'unavailable';
  const [row] = pitStopsModel(d.hass, d.entry, module('pit_stops')).rows;
  assert.equal(row.name, '16'); assert.equal(row.team, null);
});

test('incidents use decision time, support every involved driver and replace state rather than accumulating decisions', () => {
  const d = fixture(), m = module('incidents');
  let result = incidentsModel(d.hass, d.entry, m);
  assert.equal(result.rows[0].incident_status, 'no_further_action'); assert.equal(result.rows[0].event_time, '2026-09-13T13:28:00.000Z'); assert.equal(result.rows[0].decision_time, true);
  assert.equal(incidentsModel(d.hass, d.entry, module('incidents', {}, { driver: '4' })).rows.length, 1);
  assert.equal(incidentsModel(d.hass, d.entry, module('incidents', {}, { driver: 'NOR' })).rows.length, 1);
  assert.equal(incidentsModel(d.hass, d.entry, module('incidents', { categories: ['penalty'] })).rows.length, 1);
  attrs(d, 'investigations').under_investigation = [];
  result = incidentsModel(d.hass, d.entry, m); assert.equal(result.rows.length, 2); assert.ok(!result.rows.some(row => row.incident_status === 'under_investigation'));
});

test('track limits use source violations and preserve numeric turn/lap and filtering', () => {
  const d = fixture(), m = module('incidents', { content: 'track_limits', order: 'oldest' });
  const result = incidentsModel(d.hass, d.entry, m);
  assert.equal(result.rows[0].incident_status, 'time_deleted'); assert.equal(result.rows[0].incident_location, '7'); assert.equal(result.rows[0].incident_lap, 11);
  assert.equal(incidentsModel(d.hass, d.entry, module('incidents', { content: 'track_limits', search: 'NOR' })).rows.length, 2);
  assert.equal(incidentsModel(d.hass, d.entry, module('incidents', { content: 'track_limits' }, { driver: 'LEC' })).rows.length, 0);
});

test('malformed or missing session collections produce empty models without fabricated results', () => {
  const d = fixture();
  attrs(d, 'pitstops').cars = null; attrs(d, 'current_tyres').drivers = [null, false]; attrs(d, 'tyre_statistics').compounds = null;
  attrs(d, 'investigations').penalties = null; attrs(d, 'investigations').under_investigation = 'bad'; attrs(d, 'investigations').no_further_action = null;
  attrs(d, 'track_limits').by_driver = { BAD: null };
  for (const [fn, type, options] of [[pitStopsModel, 'pit_stops', {}], [tyresModel, 'tyres', {}], [tyresModel, 'tyres', { content: 'statistics' }], [incidentsModel, 'incidents', {}], [incidentsModel, 'incidents', { content: 'track_limits' }]]) assert.equal(fn(d.hass, d.entry, module(type, options)).rows.length, 0);
});

test('track-limit summaries use source counters, preserve unknown flags and replace corrections', () => {
  const d = fixture(), m = module('incidents', { content: 'track_limits_summary' });
  const byDriver = attrs(d, 'track_limits').by_driver;
  byDriver.LEC = { racing_number: '16', deletions: 0, warning: false, penalty: null, violations: [] };
  byDriver.VER = { racing_number: '1', deletions: null, violations: [] };
  byDriver.BAD = null;
  let result = incidentsModel(d.hass, d.entry, m);
  assert.deepEqual(result.rows.map(row => row.driver), ['NOR', 'LEC', 'VER']);
  assert.equal(result.rows[0].track_limit_deletions, 1); assert.equal(result.rows[0].track_limit_warning, true);
  assert.equal(result.rows[0].event_time, '2026-09-13T13:27:00.000Z');
  assert.equal(result.rows[1].track_limit_deletions, 0); assert.equal(result.rows[1].track_limit_warning, false); assert.equal(result.rows[1].penalty_known, true);
  assert.equal(result.rows[2].track_limit_deletions, null); assert.equal(result.rows[2].track_limit_warning, null); assert.equal(result.rows[2].penalty_known, false);
  byDriver.NOR.deletions = 0; byDriver.NOR.warning = false; byDriver.NOR.penalty = '5 SECOND TIME PENALTY';
  result = incidentsModel(d.hass, d.entry, m);
  const nor = result.rows.find(row => row.driver === 'NOR');
  assert.equal(nor.track_limit_deletions, 0); assert.equal(nor.track_limit_warning, false); assert.equal(nor.track_limit_penalty, '5 SECOND TIME PENALTY');
  assert.equal(result.rows.some(row => row.driver === 'RUS'), false);
});

test('track-limit summary filters apply to driver records without counting the event list as offences', () => {
  const d = fixture(); attrs(d, 'track_limits').by_driver.NOR.violations = [];
  const read = (options, extra) => incidentsModel(d.hass, d.entry, module('incidents', { content: 'track_limits_summary', ...options }, extra));
  assert.equal(read({ categories: ['warning'] }).rows.length, 1);
  assert.equal(read({ categories: ['penalty'] }).rows.length, 0);
  assert.equal(read({}, { driver: '4' }).rows[0].driver, 'NOR');
  assert.equal(read({}, { driver: 'NOR' }).rows[0].track_limit_deletions, 1);
  assert.equal(read({ search: 'Norris' }).rows.length, 1);
  assert.equal(read({}, { team: 'Ferrari' }).rows.length, 0);
});
