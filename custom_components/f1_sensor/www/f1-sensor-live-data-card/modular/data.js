const version = new URL(import.meta.url).searchParams.get('v');
const { seconds, number, positiveInteger, lapChange, safeImageUrl } = await import(`./semantics.js${version ? `?v=${encodeURIComponent(version)}` : ''}`);

const { sessionKind, timingFields, moduleFields, fieldDefinition } = await import(`./catalog.js${version ? `?v=${encodeURIComponent(version)}` : ''}`);

export const array = value => Array.isArray(value) ? value : value && typeof value === 'object' ? Object.values(value) : [];
const nonempty = value => typeof value === 'string' && value.trim() && !['unknown', 'unavailable', 'none', 'no_session'].includes(value.toLowerCase()) ? value.trim() : null;

export function source(hass, entry, key) {
  const entityId = entry?.entities?.[key];
  const state = entityId ? hass?.states?.[entityId] : null;
  const status = entry?.disabled_entities?.includes(key) ? 'disabled'
    : !entityId ? 'missing' : !state || state.state === 'unavailable' ? 'unavailable'
      : state.state === 'unknown' ? 'unknown' : 'available';
  return { key, entity_id: entityId ?? null, status, state: state?.state ?? null, attributes: state?.attributes ?? {}, updated_at: state?.last_updated ?? null };
}

// HA last_updated describes a state write, not a timing observation or receipt.
// Keep the timestamp kind with the value; age alone is not a freshness verdict.
export function modelTimestamp(model, now = Date.now()) {
  const context = model.context ?? {}, selected = model.source;
  const kind = context.updatedKind ?? (selected ? 'ha_state' : 'received');
  const raw = Object.hasOwn(context, 'updated') ? context.updated : selected?.updated_at;
  if (!raw && !selected && !context.updatedKind) return null;
  const valid = typeof raw === 'string' && /T.*(?:Z|[+-]\d{2}:\d{2})$/i.test(raw) && Number.isFinite(Date.parse(raw));
  const at = valid ? new Date(raw).toISOString() : null;
  const elapsed = at && Number.isFinite(now) ? (now - Date.parse(at)) / 1000 : null;
  return { kind, at, ageSeconds: elapsed !== null && elapsed >= 0 ? Math.floor(elapsed) : null, future: elapsed !== null && elapsed < 0 };
}

export function accentTeams(hass, entry) {
  const roster = source(hass, entry, 'driver_list');
  if (roster.status !== 'available') return [];
  const teams = new Map();
  for (const driver of array(roster.attributes.drivers)) {
    if (typeof driver?.team !== 'string' || !driver.team.trim()) continue;
    const name = driver.team.trim();
    if (!teams.has(name)) teams.set(name, new Set());
    if (/^#[0-9a-f]{6}$/i.test(driver.team_color)) teams.get(name).add(driver.team_color.toLowerCase());
  }
  return [...teams].sort(([a], [b]) => a.localeCompare(b)).map(([name, colors]) => ({ name, color: colors.size === 1 ? [...colors][0] : null }));
}

export function spoilerState(hass, entry, local = 'inherit') {
  if (local === 'hide') return 'protected';
  // Absence of this discovery capability on an old backend is not proof that
  // spoilers are disabled. The UI must explain that discovery needs refreshing.
  if (!entry || !Object.hasOwn(entry, 'global_entities')) return 'unknown';
  const entity = entry.global_entities?.no_spoiler_mode;
  if (!entity) return 'unknown';
  const state = hass?.states?.[entity]?.state;
  return state === 'on' ? 'protected' : state === 'off' ? 'clear' : 'unknown';
}

export function sessionContext(hass, entry) {
  const current = source(hass, entry, 'current_session'), status = source(hass, entry, 'session_status');
  const replay = source(hass, entry, 'replay_status');
  const attrs = current.attributes;
  const name = nonempty(current.state) ?? nonempty(attrs.resolved_label) ?? nonempty(attrs.last_label);
  const key = [entry?.entry_id, attrs.meeting_key, attrs.start, name].map(part => part ?? '').join(':');
  return { key, name, meeting: attrs.meeting_name ?? null, start: attrs.start ?? null, status: status.state, active: attrs.active === true || status.state === 'live', replay: replay.state, source: current };
}

export function sessionPhase(hass, entry) {
  const context = sessionContext(hass, entry), value = String(context.status ?? '').toLowerCase();
  if (context.active || ['live', 'started', 'green', 'red_flag', 'red flag', 'suspended', 'paused'].includes(value)) return 'active';
  if (['finished', 'finalised', 'ended', 'complete', 'completed'].includes(value)) return 'finished';
  if (['inactive', 'no_session', 'pre', 'before', 'scheduled'].includes(value)) return 'before';
  return 'unknown';
}

const sameIdentity = (selection, identity) => Number(identity.season) === selection.season
  && String(identity.meeting_key ?? '') === selection.meeting_key
  && String(identity.session_key ?? '') === selection.session_key;

export function selectionState(hass, entry, selection) {
  const phase = sessionPhase(hass, entry);
  if (selection.mode === 'follow') {
    const replay = source(hass, entry, 'replay_status'), replayActive = ['selected', 'loading', 'ready', 'seeking', 'playing', 'paused'].includes(String(replay.state).toLowerCase());
    if (selection.source === 'live' && replayActive) return { available: false, phase, reason: 'source_mismatch', selection };
    if (selection.source === 'replay' && !replayActive) return { available: false, phase: 'unknown', reason: 'replay_not_loaded', selection };
    return { available: true, phase, selection };
  }
  if (selection.source === 'archive') return { available: true, phase: 'finished', selection, archive: true };
  if (selection.source === 'live') {
    const current = source(hass, entry, 'current_session');
    const identity = { season: current.attributes.season, meeting_key: current.attributes.meeting_key, session_key: current.attributes.session_key };
    return { available: sameIdentity(selection, identity), phase, reason: sameIdentity(selection, identity) ? null : 'pinned_session_unavailable', selection, identity };
  }
  const replay = source(hass, entry, 'replay_status'), player = source(hass, entry, 'replay_player');
  const attrs = { ...replay.attributes, ...player.attributes };
  const identity = { season: attrs.selected_session_year ?? attrs.selected_year, meeting_key: attrs.selected_meeting_key, session_key: attrs.selected_session_key };
  const available = sameIdentity(selection, identity) && ['selected', 'loading', 'ready', 'seeking', 'playing', 'paused'].includes(String(replay.state ?? player.state).toLowerCase());
  return { available, phase: available ? phase : 'unknown', reason: available ? null : 'pinned_replay_unavailable', selection, identity };
}

export function sessionClock(hass, entry, key, context = sessionContext(hass, entry)) {
  const selected = source(hass, entry, key), attrs = selected.attributes;
  const raw = number(attrs.value_seconds), phase = nonempty(attrs.clock_phase), quality = nonempty(attrs.source_quality);
  const part = positiveInteger(attrs.session_part), currentPart = positiveInteger(source(hass, entry, 'driver_positions').attributes.current_qualifying_part);
  const name = nonempty(attrs.session_name), comparable = (!name || !context.name || name === context.name)
    && (!['qualifying', 'sprint_qualifying'].includes(sessionKind(context.name)) || !part || !currentPart || part === currentPart);
  const cap = key === 'race_time_to_three_hour_limit';
  const valid = selected.status === 'available' && hass?.connection?.connected !== false && comparable && (!cap || sessionKind(context.name) === 'race') && phase !== 'idle' && quality !== 'unavailable' && quality !== null && raw !== null && raw >= 0 && Number.isInteger(raw);
  const value = valid ? `${Math.floor(raw / 3600)}:${String(Math.floor(raw % 3600 / 60)).padStart(2, '0')}:${String(raw % 60).padStart(2, '0')}` : null;
  return { value, seconds: valid ? raw : null, phase, quality, part, cap, notApplicable: cap && sessionKind(context.name) !== 'race', replay: context.replay, source: selected, contextMismatch: !comparable };
}

export function lapHistory(driver) {
  const completed = number(driver.completed_laps);
  return Object.entries(driver.laps ?? {}).map(([lap, time]) => ({ lap: positiveInteger(lap), time: seconds(time) }))
    .filter(item => item.lap !== null && item.time !== null && (completed === null || item.lap <= completed))
    .sort((a, b) => a.lap - b.lap);
}

export function timingRows(hass, entry, context, sectors, module, focus = {}) {
  const positions = source(hass, entry, 'driver_positions');
  const tyres = source(hass, entry, 'current_tyres');
  const drivers = source(hass, entry, 'driver_list');
  const identity = new Map((drivers.status === 'available' ? array(drivers.attributes.drivers) : []).filter(item => item && typeof item === 'object').map(item => [String(item.racing_number), item]));
  const tyreByDriver = new Map((tyres.status === 'available' ? array(tyres.attributes.drivers) : []).filter(item => item && typeof item === 'object').map(item => [String(item.racing_number), item]));
  const chosenDriver = module.driver || focus.driver, chosenTeam = module.team || focus.team;
  const kind = sessionKind(context.name), qualifying = ['qualifying', 'sprint_qualifying'].includes(kind);
  const part = positiveInteger(positions.attributes.current_qualifying_part);
  const rawDrivers = Array.isArray(positions.attributes.drivers) ? positions.attributes.drivers
    : Object.entries(positions.attributes.drivers ?? {}).map(([rn, driver]) => ({ racing_number: rn, ...driver }));
  const rows = rawDrivers.filter(driver => driver && typeof driver === 'object').map(driver => {
    const id = String(driver.racing_number ?? driver.tla ?? '');
    const person = identity.get(id) ?? {};
    const tyre = tyreByDriver.get(id) ?? {};
    const laps = lapHistory(driver), last = laps.at(-1), previous = laps.at(-2);
    // An explicitly null official best is a correction, not permission to revive
    // an invalidated old best from the card's observed lap history.
    const official = Object.hasOwn(driver, 'best_lap_time');
    const best = official ? { time: seconds(driver.best_lap_time), lap: positiveInteger(driver.best_lap_lap) }
      : laps.reduce((result, item) => !result || item.time < result.time ? item : result, null);
    const selectedSectors = sectors.select(context.key, driver, module.options.sectors);
    const bestSectors = [1, 2, 3].map(n => {
      const detail = driver.sectors?.personal_best?.[`sector_${n}`];
      const time = seconds(detail ? detail.time : driver[`best_sector_${n}`]);
      return { time, lap: positiveInteger(detail?.lap ?? driver[`best_sector_${n}_lap`]),
        session_part: positiveInteger(detail?.session_part ?? driver[`best_sector_${n}_session_part`]),
        personal_fastest: time !== null, overall_fastest: detail?.overall_fastest === true, source: 'personal_best',
        deleted: detail?.deleted === true, invalid: detail?.invalid === true };
    });
    const comparable = bestSectors.every(item => item.time !== null && !item.deleted && !item.invalid && (qualifying ? part && item.session_part === part : item.session_part === null));
    const qualifyingTimes = Object.fromEntries([1, 2, 3].flatMap(n => [[`q${n}_time`, {
      time: qualifying ? seconds(driver[`q${n}_time`]) : null, part: n, sprint: kind === 'sprint_qualifying',
      eliminated: qualifying && driver[`q${n}_knocked_out`] === true,
    }], [`q${n}_position`, qualifying ? positiveInteger(driver[`q${n}_position`]) : null]]));
    return {
      id, driver: person.tla ?? driver.tla ?? id, name: person.full_name ?? person.name ?? driver.full_name ?? driver.name ?? driver.tla ?? id,
      team: person.team ?? driver.team ?? tyre.team ?? null, team_color: person.team_color ?? driver.team_color ?? tyre.team_color ?? null,
      position: positiveInteger(driver.current_position), gap: nonempty(driver.gap_to_leader), interval: nonempty(driver.interval_to_position_ahead),
      last_lap: last ? { ...last, source: 'completed_lap', previous_lap: true } : { time: null },
      best_lap: { time: best?.time ?? null, lap: best?.lap ?? null, personal_fastest: best?.time !== null && best?.time !== undefined, overall_fastest: driver.fastest_lap === true },
      lap_delta: last && previous && last.lap === previous.lap + 1 ? lapChange(last.time, previous.time, last.lap, previous.lap) : null,
      sector_1: selectedSectors[0], sector_2: selectedSectors[1], sector_3: selectedSectors[2],
      best_sector_1: bestSectors[0], best_sector_2: bestSectors[1], best_sector_3: bestSectors[2],
      theoretical_lap: comparable ? bestSectors.reduce((sum, item) => sum + item.time, 0) : null, ...qualifyingTimes,
      laps: number(driver.completed_laps), history: module.options.history ? laps.slice(-module.options.history).reverse() : [],
      tyre: nonempty(tyre.compound_short ?? tyre.compound), tyre_age: number(tyre.stint_laps),
      status: driver.retired === true ? 'retired' : driver.in_pit === true ? 'in_pit' : driver.pit_out === true ? 'pit_out' : driver.stopped === true ? 'stopped' : nonempty(driver.status),
      updated_at: positions.updated_at,
    };
  }).filter(row => row.id && (!chosenDriver || row.id === chosenDriver || row.driver === chosenDriver)
    && (!chosenTeam || row.team === chosenTeam));
  const partTimes = qualifying && part ? rows.map(row => row[`q${part}_time`]?.time).filter(value => value !== null && value !== undefined) : [];
  const fastestPartTime = partTimes.length ? Math.min(...partTimes) : null;
  for (const row of rows) {
    const currentPartTime = part ? row[`q${part}_time`]?.time : null;
    row.qualifying_gap = fastestPartTime !== null && currentPartTime !== null && currentPartTime !== undefined ? currentPartTime - fastestPartTime : null;
  }
  const sort = module.options.sort;
  rows.sort((a, b) => {
    const x = sort === 'best_lap' ? a.best_lap.time : a[sort];
    const y = sort === 'best_lap' ? b.best_lap.time : b[sort];
    if (x === null && y !== null) return 1;
    if (y === null && x !== null) return -1;
    const order = typeof x === 'string' ? x.localeCompare(String(y)) : (x ?? 0) - (y ?? 0);
    return order * (module.options.direction === 'desc' ? -1 : 1) || a.id.localeCompare(b.id, undefined, { numeric: true });
  });
  return { rows: rows.slice(0, module.options.rows), total: rows.length, source: positions, filtered: Boolean(chosenDriver || chosenTeam), fields: timingFields(module, context.name), sessionKind: kind, currentPart: part };
}

export const SESSION_FIELDS = [
  ['practice_1', 'first_practice', 'FirstPractice', 'Practice 1', 'Träning 1'],
  ['practice_2', 'second_practice', 'SecondPractice', 'Practice 2', 'Träning 2'],
  ['practice_3', 'third_practice', 'ThirdPractice', 'Practice 3', 'Träning 3'],
  ['sprint_qualifying', 'sprint_qualifying', 'SprintQualifying', 'Sprint qualifying', 'Sprintkval'],
  ['sprint', 'sprint', 'Sprint', 'Sprint', 'Sprint'],
  ['qualifying', 'qualifying', 'Qualifying', 'Qualifying', 'Kval'],
  ['race', 'race', null, 'Race', 'Race'],
];
const publishedDate = value => {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value ? value : null;
};
function circuitDay(timezone, now) {
  if (timezone) try {
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now).map(part => [part.type, part.value]));
    return `${parts.year}-${parts.month}-${parts.day}`;
  } catch { /* Unknown zone: callers use conservative worldwide bounds. */ }
  return null;
}
function dateHasPassed(date, timezone, now) {
  const today = circuitDay(timezone, now);
  return today ? date < today : now >= Date.parse(`${date}T00:00:00Z`) + 36 * 3600_000;
}
export function scheduleRows(hass, entry, module, now = Date.now()) {
  const calendar = source(hass, entry, module.options.range === 'season' ? 'current_season' : 'next_race');
  const races = module.options.range === 'season' ? array(calendar.attributes.races) : [calendar.attributes];
  const rows = [];
  for (const race of races) for (const [id, prefix, jolpica, en, sv] of SESSION_FIELDS) {
    if (!module.options.sessions.includes(id)) continue;
    const block = jolpica ? race[jolpica] : race;
    const candidate = race[`${prefix}_start_utc`] ?? race[`${prefix}_start`] ?? (block?.date && block?.time ? `${block.date}T${block.time}` : null);
    const start = typeof candidate === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}.*(?:Z|[+-]\d{2}:\d{2})$/.test(candidate)
      && publishedDate(candidate.slice(0, 10)) && Number.isFinite(Date.parse(candidate)) ? candidate : null;
    const date = publishedDate(block?.date) ?? publishedDate(race[`${prefix}_date`]) ?? publishedDate(typeof candidate === 'string' ? candidate.slice(0, 10) : null);
    if (!start && !date) continue;
    rows.push({ id: `${race.season ?? ''}:${race.round ?? ''}:${id}`, session: id, label: { en, sv }, meeting: race.race_name ?? race.raceName ?? null,
      start, date, timezone: race.circuit_timezone ?? null, country: race.circuit_country ?? race.Circuit?.Location?.country ?? null,
      flag: safeImageUrl(race.country_flag_url), round: race.round ?? null, circuit: race.circuit_name ?? race.Circuit?.circuitName ?? null,
      location: [race.circuit_locality ?? race.Circuit?.Location?.locality, race.circuit_country ?? race.Circuit?.Location?.country].filter(Boolean).join(', ') });
  }
  const sortTime = row => Date.parse(row.start ?? `${row.date}T00:00:00Z`);
  rows.sort((a, b) => sortTime(a) - sortTime(b));
  const marked = rows.map(row => ({ ...row, past: row.start ? Date.parse(row.start) < now : dateHasPassed(row.date, row.timezone, now), next: false }));
  const next = marked.find(row => row.start && Date.parse(row.start) >= now);
  // An untimed event may start earlier than a confirmed time; do not guess its order.
  if (next && !marked.some(row => {
    if (row.start || row.past) return false;
    const dayAtNext = circuitDay(row.timezone, Date.parse(next.start));
    return dayAtNext ? row.date <= dayAtNext : Date.parse(`${row.date}T00:00:00Z`) - 14 * 3600_000 <= Date.parse(next.start);
  })) next.next = true;
  return { rows: marked.filter(row => module.options.past !== 'hide' || !row.past), hiddenRows: module.options.past === 'hide' ? marked.filter(row => row.past).length : 0, source: calendar };
}

export function replayModel(hass, entry) {
  const status = source(hass, entry, 'replay_status'), player = source(hass, entry, 'replay_player');
  const state = ['idle', 'selected', 'loading', 'ready', 'seeking', 'playing', 'paused'].includes(status.state) ? status.state : 'unknown';
  const selectors = Object.fromEntries([['year', 'replay_year_select'], ['session', 'replay_session_select'], ['reference', 'replay_start_reference']].map(([id, key]) => {
    const selected = source(hass, entry, key);
    return [id, { ...selected, options: array(selected.attributes.options).filter(value => typeof value === 'string' && value.trim()) }];
  }));
  const online = hass?.connection?.connected !== false && status.status === 'available';
  const canSelect = online && ['idle', 'selected'].includes(state);
  const selectedSession = nonempty(status.attributes.selected_session), sessionId = nonempty(player.attributes.selected_session_id);
  const coherent = player.status === 'available' && player.attributes.replay_state === state
    && Boolean(sessionId && selectedSession && player.attributes.selected_session === selectedSession);
  const loaded = online && coherent && ['ready', 'playing', 'paused'].includes(state);
  const duration = number(player.attributes.media_duration), position = number(player.attributes.media_position);
  const validProgress = loaded && duration !== null && duration > 0 && position !== null && position >= 0 && position <= duration;
  const available = (key, domain) => {
    const id = entry?.entities?.[key], entity = id ? hass?.states?.[id] : null;
    return typeof id === 'string' && id.startsWith(`${domain}.`) && entity && entity.state !== 'unavailable' && !entry?.disabled_entities?.includes(key);
  };
  const allowed = {
    year: canSelect && available('replay_year_select', 'select'),
    session: canSelect && available('replay_session_select', 'select') && number(status.attributes.sessions_available) > 0,
    reference: canSelect && available('replay_start_reference', 'select'),
    refresh: canSelect && available('replay_refresh', 'button'),
    load: online && state === 'selected' && Boolean(selectedSession) && available('replay_load', 'button'),
    play: loaded && ['ready', 'paused'].includes(state) && available('replay_player', 'media_player'),
    pause: loaded && state === 'playing' && available('replay_player', 'media_player'),
    stop: online && ['selected', 'ready', 'playing', 'paused'].includes(state) && available('replay_player', 'media_player'),
    seek: validProgress && available('replay_player', 'media_player'),
  };
  if (!online && status.status === 'available') status.status = 'unavailable';
  return { source: status, playerStatus: player.status, replayState: state, selectedSession, sessionId, selectors, allowed, online, loaded, canSelect,
    duration: validProgress ? duration : null, position: validProgress ? position : null,
    download: state === 'loading' ? number(status.attributes.download_progress) : null,
    downloadError: Boolean(status.attributes.download_error), indexError: Boolean(status.attributes.index_error), indexStatus: status.attributes.index_status,
    scope: entry?.title ?? entry?.entry_id ?? '',
    controlContext: JSON.stringify([entry?.entry_id, state, selectedSession, sessionId, selectors.year.state, selectors.session.state, selectors.reference.state]),
  };
}

export function replayCommand(hass, entry, module, action, value, expectedContext) {
  const model = replayModel(hass, entry);
  if (expectedContext !== model.controlContext || module?.type !== 'replay' || !module.enabled) return null;
  const transport = ['play', 'pause', 'stop', 'seek'].includes(action);
  if (!module.fields.includes(transport ? 'replay_transport' : 'replay_selection') || !model.allowed[action]) return null;
  if (['year', 'session', 'reference'].includes(action)) {
    const selected = model.selectors[action];
    if (typeof value !== 'string' || !selected.options.includes(value)) return null;
    return { domain: 'select', service: 'select_option', data: { entity_id: selected.entity_id, option: value } };
  }
  if (action === 'load' || action === 'refresh') return { domain: 'button', service: 'press', data: { entity_id: entry.entities[`replay_${action}`] } };
  if (action === 'seek') {
    const position = number(value);
    if (position === null || position < 0 || position > model.duration) return null;
    return { domain: 'media_player', service: 'media_seek', data: { entity_id: entry.entities.replay_player, seek_position: Math.floor(position) } };
  }
  if (['play', 'pause', 'stop'].includes(action)) return { domain: 'media_player', service: `media_${action}`, data: { entity_id: entry.entities.replay_player } };
  return null;
}

export function lapChartModel(hass, entry, module, focus = {}) {
  const selected = source(hass, entry, 'driver_positions'), identities = source(hass, entry, 'driver_list');
  const people = identities.status === 'available' ? array(identities.attributes.drivers).filter(item => item && typeof item === 'object') : [];
  const rawDrivers = Array.isArray(selected.attributes.drivers) ? selected.attributes.drivers
    : Object.entries(selected.attributes.drivers ?? {}).map(([rn, driver]) => ({ racing_number: rn, ...driver }));
  const seen = new Set();
  const allSeries = rawDrivers.filter(item => item && typeof item === 'object').map(raw => {
    const id = String(raw.racing_number ?? raw.tla ?? ''), person = people.find(item => String(item.racing_number) === id) ?? {};
    return { id, driver: nonempty(person.tla ?? raw.tla) ?? id, name: nonempty(person.full_name ?? person.name ?? raw.full_name ?? raw.name ?? raw.tla) ?? id,
      team: nonempty(person.team ?? raw.team), position: positiveInteger(raw.current_position), history: lapHistory(raw).filter(lap => lap.lap <= 500) };
  }).filter(item => item.id && !seen.has(item.id) && seen.add(item.id)).sort((a, b) => (a.position ?? Infinity) - (b.position ?? Infinity) || a.id.localeCompare(b.id, undefined, { numeric: true }));
  const driver = module.driver || focus.driver, team = module.team || focus.team;
  const chosen = allSeries.filter(item => (!driver || item.id === driver || item.driver === driver) && (!team || item.team === team)
    && (!module.options.selected.length || module.options.selected.includes(item.id) || module.options.selected.includes(item.driver))).slice(0, module.options.series_limit);
  const observed = chosen.flatMap(item => item.history.map(lap => lap.lap));
  const first = module.options.start_lap || (observed.length ? Math.min(...observed) : 0);
  const last = module.options.end_lap || (observed.length ? Math.max(...observed) : 0);
  const rounds = first > 0 && last >= first ? Array.from({ length: last - first + 1 }, (_, index) => ({ id: first + index })) : [];
  const series = chosen.map(item => {
    const times = new Map(item.history.map(lap => [lap.lap, lap.time]));
    return { ...item, values: rounds.map(({ id }) => ({ round: id, value: module.options.metric === 'lap_change'
      ? times.has(id) && times.has(id - 1) ? times.get(id) - times.get(id - 1) : null : times.get(id) ?? null })) };
  });
  const context = sessionContext(hass, entry);
  if (hass?.connection?.connected === false && selected.status === 'available') selected.status = 'unavailable';
  return { source: selected, series, allSeries, rounds, metric: module.options.metric, axisKind: 'lap', total: allSeries.length,
    invalidRange: first > last, filtered: Boolean(driver || team || module.options.selected.length),
    context: { meeting: context.meeting, session: context.name, source: 'TimingData', updated: selected.updated_at, updatedKind: 'ha_state' } };
}

const WEATHER_SPEED_RATIOS = { 'm/s': 1, 'km/h': 3.6, mph: 2.2369362920544025, kn: 1.9438444924406046, 'ft/s': 3.280839895013124, 'in/s': 39.37007874015748, 'm/min': 60, 'mm/s': 1000 };
function weatherMeasurement(value, unit, target, temperature) {
  const aliases = { celsius: '°C', fahrenheit: '°F', kelvin: 'K' };
  unit = Object.hasOwn(aliases, unit) ? aliases[unit] : unit; target = Object.hasOwn(aliases, target) ? aliases[target] : target;
  if (unit === target) return { value, unit };
  if (temperature) {
    const known = ['°C', '°F', 'K'];
    if (!known.includes(unit) || !known.includes(target)) return { value, unit };
    if (value !== null) {
      const celsius = unit === '°F' ? (value - 32) / 1.8 : unit === 'K' ? value - 273.15 : value;
      value = target === '°F' ? celsius * 1.8 + 32 : target === 'K' ? celsius + 273.15 : celsius;
    }
  } else {
    const from = Object.hasOwn(WEATHER_SPEED_RATIOS, unit) ? WEATHER_SPEED_RATIOS[unit] : null;
    const to = Object.hasOwn(WEATHER_SPEED_RATIOS, target) ? WEATHER_SPEED_RATIOS[target] : null;
    if ((!from && unit !== 'Beaufort') || (!to && target !== 'Beaufort')) return { value, unit };
    if (value !== null) {
      const meters = unit === 'Beaufort' ? 0.836 * value ** 1.5 : value / from;
      value = target === 'Beaufort' ? Math.round((meters / 0.836) ** (2 / 3)) : meters * to;
    }
  }
  return { value, unit: target };
}

export function resolveWeatherModule(hass, entry, module) {
  if (module.type !== 'weather' || module.options?.content !== 'automatic_conditions') return module;
  const track = { ...module, options: { ...module.options, content: 'track_conditions' } };
  const status = source(hass, entry, 'session_status');
  const observations = weatherValues(hass, entry, track);
  const useTrack = status.status === 'available' && ['pre', 'live', 'suspended', 'break'].includes(status.state)
    && source(hass, entry, 'track_weather').status === 'available' && Object.values(observations.values).some(item => item.value !== null);
  return { ...module, weatherAutomatic: true, options: { ...module.options, content: useTrack ? 'track_conditions' : 'current_conditions' } };
}
export function weatherValues(hass, entry, module = { type: 'weather', options: {} }) {
  const automatic = module.options?.content === 'automatic_conditions' || module.weatherAutomatic === true;
  module = resolveWeatherModule(hass, entry, module);
  const content = module.options?.content ?? 'weather_overview', track = content === 'track_conditions';
  const weather = source(hass, entry, track ? 'track_weather' : 'weather'), attrs = weather.attributes;
  if (hass?.connection?.connected === false && weather.status === 'available') weather.status = 'unavailable';
  const available = moduleFields(module);
  const fields = automatic ? moduleFields({ ...module, options: { ...module.options, content: 'automatic_conditions' } }) : available;
  const values = Object.fromEntries(fields.map(id => {
    const field = fieldDefinition(module, id), raw = available.includes(id) ? attrs[field.path] : undefined;
    let value = number(raw), unit = attrs[`${field.path}_unit`] ?? field.unit;
    if (['temperature', 'track_temperature'].includes(id)) {
      const target = ['°C', '°F', 'K'].includes(attrs.unit_of_measurement) ? attrs.unit_of_measurement : hass?.config?.unit_system?.temperature;
      ({ value, unit } = weatherMeasurement(value, unit, target, true));
    }
    if (id === 'wind_direction') { unit = '°'; value = value !== null && value >= 0 && value <= 360 ? value % 360 : null; }
    if (['humidity', 'cloud_cover', 'rain_probability'].includes(id) && (value < 0 || value > 100)) value = null;
    if (['wind', 'wind_gusts', 'precipitation', 'visibility', 'pressure'].includes(id) && value < 0) value = null;
    if (['wind', 'wind_gusts'].includes(id)) ({ value, unit } = weatherMeasurement(value, unit, hass?.config?.unit_system?.wind_speed, false));
    // F1 WeatherData Rainfall is an indicator, despite the legacy mm unit.
    if (id === 'rainfall') { value = raw === true || raw === 1 || raw === '1' ? true : raw === false || raw === 0 || raw === '0' ? false : null; unit = null; }
    if (id === 'weather_condition') value = Number.isInteger(value) ? value : null;
    return [id, { value, unit, type: field.type, estimated: field.estimated === true, night: id === 'weather_condition' && value === 0 && attrs[field.estimated ? 'race_weather_icon' : 'icon'] === 'mdi:weather-night' }];
  }));
  // The exposed entities have no observation timestamp. Their HA update time
  // is a receipt time, including when the backing data came from replay.
  const session = track ? sessionContext(hass, entry) : null;
  return { source: weather, values, track, automatic, forecast: content === 'race_forecast', mixed: content === 'weather_overview',
    context: { meeting: track ? session?.source.status === 'available' ? session.meeting : null : nonempty(attrs.race_name) ?? nonempty(attrs.circuit_name),
      session: track && session?.source.status === 'available' ? session.name : null,
      source: track ? 'WeatherData' : 'Open-Meteo', updated: weather.updated_at, updatedKind: 'ha_state' },
    replay: track && ![null, 'idle', 'unavailable', 'unknown'].includes(session?.replay),
  };
}

export function normalizeEvent(item) {
  if (!item || typeof item !== 'object') return null;
  const message = nonempty(item.message ?? item.Message ?? item.Text);
  if (!message) return null;
  const rawUtc = item.utc ?? item.Utc ?? null;
  const parsedUtc = rawUtc ? Date.parse(rawUtc) : NaN;
  const utc = Number.isFinite(parsedUtc) ? new Date(parsedUtc).toISOString() : rawUtc;
  const category = item.category ?? item.Category ?? 'Other', flag = item.flag ?? item.Flag ?? null;
  // The sensor and log can use different IDs for the same event. Source identity
  // avoids double rendering when a snapshot overlaps a subscribed event.
  const identity = [utc ?? item.received_at ?? item.event_id ?? item.id ?? item.sequence ?? '', category, flag, item.car_number ?? item.CarNumber ?? '', message].join('|');
  return { id: identity, event_id: item.event_id ?? identity, message, utc, category, flag,
    car_number: String(item.car_number ?? item.CarNumber ?? ''), sequence: number(item.sequence), received_at: item.received_at ?? null };
}
export function filterRaceControl(rows, hass, entry, module, focus = {}) {
  const selected = String(module.driver || focus.driver || ''), roster = source(hass, entry, 'driver_list');
  const aliases = new Set(selected ? [selected] : []);
  if (selected && roster.status === 'available') {
    const person = array(roster.attributes.drivers).find(item => item && [String(item.racing_number ?? ''), item.tla].includes(selected));
    if (person) for (const value of [person.racing_number, person.tla]) if (value != null) aliases.add(String(value));
  }
  const search = module.options.search.toLocaleLowerCase();
  const filtered = rows.filter(row => (!selected || (row.car_number ? aliases.has(row.car_number) : module.options.global_messages !== 'hide'))
    && (!search || row.message.toLocaleLowerCase().includes(search)) && (!module.options.categories.length || module.options.categories.includes(row.category))
    && (!module.options.hide_blue_flags || String(row.flag ?? '').toUpperCase() !== 'BLUE' && !(!row.flag && /(?:waved )?blue flag/i.test(row.message)))
    && (!module.options.hide_track_limits || !row.message.toUpperCase().includes('TRACK LIMITS')));
  if (module.options.presentation === 'latest_message') return filtered.slice(0, 1);
  if (module.options.order === 'oldest') filtered.reverse();
  return filtered.slice(0, module.options.limit);
}

export function mergeEvents(...collections) {
  const items = new Map();
  for (const collection of collections) for (const raw of collection ?? []) {
    const item = normalizeEvent(raw); if (item) items.set(item.id, item);
  }
  return [...items.values()].sort((a, b) => (Date.parse(b.utc ?? b.received_at) || 0) - (Date.parse(a.utc ?? a.received_at) || 0) || (b.sequence ?? 0) - (a.sequence ?? 0)).slice(0, 500);
}

// Values and command targets come from registry discovery, never default IDs.
export function viewingModel(hass, entry, localSpoilers = 'inherit') {
  const delay = source(hass, entry, 'live_delay_number'), calibration = source(hass, entry, 'delay_calibration_switch');
  const replay = source(hass, entry, 'replay_status');
  const online = Boolean(hass?.connection) && hass.connection.connected !== false;
  const seconds = number(delay.state), min = number(delay.attributes.min), max = number(delay.attributes.max), step = number(delay.attributes.step);
  const valid = delay.status === 'available' && delay.entity_id?.startsWith('number.') && seconds !== null
    && min !== null && max !== null && step !== null && min >= 0 && max >= min && step > 0 && seconds >= min && seconds <= max;
  const replayKnown = replay.status === 'available' && ['idle', 'selected', 'loading', 'ready', 'playing', 'paused', 'seeking'].includes(replay.state);
  const replayActive = replayKnown && !['idle', 'selected'].includes(replay.state);
  const calibrating = calibration.status === 'available' && calibration.state === 'on';
  const calibrationKnown = calibration.status === 'available' && ['on', 'off'].includes(calibration.state);
  const protection = spoilerState(hass, entry), spoilerId = entry?.global_entities?.no_spoiler_mode;
  const changed = id => hass?.states?.[id]?.last_changed ?? null;
  return {
    scope: entry?.title ?? entry?.entry_id ?? '', entryId: entry?.entry_id ?? '', online, replayActive,
    calibration: calibrationModel(hass, entry, { online, replay, protection, localSpoilers }),
    delay: { seconds: valid ? seconds : null, min, max, step, entityId: delay.entity_id,
      reason: !online ? 'offline' : !valid ? 'missing' : replayActive ? 'replay' : !replayKnown ? 'unknown_replay' : calibrating ? 'calibrating' : !calibrationKnown ? 'unknown_calibration' : null,
      context: JSON.stringify([entry?.entry_id, delay.entity_id, delay.status, seconds, min, max, step, changed(delay.entity_id), replay.status, replay.state, calibration.status, calibration.state]),
    },
    spoilers: { protection, entityId: spoilerId,
      available: online && typeof spoilerId === 'string' && spoilerId.startsWith('switch.') && protection !== 'unknown',
      context: JSON.stringify([entry?.entry_id, spoilerId, protection, changed(spoilerId)]),
    },
  };
}

export function viewingCommand(hass, entry, action, value, expectedContext, localSpoilers = 'inherit') {
  const model = viewingModel(hass, entry, localSpoilers);
  if (!model.online || !entry) return null;
  if (action === 'delay') {
    const delay = model.delay, seconds = number(value);
    if (expectedContext !== delay.context || delay.reason || seconds === null || seconds === delay.seconds || seconds < delay.min || seconds > delay.max) return null;
    const steps = (seconds - delay.min) / delay.step;
    if (Math.abs(steps - Math.round(steps)) > 1e-7) return null;
    return { domain: 'number', service: 'set_value', data: { entity_id: delay.entityId, value: seconds } };
  }
  if (typeof action === 'string' && action.startsWith('calibration_')) {
    const kind = action.slice('calibration_'.length), calibration = model.calibration;
    if (expectedContext !== calibration.context || !calibration.allowed[kind]) return null;
    if (kind === 'reference') {
      if (!calibration.reference.options.includes(value) || value === calibration.reference.option) return null;
      return { domain: 'select', service: 'select_option', data: { entity_id: calibration.reference.entityId, option: value } };
    }
    if (kind === 'match') return { domain: 'button', service: 'press', data: { entity_id: calibration.matchId } };
    if (['start', 'cancel'].includes(kind)) return { domain: 'switch', service: kind === 'start' ? 'turn_on' : 'turn_off', data: { entity_id: calibration.switchId } };
    return null;
  }
  const spoilers = model.spoilers;
  if (!spoilers.available || expectedContext !== spoilers.context) return null;
  if (action === 'protect' && spoilers.protection === 'clear') return { domain: 'switch', service: 'turn_on', data: { entity_id: spoilers.entityId } };
  if (action === 'reveal' && spoilers.protection === 'protected') return { domain: 'switch', service: 'turn_off', data: { entity_id: spoilers.entityId } };
  return null;
}


export const CALIBRATION_REFERENCES = { 'Session live': 'session_live', 'Lap sync (race/sprint)': 'lap_sync' };
function calibrationModel(hass, entry, { online, replay, protection, localSpoilers }) {
  const control = source(hass, entry, 'delay_calibration_switch'), reference = source(hass, entry, 'live_delay_reference');
  const match = source(hass, entry, 'delay_calibration_match'), delay = source(hass, entry, 'live_delay_number');
  const attrs = control.attributes, session = sessionContext(hass, entry);
  const switchAvailable = control.status === 'available' && control.entity_id?.startsWith('switch.');
  const coherent = switchAvailable && (attrs.mode === 'idle' && control.state === 'off' || ['waiting', 'running'].includes(attrs.mode) && control.state === 'on');
  const mode = coherent ? attrs.mode : 'unknown';
  const options = [...new Set(array(reference.attributes.options).filter(option => Object.hasOwn(CALIBRATION_REFERENCES, option)))];
  const selected = options.includes(reference.state) ? reference.state : '', referenceKind = CALIBRATION_REFERENCES[selected] ?? null;
  const referenceAvailable = reference.status === 'available' && reference.entity_id?.startsWith('select.');
  const referenceMatches = referenceAvailable && referenceKind && attrs.reference === referenceKind;
  const replayIdle = replay.status === 'available' && replay.state === 'idle';
  const lapSession = session.source.status === 'available' && session.active && ['race', 'sprint'].includes(sessionKind(session.name));
  const detailsHidden = protection !== 'clear' || localSpoilers === 'hide';
  const elapsed = number(attrs.elapsed), recordedLap = number(attrs.recorded_lap);
  const validStart = typeof attrs.started_at === 'string' && Number.isFinite(Date.parse(attrs.started_at));
  const matchAvailable = ['available', 'unknown'].includes(match.status) && match.entity_id?.startsWith('button.') && Boolean(hass?.states?.[match.entity_id]);
  const reason = !online ? 'offline' : !coherent ? 'missing' : !replayIdle ? 'replay' : protection !== 'clear' ? 'protected'
    : !referenceMatches ? 'reference' : referenceKind === 'lap_sync' && !lapSession && mode === 'idle' ? 'lap_session' : null;
  const outcome = ['completed', 'cancelled', 'timeout', 'session_ended', 'replay', 'unsupported_session'].includes(attrs.idle_reason) && mode === 'idle' ? attrs.idle_reason : null;
  const last = attrs.last_result;
  const lastResult = !detailsHidden && last && Number.isInteger(last.seconds) && last.seconds >= 0 && last.seconds <= 300 && typeof last.completed_at === 'string' && Number.isFinite(Date.parse(last.completed_at)) ? { seconds: last.seconds, completedAt: last.completed_at } : null;
  return { mode, outcome, reason, detailsHidden, switchId: control.entity_id, matchId: match.entity_id,
    elapsed: !detailsHidden && mode === 'running' && elapsed !== null && elapsed >= 0 ? elapsed : null,
    recordedLap: !detailsHidden && mode === 'running' && referenceKind === 'lap_sync' && Number.isInteger(recordedLap) && recordedLap >= 0 ? recordedLap : null,
    reference: { entityId: reference.entity_id, option: selected, kind: referenceKind, options }, lastResult,
    allowed: {
      reference: online && mode === 'idle' && replayIdle && referenceAvailable && options.length > 0,
      start: mode === 'idle' && reason === null,
      cancel: online && switchAvailable && control.state === 'on',
      match: mode === 'running' && reason === null && !detailsHidden && validStart && elapsed !== null && elapsed >= 0 && matchAvailable && (referenceKind !== 'lap_sync' || Number.isInteger(recordedLap) && recordedLap >= 0),
    },
    // Elapsed time and received timestamps intentionally do not invalidate a
    // click each second. Mode, reference and run identity do invalidate it.
    context: JSON.stringify([entry?.entry_id, control.entity_id, control.status, control.state, attrs.mode, attrs.reference, attrs.idle_reason, attrs.waiting_since, attrs.started_at, attrs.timeout_at, attrs.recorded_lap,
      reference.entity_id, reference.status, selected, options, match.entity_id, match.status, delay.state, replay.status, replay.state, protection, localSpoilers, session.key, session.active]),
  };
}


// A retained module is rebuilt from one captured set of entity states. It never
// combines a saved primary source with newly received dependency values.
export function retainedSourceKey(module) {
  const options = module.options;
  return ({
    timing: 'driver_positions', lap_chart: 'driver_positions',
    tyres: options.content === 'statistics' ? 'tyre_statistics' : 'current_tyres',
    pit_stops: 'pitstops',
    incidents: options.content === 'track_limits_summary' ? 'track_limits' : options.content,
    weather: options.content === 'track_conditions' ? 'track_weather' : 'weather',
    calendar: options.range === 'season' ? 'current_season' : 'next_race',
    documents: 'fia_documents',
    results: ({ latest_race: 'last_race_results', race_results: 'season_results', sprint_results: 'sprint_results', starting_grid: 'starting_grid' })[options.content],
    standings: options.competitors === 'teams' ? 'constructor_standings' : 'driver_standings',
    progression: options.competitors === 'teams' ? 'constructor_points_progression' : 'driver_points_progression',
  })[module.type] ?? null;
}

function trackWeatherFingerprint(hass, entry) {
  const weather = source(hass, entry, 'track_weather');
  return JSON.stringify([weather.entity_id, weather.status, weather.state, weather.attributes, weather.updated_at]);
}

export class RetainedSources {
  constructor() { this.clear(); }
  clear() { this.snapshots = new Map(); this.barriers = new Map(); this.token = null; this.position = null; this.seek = false; this.epoch = 0; this.references = new Map(); this.nextEvent = null; this.part = null; this.sessionKey = null; this.liveContext = false; this.protection = 'unknown'; this.viewGeneration = null; this.weatherReference = null; this.weatherBarrier = null; }
  update(hass, entry, config, preview = false) {
    const session = sessionContext(hass, entry), replay = source(hass, entry, 'replay_status');
    const player = source(hass, entry, 'replay_player'), position = number(player.attributes.media_position);
    const seeking = replay.state === 'seeking';
    if (seeking && !this.seek || position !== null && this.position !== null && position < this.position) this.epoch++;
    this.seek = seeking; this.position = position;
    const replayPhase = ['ready', 'playing', 'paused'].includes(replay.state) ? 'loaded' : replay.state;
    const coherentReplay = replayPhase === 'loaded' && player.status === 'available'
      && Boolean(player.attributes.selected_session_id)
      && player.attributes.selected_session === replay.attributes.selected_session
      && player.attributes.replay_state === replay.state;
    this.liveContext = session.source.status === 'available' && Boolean(session.name && session.start)
      && (replay.state === 'idle' || coherentReplay);
    const weatherReference = trackWeatherFingerprint(hass, entry);
    const viewGeneration = JSON.stringify([entry?.entry_id, session.key, replayPhase, replay.attributes.selected_session, player.attributes.selected_session_id, this.epoch, source(hass, entry, 'live_delay_number').state]);
    if (this.viewGeneration !== null && this.viewGeneration !== viewGeneration) {
      this.weatherBarrier = this.weatherReference === weatherReference ? weatherReference : null;
    }
    if (this.weatherBarrier !== weatherReference) this.weatherBarrier = null;
    this.viewGeneration = viewGeneration; this.weatherReference = weatherReference;
    const next = source(hass, entry, 'next_race');
    if (next.status === 'available') this.nextEvent = [next.state, next.attributes.race_start_utc ?? next.attributes.race_start, next.attributes.race_name];
    if (session.key !== this.sessionKey) this.part = null;
    const positions = source(hass, entry, 'driver_positions');
    if (positions.status === 'available') this.part = positiveInteger(positions.attributes.current_qualifying_part);
    this.sessionKey = session.key;
    const references = new Map(Object.values(entry?.entities ?? {}).map(id => [id, hass.states?.[id]]));
    this.protection = spoilerState(hass, entry, config.context.spoilers);
    const token = JSON.stringify([entry?.entry_id, entry?.entities, entry?.disabled_entities,
      this.protection, session.key, session.active, session.source.status,
      replayPhase, replay.attributes.selected_session, player.attributes.selected_session_id, this.epoch,
      source(hass, entry, 'live_delay_number').state,
      this.nextEvent, this.part]);
    if (preview || !entry) { this.clear(); return; }
    if (this.token !== null && token !== this.token) {
      this.snapshots.clear();
      // A context transition alone is not a new source observation. Do not
      // recapture the previous state's payload until that entity updates.
      this.barriers = new Map([...references].filter(([id, state]) => this.references.get(id) === state));
    }
    this.token = token; this.references = references;
    const enabled = new Set(config.modules.filter(module => module.enabled && module.unavailable === 'retain').map(module => module.id));
    for (const id of this.snapshots.keys()) if (!enabled.has(id)) this.snapshots.delete(id);
  }
  weatherAwaitingObservation(hass, entry) {
    return this.weatherBarrier !== null && this.weatherBarrier === trackWeatherFingerprint(hass, entry);
  }
  select(hass, entry, module, definition, preview = false) {
    const primary = retainedSourceKey(module), selected = primary && source(hass, entry, primary);
    const sessionBound = ['timing', 'lap_chart', 'tyres', 'pit_stops', 'incidents'].includes(module.type)
      || primary === 'track_weather' || primary === 'starting_grid'
      || module.type === 'standings' && module.fields.some(id => id.startsWith('predicted_'));
    const signature = JSON.stringify([module.type, primary, module.options.content, module.options.competitors, module.options.range]);
    let saved = this.snapshots.get(module.id);
    if (saved?.signature !== signature) { this.snapshots.delete(module.id); saved = null; }
    const sensitive = definition?.spoiler || ['timing', 'lap_chart', 'tyres', 'pit_stops', 'incidents'].includes(module.type) || primary === 'track_weather';
    if (preview || sensitive && this.protection !== 'clear' || !module.enabled || module.unavailable !== 'retain' || !selected
      || ['missing', 'disabled'].includes(selected.status) || sessionBound && !this.liveContext) {
      this.snapshots.delete(module.id); return { hass, retained: false };
    }
    const primaryState = hass.states?.[selected.entity_id];
    if (selected.status === 'available' && hass.connection?.connected !== false) {
      if (this.barriers.has(selected.entity_id) && this.barriers.get(selected.entity_id) === primaryState) return { hass, retained: false };
      this.barriers.delete(selected.entity_id);
      const keys = new Set([primary, 'driver_list', 'current_session', 'session_status', 'replay_status',
        ...(module.type === 'timing' ? ['current_tyres'] : []),
        ...(module.type === 'pit_stops' ? ['driver_positions', 'f1tv_token_status'] : []),
        ...(module.type === 'standings' ? [module.options.competitors === 'teams' ? 'championship_prediction_teams' : 'championship_prediction_drivers'] : [])]);
      const references = [...keys].map(key => entry.entities?.[key]).filter(Boolean).map(id => [id, hass.states?.[id]]);
      if (!saved || references.length !== saved.references.length || references.some(([id, state], index) => id !== saved.references[index][0] || state !== saved.references[index][1])) {
        saved = { signature, references, states: structuredClone(Object.fromEntries(references)) };
        this.snapshots.set(module.id, saved);
      }
      return { hass, retained: false };
    }
    return saved ? { hass: { ...hass, states: { ...hass.states, ...saved.states } }, retained: true }
      : { hass, retained: false };
  }
}
