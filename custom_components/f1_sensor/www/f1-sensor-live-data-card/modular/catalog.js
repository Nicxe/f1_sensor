// Field IDs are configuration API. Labels, sources and presentation stay together.
const version = new URL(import.meta.url).searchParams.get('v');
const { words, translatePlural } = await import(`./i18n.js${version ? `?v=${encodeURIComponent(version)}` : ''}`);

export { translatePlural, words };
export const VERSION = 3;
export const CARD_TYPE = 'custom:f1-sensor-card';
export const label = (item, language = 'en') => typeof item?.label === 'string'
  ? words(language, item.label)
  : item?.id ?? '';

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

const timing = (id, sourceText, type, path, extra = {}) => ({
  id, label: sourceText, type, unit: type === 'duration' ? 's' : null,
  source: 'driver_positions', path, capability: 'public_timing',
  modes: ['live', 'replay'], sessions: ['practice', 'qualifying', 'sprint_qualifying', 'sprint', 'race'],
  identity: ['entry', 'session', 'driver', ...(type === 'duration' ? ['lap'] : [])],
  generation: 'session',
  timestamps: timestampsFor(extra.source ?? 'driver_positions'),
  freshness: 'session', spoiler: true, sortable: true, filterable: false,
  mobile: 2, presentations: ['table', 'detail'], ...extra,
});

const minisector = (id, sourceText, type, path, extra = {}) => ({
  id, label: sourceText, type, unit: null, source: 'minisectors', path,
  capability: 'public_timing', modes: ['live', 'replay'],
  sessions: ['practice', 'qualifying', 'sprint_qualifying', 'sprint', 'race'],
  identity: ['entry', 'session', 'generation', 'driver', 'lap', 'sector', 'segment'],
  generation: 'minisector_generation',
  timestamps: { source: 'stream_timestamp_or_null', received: 'subscription.received_at', updated: 'generated_at', displayed: 'snapshot' },
  freshness: 'session_delta', spoiler: true, sortable: false, filterable: false,
  mobile: 1, presentations: ['table', 'detail', 'strip'], estimated: false,
  comparison: 'provider_status', ...extra,
});

export const MINISECTOR_FIELDS = [
  minisector('minisector_1', 'S1 minisectors', 'minisector_status_strip', 'drivers.*.sectors.0.segments'),
  minisector('sector_1_with_minisectors', 'S1 with minisectors', 'sector_with_minisectors', 'driver_positions.drivers[].sectors.current.sector_1 + drivers.*.sectors.0.segments', {
    unit: 's', sortable: true, presentations: ['table', 'detail'],
  }),
  minisector('minisector_2', 'S2 minisectors', 'minisector_status_strip', 'drivers.*.sectors.1.segments'),
  minisector('sector_2_with_minisectors', 'S2 with minisectors', 'sector_with_minisectors', 'driver_positions.drivers[].sectors.current.sector_2 + drivers.*.sectors.1.segments', {
    unit: 's', sortable: true, presentations: ['table', 'detail'],
  }),
  minisector('minisector_3', 'S3 minisectors', 'minisector_status_strip', 'drivers.*.sectors.2.segments'),
  minisector('sector_3_with_minisectors', 'S3 with minisectors', 'sector_with_minisectors', 'driver_positions.drivers[].sectors.current.sector_3 + drivers.*.sectors.2.segments', {
    unit: 's', sortable: true, presentations: ['table', 'detail'],
  }),
];

export const TIMING_FIELDS = [
  timing('position', 'Pos', 'integer', 'current_position', { mobile: 0 }),
  timing('driver', 'Driver', 'driver', 'racing_number', { mobile: 0, filterable: true }),
  timing('team', 'Team', 'text', 'team', { filterable: true }),
  timing('gap', 'To leader', 'gap', 'gap_to_leader', { mobile: 1 }),
  timing('interval', 'Ahead', 'gap', 'interval_to_position_ahead', { mobile: 1 }),
  timing('last_lap', 'Last lap', 'duration', 'laps', { mobile: 1 }),
  timing('best_lap', 'Best lap', 'duration', 'best_lap_time'),
  timing('best_lap_gap', 'Gap to fastest lap', 'seconds_delta', 'best_lap_gap (TimingData.TimeDiffToFastest); fallback official best_lap_time - fastest official session best_lap_time', {
    sessions: ['practice'], unit: 's', comparison: 'fastest_official_session_best',
  }),
  timing('lap_delta', 'Lap change', 'delta', 'laps', { comparison: 'previous_completed_lap' }),
  ...[1, 2, 3].map(n => timing(`sector_${n}`, `S${n}`, 'sector', `sectors.current.sector_${n}`, {
    unit: 's', identity: ['entry', 'session', 'driver', 'lap', 'sector'], mobile: 1,
  })),
  ...[1, 2, 3].flatMap(n => [
    timing(`q${n}_time`, `Q${n} best`, 'qualifying_duration', `q${n}_time`, { sessions: ['qualifying', 'sprint_qualifying'], identity: ['entry', 'session', 'part', 'driver'] }),
    timing(`q${n}_position`, `Q${n} position`, 'integer', `q${n}_position`, { sessions: ['qualifying', 'sprint_qualifying'] }),
    timing(`best_sector_${n}`, `Best S${n}`, 'sector', `sectors.personal_best.sector_${n}`, { identity: ['entry', 'session', 'part', 'driver', 'lap', 'sector'] }),
  ]),
  timing('qualifying_gap', 'Current part gap', 'seconds_delta', 'current qualifying part best - fastest current qualifying part', { sessions: ['qualifying', 'sprint_qualifying'], unit: 's', comparison: 'fastest_current_qualifying_part' }),
  timing('theoretical_lap', 'Theoretical lap', 'theoretical_duration', 'sum(sectors.personal_best)', { estimated: true, comparison: 'personal_best_sectors' }),
  timing('laps', 'Laps', 'integer', 'completed_laps'),
  timing('tyre', 'Tyre', 'compound', 'compound', { source: 'current_tyres', mobile: 1 }),
  timing('tyre_age', 'Tyre age', 'integer', 'stint_laps', { source: 'current_tyres', unit: 'laps' }),
  timing('status', 'Status', 'status', 'in_pit'),
  ...MINISECTOR_FIELDS,
];

const basic = (id, sourceText, source, path, type = 'text', extra = {}) => ({
  id, label: sourceText, source, path, type, unit: null, capability: 'public',
  modes: ['schedule'], sessions: ['all'], identity: ['entry', 'season', 'round'],
  generation: generationFor(source),
  timestamps: timestampsFor(source),
  freshness: 'source', spoiler: false, sortable: false, filterable: false,
  mobile: 0, presentations: ['summary'], ...extra,
});
const classification = (id, sourceText, type = 'text', extra = {}) => basic(id, sourceText, 'last_race_results', `results[].${id}`, type, {
  modes: ['results'], identity: ['entry', 'season', 'round', 'session', 'driver'],
  spoiler: true, sortable: true, presentations: ['table', 'detail'], ...extra,
});
const mapAnnotation = (id, sourceText, layer) => basic(id, sourceText, 'track_map', `annotations.layers.${layer}`, 'map_annotation', {
  modes: ['live', 'replay'], capability: 'extended_timing', spoiler: true,
  identity: ['entry', 'source', 'session', 'session_generation', 'geometry'], generation: 'session',
  presentations: ['map', 'list'],
});
export const RESULT_FIELDS = [
  classification('result_position', 'Classification', 'integer', { path: 'results[].position' }),
  classification('grid_position', 'Grid', 'grid', { path: 'results[].grid' }),
  classification('position_change', 'Places gained', 'position_delta', { path: 'results[].position - results[].grid', comparison: 'starting_grid' }),
  classification('result_time', 'Time / gap', 'classification_time', { path: 'results[].time', unit: 'source_defined' }),
  classification('result_status', 'Classification status', 'text', { path: 'results[].status' }),
  classification('points', 'Points', 'number', { path: 'results[].points', unit: 'points' }),
  classification('wins', 'Wins', 'integer', { source: 'driver_standings', path: 'driver_standings[].wins' }),
  classification('predicted_points', 'Projected points', 'number', { source: 'championship_prediction_drivers', path: 'drivers.*.PredictedPoints', capability: 'extended_timing', modes: ['live', 'replay'], freshness: 'session', generation: 'session', unit: 'points', estimated: true }),
  classification('predicted_position', 'Projected position', 'integer', { source: 'championship_prediction_drivers', path: 'drivers.*.PredictedPosition', capability: 'extended_timing', modes: ['live', 'replay'], freshness: 'session', generation: 'session', estimated: true }),
  classification('points_change', 'Projected change', 'points_delta', { source: 'championship_prediction_drivers', path: 'drivers.*.PredictedPoints - drivers.*.CurrentPoints', capability: 'extended_timing', modes: ['live', 'replay'], freshness: 'session', generation: 'session', unit: 'points', estimated: true, comparison: 'current_points' }),
  classification('qualifying_position', 'Qualifying position', 'integer', { source: 'starting_grid', path: 'grid[].qualifying_position', generation: 'session' }),
  classification('qualifying_time', 'Qualifying time', 'classification_duration', { source: 'starting_grid', path: 'grid[].qualifying_time_secs', generation: 'session', unit: 's' }),
  classification('grid_delta', 'Grid change', 'position_delta', { source: 'starting_grid', path: 'grid[].grid_delta', generation: 'session', comparison: 'qualifying_position' }),
  classification('qualifying_segment', 'Qualifying segment', 'text', { source: 'starting_grid', path: 'grid[].qualifying_segment', generation: 'session' }),
  classification('qualifying_delta', 'Qualifying gap', 'seconds_delta', { source: 'starting_grid', path: 'grid[].qualifying_time_secs - fastest qualifying time', generation: 'session', unit: 's', comparison: 'fastest_qualifying_time' }),
];
export const SESSION_FIELDS = [
  timing('tyre_new', 'New set', 'boolean', 'drivers[].new', { source: 'current_tyres' }),
  timing('compound_best', 'Best recorded lap', 'lap_duration', 'compounds.*.best_times[0].time_secs', { source: 'tyre_statistics' }),
  timing('compound_gap', 'To fastest compound', 'seconds_delta', 'deltas.*', { source: 'tyre_statistics', comparison: 'fastest_compound' }),
  timing('compound_laps', 'Total laps', 'integer', 'compounds.*.total_laps', { source: 'tyre_statistics' }),
  timing('new_sets', 'New sets used', 'integer', 'compounds.*.sets_used', { source: 'tyre_statistics' }),
  timing('total_stints', 'Stints recorded', 'integer', 'compounds.*.sets_used_total', { source: 'tyre_statistics' }),
  timing('best_runs', 'Fastest recorded stints', 'stint_records', 'compounds.*.best_times', { source: 'tyre_statistics' }),
  timing('pit_count', 'Stops recorded', 'integer', 'cars.*.count', { source: 'pitstops', capability: 'extended_timing' }),
  timing('stop_lap', 'Stop lap', 'integer', 'cars.*.stops[].lap', { source: 'pitstops', capability: 'extended_timing' }),
  timing('stop_time', 'Stationary time', 'seconds_duration', 'cars.*.stops[].pit_stop_time', { source: 'pitstops', capability: 'extended_timing', unit: 's' }),
  timing('lane_time', 'Pit lane time', 'seconds_duration', 'cars.*.stops[].pit_lane_time', { source: 'pitstops', capability: 'extended_timing', unit: 's' }),
  timing('pit_delta', 'Estimated lap loss', 'seconds_delta', 'cars.*.stops[].pit_delta', { source: 'pitstops', capability: 'extended_timing', unit: 's', estimated: true, comparison: 'reference_laps' }),
  timing('stint_number', 'Stint', 'integer', 'strategy.stints[].stint_index + 1', { source: 'analysis' }),
  timing('stint_first_lap', 'First lap', 'integer', 'strategy.stints[].first_lap', { source: 'analysis' }),
  timing('stint_last_lap', 'Last lap number', 'integer', 'strategy.stints[].last_lap', { source: 'analysis' }),
  timing('stint_start_age', 'Starting tyre age', 'integer', 'strategy.stints[].tyre_age_at_start', { source: 'analysis' }),
  timing('clean_pace', 'Median clean pace', 'lap_duration', 'strategy.stints[].adjusted_median_clean_pace', { source: 'analysis', estimated: true }),
  timing('raw_pace', 'Median recorded pace', 'lap_duration', 'strategy.stints[].raw_median_pace', { source: 'analysis' }),
  timing('degradation', 'Estimated degradation', 'degradation', 'strategy.stints[].degradation_seconds_per_lap', { source: 'analysis', unit: 's/lap', estimated: true }),
  timing('clean_samples', 'Clean laps', 'integer', 'strategy.stints[].sample_count', { source: 'analysis' }),
  timing('raw_samples', 'Recorded laps', 'integer', 'strategy.stints[].raw_sample_count', { source: 'analysis' }),
  timing('excluded_samples', 'Excluded laps', 'integer', 'strategy.stints[].excluded_laps', { source: 'analysis' }),
  timing('exclusion_reasons', 'Exclusion reasons', 'reason_counts', 'strategy.stints[].excluded_reason_counts', { source: 'analysis' }),
  timing('comparison_pace', 'Median pace by driver', 'driver_paces', 'strategy.teammate_comparisons[].median_clean_pace', { source: 'analysis', estimated: true }),
  timing('comparison_gap', 'Pace difference', 'seconds_duration', 'strategy.teammate_comparisons[].delta_seconds', { source: 'analysis', estimated: true }),
  timing('pace_leader', 'Lower median pace', 'text', 'strategy.teammate_comparisons[].faster_driver', { source: 'analysis', estimated: true }),
  timing('comparison_tyres', 'Compounds compared', 'compound_list', 'strategy.compound_crossover_indications[].compounds', { source: 'analysis' }),
  timing('crossover_age', 'Estimated crossover tyre age', 'lap_age', 'strategy.compound_crossover_indications[].estimated_tyre_age_laps', { source: 'analysis', estimated: true }),
  timing('observed_age_range', 'Observed tyre-age range', 'lap_range', 'strategy.compound_crossover_indications[].observed_age_range', { source: 'analysis' }),
  timing('crossover_pace', 'Estimated pace at crossover', 'lap_duration', 'strategy.compound_crossover_indications[].pace_at_crossover', { source: 'analysis', estimated: true }),
  timing('strategy_outcome', 'Observed pit-cycle outcome', 'strategy_outcome', 'strategy.undercut_overcut_outcomes[].result', { source: 'analysis', estimated: true }),
  timing('comparison_stops', 'Stop laps by driver', 'driver_laps', 'strategy.undercut_overcut_outcomes[].stop_laps', { source: 'analysis' }),
  timing('strategy_pit_loss', 'Estimated stint-change loss', 'seconds_delta', 'strategy.stints[].pit_loss_seconds', { source: 'analysis', estimated: true, comparison: 'previous_stint_pace' }),
  timing('analysis_title', 'Event', 'text', 'timeline.events[].title', { source: 'analysis', capability: 'analysis' }),
  timing('battle_status', 'Observation', 'battle_status', 'battles[].kind', { source: 'analysis', capability: 'analysis', estimated: true }),
  timing('battle_gap', 'Observed gap', 'seconds_duration', 'battles[].gap_seconds', { source: 'analysis', capability: 'analysis' }),
  timing('exchange_positions', 'Before → after', 'exchange_positions', 'position_exchanges[].positions_before + positions_after', { source: 'analysis', capability: 'analysis', estimated: true }),
  timing('analysis_description', 'Details', 'text', 'timeline.events[].description', { source: 'analysis', capability: 'analysis' }),
  timing('analysis_category', 'Category', 'text', 'timeline.events[].category', { source: 'analysis', capability: 'analysis' }),
  timing('analysis_source', 'Source / basis', 'text', 'timeline.events[].supporting_signals', { source: 'analysis', capability: 'analysis' }),
  timing('analysis_quality', 'Evidence score', 'confidence', 'timeline.events[].confidence', { source: 'analysis', capability: 'analysis', estimated: true }),
  timing('track_limit_deletions', 'Deleted times', 'integer', 'by_driver.*.deletions', { source: 'track_limits' }),
  timing('track_limit_warning', 'Warning recorded', 'warning_indicator', 'by_driver.*.warning', { source: 'track_limits' }),
  timing('track_limit_penalty', 'Latest recorded penalty', 'penalty_summary', 'by_driver.*.penalty', { source: 'track_limits' }),
  timing('incident_status', 'Decision / status', 'incident_status', 'incident.category', { source: 'selected_incidents' }),
  timing('incident_drivers', 'Drivers involved', 'text', 'incident.drivers', { source: 'selected_incidents' }),
  timing('incident_lap', 'Lap', 'integer', 'incident.lap', { source: 'selected_incidents' }),
  timing('incident_location', 'Location', 'text', 'incident.location', { source: 'selected_incidents' }),
  timing('incident_reason', 'Reason', 'text', 'incident.reason', { source: 'selected_incidents' }),
  timing('incident_penalty', 'Penalty', 'text', 'incident.penalty', { source: 'selected_incidents' }),
];
export const WEATHER_FIELDS = [
  ['temperature', 'Air temperature', 'temperature', 'number', '°C'],
  ['track_temperature', 'Track temperature', 'track_temperature', 'number', '°C'],
  ['weather_condition', 'Conditions', 'weather_code', 'weather_condition', null],
  ['humidity', 'Humidity', 'humidity', 'number', '%'],
  ['wind', 'Wind speed', 'wind_speed', 'number', 'm/s'],
  ['wind_direction', 'Wind from', 'wind_from_direction_degrees', 'bearing', '°'],
  ['wind_gusts', 'Wind gusts', 'wind_gusts', 'number', 'm/s'],
  ['cloud_cover', 'Cloud cover', 'cloud_cover', 'number', '%'],
  ['visibility', 'Visibility', 'visibility', 'number', 'm'],
  ['pressure', 'Air pressure', 'pressure', 'number', 'hPa'],
  ['rain_probability', 'Rain probability', 'precipitation_probability', 'number', '%'],
  ['precipitation', 'Precipitation amount', 'precipitation', 'number', 'mm'],
  ['rainfall', 'Rain detected', 'rainfall', 'rain_indicator', null],
].map(([id, sourceText, path, type, unit]) => basic(id, sourceText, ['track_temperature', 'pressure', 'rainfall'].includes(id) ? 'track_weather' : 'weather', path, type, { unit, timestamps: { source: 'not_provided', received: 'not_provided', updated: 'entity.last_updated', displayed: 'snapshot' } }));
export const FIELDS = Object.fromEntries([
  ...SESSION_FIELDS,
  ...RESULT_FIELDS,
  ...TIMING_FIELDS,
  basic('meeting', 'Grand Prix', 'next_race', 'race_name'),
  basic('circuit', 'Circuit', 'next_race', 'circuit_name'),
  basic('country', 'Country', 'next_race', 'circuit_country'),
  basic('countdown', 'Countdown', 'next_race', 'race_start_utc', 'countdown'),
  basic('circuit_map', 'Circuit map', 'next_race', 'circuit_map_url', 'image'),
  basic('circuit_history', 'Circuit history', 'next_race', 'defending_winner + defending_pole_sitter + circuit history attributes', 'history'),
  basic('session', 'Session', 'current_session', 'state', 'text', { modes: ['live', 'replay'], identity: ['entry', 'session'], generation: 'session' }),
  basic('session_status', 'Session status', 'session_status', 'state', 'status', { modes: ['live', 'replay'], generation: 'session' }),
  basic('lap_progress', 'Lap progress', 'race_lap_count', 'state + total_laps', 'text', { modes: ['live', 'replay'], spoiler: true, identity: ['entry', 'session'], generation: 'session' }),
  ...[['session_time_elapsed', 'Session time elapsed'], ['session_time_remaining', 'Session time remaining'], ['race_time_to_three_hour_limit', 'Time to three-hour limit']].map(([id, sourceText]) => basic(id, sourceText, id, 'value_seconds', 'session_clock', { modes: ['live', 'replay'], spoiler: true, identity: ['entry', 'session', 'part'], generation: 'session', timestamps: { source: 'last_server_utc', received: 'not_provided', updated: 'entity.last_updated', displayed: 'snapshot' } })),
  basic('track_status', 'Track status', 'track_status', 'state', 'flag', { modes: ['live', 'replay'], spoiler: true, generation: 'session' }),
  basic('schedule', 'Schedule', 'next_race', '*_start_utc', 'schedule'),
  ...WEATHER_FIELDS,
  basic('event_time', 'Time', 'race_control_log', 'utc', 'datetime', { modes: ['live', 'replay'], spoiler: true, generation: 'session', presentations: ['timeline'] }),
  basic('track_map', 'Track map', 'track_map', 'track.points + drivers', 'map', { modes: ['live', 'replay'], capability: 'extended_timing', spoiler: true, generation: 'session', presentations: ['map', 'list'] }),
  basic('map_drivers', 'Driver positions list', 'track_map', 'drivers', 'list', { modes: ['live', 'replay'], capability: 'extended_timing', spoiler: true, generation: 'session', presentations: ['list'] }),
  mapAnnotation('map_start_finish', 'Start/finish line', 'start_finish'),
  mapAnnotation('map_corners', 'Corner numbers', 'corners'),
  mapAnnotation('map_sectors', 'Sector boundaries', 'sectors'),
  mapAnnotation('map_speed_traps', 'Speed traps', 'speed_traps'),
  mapAnnotation('map_detection_zones', 'Detection and activation points', 'detection_zones'),
  ...[['replay_selection', 'Replay selection'], ['replay_transport', 'Playback controls'], ['replay_progress', 'Playback progress']].map(([id, sourceText]) => basic(id, sourceText, 'replay_player', 'selected_session + playback_position_s + playback_total_s', 'replay_control', { modes: ['replay'], identity: ['entry', 'replay_session'], timestamps: { source: 'not_provided', updated_position: 'media_position_updated_at', received: 'not_provided', updated: 'entity.last_updated', displayed: 'snapshot' } })),
  ...[['speed', 'Speed', 'km/h'], ['throttle', 'Throttle', '%'], ['brake', 'Brake signal', null], ['gear', 'Gear', null], ['drs', 'DRS code', null], ['rpm', 'Engine speed', 'rpm'], ['delta_s', 'Estimated time delta', 's']].map(([id, sourceText, unit]) => basic(`telemetry_${id}`, sourceText, 'analysis/telemetry_compare', `series[].samples[].${id}`, 'series', { unit, modes: ['replay'], spoiler: true, capability: 'replay_telemetry', estimated: id === 'delta_s', identity: ['entry', 'replay_session', 'driver', 'lap', 'sample'], timestamps: { source: 'not_provided', position: 'time_s', received: 'request.received_at', displayed: 'snapshot' }, presentations: ['chart', 'table'] })),
  basic('lap_series', 'Recorded lap history', 'driver_positions', 'drivers[].laps', 'series', { modes: ['live', 'replay'], spoiler: true, identity: ['entry', 'session', 'driver', 'lap'], presentations: ['chart', 'table'], timestamps: { source: 'not_provided', position: 'lap_number', received: 'not_provided', updated: 'entity.last_updated', displayed: 'snapshot' } }),
  basic('progression', 'Progression', 'selected_points_progression', 'rounds + competitors.*', 'series', { modes: ['standings'], spoiler: true, presentations: ['chart', 'table'], identity: ['entry', 'season', 'round', 'competitor'] }),
  basic('document_title', 'Document', 'fia_documents', 'documents[].name', 'link', { spoiler: true }),
  basic('document_time', 'Published', 'fia_documents', 'documents[].published', 'datetime', { spoiler: true }),
  basic('document_number', 'Document number', 'fia_documents', 'documents[].document_number', 'integer', { spoiler: true }),
  basic('message', 'Message', 'race_control_log', 'message', 'text', { modes: ['live', 'replay'], spoiler: true, presentations: ['timeline'], filterable: true }),
  ...[
    ['radio_driver', 'Driver', 'driver'],
    ['radio_team', 'Team', 'text'],
    ['radio_audio', 'Audio clip', 'audio'],
    ['radio_transcript', 'Transcript', 'dialogue'],
    ['radio_time', 'Message time', 'datetime'],
  ].map(([id, sourceText, type]) => basic(id, sourceText, 'team_radio', id, type, {
    capability: 'extended_timing', modes: ['live', 'replay'], sessions: ['practice', 'qualifying', 'sprint_qualifying', 'sprint', 'race'],
    identity: ['entry', 'session', 'clip', ...(id === 'radio_driver' ? ['driver'] : id === 'radio_team' ? ['team'] : [])],
    generation: 'session', spoiler: true, presentations: ['radio'],
  })),
].map(field => [field.id, field]));

const module = (id, sourceText, fields, options, sources, extra = {}) => ({
  id, label: sourceText, fields, options, sources, version: VERSION, ...extra,
});
export const MODULES = {
  overview: module('overview', 'Overview', ['meeting', 'circuit', 'country', 'countdown', 'circuit_map', 'circuit_history', 'session', 'session_status', 'lap_progress', 'track_status', 'session_time_elapsed', 'session_time_remaining', 'race_time_to_three_hour_limit'], {
    layout_mode: { type: 'enum', values: ['auto', 'compact', 'full'], default: 'auto', label: 'Layout mode' },
  }, ['next_race', 'current_season', 'current_session', 'session_status', 'replay_status', 'replay_player', 'race_lap_count', 'track_status', 'session_time_elapsed', 'session_time_remaining', 'race_time_to_three_hour_limit'], { defaultFields: ['meeting', 'circuit', 'countdown'] }),
  calendar: module('calendar', 'Schedule', ['schedule'], {
    details: { type: 'list', values: ['round', 'circuit', 'location'], default: [], label: 'Event details' },
    past: { type: 'enum', values: ['show', 'dim', 'hide'], default: 'show', label: 'Past session starts' },
    next: { type: 'enum', values: ['none', 'label'], default: 'none', label: 'Next session marker' },
    range: { type: 'enum', values: ['weekend', 'season'], default: 'weekend', label: 'Show' },
    timezone: { type: 'enum', values: ['home', 'circuit', 'utc'], default: 'home', label: 'Time zone' },
    show_track_time: { type: 'boolean', default: false, label: 'Also show circuit time' },
    sessions: { type: 'list', values: ['practice_1', 'practice_2', 'practice_3', 'qualifying', 'sprint_qualifying', 'sprint', 'race'], default: ['practice_1', 'practice_2', 'practice_3', 'qualifying', 'sprint_qualifying', 'sprint', 'race'], label: 'Sessions' },
  }, ['next_race', 'current_season']),
  timing: module('timing', 'Timing', TIMING_FIELDS.map(field => field.id), {
    profile: { type: 'enum', values: ['custom', 'auto', 'practice', 'qualifying', 'sprint_qualifying', 'sprint', 'race'], default: 'custom', label: 'Column profile' },
    sort: { type: 'enum', values: ['position', 'best_lap', 'driver'], default: 'position', label: 'Sort by' },
    direction: { type: 'enum', values: ['asc', 'desc'], default: 'asc', label: 'Direction' },
    rows: { type: 'integer', min: 1, max: 100, default: 30, label: 'Maximum drivers' },
    sectors: { type: 'enum', values: ['coherent', 'latest'], default: 'coherent', label: 'Sector laps' },
    history: { type: 'integer', min: 0, max: 30, default: 0, label: 'Recent lap columns' },
    detail_laps: { type: 'integer', min: 0, max: 30, default: 0, label: 'Recent laps in driver details' },
    show_driver_details: { type: 'boolean', default: true, label: 'Show driver details' },
    show_gap_toggle: { type: 'boolean', default: false, label: 'Show live gap toggle' },
    show_time_context: { type: 'boolean', default: true, label: 'Show text below times' },
    show_time_status_icon: { type: 'boolean', default: true, label: 'Show time status icon' },
  }, ['driver_positions', 'driver_list', 'current_tyres', 'current_session', 'session_status'], { defaultFields: ['position', 'driver', 'gap', 'last_lap', 'sector_1', 'sector_2', 'sector_3', 'tyre'], defaultDetailFields: ['best_lap', 'tyre_age', 'status'] }),
  minisectors: module('minisectors', 'Minisectors', ['position', 'driver', 'team', 'sector_1', 'sector_2', 'sector_3', ...MINISECTOR_FIELDS.map(field => field.id)], {
    sort: { type: 'enum', values: ['position', 'driver'], default: 'position', label: 'Sort by' },
    direction: { type: 'enum', values: ['asc', 'desc'], default: 'asc', label: 'Direction' },
    rows: { type: 'integer', min: 1, max: 100, default: 30, label: 'Maximum drivers' },
    sectors: { type: 'enum', values: ['coherent', 'latest'], default: 'coherent', label: 'Sector laps' },
    show_legend: { type: 'boolean', default: true, label: 'Show status legend' },
  }, ['driver_positions', 'driver_list', 'current_session', 'session_status'], { spoiler: true, stream: 'minisectors', focus: ['driver', 'team'], defaultFields: ['driver', 'minisector_1', 'minisector_2', 'minisector_3'] }),
  race_control: module('race_control', 'Race Control', ['event_time', 'message'], {
    presentation: { type: 'enum', values: ['list', 'latest_message'], default: 'list', label: 'Message view' },
    global_messages: { type: 'enum', values: ['include', 'hide'], default: 'include', label: 'Session-wide messages with driver focus' },
    limit: { type: 'integer', min: 1, max: 500, default: 30, label: 'Messages to show' },
    order: { type: 'enum', values: ['newest', 'oldest'], default: 'newest', label: 'Order' },
    search: { type: 'text', default: '', label: 'Message contains' },
    categories: { type: 'list', values: ['Flag', 'SafetyCar', 'Drs', 'Other'], default: [], label: 'Categories (empty = all)' },
    list_max_height: { type: 'integer', min: 0, max: 2000, default: 600, label: 'List height in pixels' },
    hide_blue_flags: { type: 'boolean', default: false, label: 'Hide blue-flag messages' },
    hide_track_limits: { type: 'boolean', default: false, label: 'Hide track-limits messages' },
    show_fia_logo: { type: 'boolean', default: true, label: 'Show FIA mark' },
    min_display_time: { type: 'integer', min: 0, max: 30, default: 0, label: 'Minimum display time in seconds' },
    show_clear_button: { type: 'boolean', default: true, label: 'Show clear button' },
  }, ['race_control', 'current_session'], { stream: 'race_control' }),
  team_radio: module('team_radio', 'Team Radio (experimental)', ['radio_driver', 'radio_team', 'radio_audio', 'radio_transcript', 'radio_time'], {
    presentation: { type: 'enum', values: ['latest_message', 'recent_messages'], default: 'latest_message', label: 'Radio messages' },
    messages_to_show: { type: 'integer', min: 1, max: 10, default: 3, label: 'Messages to show' },
    show_audio_controls: { type: 'boolean', default: true, label: 'Show audio controls' },
    show_transcribe_button: { type: 'boolean', default: true, label: 'Show Transcribe button' },
    ai_task_entity_id: { type: 'entity', domain: 'ai_task', default: '', label: 'AI Task entity for transcription' },
    show_transcript: { type: 'boolean', default: true, label: 'Show transcript' },
    show_team_logo: { type: 'boolean', default: true, label: 'Show team logo' },
    show_message_time: { type: 'boolean', default: true, label: 'Show message time' },
    mark_new_messages: { type: 'boolean', default: true, label: 'Mark new messages' },
    show_transcription_status: { type: 'boolean', default: true, label: 'Show transcription status' },
  }, ['team_radio', 'driver_list'], { spoiler: true, focus: ['driver', 'team'], experimental: true, defaultFields: ['radio_driver', 'radio_team', 'radio_audio', 'radio_transcript', 'radio_time'] }),
  results: module('results', 'Results', ['result_position', 'driver', 'team', 'grid_position', 'position_change', 'laps', 'result_time', 'result_status', 'points', 'qualifying_position', 'qualifying_time', 'grid_delta', 'qualifying_segment', 'qualifying_delta'], {
    content: { type: 'enum', values: ['latest_race', 'race_results', 'sprint_results', 'starting_grid'], default: 'latest_race', label: 'Result content' },
    round: { type: 'source_choice', default: '', label: 'Round' },
    sort: { type: 'enum', values: ['result_position', 'grid_position', 'driver', 'points'], default: 'result_position', label: 'Sort by' },
    direction: { type: 'enum', values: ['asc', 'desc'], default: 'asc', label: 'Direction' },
    rows: { type: 'integer', min: 1, max: 100, default: 30, label: 'Maximum rows' },
    presentation: { type: 'enum', values: ['table', 'grid'], default: 'table', label: 'Presentation' },
    show_selector: { type: 'boolean', default: true, label: 'Show round selector' },
    show_context: { type: 'boolean', default: true, label: 'Show event details' },
    show_status: { type: 'boolean', default: true, label: 'Show grid status' },
    show_source: { type: 'boolean', default: false, label: 'Show source' },
    show_session_type_badge: { type: 'boolean', default: true, label: 'Show session type' },
    spoiler_placeholder: { type: 'text', default: '', label: 'Spoiler placeholder' },
    driver_image_type: { type: 'enum', values: ['team_logo', 'headshot'], default: 'team_logo', label: 'Driver image' },
  }, ['last_race_results', 'season_results', 'sprint_results', 'starting_grid'], { spoiler: true, focus: ['driver', 'team'], defaultFields: ['result_position', 'driver', 'team', 'result_time', 'points'], fieldDefinitions: {
    driver: { ...FIELDS.driver, source: 'selected_result', path: 'results[].driver', modes: ['results'], identity: ['entry', 'season', 'round', 'session', 'driver'] },
    team: { ...FIELDS.team, source: 'selected_result', path: 'results[].constructor', modes: ['results'], identity: ['entry', 'season', 'round', 'session', 'team'] },
    laps: { ...FIELDS.laps, source: 'selected_result', path: 'results[].laps', modes: ['results'] },
  } }),
  standings: module('standings', 'Championship', ['result_position', 'driver', 'team', 'points', 'wins', 'predicted_position', 'predicted_points', 'points_change'], {
    competitors: { type: 'enum', values: ['drivers', 'teams'], default: 'drivers', label: 'Championship' },
    sort: { type: 'enum', values: ['result_position', 'points', 'wins', 'driver', 'team', 'predicted_position', 'predicted_points'], default: 'result_position', label: 'Sort by' },
    direction: { type: 'enum', values: ['asc', 'desc'], default: 'asc', label: 'Direction' },
    rows: { type: 'integer', min: 1, max: 100, default: 30, label: 'Maximum rows' },
    show_mode_badge: { type: 'boolean', default: true, label: 'Show standings status' },
    show_availability_notice: { type: 'boolean', default: true, label: 'Explain projection availability' },
    spoiler_placeholder: { type: 'text', default: '', label: 'Spoiler placeholder' },
    driver_image_type: { type: 'enum', values: ['team_logo', 'headshot'], default: 'team_logo', label: 'Driver image' },
  }, ['driver_standings', 'constructor_standings', 'championship_prediction_drivers', 'championship_prediction_teams'], { spoiler: true, focus: ['driver', 'team'], defaultFields: ['result_position', 'driver', 'team', 'points', 'wins'], fieldDefinitions: Object.fromEntries(['result_position', 'driver', 'team', 'points', 'wins'].map(id => [id, { ...FIELDS[id], source: 'selected_standings', path: `standings[].${id}`, modes: ['standings'], identity: ['entry', 'season', 'round', 'competitor'] }])) }),
  archive: module('archive', 'Historical archive', ['result_position', 'driver', 'team', 'grid_position', 'position_change', 'laps', 'result_time', 'result_status', 'points', 'q1_time', 'q2_time', 'q3_time', 'lap_series'], {
    year: { type: 'integer', min: 1950, max: 2200, default: new Date().getUTCFullYear(), label: 'Year' },
    round: { type: 'source_choice', default: '', label: 'Grand Prix' },
    session_key: { type: 'source_choice', default: '', label: 'Session' },
    profile: { type: 'enum', values: ['auto', 'custom'], default: 'auto', label: 'Column profile' },
    content: { type: 'enum', values: ['classification', 'lap_time', 'lap_position'], default: 'classification', label: 'Archive view' },
    selected: { type: 'source_list', default: [], label: 'Drivers (empty = classification order)' },
    presentation: { type: 'enum', values: ['chart', 'table', 'both'], default: 'chart', label: 'Presentation' },
    show_session_selector: { type: 'boolean', default: true, label: 'Show archive selectors' },
    show_session_type_badge: { type: 'boolean', default: true, label: 'Show session type' },
    spoiler_placeholder: { type: 'text', default: '', label: 'Spoiler placeholder' },
    start_lap: { type: 'integer', min: 0, max: 500, default: 0, label: 'First lap (0 = first recorded)' },
    end_lap: { type: 'integer', min: 0, max: 500, default: 0, label: 'Last lap (0 = last recorded)' },
    series_limit: { type: 'integer', min: 1, max: 100, default: 5, label: 'Maximum chart drivers' },
    show_points: { type: 'boolean', default: true, label: 'Show chart points' },
    show_round_labels: { type: 'boolean', default: true, label: 'Show lap labels' },
    chart_height: { type: 'integer', min: 300, max: 720, default: 420, label: 'Chart height' },
    sort: { type: 'enum', values: ['result_position', 'grid_position', 'driver', 'points'], default: 'result_position', label: 'Sort by' },
    direction: { type: 'enum', values: ['asc', 'desc'], default: 'asc', label: 'Direction' },
    rows: { type: 'integer', min: 1, max: 100, default: 30, label: 'Maximum rows' },
  }, ['history'], { spoiler: true, defaultFields: ['result_position', 'driver', 'team', 'result_time', 'points'] }),
  telemetry: module('telemetry', 'Replay telemetry', ['telemetry_speed', 'telemetry_throttle', 'telemetry_brake', 'telemetry_gear', 'telemetry_drs', 'telemetry_rpm', 'telemetry_delta_s'], {
    selected: { type: 'lap_selections', default: [], label: 'Selected laps' },
    session_id: { type: 'text', default: '', label: 'Saved replay session' },
    axis: { type: 'enum', values: ['time_s', 'distance'], default: 'time_s', label: 'Horizontal axis' },
    presentation: { type: 'enum', values: ['chart', 'table', 'both'], default: 'chart', label: 'Presentation' },
    show_explanation: { type: 'boolean', default: true, label: 'Show About section' },
  }, ['replay_status', 'replay_player', 'analysis/telemetry_catalog', 'analysis/telemetry_compare'], { spoiler: true, defaultFields: ['telemetry_speed', 'telemetry_throttle', 'telemetry_brake'] }),
  replay: module('replay', 'Replay', ['replay_selection', 'replay_transport', 'replay_progress'], {
    display: { type: 'enum', values: ['full', 'compact'], default: 'full', label: 'Replay layout' },
    secondary_selects: { type: 'boolean', default: true, label: 'Show year and reference choices' },
    start_reference: { type: 'boolean', default: true, label: 'Show start reference' },
    seek_controls: { type: 'boolean', default: true, label: 'Show seek controls' },
    refresh: { type: 'boolean', default: true, label: 'Show refresh action' },
    status_details: { type: 'boolean', default: true, label: 'Show scope details' },
    show_button_labels: { type: 'boolean', default: true, label: 'Show button labels' },
  }, ['replay_status', 'replay_player', 'replay_year_select', 'replay_session_select', 'replay_start_reference', 'replay_load', 'replay_refresh']),
  lap_chart: module('lap_chart', 'Lap history chart', ['lap_series'], {
    metric: { type: 'enum', values: ['lap_time', 'lap_change'], default: 'lap_time', label: 'Measure' },
    presentation: { type: 'enum', values: ['chart', 'table', 'both'], default: 'chart', label: 'Presentation' },
    selected: { type: 'source_list', default: [], label: 'Drivers (empty = session order)' },
    start_lap: { type: 'integer', min: 0, max: 500, default: 0, label: 'First lap (0 = first observed)' },
    end_lap: { type: 'integer', min: 0, max: 500, default: 0, label: 'Last lap (0 = last observed)' },
    series_limit: { type: 'integer', min: 1, max: 30, default: 5, label: 'Maximum drivers' },
  }, ['driver_positions', 'driver_list', 'current_session'], { spoiler: true, focus: ['driver', 'team'] }),
  progression: module('progression', 'Season progression', ['progression'], {
    competitors: { type: 'enum', values: ['drivers', 'teams'], default: 'drivers', label: 'Competitors' },
    metric: { type: 'enum', values: ['cumulative_points', 'points_per_round', 'wins_per_round'], default: 'cumulative_points', label: 'Measure' },
    presentation: { type: 'enum', values: ['chart', 'table', 'both'], default: 'chart', label: 'Presentation' },
    selected: { type: 'source_list', default: [], label: 'Drivers or teams (empty = leaders)' },
    start_round: { type: 'source_choice', default: '', label: 'First round' },
    end_round: { type: 'source_choice', default: '', label: 'Last round' },
    series_limit: { type: 'integer', min: 1, max: 30, default: 5, label: 'Maximum series' },
    show_legend: { type: 'boolean', default: true, label: 'Show legend' },
    legend_position: { type: 'enum', values: ['bottom', 'left', 'right'], default: 'bottom', label: 'Legend position' },
    show_legend_points: { type: 'boolean', default: true, label: 'Show points in legend' },
    show_points: { type: 'boolean', default: true, label: 'Show chart points' },
    show_round_labels: { type: 'boolean', default: true, label: 'Show round labels' },
    show_future_rounds: { type: 'boolean', default: true, label: 'Show future rounds' },
    chart_height: { type: 'integer', min: 240, max: 520, default: 320, label: 'Chart height' },
  }, ['driver_points_progression', 'constructor_points_progression'], { spoiler: true, focus: ['driver', 'team'] }),
  documents: module('documents', 'FIA documents', ['document_number', 'document_title', 'document_time'], {
    presentation: { type: 'enum', values: ['list', 'latest'], default: 'list', label: 'Document view' },
    search: { type: 'text', default: '', label: 'Title contains' },
    order: { type: 'enum', values: ['newest', 'oldest'], default: 'newest', label: 'Order' },
    limit: { type: 'integer', min: 1, max: 300, default: 15, label: 'Documents to show' },
    list_max_height: { type: 'integer', min: 0, max: 2000, default: 0, label: 'List height in pixels (0 = automatic)' },
    open_new_tab: { type: 'boolean', default: true, label: 'Open links in a new tab' },
    document_coloring: { type: 'boolean', default: true, label: 'Color-code document rows' },
    show_document_type: { type: 'boolean', default: true, label: 'Show document type' },
    show_fia_logo: { type: 'boolean', default: true, label: 'Show FIA mark' },
    show_pdf_icon: { type: 'boolean', default: true, label: 'Show PDF icon' },
    show_count: { type: 'boolean', default: true, label: 'Show document count' },
    show_race_context: { type: 'boolean', default: true, label: 'Show race context' },
    show_latest_badge: { type: 'boolean', default: true, label: 'Show latest badge' },
  }, ['fia_documents'], { spoiler: true }),
  map: module('map', 'Track map', ['track_map', 'map_drivers', 'map_start_finish', 'map_corners', 'map_sectors', 'map_speed_traps', 'map_detection_zones'], {
    labels: { type: 'enum', values: ['code', 'number', 'off'], default: 'code', label: 'Driver labels' },
    show_car_markers: { type: 'boolean', default: true, label: 'Show car markers' },
    focus: { type: 'enum', values: ['highlight', 'filter'], default: 'highlight', label: 'Driver focus' },
    orientation: { type: 'enum', values: ['source', 'raw'], default: 'source', label: 'Orientation' },
    vertical: { type: 'enum', values: ['normal', 'flipped'], default: 'flipped', label: 'Vertical axis' },
    layout_mode: { type: 'enum', values: ['auto', 'compact', 'full'], default: 'auto', label: 'Layout mode' },
    show_footer: { type: 'boolean', default: true, label: 'Show source footer' },
    show_session_info: { type: 'boolean', default: true, label: 'Show session information' },
    show_lap_progress: { type: 'boolean', default: true, label: 'Show lap progress' },
    show_track_status: { type: 'boolean', default: true, label: 'Show track status' },
    track_status_line_mode: { type: 'enum', values: ['accent', 'full', 'off'], default: 'accent', label: 'Track-status line' },
    show_driver_count: { type: 'boolean', default: true, label: 'Show driver count' },
  }, ['track_map', 'current_session', 'race_lap_count', 'track_status'], { spoiler: true, stream: 'track_map', focus: ['driver', 'team'], defaultFields: ['track_map', 'map_drivers'] }),
  battles: module('battles', 'Battles and position changes', ['battle_status', 'incident_drivers', 'battle_gap', 'exchange_positions', 'analysis_source', 'analysis_quality'], {
    content: { type: 'enum', values: ['active_battles', 'battle_history', 'position_exchanges'], default: 'active_battles', label: 'Observations' },
    presentation: { type: 'enum', values: ['list', 'table'], default: 'list', label: 'Presentation' },
    kinds: { type: 'list', values: ['battle_started', 'battle_ended', 'position_exchange', 'likely_on_track_overtake'], default: [], label: 'Kinds (empty = all)' },
    minimum_score: { type: 'integer', min: 0, max: 100, default: 0, label: 'Minimum evidence score (%)' },
    order: { type: 'enum', values: ['newest', 'oldest'], default: 'newest', label: 'Recorded order' },
    rows: { type: 'integer', min: 1, max: 500, default: 20, label: 'Maximum rows' },
    show_explanation: { type: 'boolean', default: true, label: 'Show About section' },
  }, ['analysis'], { spoiler: true, stream: 'analysis', focus: ['driver', 'team'] }),
  strategy: module('strategy', 'Strategy analysis', ['driver', 'team', 'tyre', 'stint_number', 'stint_first_lap', 'stint_last_lap', 'stint_start_age', 'clean_pace', 'raw_pace', 'degradation', 'clean_samples', 'raw_samples', 'excluded_samples', 'exclusion_reasons', 'strategy_pit_loss', 'compound_gap', 'analysis_quality', 'incident_drivers', 'comparison_pace', 'comparison_gap', 'pace_leader', 'comparison_tyres', 'crossover_age', 'observed_age_range', 'crossover_pace', 'strategy_outcome', 'comparison_stops', 'exchange_positions', 'analysis_source'], {
    content: { type: 'enum', values: ['stints', 'compound_comparison', 'teammates', 'crossover', 'pit_outcomes'], default: 'stints', label: 'Analysis content' },
    compounds: { type: 'list', values: ['SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET', 'UNKNOWN'], default: [], label: 'Compounds (empty = all)' },
    minimum_score: { type: 'integer', min: 0, max: 100, default: 0, label: 'Minimum evidence score (%)' },
    presentation: { type: 'enum', values: ['table', 'both', 'chart'], default: 'table', label: 'Stint presentation' },
    minimum_clean_laps: { type: 'integer', min: 0, max: 500, default: 0, label: 'Minimum clean laps per row' },
    sort: { type: 'enum', values: ['driver', 'stint_number', 'clean_pace', 'clean_samples', 'degradation', 'analysis_quality'], default: 'driver', label: 'Sort by' },
    direction: { type: 'enum', values: ['asc', 'desc'], default: 'asc', label: 'Direction' },
    rows: { type: 'integer', min: 1, max: 500, default: 30, label: 'Maximum rows' },
    show_explanation: { type: 'boolean', default: true, label: 'Show About section' },
  }, ['analysis'], { spoiler: true, stream: 'analysis', focus: ['driver', 'team'], fieldDefinitions: {
    analysis_quality: { ...FIELDS.analysis_quality, path: 'strategy.stints[].confidence' },
    compound_gap: { ...FIELDS.compound_gap, source: 'analysis', path: 'strategy.compound_comparison[].delta_to_fastest', estimated: true },
  } }),
  timeline: module('timeline', 'Session timeline', ['event_time', 'incident_drivers', 'incident_lap', 'analysis_title', 'analysis_description', 'analysis_category', 'analysis_source', 'analysis_quality'], {
    categories: { type: 'list', values: ['session', 'track_status', 'race_control', 'lap_control', 'investigation', 'lap', 'pit', 'weather', 'radio', 'position', 'battle', 'classification'], default: [], label: 'Categories (empty = all)' },
    search: { type: 'text', default: '', label: 'Text contains' },
    order: { type: 'enum', values: ['newest', 'oldest'], default: 'newest', label: 'Order' },
    rows: { type: 'integer', min: 1, max: 500, default: 30, label: 'Maximum events' },
    presentation: { type: 'enum', values: ['list', 'table'], default: 'list', label: 'Presentation' },
  }, ['analysis'], { spoiler: true, stream: 'analysis', focus: ['driver', 'team'], defaultFields: ['event_time', 'analysis_title', 'incident_drivers', 'incident_lap', 'analysis_source'], fieldDefinitions: {
    event_time: { ...FIELDS.event_time, source: 'analysis', path: 'timeline.events[].occurred_at' },
    incident_drivers: { ...FIELDS.incident_drivers, source: 'analysis', path: 'timeline.events[].driver_numbers' },
    incident_lap: { ...FIELDS.incident_lap, source: 'analysis', path: 'timeline.events[].lap_number' },
  } }),
  tyres: module('tyres', 'Tyres', ['position', 'driver', 'team', 'tyre', 'tyre_age', 'tyre_new', 'compound_best', 'compound_gap', 'compound_laps', 'new_sets', 'total_stints', 'best_runs'], {
    content: { type: 'enum', values: ['current', 'statistics'], default: 'current', label: 'Tyre content' },
    compounds: { type: 'list', values: ['SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET', 'UNKNOWN'], default: [], label: 'Compounds (empty = all)' },
    sort: { type: 'enum', values: ['position', 'driver', 'tyre_age', 'compound_best', 'compound_laps'], default: 'position', label: 'Sort by' },
    direction: { type: 'enum', values: ['asc', 'desc'], default: 'asc', label: 'Direction' },
    rows: { type: 'integer', min: 1, max: 100, default: 30, label: 'Maximum rows' },
    show_compound_name: { type: 'boolean', default: true, label: 'Show compound name' },
    best_times_limit: { type: 'integer', min: 1, max: 500, default: 3, label: 'Fastest stints per compound' },
  }, ['current_tyres', 'tyre_statistics', 'driver_list'], { spoiler: true, focus: ['driver', 'team'] }),
  pit_stops: module('pit_stops', 'Pit stops', ['driver', 'team', 'status', 'pit_count', 'stop_lap', 'stop_time', 'lane_time', 'pit_delta', 'event_time'], {
    content: { type: 'enum', values: ['latest_stop', 'all_stops'], default: 'latest_stop', label: 'Stop history' },
    sort: { type: 'enum', values: ['event_time', 'driver', 'stop_lap', 'stop_time', 'lane_time', 'pit_delta'], default: 'event_time', label: 'Sort by' },
    direction: { type: 'enum', values: ['asc', 'desc'], default: 'desc', label: 'Direction' },
    rows: { type: 'integer', min: 1, max: 500, default: 30, label: 'Maximum rows' },
    show_availability_notice: { type: 'boolean', default: true, label: 'Explain F1TV availability' },
  }, ['pitstops', 'driver_list', 'driver_positions', 'f1tv_token_status'], { spoiler: true, focus: ['driver', 'team'], defaultFields: ['driver', 'status', 'stop_lap', 'stop_time', 'lane_time'], fieldDefinitions: {
    status: { ...FIELDS.status, source: 'driver_positions', path: 'drivers[].status', capability: 'public_timing' },
    event_time: { ...FIELDS.event_time, source: 'pitstops', path: 'cars.*.stops[].timestamp', capability: 'extended_timing' },
  } }),
  incidents: module('incidents', 'Incidents', ['incident_status', 'incident_drivers', 'event_time', 'incident_lap', 'incident_location', 'incident_reason', 'incident_penalty', 'driver', 'team', 'track_limit_deletions', 'track_limit_warning', 'track_limit_penalty'], {
    content: { type: 'enum', values: ['investigations', 'track_limits', 'track_limits_summary'], default: 'investigations', label: 'Incident content' },
    summary_sort: { type: 'enum', values: ['track_limit_deletions', 'driver'], default: 'track_limit_deletions', label: 'Summary order' },
    presentation: { type: 'enum', values: ['list', 'table'], default: 'list', label: 'Presentation' },
    categories: { type: 'list', values: ['noted', 'under_investigation', 'no_further_action', 'penalty', 'time_deleted', 'warning'], default: [], label: 'Statuses (empty = all)' },
    search: { type: 'text', default: '', label: 'Text contains' },
    order: { type: 'enum', values: ['newest', 'oldest'], default: 'newest', label: 'Order' },
    rows: { type: 'integer', min: 1, max: 500, default: 30, label: 'Maximum events' },
  }, ['investigations', 'track_limits', 'driver_list'], { spoiler: true, focus: ['driver', 'team'], defaultFields: ['incident_status', 'incident_drivers', 'event_time', 'incident_lap', 'incident_location', 'incident_reason', 'incident_penalty'], fieldDefinitions: {
    event_time: { ...FIELDS.event_time, source: 'selected_incidents', path: 'incident.nfi_utc ?? incident.utc' },
  } }),
  weather: module('weather', 'Weather', WEATHER_FIELDS.map(field => field.id), {
    content: { type: 'enum', values: ['weather_overview', 'current_conditions', 'automatic_conditions', 'race_forecast', 'track_conditions'], default: 'weather_overview', label: 'Weather source' },
    presentation: { type: 'enum', values: ['metrics', 'compact_list'], default: 'metrics', label: 'Weather layout' },
    colored_icons: { type: 'boolean', default: true, label: 'Colored weather icons' },
    show_explanation: { type: 'boolean', default: true, label: 'Show About section' },
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
    ...(/^q[123]_time$/.test(id) ? { type: 'classification_duration', label: `${id.slice(0, 2).toUpperCase()} time` } : {}) };
  if (module.type === 'incidents' && module.options?.content === 'track_limits_summary' && field) return { ...field, source: 'track_limits', identity: ['entry', 'session', 'driver'],
    path: ({ driver: 'by_driver.key', team: 'driver_list.drivers[].team', event_time: 'latest(by_driver.*.violations[].utc)' })[id] ?? field.path,
    ...(id === 'event_time' ? { label: 'Latest recorded event' } : {}) };
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
  if (module.type === 'standings' && id === 'result_position') field = { ...field, label: 'Position' };
  if (module.type === 'tyres' && ['position', 'driver', 'team', 'tyre', 'tyre_age'].includes(id)) {
    const stats = module.options?.content === 'statistics';
    field = { ...field, source: stats ? 'tyre_statistics' : 'current_tyres', path: stats ? 'compounds.key' : ({ position: 'drivers[].position', driver: 'drivers[].racing_number', team: 'driver_list.drivers[].team', tyre: 'drivers[].compound', tyre_age: 'drivers[].stint_laps' })[id] };
  }
  return field;
}
export const INCIDENT_SIGNALS = {
  noted: { symbol: '○', label: 'Noted' },
  under_investigation: { symbol: '?', label: 'Under investigation' },
  no_further_action: { symbol: '✓', label: 'No further action' },
  penalty: { symbol: '!', label: 'Penalty' },
  time_deleted: { symbol: '×', label: 'Lap time deleted' },
  warning: { symbol: '△', label: 'Warning' },
};
export const PRESETS = {
  weekend: { label: 'Race weekend', modules: [{ type: 'overview' }, { type: 'calendar' }, { type: 'weather', options: { content: 'automatic_conditions' } }, { type: 'weather', options: { content: 'race_forecast' } }] },
  weather: { label: 'Weather comparison', modules: [{ type: 'weather', options: { content: 'automatic_conditions' } }, { type: 'weather', options: { content: 'race_forecast' } }] },
  session: { label: 'Follow the session', modules: [{ type: 'overview', fields: ['session', 'track_status'] }, { type: 'timing' }, { type: 'race_control' }] },
  driver: { label: 'My driver', modules: [{ type: 'overview', fields: ['session', 'track_status'] }, { type: 'timing', fields: ['position', 'driver', 'last_lap', 'best_lap', 'tyre', 'tyre_age'], options: { history: 5 } }, { type: 'race_control' }] },
  results: { label: 'Results and championship', modules: [{ type: 'results', options: { rows: 5 } }, { type: 'standings', options: { rows: 5 } }, { type: 'progression' }] },
  custom: { label: 'Build your own', modules: [] },
};

const CONTENT_TITLES = { incidents: { investigations: 'Incidents', track_limits: 'Track limits events', track_limits_summary: 'Track limits by driver' }, weather: { automatic_conditions: 'Automatic current weather', weather_overview: 'Weather overview', current_conditions: 'Current circuit weather', race_forecast: 'Race-start forecast', track_conditions: 'Track weather observations' }, strategy: { stints: 'Stint pace and quality', compound_comparison: 'Compound pace comparison', teammates: 'Teammate comparison', crossover: 'Compound crossover estimates', pit_outcomes: 'Observed pit-cycle outcomes' }, battles: { active_battles: 'Current battles', battle_history: 'Battle history', position_exchanges: 'Position exchanges' } };
export function moduleTitle(module, language = 'en') {
  if (module.title) return module.title;
  const content = module.options?.content ?? MODULES[module.type]?.options?.content?.default;
  const titles = CONTENT_TITLES[module.type]?.[content];
  return titles ? words(language, titles) : label(MODULES[module.type], language) || module.type;
}
