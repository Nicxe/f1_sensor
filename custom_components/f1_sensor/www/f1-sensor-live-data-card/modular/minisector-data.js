const MAX_DRIVERS = 32;
const MAX_SECTORS = 3;
const MAX_SEGMENTS = 32;

const integer = value => Number.isInteger(value) ? value : null;
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);

function drivers(value) {
  if (!object(value)) return null;
  const result = {};
  for (const [driver, driverValue] of Object.entries(value).slice(0, MAX_DRIVERS)) {
    if (!object(driverValue) || !object(driverValue.sectors)) continue;
    const sectors = {};
    for (const [sector, sectorValue] of Object.entries(driverValue.sectors)) {
      const sectorIndex = Number(sector);
      if (!Number.isInteger(sectorIndex) || sectorIndex < 0 || sectorIndex >= MAX_SECTORS || !object(sectorValue) || !object(sectorValue.segments)) continue;
      const segments = {};
      for (const [segment, rawStatus] of Object.entries(sectorValue.segments)) {
        const segmentIndex = Number(segment), status = integer(rawStatus);
        if (!Number.isInteger(segmentIndex) || segmentIndex < 0 || segmentIndex >= MAX_SEGMENTS || status === null) continue;
        segments[String(segmentIndex)] = status;
      }
      sectors[String(sectorIndex)] = { segments };
    }
    result[String(driver)] = { sectors };
  }
  return result;
}

function mergeDrivers(current, patch) {
  const next = structuredClone(current);
  for (const [driver, driverValue] of Object.entries(patch)) {
    const target = next[driver] ??= { sectors: {} };
    for (const [sector, sectorValue] of Object.entries(driverValue.sectors)) {
      const targetSector = target.sectors[sector] ??= { segments: {} };
      Object.assign(targetSector.segments, sectorValue.segments);
    }
  }
  return next;
}

export class MinisectorState {
  constructor(entryId, source, sessionKey) {
    this.entryId = entryId; this.source = source; this.sessionKey = sessionKey;
    this.generation = null; this.sequence = null; this.drivers = {}; this.status = 'loading'; this.reason = null;
  }
  accept(message) {
    if (!object(message) || message.protocol_version !== 1 || message.entry_id !== this.entryId
      || message.source !== this.source || message.session_key !== this.sessionKey
      || typeof message.generation !== 'string' || !Number.isInteger(message.sequence)) return 'resync';
    if (message.type === 'unavailable') {
      this.generation = message.generation; this.sequence = message.sequence; this.drivers = {};
      this.status = 'unavailable'; this.reason = typeof message.reason === 'string' ? message.reason : 'unknown';
      return 'unavailable';
    }
    const incoming = drivers(message.drivers);
    if (incoming === null) return 'resync';
    if (message.type === 'snapshot') {
      if (message.sequence !== 0 && message.generation !== this.generation) return 'resync';
      this.generation = message.generation; this.sequence = message.sequence; this.drivers = incoming;
    } else {
      if (message.generation !== this.generation || message.sequence !== this.sequence + 1) return 'resync';
      if (message.type === 'delta') this.drivers = mergeDrivers(this.drivers, incoming);
      else if (message.type === 'reset' && object(message.scope) && Array.isArray(message.scope.drivers)) {
        const next = structuredClone(this.drivers);
        for (const driver of message.scope.drivers) {
          const key = String(driver);
          if (Object.hasOwn(incoming, key)) next[key] = incoming[key]; else delete next[key];
        }
        this.drivers = next;
      } else return 'resync';
      this.sequence = message.sequence;
    }
    this.status = 'ready'; this.reason = null;
    this.generatedAt = typeof message.generated_at === 'string' ? message.generated_at : null;
    this.streamTimestamp = typeof message.stream_timestamp === 'string' ? message.stream_timestamp : null;
    return 'updated';
  }
  value() {
    return { status: this.status, reason: this.reason, generation: this.generation, sequence: this.sequence,
      drivers: structuredClone(this.drivers), generated_at: this.generatedAt ?? null, stream_timestamp: this.streamTimestamp ?? null };
  }
}

export function minisectorContext(hass, entry, selection) {
  if (!entry || selection?.source === 'archive') return null;
  const state = key => {
    const id = entry.entities?.[key]; return id ? hass?.states?.[id] : null;
  };
  const replay = state('replay_status'), player = state('replay_player');
  const replayState = String(replay?.state ?? player?.attributes?.replay_state ?? '').toLowerCase();
  const replayActive = ['selected', 'loading', 'ready', 'seeking', 'playing', 'paused'].includes(replayState);
  const requested = selection?.mode === 'pinned' ? selection.source : selection?.source ?? 'auto';
  const source = requested === 'auto' ? replayActive ? 'replay' : 'live' : requested;
  const sessionKey = selection?.mode === 'pinned' ? selection.session_key : source === 'replay'
    ? replay?.attributes?.selected_session_key ?? player?.attributes?.selected_session_key
    : state('current_session')?.attributes?.session_key;
  if (!['live', 'replay'].includes(source) || sessionKey === null || sessionKey === undefined || !String(sessionKey).trim()) return null;
  return { entryId: entry.entry_id, source, sessionKey: String(sessionKey), key: JSON.stringify([entry.entry_id, source, String(sessionKey)]) };
}

export function segmentStrip(driver, sector) {
  const segments = driver?.sectors?.[String(sector)]?.segments;
  if (!object(segments)) return [];
  const indexes = Object.keys(segments).map(Number).filter(index => Number.isInteger(index) && index >= 0 && index < MAX_SEGMENTS);
  if (!indexes.length) return [];
  return Array.from({ length: Math.max(...indexes) + 1 }, (_, index) => ({ index, raw: integer(segments[String(index)]) }));
}

export const usesMinisectors = module => module?.type === 'minisectors'
  || module?.type === 'timing' && module.fields?.some(id => /^(?:mini|sector_[123]_with_mini)/.test(id));
