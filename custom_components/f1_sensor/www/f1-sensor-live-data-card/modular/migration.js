const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ copyConfig, normalizeConfig, ConfigurationError }, { MODULES }] = await Promise.all([load('./config.js'), load('./catalog.js')]);

// These are conversion starting points, not a claim of feature or visual parity.
// Every explicit source property is accounted for, including unsupported extensions.
const module = (type, options = {}, fields) => ({ type, options, ...(fields ? { fields } : {}) });
export const LEGACY_MIGRATIONS = {
  'f1-weekend-hub-card': [module('overview'), module('timeline'), module('strategy'), module('battles'), module('telemetry')],
  'f1-sensor-live-data-card': [module('tyres', { content: 'statistics' })],
  'f1-pitstop-overview-card': [module('pit_stops'), module('tyres')],
  'f1-driver-lap-times-card': [module('timing', { show_gap_toggle: true }, ['position', 'driver', 'status', 'interval', 'last_lap', 'best_lap', 'lap_delta'])],
  'f1-championship-prediction-drivers-card': [module('standings', { competitors: 'drivers' }, ['result_position', 'driver', 'points', 'predicted_position', 'predicted_points', 'points_change'])],
  'f1-championship-prediction-teams-card': [module('standings', { competitors: 'teams' }, ['result_position', 'team', 'points', 'predicted_position', 'predicted_points', 'points_change'])],
  'f1-season-progression-card': [module('progression')],
  'f1-last-race-results-card': [module('results'), module('archive')],
  'f1-lap-position-progression-card': [module('archive', { content: 'lap_position' })],
  'f1-replay-control-card': [module('replay')],
  'f1-track-map-card': [module('map')],
  'f1-investigations-card': [module('incidents', { content: 'investigations', presentation: 'table' })],
  'f1-track-limits-card': [module('incidents', { content: 'track_limits_summary', presentation: 'table' })],
  'f1-next-race-card': [module('overview', {}, ['meeting', 'circuit', 'countdown', 'circuit_map', 'circuit_history']), module('calendar', { show_track_time: true }), module('weather', { content: 'automatic_conditions' }), module('weather', { content: 'race_forecast' })],
  'f1-weather-card': [module('weather', { content: 'automatic_conditions' }), module('weather', { content: 'race_forecast' })],
  'f1-season-calendar-card': [module('calendar', { range: 'season', sessions: ['race'], details: ['round'], past: 'dim', next: 'label' })],
  'f1-live-session-card': [module('overview', {}, ['session', 'session_status', 'track_status']), module('weather', { content: 'track_conditions' })],
  'f1-race-control-card': [module('race_control', { presentation: 'latest_message' })],
  'f1-fia-documents-card': [module('documents', { limit: 8 })],
  'f1-qualifying-timing-card': [module('timing', {}, ['position', 'driver', 'q1_time', 'q2_time', 'q3_time', 'qualifying_gap', 'sector_1', 'sector_2', 'sector_3', 'tyre'])],
  'f1-practice-timing-card': [module('timing', {}, ['position', 'driver', 'status', 'last_lap', 'best_lap', 'tyre', 'tyre_age'])],
  'f1-race-lap-card': [module('timing', { show_gap_toggle: true }, ['position', 'driver', 'status', 'interval', 'last_lap', 'best_lap', 'tyre', 'tyre_age']), module('pit_stops')],
  'f1-starting-grid-card': [module('results', { content: 'starting_grid', presentation: 'grid', show_source: true })],
  'f1-session-archive-card': [module('archive')],
};
const typeName = value => typeof value === 'string' ? value.replace(/^custom:/, '') : '';
export const isLegacyConfig = value => Object.hasOwn(LEGACY_MIGRATIONS, typeName(value?.type));
const report = (path, status, en, sv, target = '') => ({ path, status, message: { en, sv }, target });
const own = (object, key) => Object.hasOwn(object, key);
const unset = value => value === '' || value === 'auto' || value == null;
const color = value => {
  if (typeof value !== 'string') return null;
  const text = value.trim();
  if (/^#[0-9a-f]{6}$/i.test(text)) return text;
  if (/^#[0-9a-f]{3}$/i.test(text)) return `#${[...text.slice(1)].map(c => c + c).join('')}`;
  const rgb = text.match(/^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$/i);
  return rgb && rgb.slice(1).every(n => Number(n) <= 255) ? `#${rgb.slice(1).map(n => Number(n).toString(16).padStart(2, '0')).join('')}` : null;
};
const flagFields = {
  show_position: ['position', 'result_position'], show_status: ['status', 'result_status'],
  show_last_lap: ['last_lap'], show_best_lap: ['best_lap'], show_fastest_lap: ['best_lap'],
  show_sectors: ['sector_1', 'sector_2', 'sector_3'], show_tyre: ['tyre'], show_tyre_age: ['tyre_age'], show_tyre_laps: ['tyre_age'],
  show_lap_trend: ['lap_delta'], show_current_points: ['points'], show_predicted_points: ['predicted_points'],
  show_grid: ['grid_position'], show_laps: ['laps'], show_points: ['points'], show_time_gap: ['result_time'],
  show_qualifying_position: ['qualifying_position'], show_qualifying_time: ['qualifying_time'],
  show_grid_delta: ['grid_delta'], show_qualifying_segment: ['qualifying_segment'], show_qualifying_delta: ['qualifying_delta'],
  show_pit_count: ['pit_count'], show_pit_time: ['stop_time'], show_pit_lane_time: ['lane_time'], show_pit_delta: ['pit_delta'],
  show_document_number: ['document_number'], show_published: ['document_time'],
  show_countdown: ['countdown'], show_track_status: ['track_status'],
  show_time_elapsed: ['session_time_elapsed'], show_time_remaining: ['session_time_remaining'], show_progress: ['replay_progress'],
  show_best_times: ['best_runs'], show_stats: ['compound_laps', 'new_sets', 'total_stints'],
  show_tla: ['driver'], show_team_name: ['team'],
};
export const LEGACY_ENTITY_BINDINGS = {
  'f1-live-session-card': {
    formation_start_entity: 'formation_start', overtake_mode_entity: 'overtake_mode', straight_mode_entity: 'straight_mode',
  },
  'f1-replay-control-card': {
    status_entity: 'replay_status', year_entity: 'replay_year_select', session_entity: 'replay_session_select',
    start_reference_entity: 'replay_start_reference', load_button_entity: 'replay_load', play_button_entity: 'replay_play',
    pause_button_entity: 'replay_pause', back_button_entity: 'replay_back_30', forward_button_entity: 'replay_forward_30',
    stop_button_entity: 'replay_stop', refresh_button_entity: 'replay_refresh', player_entity: 'replay_player',
  },
};
const boundSourceKeys = Object.values(LEGACY_ENTITY_BINDINGS).flatMap(bindings => Object.keys(bindings));
const sourceKeys = new Set(['entity', 'current_entity', 'drivers_entity', 'positions_entity', 'driver_positions_entity', 'driver_list_entity', 'tyres_entity', 'pitstops_entity', 'auth_status_entity', 'calendar_entity', 'current_season_entity', 'season_results_entity', 'sprint_results_entity', 'session_entity', 'current_session_entity', 'session_status_entity', 'track_status_entity', 'weather_entity', 'track_weather_entity', 'next_race_entity', 'last_race_entity', 'lap_count_entity', 'session_time_remaining_entity', 'session_time_elapsed_entity', 'investigations_entity', 'track_limits_entity', ...boundSourceKeys]);

export function proposeMigration(input, { entries = [], entryId = '' } = {}) {
  const original = copyConfig(input);
  if (!isLegacyConfig(original)) throw new ConfigurationError('type', 'expected a supported legacy F1 Sensor card');
  const type = typeName(original.type), rows = [];
  const config = normalizeConfig({ title: typeof original.title === 'string' ? original.title : 'F1 Sensor', layout: ['f1-weekend-hub-card', 'f1-last-race-results-card'].includes(type) ? 'tabs' : 'stack', appearance: { mode: ['f1-season-progression-card', 'f1-lap-position-progression-card'].includes(type) ? 'auto' : 'dark', logo_style: 'color', logos: !['f1-sensor-live-data-card', 'f1-pitstop-overview-card', 'f1-investigations-card', 'f1-track-limits-card'].includes(type) }, modules: copyConfig(LEGACY_MIGRATIONS[type]) });
  const find = kind => config.modules.find(m => m.type === kind);
  const add = (path, status, en, sv, target) => rows.push(report(path, status, en, sv, target));
  const kept = (key, target) => add(key, 'mapped', 'Carried into the new configuration.', 'Överfört till den nya konfigurationen.', target);
  const review = key => add(key, 'review', 'No equivalent setting is applied. Keep using the original card if this option is required.', 'Ingen motsvarande inställning tillämpas. Behåll originalkortet om detta val behövs.');
  const fields = (key, list) => {
    let count = 0;
    for (const m of config.modules) {
      const valid = list.filter(f => MODULES[m.type].fields.includes(f)); if (!valid.length) continue;
      m.fields = original[key] ? [...new Set([...m.fields, ...valid])] : m.fields.filter(f => !valid.includes(f)); count++;
    }
    if (count) kept(key, 'modules[].fields'); else review(key);
  };
  const option = (key, kind, name, value = original[key]) => {
    const m = find(kind), spec = MODULES[kind]?.options[name];
    const valid = spec?.type === 'enum' ? spec.values.includes(value) : spec?.type === 'integer' ? Number.isInteger(value) && value >= spec.min && value <= spec.max : spec?.type === 'boolean' ? typeof value === 'boolean' : spec?.type === 'list' ? Array.isArray(value) && value.every(v => spec.values.includes(v)) : typeof value === 'string';
    if (!m || !valid) { review(key); return; }
    m.options[name] = value; kept(key, `modules.${m.id}.options.${name}`);
  };
  const explicitEntries = ['f1_entry_id', 'entry_id', 'history_entry_id'].map(k => original[k]).filter(v => typeof v === 'string' && !unset(v));
  const sourceIds = Object.entries(original).filter(([k, v]) => sourceKeys.has(k) && typeof v === 'string' && !unset(v)).map(([, v]) => v);
  const matching = entries.filter(e => sourceIds.some(id => Object.values(e.entities ?? {}).includes(id)));
  const inferred = matching.length === 1 ? matching[0].entry_id : '';
  config.f1_entry_id = entryId || explicitEntries[0] || inferred || (entries.length === 1 ? entries[0].entry_id : '');
  const selectedEntry = entries.find(e => e.entry_id === config.f1_entry_id);
  const sourceBindings = LEGACY_ENTITY_BINDINGS[type] ?? {};
  const sourceMatch = (key, id) => selectedEntry && (key === 'auth_status_entity'
    ? id === 'sensor.f1_f1tv_token_status' || selectedEntry.entities?.f1tv_token_status === id
    : sourceBindings[key]
    ? selectedEntry.entities?.[sourceBindings[key]] === id
    : Object.values(selectedEntry.entities ?? {}).includes(id));
  if (!config.f1_entry_id) add('$installation', 'review', 'Choose an F1 Sensor installation before using the converted card.', 'Välj en F1 Sensor-installation innan det konverterade kortet används.');
  if (type === 'f1-weekend-hub-card' && !own(original, 'no_spoiler_entity')) {
    config.context.spoilers = 'hide';
    add('$spoilers', 'changed', 'The old default spoiler helper is not used by the new card. The converted card starts with spoilers hidden; choose its protection in the editor.', 'Det gamla förvalda spoilerhjälpobjektet används inte av det nya kortet. Det konverterade kortet börjar med dolt innehåll; välj skydd i editorn.');
  }
  if (type === 'f1-last-race-results-card' && original.show_archive === false) config.modules = config.modules.filter(m => m.type !== 'archive');
  if (['f1-last-race-results-card', 'f1-session-archive-card'].includes(type) && original.default_scope === 'archive') config.modules.sort((a, b) => (a.type !== 'archive') - (b.type !== 'archive'));
  for (const [key, value] of Object.entries(original)) {
    if (key === 'type') { add(key, 'changed', 'Uses F1 Sensor modules with a new layout and defaults. This is a starting point for review, not an exact copy of every legacy feature.', 'Använder F1 Sensor-moduler med ny layout och nya standardval. Detta är ett underlag för granskning, inte en exakt kopia av alla äldre funktioner.', 'type'); continue; }
    if (['title', 'grid_options', 'visibility', 'layout_options'].includes(key)) { config[key] = copyConfig(value); kept(key, key); continue; }
    if (['tap_action', 'hold_action', 'double_tap_action'].includes(key)) {
      config[key] = copyConfig(value);
      add(key, 'changed', 'Actions move to the card title and the Card actions buttons. Module controls keep their own actions; test the gestures after conversion.', 'Åtgärder flyttas till kortrubriken och knappar under Kortåtgärder. Modulkontrollerna har egna åtgärder; prova gesterna efter konverteringen.', key); continue;
    }
    if (['f1_entry_id', 'entry_id', 'history_entry_id'].includes(key)) {
      if (unset(value) || value === config.f1_entry_id) kept(key, 'f1_entry_id'); else review(key); continue;
    }
    if (key === 'auth_status_entity' && !['f1-pitstop-overview-card', 'f1-race-lap-card', 'f1-championship-prediction-drivers-card', 'f1-championship-prediction-teams-card'].includes(type)) {
      review(key); continue;
    }
    if (sourceKeys.has(key)) {
      if (unset(value) || sourceMatch(key, value)) add(key, 'changed', 'The installation is retained; each module chooses its matching F1 Sensor entities automatically. Per-field source overrides are not copied.', 'Installationen behålls; varje modul väljer sina F1 Sensor-entiteter automatiskt. Egna källval per fält kopieras inte.', 'f1_entry_id');
      else review(key);
      if (key === 'entity' && typeof value === 'string') config.entity = value; // HA background action target only.
      continue;
    }
    if (key === 'no_spoiler_entity') {
      if (!unset(value) && value !== selectedEntry?.global_entities?.no_spoiler_mode) {
        config.context.spoilers = 'hide';
        add(key, 'changed', 'Custom spoiler helper is retained in the backup. Content starts hidden; the new card also respects integration spoiler protection.', 'Eget spoilerhjälpobjekt finns i säkerhetskopian. Innehållet börjar dolt; det nya kortet respekterar också integrationens spoilerskydd.', 'context.spoilers');
      } else kept(key, 'context.spoilers');
      continue;
    }
    if (type === 'f1-season-calendar-card' && ['show_round', 'show_circuit_name', 'show_location'].includes(key) && typeof value === 'boolean') {
      const detail = { show_round: 'round', show_circuit_name: 'circuit', show_location: 'location' }[key];
      const m = find('calendar');
      m.options.details = m.options.details.filter(item => item !== detail);
      if (value) m.options.details.push(detail);
      kept(key, 'modules[].options.details'); continue;
    }
    if (type === 'f1-season-calendar-card' && ['dim_past_races', 'hide_past_races', 'highlight_next_race'].includes(key) && typeof value === 'boolean') {
      const m = find('calendar'), hide = original.hide_past_races === true, dim = original.dim_past_races !== false;
      m.options.past = hide ? 'hide' : dim ? 'dim' : 'show';
      m.options.next = original.highlight_next_race !== false && dim && !hide ? 'label' : 'none';
      add(key, 'changed', 'Past race starts are hidden or labelled as configured. The next race uses a text marker; past rows retain readable contrast.', 'Passerade racestarter döljs eller märks enligt dina val. Nästa race får en textmarkering; tidigare rader behåller läsbar kontrast.', 'modules[].options.past; modules[].options.next'); continue;
    }
    if (type === 'f1-weekend-hub-card' && key === 'default_view') {
      const views = ['overview', 'timeline', 'strategy', 'telemetry', 'battles'];
      const view = views.includes(value) ? value : 'overview';
      config.modules.sort((a, b) => Number(a.type !== view) - Number(b.type !== view));
      if (views.includes(value)) kept(key, 'modules');
      else add(key, 'changed', 'An unsupported old value opens Overview, matching the old card fallback. The exact input remains in the migration backup.', 'Ett ogiltigt äldre värde öppnar Översikt, vilket motsvarar det gamla kortets reservval. Den exakta inmatningen finns kvar i migrationskopian.', 'modules');
      continue;
    }
    if (type === 'f1-weekend-hub-card' && key === 'throttle_ms') {
      const effective = Math.min(5000, Math.max(100, Number(value) || 500));
      if (effective === 500) add(key, 'changed', 'The effective 500 ms update interval is retained by the new shared analysis subscription. It is no longer adjusted per card.', 'Det effektiva uppdateringsintervallet 500 ms behålls av den nya delade analysprenumerationen. Det kan inte längre ändras per kort.', '$analysis.throttle_ms');
      else review(key);
      continue;
    }
    if (key === 'theme_mode') { if (['auto', 'dark', 'light'].includes(value)) { config.appearance.mode = value; kept(key, 'appearance.mode'); } else review(key); continue; }
    if (key === 'font_style') {
      if (!['system', 'wide', 'balanced'].includes(value)) { review(key); continue; }
      config.appearance.font = value === 'system' ? 'system' : 'f1';
      add(key, 'changed', value === 'system' ? 'Uses Home Assistant heading typography without changing the card style or colors.' : 'Wide and Balanced become the new F1 heading font. Table text uses readable Home Assistant typography.', value === 'system' ? 'Använder Home Assistants rubriktypsnitt utan att ändra kortets stil eller färger.' : 'Wide och Balanced blir det nya F1-rubriktypsnittet. Tabelltext använder läsbar Home Assistant-typografi.', 'appearance.font'); continue;
    }
    if (['show_header', 'show_title'].includes(key) && typeof value === 'boolean') {
      // Evaluate both legacy flags together so object property order cannot win.
      const visible = original.show_header !== false && original.show_title !== false;
      config.appearance.show_header = visible;
      for (const item of config.modules) item.show_header = visible;
      add(key, 'changed', 'Title visibility is applied to the card and its modules. Session details, status labels and controls remain available.', 'Rubrikvisningen överförs till kortet och dess moduler. Sessionsuppgifter, statusmarkeringar och kontroller finns kvar.', 'appearance.show_header; modules[].show_header'); continue;
    }
    if (key === 'show_table_header' && typeof value === 'boolean') {
      for (const item of config.modules) item.show_table_header = value;
      add(key, 'changed', 'Table header visibility is retained. Hidden labels remain available to screen readers; chart data tables keep their series labels visible.', 'Tabellhuvudets synlighet behålls. Dolda namn finns kvar för skärmläsare; diagrammens datatabeller visar namnen på serierna.', 'modules[].show_table_header'); continue;
    }
    const paletteKey = { color_overall_fastest: 'overall', color_personal_fastest: 'personal', color_timed: 'timed' }[key];
    if (paletteKey) { const converted = color(value); if (converted) { config.appearance.palette[paletteKey] = converted; kept(key, `appearance.palette.${paletteKey}`); } else if (unset(value)) kept(key, 'appearance.palette'); else review(key); continue; }
    if (key === 'show_timing_indicators') { add(key, 'changed', 'Timing signals always include symbols or text. Fastest = diamond, personal best = circle, recorded = square. Lap arrows retain down for faster and up for slower.', 'Timing visas alltid med symboler eller text. Snabbast = diamant, personbästa = cirkel, registrerad = kvadrat. Varvpilar behåller nedåt för snabbare och uppåt för långsammare.', 'accessibility.signals'); continue; }
    const appearanceKey = { show_team_logo: 'logos', show_country_flag: 'flags', show_full_name: 'full_names' }[key];
    if (appearanceKey && typeof value === 'boolean') { config.appearance[appearanceKey] = value; kept(key, `appearance.${appearanceKey}`); continue; }
    if (key === 'show_flag' && typeof value === 'boolean' && type === 'f1-live-session-card') { config.appearance.flags = value; kept(key, 'appearance.flags'); continue; }
    if (key === 'team_logo_style') { if (['auto', 'color', 'white'].includes(value)) { config.appearance.logo_style = value; kept(key, 'appearance.logo_style'); } else review(key); continue; }
    if (key === 'show_tyre_image' && typeof value === 'boolean') { config.appearance.tyre_style = value ? original.show_compound_name === false ? 'image' : 'both' : 'text'; kept(key, 'appearance.tyre_style'); continue; }
    const progressionOption = { show_legend: 'show_legend', legend_position: 'legend_position', show_legend_points: 'show_legend_points', show_points: 'show_points', show_round_labels: 'show_round_labels', show_future_rounds: 'show_future_rounds', chart_height: 'chart_height' }[key];
    if (progressionOption && find('progression')) { option(key, 'progression', progressionOption); continue; }
    const lapPositionOption = { show_points: 'show_points', show_round_labels: 'show_round_labels', chart_height: 'chart_height' }[key];
    if (lapPositionOption && type === 'f1-lap-position-progression-card') { option(key, 'archive', lapPositionOption); continue; }
    if (key === 'show_session_selector' && typeof value === 'boolean') {
      const targets = config.modules.filter(item => ['results', 'archive'].includes(item.type));
      for (const item of targets) item.options[item.type === 'results' ? 'show_selector' : 'show_session_selector'] = value;
      if (targets.length) kept(key, targets.map(item => `modules.${item.id}.options.${item.type === 'results' ? 'show_selector' : 'show_session_selector'}`).join('; '));
      else review(key);
      continue;
    }
    if (key === 'show_session_type_badge' && typeof value === 'boolean') {
      const targets = config.modules.filter(item => ['results', 'archive'].includes(item.type));
      for (const item of targets) item.options.show_session_type_badge = value;
      if (targets.length) kept(key, targets.map(item => `modules.${item.id}.options.show_session_type_badge`).join('; '));
      else review(key);
      continue;
    }
    if (key === 'spoiler_placeholder' && typeof value === 'string') {
      const targets = config.modules.filter(item => ['results', 'standings', 'archive'].includes(item.type));
      for (const item of targets) item.options.spoiler_placeholder = value;
      if (targets.length) kept(key, targets.map(item => `modules.${item.id}.options.spoiler_placeholder`).join('; '));
      else review(key);
      continue;
    }
    if (key === 'driver_image_type' && ['team_logo', 'headshot'].includes(value)) {
      const targets = config.modules.filter(item => ['results', 'standings'].includes(item.type));
      for (const item of targets) item.options.driver_image_type = value;
      if (targets.length) kept(key, targets.map(item => `modules.${item.id}.options.driver_image_type`).join('; '));
      else if (find('archive')) add(key, 'changed', 'Historical results keep stable archived driver identities and team names. Current driver headshots are not joined to past seasons because racing numbers and identities can change.', 'Historiska resultat behåller stabila arkiverade föraridentiteter och teamnamn. Nutida förarbilder kopplas inte till äldre säsonger eftersom startnummer och identiteter kan ändras.', 'modules[].fields');
      else review(key);
      continue;
    }
    if (key === 'show_all_drivers' && typeof value === 'boolean' && find('incidents')) {
      add(key, 'changed', 'The new incident views list only drivers backed by recorded events or track-limit data. Missing drivers are not shown as zero because the source does not prove that they had no incidents.', 'De nya incidentvyerna visar bara förare med registrerade händelser eller track limits-uppgifter. Saknade förare visas inte med noll eftersom källan inte bevisar att de saknade incidenter.', 'modules[].options');
      continue;
    }
    if (key === 'show_context' && typeof value === 'boolean' && type === 'f1-weekend-hub-card') {
      add(key, 'changed', 'Driver focus and viewing controls remain available at card level. The old synchronized context bar is not copied as a separate row.', 'Förarfokus och visningskontroller finns kvar på kortnivå. Den äldre synkroniserade sammanhangsraden kopieras inte som en separat rad.', 'context');
      continue;
    }
    if (type === 'f1-next-race-card' && key === 'show_map' && typeof value === 'boolean') { fields(key, ['circuit_map']); continue; }
    if (type === 'f1-next-race-card' && key === 'show_history' && typeof value === 'boolean') { fields(key, ['circuit_history']); continue; }
    if (type === 'f1-next-race-card' && key === 'show_track_time' && typeof value === 'boolean') { option(key, 'calendar', 'show_track_time'); continue; }
    if (key === 'show_gap_toggle' && typeof value === 'boolean' && find('timing')) {
      if (type === 'f1-practice-timing-card') {
        add(key, 'changed', 'The old practice card exposed this setting in its editor but did not render a gap control. The converted practice view keeps that visible behavior.', 'Det äldre träningskortet visade inställningen i editorn men renderade inget avståndsval. Den konverterade träningsvyn behåller det synliga beteendet.', 'modules[].options.show_gap_toggle');
      } else option(key, 'timing', 'show_gap_toggle');
      continue;
    }
    if (type === 'f1-track-map-card' && ['show_footer', 'show_session_info', 'show_lap_progress', 'show_track_status'].includes(key) && typeof value === 'boolean') { option(key, 'map', key); continue; }
    if (type === 'f1-track-map-card' && key === 'layout_mode' && ['auto', 'compact', 'full'].includes(value)) { option(key, 'map', key); continue; }
    if (type === 'f1-track-map-card' && key === 'track_status_line_mode' && ['accent', 'full', 'off'].includes(value)) { option(key, 'map', key); continue; }
    if (own(flagFields, key) && typeof value === 'boolean') { fields(key, flagFields[key]); continue; }
    if (key === 'show_delta' && typeof value === 'boolean' && find('tyres')) { fields(key, ['compound_gap']); continue; }
    if (key === 'show_delta' && typeof value === 'boolean' && type === 'f1-qualifying-timing-card') { fields(key, ['qualifying_gap']); continue; }
    if (key === 'show_delta' && typeof value === 'boolean' && find('standings')) { fields(key, ['points_change']); continue; }
    if (key === 'show_lap_progress' && typeof value === 'boolean' && type === 'f1-live-session-card') { fields(key, ['lap_progress']); continue; }
    if (key === 'show_delta' && typeof value === 'boolean' && find('results')) { fields(key, ['position_change']); continue; }
    if (key === 'show_delta' && typeof value === 'boolean' && find('archive')) { fields(key, ['position_change']); continue; }
    if (key === 'gap_mode' && find('timing') && ['ahead', 'leader', 'off'].includes(value)) {
      const m = find('timing'); m.fields = m.fields.filter(f => !['gap', 'interval'].includes(f));
      if (value !== 'off' && original.show_gap !== false) m.fields.push(value === 'ahead' ? 'interval' : 'gap'); kept(key, 'modules[].fields'); continue;
    }
    if (key === 'show_gap' && find('timing') && typeof value === 'boolean') {
      const m = find('timing'); m.fields = m.fields.filter(f => !['gap', 'interval'].includes(f));
      if (value && original.gap_mode !== 'off') m.fields.push(original.gap_mode === 'leader' ? 'gap' : 'interval');
      kept(key, 'modules[].fields'); continue;
    }
    if (key === 'sector_display_mode') {
      if (value === 'current') option(key, 'timing', 'sectors', 'coherent');
      else if (value === 'personal_best' && find('timing')) {
        const m = find('timing'); m.fields = m.fields.map(f => /^sector_[123]$/.test(f) ? `best_${f}` : f);
        kept(key, 'modules[].fields');
      } else review(key);
      continue;
    }
    if (['lap_history_limit', 'show_lap_history'].includes(key) && find('timing')) {
      const limit = original.lap_history_limit ?? 0;
      if (original.show_lap_history !== true) option(key, 'timing', 'history', 0);
      else if (limit === 0) {
        find('timing').options.history = 30;
        add(key, 'changed', 'All-lap history becomes the last 30 laps. Choose a smaller history or keep the old card if all columns are required.', 'Historik för alla varv blir de senaste 30 varven. Välj kortare historik eller behåll det gamla kortet om alla kolumner behövs.', 'modules[].options.history');
      } else option(key, 'timing', 'history', limit);
      continue;
    }
    if (key === 'compounds') { option(key, 'tyres', 'compounds', Array.isArray(value) ? value.map(v => String(v).toUpperCase()) : value); continue; }
    if (key === 'show_compound_name' && typeof value === 'boolean' && find('tyres')) { option(key, 'tyres', 'show_compound_name'); continue; }
    if (key === 'show_availability_notice' && typeof value === 'boolean' && find('pit_stops')) { option(key, 'pit_stops', 'show_availability_notice'); continue; }
    if (key === 'show_availability_notice' && typeof value === 'boolean' && find('standings')) { option(key, 'standings', 'show_availability_notice'); continue; }
    if (key === 'show_mode_badge' && typeof value === 'boolean' && find('standings')) { option(key, 'standings', 'show_mode_badge'); continue; }
    if (key === 'max_best_times' && find('tyres')) {
      if (Number.isInteger(value) && value >= 0 && value <= MODULES.tyres.options.best_times_limit.max) option(key, 'tyres', 'best_times_limit', value || 3);
      else review(key);
      continue;
    }
    if (key === 'mode' && find('progression')) { option(key, 'progression', 'competitors', value === 'constructors' ? 'teams' : value); continue; }
    if (key === 'layout_mode' && type === 'f1-live-session-card') { option(key, 'overview', 'layout_mode'); continue; }
    if (['history_year', 'year'].includes(key)) { option(key, 'archive', 'year', original.history_year ?? value); continue; }
    if (key === 'top_limit') {
      const m = config.modules.find(m => MODULES[m.type].options.rows || MODULES[m.type].options.series_limit);
      if (m) { const name = MODULES[m.type].options.rows ? 'rows' : 'series_limit'; option(key, m.type, name, value === 0 ? MODULES[m.type].options[name].max : value); }
      else review(key); continue;
    }
    if (key === 'sort_order') { option(key, 'documents', 'order', value === 'asc' ? 'oldest' : value === 'desc' ? 'newest' : value); continue; }
    if (key === 'visible_rows') { option(key, 'documents', 'limit'); continue; }
    if (['driver_label_mode', 'show_labels'].includes(key) && find('map')) {
      const labels = original.driver_label_mode == null && original.show_labels === false ? 'off'
        : original.driver_label_mode === 'number' ? 'number' : original.driver_label_mode === 'off' ? 'off' : 'code';
      option(key, 'map', 'labels', labels); continue;
    }
    if (key === 'show_driver_count' && find('map')) { option(key, 'map', 'show_driver_count'); continue; }
    if (type === 'f1-track-map-card' && key === 'throttle_ms') {
      add(key, 'changed', 'The map now shares one 500 ms position stream across cards instead of creating a separate update interval for each card.', 'Kartan delar nu en positionsström på 500 ms mellan kort i stället för att skapa ett separat uppdateringsintervall per kort.', '$map.throttle_ms'); continue;
    }
    if (type === 'f1-track-map-card' && key === 'interpolation_ms') {
      add(key, 'changed', 'The map now renders authoritative pushed positions without a configurable per-card interpolation delay.', 'Kartan visar nu auktoritativa pushade positioner utan en konfigurerbar interpoleringsfördröjning per kort.', '$map.interpolation_ms'); continue;
    }
    if (key === 'invert_y' && typeof value === 'boolean') { option(key, 'map', 'vertical', value ? 'flipped' : 'normal'); continue; }
    if (key === 'display_mode' && find('race_control')) { option(key, 'race_control', 'presentation', value === 'list' ? 'list' : ['latest', 'banner'].includes(value) ? 'latest_message' : value); continue; }
    if (key === 'display_mode' && find('documents')) { option(key, 'documents', 'presentation', value); continue; }
    if (key === 'display_mode' && type === 'f1-starting-grid-card') { option(key, 'results', 'presentation'); continue; }
    if (key === 'display_mode' && find('replay')) { option(key, 'replay', 'display'); continue; }
    if (key === 'list_max_height' && find('race_control')) {
      const normalized = Number.isInteger(value) ? value <= 0 ? 600 : Math.min(2000, Math.max(240, value)) : value;
      option(key, 'race_control', 'list_max_height', normalized); continue;
    }
    if (key === 'list_max_height' && find('documents')) {
      if (value === 0 || Number.isInteger(value) && value >= 180 && value <= 2000) option(key, 'documents', 'list_max_height'); else review(key);
      continue;
    }
    const documentOption = { open_in_new_tab: 'open_new_tab', show_document_coloring: 'document_coloring', show_document_type: 'show_document_type', show_fia_logo: 'show_fia_logo', show_pdf_icon: 'show_pdf_icon', show_count: 'show_count', show_race_context: 'show_race_context', show_latest_badge: 'show_latest_badge' }[key];
    if (documentOption && find('documents')) { option(key, 'documents', documentOption); continue; }
    const raceControlOption = { hide_blue_flags: 'hide_blue_flags', hide_track_limits: 'hide_track_limits', show_fia_logo: 'show_fia_logo', min_display_time: 'min_display_time', show_clear_button: 'show_clear_button' }[key];
    if (raceControlOption && find('race_control')) { option(key, 'race_control', raceControlOption); continue; }
    if (type === 'f1-starting-grid-card' && key === 'show_metadata') { option(key, 'results', 'show_context'); continue; }
    if (type === 'f1-starting-grid-card' && key === 'show_source_badge') { option(key, 'results', 'show_source'); continue; }
    if (type === 'f1-starting-grid-card' && key === 'show_status_badge') { option(key, 'results', 'show_status'); continue; }
    const replayOption = { show_secondary_selects: 'secondary_selects', show_start_reference: 'start_reference', show_seek_controls: 'seek_controls', show_refresh: 'refresh', show_status_details: 'status_details', show_button_labels: 'show_button_labels' }[key];
    if (replayOption && find('replay')) { option(key, 'replay', replayOption); continue; }
    if (key === 'prefer_live_weather' && ['f1-weather-card', 'f1-next-race-card'].includes(type) && typeof value === 'boolean') {
      option(key, 'weather', 'content', value ? 'automatic_conditions' : 'current_conditions'); continue;
    }
    if (['show_weather', 'show_schedule', 'show_overview', 'show_archive'].includes(key) && typeof value === 'boolean') {
      const kind = { show_weather: 'weather', show_schedule: 'calendar', show_overview: 'overview', show_archive: 'archive' }[key];
      const targets = config.modules.filter(m => m.type === kind);
      if (targets.length) { for (const m of targets) m.enabled = value; kept(key, targets.map(m => `modules.${m.id}.enabled`).join(', ')); } else if (!value) kept(key, 'modules'); else review(key); continue;
    }
    if (key === 'default_scope' && ['archive', 'current'].includes(value) && type === 'f1-last-race-results-card') { kept(key, 'modules'); continue; }
    if (key === 'default_scope' && type === 'f1-session-archive-card') {
      add(key, 'mapped', 'The archive alias continues to open the historical archive. Its legacy compatibility layer always forced archive mode regardless of this saved value.', 'Arkivaliaset fortsätter att öppna det historiska arkivet. Dess äldre kompatibilitetslager tvingade alltid arkivläge oavsett detta sparade värde.', 'modules.0'); continue;
    }
    review(key);
  }
  if (['f1-practice-timing-card', 'f1-qualifying-timing-card', 'f1-race-lap-card'].includes(type)) add('$sessions', 'changed', 'The new timing module follows the available session with your selected columns. The old card’s practice, qualifying or race visibility restriction is not copied.', 'Den nya timingmodulen följer tillgänglig session med dina valda kolumner. Det gamla kortets begränsning till träning, kval eller race kopieras inte.');
  if (find('timing') && !own(original, 'show_timing_indicators')) add('$timing', 'changed', 'Timing states always include symbols or text. Lap arrows keep down for faster and up for slower.', 'Timingstatus får alltid symboler eller text. Varvpilar behåller nedåt för snabbare och uppåt för långsammare.');
  if (type === 'f1-fia-documents-card') add('$documents', 'changed', 'The document limit controls how many records are shown, rather than the height of a scroll area. Document badges and opening behavior use the new module defaults.', 'Dokumentgränsen styr hur många poster som visas, i stället för höjden på en rullyta. Dokumentmärken och öppningsbeteende följer modulens nya standardval.');
  if (['f1-weather-card', 'f1-next-race-card'].includes(type)) add('$weather', 'changed', 'Current weather and race-start forecast become two independently editable modules. Automatic track observations require a confirmed active session; missing or unknown session status uses current weather.', 'Aktuellt väder och prognos inför racestart blir två separat redigerbara moduler. Automatiska banobservationer kräver en bekräftad aktiv session; saknad eller okänd sessionsstatus använder aktuellt väder.');
  if (type === 'f1-next-race-card') add('$coverage', 'changed', 'Circuit illustration and history remain in the overview module, while schedule and weather are independently editable modules.', 'Banillustration och historik finns kvar i översiktsmodulen, medan schema och väder är separat redigerbara moduler.', 'modules');
  if (['f1-last-race-results-card', 'f1-session-archive-card', 'f1-lap-position-progression-card'].includes(type)) add('$session', 'review', 'Choose the archive year, event and session in the new editor. A temporary selection from the old card is not stored in its configuration.', 'Välj arkivets år, tävling och session i den nya editorn. Ett tillfälligt val i det gamla kortet finns inte i dess konfiguration.');
  if (['f1-championship-prediction-drivers-card', 'f1-championship-prediction-teams-card'].includes(type)) add('$projection', 'changed', 'Current and available projected standings use separate labelled columns. Legacy position-change badges are not copied.', 'Aktuell och tillgänglig prognostiserad ställning använder separata namngivna kolumner. Gamla märken för positionsförändring kopieras inte.');
  add('$appearance', 'changed', 'Spacing, headings, fonts and table presentation use the new design. Custom timing colors can be adjusted for contrast by the selected accessibility mode.', 'Mellanrum, rubriker, typsnitt och tabeller använder den nya formen. Egna timingfärger kan kontrastjusteras av valt tillgänglighetsläge.');
  add('$focus', 'changed', 'Temporary driver focus and gap controls are local unless you explicitly join a named group in the new editor.', 'Tillfälligt förarfokus och gapkontroller är lokala tills du uttryckligen väljer en namngiven grupp i den nya editorn.');
  // Bind the report to the exact original. Later edits to the new card never alter it.
  config.migration = { version: 1, original, report: rows };
  return { config: normalizeConfig(config), rows: copyConfig(rows) };
}

export function restoreLegacy(config) {
  if (config?.migration?.version !== 1 || !isLegacyConfig(config.migration.original)) throw new ConfigurationError('migration', 'no supported legacy backup');
  return copyConfig(config.migration.original);
}
