import assert from 'node:assert/strict';
import test from 'node:test';

import { FIELDS, MINISECTOR_FIELDS, MODULES, TIMING_PROFILES } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { watchMinisectors, connectionDiagnostics } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/connection.js';
import { MinisectorState, minisectorContext, segmentStrip, usesMinisectors } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/minisector-data.js';

const turn = () => new Promise(resolve => setImmediate(resolve));
const snapshot = (overrides = {}) => ({ protocol_version: 1, type: 'snapshot', entry_id: 'entry', source: 'live', session_key: '77', generation: 'g1', sequence: 0, generated_at: '2026-10-08T10:00:00Z', stream_timestamp: null,
  drivers: { 16: { sectors: { 0: { segments: { 0: 2048, 2: 2051 } } } } }, ...overrides });

test('catalog exposes six status-only fields and leaves existing timing profiles unchanged', () => {
  assert.deepEqual(MINISECTOR_FIELDS.map(field => field.id), [
    'minisector_1', 'sector_1_with_minisectors', 'minisector_2',
    'sector_2_with_minisectors', 'minisector_3', 'sector_3_with_minisectors',
  ]);
  for (const field of MINISECTOR_FIELDS) {
    assert.equal(field.source, 'minisectors'); assert.equal(field.estimated, false);
    assert.ok(field.identity.includes('segment')); assert.deepEqual(field.modes, ['live', 'replay']);
  }
  assert.deepEqual(TIMING_PROFILES.race, ['position', 'driver', 'gap', 'interval', 'last_lap', 'sector_1', 'sector_2', 'sector_3', 'tyre']);
  assert.deepEqual(MODULES.minisectors.defaultFields, ['driver', 'minisector_1', 'minisector_2', 'minisector_3']);
  const config = normalizeConfig({ modules: [{ type: 'minisectors' }, { type: 'timing', fields: ['driver', 'sector_1_with_minisectors'] }] });
  assert.equal(config.modules[0].focus_mode, 'inherit'); assert.equal(config.modules[1].options.profile, 'custom');
  assert.equal(FIELDS.minisector_1.unit, null); assert.equal(FIELDS.sector_1_with_minisectors.unit, 's');
});

test('reducer preserves sparse indexes and requires exact generation and sequence', () => {
  const state = new MinisectorState('entry', 'live', '77');
  assert.equal(state.accept(snapshot()), 'updated');
  assert.deepEqual(segmentStrip(state.value().drivers['16'], 0), [
    { index: 0, raw: 2048 }, { index: 1, raw: null }, { index: 2, raw: 2051 },
  ]);
  assert.equal(state.accept(snapshot({ type: 'delta', sequence: 1, drivers: { 16: { sectors: { 0: { segments: { 2: 2049 } } } } } })), 'updated');
  assert.equal(state.value().drivers['16'].sectors['0'].segments['2'], 2049);
  assert.equal(state.accept(snapshot({ type: 'delta', sequence: 3, drivers: {} })), 'resync');
  assert.equal(state.accept(snapshot({ type: 'reset', sequence: 2, reason: 'new_lap', scope: { drivers: ['16'] }, drivers: {} })), 'updated');
  assert.deepEqual(state.value().drivers, {});
  assert.equal(state.accept(snapshot({ type: 'unavailable', sequence: 3, reason: 'source_inactive', drivers: undefined })), 'unavailable');
  assert.deepEqual(state.value().drivers, {});
});

test('session context follows live and replay identities without archive fallback', () => {
  const entry = { entry_id: 'entry', entities: { current_session: 'sensor.current', replay_status: 'sensor.replay', replay_player: 'media_player.replay' } };
  const hass = { states: {
    'sensor.current': { state: 'Race', attributes: { session_key: '77' } },
    'sensor.replay': { state: 'idle', attributes: {} },
    'media_player.replay': { state: 'idle', attributes: {} },
  } };
  assert.deepEqual(minisectorContext(hass, entry, { mode: 'follow', source: 'auto' }), { entryId: 'entry', source: 'live', sessionKey: '77', key: '["entry","live","77"]' });
  hass.states['sensor.replay'] = { state: 'paused', attributes: { selected_session_key: '88' } };
  assert.equal(minisectorContext(hass, entry, { mode: 'follow', source: 'auto' }).source, 'replay');
  assert.equal(minisectorContext(hass, entry, { mode: 'pinned', source: 'archive', session_key: '99' }), null);
  assert.equal(usesMinisectors({ type: 'timing', fields: ['driver'] }), false);
  assert.equal(usesMinisectors({ type: 'timing', fields: ['minisector_1'] }), true);
  const detailOnly = { type: 'timing', fields: ['driver'], detail_fields: ['minisector_1'], options: { show_driver_details: true } };
  assert.equal(usesMinisectors(detailOnly), false);
  assert.equal(usesMinisectors(detailOnly, true), true);
  assert.equal(usesMinisectors({ ...detailOnly, options: { show_driver_details: false } }, true), false);
});

test('matching consumers share one websocket subscription and release it after the last consumer', async () => {
  const lifecycle = new Map(), callbacks = []; let subscriptions = 0, removals = 0;
  const connection = {
    addEventListener: (name, callback) => { if (!lifecycle.has(name)) lifecycle.set(name, new Set()); lifecycle.get(name).add(callback); },
    removeEventListener: (name, callback) => lifecycle.get(name)?.delete(callback),
    subscribeMessage: async (callback, message, options) => {
      subscriptions++; callbacks.push(callback);
      assert.deepEqual(message, { type: 'f1_sensor/minisectors/subscribe', protocol_version: 1, entry_id: 'entry', source: 'live', session_key: '77' });
      assert.equal(options.resubscribe, false);
      return () => { removals++; };
    },
  };
  const hass = { connection }, context = { entryId: 'entry', source: 'live', sessionKey: '77' }; let latest;
  const first = watchMinisectors(hass, context, state => { latest = state; });
  const second = watchMinisectors(hass, context, () => {});
  await turn(); assert.equal(subscriptions, 1);
  callbacks[0](snapshot()); assert.equal(latest.data.status, 'ready');
  first(); assert.equal(removals, 0); second(); assert.equal(removals, 1);
  assert.deepEqual(connectionDiagnostics(connection), { resources: 0, consumers: 0, groups: 0 });
});
