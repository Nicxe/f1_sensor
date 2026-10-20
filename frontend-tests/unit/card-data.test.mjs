import assert from 'node:assert/strict';
import test from 'node:test';
import { watchCardData, connectionDiagnostics } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/connection.js';
import { source } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';

const tick = () => new Promise(resolve => setImmediate(resolve));

test('explicit direct data works without an entity and never falls back through a block or disconnect', () => {
  const hass = { states: { 'sensor.old': { state: 'old', attributes: { secret: true } } } };
  const entry = { entities: { driver_standings: 'sensor.old' }, data_api: { enabled: ['driver_standings'] }, card_data: {
    driver_standings: { status: 'ready', data: { status: 'ready', payload: { state: 1, attributes: { driver_standings: [{ points: '331' }] } } } },
  } };
  assert.equal(source(hass, entry, 'driver_standings').state, 1);
  entry.entities = {};
  assert.equal(source(hass, entry, 'driver_standings').status, 'available');
  entry.card_data.driver_standings.data = { status: 'blocked', payload: null };
  assert.deepEqual(source(hass, entry, 'driver_standings').attributes, {});
  assert.equal(source(hass, entry, 'driver_standings').state, null);
  entry.card_data.driver_standings.status = 'disconnected';
  assert.equal(source(hass, entry, 'driver_standings').status, 'unavailable');
});

test('an old backend keeps the existing entity transport', () => {
  assert.equal(source({ states: { 'sensor.old': { state: '2' } } }, { entities: { driver_standings: 'sensor.old' } }, 'driver_standings').state, '2');
});

test('multiple cards share one pushed initial snapshot and release the final subscription', async () => {
  const callbacks = []; let removed = 0;
  const connection = { addEventListener() {}, removeEventListener() {}, subscribeMessage: async (callback, request) => {
    assert.deepEqual(request.data_keys, ['driver_standings']); callbacks.push(callback); return () => removed++;
  } };
  const hass = { connection }; let latest;
  const stop = watchCardData(hass, 'entry', 'driver_standings', state => { latest = state; });
  const peer = watchCardData(hass, 'entry', 'driver_standings', () => {});
  await tick(); assert.equal(callbacks.length, 1);
  const message = { entry_id: 'entry', dataset: 'driver_standings', protocol_version: 1, generation: 'first', revision: 2, status: 'ready', payload: { state: 2 } };
  callbacks[0](message); callbacks[0]({ ...message, revision: 1, payload: { state: 1 } });
  assert.equal(latest.data.payload.state, 2);
  callbacks[0]({ ...message, generation: 'second', revision: 1, payload: { state: 3 } });
  callbacks[0]({ ...message, revision: 99, payload: { state: 99 } });
  assert.equal(latest.data.payload.state, 3);
  stop(); assert.equal(removed, 0); peer(); assert.equal(removed, 1);
  assert.equal(connectionDiagnostics(connection).resources, 0);
});

test('required configuration blocks existing entity data', () => {
  const entry = { entities: { driver_standings: 'sensor.old' }, data_api: { configuration_required: true } };
  const result = source({ states: { 'sensor.old': { state: 'old', attributes: { secret: true } } } }, entry, 'driver_standings');
  assert.equal(result.reason, 'configuration_required');
  assert.equal(result.state, null);
  assert.deepEqual(result.attributes, {});
});

test('timing from an earlier qualifying part is hidden until matching context arrives', () => {
  const entry = { entities: { driver_positions: 'sensor.old' }, data_api: { enabled: ['driver_positions', 'session_context'] }, card_data: {
    session_context: { status: 'ready', data: { generation: 'session', context: { qualifying_part: 2 } } },
    driver_positions: { status: 'ready', data: { generation: 'session', context: { qualifying_part: 1 }, source: 'live', status: 'ready', payload: { state: 22, attributes: { drivers: [{ position: 1 }] } } } },
  } };
  const hass = { states: { 'sensor.old': { state: 'old', attributes: { drivers: ['previous'] } } } };
  assert.equal(source(hass, entry, 'driver_positions').status, 'unavailable');
  assert.deepEqual(source(hass, entry, 'driver_positions').attributes, {});
  entry.card_data.driver_positions.data.context.qualifying_part = 2;
  assert.equal(source(hass, entry, 'driver_positions').state, 22);
});
