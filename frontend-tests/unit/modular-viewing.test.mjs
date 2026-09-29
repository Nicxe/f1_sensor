import assert from 'node:assert/strict';
import test from 'node:test';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { viewingModel, viewingCommand } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';
import { callEntityService } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/connection.js';
const fixture = () => { const d = makeDemo(); d.hass.connection = { connected: true }; return { ...d, entry: d.preview.entries[0] }; };
const read = d => viewingModel(d.hass, d.entry);
const command = (d, action, value, context = action === 'delay' ? read(d).delay.context : read(d).spoilers.context) => viewingCommand(d.hass, d.entry, action, value, context);

test('viewing controls are opt-in, serializable and independent of local spoiler masking', () => {
  assert.equal(normalizeConfig({}).context.viewing_controls, false);
  const config = normalizeConfig({ context: { viewing_controls: true, spoilers: 'hide' } });
  assert.deepEqual(normalizeConfig(JSON.parse(JSON.stringify(config))), config);
  assert.throws(() => normalizeConfig({ context: { viewing_controls: 'true' } }), /viewing_controls/);
});

test('manual delay respects discovered IDs, bounds, step and zero without rounding silently', () => {
  const d = fixture(), old = d.entry.entities.live_delay_number;
  d.entry.entities.live_delay_number = 'number.renamed_delay'; d.hass.states[d.entry.entities.live_delay_number] = d.hass.states[old]; delete d.hass.states[old];
  assert.deepEqual(command(d, 'delay', '0'), { domain: 'number', service: 'set_value', data: { entity_id: 'number.renamed_delay', value: 0 } });
  for (const value of [null, undefined, false, '', ' ', NaN, Infinity, -1, 301, 2.5, 45]) assert.equal(command(d, 'delay', value), null);
  d.hass.states[d.entry.entities.live_delay_number].attributes.step = 5;
  assert.equal(command(d, 'delay', 43), null); assert.ok(command(d, 'delay', 50));
});

test('old values, renamed controls, replay, calibration and unavailable sources cannot change manual delay', () => {
  const d = fixture(), context = read(d).delay.context;
  d.hass.states[d.entry.entities.live_delay_number].state = '30';
  assert.equal(command(d, 'delay', 60, context), null);
  for (const [key, states] of [['replay_status', ['loading', 'ready', 'playing', 'paused', 'seeking', 'unknown', 'unavailable']], ['delay_calibration_switch', ['on', 'unknown', 'unavailable']]]) {
    const original = d.hass.states[d.entry.entities[key]].state;
    for (const state of states) { d.hass.states[d.entry.entities[key]].state = state; assert.equal(command(d, 'delay', 60), null); }
    d.hass.states[d.entry.entities[key]].state = original;
  }
  d.entry.disabled_entities = ['live_delay_number']; assert.equal(command(d, 'delay', 60), null);
  d.entry.disabled_entities = []; d.hass.connection.connected = false; assert.equal(command(d, 'delay', 60), null);
});

test('global protection only uses explicit on/off and current discovered switch state', () => {
  const d = fixture(), context = read(d).spoilers.context;
  assert.deepEqual(command(d, 'protect'), { domain: 'switch', service: 'turn_on', data: { entity_id: 'switch.f1_demo_spoilers' } });
  assert.equal(command(d, 'reveal'), null);
  d.hass.states[d.entry.global_entities.no_spoiler_mode].state = 'on';
  assert.equal(command(d, 'reveal', null, context), null);
  assert.equal(command(d, 'reveal').service, 'turn_off');
  assert.equal(command(d, 'protect'), null);
  const confirmed = read(d).spoilers.context;
  d.hass.states[d.entry.global_entities.no_spoiler_mode].last_changed = '2026-09-14T08:00:00Z';
  assert.equal(command(d, 'reveal', null, confirmed), null);
  d.hass.states[d.entry.global_entities.no_spoiler_mode].state = 'unknown';
  assert.equal(command(d, 'reveal'), null); assert.equal(command(d, 'protect'), null);
  delete d.entry.global_entities; assert.equal(command(d, 'protect'), null);
});

test('concurrent cards share pending entity writes; failures and completion release the lock', async () => {
  const d = fixture(); let resolve, reject, calls = 0;
  d.hass.callService = () => { calls++; return new Promise((yes, no) => { resolve = yes; reject = no; }); };
  const cmd = command(d, 'protect'), first = callEntityService(d.hass, cmd);
  assert.equal(await callEntityService({ ...d.hass }, cmd), false); assert.equal(calls, 1);
  resolve(); assert.equal(await first, true);
  const second = callEntityService(d.hass, cmd); reject(new Error('permission denied')); await assert.rejects(second, /permission denied/);
  const third = callEntityService(d.hass, cmd); resolve(); assert.equal(await third, true); assert.equal(calls, 3);
  d.hass.connection.connected = false; assert.equal(await callEntityService(d.hass, cmd), false);
});
