import assert from 'node:assert/strict';
import test from 'node:test';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';
import { normalizeConfig, applyPreset } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { MODULES, fieldDefinition, moduleFields } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js';
import { sessionRainRisk, weatherValues, RetainedSources } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';

function fixture() {
  const demo = makeDemo('practice'), entry = demo.preview.entries[0];
  return { ...demo, entry, risk: demo.hass.states[entry.entities.session_rain_risk],
    current: demo.hass.states[entry.entities.current_session] };
}

test('session assessment preserves reported zero and stays separate from the race forecast and rain detection', () => {
  const d = fixture();
  d.risk.state = '0'; d.risk.attributes.percentage = 0;
  assert.equal(sessionRainRisk(d.hass, d.entry).value, 0);
  assert.equal(weatherValues(d.hass, d.entry).values.rain_probability.value, 15);
  assert.equal(weatherValues(d.hass, d.entry, { type: 'weather', options: { content: 'track_conditions' } }).values.rainfall.value, false);
  for (const value of ['unknown', 'unavailable', null, '', '-1', '101', 'NaN']) {
    d.risk.state = value;
    assert.equal(sessionRainRisk(d.hass, d.entry), null, String(value));
  }
});

test('session assessment fails closed for another session, unknown protection, terminal sessions and disconnection', () => {
  const d = fixture();
  d.current.attributes.session_key = 'other';
  assert.equal(sessionRainRisk(d.hass, d.entry), null);
  d.current.attributes.session_key = 'demo-session';
  assert.equal(sessionRainRisk(d.hass, d.entry).value, 30);
  d.current.attributes.meeting_key = 'other-meeting';
  assert.equal(sessionRainRisk(d.hass, d.entry), null);
  d.current.attributes.meeting_key = 'demo-meeting';
  assert.equal(sessionRainRisk(d.hass, d.entry, 'hide'), null);
  d.hass.states[d.entry.global_entities.no_spoiler_mode].state = 'on';
  assert.equal(sessionRainRisk(d.hass, d.entry), null);
  d.hass.states[d.entry.global_entities.no_spoiler_mode].state = 'unknown';
  assert.equal(sessionRainRisk(d.hass, d.entry), null);
  d.hass.states[d.entry.global_entities.no_spoiler_mode].state = 'off';
  d.hass.states[d.entry.entities.session_status].state = 'finished';
  assert.equal(sessionRainRisk(d.hass, d.entry), null);
  d.hass.states[d.entry.entities.session_status].state = 'live';
  d.hass.connection = { connected: false };
  assert.equal(sessionRainRisk(d.hass, d.entry), null);
});

test('direct card data shows the assessment without a sensor or Race Control module and rejects the wrong generation', () => {
  const d = fixture();
  const data = { source: 'live', status: 'ready', generation: 'session-a', payload: { state: 0, attributes: { ...d.risk.attributes, percentage: 0 } } };
  delete d.entry.entities.session_rain_risk;
  d.entry.data_api = { enabled: ['session_rain_risk'] };
  d.entry.card_data = { session_rain_risk: { status: 'ready', data }, session_context: { data: { generation: 'session-a' } } };
  assert.equal(sessionRainRisk(d.hass, d.entry).value, 0);
  d.entry.card_data.session_context.data.generation = 'session-b';
  assert.equal(sessionRainRisk(d.hass, d.entry), null);
});

test('overview and all Weather sources expose a distinct session field and useful presets opt in', () => {
  for (const content of ['weather_overview', 'automatic_conditions', 'track_conditions', 'current_conditions', 'race_forecast']) {
    const module = normalizeConfig({ modules: [{ type: 'weather', options: { content } }] }).modules[0];
    assert.ok(moduleFields(module).includes('session_rain_risk'));
    const field = fieldDefinition(module, 'session_rain_risk');
    assert.equal(field.source, 'session_rain_risk');
    assert.equal(field.spoiler, true);
    assert.equal(field.generation, 'session');
    assert.equal(field.path, 'percentage');
    if (['weather_overview', 'automatic_conditions', 'track_conditions'].includes(content)) assert.ok(module.fields.includes('session_rain_risk'));
    else assert.ok(!module.fields.includes('session_rain_risk'));
  }
  assert.ok(normalizeConfig({ modules: [{ type: 'overview' }] }).modules[0].fields.includes('session_rain_risk'));
  for (const preset of ['weekend', 'weather', 'session', 'driver']) {
    assert.ok(applyPreset(normalizeConfig({}), preset).modules.some(module => module.fields.includes('session_rain_risk')), preset);
  }
});

test('seek, live delay and session transitions require a newly delivered assessment before redisplay', () => {
  const d = fixture(), store = new RetainedSources();
  const config = normalizeConfig({ modules: [{ type: 'overview' }] });
  const update = () => store.update(d.hass, d.entry, config);
  update();
  assert.equal(store.rainRiskAwaitingObservation(d.hass, d.entry), false);
  d.hass.states[d.entry.entities.live_delay_number].state = '50'; update();
  assert.equal(store.rainRiskAwaitingObservation(d.hass, d.entry), true);
  d.risk.last_updated = '2026-09-13T13:31:00Z'; update();
  assert.equal(store.rainRiskAwaitingObservation(d.hass, d.entry), false);
  d.current.attributes.session_key = 'other'; update();
  assert.equal(store.rainRiskAwaitingObservation(d.hass, d.entry), true);
  d.risk.attributes.session_key = 'other'; update();
  assert.equal(store.rainRiskAwaitingObservation(d.hass, d.entry), false);
  const player = d.hass.states[d.entry.entities.replay_player];
  player.attributes.media_position = 100; update();
  player.attributes.media_position = 10; update();
  assert.equal(store.rainRiskAwaitingObservation(d.hass, d.entry), true);
});

test('a retained weather snapshot keeps its captured session assessment instead of combining new information', () => {
  const d = fixture(), store = new RetainedSources();
  const config = normalizeConfig({ modules: [{ type: 'weather', fields: ['temperature', 'session_rain_risk'], unavailable: 'retain' }] });
  const module = config.modules[0];
  const read = () => { store.update(d.hass, d.entry, config); return store.select(d.hass, d.entry, module, MODULES.weather); };
  assert.equal(read().retained, false);
  d.hass.states[d.entry.entities.weather] = { state: 'unavailable', attributes: {} };
  d.hass.states[d.entry.entities.session_rain_risk] = { ...d.risk, state: '60', attributes: { ...d.risk.attributes, percentage: 60 } };
  const saved = read();
  assert.equal(saved.retained, true);
  assert.equal(sessionRainRisk(saved.hass, d.entry).value, 30);
  assert.equal(sessionRainRisk(d.hass, d.entry).value, 60);
});
