const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ source, array, sessionContext }, { number, positiveInteger, seconds, compoundMeta }, { selectRows }] = await Promise.all([
  load('./data.js'), load('./semantics.js'), load('./season-data.js'),
]);
const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
const records = value => array(value).filter(item => item && typeof item === 'object' && !Array.isArray(item));
const key = value => ['string', 'number'].includes(typeof value) ? String(value).trim() : '';
const text = value => typeof value === 'string' && value.trim() ? value.trim() : null;
const count = value => { const n = number(value); return Number.isInteger(n) && n >= 0 ? n : null; };
const unique = rows => [...new Map(rows.filter(row => row.id).map(row => [row.id, row])).values()];
const stamp = value => { const raw = text(value); return raw && Number.isFinite(Date.parse(raw)) ? new Date(raw).toISOString() : null; };
function roster(hass, entry) {
  const selected = source(hass, entry, 'driver_list');
  return selected.status === 'available' ? records(selected.attributes.drivers) : [];
}
function person(roster, rn, raw = {}) {
  const identity = roster.find(item => key(item.racing_number) === rn || Boolean(raw.tla && item.tla === raw.tla)) ?? {};
  return { id: rn || key(raw.tla), number: rn, driver: text(identity.tla ?? raw.tla) ?? rn,
    name: text(identity.full_name ?? identity.name ?? raw.name ?? raw.driver_name ?? raw.tla) ?? rn,
    team: text(identity.team ?? raw.team), team_color: text(identity.team_color ?? raw.team_color), history: [] };
}
function context(hass, entry, selected) {
  const session = sessionContext(hass, entry);
  return { session: session.name, meeting: session.meeting, key: session.key, source: selected.key === 'pitstops' ? 'PitStopSeries' : selected.key === 'current_tyres' || selected.key === 'tyre_statistics' ? 'TimingAppData' : 'Race Control', updated: selected.updated_at, updatedKind: 'ha_state' };
}
const compoundMatches = (value, module) => !module.options.compounds.length || module.options.compounds.includes(compoundMeta(value).key ?? 'UNKNOWN');

export function tyresModel(hass, entry, module, focus = {}) {
  const statistics = module.options.content === 'statistics';
  const selected = source(hass, entry, statistics ? 'tyre_statistics' : 'current_tyres'), attrs = selected.attributes;
  const people = roster(hass, entry);
  let rows;
  if (statistics) {
    rows = Object.entries(object(attrs.compounds)).map(([compound, value]) => {
      const item = object(value);
      const runs = records(item.best_times).map(run => ({ ...person(people, key(run.racing_number), { tla: run.driver_tla, driver_name: run.driver_name, team_color: run.team_color }),
        time: seconds(run.time_secs ?? run.time), stint: count(run.stint_index), new_tyre: typeof run.new_tyre === 'boolean' ? run.new_tyre : null,
      })).filter(run => run.time !== null).sort((a, b) => a.time - b.time).slice(0, module.options.best_times_limit);
      return { id: compound, tyre: compound, compound_best: runs[0]?.time ?? null, compound_gap: number(object(attrs.deltas)[compound]),
        compound_laps: count(item.total_laps), new_sets: count(item.sets_used), total_stints: count(item.sets_used_total), best_runs: runs };
    });
  } else rows = records(attrs.drivers).map(item => ({ ...person(people, key(item.racing_number), item), position: positiveInteger(item.position),
    tyre: text(item.compound ?? item.compound_short), tyre_age: count(item.stint_laps), tyre_new: typeof item.new === 'boolean' ? item.new : null }));
  rows = unique(rows).filter(row => compoundMatches(row.tyre, module));
  // Aggregate compound data cannot be filtered by a driver: the source has already
  // combined all competitors. Preserve pins for returning to the current-tyre view.
  const options = statistics ? { ...module.options, sort: ['position', 'driver', 'tyre_age'].includes(module.options.sort) ? 'compound_best' : module.options.sort } : module.options;
  const selection = statistics ? { ...module, options, driver: '', team: '' } : module;
  return { ...selectRows(rows, selection, statistics ? {} : focus), allRows: rows, source: selected, statistics,
    waiting: attrs.status === 'waiting_for_compound_data', context: context(hass, entry, selected), countKind: statistics ? 'compounds' : 'competitors' };
}

export function pitStopsModel(hass, entry, module, focus = {}) {
  const selected = source(hass, entry, 'pitstops'), people = roster(hass, entry);
  const positionSource = source(hass, entry, 'driver_positions');
  const statuses = new Map(positionSource.status === 'available' ? records(positionSource.attributes.drivers).map(item => {
    const rn = key(item.racing_number);
    return [rn, text(item.status) ?? (item.in_pit === true ? 'in_pit' : null)];
  }).filter(([rn]) => rn) : []);
  const rows = [];
  for (const [rn, raw] of Object.entries(object(selected.attributes.cars))) {
    const car = object(raw), identity = person(people, rn);
    const stops = unique(records(car.stops).map((stop, index) => {
      const lap = count(stop.lap), time = stamp(stop.timestamp);
      return { ...identity, id: `${rn}:${time ?? `lap-${lap ?? 'unknown'}-${index}`}`, status: statuses.get(rn) ?? null, stop_lap: lap,
        event_time: time, stop_time: seconds(stop.pit_stop_time), lane_time: seconds(stop.pit_lane_time),
        pit_delta: number(stop.pit_delta), pit_count: count(car.count), sourceOrder: index };
    }));
    stops.sort((a, b) => a.event_time && b.event_time ? a.event_time.localeCompare(b.event_time) || a.sourceOrder - b.sourceOrder : a.sourceOrder - b.sourceOrder);
    rows.push(...(module.options.content === 'latest_stop' ? stops.slice(-1) : stops));
  }
  return { ...selectRows(rows, module, focus), allRows: rows, source: selected, countKind: 'stops', context: context(hass, entry, selected) };
}

export function incidentsModel(hass, entry, module, focus = {}) {
  const summary = module.options.content === 'track_limits_summary';
  const selected = source(hass, entry, summary ? 'track_limits' : module.options.content), attrs = selected.attributes, people = roster(hass, entry);
  if (summary) {
    const allRows = Object.entries(object(attrs.by_driver)).filter(([, info]) => info && typeof info === 'object' && !Array.isArray(info)).map(([tla, info]) => ({
      ...person(people, key(info.racing_number), { tla }), track_limit_deletions: count(info.deletions),
      track_limit_warning: typeof info.warning === 'boolean' ? info.warning : null,
      track_limit_penalty: text(info.penalty), penalty_known: Object.hasOwn(info, 'penalty') && (info.penalty === null || typeof info.penalty === 'string'),
      event_time: records(info.violations).map(item => stamp(item.utc)).filter(Boolean).sort().at(-1) ?? null,
    }));
    const search = module.options.search.toLocaleLowerCase(), categories = module.options.categories;
    const filtered = allRows.filter(row => (!search || [row.driver, row.number, row.name, row.team, row.track_limit_penalty].some(value => value?.toLocaleLowerCase().includes(search)))
      && (!categories.length || categories.some(category => category === 'time_deleted' && row.track_limit_deletions > 0 || category === 'warning' && row.track_limit_warning === true || category === 'penalty' && Boolean(row.track_limit_penalty))));
    const sort = module.options.summary_sort;
    const selection = selectRows(filtered, { ...module, options: { ...module.options, sort, direction: sort === 'driver' ? 'asc' : 'desc' } }, focus);
    return { ...selection, filtered: selection.filtered || Boolean(search || categories.length), allRows, source: selected, summary: true,
      countKind: 'competitors', context: context(hass, entry, selected), trackLimits: true };
  }
  const events = [];
  if (module.options.content === 'track_limits') {
    for (const [tla, info] of Object.entries(object(attrs.by_driver))) for (const violation of records(object(info).violations)) {
      events.push({ ...violation, category: violation.type, drivers: [tla], racing_numbers: [key(info.racing_number)], location: key(violation.turn) || null });
    }
  } else for (const category of ['noted', 'under_investigation', 'no_further_action', 'penalties']) {
    for (const item of records(attrs[category])) events.push({ ...item, category: category === 'penalties' ? 'penalty' : category,
      drivers: category === 'penalties' ? [item.driver] : item.drivers, racing_numbers: category === 'penalties' ? [item.racing_number] : item.racing_numbers });
  }
  const rows = unique(events.map(item => {
    const numbers = array(item.racing_numbers).map(key).filter(Boolean), codes = array(item.drivers).map(key).filter(Boolean);
    const involved = [...new Set([...numbers.map((rn, index) => person(people, rn, { tla: codes[index] }).driver), ...codes])];
    const time = stamp(item.nfi_utc ?? item.utc), lap = count(item.lap), location = text(item.location), reason = text(item.reason), penalty = text(item.penalty);
    const id = JSON.stringify([item.category, [...numbers].sort(), [...codes].sort(), time, lap, location, reason, penalty]);
    return { id, incident_status: text(item.category), incident_drivers: involved.join(' / ') || null, event_time: time, incident_lap: lap,
      incident_location: location, incident_reason: reason, incident_penalty: penalty, after_race: item.after_race === true,
      decision_time: Boolean(item.nfi_utc), numbers, codes,
      teams: people.filter(person => numbers.includes(key(person.racing_number)) || codes.includes(person.tla)).map(person => person.team).filter(Boolean) };
  }));
  const driver = module.driver || focus.driver, team = module.team || focus.team, search = module.options.search.toLocaleLowerCase();
  const filtered = rows.filter(row => (!driver || row.numbers.includes(driver) || row.codes.includes(driver)) && (!team || row.teams.includes(team))
    && (!module.options.categories.length || module.options.categories.includes(row.incident_status))
    && (!search || [row.incident_drivers, row.incident_location, row.incident_reason, row.incident_penalty].some(value => value?.toLocaleLowerCase().includes(search))));
  filtered.sort((a, b) => {
    if (!a.event_time && b.event_time) return 1;
    if (!b.event_time && a.event_time) return -1;
    return (a.event_time ?? '').localeCompare(b.event_time ?? '') * (module.options.order === 'oldest' ? 1 : -1) || a.id.localeCompare(b.id);
  });
  return { rows: filtered.slice(0, module.options.rows), total: filtered.length, filtered: Boolean(driver || team || search || module.options.categories.length),
    allRows: rows, source: selected, countKind: 'events', context: context(hass, entry, selected), trackLimits: module.options.content === 'track_limits' };
}
