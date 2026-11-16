// Cumulative recorded lap-time differences, never a simultaneous race gap.
const version = new URL(import.meta.url).searchParams.get('v');
const { seconds, number } = await import(`./semantics.js${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const MAX_LAP = 500;
const driverId = value => (typeof value === 'string' && /^\d+$/.test(value.trim()) || typeof value === 'number')
  && Number.isInteger(Number(value)) && Number(value) > 0 && Number(value) <= 99 ? String(Number(value)) : null;
const lapNumber = value => /^\d+$/.test(String(value)) && Number(value) > 0 && Number(value) <= MAX_LAP ? Number(value) : null;
const anchorValid = value => Number.isInteger(value) && value >= 0 && value <= MAX_LAP;
const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
const label = (...values) => values.find(value => typeof value === 'string' && value.trim())?.trim() ?? null;

function recordedLaps(driver, completed) {
  const result = new Map(), metadata = object(driver.lap_metadata);
  // Legacy times can survive a delay reset. Only association observations can
  // establish this context's range, while conflicting aliases still form gaps.
  const observed = new Set(Object.entries(metadata).filter(([, value]) => ['confirmed', 'inferred', 'ambiguous'].includes(object(value).association))
    .map(([key]) => lapNumber(key)).filter(lap => lap !== null && lap <= completed));
  for (const [key, raw] of Object.entries(object(driver.laps))) {
    const lap = lapNumber(key);
    if (!observed.has(lap)) continue;
    const association = object(metadata[key] ?? metadata[String(lap)]).association;
    const time = seconds(raw), ms = time !== null && Number.isFinite(time) ? Math.round(time * 1000) : null;
    const reason = !Number.isSafeInteger(ms) || ms <= 0 ? 'invalid_time'
      : association === 'ambiguous' ? 'ambiguous_lap' : association !== 'confirmed' ? 'unconfirmed_lap' : null;
    const candidate = { time, ms, reason }, previous = result.get(lap);
    if (!previous) result.set(lap, candidate);
    // A snapshot supplies no ordering guarantee between aliases of one lap.
    else if (previous.time !== time || previous.reason === 'ambiguous_lap' || reason === 'ambiguous_lap') result.set(lap, { time: null, ms: null, reason: 'ambiguous_lap' });
    else if (reason) result.set(lap, candidate);
  }
  return result;
}

export function raceTraceModel(rawDrivers, { reference_driver, selected = [], anchor_lap = 0, lockedAnchor = null } = {}) {
  const referenceDriver = driverId(reference_driver);
  let anchorLap = anchorValid(anchor_lap) && anchor_lap > 0 ? anchor_lap
    : anchorValid(lockedAnchor) && lockedAnchor > 0 ? lockedAnchor : null;
  const empty = (status, reason) => ({ metric: 'cumulative_lap_delta', axisKind: 'lap', status, reason, anchorLap, referenceDriver, rounds: [], series: [] });
  if (!reference_driver) return empty('invalid_selection', 'reference_required');
  if (!referenceDriver || !Array.isArray(selected) || selected.some(value => !driverId(value))) return empty('invalid_selection', 'invalid_selection');
  if (!anchorValid(anchor_lap) || lockedAnchor !== null && (!anchorValid(lockedAnchor) || lockedAnchor === 0)) return empty('invalid_selection', 'invalid_anchor');
  const ids = [...new Set([referenceDriver, ...selected.map(driverId)])];
  if (ids.length > 4) return empty('invalid_selection', 'too_many_drivers');
  const drivers = [];
  for (const id of ids) {
    const matches = (Array.isArray(rawDrivers) ? rawDrivers : []).filter(item => item && driverId(item.racing_number) === id);
    if (!matches.length) return empty('pending', id === referenceDriver ? 'reference_missing' : 'driver_missing');
    if (matches.length !== 1) return empty('pending', 'ambiguous_driver');
    const raw = matches[0], completed = number(raw.completed_laps);
    if (!Number.isSafeInteger(completed) || completed < 0) return empty('pending', 'completion_unknown');
    drivers.push({ id, driver: label(raw.tla, id), name: label(raw.full_name, raw.name, raw.tla, id), team: label(raw.team),
      isReference: id === referenceDriver, laps: recordedLaps(raw, completed) });
  }
  const observed = [...new Set(drivers.flatMap(item => [...item.laps.keys()]))].sort((a, b) => a - b);
  const common = lap => drivers.every(item => item.laps.has(lap) && item.laps.get(lap).reason === null);
  if (anchorLap === null) anchorLap = observed.find(common) ?? null;
  if (anchorLap === null) return empty('pending', 'no_common_anchor');
  if (!common(anchorLap)) return empty('pending', 'anchor_unavailable');
  const first = observed[0], last = observed.at(-1);
  const rounds = Array.from({ length: last - first + 1 }, (_, i) => ({ id: first + i }));
  const reference = drivers[0].laps;
  const series = drivers.map(({ laps, ...identity }) => {
    let sum = 0, broken = false;
    const values = rounds.map(({ id: lap }) => {
      let reason = null, delta = null;
      if (lap < anchorLap) reason = 'before_anchor';
      else if (broken) reason = 'preceding_gap';
      else {
        const ref = reference.get(lap), own = laps.get(lap);
        reason = !ref || !own ? 'missing_lap' : ref.reason ?? own.reason;
        if (!reason) {
          const next = lap === anchorLap ? 0 : sum + (own.ms - ref.ms);
          if (!Number.isSafeInteger(next)) reason = 'unsafe_sum';
          else { sum = next; delta = sum; }
        }
        broken = reason !== null;
      }
      return { round: lap, value: delta === null ? null : delta / 1000, delta_ms: delta, reason };
    });
    return { ...identity, values };
  });
  return { ...empty('ready', null), rounds, series };
}

// Display limits never choose a new anchor or restart a cumulative sum.
export function clipRaceTrace(model, start_lap = 0, end_lap = 0) {
  const first = start_lap || model.rounds[0]?.id || 0, last = end_lap || model.rounds.at(-1)?.id || 0;
  const invalidRange = !anchorValid(start_lap) || !anchorValid(end_lap)
    || first > last && (model.status === 'ready' || start_lap > 0 && end_lap > 0);
  if (invalidRange) return { ...model, invalidRange: true, rounds: [], series: model.series.map(item => ({ ...item, values: [] })) };
  if (model.status !== 'ready' || first === 0 || last === 0) return { ...model, invalidRange: false };
  const rounds = Array.from({ length: last - first + 1 }, (_, i) => ({ id: first + i }));
  const series = model.series.map(item => {
    const points = new Map(item.values.map(point => [point.round, point]));
    return { ...item, values: rounds.map(({ id }) => points.get(id) ?? { round: id, value: null, delta_ms: null, reason: id < model.anchorLap ? 'before_anchor' : 'missing_lap' }) };
  });
  return { ...model, invalidRange: false, rounds, series };
}
