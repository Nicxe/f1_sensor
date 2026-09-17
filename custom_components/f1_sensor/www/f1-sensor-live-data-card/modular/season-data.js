const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ source, array, sessionContext }, { number, positiveInteger, seconds, positionChange, safeImageUrl }, { normalizeTeamName }] = await Promise.all([
  load('./data.js'), load('./semantics.js'), load('../platform/branding.js'),
]);
const { defaultFields } = await load('./catalog.js');
const records = value => array(value).filter(item => item && typeof item === 'object' && !Array.isArray(item));
const text = value => typeof value === 'string' && value.trim() ? value.trim() : null;
const key = value => value == null ? '' : String(value).trim();
const teamKey = value => normalizeTeamName(value) || key(value).toLocaleLowerCase().replace(/[^a-z0-9]/g, '');
const uniqueRows = rows => [...new Map(rows.filter(row => row.id).map(row => [row.id, row])).values()];
const driverRoster = (hass, entry) => records(source(hass, entry, 'driver_list').attributes.drivers);
const driverIdentity = (people, numberValue, code) => people.find(item => key(item.racing_number) === numberValue || Boolean(code && text(item.tla) === code)) ?? {};
const sourceKey = module => ({ latest_race: 'last_race_results', race_results: 'season_results', sprint_results: 'sprint_results', starting_grid: 'starting_grid' })[module.options.content];

export function selectRows(rows, module, focus = {}) {
  const driver = module.driver || focus.driver, team = module.team || focus.team;
  const selected = rows.filter(row => (!driver || row.id === driver || row.driver === driver || row.number === driver)
    && (!team || row.team_id === team || (row.teams ?? [row.team]).some(name => Boolean(teamKey(name) && teamKey(name) === teamKey(team)))));
  const sort = module.options.sort, direction = module.options.direction === 'desc' ? -1 : 1;
  selected.sort((a, b) => {
    const x = a[sort], y = b[sort];
    // Missing data stays last in either direction. Equal values retain a stable identity order.
    if (x == null && y != null) return 1;
    if (y == null && x != null) return -1;
    return (typeof x === 'string' ? x.localeCompare(String(y), undefined, { numeric: true }) : (x ?? 0) - (y ?? 0)) * direction || a.id.localeCompare(b.id, undefined, { numeric: true });
  });
  return { rows: selected.slice(0, module.options.rows), total: selected.length, filtered: Boolean(driver || team) };
}

export function resultChoices(hass, entry, module) {
  const selected = source(hass, entry, sourceKey(module));
  return records(selected.attributes.races).filter(race => key(race.round)).map(race => ({ id: key(race.round), name: text(race.race_name) ?? key(race.round) }))
    .sort((a, b) => Number(b.id) - Number(a.id));
}
export function resultsModel(hass, entry, module, focus = {}) {
  const selected = source(hass, entry, sourceKey(module)), attrs = selected.attributes;
  const people = driverRoster(hass, entry);
  const isGrid = module.options.content === 'starting_grid';
  const choices = resultChoices(hass, entry, module);
  const rounds = records(attrs.races).sort((a, b) => (number(b.round) ?? 0) - (number(a.round) ?? 0));
  const race = ['race_results', 'sprint_results'].includes(module.options.content)
    ? module.options.round ? rounds.find(item => key(item.round) === module.options.round) : rounds.find(item => records(item.results).length)
    : attrs;
  const raw = records(isGrid ? attrs.grid : race?.results);
  const rows = uniqueRows(raw.map(item => {
    const driver = item.driver ?? item.Driver ?? {}, team = item.constructor ?? item.Constructor ?? {};
    const numberValue = key(item.racing_number ?? item.number ?? driver.permanentNumber);
    const code = text(item.tla ?? driver.code), name = text(item.driver_name) ?? text([driver.givenName, driver.familyName].filter(Boolean).join(' ')) ?? code ?? numberValue;
    const identity = driverIdentity(people, numberValue, code);
    const grid = number(isGrid ? item.grid_position : item.grid);
    const position = isGrid ? null : positiveInteger(item.position);
    return { id: numberValue || key(driver.driverId) || code || '', number: numberValue, driver: code || numberValue || name, name,
      team: text(isGrid ? item.team_name : team.name), team_id: key(team.constructorId), team_color: isGrid ? item.team_color : null,
      headshot: safeImageUrl(identity.headshot_large ?? identity.headshot_small),
      result_position: position, grid_position: Number.isInteger(grid) && grid >= 0 ? grid : null,
      position_change: isGrid ? null : positionChange(position, grid), laps: number(item.laps), points: number(item.points),
      result_time: text(item.time ?? item.Time?.time), result_status: text(item.status),
      qualifying_position: positiveInteger(item.qualifying_position), qualifying_time: seconds(item.qualifying_time_secs ?? item.qualifying_time),
      grid_delta: number(item.grid_delta) ?? (isGrid && Number.isInteger(grid) && positiveInteger(item.qualifying_position) ? grid - positiveInteger(item.qualifying_position) : null),
      qualifying_segment: text(item.qualifying_segment), qualifying_delta: null, history: [],
    };
  }));
  if (isGrid) {
    const times = rows.map(item => item.qualifying_time).filter(value => value !== null);
    const fastest = times.length ? Math.min(...times) : null;
    if (fastest !== null) for (const item of rows) item.qualifying_delta = item.qualifying_time === null ? null : Math.max(0, item.qualifying_time - fastest);
  }
  // Grid is a different data category; default classification order uses the actual grid order.
  const sortModule = isGrid && module.options.sort === 'result_position' ? { ...module, options: { ...module.options, sort: 'grid_position' } } : module;
  return { ...selectRows(rows, sortModule, focus), allRows: rows, source: selected, choices, selected: key(race?.round),
    context: { meeting: text(isGrid ? attrs.meeting_name : race?.race_name), season: key(race?.season), round: key(race?.round), session: isGrid ? text(attrs.target_session_name) : module.options.content === 'sprint_results' ? 'Sprint' : 'Race', status: isGrid ? attrs.status : null, source: isGrid ? attrs.source : 'Jolpica', updated: isGrid ? attrs.source_updated_at : selected.updated_at, updatedKind: isGrid ? 'generated' : 'ha_state' },
    grid: isGrid,
  };
}

function predictions(hass, entry, teams) {
  const selected = source(hass, entry, teams ? 'championship_prediction_teams' : 'championship_prediction_drivers');
  const collection = selected.attributes[teams ? 'teams' : 'drivers'];
  const rows = Array.isArray(collection) ? records(collection) : Object.entries(collection ?? {}).filter(([, item]) => item && typeof item === 'object').map(([id, item]) => ({ source_id: id, ...item }));
  const session = sessionContext(hass, entry);
  // A restored projection outside an active race must not look like official standings.
  const active = session.active && /^(race|sprint)$/i.test(session.name ?? '');
  return { source: selected, active, rows: active && selected.status === 'available' ? rows : [] };
}
export function standingsModel(hass, entry, module, focus = {}) {
  const teams = module.options.competitors === 'teams';
  const selected = source(hass, entry, teams ? 'constructor_standings' : 'driver_standings');
  const attrs = selected.attributes, projection = predictions(hass, entry, teams), people = driverRoster(hass, entry);
  const rows = uniqueRows(records(attrs[teams ? 'constructor_standings' : 'driver_standings']).map(item => {
    const person = item.Driver ?? {}, constructors = records(item.Constructors), constructor = item.Constructor ?? constructors[0] ?? {};
    const name = teams ? text(constructor.name) : text([person.givenName, person.familyName].filter(Boolean).join(' '));
    const id = key(teams ? constructor.constructorId ?? constructor.name : person.permanentNumber ?? person.driverId ?? person.code);
    const code = text(person.code), team = text(constructor.name), teamId = key(constructor.constructorId);
    const identity = teams ? {} : driverIdentity(people, key(person.permanentNumber), code);
    const prediction = projection.rows.find(row => teams ? Boolean(teamKey(team) && teamKey(row.TeamName ?? row.team_name ?? row.source_id) === teamKey(team))
      : key(row.RacingNumber ?? row.racing_number ?? row.source_id) === id || Boolean(code && (row.Tla ?? row.tla) === code));
    const currentPoints = number(prediction?.CurrentPoints ?? prediction?.current_points) ?? number(item.points);
    const predictedPoints = number(prediction?.PredictedPoints ?? prediction?.predicted_points);
    return { id, number: teams ? '' : key(person.permanentNumber), driver: teams ? name : code ?? name ?? id, name: name ?? id,
      team: teams ? team : constructors.map(item => text(item.name)).filter(Boolean).join(' / ') || team, team_id: teamId, teams: teams ? [team] : constructors.map(item => text(item.name)).filter(Boolean), team_color: null,
      headshot: safeImageUrl(identity.headshot_large ?? identity.headshot_small),
      result_position: positiveInteger(item.position), points: number(item.points), wins: number(item.wins),
      predicted_position: positiveInteger(prediction?.PredictedPosition ?? prediction?.predicted_position), predicted_points: predictedPoints,
      points_change: predictedPoints !== null && currentPoints !== null ? predictedPoints - currentPoints : null, history: [],
    };
  }));
  return { ...selectRows(rows, module, teams ? { ...focus, driver: '' } : focus), allRows: rows, source: selected,
    projection: { requested: module.fields.some(id => id.startsWith('predicted_')) || module.options.sort.startsWith('predicted_'), available: projection.rows.length > 0, source: projection.source, active: projection.active },
    context: { season: key(attrs.season), round: key(attrs.round), source: 'Jolpica', updated: selected.updated_at, updatedKind: 'ha_state' }, teams,
  };
}

export function documentsModel(hass, entry, module) {
  const selected = source(hass, entry, 'fia_documents'), attrs = selected.attributes;
  const items = records(attrs.documents);
  if (text(attrs.name)) items.push(attrs);
  const documents = uniqueRows(items.map(item => {
    const title = text(item.name), url = safeImageUrl(item.url), published = text(item.published);
    return { id: url || [title, published, item.document_number].join('|'), document_title: title, document_time: published,
      document_number: positiveInteger(item.document_number), url, timestamp: published && /T.*(?:Z|[+-]\d\d:\d\d)$/.test(published) ? Date.parse(published) : null };
  }).filter(item => item.document_title));
  const search = module.options.search.toLocaleLowerCase();
  const rows = documents.filter(item => !search || item.document_title.toLocaleLowerCase().includes(search));
  rows.sort((a, b) => {
    const x = number(a.timestamp), y = number(b.timestamp);
    if (x === null && y !== null) return 1;
    if (y === null && x !== null) return -1;
    return ((y ?? 0) - (x ?? 0) || (b.document_number ?? 0) - (a.document_number ?? 0) || a.id.localeCompare(b.id)) * (module.options.order === 'oldest' ? -1 : 1);
  });
  return { rows: rows.slice(0, module.options.limit), total: rows.length, filtered: Boolean(search), source: selected,
    context: { meeting: text(attrs.race?.race_name), season: key(attrs.race?.season), round: key(attrs.race?.round), source: 'FIA', updated: selected.updated_at, updatedKind: 'ha_state' } };
}


export function progressionModel(hass, entry, module, focus = {}) {
  const teams = module.options.competitors === 'teams';
  const selected = source(hass, entry, teams ? 'constructor_points_progression' : 'driver_points_progression'), attrs = selected.attributes;
  const seen = new Set();
  const rounds = records(attrs.rounds).map((item, index) => ({ ...item, id: positiveInteger(item.round), index })).filter(item => {
    if (!item.id || seen.has(item.id)) return false;
    seen.add(item.id); return true;
  }).sort((a, b) => a.id - b.id);
  const collection = attrs[teams ? 'constructors' : 'drivers'];
  const competitors = collection && typeof collection === 'object' && !Array.isArray(collection) ? Object.entries(collection).filter(([, item]) => item && typeof item === 'object') : [];
  const first = positiveInteger(module.options.start_round), last = positiveInteger(module.options.end_round);
  const lastObservedIndex = rounds.reduce((latest, round) => competitors.some(([, item]) => number(item[module.options.metric]?.[round.index]) !== null) ? Math.max(latest, round.index) : latest, -1);
  const displayed = rounds.filter(item => (!first || item.id >= first) && (!last || item.id <= last)
    && (module.options.show_future_rounds !== false || item.index <= lastObservedIndex));
  const allSeries = competitors.map(([id, item]) => ({ id, name: text(item.identity?.name) ?? id, driver: text(item.identity?.code) ?? id,
    driver_id: key(item.identity?.driverId), team_id: key(item.identity?.constructorId),
    total: number(item.totals?.points),
    values: displayed.map(round => ({ round: round.id, value: number(item[module.options.metric]?.[round.index]) })),
  })).sort((a, b) => (b.total ?? -1) - (a.total ?? -1) || a.id.localeCompare(b.id));
  const pinned = teams ? module.team || focus.team : module.driver || focus.driver;
  // Season progression identifies drivers by historical code/ID. Use a current
  // racing number only to resolve that code, never to replace historical names.
  const roster = records(source(hass, entry, 'driver_list').attributes.drivers);
  const code = pinned && roster.find(item => key(item.racing_number) === pinned)?.tla;
  const matches = series => !pinned || [series.id, series.driver, series.driver_id, series.team_id, series.name].includes(pinned) || series.driver === code;
  const series = allSeries.filter(matches).filter(item => !module.options.selected.length || module.options.selected.includes(item.id)).slice(0, module.options.series_limit);
  return { source: selected, series, allSeries, rounds: displayed, allRounds: rounds, total: allSeries.length, filtered: Boolean(pinned || module.options.selected.length),
    metric: module.options.metric, teams, context: { season: key(attrs.season), source: 'Jolpica', updated: selected.updated_at, updatedKind: 'ha_state' },
  };
}


export function seriesSegments(values) {
  const segments = []; let active = [];
  for (const [index, item] of values.entries()) {
    if (number(item.value) === null) { if (active.length) segments.push(active); active = []; }
    else active.push({ index, round: item.round, value: item.value });
  }
  if (active.length) segments.push(active);
  return segments;
}


export function chartAxis(values, discrete = false, zeroBaseline = true) {
  const valid = values.map(number).filter(value => value !== null);
  let minimum = zeroBaseline || !valid.length ? Math.min(0, ...valid) : Math.min(...valid);
  let maximum = zeroBaseline || !valid.length ? Math.max(1, ...valid) : Math.max(...valid);
  if (maximum === minimum) { const padding = Math.max(.001, Math.abs(minimum) * .005); minimum -= padding; maximum += padding; }
  const raw = (maximum - minimum) / 4;
  const base = 10 ** Math.floor(Math.log10(raw));
  let step = base * ([1, 2, 2.5, 5, 10].find(factor => factor * base >= raw) ?? 10);
  if (discrete) step = Math.max(1, Math.ceil(step));
  const low = Math.floor(minimum / step) * step, high = Math.ceil(maximum / step) * step;
  const ticks = Array.from({ length: Math.round((high - low) / step) + 1 }, (_, i) => Number((low + i * step).toPrecision(12)));
  return { low, high, ticks };
}


export function archivePlan(module, entryId, read, now = Date.now()) {
  const options = module.options, pinned = module.selection?.mode === 'pinned' && module.selection.source === 'archive' ? module.selection : null;
  const year = pinned?.season ?? options.year;
  const catalogQuery = { type: 'f1_sensor/history/catalog', entry_id: entryId, year };
  const catalogState = read(catalogQuery), catalog = catalogState.status === 'ready' ? catalogState.data?.payload : null;
  const meetings = number(catalog?.year) === year ? records(catalog.meetings).filter(item => positiveInteger(item.round) && Number(item.round) <= 99) : [];
  const started = item => Number.isFinite(Date.parse(item.start)) && Date.parse(item.start) <= now;
  const eligible = item => options.content === 'classification' ? ['race', 'sprint', 'qualifying'].includes(item.kind) : item.kind === 'race';
  const chronological = meetings.toSorted((a, b) => Number(b.round) - Number(a.round));
  const meeting = pinned ? meetings.find(item => key(item.meeting_key) === pinned.meeting_key) ?? null
    : options.round ? meetings.find(item => key(item.round) === options.round)
    : chronological.find(item => records(item.sessions).some(session => eligible(session) && started(session))) ?? null;
  const sessions = records(meeting?.sessions).filter(item => text(item.session_key));
  const requestedSession = pinned?.session_key ?? options.session_key;
  const session = requestedSession ? sessions.find(item => key(item.session_key) === requestedSession) ?? null
    : sessions.filter(item => eligible(item) && started(item)).toSorted((a, b) => Date.parse(b.start) - Date.parse(a.start))[0] ?? null;
  const requests = [catalogQuery], unsupported = Boolean(session && !eligible(session));
  let resultQuery = null, lapQuery = null;
  if (session && !unsupported) {
    resultQuery = { type: 'f1_sensor/history/results', entry_id: entryId, year, round: Number(meeting.round), session_type: session.kind, session_key: session.session_key }; requests.push(resultQuery);
    if (options.content !== 'classification') { lapQuery = { type: 'f1_sensor/history/laps', entry_id: entryId, year, round: Number(meeting.round), session_type: session.kind }; requests.push(lapQuery); }
  }
  return { year, meeting, session, meetings, sessions, requests, catalogState, resultQuery, lapQuery, unsupported,
    requestedRound: pinned?.meeting_key ?? options.round, requestedSession: pinned?.session_key ?? options.session_key };
}

export function archiveModel(module, entryId, read, now = Date.now()) {
  const plan = archivePlan(module, entryId, read, now), { meeting, session, resultQuery, lapQuery } = plan, options = module.options;
  const states = plan.requests.map(read), error = states.some(state => state.status === 'error' || state.data?.failed), disconnected = states.some(state => state.status === 'disconnected');
  const loading = states.some(state => ['loading', 'refreshing'].includes(state.status));
  const resultState = resultQuery ? read(resultQuery) : null, lapState = lapQuery ? read(lapQuery) : null;
  const ready = state => state?.status === 'ready' && !state.data?.failed ? state.data?.payload : null;
  const result = ready(resultState), laps = ready(lapState);
  const rows = uniqueRows(records(result?.results).map((item, index) => {
    const stableId = text(item.driver_id), grid = number(item.grid), position = positiveInteger(item.position), name = text(item.driver_name);
    // Old backends may omit IDs. Render their classification, but never guess a
    // join to lap data from today's driver roster or a reused racing number.
    return { id: stableId ?? `unidentified:${index}`, stableId, number: key(item.driver_number), driver: text(item.driver_acronym) ?? name ?? stableId ?? '—', name: name ?? stableId ?? '—',
      team: text(item.constructor_name), team_id: text(item.constructor_id), result_position: position, grid_position: Number.isInteger(grid) && grid >= 0 ? grid : null,
      position_change: positionChange(position, grid), laps: number(item.laps), points: number(item.points), result_time: text(item.duration), result_status: text(item.status_detail) ?? text(item.status),
      q1_time: seconds(item.q1), q2_time: seconds(item.q2), q3_time: seconds(item.q3), history: [] };
  }));
  const selectedIds = options.selected, filteredRows = selectedIds.length ? rows.filter(row => selectedIds.includes(row.id)) : rows;
  const validLaps = laps && number(laps.year) === plan.year && number(laps.round) === number(meeting?.round) && laps.session_type === session?.kind
    ? records(laps.laps).map(item => ({ ...item, driver_id: text(item.driver_id), lap_number: positiveInteger(item.lap_number) })).filter(item => item.driver_id && item.lap_number && item.lap_number <= 500) : [];
  const lapByDriver = new Map();
  for (const item of validLaps) {
    if (!lapByDriver.has(item.driver_id)) lapByDriver.set(item.driver_id, new Map());
    lapByDriver.get(item.driver_id).set(item.lap_number, item);
  }
  const allSeries = rows.filter(row => row.stableId).toSorted((a, b) => (a.result_position ?? Infinity) - (b.result_position ?? Infinity) || a.id.localeCompare(b.id)).map(row => ({ id: row.id, name: row.name }));
  for (const id of lapByDriver.keys()) if (!allSeries.some(item => item.id === id)) allSeries.push({ id, name: id });
  const chosen = (selectedIds.length ? allSeries.filter(item => selectedIds.includes(item.id)) : allSeries).slice(0, options.series_limit);
  const bounds = validLaps.reduce(([first, last], item) => [Math.min(first, item.lap_number), Math.max(last, item.lap_number)], [Infinity, 0]);
  const first = options.start_lap || (Number.isFinite(bounds[0]) ? bounds[0] : 0), last = options.end_lap || bounds[1];
  const invalidRange = Boolean(first && last && first > last), rounds = !invalidRange && first && last ? Array.from({ length: last - first + 1 }, (_, index) => ({ id: String(first + index) })) : [];
  const series = chosen.map(item => ({ ...item, values: rounds.map(round => {
    const lap = lapByDriver.get(item.id)?.get(Number(round.id)), value = options.content === 'lap_position' ? positiveInteger(lap?.position) <= 100 ? positiveInteger(lap?.position) : null : seconds(lap?.lap_duration);
    return { round: round.id, value };
  }) }));
  const resultUnsupported = result?.coverage?.results === 'not_available';
  return { ...plan, ...selectRows(filteredRows, { ...module, driver: '', team: '' }), filtered: selectedIds.length > 0, allRows: rows, allSeries, series, rounds, axisKind: 'lap', metric: options.content,
    error, disconnected, loading, invalidRange, unsupported: plan.unsupported || resultUnsupported,
    context: meeting && session ? { season: plan.year, round: meeting.round, meetingKey: key(meeting.meeting_key), session: session.name, sessionKey: key(session.session_key), source: 'jolpica', updated: (lapState ?? resultState)?.received_at, updatedKind: 'received' } : null,
    fields: options.content === 'classification' && options.profile === 'auto' ? session?.kind === 'qualifying' ? ['result_position', 'driver', 'team', 'q1_time', 'q2_time', 'q3_time'] : defaultFields(module) : module.fields,
    resultCoverage: result?.coverage, lapCoverage: laps?.coverage, attribution: text(result?.attribution) ?? text(laps?.attribution) ?? 'Data provided by Jolpica (jolpi.ca)',
    invalidIdentity: Boolean(laps && !validLaps.length && records(laps.laps).length),
  };
}
