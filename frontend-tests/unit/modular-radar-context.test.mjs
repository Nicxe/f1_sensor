import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { radarModel } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';

const race = (id, name, lat, lon) => ({ Circuit: { circuitId: id, circuitName: name, Location: { lat, long: lon } } });
const calendar = [
  race('baku', 'Baku City Circuit', '40.3725', '49.8533'),
  race('shanghai', 'Shanghai International Circuit', '31.3389', '121.22'),
  race('albert_park', 'Albert Park Grand Prix Circuit', '-37.8497', '144.968'),
  race('losail', 'Lusail International Circuit', '25.49', '51.4542'),
  race('yas_marina', 'Yas Marina Circuit', '24.4672', '54.6031'),
];
const configModule = (options = {}) => normalizeConfig({ modules: [{ type: 'radar', options }] }).modules[0];

function fixture(races = calendar) {
  const entry = { entry_id: 'calendar-owner', entities: {
    current_season: 'sensor.renamed_calendar', next_race: 'sensor.renamed_next',
    replay_status: 'sensor.renamed_replay', live_delay_number: 'number.renamed_delay',
  } };
  const hass = { states: {
    'sensor.renamed_calendar': { state: String(races.length), attributes: { races } },
    'sensor.renamed_next': { state: 'Qatar Grand Prix', attributes: { circuit_id: 'losail' } },
    'sensor.renamed_replay': { state: 'idle', attributes: {} },
    'number.renamed_delay': { state: '0', attributes: {} },
  } };
  return { entry, hass };
}

test('radar uses the selected installation calendar and preserves all five requested circuit coordinates', () => {
  const { hass, entry } = fixture();
  hass.states['sensor.unrelated_calendar'] = { state: '1', attributes: { races: [race('wrong', 'Wrong installation', 0, 0)] } };
  const module = configModule(), model = radarModel(hass, entry, module);
  assert.deepEqual(module.fields, []);
  assert.equal(module.options.zoom, 13);
  assert.equal(configModule({ zoom: 14 }).options.zoom, 14);
  assert.deepEqual(model.circuits, calendar.map(({ Circuit }) => ({
    id: Circuit.circuitId, name: Circuit.circuitName,
    lat: Number(Circuit.Location.lat), lon: Number(Circuit.Location.long),
  })));
  assert.equal(model.selectedId, 'losail');
  assert.equal(model.currentOnly, false);
  assert.equal(radarModel(hass, entry, configModule({ circuit: 'shanghai', zoom: 9 })).selectedId, 'losail');
  assert.equal(radarModel(hass, entry, configModule({ circuit: 'removed-circuit' })).selectedId, 'losail');
});

test('radar rejects missing and invalid coordinates, deduplicates circuit identities and accepts geographical zero', () => {
  const { hass, entry } = fixture([
    ...calendar, calendar[0], null, {}, race('', 'No identity', 1, 2),
    ...[null, undefined, '', 'unknown', 'NaN', Infinity, 91, -91].map((value, i) => race(`bad-lat-${i}`, 'Invalid latitude', value, 2)),
    ...[null, undefined, '', 'unknown', 'NaN', Infinity, 181, -181].map((value, i) => race(`bad-lon-${i}`, 'Invalid longitude', 1, value)),
    race('zero', 'Equator at Greenwich', '0', '0'),
  ]);
  const result = radarModel(hass, entry, configModule());
  assert.deepEqual(result.circuits.map(circuit => circuit.id), [...calendar.map(item => item.Circuit.circuitId), 'zero']);
  assert.deepEqual(result.circuits.at(-1), { id: 'zero', name: 'Equator at Greenwich', lat: 0, lon: 0 });
  hass.states[entry.entities.current_season].state = 'unavailable';
  assert.deepEqual(radarModel(hass, entry, configModule()).circuits, []);
  assert.equal(radarModel(hass, entry, configModule()).selectedId, null);
});

test('replay, delayed viewing and pinned historical selection require a distinct current-weather opt-in context', () => {
  const { hass, entry } = fixture(), module = configModule();
  const live = radarModel(hass, entry, module);
  for (const state of ['selected', 'loading', 'ready', 'seeking', 'playing', 'paused', 'error']) {
    hass.states[entry.entities.replay_status].state = state;
    const result = radarModel(hass, entry, module);
    assert.equal(result.currentOnly, true, state);
    assert.notEqual(result.contextKey, live.contextKey);
  }
  hass.states[entry.entities.replay_status].state = 'idle';
  hass.states[entry.entities.live_delay_number].state = '45';
  const delayed = radarModel(hass, entry, module);
  assert.equal(delayed.currentOnly, true);
  hass.states[entry.entities.live_delay_number].state = '60';
  assert.notEqual(radarModel(hass, entry, module).contextKey, delayed.contextKey);
  hass.states[entry.entities.live_delay_number].state = '0';
  for (const selection of [
    { mode: 'pinned', source: 'live', season: 2026, meeting_key: 'demo-meeting', session_key: 'demo-session' },
    { mode: 'follow', source: 'replay' },
    { mode: 'pinned', source: 'archive', season: 2026, meeting_key: 'demo-meeting', session_key: 'demo-session' },
  ]) {
    const selected = normalizeConfig({ modules: [{ type: 'radar', selection }] }).modules[0];
    assert.equal(radarModel(hass, entry, selected).currentOnly, true, JSON.stringify(selection));
  }
  entry.card_data = { session_context: { data: { source: 'replay' } } };
  assert.equal(radarModel(hass, entry, module).currentOnly, true);
  delete entry.card_data;
  assert.equal(radarModel(hass, entry, module).currentOnly, false);
});


test('next-race identity remains authoritative without a published start and can supply its own map coordinates', () => {
  const { hass, entry } = fixture([]);
  const next = hass.states[entry.entities.next_race];
  next.state = 'unknown';
  next.attributes = { circuit_id: 'losail', circuit_name: 'Lusail', circuit_lat: '25.49', circuit_long: '51.4542', season: '2026', round: '23' };
  const result = radarModel(hass, entry, configModule());
  assert.equal(result.selectedId, 'losail');
  assert.deepEqual(result.circuits, [{ id: 'losail', name: 'Lusail', lat: 25.49, lon: 51.4542 }]);
  assert.notEqual(radarModel(hass, { ...entry, entry_id: 'another-installation' }, configModule()).selectionKey, result.selectionKey);
  next.attributes.round = '24';
  assert.notEqual(radarModel(hass, entry, configModule()).selectionKey, result.selectionKey);
});

test('missing next-race data falls back to the dated upcoming event rather than calendar order', () => {
  const now = Date.parse('2026-11-10T12:00:00Z');
  const { hass, entry } = fixture([
    { ...calendar[0], date: '2026-09-27', time: '11:00:00Z' },
    { ...calendar[4], date: '2026-12-06', time: '13:00:00Z' },
    { ...calendar[3], date: '2026-11-29', time: '16:00:00Z' },
    { ...calendar[1], date: '2026-02-30', time: '12:00:00Z' },
  ]);
  hass.states[entry.entities.next_race] = { state: 'unavailable', attributes: { circuit_id: 'baku' } };
  assert.equal(radarModel(hass, entry, configModule(), now).selectedId, 'losail');
  assert.equal(radarModel(hass, entry, configModule(), Date.parse('2027-01-01T12:00:00Z')).selectedId, null);
  hass.states[entry.entities.current_season].attributes.races[2].time = undefined;
  assert.equal(radarModel(hass, entry, configModule(), now).selectedId, 'losail');
});

test('absent next-race identity, undated calendars and unmapped next circuits never silently select the first circuit', () => {
  const { hass, entry } = fixture();
  hass.states[entry.entities.next_race] = { state: 'unknown', attributes: {} };
  assert.equal(radarModel(hass, entry, configModule()).selectedId, null);
  hass.states[entry.entities.next_race] = { state: 'available', attributes: { circuit_id: 'missing-circuit' } };
  assert.equal(radarModel(hass, entry, configModule()).selectedId, null);
});
