import assert from 'node:assert/strict';
import test from 'node:test';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { MODULES } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js';
import { RetainedSources, retainedSourceKey, resolveWeatherModule, source, weatherValues } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';

function fixture(module = { type: 'timing' }, scene = 'race') {
  const demo = makeDemo(scene), entry = demo.preview.entries[0];
  entry.entities.current_season = 'sensor.demo_current_season';
  demo.hass.states[entry.entities.current_season] = { state: '2026', attributes: { races: [{ round: '1', race_name: 'Demo Grand Prix', race_start_utc: '2026-09-13T13:00:00Z' }] } };
  const config = normalizeConfig({ modules: [{ ...module, unavailable: 'retain' }] });
  const store = new RetainedSources();
  const d = { ...demo, entry, config, store, module: config.modules[0] };
  d.read = () => { store.update(d.hass, d.entry, config); return store.select(d.hass, d.entry, d.module, MODULES[d.module.type]); };
  d.push = (key, state, attributes = {}) => {
    const id = d.entry.entities[key];
    d.hass = { ...d.hass, states: { ...d.hass.states, [id]: { ...d.hass.states[id], state, attributes } } };
  };
  return d;
}

test('automatic weather retains its chosen track source offline and discards it when the session ends', () => {
  const d = fixture({ type: 'weather', options: { content: 'automatic_conditions' } });
  d.push('session_status', 'live');
  d.push('track_weather', 'live', { air_temperature: 30 });
  d.push('weather', 'cloudy', { current_temperature: 12, current_humidity: 70 });
  const read = () => {
    d.store.update(d.hass, d.entry, d.config);
    const effective = resolveWeatherModule(d.hass, d.entry, d.module);
    return { effective, saved: d.store.select(d.hass, d.entry, effective, MODULES.weather) };
  };
  assert.equal(read().saved.retained, false);
  d.hass = { ...d.hass, connection: { connected: false } };
  const offline = read();
  assert.equal(offline.effective.options.content, 'track_conditions');
  assert.equal(offline.saved.retained, true);
  const values = weatherValues(offline.saved.hass, d.entry, offline.effective).values;
  assert.equal(values.temperature.value, 30);
  assert.equal(values.humidity.value, null);
  d.push('session_status', 'idle');
  const ended = read();
  assert.equal(ended.effective.options.content, 'current_conditions');
  assert.equal(ended.saved.retained, false, 'track snapshot cannot supply a forecast block');
  d.hass = { ...d.hass, connection: { connected: true } };
  assert.equal(weatherValues(read().saved.hass, d.entry, read().effective).values.temperature.value, 12);
});

test('entity-backed modules retain their selected data source when its attributes disappear', () => {
  for (const module of [
    { type: 'timing' }, { type: 'lap_chart' }, { type: 'tyres' },
    { type: 'tyres', options: { content: 'statistics' } }, { type: 'pit_stops' },
    { type: 'incidents' }, { type: 'incidents', options: { content: 'track_limits_summary' } },
    { type: 'weather' }, { type: 'weather', options: { content: 'track_conditions' } },
    { type: 'calendar' }, { type: 'calendar', options: { range: 'season' } },
    { type: 'documents' }, { type: 'results' }, { type: 'results', options: { content: 'starting_grid' } },
    { type: 'standings' }, { type: 'standings', options: { competitors: 'teams' } },
    { type: 'progression' }, { type: 'progression', options: { competitors: 'teams' } },
  ]) {
    const d = fixture(module), key = retainedSourceKey(d.module);
    const original = source(d.hass, d.entry, key);
    assert.equal(original.status, 'available', `${module.type}/${key} fixture`);
    assert.equal(d.read().retained, false);
    d.push(key, 'unavailable');
    const saved = d.read();
    assert.equal(saved.retained, true, `${module.type}/${key}`);
    assert.deepEqual(source(saved.hass, d.entry, key).attributes, original.attributes);
    assert.equal(source(d.hass, d.entry, key).status, 'unavailable', 'actual HA states must remain unchanged');
  }
});

test('saved dependencies stay with their captured primary source and new observations replace the snapshot', () => {
  const d = fixture(); d.read();
  const oldRoster = source(d.hass, d.entry, 'driver_list').attributes;
  d.push('driver_list', '1', { drivers: [{ racing_number: '4', tla: 'NEW' }] });
  d.push('driver_positions', 'unavailable');
  assert.deepEqual(source(d.read().hass, d.entry, 'driver_list').attributes, oldRoster);
  d.push('driver_positions', '0', { drivers: [] });
  assert.equal(d.read().retained, false);
  d.push('driver_positions', 'unknown');
  assert.deepEqual(source(d.read().hass, d.entry, 'driver_positions').attributes.drivers, []);
});

test('presentation and focus edits can reuse a snapshot, but changing its data category cannot', () => {
  const d = fixture({ type: 'results' }); d.read();
  d.push('last_race_results', 'unavailable');
  d.module.fields = ['driver']; d.module.driver = '4'; d.module.options.rows = 1;
  assert.equal(d.read().retained, true);
  d.module.options.content = 'starting_grid';
  d.push('starting_grid', 'unavailable');
  assert.equal(d.read().retained, false);
});

test('disabled sources, removed modules and card removal release snapshots', () => {
  const d = fixture(); d.read();
  d.entry.disabled_entities = ['driver_positions'];
  assert.equal(d.read().retained, false);
  assert.equal(d.store.snapshots.size, 0);
  d.entry.disabled_entities = [];
  d.push('driver_positions', '1', { drivers: [] }); d.read();
  assert.equal(d.store.snapshots.size, 1);
  d.module.enabled = false; d.read();
  assert.equal(d.store.snapshots.size, 0);
  d.store.clear(); assert.equal(d.store.references.size, 0);
});

test('session or qualifying-part changes clear old snapshots and accept a new source observation', () => {
  const d = fixture({ type: 'timing' }, 'qualifying');
  d.module.type = 'timing'; d.read();
  const attrs = source(d.hass, d.entry, 'driver_positions').attributes;
  d.push('driver_positions', '1', { ...attrs, current_qualifying_part: 2 });
  d.read();
  d.push('driver_positions', 'unavailable');
  assert.equal(source(d.read().hass, d.entry, 'driver_positions').attributes.current_qualifying_part, 2);
  d.push('current_session', 'Race', { active: true, start: '2026-09-15T13:00:00Z', meeting_key: 'different' });
  assert.equal(d.read().retained, false);
});

test('seek transitions and backward replay movement never recapture an unchanged pre-seek payload', () => {
  for (const kind of ['seeking', 'backward']) {
    const d = fixture({ type: 'timing' }, 'replay'); d.read();
    const status = source(d.hass, d.entry, 'replay_status');
    const player = source(d.hass, d.entry, 'replay_player');
    if (kind === 'seeking') {
      d.push('replay_status', 'seeking', status.attributes); d.read();
      d.push('replay_status', status.state, status.attributes);
    } else d.push('replay_player', player.state, { ...player.attributes, media_position: 100 });
    d.read();
    d.push('driver_positions', 'unavailable');
    assert.equal(d.read().retained, false, kind);
    d.push('driver_positions', '0', { drivers: [] }); d.read();
    d.push('driver_positions', 'unavailable');
    assert.equal(d.read().retained, true, `${kind}: a new observation is usable`);
  }
});

test('another installation, unknown session, preview and unknown protection cannot reuse prior snapshots', () => {
  for (const change of ['entry', 'session', 'preview', 'protection']) {
    const d = fixture(); d.read(); d.push('driver_positions', 'unavailable');
    if (change === 'entry') d.entry = { ...d.entry, entry_id: 'another' };
    if (change === 'session') d.push('current_session', 'unavailable');
    if (change === 'protection') {
      const id = d.entry.global_entities.no_spoiler_mode;
      d.hass = { ...d.hass, states: { ...d.hass.states, [id]: { state: 'unknown' } } };
    }
    if (change === 'preview') d.store.update(d.hass, d.entry, d.config, true);
    assert.equal(d.read().retained, false, change);
  }
});

test('track weather waits across session, delay and replay discontinuities but not ordinary playback', () => {
  for (const change of ['session', 'delay', 'seek', 'backward', 'forward']) {
    const d = fixture({ type: 'weather', options: { content: 'track_conditions' } }, 'replay');
    d.read();
    assert.equal(d.store.weatherAwaitingObservation(d.hass, d.entry), false);
    if (change === 'session') d.push('current_session', 'Race', { active: true, start: '2026-09-15T13:00:00Z', meeting_key: 'new' });
    if (change === 'delay') d.push('live_delay_number', '90');
    if (change === 'seek') d.push('replay_status', 'seeking', source(d.hass, d.entry, 'replay_status').attributes);
    if (['backward', 'forward'].includes(change)) {
      const player = source(d.hass, d.entry, 'replay_player');
      d.push('replay_player', player.state, { ...player.attributes, media_position: change === 'forward' ? 1810 : 100 });
    }
    d.read();
    assert.equal(d.store.weatherAwaitingObservation(d.hass, d.entry), change !== 'forward', change);
    d.hass = { ...d.hass, states: structuredClone(d.hass.states) };
    d.read();
    assert.equal(d.store.weatherAwaitingObservation(d.hass, d.entry), change !== 'forward', 'recreated HA objects are not new measurements');
    const track = source(d.hass, d.entry, 'track_weather');
    d.push('track_weather', track.state, { ...track.attributes, air_temperature: 33 });
    d.read();
    assert.equal(d.store.weatherAwaitingObservation(d.hass, d.entry), false, 'a new weather payload releases the barrier');
  }
});
