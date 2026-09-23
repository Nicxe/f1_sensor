const version = new URL(import.meta.url).searchParams.get('v');
const { replayModel } = await import(`./data.js${version ? `?v=${encodeURIComponent(version)}` : ''}`);
export const CHANNELS = {
  speed: { en: 'Speed', sv: 'Hastighet', unit: 'km/h', min: 0, max: 500 },
  throttle: { en: 'Throttle', sv: 'Gas', unit: '%', min: 0, max: 100 },
  brake: { en: 'Brake signal', sv: 'Bromssignal', unit: '', min: 0, max: 100 },
  gear: { en: 'Gear', sv: 'Växel', unit: '', min: 0, max: 8 },
  drs: { en: 'DRS code', sv: 'DRS-kod', unit: '', min: 0, max: 99 },
  rpm: { en: 'Engine speed', sv: 'Motorvarvtal', unit: 'rpm', min: 0, max: 25000 },
  delta_s: { en: 'Estimated time delta', sv: 'Uppskattat tidsdelta', unit: 's', min: -1000, max: 1000 },
};
const number = value => typeof value === 'number' && Number.isFinite(value) ? value : null;
const validId = id => typeof id === 'string' && /^[1-9]\d?:[1-9]\d{0,2}$/.test(id) && Number(id.split(':')[1]) <= 500;
export function canonicalSelections(selected) {
  return [...new Set(selected.filter(validId))].map(id => id.split(':').map(Number))
    .sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(([driver_number, lap_number]) => ({ driver_number, lap_number }));
}
export function telemetryPlan(module, entry, replay, read, requested) {
  const options = module.options, selected = options.selected ?? [];
  const catalogQuery = replay.loaded && entry?.entry_id ? { type: 'f1_sensor/analysis/telemetry_catalog', entry_id: entry.entry_id, expected_session_id: replay.sessionId } : null;
  const state = catalogQuery ? read(catalogQuery) : null, payload = state?.data?.payload;
  const valid = payload?.protocol_version === 1 && payload.session_id === replay.sessionId && Array.isArray(payload.drivers);
  const drivers = valid ? payload.drivers.filter(driver => Number.isInteger(driver.driver_number) && driver.driver_number >= 1 && driver.driver_number <= 99)
    .map(driver => ({ id: String(driver.driver_number), name: [driver.name ?? driver.tla ?? driver.driver_number, driver.team].filter(Boolean).join(' · '), laps: [...new Set((Array.isArray(driver.laps) ? driver.laps : []).filter(lap => Number.isInteger(lap) && lap >= 1 && lap <= 500))].sort((a, b) => a - b) })) : [];
  const selectionChanged = Boolean(replay.loaded && selected.length > 0 && options.session_id !== replay.sessionId);
  const missing = valid && state.status === 'ready' ? selected.filter(id => !drivers.some(driver => driver.id === id.split(':')[0] && driver.laps.includes(Number(id.split(':')[1])))) : [];
  const canCompare = Boolean(replay.loaded && valid && state.status === 'ready' && !selectionChanged && selected.length && selected.length <= 4 && !missing.length);
  const compareQuery = canCompare ? { type: 'f1_sensor/analysis/telemetry_compare', entry_id: entry.entry_id, expected_session_id: replay.sessionId, selections: canonicalSelections(selected) } : null;
  const activeCompare = compareQuery && JSON.stringify(compareQuery) === JSON.stringify(requested) ? compareQuery : null;
  return { replay, catalogQuery, compareQuery, activeCompare, drivers, selected, selectionChanged, missing, canCompare,
    loading: state && ['loading', 'refreshing'].includes(state.status), disconnected: state?.status === 'disconnected',
    error: Boolean(state && (state.data?.failed || state.status === 'error' || state.status === 'ready' && !valid)),
    requests: [catalogQuery, activeCompare].filter(Boolean) };
}
export function telemetryModel(hass, entry, module, read, requested) {
  const plan = telemetryPlan(module, entry, replayModel(hass, entry), read, requested);
  const state = plan.activeCompare ? read(plan.activeCompare) : null, payload = state?.data?.payload;
  const expected = plan.activeCompare?.selections.map(item => `${item.driver_number}:${item.lap_number}`) ?? [];
  const ids = Array.isArray(payload?.series) ? payload.series.map(item => `${item.driver_number}:${item.lap_number}`) : [];
  const valid = payload?.protocol_version === 1 && payload.session_id === plan.replay.sessionId && ids.length === expected.length && new Set(ids).size === ids.length && ids.every(id => expected.includes(id));
  const series = valid ? payload.series.slice(0, 4).map(item => {
    const id = `${item.driver_number}:${item.lap_number}`, driver = plan.drivers.find(driver => driver.id === String(item.driver_number));
    return { id, driver: String(item.driver_number), lap: item.lap_number, name: driver?.name ?? String(item.driver_number), samples: (Array.isArray(item.samples) ? item.samples : []).slice(0, 500).map(sample => ({
      time_s: number(sample.time_s), distance: number(sample.distance), gap_before: sample.gap_before === true,
      ...Object.fromEntries(Object.entries(CHANNELS).map(([key, spec]) => { const value = number(sample[key]); return [key, value !== null && value >= spec.min && value <= spec.max ? value : null]; })),
    })).filter(sample => sample.time_s !== null && sample.time_s >= 0).sort((a, b) => a.time_s - b.time_s) };
  }).sort((a, b) => Number(a.driver) - Number(b.driver) || a.lap - b.lap) : [];
  return { ...plan, fields: module.fields, options: module.options, series, reference: series[0]?.id,
    comparing: state && ['loading', 'refreshing'].includes(state.status), compared: Boolean(state?.status === 'ready' && valid),
    compareError: Boolean(state && (state.data?.failed || state.status === 'error' || state.status === 'ready' && !valid)), compareDisconnected: state?.status === 'disconnected',
    receivedAt: state?.received_at ?? null };
}
export function telemetrySegments(samples, channel, axis = 'time_s') {
  const segments = []; let segment = [], previous = null;
  for (const sample of samples) {
    const x = number(sample[axis]), y = number(sample[channel]);
    if (x === null || y === null || sample.gap_before || previous && (sample.time_s <= previous.time_s || sample.time_s - previous.time_s > 2 || x < previous[axis])) {
      if (segment.length) segments.push(segment); segment = [];
    }
    if (x !== null && y !== null) segment.push({ x, y });
    previous = sample;
  }
  if (segment.length) segments.push(segment);
  return segments;
}
