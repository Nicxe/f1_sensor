// Field IDs are configuration API. Labels, sources and presentation stay together.
export const VERSION = 3;
export const CARD_TYPE = 'custom:f1-sensor-card';
export const label = (item, language = 'en') => item?.label?.[String(language).startsWith('sv') ? 'sv' : 'en'] ?? item?.id ?? '';

const timestampsFor = source => source === 'analysis'
  ? { source: 'not_provided', received: 'subscription.received_at', updated: 'not_provided', displayed: 'snapshot' }
  : source === 'track_map' ? { source: 'stream_timestamp', received: 'subscription.received_at', updated: 'generated_at', displayed: 'snapshot' }
    : source === 'race_control_log' ? { source: 'events[].utc', received: 'subscription.received_at', updated: 'not_provided', displayed: 'snapshot' }
      : { source: 'not_provided', received: 'not_provided', updated: 'entity.last_updated', displayed: 'snapshot' };
const generationFor = source => source === 'analysis' || source === 'track_map' || source === 'race_control_log'
  ? 'session'
  : source === 'replay_player' || source === 'analysis/telemetry_compare' ? 'replay_session'
    : source === 'selected_points_progression' ? 'season'
      : ['last_race_results', 'next_race', 'selected_result', 'selected_standings', 'starting_grid', 'weather'].includes(source) ? 'season_round'
        : 'source_snapshot';

const timing = (id, en, sv, type, path, extra = {}) => ({
  id, label: { en, sv }, type, unit: type === 'duration' ? 's' : null,
  source: 'driver_positions', path, capability: 'public_timing',
  modes: ['live', 'replay'], sessions: ['practice', 'qualifying', 'sprint_qualifying', 'sprint', 'race'],
  identity: ['entry', 'session', 'driver', ...(type === 'duration' ? ['lap'] : [])],
  generation: 'session',
  timestamps: timestampsFor(extra.source ?? 'driver_positions'),
  freshness: 'session', spoiler: true, sortable: true, filterable: false,
  mobile: 2, presentations: ['table', 'detail'], ...extra,
});

export const TIMING_FIELDS = [
  timing('position', 'Pos', 'Pos', 'integer', 'current_position', { mobile: 0 }),
  timing('driver', 'Driver', 'Förare', 'driver', 'racing_number', { mobile: 0, filterable: true }),
  timing('team', 'Team', 'Team', 'text', 'team', { filterable: true }),
  timing('gap', 'To leader', 'Till ledaren', 'gap', 'gap_to_leader', { mobile: 1 }),
  timing('interval', 'Ahead', 'Framför', 'gap', 'interval_to_position_ahead', { mobile: 1 }),
  timing('last_lap', 'Last lap', 'Senaste varv', 'duration', 'laps', { mobile: 1 }),
  timing('best_lap', 'Best lap', 'Bästa varv', 'duration', 'best_lap_time'),
  timing('lap_delta', 'Lap change', 'Varvskillnad', 'delta', 'laps', { comparison: 'previous_completed_lap' }),
  ...[1, 2, 3].map(n => timing(`sector_${n}`, `S${n}`, `S${n}`, 'sector', `sectors.current.sector_${n}`, {
    unit: 's', identity: ['entry', 'session', 'driver', 'lap', 'sector'], mobile: 1,
  })),
  ...[1, 2, 3].flatMap(n => [
    timing(`q${n}_time`, `Q${n} best`, `Q${n} bästa`, 'qualifying_duration', `q${n}_time`, { sessions: ['qualifying', 'sprint_qualifying'], identity: ['entry', 'session', 'part', 'driver'] }),
    timing(`q${n}_position`, `Q${n} position`, `Q${n} placering`, 'integer', `q${n}_position`, { sessions: ['qualifying', 'sprint_qualifying'] }),
    timing(`best_sector_${n}`, `Best S${n}`, `Bästa S${n}`, 'sector', `sectors.personal_best.sector_${n}`, { identity: ['entry', 'session', 'part', 'driver', 'lap', 'sector'] }),
  ]),
  timing('qualifying_gap', 'Current part gap', 'Avstånd i aktuell kvaldel', 'seconds_delta', 'current qualifying part best - fastest current qualifying part', { sessions: ['qualifying', 'sprint_qualifying'], unit: 's', comparison: 'fastest_current_qualifying_part' }),
  timing('theoretical_lap', 'Theoretical lap', 'Teoretiskt varv', 'theoretical_duration', 'sum(sectors.personal_best)', { estimated: true, comparison: 'personal_best_sectors' }),
  timing('laps', 'Laps', 'Varv', 'integer', 'completed_laps'),
  timing('tyre', 'Tyre', 'Däck', 'compound', 'compound', { source: 'current_tyres', mobile: 1 }),
  timing('tyre_age', 'Tyre age', 'Däckålder', 'integer', 'stint_laps', { source: 'current_tyres', unit: 'laps' }),
  timing('status', 'Status', 'Status', 'status', 'in_pit'),
];

const basic = (id, en, sv, source, path, type = 'text', extra = {}) => ({
  id, label: { en, sv }, source, path, type, unit: null, capability: 'public',
  modes: ['schedule'], sessions: ['all'], identity: ['entry', 'season', 'round'],
  generation: generationFor(source),
  timestamps: timestampsFor(source),
  freshness: 'source', spoiler: false, sortable: false, filterable: false,
  mobile: 0, presentations: ['summary'], ...extra,
});
const classification = (id, en, sv, type = 'text', extra = {}) => basic(id, en, sv, 'last_race_results', `results[].${id}`, type, {
  modes: ['results'], identity: ['entry', 'season', 'round', 'session', 'driver'],
  spoiler: true, sortable: true, presentations: ['table', 'detail'], ...extra,
});
export const RESULT_FIELDS = [
  classification('result_position', 'Classification', 'Klassificering', 'integer', { path: 'results[].position' }),
  classification('grid_position', 'Grid', 'Startplats', 'grid', { path: 'results[].grid' }),
  classification('position_change', 'Places gained', 'Vunna platser', 'position_delta', { path: 'results[].position - results[].grid', comparison: 'starting_grid' }),
  classification('result_time', 'Time / gap', 'Tid / avstånd', 'classification_time', { path: 'results[].time', unit: 'source_defined' }),
  classification('result_status', 'Classification status', 'Resultatstatus', 'text', { path: 'results[].status' }),
  classification('points', 'Points', 'Poäng', 'number', { path: 'results[].points', unit: 'points' }),
  classification('wins', 'Wins', 'Vinster', 'integer', { source: 'driver_standings', path: 'driver_standings[].wins' }),
  classification('predicted_points', 'Projected points', 'Prognospoäng', 'number', { source: 'championship_prediction_drivers', path: 'drivers.*.PredictedPoints', capability: 'extended_timing', modes: ['live', 'replay'], freshness: 'session', generation: 'session', unit: 'points', estimated: true }),
  classification('predicted_position', 'Projected position', 'Prognosplacering', 'integer', { source: 'championship_prediction_drivers', path: 'drivers.*.PredictedPosition', capability: 'extended_timing', modes: ['live', 'replay'], freshness: 'session', generation: 'session', estimated: true }),
  classification('points_change', 'Projected change', 'Prognosförändring', 'points_delta', { source: 'championship_prediction_drivers', path: 'drivers.*.PredictedPoints - drivers.*.CurrentPoints', capability: 'extended_timing', modes: ['live', 'replay'], freshness: 'session', generation: 'session', unit: 'points', estimated: true, comparison: 'current_points' }),
  classification('qualifying_position', 'Qualifying position', 'Kvalplacering', 'integer', { source: 'starting_grid', path: 'grid[].qualifying_position', generation: 'session' }),
  classification('qualifying_time', 'Qualifying time', 'Kvaltid', 'classification_duration', { source: 'starting_grid', path: 'grid[].qualifying_time_secs', generation: 'session', unit: 's' }),
  classification('grid_delta', 'Grid change', 'Förändrad startplats', 'position_delta', { source: 'starting_grid', path: 'grid[].grid_delta', generation: 'session', comparison: 'qualifying_position' }),
  classification('qualifying_segment', 'Qualifying segment', 'Kvaldel', 'text', { source: 'starting_grid', path: 'grid[].qualifying_segment', generation: 'session' }),
  classification('qualifying_delta', 'Qualifying gap', 'Kvalavstånd', 'seconds_delta', { source: 'starting_grid', path: 'grid[].qualifying_time_secs - fastest qualifying time', generation: 'session', unit: 's', comparison: 'fastest_qualifying_time' }),
];
export const SESSION_FIELDS = [
  timing('tyre_new', 'New set', 'Nytt set', 'boolean', 'drivers[].new', { source: 'current_tyres' }),
  timing('compound_best', 'Best recorded lap', 'Bästa registrerade varv', 'lap_duration', 'compounds.*.best_times[0].time_secs', { source: 'tyre_statistics' }),
  timing('compound_gap', 'To fastest compound', 'Till snabbaste blandning', 'seconds_delta', 'deltas.*', { source: 'tyre_statistics', comparison: 'fastest_compound' }),
  timing('compound_laps', 'Total laps', 'Totalt antal varv', 'integer', 'compounds.*.total_laps', { source: 'tyre_statistics' }),
  timing('new_sets', 'New sets used', 'Nya set använda', 'integer', 'compounds.*.sets_used', { source: 'tyre_statistics' }),
  timing('total_stints', 'Stints recorded', 'Registrerade stintar', 'integer', 'compounds.*.sets_used_total', { source: 'tyre_statistics' }),
  timing('best_runs', 'Fastest recorded stints', 'Snabbaste registrerade stintar', 'stint_records', 'compounds.*.best_times', { source: 'tyre_statistics' }),
  timing('pit_count', 'Stops recorded', 'Registrerade stopp', 'integer', 'cars.*.count', { source: 'pitstops', capability: 'extended_timing' }),
  timing('stop_lap', 'Stop lap', 'Depåvarv', 'integer', 'cars.*.stops[].lap', { source: 'pitstops', capability: 'extended_timing' }),
  timing('stop_time', 'Stationary time', 'Stillastående tid', 'seconds_duration', 'cars.*.stops[].pit_stop_time', { source: 'pitstops', capability: 'extended_timing', unit: 's' }),
  timing('lane_time', 'Pit lane time', 'Tid i depåområdet', 'seconds_duration', 'cars.*.stops[].pit_lane_time', { source: 'pitstops', capability: 'extended_timing', unit: 's' }),
  timing('pit_delta', 'Estimated lap loss', 'Beräknad varvförlust', 'seconds_delta', 'cars.*.stops[].pit_delta', { source: 'pitstops', capability: 'extended_timing', unit: 's', estimated: true, comparison: 'reference_laps' }),
  timing('stint_number', 'Stint', 'Stint', 'integer', 'strategy.stints[].stint_index + 1', { source: 'analysis' }),
  timing('stint_first_lap', 'First lap', 'Första varv', 'integer', 'strategy.stints[].first_lap', { source: 'analysis' }),
  timing('stint_last_lap', 'Last lap number', 'Sista varvnummer', 'integer', 'strategy.stints[].last_lap', { source: 'analysis' }),
  timing('stint_start_age', 'Starting tyre age', 'Däckålder vid start', 'integer', 'strategy.stints[].tyre_age_at_start', { source: 'analysis' }),
  timing('clean_pace', 'Median clean pace', 'Median för rena varv', 'lap_duration', 'strategy.stints[].adjusted_median_clean_pace', { source: 'analysis', estimated: true }),
  timing('raw_pace', 'Median recorded pace', 'Median för registrerade varv', 'lap_duration', 'strategy.stints[].raw_median_pace', { source: 'analysis' }),
  timing('degradation', 'Estimated degradation', 'Beräknad försämring', 'degradation', 'strategy.stints[].degradation_seconds_per_lap', { source: 'analysis', unit: 's/lap', estimated: true }),
  timing('clean_samples', 'Clean laps', 'Rena varv', 'integer', 'strategy.stints[].sample_count', { source: 'analysis' }),
  timing('raw_samples', 'Recorded laps', 'Registrerade varv', 'integer', 'strategy.stints[].raw_sample_count', { source: 'analysis' }),
  timing('excluded_samples', 'Excluded laps', 'Uteslutna varv', 'integer', 'strategy.stints[].excluded_laps', { source: 'analysis' }),
  timing('exclusion_reasons', 'Exclusion reasons', 'Orsaker till uteslutning', 'reason_counts', 'strategy.stints[].excluded_reason_counts', { source: 'analysis' }),
  timing('comparison_pace', 'Median pace by driver', 'Mediantempo per förare', 'driver_paces', 'strategy.teammate_comparisons[].median_clean_pace', { source: 'analysis', estimated: true }),
  timing('comparison_gap', 'Pace difference', 'Temposkillnad', 'seconds_duration', 'strategy.teammate_comparisons[].delta_seconds', { source: 'analysis', estimated: true }),
  timing('pace_leader', 'Lower median pace', 'Lägre mediantempo', 'text', 'strategy.teammate_comparisons[].faster_driver', { source: 'analysis', estimated: true }),
  timing('comparison_tyres', 'Compounds compared', 'Jämförda blandningar', 'compound_list', 'strategy.compound_crossover_indications[].compounds', { source: 'analysis' }),
  timing('crossover_age', 'Estimated crossover tyre age', 'Beräknad däckålder vid skärning', 'lap_age', 'strategy.compound_crossover_indications[].estimated_tyre_age_laps', { source: 'analysis', estimated: true }),
  timing('observed_age_range', 'Observed tyre-age range', 'Observerat däckåldersintervall', 'lap_range', 'strategy.compound_crossover_indications[].observed_age_range', { source: 'analysis' }),
  timing('crossover_pace', 'Estimated pace at crossover', 'Beräknat tempo vid skärning', 'lap_duration', 'strategy.compound_crossover_indications[].pace_at_crossover', { source: 'analysis', estimated: true }),
  timing('strategy_outcome', 'Observed pit-cycle outcome', 'Observerat utfall av depåcykel', 'strategy_outcome', 'strategy.undercut_overcut_outcomes[].result', { source: 'analysis', estimated: true }),
  timing('comparison_stops', 'Stop laps by driver', 'Depåvarv per förare', 'driver_laps', 'strategy.undercut_overcut_outcomes[].stop_laps', { source: 'analysis' }),
  timing('strategy_pit_loss', 'Estimated stint-change loss', 'Beräknad förlust vid stintbyte', 'seconds_delta', 'strategy.stints[].pit_loss_seconds', { source: 'analysis', estimated: true, comparison: 'previous_stint_pace' }),
  timing('analysis_title', 'Event', 'Händelse', 'text', 'timeline.events[].title', { source: 'analysis', capability: 'analysis' }),
  timing('battle_status', 'Observation', 'Observation', 'battle_status', 'battles[].kind', { source: 'analysis', capability: 'analysis', estimated: true }),
  timing('battle_gap', 'Observed gap', 'Observerat avstånd', 'seconds_duration', 'battles[].gap_seconds', { source: 'analysis', capability: 'analysis' }),
  timing('exchange_positions', 'Before → after', 'Före → efter', 'exchange_positions', 'position_exchanges[].positions_before + positions_after', { source: 'analysis', capability: 'analysis', estimated: true }),
  timing('analysis_description', 'Details', 'Detaljer', 'text', 'timeline.events[].description', { source: 'analysis', capability: 'analysis' }),
  timing('analysis_category', 'Category', 'Kategori', 'text', 'timeline.events[].category', { source: 'analysis', capability: 'analysis' }),
  timing('analysis_source', 'Source / basis', 'Källa / underlag', 'text', 'timeline.events[].supporting_signals', { source: 'analysis', capability: 'analysis' }),
  timing('analysis_quality', 'Evidence score', 'Underlagspoäng', 'confidence', 'timeline.events[].confidence', { source: 'analysis', capability: 'analysis', estimated: true }),
  timing('track_limit_deletions', 'Deleted times', 'Strukna tider', 'integer', 'by_driver.*.deletions', { source: 'track_limits' }),
  timing('track_limit_warning', 'Warning recorded', 'Varning registrerad', 'warning_indicator', 'by_driver.*.warning', { source: 'track_limits' }),
  timing('track_limit_penalty', 'Latest recorded penalty', 'Senast registrerade bestraffning', 'penalty_summary', 'by_driver.*.penalty', { source: 'track_limits' }),
  timing('incident_status', 'Decision / status', 'Beslut / status', 'incident_status', 'incident.category', { source: 'selected_incidents' }),
  timing('incident_drivers', 'Drivers involved', 'Berörda förare', 'text', 'incident.drivers', { source: 'selected_incidents' }),
  timing('incident_lap', 'Lap', 'Varv', 'integer', 'incident.lap', { source: 'selected_incidents' }),
  timing('incident_location', 'Location', 'Plats', 'text', 'incident.location', { source: 'selected_incidents' }),
  timing('incident_reason', 'Reason', 'Orsak', 'text', 'incident.reason', { source: 'selected_incidents' }),
  timing('incident_penalty', 'Penalty', 'Bestraffning', 'text', 'incident.penalty', { source: 'selected_incidents' }),
];
export const WEATHER_FIELDS = [
  ['temperature', 'Air temperature', 'Lufttemperatur', 'temperature', 'number', '°C'],
  ['track_temperature', 'Track temperature', 'Bantemperatur', 'track_temperature', 'number', '°C'],
  ['weather_condition', 'Conditions', 'Väderförhållanden', 'weather_code', 'weather_condition', null],
  ['humidity', 'Humidity', 'Luftfuktighet', 'humidity', 'number', '%'],
  ['wind', 'Wind speed', 'Vindhastighet', 'wind_speed', 'number', 'm/s'],
  ['wind_direction', 'Wind from', 'Vind från', 'wind_from_direction_degrees', 'bearing', '°'],
  ['wind_gusts', 'Wind gusts', 'Vindbyar', 'wind_gusts', 'number', 'm/s'],
  ['cloud_cover', 'Cloud cover', 'Molntäcke', 'cloud_cover', 'number', '%'],
  ['visibility', 'Visibility', 'Sikt', 'visibility', 'number', 'm'],
  ['pressure', 'Air pressure', 'Lufttryck', 'pressure', 'number', 'hPa'],
  ['rain_probability', 'Rain probability', 'Regnrisk', 'precipitation_probability', 'number', '%'],
  ['precipitation', 'Precipitation amount', 'Nederbördsmängd', 'precipitation', 'number', 'mm'],
  ['rainfall', 'Rain detected', 'Regn registrerat', 'rainfall', 'rain_indicator', null],
].map(([id, en, sv, path, type, unit]) => basic(id, en, sv, ['track_temperature', 'pressure', 'rainfall'].includes(id) ? 'track_weather' : 'weather', path, type, { unit, timestamps: { source: 'not_provided', received: 'not_provided', updated: 'entity.last_updated', displayed: 'snapshot' } }));
export const FIELDS = Object.fromEntries([
  ...SESSION_FIELDS,
  ...RESULT_FIELDS,
  ...TIMING_FIELDS,
  basic('meeting', 'Grand Prix', 'Grand Prix', 'next_race', 'race_name'),
  basic('circuit', 'Circuit', 'Bana', 'next_race', 'circuit_name'),
  basic('country', 'Country', 'Land', 'next_race', 'circuit_country'),
  basic('countdown', 'Countdown', 'Nedräkning', 'next_race', 'race_start_utc', 'countdown'),
  basic('circuit_map', 'Circuit map', 'Bankarta', 'next_race', 'circuit_map_url', 'image'),
  basic('circuit_history', 'Circuit history', 'Banhistorik', 'next_race', 'defending_winner + defending_pole_sitter + circuit history attributes', 'history'),
  basic('session', 'Session', 'Session', 'current_session', 'state', 'text', { modes: ['live', 'replay'], identity: ['entry', 'session'], generation: 'session' }),
  basic('session_status', 'Session status', 'Sessionsstatus', 'session_status', 'state', 'status', { modes: ['live', 'replay'], generation: 'session' }),
  basic('lap_progress', 'Lap progress', 'Varvförlopp', 'race_lap_count', 'state + total_laps', 'text', { modes: ['live', 'replay'], spoiler: true, identity: ['entry', 'session'], generation: 'session' }),
  ...[['session_time_elapsed', 'Session time elapsed', 'Förfluten sessionstid'], ['session_time_remaining', 'Session time remaining', 'Återstående sessionstid'], ['race_time_to_three_hour_limit', 'Time to three-hour limit', 'Tid till tretimmarsgränsen']].map(([id, en, sv]) => basic(id, en, sv, id, 'value_seconds', 'session_clock', { modes: ['live', 'replay'], spoiler: true, identity: ['entry', 'session', 'part'], generation: 'session', timestamps: { source: 'last_server_utc', received: 'not_provided', updated: 'entity.last_updated', displayed: 'snapshot' } })),
  basic('track_status', 'Track status', 'Banstatus', 'track_status', 'state', 'flag', { modes: ['live', 'replay'], spoiler: true, generation: 'session' }),
  basic('schedule', 'Schedule', 'Schema', 'next_race', '*_start_utc', 'schedule'),
  ...WEATHER_FIELDS,
  basic('event_time', 'Time', 'Tid', 'race_control_log', 'utc', 'datetime', { modes: ['live', 'replay'], spoiler: true, generation: 'session', presentations: ['timeline'] }),
  basic('track_map', 'Track map', 'Bankarta', 'track_map', 'track.points + drivers', 'map', { modes: ['live', 'replay'], capability: 'extended_timing', spoiler: true, generation: 'session', presentations: ['map', 'list'] }),
  basic('map_drivers', 'Driver positions list', 'Lista över förarpositioner', 'track_map', 'drivers', 'list', { modes: ['live', 'replay'], capability: 'extended_timing', spoiler: true, generation: 'session', presentations: ['list'] }),
  ...[['replay_selection', 'Replay selection', 'Val av replay'], ['replay_transport', 'Playback controls', 'Uppspelningskontroller'], ['replay_progress', 'Playback progress', 'Uppspelningsposition']].map(([id, en, sv]) => basic(id, en, sv, 'replay_player', 'selected_session + playback_position_s + playback_total_s', 'replay_control', { modes: ['replay'], identity: ['entry', 'replay_session'], timestamps: { source: 'not_provided', updated_position: 'media_position_updated_at', received: 'not_provided', updated: 'entity.last_updated', displayed: 'snapshot' } })),
  ...[['speed', 'Speed', 'Hastighet', 'km/h'], ['throttle', 'Throttle', 'Gas', '%'], ['brake', 'Brake signal', 'Bromssignal', null], ['gear', 'Gear', 'Växel', null], ['drs', 'DRS code', 'DRS-kod', null], ['rpm', 'Engine speed', 'Motorvarvtal', 'rpm'], ['delta_s', 'Estimated time delta', 'Uppskattat tidsdelta', 's']].map(([id, en, sv, unit]) => basic(`telemetry_${id}`, en, sv, 'analysis/telemetry_compare', `series[].samples[].${id}`, 'series', { unit, modes: ['replay'], spoiler: true, capability: 'replay_telemetry', estimated: id === 'delta_s', identity: ['entry', 'replay_session', 'driver', 'lap', 'sample'], timestamps: { source: 'not_provided', position: 'time_s', received: 'request.received_at', displayed: 'snapshot' }, presentations: ['chart', 'table'] })),
  basic('lap_series', 'Recorded lap history', 'Registrerad varvhistorik', 'driver_positions', 'drivers[].laps', 'series', { modes: ['live', 'replay'], spoiler: true, identity: ['entry', 'session', 'driver', 'lap'], presentations: ['chart', 'table'], timestamps: { source: 'not_provided', position: 'lap_number', received: 'not_provided', updated: 'entity.last_updated', displayed: 'snapshot' } }),
  basic('progression', 'Progression', 'Utveckling', 'selected_points_progression', 'rounds + competitors.*', 'series', { modes: ['standings'], spoiler: true, presentations: ['chart', 'table'], identity: ['entry', 'season', 'round', 'competitor'] }),
  basic('document_title', 'Document', 'Dokument', 'fia_documents', 'documents[].name', 'link', { spoiler: true }),
  basic('document_time', 'Published', 'Publicerad', 'fia_documents', 'documents[].published', 'datetime', { spoiler: true }),
  basic('document_number', 'Document number', 'Dokumentnummer', 'fia_documents', 'documents[].document_number', 'integer', { spoiler: true }),
  basic('message', 'Message', 'Meddelande', 'race_control_log', 'message', 'text', { modes: ['live', 'replay'], spoiler: true, presentations: ['timeline'], filterable: true }),
].map(field => [field.id, field]));

const module = (id, en, sv, fields, options, sources, extra = {}) => ({
  id, label: { en, sv }, fields, options, sources, version: VERSION, ...extra,
});
export const MODULES = {
  overview: module('overview', 'Overview', 'Översikt', ['meeting', 'circuit', 'country', 'countdown', 'circuit_map', 'circuit_history', 'session', 'session_status', 'lap_progress', 'track_status', 'session_time_elapsed', 'session_time_remaining', 'race_time_to_three_hour_limit'], {
    layout_mode: { type: 'enum', values: ['auto', 'compact', 'full'], default: 'auto', label: { en: 'Layout mode', sv: 'Layoutläge' } },
  }, ['next_race', 'current_session', 'session_status', 'race_lap_count', 'track_status', 'session_time_elapsed', 'session_time_remaining', 'race_time_to_three_hour_limit'], { defaultFields: ['meeting', 'circuit', 'countdown'] }),
  calendar: module('calendar', 'Schedule', 'Schema', ['schedule'], {
    details: { type: 'list', values: ['round', 'circuit', 'location'], default: [], label: { en: 'Event details', sv: 'Tävlingsuppgifter' } },
    past: { type: 'enum', values: ['show', 'dim', 'hide'], default: 'show', label: { en: 'Past session starts', sv: 'Passerade sessionsstarter' } },
    next: { type: 'enum', values: ['none', 'label'], default: 'none', label: { en: 'Next session marker', sv: 'Markera nästa session' } },
    range: { type: 'enum', values: ['weekend', 'season'], default: 'weekend', label: { en: 'Show', sv: 'Visa' } },
    timezone: { type: 'enum', values: ['home', 'circuit', 'utc'], default: 'home', label: { en: 'Time zone', sv: 'Tidszon' } },
    show_track_time: { type: 'boolean', default: false, label: { en: 'Also show circuit time', sv: 'Visa även bantid' } },
    sessions: { type: 'list', values: ['practice_1', 'practice_2', 'practice_3', 'qualifying', 'sprint_qualifying', 'sprint', 'race'], default: ['practice_1', 'practice_2', 'practice_3', 'qualifying', 'sprint_qualifying', 'sprint', 'race'], label: { en: 'Sessions', sv: 'Sessioner' } },
  }, ['next_race', 'current_season']),
  timing: module('timing', 'Timing', 'Timing', TIMING_FIELDS.map(field => field.id), {
    profile: { type: 'enum', values: ['custom', 'auto', 'practice', 'qualifying', 'sprint_qualifying', 'sprint', 'race'], default: 'custom', label: { en: 'Column profile', sv: 'Kolumnprofil' } },
    sort: { type: 'enum', values: ['position', 'best_lap', 'driver'], default: 'position', label: { en: 'Sort by', sv: 'Sortera efter' } },
    direction: { type: 'enum', values: ['asc', 'desc'], default: 'asc', label: { en: 'Direction', sv: 'Ordning' } },
    rows: { type: 'integer', min: 1, max: 100, default: 30, label: { en: 'Maximum drivers', sv: 'Max antal förare' } },
    sectors: { type: 'enum', values: ['coherent', 'latest'], default: 'coherent', label: { en: 'Sector laps', sv: 'Sektorernas varv' } },
    history: { type: 'integer', min: 0, max: 30, default: 0, label: { en: 'Recent lap columns', sv: 'Kolumner för senaste varv' } },
    show_gap_toggle: { type: 'boolean', default: false, label: { en: 'Show live gap toggle', sv: 'Visa val av liveavstånd' } },
  }, ['driver_positions', 'driver_list', 'current_tyres', 'current_session', 'session_status'], { defaultFields: ['position', 'driver', 'gap', 'last_lap', 'sector_1', 'sector_2', 'sector_3', 'tyre'] }),
  race_control: module('race_control', 'Race Control', 'Race Control', ['event_time', 'message'], {
    presentation: { type: 'enum', values: ['list', 'latest_message'], default: 'list', label: { en: 'Message view', sv: 'Meddelandevy' } },
    global_messages: { type: 'enum', values: ['include', 'hide'], default: 'include', label: { en: 'Session-wide messages with driver focus', sv: 'Sessionsmeddelanden med förarfokus' } },
    limit: { type: 'integer', min: 1, max: 500, default: 30, label: { en: 'Messages to show', sv: 'Antal meddelanden' } },
    order: { type: 'enum', values: ['newest', 'oldest'], default: 'newest', label: { en: 'Order', sv: 'Ordning' } },
    search: { type: 'text', default: '', label: { en: 'Message contains', sv: 'Meddelandet innehåller' } },
    categories: { type: 'list', values: ['Flag', 'SafetyCar', 'Drs', 'Other'], default: [], label: { en: 'Categories (empty = all)', sv: 'Kategorier (tomt = alla)' } },
    list_max_height: { type: 'integer', min: 0, max: 2000, default: 600, label: { en: 'List height in pixels', sv: 'Listhöjd i pixlar' } },
    hide_blue_flags: { type: 'boolean', default: false, label: { en: 'Hide blue-flag messages', sv: 'Dölj meddelanden om blåflagg' } },
    hide_track_limits: { type: 'boolean', default: false, label: { en: 'Hide track-limits messages', sv: 'Dölj meddelanden om track limits' } },
    show_fia_logo: { type: 'boolean', default: true, label: { en: 'Show FIA mark', sv: 'Visa FIA-markering' } },
    min_display_time: { type: 'integer', min: 0, max: 30, default: 0, label: { en: 'Minimum display time in seconds', sv: 'Minsta visningstid i sekunder' } },
    show_clear_button: { type: 'boolean', default: true, label: { en: 'Show clear button', sv: 'Visa tömningsknapp' } },
  }, ['race_control', 'current_session'], { stream: 'race_control' }),
  results: module('results', 'Results', 'Resultat', ['result_position', 'driver', 'team', 'grid_position', 'position_change', 'laps', 'result_time', 'result_status', 'points', 'qualifying_position', 'qualifying_time', 'grid_delta', 'qualifying_segment', 'qualifying_delta'], {
    content: { type: 'enum', values: ['latest_race', 'race_results', 'sprint_results', 'starting_grid'], default: 'latest_race', label: { en: 'Result content', sv: 'Resultatinnehåll' } },
    round: { type: 'source_choice', default: '', label: { en: 'Round', sv: 'Deltävling' } },
    sort: { type: 'enum', values: ['result_position', 'grid_position', 'driver', 'points'], default: 'result_position', label: { en: 'Sort by', sv: 'Sortera efter' } },
    direction: { type: 'enum', values: ['asc', 'desc'], default: 'asc', label: { en: 'Direction', sv: 'Ordning' } },
    rows: { type: 'integer', min: 1, max: 100, default: 30, label: { en: 'Maximum rows', sv: 'Max antal rader' } },
    presentation: { type: 'enum', values: ['table', 'grid'], default: 'table', label: { en: 'Presentation', sv: 'Visning' } },
    show_selector: { type: 'boolean', default: true, label: { en: 'Show round selector', sv: 'Visa tävlingsval' } },
    show_context: { type: 'boolean', default: true, label: { en: 'Show event details', sv: 'Visa tävlingsuppgifter' } },
    show_status: { type: 'boolean', default: true, label: { en: 'Show grid status', sv: 'Visa status för startuppställning' } },
    show_source: { type: 'boolean', default: false, label: { en: 'Show source', sv: 'Visa källa' } },
    show_session_type_badge: { type: 'boolean', default: true, label: { en: 'Show session type', sv: 'Visa sessionstyp' } },
    spoiler_placeholder: { type: 'text', default: '', label: { en: 'Spoiler placeholder', sv: 'Platshållare för spoilers' } },
    driver_image_type: { type: 'enum', values: ['team_logo', 'headshot'], default: 'team_logo', label: { en: 'Driver image', sv: 'Förarbild' } },
  }, ['last_race_results', 'season_results', 'sprint_results', 'starting_grid'], { spoiler: true, focus: ['driver', 'team'], defaultFields: ['result_position', 'driver', 'team', 'result_time', 'points'], fieldDefinitions: {
    driver: { ...FIELDS.driver, source: 'selected_result', path: 'results[].driver', modes: ['results'], identity: ['entry', 'season', 'round', 'session', 'driver'] },
    team: { ...FIELDS.team, source: 'selected_result', path: 'results[].constructor', modes: ['results'], identity: ['entry', 'season', 'round', 'session', 'team'] },
    laps: { ...FIELDS.laps, source: 'selected_result', path: 'results[].laps', modes: ['results'] },
  } }),
  standings: module('standings', 'Championship', 'Mästerskap', ['result_position', 'driver', 'team', 'points', 'wins', 'predicted_position', 'predicted_points', 'points_change'], {
    competitors: { type: 'enum', values: ['drivers', 'teams'], default: 'drivers', label: { en: 'Championship', sv: 'Mästerskap' } },
    sort: { type: 'enum', values: ['result_position', 'points', 'wins', 'driver', 'team', 'predicted_position', 'predicted_points'], default: 'result_position', label: { en: 'Sort by', sv: 'Sortera efter' } },
    direction: { type: 'enum', values: ['asc', 'desc'], default: 'asc', label: { en: 'Direction', sv: 'Ordning' } },
    rows: { type: 'integer', min: 1, max: 100, default: 30, label: { en: 'Maximum rows', sv: 'Max antal rader' } },
    show_mode_badge: { type: 'boolean', default: true, label: { en: 'Show standings status', sv: 'Visa status för mästerskapet' } },
    show_availability_notice: { type: 'boolean', default: true, label: { en: 'Explain projection availability', sv: 'Förklara prognostillgänglighet' } },
    spoiler_placeholder: { type: 'text', default: '', label: { en: 'Spoiler placeholder', sv: 'Platshållare för spoilers' } },
    driver_image_type: { type: 'enum', values: ['team_logo', 'headshot'], default: 'team_logo', label: { en: 'Driver image', sv: 'Förarbild' } },
  }, ['driver_standings', 'constructor_standings', 'championship_prediction_drivers', 'championship_prediction_teams'], { spoiler: true, focus: ['driver', 'team'], defaultFields: ['result_position', 'driver', 'team', 'points', 'wins'], fieldDefinitions: Object.fromEntries(['result_position', 'driver', 'team', 'points', 'wins'].map(id => [id, { ...FIELDS[id], source: 'selected_standings', path: `standings[].${id}`, modes: ['standings'], identity: ['entry', 'season', 'round', 'competitor'] }])) }),
  archive: module('archive', 'Historical archive', 'Historiskt arkiv', ['result_position', 'driver', 'team', 'grid_position', 'position_change', 'laps', 'result_time', 'result_status', 'points', 'q1_time', 'q2_time', 'q3_time', 'lap_series'], {
    year: { type: 'integer', min: 1950, max: 2200, default: new Date().getUTCFullYear(), label: { en: 'Year', sv: 'År' } },
    round: { type: 'source_choice', default: '', label: { en: 'Grand Prix', sv: 'Grand Prix' } },
    session_key: { type: 'source_choice', default: '', label: { en: 'Session', sv: 'Session' } },
    profile: { type: 'enum', values: ['auto', 'custom'], default: 'auto', label: { en: 'Column profile', sv: 'Kolumnprofil' } },
    content: { type: 'enum', values: ['classification', 'lap_time', 'lap_position'], default: 'classification', label: { en: 'Archive view', sv: 'Arkivvy' } },
    selected: { type: 'source_list', default: [], label: { en: 'Drivers (empty = classification order)', sv: 'Förare (tomt = resultatordning)' } },
    presentation: { type: 'enum', values: ['chart', 'table', 'both'], default: 'chart', label: { en: 'Presentation', sv: 'Visning' } },
    show_session_selector: { type: 'boolean', default: true, label: { en: 'Show archive selectors', sv: 'Visa arkivval' } },
    show_session_type_badge: { type: 'boolean', default: true, label: { en: 'Show session type', sv: 'Visa sessionstyp' } },
    spoiler_placeholder: { type: 'text', default: '', label: { en: 'Spoiler placeholder', sv: 'Platshållare för spoilers' } },
    start_lap: { type: 'integer', min: 0, max: 500, default: 0, label: { en: 'First lap (0 = first recorded)', sv: 'Första varv (0 = första registrerade)' } },
    end_lap: { type: 'integer', min: 0, max: 500, default: 0, label: { en: 'Last lap (0 = last recorded)', sv: 'Sista varv (0 = sista registrerade)' } },
    series_limit: { type: 'integer', min: 1, max: 100, default: 5, label: { en: 'Maximum chart drivers', sv: 'Max antal förare i diagram' } },
    show_points: { type: 'boolean', default: true, label: { en: 'Show chart points', sv: 'Visa diagrampunkter' } },
    show_round_labels: { type: 'boolean', default: true, label: { en: 'Show lap labels', sv: 'Visa varvetiketter' } },
    chart_height: { type: 'integer', min: 300, max: 720, default: 420, label: { en: 'Chart height', sv: 'Diagramhöjd' } },
    sort: { type: 'enum', values: ['result_position', 'grid_position', 'driver', 'points'], default: 'result_position', label: { en: 'Sort by', sv: 'Sortera efter' } },
    direction: { type: 'enum', values: ['asc', 'desc'], default: 'asc', label: { en: 'Direction', sv: 'Ordning' } },
    rows: { type: 'integer', min: 1, max: 100, default: 30, label: { en: 'Maximum rows', sv: 'Max antal rader' } },
  }, ['history'], { spoiler: true, defaultFields: ['result_position', 'driver', 'team', 'result_time', 'points'] }),
  telemetry: module('telemetry', 'Replay telemetry', 'Replaytelemetri', ['telemetry_speed', 'telemetry_throttle', 'telemetry_brake', 'telemetry_gear', 'telemetry_drs', 'telemetry_rpm', 'telemetry_delta_s'], {
    selected: { type: 'lap_selections', default: [], label: { en: 'Selected laps', sv: 'Valda varv' } },
    session_id: { type: 'text', default: '', label: { en: 'Saved replay session', sv: 'Sparad replaysession' } },
    axis: { type: 'enum', values: ['time_s', 'distance'], default: 'time_s', label: { en: 'Horizontal axis', sv: 'Horisontell axel' } },
    presentation: { type: 'enum', values: ['chart', 'table', 'both'], default: 'chart', label: { en: 'Presentation', sv: 'Visning' } },
    show_explanation: { type: 'boolean', default: true, label: { en: 'Show About section', sv: 'Visa Om-sektion' } },
  }, ['replay_status', 'replay_player', 'analysis/telemetry_catalog', 'analysis/telemetry_compare'], { spoiler: true, defaultFields: ['telemetry_speed', 'telemetry_throttle', 'telemetry_brake'] }),
  replay: module('replay', 'Replay', 'Replay', ['replay_selection', 'replay_transport', 'replay_progress'], {
    display: { type: 'enum', values: ['full', 'compact'], default: 'full', label: { en: 'Replay layout', sv: 'Replaylayout' } },
    secondary_selects: { type: 'boolean', default: true, label: { en: 'Show year and reference choices', sv: 'Visa val för år och referens' } },
    start_reference: { type: 'boolean', default: true, label: { en: 'Show start reference', sv: 'Visa startreferens' } },
    seek_controls: { type: 'boolean', default: true, label: { en: 'Show seek controls', sv: 'Visa sökkontroller' } },
    refresh: { type: 'boolean', default: true, label: { en: 'Show refresh action', sv: 'Visa uppdateringsåtgärd' } },
    status_details: { type: 'boolean', default: true, label: { en: 'Show scope details', sv: 'Visa information om räckvidd' } },
    show_button_labels: { type: 'boolean', default: true, label: { en: 'Show button labels', sv: 'Visa knapptexter' } },
  }, ['replay_status', 'replay_player', 'replay_year_select', 'replay_session_select', 'replay_start_reference', 'replay_load', 'replay_refresh']),
  lap_chart: module('lap_chart', 'Lap history chart', 'Diagram över varvhistorik', ['lap_series'], {
    metric: { type: 'enum', values: ['lap_time', 'lap_change'], default: 'lap_time', label: { en: 'Measure', sv: 'Mått' } },
    presentation: { type: 'enum', values: ['chart', 'table', 'both'], default: 'chart', label: { en: 'Presentation', sv: 'Visning' } },
    selected: { type: 'source_list', default: [], label: { en: 'Drivers (empty = session order)', sv: 'Förare (tomt = sessionsordning)' } },
    start_lap: { type: 'integer', min: 0, max: 500, default: 0, label: { en: 'First lap (0 = first observed)', sv: 'Första varv (0 = första observerade)' } },
    end_lap: { type: 'integer', min: 0, max: 500, default: 0, label: { en: 'Last lap (0 = last observed)', sv: 'Sista varv (0 = sista observerade)' } },
    series_limit: { type: 'integer', min: 1, max: 30, default: 5, label: { en: 'Maximum drivers', sv: 'Max antal förare' } },
  }, ['driver_positions', 'driver_list', 'current_session'], { spoiler: true, focus: ['driver', 'team'] }),
  progression: module('progression', 'Season progression', 'Säsongsutveckling', ['progression'], {
    competitors: { type: 'enum', values: ['drivers', 'teams'], default: 'drivers', label: { en: 'Competitors', sv: 'Deltagare' } },
    metric: { type: 'enum', values: ['cumulative_points', 'points_per_round', 'wins_per_round'], default: 'cumulative_points', label: { en: 'Measure', sv: 'Mått' } },
    presentation: { type: 'enum', values: ['chart', 'table', 'both'], default: 'chart', label: { en: 'Presentation', sv: 'Visning' } },
    selected: { type: 'source_list', default: [], label: { en: 'Drivers or teams (empty = leaders)', sv: 'Förare eller team (tomt = ledarna)' } },
    start_round: { type: 'source_choice', default: '', label: { en: 'First round', sv: 'Första deltävling' } },
    end_round: { type: 'source_choice', default: '', label: { en: 'Last round', sv: 'Sista deltävling' } },
    series_limit: { type: 'integer', min: 1, max: 30, default: 5, label: { en: 'Maximum series', sv: 'Max antal serier' } },
    show_legend: { type: 'boolean', default: true, label: { en: 'Show legend', sv: 'Visa teckenförklaring' } },
    legend_position: { type: 'enum', values: ['bottom', 'left', 'right'], default: 'bottom', label: { en: 'Legend position', sv: 'Teckenförklaringens placering' } },
    show_legend_points: { type: 'boolean', default: true, label: { en: 'Show points in legend', sv: 'Visa poäng i teckenförklaringen' } },
    show_points: { type: 'boolean', default: true, label: { en: 'Show chart points', sv: 'Visa diagrampunkter' } },
    show_round_labels: { type: 'boolean', default: true, label: { en: 'Show round labels', sv: 'Visa deltävlingarnas etiketter' } },
    show_future_rounds: { type: 'boolean', default: true, label: { en: 'Show future rounds', sv: 'Visa framtida deltävlingar' } },
    chart_height: { type: 'integer', min: 240, max: 520, default: 320, label: { en: 'Chart height', sv: 'Diagramhöjd' } },
  }, ['driver_points_progression', 'constructor_points_progression'], { spoiler: true, focus: ['driver', 'team'] }),
  documents: module('documents', 'FIA documents', 'FIA-dokument', ['document_number', 'document_title', 'document_time'], {
    presentation: { type: 'enum', values: ['list', 'latest'], default: 'list', label: { en: 'Document view', sv: 'Dokumentvy' } },
    search: { type: 'text', default: '', label: { en: 'Title contains', sv: 'Rubriken innehåller' } },
    order: { type: 'enum', values: ['newest', 'oldest'], default: 'newest', label: { en: 'Order', sv: 'Ordning' } },
    limit: { type: 'integer', min: 1, max: 300, default: 15, label: { en: 'Documents to show', sv: 'Antal dokument' } },
    list_max_height: { type: 'integer', min: 0, max: 2000, default: 0, label: { en: 'List height in pixels (0 = automatic)', sv: 'Listhöjd i pixlar (0 = automatisk)' } },
    open_new_tab: { type: 'boolean', default: true, label: { en: 'Open links in a new tab', sv: 'Öppna länkar i en ny flik' } },
    document_coloring: { type: 'boolean', default: true, label: { en: 'Color-code document rows', sv: 'Färgkoda dokumentrader' } },
    show_document_type: { type: 'boolean', default: true, label: { en: 'Show document type', sv: 'Visa dokumenttyp' } },
    show_fia_logo: { type: 'boolean', default: true, label: { en: 'Show FIA mark', sv: 'Visa FIA-markering' } },
    show_pdf_icon: { type: 'boolean', default: true, label: { en: 'Show PDF icon', sv: 'Visa PDF-ikon' } },
    show_count: { type: 'boolean', default: true, label: { en: 'Show document count', sv: 'Visa antal dokument' } },
    show_race_context: { type: 'boolean', default: true, label: { en: 'Show race context', sv: 'Visa tävlingssammanhang' } },
    show_latest_badge: { type: 'boolean', default: true, label: { en: 'Show latest badge', sv: 'Visa senaste-markering' } },
  }, ['fia_documents'], { spoiler: true }),
  map: module('map', 'Track map', 'Bankarta', ['track_map', 'map_drivers'], {
    labels: { type: 'enum', values: ['code', 'number', 'off'], default: 'code', label: { en: 'Driver labels', sv: 'Föraretiketter' } },
    focus: { type: 'enum', values: ['highlight', 'filter'], default: 'highlight', label: { en: 'Driver focus', sv: 'Förarfokus' } },
    orientation: { type: 'enum', values: ['source', 'raw'], default: 'source', label: { en: 'Orientation', sv: 'Orientering' } },
    vertical: { type: 'enum', values: ['normal', 'flipped'], default: 'flipped', label: { en: 'Vertical axis', sv: 'Vertikal axel' } },
    layout_mode: { type: 'enum', values: ['auto', 'compact', 'full'], default: 'auto', label: { en: 'Layout mode', sv: 'Layoutläge' } },
    show_footer: { type: 'boolean', default: true, label: { en: 'Show source footer', sv: 'Visa källfot' } },
    show_session_info: { type: 'boolean', default: true, label: { en: 'Show session information', sv: 'Visa sessionsinformation' } },
    show_lap_progress: { type: 'boolean', default: true, label: { en: 'Show lap progress', sv: 'Visa varvförlopp' } },
    show_track_status: { type: 'boolean', default: true, label: { en: 'Show track status', sv: 'Visa banstatus' } },
    track_status_line_mode: { type: 'enum', values: ['accent', 'full', 'off'], default: 'accent', label: { en: 'Track-status line', sv: 'Banstatuslinje' } },
    show_driver_count: { type: 'boolean', default: true, label: { en: 'Show driver count', sv: 'Visa antal förare' } },
  }, ['track_map', 'current_session', 'race_lap_count', 'track_status'], { spoiler: true, stream: 'track_map', focus: ['driver', 'team'] }),
  battles: module('battles', 'Battles and position changes', 'Närkamper och positionsbyten', ['battle_status', 'incident_drivers', 'battle_gap', 'exchange_positions', 'analysis_source', 'analysis_quality'], {
    content: { type: 'enum', values: ['active_battles', 'battle_history', 'position_exchanges'], default: 'active_battles', label: { en: 'Observations', sv: 'Observationer' } },
    presentation: { type: 'enum', values: ['list', 'table'], default: 'list', label: { en: 'Presentation', sv: 'Presentation' } },
    kinds: { type: 'list', values: ['battle_started', 'battle_ended', 'position_exchange', 'likely_on_track_overtake'], default: [], label: { en: 'Kinds (empty = all)', sv: 'Typer (tomt = alla)' } },
    minimum_score: { type: 'integer', min: 0, max: 100, default: 0, label: { en: 'Minimum evidence score (%)', sv: 'Lägsta underlagspoäng (%)' } },
    order: { type: 'enum', values: ['newest', 'oldest'], default: 'newest', label: { en: 'Recorded order', sv: 'Registreringsordning' } },
    rows: { type: 'integer', min: 1, max: 500, default: 20, label: { en: 'Maximum rows', sv: 'Max antal rader' } },
    show_explanation: { type: 'boolean', default: true, label: { en: 'Show About section', sv: 'Visa Om-sektion' } },
  }, ['analysis'], { spoiler: true, stream: 'analysis', focus: ['driver', 'team'] }),
  strategy: module('strategy', 'Strategy analysis', 'Strategianalys', ['driver', 'team', 'tyre', 'stint_number', 'stint_first_lap', 'stint_last_lap', 'stint_start_age', 'clean_pace', 'raw_pace', 'degradation', 'clean_samples', 'raw_samples', 'excluded_samples', 'exclusion_reasons', 'strategy_pit_loss', 'compound_gap', 'analysis_quality', 'incident_drivers', 'comparison_pace', 'comparison_gap', 'pace_leader', 'comparison_tyres', 'crossover_age', 'observed_age_range', 'crossover_pace', 'strategy_outcome', 'comparison_stops', 'exchange_positions', 'analysis_source'], {
    content: { type: 'enum', values: ['stints', 'compound_comparison', 'teammates', 'crossover', 'pit_outcomes'], default: 'stints', label: { en: 'Analysis content', sv: 'Analysinnehåll' } },
    compounds: { type: 'list', values: ['SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET', 'UNKNOWN'], default: [], label: { en: 'Compounds (empty = all)', sv: 'Blandningar (tomt = alla)' } },
    minimum_score: { type: 'integer', min: 0, max: 100, default: 0, label: { en: 'Minimum evidence score (%)', sv: 'Lägsta underlagspoäng (%)' } },
    presentation: { type: 'enum', values: ['table', 'both', 'chart'], default: 'table', label: { en: 'Stint presentation', sv: 'Stintvisning' } },
    minimum_clean_laps: { type: 'integer', min: 0, max: 500, default: 0, label: { en: 'Minimum clean laps per row', sv: 'Minst antal rena varv per rad' } },
    sort: { type: 'enum', values: ['driver', 'stint_number', 'clean_pace', 'clean_samples', 'degradation', 'analysis_quality'], default: 'driver', label: { en: 'Sort by', sv: 'Sortera efter' } },
    direction: { type: 'enum', values: ['asc', 'desc'], default: 'asc', label: { en: 'Direction', sv: 'Ordning' } },
    rows: { type: 'integer', min: 1, max: 500, default: 30, label: { en: 'Maximum rows', sv: 'Max antal rader' } },
    show_explanation: { type: 'boolean', default: true, label: { en: 'Show About section', sv: 'Visa Om-sektion' } },
  }, ['analysis'], { spoiler: true, stream: 'analysis', focus: ['driver', 'team'], fieldDefinitions: {
    analysis_quality: { ...FIELDS.analysis_quality, path: 'strategy.stints[].confidence' },
    compound_gap: { ...FIELDS.compound_gap, source: 'analysis', path: 'strategy.compound_comparison[].delta_to_fastest', estimated: true },
  } }),
  timeline: module('timeline', 'Session timeline', 'Sessionens tidslinje', ['event_time', 'incident_drivers', 'incident_lap', 'analysis_title', 'analysis_description', 'analysis_category', 'analysis_source', 'analysis_quality'], {
    categories: { type: 'list', values: ['session', 'track_status', 'race_control', 'lap_control', 'investigation', 'lap', 'pit', 'weather', 'radio', 'position', 'battle', 'classification'], default: [], label: { en: 'Categories (empty = all)', sv: 'Kategorier (tomt = alla)' } },
    search: { type: 'text', default: '', label: { en: 'Text contains', sv: 'Texten innehåller' } },
    order: { type: 'enum', values: ['newest', 'oldest'], default: 'newest', label: { en: 'Order', sv: 'Ordning' } },
    rows: { type: 'integer', min: 1, max: 500, default: 30, label: { en: 'Maximum events', sv: 'Max antal händelser' } },
    presentation: { type: 'enum', values: ['list', 'table'], default: 'list', label: { en: 'Presentation', sv: 'Visning' } },
  }, ['analysis'], { spoiler: true, stream: 'analysis', focus: ['driver', 'team'], defaultFields: ['event_time', 'analysis_title', 'incident_drivers', 'incident_lap', 'analysis_source'], fieldDefinitions: {
    event_time: { ...FIELDS.event_time, source: 'analysis', path: 'timeline.events[].occurred_at' },
    incident_drivers: { ...FIELDS.incident_drivers, source: 'analysis', path: 'timeline.events[].driver_numbers' },
    incident_lap: { ...FIELDS.incident_lap, source: 'analysis', path: 'timeline.events[].lap_number' },
  } }),
  tyres: module('tyres', 'Tyres', 'Däck', ['position', 'driver', 'team', 'tyre', 'tyre_age', 'tyre_new', 'compound_best', 'compound_gap', 'compound_laps', 'new_sets', 'total_stints', 'best_runs'], {
    content: { type: 'enum', values: ['current', 'statistics'], default: 'current', label: { en: 'Tyre content', sv: 'Däckinnehåll' } },
    compounds: { type: 'list', values: ['SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET', 'UNKNOWN'], default: [], label: { en: 'Compounds (empty = all)', sv: 'Blandningar (tomt = alla)' } },
    sort: { type: 'enum', values: ['position', 'driver', 'tyre_age', 'compound_best', 'compound_laps'], default: 'position', label: { en: 'Sort by', sv: 'Sortera efter' } },
    direction: { type: 'enum', values: ['asc', 'desc'], default: 'asc', label: { en: 'Direction', sv: 'Ordning' } },
    rows: { type: 'integer', min: 1, max: 100, default: 30, label: { en: 'Maximum rows', sv: 'Max antal rader' } },
    show_compound_name: { type: 'boolean', default: true, label: { en: 'Show compound name', sv: 'Visa blandningsnamn' } },
    best_times_limit: { type: 'integer', min: 1, max: 500, default: 3, label: { en: 'Fastest stints per compound', sv: 'Snabbaste stintar per blandning' } },
  }, ['current_tyres', 'tyre_statistics', 'driver_list'], { spoiler: true, focus: ['driver', 'team'] }),
  pit_stops: module('pit_stops', 'Pit stops', 'Depåstopp', ['driver', 'team', 'status', 'pit_count', 'stop_lap', 'stop_time', 'lane_time', 'pit_delta', 'event_time'], {
    content: { type: 'enum', values: ['latest_stop', 'all_stops'], default: 'latest_stop', label: { en: 'Stop history', sv: 'Stopphistorik' } },
    sort: { type: 'enum', values: ['event_time', 'driver', 'stop_lap', 'stop_time', 'lane_time', 'pit_delta'], default: 'event_time', label: { en: 'Sort by', sv: 'Sortera efter' } },
    direction: { type: 'enum', values: ['asc', 'desc'], default: 'desc', label: { en: 'Direction', sv: 'Ordning' } },
    rows: { type: 'integer', min: 1, max: 500, default: 30, label: { en: 'Maximum rows', sv: 'Max antal rader' } },
    show_availability_notice: { type: 'boolean', default: true, label: { en: 'Explain F1TV availability', sv: 'Förklara F1TV-tillgänglighet' } },
  }, ['pitstops', 'driver_list', 'driver_positions', 'f1tv_token_status'], { spoiler: true, focus: ['driver', 'team'], defaultFields: ['driver', 'status', 'stop_lap', 'stop_time', 'lane_time'], fieldDefinitions: {
    status: { ...FIELDS.status, source: 'driver_positions', path: 'drivers[].status', capability: 'public_timing' },
    event_time: { ...FIELDS.event_time, source: 'pitstops', path: 'cars.*.stops[].timestamp', capability: 'extended_timing' },
  } }),
  incidents: module('incidents', 'Incidents', 'Incidenter', ['incident_status', 'incident_drivers', 'event_time', 'incident_lap', 'incident_location', 'incident_reason', 'incident_penalty', 'driver', 'team', 'track_limit_deletions', 'track_limit_warning', 'track_limit_penalty'], {
    content: { type: 'enum', values: ['investigations', 'track_limits', 'track_limits_summary'], default: 'investigations', label: { en: 'Incident content', sv: 'Incidentinnehåll' } },
    summary_sort: { type: 'enum', values: ['track_limit_deletions', 'driver'], default: 'track_limit_deletions', label: { en: 'Summary order', sv: 'Sammanställningens ordning' } },
    presentation: { type: 'enum', values: ['list', 'table'], default: 'list', label: { en: 'Presentation', sv: 'Visning' } },
    categories: { type: 'list', values: ['noted', 'under_investigation', 'no_further_action', 'penalty', 'time_deleted', 'warning'], default: [], label: { en: 'Statuses (empty = all)', sv: 'Status (tomt = alla)' } },
    search: { type: 'text', default: '', label: { en: 'Text contains', sv: 'Texten innehåller' } },
    order: { type: 'enum', values: ['newest', 'oldest'], default: 'newest', label: { en: 'Order', sv: 'Ordning' } },
    rows: { type: 'integer', min: 1, max: 500, default: 30, label: { en: 'Maximum events', sv: 'Max antal händelser' } },
  }, ['investigations', 'track_limits', 'driver_list'], { spoiler: true, focus: ['driver', 'team'], defaultFields: ['incident_status', 'incident_drivers', 'event_time', 'incident_lap', 'incident_location', 'incident_reason', 'incident_penalty'], fieldDefinitions: {
    event_time: { ...FIELDS.event_time, source: 'selected_incidents', path: 'incident.nfi_utc ?? incident.utc' },
  } }),
  weather: module('weather', 'Weather', 'Väder', WEATHER_FIELDS.map(field => field.id), {
    content: { type: 'enum', values: ['weather_overview', 'current_conditions', 'automatic_conditions', 'race_forecast', 'track_conditions'], default: 'weather_overview', label: { en: 'Weather source', sv: 'Väderkälla' } },
    presentation: { type: 'enum', values: ['metrics', 'compact_list'], default: 'metrics', label: { en: 'Weather layout', sv: 'Väderlayout' } },
    show_explanation: { type: 'boolean', default: true, label: { en: 'Show About section', sv: 'Visa Om-sektion' } },
  }, ['weather', 'track_weather']),
};

export function moduleFocusKinds(module) {
  if (module.type === 'tyres' && module.options?.content === 'statistics' || module.type === 'strategy' && ['compound_comparison', 'crossover'].includes(module.options?.content)) return [];
  if (['standings', 'progression'].includes(module.type) && module.options?.competitors === 'teams') return ['team'];
  if (module.type === 'progression') return ['driver'];
  return MODULES[module.type]?.focus ?? (module.type === 'timing' ? ['driver', 'team'] : module.type === 'race_control' ? ['driver'] : []);
}
export const RESULT_PROFILES = {
  latest_race: ['result_position', 'driver', 'team', 'result_time', 'points'],
  race_results: ['result_position', 'driver', 'team', 'result_time', 'points'],
  sprint_results: ['result_position', 'driver', 'team', 'result_time', 'points'],
  starting_grid: ['grid_position', 'driver', 'team', 'qualifying_position', 'grid_delta', 'qualifying_segment', 'qualifying_time'],
};
export const TIMING_PROFILES = {
  practice: ['position', 'driver', 'best_lap', 'last_lap', 'sector_1', 'sector_2', 'sector_3', 'laps'],
  qualifying: ['position', 'driver', 'q1_time', 'q2_time', 'q3_time', 'sector_1', 'sector_2', 'sector_3'],
  sprint_qualifying: ['position', 'driver', 'q1_time', 'q2_time', 'q3_time', 'sector_1', 'sector_2', 'sector_3'],
  sprint: ['position', 'driver', 'gap', 'interval', 'last_lap', 'sector_1', 'sector_2', 'sector_3', 'tyre'],
  race: ['position', 'driver', 'gap', 'interval', 'last_lap', 'sector_1', 'sector_2', 'sector_3', 'tyre'],
};
export function sessionKind(name) {
  const value = String(name ?? '').toLowerCase().replaceAll('_', ' ');
  if (/sprint.*(qualifying|shootout)|shootout/.test(value)) return 'sprint_qualifying';
  if (value.includes('qualifying')) return 'qualifying';
  if (value.includes('practice')) return 'practice';
  if (value === 'sprint') return 'sprint';
  if (value === 'race') return 'race';
  return null;
}
export function timingFields(module, session) {
  const profile = module.options?.profile;
  return [...(TIMING_PROFILES[profile === 'auto' ? sessionKind(session) : profile] ?? module.fields)];
}
export const TYRE_PROFILES = {
  current: ['position', 'driver', 'tyre', 'tyre_age', 'tyre_new'],
  statistics: ['tyre', 'compound_best', 'compound_gap', 'compound_laps', 'new_sets'],
};
export const INCIDENT_PROFILES = {
  investigations: ['incident_status', 'incident_drivers', 'event_time', 'incident_lap', 'incident_location', 'incident_reason', 'incident_penalty'],
  track_limits: ['incident_status', 'incident_drivers', 'event_time', 'incident_lap', 'incident_location', 'incident_reason', 'incident_penalty'],
  track_limits_summary: ['driver', 'track_limit_deletions', 'track_limit_warning', 'track_limit_penalty'],
};
export const WEATHER_PROFILES = {
  weather_overview: ['temperature', 'humidity', 'wind', 'rain_probability'],
  current_conditions: ['weather_condition', 'temperature', 'humidity', 'wind'],
  race_forecast: ['weather_condition', 'temperature', 'rain_probability', 'precipitation', 'wind'],
  automatic_conditions: ['temperature', 'humidity', 'wind'],
  track_conditions: ['temperature', 'track_temperature', 'wind', 'rainfall'],
};
export const BATTLE_PROFILES = {
  active_battles: ['battle_status', 'incident_drivers', 'battle_gap'],
  battle_history: ['battle_status', 'incident_drivers', 'battle_gap', 'analysis_source'],
  position_exchanges: ['battle_status', 'incident_drivers', 'exchange_positions', 'analysis_source'],
};
export const STRATEGY_PROFILES = {
  teammates: ['team', 'incident_drivers', 'comparison_pace', 'comparison_gap', 'pace_leader', 'analysis_quality'],
  crossover: ['comparison_tyres', 'crossover_age', 'observed_age_range', 'crossover_pace', 'analysis_quality'],
  pit_outcomes: ['team', 'incident_drivers', 'comparison_stops', 'exchange_positions', 'strategy_outcome', 'analysis_quality'],
  stints: ['driver', 'tyre', 'stint_first_lap', 'stint_last_lap', 'clean_pace', 'clean_samples', 'analysis_quality'],
  compound_comparison: ['tyre', 'clean_pace', 'compound_gap', 'clean_samples', 'analysis_quality'],
};
export function defaultFields(module) {
  const definition = MODULES[module.type];
  if (module.type === 'archive' && module.options?.content && module.options.content !== 'classification') return ['lap_series'];
  const profiles = module.type === 'incidents' ? INCIDENT_PROFILES : module.type === 'weather' ? WEATHER_PROFILES : module.type === 'results' ? RESULT_PROFILES : module.type === 'tyres' ? TYRE_PROFILES : module.type === 'strategy' ? STRATEGY_PROFILES : module.type === 'battles' ? BATTLE_PROFILES : null;
  return profiles?.[module.options?.content ?? definition?.options?.content?.default] ?? definition?.defaultFields ?? definition?.fields ?? [];
}
export function moduleFields(module) {
  if (module.type === 'archive') return module.options?.content === 'classification' ? MODULES.archive.fields.filter(id => id !== 'lap_series') : ['lap_series'];
  if (module.type === 'incidents') return module.options?.content === 'track_limits_summary'
    ? ['driver', 'team', 'track_limit_deletions', 'track_limit_warning', 'track_limit_penalty', 'event_time'] : INCIDENT_PROFILES.investigations;
  if (module.type === 'weather' && module.options?.content === 'automatic_conditions') return MODULES.weather.fields;
  if (module.type === 'weather') return MODULES.weather.fields.filter(id => module.options?.content === 'track_conditions'
    ? ['temperature', 'track_temperature', 'humidity', 'wind', 'wind_direction', 'pressure', 'rainfall'].includes(id)
    : !['track_temperature', 'pressure', 'rainfall'].includes(id));
  if (module.type === 'battles') return MODULES.battles.fields.filter(id => id !== 'exchange_positions' || module.options?.content === 'position_exchanges');
  if (module.type === 'strategy') {
    const content = module.options?.content ?? 'stints';
    if (content === 'stints') return ['driver', 'team', 'tyre', 'stint_number', 'stint_first_lap', 'stint_last_lap', 'stint_start_age', 'clean_pace', 'raw_pace', 'degradation', 'clean_samples', 'raw_samples', 'excluded_samples', 'exclusion_reasons', 'strategy_pit_loss', 'analysis_quality'];
    return [...(STRATEGY_PROFILES[content] ?? []), ...(content === 'pit_outcomes' ? ['analysis_source'] : [])];
  }
  if (module.type === 'tyres') return module.options?.content === 'statistics'
    ? ['tyre', 'compound_best', 'compound_gap', 'compound_laps', 'new_sets', 'total_stints', 'best_runs']
    : ['position', 'driver', 'team', 'tyre', 'tyre_age', 'tyre_new'];
  if (module.type === 'results') return module.options?.content === 'starting_grid'
    ? ['grid_position', 'driver', 'team', 'qualifying_position', 'grid_delta', 'qualifying_segment', 'qualifying_time', 'qualifying_delta']
    : ['result_position', 'driver', 'team', 'grid_position', 'position_change', 'laps', 'result_time', 'result_status', 'points'];
  return (MODULES[module.type]?.fields ?? []).filter(id => !(module.type === 'standings' && module.options?.competitors === 'teams' && id === 'driver'));
}
export function fieldDefinition(module, id) {
  let field = MODULES[module.type]?.fieldDefinitions?.[id] ?? FIELDS[id];
  if (module.type === 'archive' && field) return { ...field, source: id === 'lap_series' ? 'history/laps' : 'history/results', capability: 'history', modes: ['history'], freshness: 'published', generation: 'archive_selection', spoiler: true, identity: ['entry', 'season', 'round', 'session', 'driver', ...(id === 'lap_series' ? ['lap'] : [])], timestamps: { source: 'not_provided', received: 'request.received_at', displayed: 'snapshot' },
    path: id === 'lap_series' ? 'laps[].lap_number + lap_duration + position' : `results[].${({ result_position: 'position', grid_position: 'grid', driver: 'driver_id', team: 'constructor_name', result_time: 'duration', result_status: 'status_detail', q1_time: 'q1', q2_time: 'q2', q3_time: 'q3', position_change: 'grid - position' })[id] ?? id}`,
    ...(/^q[123]_time$/.test(id) ? { type: 'classification_duration', label: { en: `${id.slice(0, 2).toUpperCase()} time`, sv: `${id.slice(0, 2).toUpperCase()}-tid` } } : {}) };
  if (module.type === 'incidents' && module.options?.content === 'track_limits_summary' && field) return { ...field, source: 'track_limits', identity: ['entry', 'session', 'driver'],
    path: ({ driver: 'by_driver.key', team: 'driver_list.drivers[].team', event_time: 'latest(by_driver.*.violations[].utc)' })[id] ?? field.path,
    ...(id === 'event_time' ? { label: { en: 'Latest recorded event', sv: 'Senaste registrerade händelse' } } : {}) };
  if (module.type === 'weather' && field) {
    const content = module.options?.content ?? 'weather_overview', track = content === 'track_conditions';
    if (content === 'automatic_conditions') return { ...field, source: 'automatic_weather', path: 'selected_source', modes: ['weather', 'live', 'replay'], generation: 'selected_weather_source', spoiler: true,
      alternatives: ['current_conditions', 'track_conditions'].map(content => ({ ...module, options: { ...module.options, content } })).filter(candidate => moduleFields(candidate).includes(id)).map(candidate => fieldDefinition(candidate, id)),
    };
    const forecast = content === 'race_forecast' || content === 'weather_overview' && id === 'rain_probability';
    const path = WEATHER_FIELDS.find(item => item.id === id)?.path;
    return { ...field, source: track ? 'track_weather' : 'weather', path: track ? id === 'temperature' ? 'air_temperature' : path : `${forecast ? 'race' : 'current'}_${path}`,
      modes: track ? ['live', 'replay'] : [forecast ? 'forecast' : 'weather'], identity: track ? ['entry', 'session'] : ['entry', 'season', 'round', 'circuit'],
      capability: track ? 'public_timing' : 'public', spoiler: track, estimated: forecast, freshness: track ? 'session' : 'source', generation: track ? 'session' : 'season_round', presentations: ['summary', 'list'],
    };
  }
  if (module.type === 'battles' && field) {
    const path = ({ battle_status: 'kind', battle_gap: 'gap_seconds', incident_drivers: 'driver_numbers', exchange_positions: 'positions_before + positions_after', analysis_source: 'supporting_signals', analysis_quality: 'confidence' })[id];
    if (path) field = { ...field, source: 'analysis', identity: ['entry', 'session', 'observation'], path: `${module.options?.content === 'position_exchanges' ? 'position_exchanges' : module.options?.content === 'battle_history' ? 'battles.history' : 'battles.active'}[].${path}`, timestamps: { source: 'not_provided', received: 'subscription.received_at', displayed: 'snapshot' } };
  }
  if (module.type === 'strategy' && field) {
    const content = module.options?.content ?? 'stints', compounds = content === 'compound_comparison';
    if (['teammates', 'crossover', 'pit_outcomes'].includes(content)) {
      const key = { teammates: 'teammate_comparisons', crossover: 'compound_crossover_indications', pit_outcomes: 'undercut_overcut_outcomes' }[content];
      const fieldPath = { team: 'team', incident_drivers: 'drivers', analysis_quality: 'confidence', analysis_source: 'supporting_signals', exchange_positions: 'positions_before + positions_after' }[id];
      return { ...field, source: 'analysis', timestamps: timestampsFor('analysis'), identity: ['entry', 'session', 'comparison'], ...(fieldPath ? { path: `strategy.${key}[].${fieldPath}` } : {}) };
    }
    const path = ({ driver: 'driver_number', team: 'team', tyre: 'compound', analysis_quality: 'confidence', clean_pace: compounds ? 'median_clean_pace' : 'adjusted_median_clean_pace', clean_samples: 'sample_count', compound_gap: 'delta_to_fastest' })[id];
    if (path) field = { ...field, source: 'analysis', timestamps: timestampsFor('analysis'), path: `strategy.${compounds ? 'compound_comparison' : 'stints'}[].${path}` };
  }
  if (module.type === 'standings' && id === 'result_position') field = { ...field, label: { en: 'Position', sv: 'Placering' } };
  if (module.type === 'tyres' && ['position', 'driver', 'team', 'tyre', 'tyre_age'].includes(id)) {
    const stats = module.options?.content === 'statistics';
    field = { ...field, source: stats ? 'tyre_statistics' : 'current_tyres', path: stats ? 'compounds.key' : ({ position: 'drivers[].position', driver: 'drivers[].racing_number', team: 'driver_list.drivers[].team', tyre: 'drivers[].compound', tyre_age: 'drivers[].stint_laps' })[id] };
  }
  return field;
}
export const INCIDENT_SIGNALS = {
  noted: { symbol: '○', label: { en: 'Noted', sv: 'Noterad' } },
  under_investigation: { symbol: '?', label: { en: 'Under investigation', sv: 'Under utredning' } },
  no_further_action: { symbol: '✓', label: { en: 'No further action', sv: 'Ingen ytterligare åtgärd' } },
  penalty: { symbol: '!', label: { en: 'Penalty', sv: 'Bestraffning' } },
  time_deleted: { symbol: '×', label: { en: 'Lap time deleted', sv: 'Varvtid struken' } },
  warning: { symbol: '△', label: { en: 'Warning', sv: 'Varning' } },
};
export const PRESETS = {
  weekend: { label: { en: 'Race weekend', sv: 'Tävlingshelgen' }, modules: [{ type: 'overview' }, { type: 'calendar' }, { type: 'weather', options: { content: 'automatic_conditions' } }, { type: 'weather', options: { content: 'race_forecast' } }] },
  weather: { label: { en: 'Weather comparison', sv: 'Väderjämförelse' }, modules: [{ type: 'weather', options: { content: 'automatic_conditions' } }, { type: 'weather', options: { content: 'race_forecast' } }] },
  session: { label: { en: 'Follow the session', sv: 'Följ sessionen' }, modules: [{ type: 'overview', fields: ['session', 'track_status'] }, { type: 'timing' }, { type: 'race_control' }] },
  driver: { label: { en: 'My driver', sv: 'Min förare' }, modules: [{ type: 'overview', fields: ['session', 'track_status'] }, { type: 'timing', fields: ['position', 'driver', 'last_lap', 'best_lap', 'tyre', 'tyre_age'], options: { history: 5 } }, { type: 'race_control' }] },
  results: { label: { en: 'Results and championship', sv: 'Resultat och mästerskap' }, modules: [{ type: 'results', options: { rows: 5 } }, { type: 'standings', options: { rows: 5 } }, { type: 'progression' }] },
  custom: { label: { en: 'Build your own', sv: 'Bygg själv' }, modules: [] },
};

const CONTENT_TITLES = { incidents: { investigations: ['Investigations and decisions', 'Utredningar och beslut'], track_limits: ['Track limits events', 'Track limits-händelser'], track_limits_summary: ['Track limits by driver', 'Track limits per förare'] }, weather: { automatic_conditions: ['Automatic current weather', 'Automatiskt aktuellt väder'], weather_overview: ['Weather overview', 'Väderöversikt'], current_conditions: ['Current circuit weather', 'Aktuellt väder vid banan'], race_forecast: ['Race-start forecast', 'Prognos inför racestart'], track_conditions: ['Track weather observations', 'Väderobservationer från banan'] }, strategy: { stints: ['Stint pace and quality', 'Stinttempo och kvalitet'], compound_comparison: ['Compound pace comparison', 'Tempojämförelse mellan blandningar'], teammates: ['Teammate comparison', 'Jämförelse mellan teamkamrater'], crossover: ['Compound crossover estimates', 'Uppskattade skärningar mellan blandningar'], pit_outcomes: ['Observed pit-cycle outcomes', 'Observerade utfall av depåcykler'] }, battles: { active_battles: ['Current battles', 'Pågående närkamper'], battle_history: ['Battle history', 'Närkampernas historik'], position_exchanges: ['Position exchanges', 'Positionsbyten'] } };
export function moduleTitle(module, language = 'en') {
  if (module.title) return module.title;
  const content = module.options?.content ?? MODULES[module.type]?.options?.content?.default;
  const titles = CONTENT_TITLES[module.type]?.[content];
  return titles ? titles[String(language).startsWith('sv') ? 1 : 0] : label(MODULES[module.type], language) || module.type;
}
