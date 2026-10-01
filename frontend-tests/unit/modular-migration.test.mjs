import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import { LEGACY_MIGRATIONS, isLegacyConfig, proposeMigration, restoreLegacy } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/migration.js';
import { exportConfig, importConfig, configWarnings } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { MODULES } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js';
const entries = [{ entry_id: 'a', title: 'Home', entities: { driver_positions: 'sensor.renamed_timing' }, global_entities: { no_spoiler_mode: 'switch.protection' } }, { entry_id: 'b', title: 'Other', entities: { driver_positions: 'sensor.other_timing' } }];
const legacy = (type, values = {}) => ({ type: `custom:${type}`, ...values });

test('weather migration separates current and race forecast while preserving preferences and visibility', () => {
  for (const type of ['f1-weather-card', 'f1-next-race-card']) {
    for (const preference of [undefined, true, false]) for (const visible of [undefined, true, false]) {
      const settings = { ...(preference === undefined ? {} : { prefer_live_weather: preference }), ...(visible === undefined ? {} : { show_weather: visible }) };
      for (const ordered of [settings, Object.fromEntries(Object.entries(settings).reverse())]) {
        const original = legacy(type, ordered), { config, rows } = proposeMigration(original);
        const weather = config.modules.filter(m => m.type === 'weather');
        assert.equal(weather.length, 2);
        assert.equal(weather[0].options.content, preference === false ? 'current_conditions' : 'automatic_conditions');
        assert.equal(weather[1].options.content, 'race_forecast');
        assert.ok(weather.every(m => m.enabled === (visible !== false)));
        if (visible !== undefined) for (const m of weather) assert.ok(rows.find(r => r.path === 'show_weather').target.includes(m.id));
        if (preference !== undefined) assert.equal(rows.find(r => r.path === 'prefer_live_weather').status, 'mapped');
        assert.ok(rows.some(r => r.path === '$weather' && r.status === 'changed'));
        assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
      }
    }
  }
});

test('legacy graphical choices preserve visibility and separate font from colors and style', () => {
  for (const font_style of ['system', 'wide', 'balanced']) {
    const original = legacy('f1-practice-timing-card', { font_style, theme_mode: 'light', show_header: false, show_table_header: false, color_personal_fastest: '#2255bb' });
    const { config, rows } = proposeMigration(original);
    assert.equal(config.appearance.font, font_style === 'system' ? 'system' : 'f1');
    assert.equal(config.appearance.style, 'f1');
    assert.equal(config.appearance.mode, 'light');
    assert.equal(config.appearance.palette.personal, '#2255bb');
    assert.equal(config.appearance.show_header, false);
    assert.ok(config.modules.every(m => !m.show_header && !m.show_table_header));
    assert.equal(rows.find(r => r.path === 'font_style').target, 'appearance.font');
    assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
  }
  assert.equal(proposeMigration(legacy('f1-race-lap-card', { font_style: 'invented' })).rows.find(r => r.path === 'font_style').status, 'review');
  for (const flags of [{ show_header: true, show_title: false }, { show_title: false, show_header: true }]) {
    assert.equal(proposeMigration(legacy('f1-race-control-card', flags)).config.appearance.show_header, false);
  }
});

test('tyre statistics migration retains compound identity and fastest-stint limits', () => {
  for (const [showImage, showName, style] of [[true, true, 'both'], [true, false, 'image'], [false, true, 'text'], [false, false, 'text']]) {
    const original = legacy('f1-sensor-live-data-card', { show_tyre_image: showImage, show_compound_name: showName, max_best_times: 5 });
    const { config, rows } = proposeMigration(original);
    assert.equal(config.appearance.tyre_style, style);
    assert.equal(config.modules[0].options.show_compound_name, showName);
    assert.equal(config.modules[0].options.best_times_limit, 5);
    for (const key of ['show_tyre_image', 'show_compound_name', 'max_best_times']) assert.equal(rows.find(row => row.path === key).status, 'mapped', key);
    assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
  }
  const zero = proposeMigration(legacy('f1-sensor-live-data-card', { max_best_times: 0 }));
  assert.equal(zero.config.modules[0].options.best_times_limit, 3);
  assert.equal(zero.rows.find(row => row.path === 'max_best_times').status, 'mapped');
  assert.equal(proposeMigration(legacy('f1-sensor-live-data-card', { max_best_times: 'auto' })).rows.find(row => row.path === 'max_best_times').status, 'review');
});

test('all 23 legacy cards and the archive alias have valid editable conversion starting points', () => {
  const inventory = JSON.parse(fs.readFileSync(new URL('../../quality/legacy-card-options.json', import.meta.url)));
  assert.deepEqual(Object.keys(LEGACY_MIGRATIONS).sort(), [...inventory.cards, ...inventory.aliases].map(c => c.type).sort());
  for (const type of Object.keys(LEGACY_MIGRATIONS)) {
    const source = legacy(type), { config, rows } = proposeMigration(source, { entries: [entries[0]] });
    assert.deepEqual(configWarnings(config), [], type);
    assert.ok(config.modules.length > 0, type);
    assert.ok(config.modules.every(m => MODULES[m.type]), type);
    assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), source, type);
    assert.equal(rows.find(r => r.path === 'type').status, 'changed');
  }
});

test('backup preserves nested actions, unknown extensions and exact input across edits and import/export', () => {
  const original = legacy('f1-practice-timing-card', {
    title: 'My view', future: { list: [false, null, 0, 'å'] },
    tap_action: { action: 'perform-action', perform_action: 'script.read', data: { literal: '${keep}' }, confirmation: { text: 'Read?' } },
    grid_options: { columns: 6 }, card_mod: { style: 'ha-card { border: 0; }' },
  });
  const before = JSON.stringify(original), proposed = proposeMigration(original).config;
  assert.equal(JSON.stringify(original), before);
  assert.deepEqual(proposed.tap_action, original.tap_action);
  proposed.title = 'Changed'; proposed.modules.reverse(); proposed.appearance.mode = 'light';
  const restored = restoreLegacy(importConfig(exportConfig(proposed)));
  assert.deepEqual(restored, original);
  restored.future.list.push('changed'); assert.equal(proposed.migration.original.future.list.length, 4);
  assert.equal(proposed.migration.report.find(r => r.path === 'card_mod').status, 'review');
});

test('every explicit source setting receives a report entry, even unknown and computed color settings', () => {
  const source = legacy('f1-race-lap-card', { show_sectors: true, color_overall_fastest: '#963', color_personal_fastest: 'rgb(12, 44, 230)', color_timed: 'var(--mine)', show_timing_indicators: false, invented: 42 });
  const { config, rows } = proposeMigration(source);
  for (const key of Object.keys(source)) assert.equal(rows.filter(r => r.path === key).length, 1, key);
  assert.deepEqual(config.appearance.palette, { overall: '#996633', personal: '#0c2ce6' });
  assert.equal(rows.find(r => r.path === 'color_timed').status, 'review');
  assert.equal(rows.find(r => r.path === 'show_timing_indicators').status, 'changed');
  assert.equal(config.accessibility.signals, 'shape');
  assert.ok(config.modules[0].fields.includes('sector_3'));
});

test('renamed entity discovery retains a unique installation and discloses mixed or custom sources', () => {
  const a = proposeMigration(legacy('f1-driver-lap-times-card', { positions_entity: 'sensor.renamed_timing' }), { entries });
  assert.equal(a.config.f1_entry_id, 'a');
  assert.equal(a.rows.find(r => r.path === 'positions_entity').status, 'changed');
  const mixed = proposeMigration(legacy('f1-race-lap-card', { positions_entity: 'sensor.renamed_timing', tyres_entity: 'sensor.other_timing' }), { entries });
  assert.equal(mixed.config.f1_entry_id, '');
  assert.equal(mixed.rows.find(r => r.path === 'positions_entity').status, 'review');
  const selected = proposeMigration(legacy('f1-race-lap-card', { f1_entry_id: 'a', tyres_entity: 'sensor.arbitrary' }), { entries, entryId: 'b' });
  assert.equal(selected.config.f1_entry_id, 'b');
  assert.equal(selected.rows.find(r => r.path === 'f1_entry_id').status, 'review');
  assert.equal(selected.rows.find(r => r.path === 'tyres_entity').status, 'review');
});

test('custom and default Weekend Hub spoiler helpers fail closed instead of revealing results', () => {
  for (const original of [legacy('f1-weekend-hub-card'), legacy('f1-last-race-results-card', { no_spoiler_entity: 'input_boolean.private' })]) {
    const { config } = proposeMigration(original, { entries: [entries[0]] });
    assert.equal(config.context.spoilers, 'hide'); assert.deepEqual(restoreLegacy(config), original);
  }
  assert.equal(proposeMigration(legacy('f1-last-race-results-card', { no_spoiler_entity: 'switch.protection' }), { entries: [entries[0]] }).config.context.spoilers, 'inherit');
});

test('Weekend Hub migration opens the selected legacy view and discloses update-rate limits', () => {
  for (const default_view of ['overview', 'timeline', 'strategy', 'telemetry', 'battles']) {
    const original = legacy('f1-weekend-hub-card', { default_view, throttle_ms: 500 });
    const { config, rows } = proposeMigration(original, { entries: [entries[0]] });
    assert.equal(config.layout, 'tabs');
    assert.equal(config.modules[0].type, default_view);
    assert.equal(rows.find(row => row.path === 'default_view').status, 'mapped');
    assert.equal(rows.find(row => row.path === 'throttle_ms').status, 'changed');
    assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
  }
  const fallback = proposeMigration(legacy('f1-weekend-hub-card', { default_view: 'invalid' }));
  assert.equal(fallback.config.modules[0].type, 'overview');
  assert.equal(fallback.rows.find(row => row.path === 'default_view').status, 'changed');
  for (const throttle_ms of [100, 5000]) {
    assert.equal(proposeMigration(legacy('f1-weekend-hub-card', { throttle_ms })).rows.find(row => row.path === 'throttle_ms').status, 'review');
  }
});

test('Pit Stops conversion preserves status and availability choices while discovering authentication by installation', () => {
  const pitEntry = { ...entries[0], entities: { ...entries[0].entities, f1tv_token_status: 'sensor.f1_token_health' } };
  const original = legacy('f1-pitstop-overview-card', {
    auth_status_entity: 'sensor.f1_f1tv_token_status', show_availability_notice: false, show_status: true,
  });
  const { config, rows } = proposeMigration(original, { entries: [pitEntry] });
  const pit = config.modules.find(module => module.type === 'pit_stops');
  assert.ok(pit.fields.includes('status'));
  assert.equal(pit.options.show_availability_notice, false);
  for (const key of ['auth_status_entity', 'show_availability_notice', 'show_status']) {
    assert.notEqual(rows.find(row => row.path === key).status, 'review', key);
  }
  assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
  const hidden = proposeMigration(legacy('f1-pitstop-overview-card', { show_status: false })).config.modules.find(module => module.type === 'pit_stops');
  assert.equal(hidden.fields.includes('status'), false);
  assert.ok(proposeMigration(legacy('f1-pitstop-overview-card')).config.modules.find(module => module.type === 'pit_stops').fields.includes('status'));
  assert.equal(proposeMigration(legacy('f1-pitstop-overview-card', { auth_status_entity: 'sensor.custom_auth' }), { entries: [pitEntry] }).rows.find(row => row.path === 'auth_status_entity').status, 'review');
});

test('championship conversion preserves delta, status and availability choices while discovering authentication by installation', () => {
  const championshipEntry = { ...entries[0], entities: { ...entries[0].entities, f1tv_token_status: 'sensor.f1_token_health' } };
  for (const type of ['f1-championship-prediction-drivers-card', 'f1-championship-prediction-teams-card']) {
    for (const visible of [false, true]) {
      const original = legacy(type, { auth_status_entity: 'sensor.f1_f1tv_token_status', show_availability_notice: visible, show_delta: visible, show_mode_badge: visible });
      const { config, rows } = proposeMigration(original, { entries: [championshipEntry] });
      const standings = config.modules.find(module => module.type === 'standings');
      assert.equal(standings.fields.includes('points_change'), visible);
      assert.equal(standings.options.show_availability_notice, visible);
      assert.equal(standings.options.show_mode_badge, visible);
      for (const key of ['auth_status_entity', 'show_availability_notice', 'show_delta', 'show_mode_badge']) assert.notEqual(rows.find(row => row.path === key).status, 'review', `${type}:${key}`);
      assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
    }
    assert.equal(proposeMigration(legacy(type, { auth_status_entity: 'sensor.custom_auth' }), { entries: [championshipEntry] }).rows.find(row => row.path === 'auth_status_entity').status, 'review');
  }
});

test('Live Session conversion preserves flags, lap progress and supported layouts', () => {
  for (const layout_mode of ['auto', 'compact', 'full']) {
    for (const visible of [false, true]) {
      const original = legacy('f1-live-session-card', { layout_mode, show_flag: visible, show_lap_progress: visible });
      const { config, rows } = proposeMigration(original);
      const overview = config.modules.find(module => module.type === 'overview');
      assert.equal(config.appearance.flags, visible);
      assert.equal(overview.fields.includes('lap_progress'), visible);
      assert.equal(overview.options.layout_mode, layout_mode);
      for (const key of ['layout_mode', 'show_flag', 'show_lap_progress']) {
        assert.equal(rows.find(row => row.path === key).status, 'mapped', `${layout_mode}:${visible}:${key}`);
      }
      assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
    }
  }
});

test('Track Map conversion preserves metadata visibility, layout and status-line meaning', () => {
  for (const layout_mode of ['auto', 'compact', 'full']) for (const track_status_line_mode of ['accent', 'full', 'off']) {
    for (const visible of [false, true]) {
      const original = legacy('f1-track-map-card', {
        layout_mode, track_status_line_mode, show_footer: visible, show_session_info: visible,
        show_lap_progress: visible, show_track_status: visible,
      });
      const { config, rows } = proposeMigration(original);
      const map = config.modules.find(module => module.type === 'map');
      assert.equal(map.options.layout_mode, layout_mode);
      assert.equal(map.options.track_status_line_mode, track_status_line_mode);
      for (const key of ['show_footer', 'show_session_info', 'show_lap_progress', 'show_track_status']) assert.equal(map.options[key], visible, key);
      for (const key of Object.keys(original).filter(key => key !== 'type')) assert.equal(rows.find(row => row.path === key).status, 'mapped', key);
      assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
    }
  }
});

test('Next Race conversion preserves circuit map, history and parallel circuit times', () => {
  for (const visible of [false, true]) {
    const original = legacy('f1-next-race-card', { show_map: visible, show_history: visible, show_track_time: visible });
    const { config, rows } = proposeMigration(original);
    const overview = config.modules.find(module => module.type === 'overview');
    const calendar = config.modules.find(module => module.type === 'calendar');
    assert.equal(overview.fields.includes('circuit_map'), visible);
    assert.equal(overview.fields.includes('circuit_history'), visible);
    assert.equal(calendar.options.show_track_time, visible);
    for (const key of ['show_map', 'show_history', 'show_track_time']) assert.equal(rows.find(row => row.path === key).status, 'mapped', key);
    assert.equal(rows.find(row => row.path === '$coverage').status, 'changed');
    assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
  }
  const defaults = proposeMigration(legacy('f1-next-race-card')).config;
  assert.ok(defaults.modules.find(module => module.type === 'overview').fields.includes('circuit_map'));
  assert.ok(defaults.modules.find(module => module.type === 'overview').fields.includes('circuit_history'));
  assert.equal(defaults.modules.find(module => module.type === 'calendar').options.show_track_time, true);
});

test('gap mapping is independent of key order and off hides both gap references', () => {
  for (const options of [{ gap_mode: 'off', show_gap: true }, { show_gap: true, gap_mode: 'off' }, { gap_mode: 'leader', show_gap: true }, { show_gap: true, gap_mode: 'leader' }]) {
    const { config } = proposeMigration(legacy('f1-driver-lap-times-card', options));
    assert.equal(config.modules[0].fields.includes('interval'), false);
    assert.equal(config.modules[0].fields.includes('gap'), options.gap_mode === 'leader');
  }
});

test('legacy live gap controls remain interactive only where the old card rendered them', () => {
  for (const type of ['f1-driver-lap-times-card', 'f1-race-lap-card']) {
    assert.equal(proposeMigration(legacy(type)).config.modules[0].options.show_gap_toggle, true, type);
    for (const show_gap_toggle of [false, true]) {
      const original = legacy(type, { show_gap_toggle });
      const { config, rows } = proposeMigration(original);
      assert.equal(config.modules[0].options.show_gap_toggle, show_gap_toggle, type);
      assert.equal(rows.find(row => row.path === 'show_gap_toggle').status, 'mapped', type);
      assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original, type);
    }
  }
  const practice = proposeMigration(legacy('f1-practice-timing-card', { show_gap_toggle: true }));
  assert.equal(practice.config.modules[0].options.show_gap_toggle, false);
  assert.equal(practice.rows.find(row => row.path === 'show_gap_toggle').status, 'changed');
});

test('conversion handles unsupported values without silently clamping them', () => {
  const { config, rows } = proposeMigration(legacy('f1-driver-lap-times-card', { show_lap_history: true, lap_history_limit: 999, theme_mode: 'pink' }));
  assert.equal(rows.find(r => r.path === 'lap_history_limit').status, 'review');
  assert.equal(rows.find(r => r.path === 'theme_mode').status, 'review');
  assert.equal(config.modules[0].options.history, 0);
});

test('only a known recoverable legacy configuration can be restored', () => {
  assert.equal(isLegacyConfig({ type: 'constructor' }), false);
  assert.throws(() => proposeMigration({ type: 'custom:elsewhere' }), /supported legacy/);
  assert.throws(() => proposeMigration(JSON.parse('{"type":"custom:f1-race-lap-card","__proto__":{}}')), /reserved/);
  assert.throws(() => restoreLegacy({ migration: { version: 2, original: legacy('f1-race-lap-card') } }), /backup/);
  assert.throws(() => restoreLegacy({ migration: { version: 1, original: { type: 'custom:elsewhere' } } }), /backup/);
});


test('all-lap history is disclosed as bounded, while disabled history stays disabled', () => {
  for (const values of [{ show_lap_history: true, lap_history_limit: 0 }, { lap_history_limit: 0, show_lap_history: true }, { show_lap_history: true }]) {
    const result = proposeMigration(legacy('f1-driver-lap-times-card', values));
    assert.equal(result.config.modules[0].options.history, 30);
    assert.ok(result.rows.some(r => r.status === 'changed' && r.message.en.includes('30 laps')));
  }
  assert.equal(proposeMigration(legacy('f1-driver-lap-times-card', { lap_history_limit: 8 })).config.modules[0].options.history, 0);
});

test('personal best sectors transfer their meaning and hybrid remains an explicit difference', () => {
  const personal = proposeMigration(legacy('f1-qualifying-timing-card', { sector_display_mode: 'personal_best' }));
  assert.ok(personal.config.modules[0].fields.includes('best_sector_1'));
  assert.ok(!personal.config.modules[0].fields.includes('sector_1'));
  const hybrid = proposeMigration(legacy('f1-qualifying-timing-card', { sector_display_mode: 'hybrid' }));
  assert.equal(hybrid.rows.find(r => r.path === 'sector_display_mode').status, 'review');
});

test('qualifying conversion preserves current-part delta visibility', () => {
  for (const show_delta of [false, true]) {
    const original = legacy('f1-qualifying-timing-card', { show_delta });
    const { config, rows } = proposeMigration(original);
    assert.equal(config.modules[0].fields.includes('qualifying_gap'), show_delta);
    assert.equal(rows.find(row => row.path === 'show_delta').status, 'mapped');
    assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
  }
  assert.ok(proposeMigration(legacy('f1-qualifying-timing-card')).config.modules[0].fields.includes('qualifying_gap'));
});

test('legacy identity columns, archive delta and document order retain their meaning', () => {
  const hiddenDriver = proposeMigration(legacy('f1-driver-lap-times-card', { show_tla: false }));
  assert.equal(hiddenDriver.config.modules[0].fields.includes('driver'), false);
  assert.equal(hiddenDriver.rows.find(row => row.path === 'show_tla').status, 'mapped');

  const hiddenTeam = proposeMigration(legacy('f1-championship-prediction-teams-card', { show_team_name: false }));
  assert.equal(hiddenTeam.config.modules[0].fields.includes('team'), false);
  assert.equal(hiddenTeam.rows.find(row => row.path === 'show_team_name').status, 'mapped');

  for (const [sort_order, order] of [['asc', 'oldest'], ['desc', 'newest']]) {
    const documents = proposeMigration(legacy('f1-fia-documents-card', { sort_order }));
    assert.equal(documents.config.modules[0].options.order, order);
    assert.equal(documents.rows.find(row => row.path === 'sort_order').status, 'mapped');
  }

  for (const show_delta of [false, true]) {
    const archive = proposeMigration(legacy('f1-session-archive-card', { show_delta }));
    assert.equal(archive.config.modules[0].fields.includes('position_change'), show_delta);
    assert.equal(archive.rows.find(row => row.path === 'show_delta').status, 'mapped');
  }
});

test('FIA document migration retains supported presentation and link choices', () => {
  const original = legacy('f1-fia-documents-card', {
    display_mode: 'latest', open_in_new_tab: false, show_count: false,
    show_race_context: true, show_latest_badge: false, list_max_height: 480,
    show_document_coloring: false, show_document_type: false,
    show_fia_logo: false, show_pdf_icon: false,
  });
  const { config, rows } = proposeMigration(original);
  const options = config.modules[0].options;
  assert.equal(options.presentation, 'latest');
  assert.equal(options.open_new_tab, false);
  assert.equal(options.show_count, false);
  assert.equal(options.show_race_context, true);
  assert.equal(options.show_latest_badge, false);
  assert.equal(options.list_max_height, 480);
  assert.equal(options.document_coloring, false);
  assert.equal(options.show_document_type, false);
  assert.equal(options.show_fia_logo, false);
  assert.equal(options.show_pdf_icon, false);
  for (const key of Object.keys(original).filter(key => key !== 'type')) {
    assert.equal(rows.find(row => row.path === key).status, 'mapped', key);
  }
  assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
  assert.equal(proposeMigration(legacy('f1-fia-documents-card', { display_mode: 'banner' })).rows.find(row => row.path === 'display_mode').status, 'review');
  assert.equal(proposeMigration(legacy('f1-fia-documents-card', { list_max_height: 5 })).rows.find(row => row.path === 'list_max_height').status, 'review');
});

test('starting grid migration retains supported comparison columns and context visibility', () => {
  const original = legacy('f1-starting-grid-card', {
    display_mode: 'table',
    show_grid_delta: false, show_qualifying_segment: true,
    show_qualifying_delta: true, show_metadata: false, show_status_badge: false,
    show_source_badge: false,
  });
  const { config, rows } = proposeMigration(original);
  const [grid] = config.modules;
  assert.equal(grid.options.presentation, 'table');
  assert.equal(grid.fields.includes('grid_delta'), false);
  assert.equal(grid.fields.includes('qualifying_segment'), true);
  assert.equal(grid.fields.includes('qualifying_delta'), true);
  assert.equal(grid.options.show_context, false);
  assert.equal(grid.options.show_status, false);
  assert.equal(grid.options.show_source, false);
  for (const key of Object.keys(original).filter(key => key !== 'type')) assert.equal(rows.find(row => row.path === key).status, 'mapped', key);
  assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
  assert.equal(proposeMigration(legacy('f1-starting-grid-card')).config.modules[0].options.presentation, 'grid');
  assert.equal(proposeMigration(legacy('f1-starting-grid-card')).config.modules[0].options.show_source, true);
});

test('Race Control migration retains message filters, display timing, clearing and effective list height', () => {
  const original = legacy('f1-race-control-card', { hide_blue_flags: true, hide_track_limits: true, show_fia_logo: false, list_max_height: 5, min_display_time: 12, show_clear_button: false });
  const { config, rows } = proposeMigration(original);
  const options = config.modules[0].options;
  assert.equal(options.hide_blue_flags, true);
  assert.equal(options.hide_track_limits, true);
  assert.equal(options.show_fia_logo, false);
  assert.equal(options.list_max_height, 240);
  assert.equal(options.min_display_time, 12);
  assert.equal(options.show_clear_button, false);
  for (const key of Object.keys(original).filter(key => key !== 'type')) assert.equal(rows.find(row => row.path === key).status, 'mapped', key);
  assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
  assert.equal(proposeMigration(legacy('f1-race-control-card', { min_display_time: 31 })).rows.find(row => row.path === 'min_display_time').status, 'review');
});

test('progression migrations retain chart layout and future-data choices', () => {
  const seasonOriginal = legacy('f1-season-progression-card', {
    show_legend: false, legend_position: 'right', show_legend_points: false,
    show_points: false, show_round_labels: false, show_future_rounds: false, chart_height: 500,
  });
  const season = proposeMigration(seasonOriginal);
  assert.deepEqual(Object.fromEntries(['show_legend', 'legend_position', 'show_legend_points', 'show_points', 'show_round_labels', 'show_future_rounds', 'chart_height'].map(key => [key, season.config.modules[0].options[key]])), {
    show_legend: false, legend_position: 'right', show_legend_points: false,
    show_points: false, show_round_labels: false, show_future_rounds: false, chart_height: 500,
  });
  for (const key of Object.keys(seasonOriginal).filter(key => key !== 'type')) assert.equal(season.rows.find(row => row.path === key).status, 'mapped', key);
  assert.deepEqual(restoreLegacy(importConfig(exportConfig(season.config))), seasonOriginal);

  const lapOriginal = legacy('f1-lap-position-progression-card', { show_points: false, show_round_labels: false, chart_height: 700 });
  const lap = proposeMigration(lapOriginal), archive = lap.config.modules[0];
  assert.deepEqual({ show_points: archive.options.show_points, show_round_labels: archive.options.show_round_labels, chart_height: archive.options.chart_height }, { show_points: false, show_round_labels: false, chart_height: 700 });
  for (const key of Object.keys(lapOriginal).filter(key => key !== 'type')) assert.equal(lap.rows.find(row => row.path === key).status, 'mapped', key);
  assert.deepEqual(restoreLegacy(importConfig(exportConfig(lap.config))), lapOriginal);
  assert.equal(proposeMigration(legacy('f1-season-progression-card', { chart_height: 521 })).rows.find(row => row.path === 'chart_height').status, 'review');
  assert.equal(proposeMigration(legacy('f1-lap-position-progression-card', { chart_height: 299 })).rows.find(row => row.path === 'chart_height').status, 'review');
});

test('legacy race selectors remain hidden across result and archive modules', () => {
  for (const type of ['f1-last-race-results-card', 'f1-session-archive-card', 'f1-lap-position-progression-card']) {
    const original = legacy(type, { show_session_selector: false });
    const { config, rows } = proposeMigration(original);
    const targets = config.modules.filter(module => ['results', 'archive'].includes(module.type));
    assert.ok(targets.length, type);
    for (const module of targets) assert.equal(module.options[module.type === 'results' ? 'show_selector' : 'show_session_selector'], false, `${type}:${module.type}`);
    assert.equal(rows.find(row => row.path === 'show_session_selector').status, 'mapped');
    assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
  }
});

test('session archive alias keeps its forced archive scope regardless of the saved legacy value', () => {
  for (const default_scope of ['current', 'archive']) {
    const original = legacy('f1-session-archive-card', { default_scope });
    const { config, rows } = proposeMigration(original);
    assert.equal(config.modules[0].type, 'archive');
    assert.equal(rows.find(row => row.path === 'default_scope').status, 'mapped');
    assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
  }
});

test('results and archive conversion retain session-type badge visibility', () => {
  for (const type of ['f1-last-race-results-card', 'f1-session-archive-card']) for (const show_session_type_badge of [false, true]) {
    const original = legacy(type, { show_session_type_badge });
    const { config, rows } = proposeMigration(original);
    const targets = config.modules.filter(module => ['results', 'archive'].includes(module.type));
    assert.ok(targets.length);
    assert.ok(targets.every(module => module.options.show_session_type_badge === show_session_type_badge));
    assert.equal(rows.find(row => row.path === 'show_session_type_badge').status, 'mapped');
    assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
  }
});

test('championship, results and archive conversion retain spoiler placeholder text', () => {
  for (const type of ['f1-championship-prediction-drivers-card', 'f1-championship-prediction-teams-card', 'f1-last-race-results-card', 'f1-session-archive-card']) {
    const original = legacy(type, { spoiler_placeholder: 'CLASSIFIED' });
    const { config, rows } = proposeMigration(original);
    const targets = config.modules.filter(module => ['results', 'standings', 'archive'].includes(module.type));
    assert.ok(targets.length);
    assert.ok(targets.every(module => module.options.spoiler_placeholder === 'CLASSIFIED'));
    assert.equal(rows.find(row => row.path === 'spoiler_placeholder').status, 'mapped');
    assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
  }
});

test('legacy context and all-driver rows disclose their narrower evidence-backed replacement', () => {
  const weekend = proposeMigration(legacy('f1-weekend-hub-card', { show_context: false }));
  assert.equal(weekend.rows.find(row => row.path === 'show_context').status, 'changed');
  for (const type of ['f1-investigations-card', 'f1-track-limits-card']) for (const show_all_drivers of [false, true]) {
    const original = legacy(type, { show_all_drivers });
    const { config, rows } = proposeMigration(original);
    assert.equal(rows.find(row => row.path === 'show_all_drivers').status, 'changed');
    assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
  }
});

test('current results and standings retain driver image choice while archive avoids current identity joins', () => {
  for (const type of ['f1-championship-prediction-drivers-card', 'f1-last-race-results-card']) for (const driver_image_type of ['team_logo', 'headshot']) {
    const original = legacy(type, { driver_image_type });
    const { config, rows } = proposeMigration(original);
    const targets = config.modules.filter(module => ['results', 'standings'].includes(module.type));
    assert.ok(targets.length);
    assert.ok(targets.every(module => module.options.driver_image_type === driver_image_type));
    assert.equal(rows.find(row => row.path === 'driver_image_type').status, 'mapped');
    assert.deepEqual(restoreLegacy(importConfig(exportConfig(config))), original);
  }
  const archive = proposeMigration(legacy('f1-session-archive-card', { driver_image_type: 'headshot' }));
  assert.equal(archive.rows.find(row => row.path === 'driver_image_type').status, 'changed');
});

test('track map conversion preserves hidden labels and explicit label mode regardless of key order', () => {
  for (const values of [{ show_labels: false }, { show_labels: false, driver_label_mode: 'number' }, { driver_label_mode: 'number', show_labels: false }]) {
    const { config, rows } = proposeMigration(legacy('f1-track-map-card', values));
    assert.equal(config.modules[0].options.labels, Object.hasOwn(values, 'driver_label_mode') ? 'number' : 'off');
    for (const key of Object.keys(values)) assert.equal(rows.find(row => row.path === key).status, 'mapped', key);
  }
  const count = proposeMigration(legacy('f1-track-map-card', { show_driver_count: false }));
  assert.equal(count.config.modules[0].options.show_driver_count, false);
  assert.equal(count.rows.find(row => row.path === 'show_driver_count').status, 'mapped');
  const cadence = proposeMigration(legacy('f1-track-map-card', { throttle_ms: 100, interpolation_ms: 'auto' }));
  assert.equal(cadence.rows.find(row => row.path === 'throttle_ms').status, 'changed');
  assert.equal(cadence.rows.find(row => row.path === 'interpolation_ms').status, 'changed');
});

test('replay entity bindings retain the discovered installation but reject custom overrides', () => {
  const entityBindings = {
    status_entity: ['replay_status', 'sensor.replay_status'],
    year_entity: ['replay_year_select', 'select.replay_year'],
    session_entity: ['replay_session_select', 'select.replay_session'],
    start_reference_entity: ['replay_start_reference', 'select.replay_reference'],
    load_button_entity: ['replay_load', 'button.replay_load'],
    play_button_entity: ['replay_play', 'button.replay_play'],
    pause_button_entity: ['replay_pause', 'button.replay_pause'],
    back_button_entity: ['replay_back_30', 'button.replay_back'],
    forward_button_entity: ['replay_forward_30', 'button.replay_forward'],
    stop_button_entity: ['replay_stop', 'button.replay_stop'],
    refresh_button_entity: ['replay_refresh', 'button.replay_refresh'],
    player_entity: ['replay_player', 'media_player.replay'],
  };
  const replayEntry = {
    entry_id: 'replay-entry',
    entities: Object.fromEntries(Object.values(entityBindings)),
  };
  const original = legacy('f1-replay-control-card', Object.fromEntries(Object.entries(entityBindings).map(([key, [, entityId]]) => [key, entityId])));
  const result = proposeMigration(original, { entries: [replayEntry] });
  assert.equal(result.config.f1_entry_id, 'replay-entry');
  for (const key of Object.keys(entityBindings)) {
    assert.equal(result.rows.find(row => row.path === key).status, 'changed', key);
  }
  assert.deepEqual(restoreLegacy(result.config), original);

  const custom = proposeMigration(legacy('f1-replay-control-card', { player_entity: 'media_player.custom' }), { entries: [replayEntry], entryId: 'replay-entry' });
  assert.equal(custom.rows.find(row => row.path === 'player_entity').status, 'review');
});

test('replay display migration retains supported visibility choices', () => {
  const original = legacy('f1-replay-control-card', {
    display_mode: 'compact',
    show_refresh: false,
    show_button_labels: false,
    show_secondary_selects: false,
    show_seek_controls: false,
    show_start_reference: false,
    show_status_details: false,
  });
  const result = proposeMigration(original);
  assert.deepEqual(result.config.modules[0].options, {
    display: 'compact',
    secondary_selects: false,
    start_reference: false,
    seek_controls: false,
    refresh: false,
    show_button_labels: false,
    status_details: false,
  });
  for (const key of Object.keys(original).filter(key => key !== 'type')) {
    assert.equal(result.rows.find(row => row.path === key).status, 'mapped', key);
  }
});

test('season calendar conversion preserves race scope and coupled display choices regardless of property order', () => {
  const defaults = proposeMigration(legacy('f1-season-calendar-card')).config.modules[0].options;
  assert.deepEqual(defaults.sessions, ['race']);
  assert.deepEqual(defaults.details, ['round']);
  assert.equal(defaults.past, 'dim');
  for (const dim of [false, true]) for (const hide of [false, true]) for (const highlight of [false, true]) {
    const flags = { dim_past_races: dim, hide_past_races: hide, highlight_next_race: highlight, show_round: false, show_circuit_name: true, show_location: true };
    for (const choices of [flags, Object.fromEntries(Object.entries(flags).reverse())]) {
      const original = legacy('f1-season-calendar-card', choices);
      const { config, rows } = proposeMigration(original);
      assert.equal(config.modules[0].options.past, hide ? 'hide' : dim ? 'dim' : 'show');
      assert.equal(config.modules[0].options.next, highlight && dim && !hide ? 'label' : 'none');
      assert.deepEqual([...config.modules[0].options.details].sort(), ['circuit', 'location']);
      assert.ok(rows.filter(row => Object.hasOwn(choices, row.path)).every(row => row.status !== 'review'));
      assert.deepEqual(restoreLegacy(config), original);
    }
  }
});
