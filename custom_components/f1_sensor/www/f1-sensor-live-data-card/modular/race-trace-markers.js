// Marker context and observation order are validated before this pure projection.
const KINDS = ['pit', 'sc', 'vsc', 'red_flag'];
const PHASES = ['point', 'start', 'ending', 'end'];
const text = value => typeof value === 'string' && value.trim() ? value.trim() : null;
const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
const driverId = value => (typeof value === 'string' && /^\d+$/.test(value.trim()) || typeof value === 'number')
  && Number.isInteger(Number(value)) && Number(value) > 0 && Number(value) <= 99 ? String(Number(value)) : null;
const lapNumber = value => Number.isInteger(value) && value > 0 && value <= 500 ? value : null;

function projectEvent(raw, reference, drivers) {
  if (!KINDS.includes(raw.kind)) return null;
  let driver, lap, anchor_type;
  if (raw.kind === 'pit') {
    driver = driverId(raw.driver_number); lap = lapNumber(raw.lap_number);
    if (raw.phase !== 'point' || raw.source !== 'PitStopSeries' || raw.anchor_type !== 'driver_lap' || !drivers.has(driver)) return null;
    anchor_type = 'driver_lap';
  } else {
    if (!['start', 'ending', 'end'].includes(raw.phase) || raw.source !== 'TrackStatus' || !drivers.has(reference)) return null;
    const anchors = Object.entries(object(raw.reference_anchors)).filter(([id]) => driverId(id) === reference).map(([, value]) => object(value));
    if (!anchors.length || anchors.some(anchor => anchor.basis !== 'confirmed_completed' || lapNumber(anchor.lap_number) === null)
      || new Set(anchors.map(anchor => anchor.lap_number)).size !== 1) return null;
    driver = reference; lap = anchors[0].lap_number; anchor_type = 'reference_driver_lap';
  }
  if (lap === null) return null;
  return { id: text(raw.event_id), revision: raw.revision, kind: raw.kind, phase: raw.phase,
    driver, lap, anchor_type, source: raw.source, description: text(raw.description) };
}

export function raceTraceMarkers(traceModel, validatedMarkerSnapshot, selectedKinds = []) {
  const kinds = new Set((Array.isArray(selectedKinds) ? selectedKinds : []).filter(kind => KINDS.includes(kind)));
  const empty = (status, reason = null) => ({ status, reason, events: [] });
  if (!kinds.size) return empty('disabled');
  const snapshot = validatedMarkerSnapshot;
  if (!snapshot || snapshot.status !== 'ready') return empty(text(snapshot?.status) ?? 'unavailable', text(snapshot?.reason) ?? 'marker_data_unavailable');
  if (traceModel?.status !== 'ready') return empty('pending', 'waiting_for_trace');
  if (!Array.isArray(snapshot.events)) return empty('unavailable', 'invalid_events');
  const reference = driverId(traceModel.referenceDriver);
  const drivers = new Set((Array.isArray(traceModel.series) ? traceModel.series : []).map(series => driverId(series.id)).filter(Boolean));
  const laps = new Set((Array.isArray(traceModel.rounds) ? traceModel.rounds : []).map(round => lapNumber(round.id)).filter(lap => lap !== null));
  const latest = new Map(), uncertain = new Set();
  for (const raw of snapshot.events) {
    const id = text(raw?.event_id);
    if (!id) continue;
    // An unorderable correction cannot leave an older point looking current.
    if (!Number.isSafeInteger(raw.revision) || raw.revision < 1) { uncertain.add(id); continue; }
    const previous = latest.get(id);
    if (previous && previous.revision > raw.revision) continue;
    const event = projectEvent(raw, reference, drivers), signature = JSON.stringify(event);
    if (previous && previous.revision === raw.revision) {
      if (previous.signature !== signature) previous.ambiguous = true;
    } else latest.set(id, { revision: raw.revision, event, signature, ambiguous: false });
  }
  const events = [...latest.entries()].filter(([id, item]) => !uncertain.has(id) && !item.ambiguous && item.event
    && kinds.has(item.event.kind) && laps.has(item.event.lap)).map(([, item]) => item.event);
  events.sort((a, b) => a.lap - b.lap || PHASES.indexOf(a.phase) - PHASES.indexOf(b.phase)
    || a.kind.localeCompare(b.kind) || Number(a.driver) - Number(b.driver) || a.id.localeCompare(b.id));
  return { status: 'ready', reason: null, events };
}
