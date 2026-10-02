const version = new URL(import.meta.url).searchParams.get('v');
const { mergeEvents } = await import(`./data.js${version ? `?v=${encodeURIComponent(version)}` : ''}`);

const connections = new WeakMap();
const cancel = cleanup => { try { Promise.resolve(cleanup?.()).catch(() => {}); } catch { /* An obsolete connection can already be closed. */ } };

// One resource per connection/query, independent of how many cards consume it.
// Factories only subscribe/read. They never own backend replay or live windows.
export function watchShared(hass, key, factory, listener) {
  const connection = hass?.connection;
  if (!connection) throw new Error('Home Assistant connection is unavailable');
  let resources = connections.get(connection);
  if (!resources) { resources = new Map(); connections.set(connection, resources); }
  let resource = resources.get(key);
  if (!resource) {
    resource = { listeners: new Set(), state: { status: 'loading', data: null, error: null }, generation: 0, cleanups: [], retry: null, attempt: 0 };
    resources.set(key, resource);
    resource.publish = update => {
      resource.state = { ...resource.state, ...update };
      for (const callback of resource.listeners) callback(resource.state);
    };
    resource.stop = () => {
      resource.generation++;
      clearTimeout(resource.retry); resource.retry = null;
      for (const cleanup of resource.cleanups.splice(0)) cancel(cleanup);
    };
    resource.start = () => {
      resource.stop();
      const generation = resource.generation;
      const active = () => resource.generation === generation && resource.listeners.size > 0;
      resource.publish({ status: resource.state.data ? 'refreshing' : 'loading', error: null });
      const failed = error => {
        if (!active()) return;
        resource.stop();
        const retryGeneration = resource.generation;
        resource.publish({ status: 'error', error: error?.message ?? String(error) });
        const delay = Math.min(30_000, 1000 * 2 ** resource.attempt++);
        resource.retry = setTimeout(() => {
          if (resource.generation === retryGeneration && resource.listeners.size) resource.start();
        }, delay);
      };
      const scope = {
        active,
        emit: data => { if (active()) { resource.attempt = 0; resource.publish({ status: 'ready', data, error: null, received_at: new Date().toISOString() }); } },
        refreshing: () => { if (active()) resource.publish({ status: 'refreshing', error: null }); },
        cleanup: fn => { if (active()) resource.cleanups.push(fn); else cancel(fn); },
        error: failed,
      };
      Promise.resolve().then(() => active() ? factory(scope) : undefined).catch(failed);
    };
    resource.onDisconnected = () => { resource.stop(); resource.publish({ status: 'disconnected' }); };
    resource.onReady = () => resource.start();
    connection.addEventListener?.('disconnected', resource.onDisconnected);
    connection.addEventListener?.('ready', resource.onReady);
  }
  resource.listeners.add(listener);
  listener(resource.state);
  if (resource.listeners.size === 1) resource.start();
  let closed = false;
  return () => {
    if (closed) return; closed = true;
    resource.listeners.delete(listener);
    if (resource.listeners.size) return;
    resource.stop();
    connection.removeEventListener?.('disconnected', resource.onDisconnected);
    connection.removeEventListener?.('ready', resource.onReady);
    resources.delete(key);
  };
}

export function watchEntries(hass, callback) {
  return watchShared(hass, 'entities', async scope => {
    let request = 0;
    const load = async () => {
      const token = ++request;
      const entries = await hass.callWS({ type: 'f1_sensor/entities' });
      if (token !== request || !scope.active()) return;
      if (!Array.isArray(entries)) throw new Error('F1 Sensor entity discovery is unavailable');
      scope.emit(entries);
    };
    if (hass.connection.subscribeEvents) {
      const unsubscribe = await hass.connection.subscribeEvents(() => {
        // Reload once per registry notification; overlapping responses are
        // discarded. No timer/polling is used for stable registry data.
        load().catch(scope.error);
      }, 'entity_registry_updated');
      scope.cleanup(unsubscribe);
    }
    if (scope.active()) await load();
  }, callback);
}

export function watchRaceControl(hass, entityId, callback) {
  return watchShared(hass, `race-control:${entityId}`, async scope => {
    let items = [], reset = 0;
    const connection = hass.connection;
    if (!connection.subscribeEvents) throw new Error('Race Control event subscription is unavailable');
    const unsubscribe = await connection.subscribeEvents(event => {
      if (!scope.active()) return;
      const data = event?.data;
      // Events without an entity cannot safely be assigned to one of several
      // integration entries. A later snapshot will recover valid persisted data.
      if (data?.entity_id !== entityId) return;
      items = mergeEvents(items, [data.log_item ?? data.message]); scope.emit(items);
    }, 'f1_sensor_race_control_event');
    scope.cleanup(unsubscribe);
    if (!scope.active()) return;
    const resetUnsubscribe = await connection.subscribeEvents(event => {
      if (!scope.active() || event?.data?.entity_id !== entityId) return;
      reset++; items = []; scope.emit(items);
    }, 'f1_sensor_race_control_log_reset_event');
    scope.cleanup(resetUnsubscribe);
    if (!scope.active()) return;
    // Subscribe before requesting history so messages during the request are
    // merged. A reset during that request invalidates the old snapshot.
    const before = reset;
    const response = await hass.callWS({ type: 'f1_sensor/race_control_log/get', entity_id: entityId });
    if (!scope.active() || reset !== before) return;
    items = mergeEvents(response?.items, items); scope.emit(items);
  }, callback);
}

export function watchAnalysis(hass, entryId, callback) {
  return watchShared(hass, `analysis:${entryId}`, async scope => {
    if (!entryId || !hass.connection.subscribeMessage) throw new Error('Analysis subscription is unavailable');
    const unsubscribe = await hass.connection.subscribeMessage(payload => {
      if (!scope.active()) return;
      if (payload?.protocol_version !== 1) { scope.error(new Error('Unsupported F1 analysis protocol')); return; }
      scope.emit(payload);
    }, { type: 'f1_sensor/analysis/subscribe', entry_id: entryId, protocol_version: 1, throttle_ms: 500 }, { resubscribe: false });
    // The subscription sends its own initial snapshot. A parallel GET could
    // arrive later and overwrite a newer correction or a replay seek.
    scope.cleanup(unsubscribe);
  }, callback);
}

export function watchTrackMap(hass, entryId, callback) {
  return watchShared(hass, `track-map:${entryId}`, async scope => {
    if (!entryId || !hass.connection.subscribeMessage) throw new Error('Track map subscription is unavailable');
    const { TrackMapState } = await import(`./map-data.js${version ? `?v=${encodeURIComponent(version)}` : ''}`);
    if (!scope.active()) return;
    const state = new TrackMapState(entryId);
    let pending = false, queue = [], overflow = false, attempts = 0;
    const emit = () => scope.emit({ snapshot: state.snapshot, sequence: state.sequence, geometry_revision: state.geometryRevision });
    const buffer = message => { queue.push(message); if (queue.length > 128) { queue = queue.slice(-128); overflow = true; } };
    const resync = async () => {
      if (pending || !scope.active()) return;
      pending = true; scope.refreshing();
      try {
        let again = true;
        while (again && scope.active()) {
          if (++attempts > 3) throw new Error('Track map sequence could not be recovered');
          const response = await hass.callWS({ type: 'f1_sensor/track_map/resync', entry_id: entryId, protocol_version: 2 });
          if (!scope.active()) return;
          const outcome = state.accept(response);
          if (!['updated', 'ignored'].includes(outcome) || !state.snapshot) throw new Error('Track map resynchronization failed');
          const buffered = queue; queue = []; again = overflow; overflow = false;
          for (let index = 0; index < buffered.length; index++) {
            const result = state.accept(buffered[index]);
            if (result === 'closed') throw new Error('Track map entry was unloaded');
            if (result === 'resync') { queue = buffered.slice(index); again = true; break; }
          }
        }
        if (scope.active()) { attempts = 0; emit(); }
      } finally { pending = false; }
    };
    const unsubscribe = await hass.connection.subscribeMessage(message => {
      if (!scope.active() || message?.entry_id !== entryId) return;
      if (message.status === 'closed') { scope.error(new Error('Track map entry was unloaded')); return; }
      if (pending) { buffer(message); return; }
      const outcome = state.accept(message);
      if (outcome === 'updated') { attempts = 0; emit(); }
      else if (outcome === 'resync') { buffer(message); resync().catch(scope.error); }
    }, { type: 'f1_sensor/track_map/subscribe', entry_id: entryId, protocol_version: 2, throttle_ms: 500 }, { resubscribe: false });
    scope.cleanup(unsubscribe);
  }, callback);
}

const groups = new WeakMap();
export function watchGroup(connection, { entry, dashboard, view, name }, listener) {
  if (!entry || !dashboard || !view || !name?.trim()) throw new Error('A control group needs an entry, dashboard, view and name');
  let contexts = groups.get(connection);
  if (!contexts) { contexts = new Map(); groups.set(connection, contexts); }
  const key = JSON.stringify([entry, dashboard, view, name.trim()]);
  let group = contexts.get(key);
  if (!group) { group = { value: {}, listeners: new Set() }; contexts.set(key, group); }
  group.listeners.add(listener); listener({ ...group.value });
  let closed = false;
  return {
    publish: patch => {
      if (closed) return;
      // Only local display focus is allowed here; integration controls cannot
      // accidentally be routed through a group message.
      const allowed = Object.fromEntries(['driver', 'team'].filter(key => typeof patch?.[key] === 'string').map(key => [key, patch[key]]));
      const selection = patch?.selection;
      const validFollow = selection?.mode === 'follow' && ['auto', 'live', 'replay'].includes(selection.source)
        && Object.keys(selection).every(key => ['mode', 'source'].includes(key));
      const validPinned = selection?.mode === 'pinned' && ['live', 'archive', 'replay'].includes(selection.source)
        && Number.isInteger(selection.season) && selection.season >= 1950 && selection.season <= 9999
        && ['meeting_key', 'session_key'].every(key => typeof selection[key] === 'string' && selection[key].trim())
        && Object.keys(selection).every(key => ['mode', 'source', 'season', 'meeting_key', 'session_key'].includes(key));
      if (validFollow || validPinned) allowed.selection = structuredClone(selection);
      group.value = { ...group.value, ...allowed };
      for (const callback of group.listeners) callback({ ...group.value });
    },
    close: () => { if (closed) return; closed = true; group.listeners.delete(listener); if (!group.listeners.size) contexts.delete(key); },
  };
}

export function connectionDiagnostics(connection) {
  const resources = connections.get(connection);
  return { resources: resources?.size ?? 0, consumers: [...(resources?.values() ?? [])].reduce((sum, item) => sum + item.listeners.size, 0), groups: groups.get(connection)?.size ?? 0 };
}

// History reads are keyed by exact installation/session queries. An error needs
// an explicit retry or a new HA connection; it must not poll the community API.
export class HistoryResources {
  constructor(changed) { this.changed = changed; this.resources = new Map(); }
  key(query) { return JSON.stringify(query); }
  read(query) { return this.resources.get(this.key(query))?.state ?? { status: 'loading', data: null }; }
  sync(hass, queries) {
    if (this.connection !== hass?.connection) { this.close(); this.connection = hass?.connection; }
    const wanted = new Map(queries.map(query => [this.key(query), query]));
    for (const [key, resource] of this.resources) if (!wanted.has(key)) { resource.stop?.(); this.resources.delete(key); }
    if (!this.connection) return;
    for (const [key, query] of wanted) {
      if (this.resources.has(key)) continue;
      const resource = { state: { status: 'loading', data: null } }; this.resources.set(key, resource);
      resource.stop = watchShared(hass, `history:${key}`, async scope => {
        try { const payload = await hass.callWS(query); scope.emit({ payload }); }
        catch { scope.emit({ failed: true }); }
      }, state => { resource.state = state; this.changed(); });
    }
  }
  retry(queries) {
    const shared = connections.get(this.connection);
    for (const query of queries) {
      const resource = shared?.get(`history:${this.key(query)}`);
      if (resource && !['loading', 'refreshing', 'disconnected'].includes(resource.state.status) && (resource.state.data?.failed || resource.state.status === 'error')) resource.start();
    }
  }
  close() { for (const resource of this.resources.values()) resource.stop?.(); this.resources.clear(); this.connection = null; }
}


const entityCommands = new WeakMap();
// Concurrent cards share a write lock only until HA resolves the service call.
// Explicit values make a later repeated request idempotent; never use toggle.
export async function callEntityService(hass, command, lockKey) {
  const connection = hass?.connection;
  if (!connection || connection.connected === false || typeof hass.callService !== 'function') return false;
  let active = entityCommands.get(connection);
  if (!active) { active = new Set(); entityCommands.set(connection, active); }
  const target = lockKey ?? command.data.entity_id;
  if (active.has(target)) return false;
  active.add(target);
  try { await hass.callService(command.domain, command.service, command.data); return true; }
  finally { active.delete(target); if (!active.size) entityCommands.delete(connection); }
}
