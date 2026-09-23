// Demonstration values are never merged with the user's Home Assistant states.
export function makeDemo(scene = 'race', language = 'en', entryId = 'demo') {
  const now = Date.parse('2026-09-13T13:30:00Z'), states = {};
  const entry = { entry_id: entryId || 'demo', title: 'F1 Sensor · Demo', entities: {}, global_entities: { no_spoiler_mode: 'switch.f1_demo_spoilers' }, disabled_entities: [] };
  states['switch.f1_demo_spoilers'] = { state: 'off', attributes: {} };
  const put = (key, state, attributes = {}) => {
    const entityId = `sensor.f1_demo_${key}`; entry.entities[key] = entityId;
    states[entityId] = { entity_id: entityId, state, attributes, last_updated: new Date(now).toISOString() };
  };
  const name = ({ practice: 'Practice 1', qualifying: 'Qualifying', sprint_qualifying: 'Sprint Qualifying', sprint: 'Sprint', race: 'Race', ended: 'Race', replay: 'Race', missing: 'Race', before: 'Race' })[scene] ?? 'Race';
  const active = !['before', 'ended', 'missing'].includes(scene);
  const qualifying = ['qualifying', 'sprint_qualifying'].includes(scene);
  const people = [
    ['16', 'LEC', 'Charles Leclerc', 'Ferrari', '#e80020', 'S'],
    ['4', 'NOR', 'Lando Norris', 'McLaren', '#ff8000', 'M'],
    ['63', 'RUS', 'George Russell', 'Mercedes', '#27f4d2', 'H'],
    ['1', 'VER', 'Max Verstappen', 'Red Bull Racing', '#3671c6', 'M'],
    ['14', 'ALO', 'Fernando Alonso', 'Aston Martin', '#229971', 'H'],
  ].map(([racing_number, tla, full_name, team, team_color, compound]) => ({ racing_number, tla, full_name, team, team_color, compound }));
  people[0].headshot_small = 'https://example.com/demo-driver-headshot.png';
  put('current_session', active ? name : scene === 'missing' ? 'unavailable' : 'no_session', { season: 2026, meeting_key: 'demo-meeting', session_key: 'demo-session', meeting_name: 'Demo Grand Prix', start: '2026-09-13T13:00:00Z', active, last_label: active || scene === 'ended' ? name : null });
  put('session_status', active ? 'live' : scene === 'ended' ? 'finished' : scene === 'missing' ? 'unavailable' : 'inactive');
  for (const [key, value] of [['session_time_elapsed', 1800], ['session_time_remaining', 5400], ['race_time_to_three_hour_limit', 9000]]) put(key, active ? 'clock' : 'unavailable', { value_seconds: value, session_name: name, session_part: qualifying ? 2 : null, clock_running: active && scene !== 'replay', clock_phase: active ? scene === 'replay' ? 'paused' : 'running' : 'idle', source_quality: 'official' });
  put('track_status', active ? 'Clear' : 'unavailable');
  put('race_lap_count', active ? '12' : 'unavailable', active ? { total_laps: 53 } : {});
  put('driver_list', String(people.length), { drivers: people });
  put('driver_positions', active || scene === 'ended' ? '12' : 'unavailable', { drivers: active || scene === 'ended' ? people.map((driver, index) => ({
    ...driver, q1_time: qualifying ? 81.12 + index * .2 : null, q2_time: qualifying && index < 3 ? 80.9 + index * .25 : null, q3_time: null, q1_knocked_out: qualifying && index >= 3, q2_knocked_out: false, q3_knocked_out: false, q1_position: qualifying ? index + 1 : null,
    current_position: index + 1, completed_laps: 12, status: index === 3 ? 'in_pit' : 'on_track', in_pit: index === 3,
    gap_to_leader: index ? `+${(index * 1.245).toFixed(3)}` : 'LEADER', interval_to_position_ahead: index ? '+1.245' : null,
    laps: { 10: 81.543 + index * .2, 11: 81.1 + index * .18, 12: 80.873 + index * .23 }, best_lap_time: 80.873 + index * .23, best_lap_lap: 12, fastest_lap: index === 0,
    sector_current_lap: 13, sectors: { current: {
      sector_1: { time: 24.321 + index * .121, lap: 13, overall_fastest: index === 0, personal_fastest: index < 3 },
      sector_2: { time: 30.543 + index * .14, lap: 13, personal_fastest: index === 1 },
    }, personal_best: Object.fromEntries([1, 2, 3].map(n => [`sector_${n}`, { time: [24.321, 30.543, 25.91][n - 1] + index * .1, lap: 10 + n - 1, session_part: qualifying ? 2 : null, personal_fastest: true, overall_fastest: index === 0 }])) },
  })) : [], current_qualifying_part: qualifying ? 2 : null });
  put('current_tyres', active ? String(people.length) : 'unavailable', { drivers: people.map((driver, i) => ({ racing_number: driver.racing_number, compound_short: driver.compound, position: i + 1, new: i !== 3, stint_laps: 7 + i })) });
  put('tyre_statistics', active ? 'SOFT' : 'unavailable', { status: 'ready', source_stream: 'TimingAppData', compounds: Object.fromEntries(['SOFT', 'MEDIUM', 'HARD'].map((compound, index) => [compound, { total_laps: 78 + index * 14, sets_used: index + 2, sets_used_total: index + 4, best_times: [{ time_secs: 80.873 + index * .75, racing_number: people[index].racing_number, driver_name: people[index].full_name, driver_tla: people[index].tla, stint_index: 0, new_tyre: true }] }])), deltas: { SOFT: 0, MEDIUM: .75, HARD: 1.5 } });
  put('pitstops', active ? '3' : 'unavailable', { cars: { 16: { count: 2, stops: [{ lap: 5, timestamp: '2026-09-13T13:08:00Z', pit_stop_time: 2.43, pit_lane_time: 23.781, pit_delta: 20.02 }, { lap: 10, timestamp: '2026-09-13T13:20:00Z', pit_stop_time: 2.17, pit_lane_time: 22.9, pit_delta: null }] }, 4: { count: 1, stops: [{ lap: 9, timestamp: '2026-09-13T13:18:00Z', pit_stop_time: 2.5, pit_lane_time: 23.15, pit_delta: 19.521 }] } }, last_update: '2026-09-13T13:20:00Z' });
  put('investigations', active ? '2' : 'unavailable', { noted: [], under_investigation: [{ drivers: ['NOR', 'VER'], racing_numbers: ['4', '1'], utc: '2026-09-13T13:24:00Z', lap: 11, location: 'TURN 1', reason: 'Demo · causing a collision', after_race: true }], penalties: [{ driver: 'VER', racing_number: '1', utc: '2026-09-13T13:26:00Z', lap: 12, penalty: '5 SECOND TIME PENALTY', reason: 'Demo · leaving the track' }], no_further_action: [{ drivers: ['LEC'], racing_numbers: ['16'], utc: '2026-09-13T13:15:00Z', nfi_utc: '2026-09-13T13:28:00Z', lap: 8, location: 'PIT EXIT', reason: 'Demo · impeding' }] });
  put('track_limits', active ? '2' : 'unavailable', { by_driver: { NOR: { racing_number: '4', deletions: 1, warning: true, penalty: null, violations: [{ utc: '2026-09-13T13:25:00Z', lap: 11, turn: 7, type: 'time_deleted' }, { utc: '2026-09-13T13:27:00Z', lap: 12, turn: 7, type: 'warning' }] } }, total_deletions: 1, total_warnings: 1, total_penalties: 0 });
  put('next_race', '2026-09-20T13:00:00Z', { race_name: 'Demo Grand Prix', circuit_name: 'Demonstration Circuit', circuit_locality: 'Monza', circuit_country: 'Italy', country_flag_url: 'https://flagcdn.com/w80/it.png', circuit_map_url: 'https://example.com/demo-circuit-map.webp', circuit_timezone: 'Europe/Rome', season: '2026', round: 'demo', first_practice_start_utc: '2026-09-18T10:30:00Z', second_practice_start_utc: '2026-09-18T14:00:00Z', third_practice_start_utc: '2026-09-19T10:30:00Z', qualifying_start_utc: '2026-09-19T14:00:00Z', race_start_utc: '2026-09-20T13:00:00Z', defending_winner: { driver_name: 'Charles Leclerc', constructor_name: 'Ferrari', season: '2025' }, defending_pole_sitter: { driver_name: 'Lando Norris', constructor_name: 'McLaren', season: '2025' }, races_held_here: 75, first_f1_race_here: { season: '1950', race_name: 'Demo Grand Prix' }, last_year_podium: { season: '2025', podium: [{ driver_name: 'Charles Leclerc', constructor_name: 'Ferrari' }, { driver_name: 'Lando Norris', constructor_name: 'McLaren' }, { driver_name: 'George Russell', constructor_name: 'Mercedes' }] }, last_5_winners: [{ driver_name: 'Charles Leclerc', constructor_name: 'Ferrari', season: '2025' }, { driver_name: 'Max Verstappen', constructor_name: 'Red Bull Racing', season: '2024' }], top_5_driver_wins_here: [{ driver_name: 'Lewis Hamilton', wins: 5 }], top_5_constructor_wins_here: [{ constructor_name: 'Ferrari', wins: 20 }], dnf_rate_last_5: 12.5, pole_to_win_conversion_last_5: 60 });
  put('weather', '24.5', { race_name: 'Demo Grand Prix', circuit_name: 'Demonstration Circuit', current_temperature: 24.5, current_humidity: 58, current_wind_speed: 3.2, current_wind_speed_unit: 'm/s', current_wind_from_direction_degrees: 225, current_wind_gusts: 5.8, current_cloud_cover: 30, current_visibility: 24000, current_precipitation: 0, current_precipitation_probability: 5, current_weather_code: 2, race_temperature: 22.8, race_humidity: 65, race_wind_speed: 4.1, race_wind_gusts: 7.2, race_wind_from_direction_degrees: 270, race_cloud_cover: 70, race_visibility: 18000, race_weather_code: 61, race_precipitation: 0.4, race_precipitation_probability: 15 });
  put('track_weather', active ? '25.2' : 'unavailable', active ? { air_temperature: 25.2, track_temperature: 43.8, humidity: 57, pressure: 1012.4, rainfall: 0, rainfall_unit: 'mm', wind_speed: 3.1, wind_from_direction_degrees: 225, measurement_inferred: true } : {});
  const results = people.map((driver, index) => ({ number: driver.racing_number, position: String(index + 1), grid: String(index === 0 ? 3 : index === 2 ? 1 : index + 1), laps: '53', time: index ? `+${(index * 4.83).toFixed(3)}` : '1:24:10.456', points: String([25, 18, 15, 12, 10][index]), status: 'Finished', driver: { permanentNumber: driver.racing_number, code: driver.tla, givenName: driver.full_name.split(' ')[0], familyName: driver.full_name.split(' ').slice(1).join(' ') }, constructor: { constructorId: driver.team.toLowerCase(), name: driver.team } }));
  put('last_race_results', 'Leclerc', { race_name: 'Demo Grand Prix', round: '14', race_start_utc: '2026-09-06T13:00:00Z', results });
  put('season_results', '2', { races: [{ round: '13', race_name: 'Previous Demo Grand Prix', results: results.map(item => ({ ...item, time: null })) }, { round: '14', race_name: 'Demo Grand Prix', results }] });
  put('sprint_results', '1', { races: [{ round: '13', race_name: 'Demo Sprint', results: results.map((item, index) => ({ ...item, laps: '24', points: String(8 - index) })) }] });
  put('starting_grid', 'provisional', { status: 'provisional', meeting_name: 'Demo Grand Prix', target_session_name: 'Race', source: 'qualifying', source_updated_at: '2026-09-12T14:30:00Z', grid: people.map((driver, index) => ({ racing_number: driver.racing_number, tla: driver.tla, driver_name: driver.full_name, team_name: driver.team, team_color: driver.team_color, grid_position: index + 1, qualifying_position: index + 1, qualifying_time_secs: 80.123 + index * .2 })) });
  put('driver_standings', '5', { season: '2026', round: '14', driver_standings: results.map((item, index) => ({ position: item.position, points: String(230 - index * 19), wins: String(index === 0 ? 5 : 2), Driver: item.driver, Constructors: [item.constructor] })) });
  put('constructor_standings', '5', { season: '2026', round: '14', constructor_standings: results.map((item, index) => ({ position: item.position, points: String(410 - index * 31), wins: String(6 - index), Constructor: item.constructor })) });
  put('championship_prediction_drivers', active ? 'LEC' : 'unavailable', { drivers: Object.fromEntries(people.map((driver, index) => [driver.racing_number, { RacingNumber: driver.racing_number, Tla: driver.tla, PredictedPosition: index + 1, PredictedPoints: 250 - index * 20 }])) });
  put('championship_prediction_teams', active ? 'Ferrari' : 'unavailable', { teams: Object.fromEntries(people.map((driver, index) => [driver.team, { TeamName: driver.team, PredictedPosition: index + 1, PredictedPoints: 450 - index * 35 }])) });
  const rounds = [{ round: 1, race_name: 'Demo opening round' }, { round: 2, race_name: 'Demo second round' }, { round: 3, race_name: 'Demo Grand Prix' }, { round: 4, race_name: 'Future Demo Grand Prix' }];
  put('driver_points_progression', '4', { season: '2026', rounds, drivers: Object.fromEntries(people.map((driver, index) => [driver.tla, { identity: { code: driver.tla, name: driver.full_name }, points_per_round: [25 - index * 2, 18 - index, 25 - index, null], cumulative_points: [25 - index * 2, 43 - index * 3, 68 - index * 4, null], wins_per_round: [index === 0 ? 1 : 0, index === 1 ? 1 : 0, index === 0 ? 1 : 0, null], totals: { points: 68 - index * 4 } }])) });
  put('constructor_points_progression', '4', { season: '2026', rounds, constructors: Object.fromEntries(people.map((driver, index) => [driver.team, { identity: { constructorId: driver.team, name: driver.team }, points_per_round: [43 - index * 2, 33 - index, 40 - index, null], cumulative_points: [43 - index * 2, 76 - index * 3, 116 - index * 4, null], wins_per_round: [index === 0 ? 1 : 0, index === 1 ? 1 : 0, index === 0 ? 1 : 0, null], totals: { points: 116 - index * 4 } }])) });
  put('fia_documents', '2', { race: { race_name: 'Demo Grand Prix', season: '2026', round: '14' }, documents: [{ name: 'Demo · Provisional starting grid', document_number: 20, published: '2026-09-12T15:00:00Z', url: 'https://www.fia.com/documents' }, { name: 'Demo · Event notes', document_number: 1, published: '2026-09-10T09:00:00Z', url: null }] });
  put('race_control', active ? 'TRACK CLEAR' : 'unavailable');
  const replaying = scene === 'replay', replayLabel = 'Demo Grand Prix · Race';
  put('replay_status', replaying ? 'paused' : 'idle', { selected_session: replaying ? replayLabel : null, selected_session_id: replaying ? 'demo-replay' : null, selected_session_year: replaying ? 2026 : null, selected_meeting_key: replaying ? 'demo-meeting' : null, selected_session_key: replaying ? 'demo-session' : null, selected_year: 2026, sessions_available: 1, index_status: 'ready' });
  for (const [key, domain, state, attributes] of [
    ['live_delay_number', 'number', '45', { min: 0, max: 300, step: 1 }],
    ['delay_calibration_switch', 'switch', 'off', { mode: 'idle', reference: 'session_live', idle_reason: null, last_result: null, elapsed: 0, started_at: null, waiting_since: null, timeout_at: null, recorded_lap: null }],
    ['live_delay_reference', 'select', 'Session live', { options: ['Session live', 'Lap sync (race/sprint)'] }],
    ['delay_calibration_match', 'button', 'unknown', {}],
    ['replay_player', 'media_player', replaying ? 'paused' : 'idle', { replay_state: replaying ? 'paused' : 'idle', selected_session: replaying ? replayLabel : null, selected_session_id: replaying ? 'demo-replay' : null, selected_session_year: replaying ? 2026 : null, selected_meeting_key: replaying ? 'demo-meeting' : null, selected_session_key: replaying ? 'demo-session' : null, media_position: replaying ? 1800 : 0, media_duration: replaying ? 7200 : 0 }],
    ['replay_year_select', 'select', '2026', { options: ['2026', '2025'] }],
    ['replay_session_select', 'select', replayLabel, { options: [replayLabel, 'Demo Grand Prix · Qualifying'] }],
    ['replay_start_reference', 'select', 'Session live', { options: ['Session live', 'Formation start (race/sprint)'] }],
    ['replay_load', 'button', 'unknown', {}], ['replay_refresh', 'button', 'unknown', {}],
  ]) {
    const entity_id = `${domain}.f1_demo_${key}`;
    entry.entities[key] = entity_id; states[entity_id] = { entity_id, state, attributes, last_updated: new Date(now).toISOString() };
  }
  if (scene === 'missing') for (const key of ['driver_list', 'driver_positions', 'current_tyres', 'race_control', 'tyre_statistics', 'pitstops', 'investigations', 'track_limits']) { states[entry.entities[key]].state = 'unavailable'; states[entry.entities[key]].attributes = {}; }
  const events = active ? [
    { event_id: 'demo-2', utc: '2026-09-13T13:29:12Z', category: 'Flag', flag: 'CLEAR', message: 'TRACK CLEAR' },
    { event_id: 'demo-1', utc: '2026-09-13T13:27:31Z', category: 'Other', car_number: '4', message: 'CAR 4 · TRACK LIMITS AT TURN 7 · LAP TIME DELETED' },
  ] : [];
  const analysis = { protocol_version: 1, provider: scene === 'replay' ? 'f1_replay' : 'f1_live', session_id: 'demo-analysis', session_name: name, phase: active ? 'live' : 'before',
    drivers: people.map(person => ({ driver_number: Number(person.racing_number), name: person.full_name, tla: person.tla, team: person.team })),
    timeline: { events: active ? [
      { event_id: 'timeline-1', revision: 1, sequence: 1, provider: 'f1_live', session_id: 'demo-analysis', occurred_at: '2026-09-13T13:24:00Z', category: 'race_control', title: 'Demo · track clear', driver_numbers: [], lap_number: 11, confidence: 1, supporting_signals: ['RaceControlMessages'] },
      { event_id: 'timeline-2', revision: 2, sequence: 2, provider: 'f1_live', session_id: 'demo-analysis', occurred_at: '2026-09-13T13:26:00Z', category: 'position', title: 'Demo · cars 16 and 4 exchanged position', description: 'Position exchange with pit context', driver_numbers: [16, 4], lap_number: 12, confidence: .55, supporting_signals: ['TimingData', 'pit_context'] },
    ] : [] }, capabilities: { timeline: active ? 'ready' : 'waiting_for_events' } };
  analysis.battles = { threshold_seconds: 1.5, active: active ? [{ battle_id: 'demo-battle', kind: 'battle_started', driver_numbers: [16, 4], gap_seconds: .85, confidence: .8, supporting_signals: ['TimingData', 'consecutive_gap_frames'], active: true }] : [], history: active ? [
    { battle_id: 'demo-ended', kind: 'battle_started', driver_numbers: [1, 63], gap_seconds: 1.2, confidence: .8, supporting_signals: ['TimingData', 'consecutive_gap_frames'], active: true },
    { battle_id: 'demo-ended', kind: 'battle_ended', driver_numbers: [1, 63], gap_seconds: 1.2, confidence: .75, supporting_signals: ['TimingData', 'gap_opened'], active: false },
  ] : [] };
  analysis.position_exchanges = active ? [{ event_id: 'demo-exchange', kind: 'position_exchange', driver_numbers: [16, 4], gaining_driver: 4, gap_seconds: 2.1, positions_before: { 16: 1, 4: 2 }, positions_after: { 16: 2, 4: 1 }, confidence: .55, supporting_signals: ['TimingData', 'pit_context'] }] : [];
  analysis.capabilities.battles = active ? 'ready' : 'waiting_for_positions';
  analysis.capabilities.position_exchanges = active ? 'ready' : 'waiting_for_positions';
  analysis.strategy = { status: active ? 'ready' : 'waiting_for_clean_laps', analysis_type: 'local_estimate', coverage: { raw_laps: active ? 40 : 0, clean_laps: active ? 30 : 0, excluded_laps: active ? 10 : 0 },
    stints: active ? people.map((person, index) => ({ driver_number: Number(person.racing_number), driver_name: person.full_name, team: person.team, stint_index: 0, compound: person.compound, first_lap: 1, last_lap: 8, tyre_age_at_start: 0, sample_count: 6, raw_sample_count: 8, adjusted_median_clean_pace: 81.12 + index * .21, raw_median_pace: 81.5 + index * .2, degradation_seconds_per_lap: .053 + index * .01, confidence: .8, excluded_laps: 2, excluded_reason_counts: { pit_in: 1, safety_car: 1 }, pit_loss_seconds: null })) : [],
    compound_comparison: active ? ['SOFT', 'MEDIUM', 'HARD'].map((compound, index) => ({ compound, median_clean_pace: 81.12 + index * .75, delta_to_fastest: index * .75, sample_count: 10, confidence: .85 })) : [],
    assumptions: ['Demonstration estimates from sample clean laps'],
  };
  analysis.drivers.push({ driver_number: 44, tla: 'HAM', name: 'Lewis Hamilton', team: 'Ferrari' });
  analysis.strategy.teammate_comparisons = active ? [{ team: 'Ferrari', drivers: [16, 44], median_clean_pace: { 16: 81.12, 44: 81.32 }, delta_seconds: .2, faster_driver: 16, confidence: .8 }] : [];
  analysis.strategy.compound_crossover_indications = active ? [{ compounds: ['SOFT', 'MEDIUM'], estimated_tyre_age_laps: 8.5, observed_age_range: [5, 12], pace_at_crossover: 82.13, confidence: .75, status: 'observed_range_estimate' }] : [];
  analysis.strategy.undercut_overcut_outcomes = active ? [{ team: 'Ferrari', drivers: [44, 16], earlier_stop_driver: 44, later_stop_driver: 16, stop_laps: { 44: 10, 16: 12 }, positions_before: { 44: 3, 16: 2 }, positions_after: { 44: 2, 16: 3 }, result: 'undercut_succeeded', successful_driver: 44, confidence: .8, supporting_signals: ['stint_transition', 'lap_position_before', 'lap_position_after'] }] : [];
  const map = { entry_id: entry.entry_id, source: scene === 'replay' ? 'replay' : 'live', status: active ? 'active' : 'no_session', generated_at: new Date(now).toISOString(), stream_timestamp: new Date(now).toISOString(), stale: false, stale_after_seconds: 10,
    session: { session_key: 'demo-map', meeting_name: 'Demo Grand Prix', session_name: name },
    track: active ? { rotation: 0, points: [[0, 0], [90, 0], [100, 10], [100, 60], [80, 75], [60, 75], [50, 55], [30, 55], [20, 80], [0, 80], [-10, 65], [0, 0]] } : null,
    drivers: active ? people.map((person, index) => ({ ...person, team_name: person.team, timestamp: new Date(now).toISOString(), x: [70, 40, 100, 60, 0][index], y: [0, 0, 40, 75, 60][index], status: 'OnTrack', stale: index === 4 })) : [],
  };
  const history = query => {
    const year = query.year, round = query.round ?? 1;
    const meetings = [1, 2].map(round => ({ round, meeting_key: `jolpica:${year}:${round}`, name: `Demo Archive Grand Prix ${round}`, sessions: [
      { session_key: `demo:${year}:${round}:practice`, name: 'Practice 1', kind: 'practice', start: `${year}-0${round}-12T10:00:00Z` },
      { session_key: `demo:${year}:${round}:qualifying`, name: 'Qualifying', kind: 'qualifying', start: `${year}-0${round}-13T13:00:00Z` },
      { session_key: `demo:${year}:${round}:race`, name: 'Race', kind: 'race', start: `${year}-0${round}-14T13:00:00Z` },
    ] }));
    const results = people.map((person, index) => ({ driver_id: `demo-driver-${person.racing_number}`, driver_number: person.racing_number, driver_name: person.full_name, driver_acronym: person.tla, constructor_id: `demo-${person.team}`, constructor_name: person.team, position: index + 1, grid: index === 4 ? 0 : index + 2, points: [25, 18, 15, 12, 0][index], duration: index ? `+${index * 3}.200` : '1:25:32.123', status: 'classified', status_detail: 'Finished', q1: '1:22.123', q2: index === 4 ? null : '1:21.123', q3: index > 2 ? null : '1:20.123', laps: 12 }));
    const laps = results.flatMap((person, index) => Array.from({ length: 12 }, (_, lap) => ({ provider: 'jolpica', driver_id: person.driver_id, lap_number: lap + 1, lap_duration: lap === 5 && index === 0 ? null : 82 + index * .5 + (lap % 3) * .13, position: lap < 3 ? results.length - index : index + 1 })));
    const payload = query.type.endsWith('/catalog') ? { year, meetings } : query.type.endsWith('/results') ? { results, coverage: { results: 'available' }, attribution: 'DEMO · Jolpica-shaped example data' } : { year, round, session_type: query.session_type, laps, coverage: { lap_times: 'available', positions: 'available', lap_quality: 'timing_only' }, attribution: 'DEMO · Jolpica-shaped example data' };
    return { status: 'ready', data: { payload }, received_at: new Date(now).toISOString() };
  };
  const telemetry = query => {
    const payload = query.type.endsWith('telemetry_catalog') ? { protocol_version: 1, session_id: 'demo-replay', drivers: people.map(person => ({ driver_number: Number(person.racing_number), name: person.full_name, tla: person.tla, team: person.team, laps: [2, 3, 4] })) }
      : { protocol_version: 1, session_id: 'demo-replay', series: (query.selections ?? []).map((selection, index) => ({ ...selection, samples: Array.from({ length: 101 }, (_, sample) => ({ time_s: sample * .8, distance: sample * 48, speed: sample > 40 && sample < 45 && index === 1 ? null : 230 + Math.sin(sample / 7 + index) * 80, throttle: sample % 20 < 5 ? 0 : 100, brake: sample % 20 < 3 ? 100 : 0, gear: sample % 20 < 5 ? 4 : 8, drs: sample % 20 < 5 ? 0 : 12, rpm: 10800 + Math.sin(sample / 7) * 1500, delta_s: index ? sample * .009 : 0 })) })) };
    return { status: 'ready', data: { payload }, received_at: new Date(now).toISOString() };
  };
  return { hass: { states, locale: { language, time_format: '24', time_zone: 'Europe/Stockholm' }, language, config: { time_zone: 'Europe/Stockholm' }, themes: { darkMode: true } }, preview: { entries: [entry], events, now, analysis, map, history, telemetry } };
}
