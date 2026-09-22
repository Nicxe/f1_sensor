import assert from 'node:assert/strict';
import test from 'node:test';
import { watchShared, watchRaceControl, watchEntries, watchGroup, connectionDiagnostics } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/connection.js';

const turn = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
function harness(callWS = async () => ({ items: [] })) {
  const handlers = new Map(), connectionHandlers = new Map();
  const counts = { subscriptions: 0, unsubscribe: 0, requests: 0, services: 0 };
  const connection = {
    addEventListener: (type, callback) => { if (!connectionHandlers.has(type)) connectionHandlers.set(type, new Set()); connectionHandlers.get(type).add(callback); },
    removeEventListener: (type, callback) => connectionHandlers.get(type)?.delete(callback),
    subscribeEvents: async (callback, type) => {
      counts.subscriptions++;
      if (!handlers.has(type)) handlers.set(type, new Set()); handlers.get(type).add(callback);
      return () => { counts.unsubscribe++; handlers.get(type).delete(callback); };
    },
  };
  return { connection, counts,
    hass: { connection, callWS: async message => { counts.requests++; return callWS(message); }, callService: () => { counts.services++; } },
    emit: (type, data) => { for (const callback of handlers.get(type) ?? []) callback({ data }); },
    lifecycle: type => { for (const callback of connectionHandlers.get(type) ?? []) callback(); },
    active: () => [...handlers.values()].reduce((n, set) => n + set.size, 0),
  };
}

test('ten cards share one snapshot and two event subscriptions, with final cleanup and no service calls', async () => {
  const h = harness(), snapshots = [];
  const stops = Array.from({ length: 10 }, () => watchRaceControl(h.hass, 'sensor.rc', value => snapshots.push(value)));
  await turn();
  assert.equal(h.counts.requests, 1);
  assert.equal(h.counts.subscriptions, 2);
  stops.slice(0, 9).forEach(stop => stop());
  assert.equal(h.active(), 2);
  stops[9](); stops[9]();
  assert.equal(h.active(), 0);
  assert.deepEqual(connectionDiagnostics(h.connection), { resources: 0, consumers: 0, groups: 0 });
  assert.equal(h.counts.services, 0);
});

test('messages arriving before history resolves are merged, reset invalidates in-flight history', async () => {
  const history = deferred(), h = harness(() => history.promise);
  let latest;
  const stop = watchRaceControl(h.hass, 'sensor.rc', state => { latest = state; });
  await turn();
  const event = { utc: '2026-09-13T13:30:00Z', message: 'YELLOW FLAG', category: 'Flag' };
  h.emit('f1_sensor_race_control_event', { entity_id: 'sensor.other', log_item: event });
  assert.equal(latest.data, null);
  h.emit('f1_sensor_race_control_event', { entity_id: 'sensor.rc', log_item: event });
  assert.equal(latest.data.length, 1);
  h.emit('f1_sensor_race_control_log_reset_event', { entity_id: 'sensor.rc' });
  history.resolve({ items: [event] }); await turn();
  assert.deepEqual(latest.data, []);
  stop();
});

test('a late subscribe resolution after removal is immediately unsubscribed', async () => {
  const subscription = deferred(), h = harness(); let removed = 0;
  h.connection.subscribeEvents = () => subscription.promise;
  const stop = watchRaceControl(h.hass, 'sensor.rc', () => {});
  await turn(); stop(); subscription.resolve(() => { removed++; }); await turn();
  assert.equal(removed, 1);
  assert.equal(h.counts.requests, 0);
});

test('reconnect obtains new history and ignores responses from a prior connection generation', async () => {
  const first = deferred(); let call = 0, latest;
  const h = harness(() => ++call === 1 ? first.promise : { items: [{ message: 'New session', utc: '2026-09-13T14:00:00Z' }] });
  const stop = watchRaceControl(h.hass, 'sensor.rc', state => { latest = state; });
  await turn(); h.lifecycle('disconnected');
  assert.equal(latest.status, 'disconnected');
  assert.equal(h.active(), 0);
  h.lifecycle('ready'); await turn();
  first.resolve({ items: [{ message: 'Old session' }] }); await turn();
  assert.deepEqual(latest.data.map(item => item.message), ['New session']);
  assert.equal(h.active(), 2);
  assert.equal(h.counts.requests, 2);
  stop();
});

test('partial subscription failure cleans up and does not leave a retry after final removal', async () => {
  const h = harness(); const original = h.connection.subscribeEvents; let calls = 0, latest;
  h.connection.subscribeEvents = (callback, type) => ++calls === 2 ? Promise.reject(new Error('Denied')) : original(callback, type);
  const stop = watchRaceControl(h.hass, 'sensor.rc', state => { latest = state; });
  await turn();
  assert.equal(latest.status, 'error');
  assert.equal(h.active(), 0);
  stop();
  assert.equal(connectionDiagnostics(h.connection).resources, 0);
});

test('discovery is shared and refreshes after registry changes', async () => {
  let entries = [{ entry_id: 'one', entities: { driver_list: 'sensor.old' } }], latest;
  const h = harness(() => entries);
  const a = watchEntries(h.hass, state => { latest = state; }); const b = watchEntries(h.hass, () => {});
  await turn(); assert.equal(h.counts.requests, 1);
  entries = [{ entry_id: 'one', entities: { driver_list: 'sensor.renamed' } }];
  h.emit('entity_registry_updated', {}); await turn();
  assert.equal(latest.data[0].entities.driver_list, 'sensor.renamed');
  a(); b();
});

test('control groups isolate entry, dashboard, view and connection and never share integration commands', () => {
  const connection = {}, address = { entry: 'one', dashboard: 'racing', view: 'live', name: 'focus' };
  let peer, other;
  const first = watchGroup(connection, address, () => {});
  const second = watchGroup(connection, address, value => { peer = value; });
  const isolated = watchGroup(connection, { ...address, entry: 'two' }, value => { other = value; });
  first.publish({ driver: '16', selection: { mode: 'follow', source: 'replay' }, replay: 'stop', no_spoiler: false });
  assert.deepEqual(peer, { driver: '16', selection: { mode: 'follow', source: 'replay' } }); assert.deepEqual(other, {});
  first.publish({ selection: { mode: 'pinned', source: 'live', season: 2026, meeting_key: '', session_key: 'race' } });
  assert.deepEqual(peer.selection, { mode: 'follow', source: 'replay' });
  for (const change of [{ dashboard: 'elsewhere' }, { view: 'archive' }, { name: 'other' }]) {
    const group = watchGroup(connection, { ...address, ...change }, value => assert.deepEqual(value, {})); group.close();
  }
  const separate = watchGroup({}, address, value => assert.deepEqual(value, {})); separate.close();
  first.close(); second.close(); isolated.close();
  assert.equal(connectionDiagnostics(connection).groups, 0);
});

test('unsubscribed shared resource cannot publish stale results to a new consumer', async () => {
  const pending = deferred(), h = harness(); let latest;
  const stop = watchShared(h.hass, 'query', async scope => { await pending.promise; scope.emit('old'); }, () => {});
  await turn(); stop();
  const next = watchShared(h.hass, 'query', scope => scope.emit('new'), state => { latest = state; });
  await turn(); pending.resolve(); await turn();
  assert.equal(latest.data, 'new'); next();
});

test('analysis consumers share one pushed snapshot stream and discard an obsolete generation after reconnect', async () => {
  const { watchAnalysis } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/connection.js');
  const h = harness(), handlers = []; let removed = 0, latest;
  h.connection.subscribeMessage = async (callback, message, options) => {
    assert.equal(message.type, 'f1_sensor/analysis/subscribe'); assert.equal(message.entry_id, 'one'); assert.equal(options.resubscribe, false);
    handlers.push(callback); return () => removed++;
  };
  const stops = Array.from({ length: 10 }, () => watchAnalysis(h.hass, 'one', state => { latest = state; }));
  await turn(); assert.equal(handlers.length, 1);
  handlers[0]({ protocol_version: 1, session_id: 'old' }); assert.equal(latest.data.session_id, 'old'); assert.ok(latest.received_at);
  h.lifecycle('disconnected'); h.lifecycle('ready'); await turn();
  handlers[1]({ protocol_version: 1, session_id: 'new' }); handlers[0]({ protocol_version: 1, session_id: 'old-late' });
  assert.equal(latest.data.session_id, 'new'); assert.equal(h.counts.requests, 0);
  stops.forEach(stop => stop()); assert.equal(removed, 2); assert.equal(h.counts.services, 0);
  assert.equal(connectionDiagnostics(h.connection).resources, 0);
});

test('late analysis subscription cleanup cannot stop backend replay or publish after removal', async () => {
  const { watchAnalysis } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/connection.js');
  const h = harness(), pending = deferred(); let callback, removed = 0, latest;
  h.connection.subscribeMessage = fn => { callback = fn; return pending.promise; };
  const stop = watchAnalysis(h.hass, 'one', state => { latest = state; }); await turn(); stop();
  pending.resolve(() => removed++); await turn(); callback({ protocol_version: 1, session_id: 'late' });
  assert.equal(removed, 1); assert.equal(latest.data, null); assert.equal(h.counts.services, 0);
});

test('map consumers share a stream and resync merges buffered deltas without publishing an older snapshot', async () => {
  const { watchTrackMap } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/connection.js');
  const pending = deferred(), subscribed = deferred(), h = harness(() => pending.promise); let receive, calls = 0, latest;
  h.connection.subscribeMessage = async callback => { receive = callback; calls++; subscribed.resolve(); return () => {}; };
  const stops = [watchTrackMap(h.hass, 'one', state => { latest = state; }), watchTrackMap(h.hass, 'one', () => {})];
  // The map decoder is loaded only when the first map subscription is requested.
  await subscribed.promise;
  assert.equal(calls, 1);
  const full = sequence => ({ protocol_version: 2, type: 'snapshot', entry_id: 'one', sequence, snapshot: { entry_id: 'one', drivers: [] } });
  const delta = (sequence, base_sequence) => ({ protocol_version: 2, type: 'delta', entry_id: 'one', sequence, base_sequence, patch: {}, changes: { 16: { racing_number: '16', x: sequence, y: 1 } }, removed: [] });
  receive(full(1)); receive(delta(4, 3)); await turn(); receive(delta(5, 4));
  assert.equal(h.counts.requests, 1); assert.equal(latest.data.sequence, 1);
  assert.equal(latest.status, 'refreshing');
  pending.resolve(full(3)); await turn();
  assert.equal(latest.data.sequence, 5); assert.equal(latest.data.snapshot.drivers[0].x, 5);
  stops.forEach(stop => stop()); assert.equal(h.counts.services, 0); assert.equal(connectionDiagnostics(h.connection).resources, 0);
});
