export const RADAR_API = 'https://api.librewxr.net';
export const RADAR_METADATA_URL = `${RADAR_API}/public/weather-maps.json`;
export const RADAR_REFRESH_MS = 5 * 60 * 1000;
const MAX_AGE_SECONDS = 30 * 60;
export const RADAR_MIN_ZOOM = 5;
export const RADAR_MAX_ZOOM = 14;
export const RADAR_DEFAULT_ZOOM = 13;
export const RADAR_NATIVE_ZOOM = 12;
const EARTH_CIRCUMFERENCE = 40075016.686;
export const radarZoom = value => Number.isFinite(Number(value))
  ? Math.max(RADAR_MIN_ZOOM, Math.min(RADAR_MAX_ZOOM, Math.round(Number(value)))) : RADAR_DEFAULT_ZOOM;

// A successful empty tile is not evidence of either radar coverage or dry weather.
// LibreWXR's precipitation mosaic also contains satellite estimates and models.
export function radarMetadata(payload, now = Date.now()) {
  const seconds = now / 1000;
  if (payload?.host !== RADAR_API || !Number.isFinite(payload.generated)
    || payload.generated > seconds + 300 || seconds - payload.generated > MAX_AGE_SECONDS) {
    throw new Error('Invalid or stale precipitation metadata');
  }
  const frames = new Map();
  for (const [type, items] of [['observed', payload.radar?.past], ['forecast', payload.radar?.nowcast]]) {
    if (!Array.isArray(items) || items.length > 36) throw new Error('Invalid precipitation frames');
    for (const item of items) {
      if (!Number.isInteger(item?.time) || item.time < payload.generated - 4 * 3600
        || item.time > payload.generated + 2 * 3600 || item.path !== `/v2/radar/${item.time}`) {
        throw new Error('Invalid precipitation frame');
      }
      if (!frames.has(item.time)) frames.set(item.time, Object.freeze({ time: item.time, path: item.path, type }));
    }
  }
  const sorted = [...frames.values()].sort((a, b) => a.time - b.time);
  const observed = sorted.filter(frame => frame.type === 'observed');
  if (!observed.length || seconds - observed.at(-1).time > MAX_AGE_SECONDS
    || observed.at(-1).time > seconds + 300 || sorted.length > 36) {
    throw new Error('No recent precipitation frames');
  }
  const latestTime = observed.at(-1).time;
  const near = sorted.filter(frame => frame.time >= latestTime - 1800 && frame.time <= latestTime + 1800);
  const intervals = [...new Set(sorted.slice(1).map((frame, index) => (frame.time - sorted[index].time) / 60))];
  return Object.freeze({ generated: payload.generated, latestTime,
    intervalMinutes: intervals.length === 1 ? intervals[0] : null, frames: Object.freeze(near) });
}

// All map layers use the same Web Mercator projection. Outlines are geographic
// centerlines; normalized F1 artwork must never be placed onto this map.
const worldPoint = (lat, lon, zoom) => ({
  x: (lon + 180) / 360 * 2 ** zoom,
  y: (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * 2 ** zoom,
});

const outlineCenters = new WeakMap();
function outlineCenter(outline) {
  if (!outline || typeof outline !== 'object') return null;
  if (outlineCenters.has(outline)) return outlineCenters.get(outline);
  const points = outline.coordinates;
  let center = null;
  if (Array.isArray(points) && points.length >= 3 && points.length <= 5000
    && points.every(point => Array.isArray(point) && point.length === 2 && Number.isFinite(point[0])
      && Number.isFinite(point[1]) && Math.abs(point[0]) <= 180 && Math.abs(point[1]) <= 85)) {
    let west = 180, east = -180, south = 85, north = -85;
    for (const [lon, lat] of points) { west = Math.min(west, lon); east = Math.max(east, lon); south = Math.min(south, lat); north = Math.max(north, lat); }
    if (east - west <= 2 && north - south <= 2) center = { lat: (south + north) / 2, lon: (west + east) / 2 };
  }
  outlineCenters.set(outline, center);
  return center;
}

export function radarCircuit(circuits, selectedId, outlines = {}) {
  const valid = (Array.isArray(circuits) ? circuits : []).filter(item => item && typeof item.id === 'string'
    && typeof item.name === 'string' && Number.isFinite(item.lat) && Number.isFinite(item.lon)
    && Math.abs(item.lat) <= 85 && Math.abs(item.lon) <= 180).map(circuit => {
    const outline = outlines[circuit.id], center = outlineCenter(outline);
    return center ? { ...circuit, ...center, outline } : circuit;
  });
  return { circuits: valid, selected: valid.find(item => item.id === selectedId) ?? valid[0] ?? null };
}

export function radarMapPoint(circuit, coordinate, zoom = RADAR_DEFAULT_ZOOM) {
  const z = radarZoom(zoom), center = worldPoint(circuit.lat, circuit.lon, z);
  const point = worldPoint(coordinate[1], coordinate[0], z), size = 2 ** z;
  let dx = point.x - center.x;
  if (dx > size / 2) dx -= size;
  if (dx < -size / 2) dx += size;
  return { x: 256 + dx * 256, y: 192 + (point.y - center.y) * 256 };
}

export function radarTrackPath(circuit, zoom = RADAR_DEFAULT_ZOOM) {
  return circuit?.outline?.coordinates?.map((coordinate, index) => {
    const point = radarMapPoint(circuit, coordinate, zoom);
    return `${index ? 'L' : 'M'}${point.x.toFixed(3)},${point.y.toFixed(3)}`;
  }).join(' ') ?? '';
}

export function radarScale(circuit, zoom = RADAR_DEFAULT_ZOOM) {
  const metersPerPixel = Math.cos(circuit.lat * Math.PI / 180) * EARTH_CIRCUMFERENCE / (256 * 2 ** radarZoom(zoom));
  const target = metersPerPixel * 128, magnitude = 10 ** Math.floor(Math.log10(target));
  const meters = [5, 2, 1].map(value => value * magnitude).find(value => value <= target);
  return { meters, width: meters / metersPerPixel / 512 * 100,
    label: meters >= 1000 ? `${meters / 1000} km` : `${meters} m` };
}

// At close zoom levels, enlarge native radar tiles without inventing detail.
// Request each needed parent tile once; base tiles remain at the display zoom.
export function radarTiles(circuit, zoom = RADAR_DEFAULT_ZOOM, maxSourceZoom = RADAR_MAX_ZOOM) {
  const displayZoom = radarZoom(zoom), z = Math.min(displayZoom, maxSourceZoom);
  const size = 2 ** z, scale = 2 ** (displayZoom - z);
  const { x, y } = worldPoint(circuit.lat, circuit.lon, z);
  const minX = scale === 1 ? Math.floor(x) - 1 : Math.floor(x - 1 / scale);
  const maxX = scale === 1 ? Math.floor(x) + 1 : Math.floor(x + 1 / scale);
  const minY = scale === 1 ? Math.floor(y) - 1 : Math.floor(y - .75 / scale);
  const maxY = scale === 1 ? Math.floor(y) + 1 : Math.floor(y + .75 / scale);
  const tiles = [];
  for (let tileY = minY; tileY <= maxY; tileY++) for (let tileX = minX; tileX <= maxX; tileX++) {
    if (tileY < 0 || tileY >= size) continue;
    tiles.push({ z, x: (tileX + size) % size, y: tileY,
      left: (tileX - x) * 50 * scale + 50, top: (tileY - y) * (256 / 384 * 100) * scale + 50,
      width: 50 * scale, height: 256 / 384 * 100 * scale });
  }
  return tiles;
}

export const radarTileUrl = (frame, tile) => `${RADAR_API}${frame.path}/256/${tile.z}/${tile.x}/${tile.y}/2/1_0.png`;
export const radarBaseUrl = tile => `https://tile.openstreetmap.org/${tile.z}/${tile.x}/${tile.y}.png`;

// Shared by visible module instances. A disappearing consumer releases its lease;
// the last release cancels an unfinished request without disrupting other cards.
export function createRadarMetadataCache({ fetcher = (...args) => fetch(...args), now = Date.now } = {}) {
  let value = null, expires = 0, flight = null;
  return {
    acquire() {
      if (value && now() < expires) return { promise: Promise.resolve(value), release() {} };
      if (!flight) {
        const controller = new AbortController();
        const current = { controller, users: 0, promise: null };
        let timedOut = false;
        const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 15000);
        current.promise = (async () => {
          try {
            const response = await fetcher(RADAR_METADATA_URL, { signal: controller.signal, credentials: 'omit' });
            if (!response.ok) throw new Error('Precipitation service unavailable');
            const result = radarMetadata(await response.json(), now());
            if (controller.signal.aborted) throw new DOMException('Aborted', 'AbortError');
            value = result;
            expires = now() + RADAR_REFRESH_MS;
            return result;
          } catch (error) {
            if (timedOut && error.name === 'AbortError') throw new Error('Precipitation metadata request timed out');
            throw error;
          } finally {
            clearTimeout(timeout);
            if (flight === current) flight = null;
          }
        })();
        flight = current;
      }
      const current = flight;
      current.users++;
      let released = false;
      return { promise: current.promise, release() {
        if (released) return;
        released = true;
        current.users--;
        if (!current.users && flight === current) {
          flight = null;
          current.controller.abort();
        }
      } };
    },
  };
}

export const radarMetadataCache = createRadarMetadataCache();
