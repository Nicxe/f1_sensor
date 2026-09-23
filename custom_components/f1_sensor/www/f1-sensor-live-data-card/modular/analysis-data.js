const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ array }, { number, positiveInteger, seconds, compoundMeta }, { selectRows }] = await Promise.all([load('./data.js'), load('./semantics.js'), load('./season-data.js')]);
const records = value => array(value).filter(item => item && typeof item === 'object' && !Array.isArray(item));
const text = value => typeof value === 'string' && value.trim() ? value.trim() : null;
const id = value => ['string', 'number'].includes(typeof value) ? String(value).trim() : '';
const score = value => { const result = number(value); return result !== null && result >= 0 && result <= 1 ? result : null; };
export function timelineModel(snapshot, module, focus = {}) {
  if (!snapshot || snapshot.protocol_version !== 1) return { rows: [], total: 0, pending: true };
  const people = records(snapshot.drivers), events = new Map();
  for (const raw of records(snapshot.timeline?.events)) {
    const key = id(raw.event_id); if (!key || raw.session_id && snapshot.session_id && raw.session_id !== snapshot.session_id) continue;
    const revision = positiveInteger(raw.revision) ?? 1;
    if ((events.get(key)?.revision ?? 0) > revision) continue;
    const numbers = array(raw.driver_numbers).map(id).filter(Boolean);
    const drivers = numbers.map(rn => people.find(person => id(person.driver_number) === rn) ?? { driver_number: rn });
    const signals = array(raw.supporting_signals).map(text).filter(Boolean);
    const derived = ['position', 'battle'].includes(raw.category) || raw.provider === 'local_estimate';
    events.set(key, { id: `${snapshot.session_id ?? ''}:${key}`, revision, sequence: number(raw.sequence), numbers,
      codes: drivers.map(person => text(person.tla)).filter(Boolean), teams: drivers.map(person => text(person.team)).filter(Boolean),
      incident_drivers: drivers.map(person => text(person.tla) ?? text(person.name) ?? id(person.driver_number)).join(' / ') || null,
      incident_lap: positiveInteger(raw.lap_number), event_time: text(raw.occurred_at),
      analysis_title: text(raw.title), analysis_description: text(raw.description), analysis_category: text(raw.category),
      analysis_source: [text(raw.provider), ...signals].filter(Boolean).join(' · ') || null, source_signals: signals, source_provider: text(raw.provider),
      analysis_quality: score(raw.confidence), derived, final: typeof raw.final === 'boolean' ? raw.final : null,
    });
  }
  const driver = module.driver || focus.driver, team = module.team || focus.team, search = module.options.search.toLocaleLowerCase();
  const rows = [...events.values()].filter(row => (!driver || row.numbers.includes(driver) || row.codes.includes(driver)) && (!team || row.teams.includes(team))
    && (!module.options.categories.length || module.options.categories.includes(row.analysis_category))
    && (!search || [row.analysis_title, row.analysis_description, row.incident_drivers].some(value => value?.toLocaleLowerCase().includes(search))));
  rows.sort((a, b) => {
    const x = a.event_time ? Date.parse(a.event_time) : NaN, y = b.event_time ? Date.parse(b.event_time) : NaN;
    if (!Number.isFinite(x) && Number.isFinite(y)) return 1;
    if (!Number.isFinite(y) && Number.isFinite(x)) return -1;
    return ((Number.isFinite(x) && Number.isFinite(y) ? x - y : 0) || (a.sequence ?? 0) - (b.sequence ?? 0) || a.id.localeCompare(b.id)) * (module.options.order === 'oldest' ? 1 : -1);
  });
  return { rows: rows.slice(0, module.options.rows), total: rows.length, countKind: 'events', filtered: Boolean(driver || team || search || module.options.categories.length),
    context: { session: text(snapshot.session_name), key: id(snapshot.session_id), source: text(snapshot.provider) },
    capability: snapshot.capabilities?.timeline, provider: snapshot.provider, phase: snapshot.phase,
  };
}


export function battlesModel(snapshot, module, focus = {}) {
  if (!snapshot || snapshot.protocol_version !== 1) return { rows: [], total: 0, pending: true };
  const content = module.options.content, exchanges = content === 'position_exchanges', active = content === 'active_battles';
  const input = exchanges ? snapshot.position_exchanges : active ? snapshot.battles?.active : snapshot.battles?.history;
  const people = records(snapshot.drivers), unique = new Map();
  for (const [index, raw] of records(input).entries()) {
    const key = id(exchanges ? raw.event_id : raw.battle_id);
    if (!key || raw.session_id && snapshot.session_id && raw.session_id !== snapshot.session_id) continue;
    if (active && raw.active === false) continue;
    const numbers = array(raw.driver_numbers).map(id).filter(Boolean);
    const drivers = numbers.map(rn => people.find(person => id(person.driver_number) === rn) ?? { driver_number: rn });
    const signals = array(raw.supporting_signals).map(text).filter(Boolean), kind = text(raw.kind);
    const rowId = `${snapshot.session_id ?? ''}:${key}:${kind ?? 'unknown'}`;
    const gap = number(raw.gap_seconds);
    unique.set(rowId, { id: rowId, index, numbers, codes: drivers.map(person => text(person.tla)).filter(Boolean), teams: drivers.map(person => text(person.team)).filter(Boolean),
      incident_drivers: drivers.map(person => text(person.tla) ?? text(person.name) ?? id(person.driver_number)).join(' / ') || null,
      battle_status: active ? 'active_battle' : kind, kind, battle_gap: gap !== null && gap >= 0 ? gap : null,
      exchange_positions: exchanges ? drivers.map(person => { const rn = id(person.driver_number); return { driver: text(person.tla) ?? rn, before: positiveInteger(raw.positions_before?.[rn]), after: positiveInteger(raw.positions_after?.[rn]) }; }) : [],
      source_provider: text(snapshot.provider), source_signals: signals, analysis_quality: score(raw.confidence), derived: true,
    });
  }
  const driver = module.driver || focus.driver, team = module.team || focus.team;
  const rows = [...unique.values()].filter(row => (!driver || row.numbers.includes(String(driver)) || row.codes.includes(String(driver))) && (!team || row.teams.includes(team))
    && (!module.options.kinds.length || module.options.kinds.includes(row.kind)) && (!module.options.minimum_score || row.analysis_quality !== null && row.analysis_quality * 100 >= module.options.minimum_score));
  rows.sort((a, b) => (a.index - b.index) * (module.options.order === 'oldest' ? 1 : -1));
  return { rows: rows.slice(0, module.options.rows), total: rows.length, countKind: 'events', filtered: Boolean(driver || team || module.options.kinds.length || module.options.minimum_score),
    context: { session: text(snapshot.session_name), key: id(snapshot.session_id), source: text(snapshot.provider) },
    capability: snapshot.capabilities?.[exchanges ? 'position_exchanges' : 'battles'], threshold: number(snapshot.battles?.threshold_seconds), active, exchanges,
  };
}

function strategyComparisons(snapshot, module, focus) {
  const content = module.options.content, strategy = snapshot.strategy ?? {}, people = records(snapshot.drivers);
  const sourceKey = { teammates: 'teammate_comparisons', crossover: 'compound_crossover_indications', pit_outcomes: 'undercut_overcut_outcomes' }[content];
  const nonnegative = value => { const n = number(value); return n !== null && n >= 0 ? n : null; };
  const personName = rn => { const person = people.find(item => id(item.driver_number) === id(rn)); return text(person?.tla) ?? text(person?.name) ?? id(rn); };
  const driver = module.driver || focus.driver, team = module.team || focus.team;
  const rows = records(strategy[sourceKey]).map(raw => {
    const numbers = array(raw.drivers).map(id).filter(Boolean), codes = numbers.map(personName), compounds = array(raw.compounds).map(text).filter(Boolean);
    const lower = nonnegative(raw.observed_age_range?.[0]), upper = nonnegative(raw.observed_age_range?.[1]), age = nonnegative(raw.estimated_tyre_age_laps);
    const range = lower !== null && upper !== null && lower <= upper ? [lower, upper] : null;
    const observedCrossover = Boolean(range && age !== null && age >= lower && age <= upper);
    const rowId = JSON.stringify([snapshot.session_id, content, raw.team, numbers, compounds, numbers.map(rn => raw.stop_laps?.[rn])]);
    const difference = nonnegative(raw.delta_seconds);
    return { id: rowId, driver: codes.join(' / '), incident_drivers: codes.join(' / '), numbers, codes, team: text(raw.team),
      comparison_pace: numbers.map(rn => ({ driver: personName(rn), value: seconds(raw.median_clean_pace?.[rn]) })),
      comparison_gap: difference, pace_leader: difference === 0 ? null : numbers.includes(id(raw.faster_driver)) ? personName(raw.faster_driver) : null, equal_pace: difference === 0,
      comparison_tyres: compounds, crossover_age: observedCrossover ? age : null, observed_age_range: range, crossover_pace: observedCrossover ? seconds(raw.pace_at_crossover) : null,
      strategy_outcome: text(raw.result), comparison_stops: numbers.map(rn => ({ driver: personName(rn), value: positiveInteger(raw.stop_laps?.[rn]) })),
      exchange_positions: numbers.map(rn => ({ driver: personName(rn), before: positiveInteger(raw.positions_before?.[rn]), after: positiveInteger(raw.positions_after?.[rn]) })),
      analysis_quality: score(raw.confidence), source_provider: text(snapshot.provider), source_signals: array(raw.supporting_signals).map(text).filter(Boolean), derived: true,
    };
  }).filter(row => content === 'crossover' ? row.comparison_tyres.length >= 2 && (!module.options.compounds.length || row.comparison_tyres.some(compound => module.options.compounds.includes(compoundMeta(compound).key ?? 'UNKNOWN')))
    : row.numbers.length >= 2 && (!driver || row.numbers.includes(String(driver)) || row.codes.includes(String(driver))) && (!team || row.team === team));
  const unique = [...new Map(rows.map(row => [row.id, row])).values()].filter(row => !module.options.minimum_score || row.analysis_quality !== null && row.analysis_quality * 100 >= module.options.minimum_score);
  const selected = selectRows(unique, { ...module, driver: '', team: '' }, {});
  return { ...selected, allRows: unique, filtered: content !== 'crossover' && Boolean(driver || team), qualityFiltered: Boolean(module.options.minimum_score), countKind: 'comparisons',
    context: { session: text(snapshot.session_name), key: id(snapshot.session_id), source: text(snapshot.provider) },
    capability: strategy.status, coverage: strategy.coverage ?? {}, assumptions: array(strategy.assumptions).map(text).filter(Boolean), comparison: content,
  };
}

export function strategyModel(snapshot, module, focus = {}) {
  if (!snapshot || snapshot.protocol_version !== 1) return { rows: [], total: 0, pending: true };
  if (['teammates', 'crossover', 'pit_outcomes'].includes(module.options.content)) return strategyComparisons(snapshot, module, focus);
  const compounds = module.options.content === 'compound_comparison', strategy = snapshot.strategy ?? {}, people = records(snapshot.drivers);
  const count = value => { const n = number(value); return Number.isInteger(n) && n >= 0 ? n : null; };
  const rows = records(compounds ? strategy.compound_comparison : strategy.stints).map(raw => {
    const rn = id(raw.driver_number), stint = count(raw.stint_index), person = people.find(item => id(item.driver_number) === rn) ?? {};
    return { id: compounds ? id(raw.compound) : `${snapshot.session_id ?? ''}:${rn}:${stint ?? 'unknown'}`, number: rn,
      driver: text(person.tla) ?? rn, name: text(raw.driver_name ?? person.name) ?? rn, team: text(raw.team ?? person.team), team_color: text(person.team_color), history: [],
      tyre: text(raw.compound), stint_number: stint === null ? null : stint + 1, stint_first_lap: positiveInteger(raw.first_lap), stint_last_lap: positiveInteger(raw.last_lap), stint_start_age: count(raw.tyre_age_at_start),
      clean_pace: seconds(compounds ? raw.median_clean_pace : raw.adjusted_median_clean_pace), raw_pace: seconds(raw.raw_median_pace), degradation: number(raw.degradation_seconds_per_lap),
      clean_samples: count(raw.sample_count), raw_samples: count(raw.raw_sample_count), excluded_samples: count(raw.excluded_laps),
      exclusion_reasons: raw.excluded_reason_counts && typeof raw.excluded_reason_counts === 'object' && !Array.isArray(raw.excluded_reason_counts)
        ? Object.entries(raw.excluded_reason_counts).map(([reason, value]) => ({ reason, count: count(value) })).filter(item => item.count !== null) : [],
      compound_gap: number(raw.delta_to_fastest), strategy_pit_loss: number(raw.pit_loss_seconds), analysis_quality: score(raw.confidence), derived: true,
    };
  }).filter(row => row.id && (compounds || row.number) && (!module.options.compounds.length || module.options.compounds.includes(compoundMeta(row.tyre).key ?? 'UNKNOWN')));
  const unique = [...new Map(rows.map(row => [row.id, row])).values()].filter(row => (!module.options.minimum_score || row.analysis_quality !== null && row.analysis_quality * 100 >= module.options.minimum_score) && (!module.options.minimum_clean_laps || row.clean_samples !== null && row.clean_samples >= module.options.minimum_clean_laps));
  const selection = compounds ? { ...module, driver: '', team: '', options: { ...module.options, sort: ['driver', 'stint_number', 'degradation'].includes(module.options.sort) ? 'clean_pace' : module.options.sort } } : module;
  return { ...selectRows(unique, selection, compounds ? {} : focus), allRows: unique, qualityFiltered: Boolean(module.options.minimum_score || module.options.minimum_clean_laps), countKind: compounds ? 'compounds' : 'stints',
    context: { session: text(snapshot.session_name), key: id(snapshot.session_id), source: text(snapshot.provider) },
    capability: strategy.status, coverage: strategy.coverage ?? {}, assumptions: array(strategy.assumptions).map(text).filter(Boolean), compounds,
  };
}
