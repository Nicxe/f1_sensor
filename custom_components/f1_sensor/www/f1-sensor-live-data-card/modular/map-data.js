const version = new URL(import.meta.url).searchParams.get('v');
const { number } = await import(`./semantics.js${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const object = value => value && typeof value === 'object' && !Array.isArray(value);
const sequence = value => Number.isSafeInteger(value) && value >= 0;
const drivers = value => Array.isArray(value) ? value.filter(item => object(item) && item.racing_number != null) : [];

// A decoder belongs to one frontend subscription generation. Reconnect creates a
// new decoder; a sequence from a prior server hub must never survive that reset.
export class TrackMapState {
  constructor(entryId) { this.entryId = entryId; this.sequence = null; this.snapshot = null; this.geometryRevision = null; }
  accept(message) {
    if (!object(message) || message.entry_id !== this.entryId) return 'ignored';
    if (message.status === 'closed') return 'closed';
    if (message.protocol_version !== 2 || !sequence(message.sequence)) return 'resync';
    if (this.sequence !== null && message.sequence <= this.sequence) return 'ignored';
    if (message.type === 'snapshot') {
      const snapshot = message.snapshot;
      if (!object(snapshot) || snapshot.entry_id !== this.entryId || !Array.isArray(snapshot.drivers)) return 'resync';
      this.snapshot = { ...snapshot, drivers: [...new Map(drivers(snapshot.drivers).map(driver => [String(driver.racing_number), driver])).values()] };
    } else if (message.type === 'delta') {
      if (!this.snapshot || message.base_sequence !== this.sequence || !object(message.changes) || !Array.isArray(message.removed) || !object(message.patch)) return 'resync';
      if (Object.hasOwn(message.patch, 'entry_id') && message.patch.entry_id !== this.entryId) return 'resync';
      const sessionKey = session => JSON.stringify([session?.session_key, session?.path, session?.meeting_key]);
      const changedSession = Object.hasOwn(message.patch, 'session') && sessionKey(message.patch.session) !== sessionKey(this.snapshot.session);
      if (changedSession && this.snapshot.track && !Object.hasOwn(message.patch, 'track')) return 'resync';
      const mapped = new Map((changedSession ? [] : this.snapshot.drivers).map(driver => [String(driver.racing_number), driver]));
      for (const [id, driver] of Object.entries(message.changes)) {
        if (!object(driver) || String(driver.racing_number) !== id) return 'resync';
        mapped.set(id, driver);
      }
      for (const id of message.removed) mapped.delete(String(id));
      // Drivers are defined by changes/removals, never by a nested patch array.
      const { drivers: ignored, ...patch } = message.patch;
      const invalidatesAnnotations = changedSession || Object.hasOwn(patch, 'track') || ['seeking', 'loading'].includes(patch.replay_state);
      this.snapshot = { ...this.snapshot, ...patch, annotations: Object.hasOwn(patch, 'annotations') ? patch.annotations : invalidatesAnnotations ? null : this.snapshot.annotations, drivers: [...mapped.values()] };
    } else return 'resync';
    this.sequence = message.sequence; this.geometryRevision = message.geometry_revision;
    return 'updated';
  }
}

export function trackProjection(track, invertY = true) {
  const points = Array.isArray(track?.points) ? track.points : [];
  if (points.length > 50_000) return null;
  // Preserve path gaps. Removing a malformed point would silently draw a line
  // over a geometry discontinuity instead of exposing incomplete source data.
  const valid = points.map(point => Array.isArray(point) && number(point[0]) !== null && number(point[1]) !== null ? [number(point[0]), number(point[1])] : null);
  const actual = valid.filter(Boolean);
  if (actual.length < 2) return null;
  const minX = Math.min(...actual.map(point => point[0])), maxX = Math.max(...actual.map(point => point[0]));
  const minY = Math.min(...actual.map(point => point[1])), maxY = Math.max(...actual.map(point => point[1]));
  if (minX === maxX && minY === maxY) return null;
  const center = [(minX + maxX) / 2, (minY + maxY) / 2], rotation = (number(track.rotation) ?? 0) * Math.PI / 180;
  const rotate = (x, y) => { const a = x - center[0], b = y - center[1]; return [a * Math.cos(rotation) - b * Math.sin(rotation), a * Math.sin(rotation) + b * Math.cos(rotation)]; };
  const rotated = actual.map(point => rotate(...point));
  const left = Math.min(...rotated.map(point => point[0])), right = Math.max(...rotated.map(point => point[0]));
  const bottom = Math.min(...rotated.map(point => point[1])), top = Math.max(...rotated.map(point => point[1]));
  const width = right - left, height = top - bottom;
  if (!Number.isFinite(width) || !Number.isFinite(height)) return null;
  const rotatedCenter = [(left + right) / 2, (bottom + top) / 2];
  const scale = 90 / Math.max(width, height, 1);
  const project = (x, y) => {
    if (number(x) === null || number(y) === null) return null;
    const [a, b] = rotate(number(x), number(y)); return [50 + (a - rotatedCenter[0]) * scale, 50 + (b - rotatedCenter[1]) * scale * (invertY ? -1 : 1)];
  };
  return { points: valid.map(point => point && project(...point)), project };
}

export function mapExpiry(snapshot) {
  if (!snapshot || snapshot.source === 'replay' || snapshot.stale === true || snapshot.status === 'stale') return null;
  const timestamp = Date.parse(snapshot.stream_timestamp), threshold = number(snapshot.stale_after_seconds);
  return Number.isFinite(timestamp) && threshold !== null && threshold >= 0 ? timestamp + threshold * 1000 : null;
}

export function mapFreshness(snapshot, now = Date.now()) {
  if (!snapshot) return { stale: true, age: null };
  const timestamp = Date.parse(snapshot.stream_timestamp), age = Number.isFinite(timestamp) ? Math.max(0, now - timestamp) / 1000 : null;
  const threshold = number(snapshot.stale_after_seconds);
  const replay = snapshot.source === 'replay';
  return { stale: snapshot.stale === true || snapshot.status === 'stale' || (!replay && age !== null && threshold !== null && threshold >= 0 && age >= threshold), age };
}

function inactiveDriverIds(driverPositions) {
  const inactive = new Set();
  for (const item of drivers(driverPositions)) {
    const status = String(item.status ?? '').trim().toLowerCase();
    if (!item.retired && !item.stopped && !['out', 'retired'].includes(status)) continue;
    if (item.racing_number != null) inactive.add(String(item.racing_number));
    if (item.tla) inactive.add(String(item.tla).toUpperCase());
  }
  return inactive;
}

const projections = new WeakMap();
function projectionFor(track, options) {
  if (!object(track)) return null;
  let variants = projections.get(track);
  if (!variants) { variants = new Map(); projections.set(track, variants); }
  const key = `${options.orientation}:${options.vertical}`;
  if (!variants.has(key)) variants.set(key, trackProjection(options.orientation === 'raw' ? { ...track, rotation: 0 } : track, options.vertical === 'flipped'));
  return variants.get(key);
}

const ANNOTATION_FIELDS = { map_start_finish: 'start_finish', map_corners: 'corners', map_sectors: 'sectors', map_speed_traps: 'speed_traps', map_detection_zones: 'detection_zones' };
const REVIEWED_LAYOUTS = { '2:2025': 'silverstone_2025', '61:2025': 'marina_bay_post_2023', '61:2026': 'marina_bay_post_2023' };
const pointInMap = point => Array.isArray(point) && point.length === 2 && point.every(value => Number.isFinite(value) && value >= 0 && value <= 100);
function annotationPoint(raw, projection) {
  if (!Array.isArray(raw) || raw.length !== 2 || raw.some(value => number(value) === null)) return null;
  const point = projection?.project(raw[0], raw[1]);
  return pointInMap(point) ? point : null;
}

export function mapAnnotations(snapshot, module, projection) {
  const selected = Object.entries(ANNOTATION_FIELDS).filter(([field]) => module.fields?.includes(field));
  const unavailable = selected.map(([field]) => field);
  const result = { lines: [], corners: [], points: [], unavailable };
  if (!selected.length || !projection || !snapshot || !object(snapshot.annotations)) return result;
  const payload = snapshot.annotations, binding = payload.binding, session = snapshot.session, track = snapshot.track;
  const season = /^(\d{4})\//.exec(session?.path ?? '')?.[1];
  const source = snapshot.source === 'replay' ? 'replay' : snapshot.source === 'live' ? 'live' : null;
  if (payload.schema_version !== 1 || !object(binding) || !Array.isArray(payload.layers) || payload.layers.length > 5 ||
    !source || snapshot.replay_state === 'seeking' || snapshot.replay_state === 'loading' ||
    binding.entry_id !== snapshot.entry_id || binding.source !== source || binding.session_key !== session?.session_key ||
    !Number.isSafeInteger(binding.session_generation) || binding.session_generation < 0 ||
    binding.circuit_key !== session?.circuit_key || binding.circuit_key !== track?.circuit_key ||
    !season || binding.season !== Number(season) ||
    (session?.start_date != null && (typeof session.start_date !== 'string' || !session.start_date.startsWith(`${season}-`))) ||
    binding.layout_key !== REVIEWED_LAYOUTS[`${binding.circuit_key}:${season}`] ||
    binding.geometry_fingerprint !== track?.geometry_fingerprint) return result;
  const layers = new Map();
  for (const layer of payload.layers) {
    if (!object(layer) || layers.has(layer.layer)) return result;
    layers.set(layer.layer, layer);
  }
  for (const [field, name] of selected) {
    const layer = layers.get(name);
    if (!layer || !object(layer.source) || typeof layer.source.url !== 'string' ||
      !Array.isArray(layer.columns) || !Array.isArray(layer.items) || layer.items.length > 64) continue;
    const columns = layer.columns;
    if (new Set(columns).size !== columns.length || columns.some(column => typeof column !== 'string')) continue;
    const parsed = [];
    for (const values of layer.items) {
      if (!Array.isArray(values) || values.length !== columns.length) { parsed.length = 0; break; }
      const item = Object.fromEntries(columns.map((column, index) => [column, values[index]]));
      if (typeof item.id !== 'string' || !/^[a-z0-9_]{1,64}$/.test(item.id) ||
        typeof item.label !== 'string' || item.label.length > 24) { parsed.length = 0; break; }
      if ((name === 'start_finish' || name === 'sectors') && item.kind === 'line' &&
        (name !== 'sectors' || /^S[12]$/.test(item.label))) {
        const start = annotationPoint(item.start, projection), end = annotationPoint(item.end, projection);
        if (!start || !end) { parsed.length = 0; break; }
        parsed.push({ id: `${name}:${item.id}`, layer: name, label: item.label, start, end });
      } else if (name === 'corners' && item.kind === 'point' && /^\d{1,2}$/.test(item.label)) {
        const point = annotationPoint(item.anchor, projection);
        if (!point) { parsed.length = 0; break; }
        const offset = Array.isArray(item.label_offset) && item.label_offset.length === 2 &&
          item.label_offset.every(value => number(value) !== null && Math.abs(value) <= 12)
          ? item.label_offset : [3, -4];
        parsed.push({ id: item.id, label: item.label, point, offset });
      } else if ((name === 'speed_traps' || name === 'detection_zones') && item.kind === 'point' &&
        (name !== 'detection_zones' || /^(?:DRS [DA][1-4]|OT [DA]|SM A[1-5] [NL])$/.test(item.label))) {
        const point = annotationPoint(item.anchor, projection);
        if (!point || !Array.isArray(item.label_offset) || item.label_offset.length !== 2 ||
          item.label_offset.some(value => number(value) === null || Math.abs(value) > 10)) { parsed.length = 0; break; }
        parsed.push({ id: `${name}:${item.id}`, layer: name, label: item.label, point, offset: item.label_offset });
      } else { parsed.length = 0; break; }
    }
    if (!parsed.length || new Set(parsed.map(item => item.id)).size !== parsed.length) continue;
    if (name === 'start_finish' || name === 'sectors') result.lines.push(...parsed);
    else if (name === 'corners') result.corners = parsed;
    else result.points.push(...parsed);
    result.unavailable = result.unavailable.filter(value => value !== field);
  }
  return result;
}

export function mapModel(snapshot, module, focus = {}, now = Date.now(), driverPositions = []) {
  if (!snapshot) return { pending: true, rows: [] };
  const projection = projectionFor(snapshot.track, module.options);
  const freshness = mapFreshness(snapshot, now), driver = module.driver || focus.driver, team = module.team || focus.team;
  // Position.z can retain an OnTrack coordinate after TimingData has declared
  // the driver out. Match the legacy card by removing stopped or retired cars.
  const inactive = inactiveDriverIds(driverPositions);
  const rows = drivers(snapshot.drivers).map(item => {
    const id = String(item.racing_number), name = item.full_name ?? item.name ?? item.tla ?? id;
    const point = projection?.project(item.x, item.y);
    const selected = Boolean((driver || team) && (!driver || [id, item.tla].includes(String(driver))) && (!team || item.team_name === team));
    return { id, name, driver: item.tla ?? id, team: item.team_name ?? null, team_color: item.team_color ?? null,
      point: point?.every(Number.isFinite) ? point : null, timestamp: item.timestamp, status: item.status, stale: freshness.stale || item.stale === true, selected };
  }).filter(row => !inactive.has(row.id) && !inactive.has(String(row.driver).toUpperCase()))
    .filter(row => module.options.focus !== 'filter' || !driver && !team || row.selected);
  rows.sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
  return { rows, points: projection?.points ?? null, annotations: mapAnnotations(snapshot, module, projection), freshness, status: snapshot.status, sourceMode: snapshot.source, sessionKey: JSON.stringify([snapshot.session?.session_key, snapshot.session?.path, snapshot.session?.meeting_key, snapshot.annotations?.binding?.session_generation]),
    context: { meeting: snapshot.session?.meeting_name, session: snapshot.session?.session_name, key: snapshot.session?.session_key, source: snapshot.source === 'replay' ? 'f1_replay' : 'f1_live', updated: snapshot.generated_at, updatedKind: 'generated' },
  };
}
