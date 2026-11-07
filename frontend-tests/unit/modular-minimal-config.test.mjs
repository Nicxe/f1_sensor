import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig, duplicateModule, exportConfig, importConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { timingFields } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js';

const timing = options => normalizeConfig({ modules: [{ type: 'timing', options }] }).modules[0];

test('existing Timing configurations keep their presentation, columns and legacy gap toggle', () => {
  const source = { appearance: { style: 'minimal', density: 'compact' }, modules: [{ type: 'timing', fields: ['driver', 'gap', 'interval', 'last_lap'], options: { show_gap_toggle: true } }] };
  const saved = normalizeConfig(source), module = saved.modules[0];
  assert.deepEqual(module.fields, source.modules[0].fields);
  assert.equal(saved.appearance.style, 'minimal');
  assert.equal(saved.appearance.density, 'compact');
  assert.deepEqual(Object.fromEntries(['presentation', 'narrow_layout', 'gap_display', 'gap_primary', 'position_change', 'driver_badges', 'dim_retired', 'tyre_age_inline', 'qualifying_focus', 'show_gap_toggle'].map(key => [key, module.options[key]])), {
    presentation: 'current', narrow_layout: false, gap_display: 'separate', gap_primary: 'interval', position_change: 'off', driver_badges: false, dim_retired: false, tyre_age_inline: false, qualifying_focus: 'all', show_gap_toggle: true,
  });
  assert.deepEqual(source.modules[0].options, { show_gap_toggle: true });
});

test('minimal presentation and detail choices survive export, duplication and independent appearance changes', () => {
  const options = { presentation: 'minimal', narrow_layout: true, gap_display: 'combined', gap_primary: 'gap', position_change: 'grid', driver_badges: true, dim_retired: true, tyre_age_inline: true, qualifying_focus: 'current' };
  const config = normalizeConfig({ appearance: { density: 'spacious' }, modules: [{ id: 'timing', type: 'timing', fields: ['driver', 'gap', 'interval', 'q1_time', 'q2_time', 'q3_time'], options }] });
  const imported = importConfig(exportConfig(config));
  assert.deepEqual(imported, config);
  assert.equal(imported.appearance.density, 'spacious');
  const duplicated = duplicateModule(imported, 'timing');
  duplicated.modules[1].options.gap_primary = 'interval';
  duplicated.modules[1].options.presentation = 'current';
  assert.equal(duplicated.modules[0].options.gap_primary, 'gap');
  assert.equal(duplicated.modules[0].options.presentation, 'minimal');
  assert.deepEqual(duplicated.modules[0].fields, config.modules[0].fields);
  const restyled = normalizeConfig({ ...config, appearance: { ...config.appearance, style: 'ha', density: 'compact' } });
  assert.deepEqual(restyled.modules, config.modules);
});

test('qualifying focus remains independent of saved columns and session profiles', () => {
  for (const qualifying_focus of ['all', 'current', 'q1', 'q2', 'q3']) {
    const module = timing({ profile: 'auto', presentation: 'minimal', qualifying_focus });
    assert.equal(module.options.qualifying_focus, qualifying_focus);
    assert.deepEqual(timingFields(module, 'Qualifying'), ['position', 'driver', 'q1_time', 'q2_time', 'q3_time', 'sector_1', 'sector_2', 'sector_3']);
    assert.deepEqual(timingFields(module, 'Race'), ['position', 'driver', 'gap', 'interval', 'last_lap', 'sector_1', 'sector_2', 'sector_3', 'tyre']);
    assert.deepEqual(importConfig(exportConfig({ modules: [module] })).modules[0], module);
  }
});

test('minimal Timing choices reject malformed values at their precise setting', () => {
  for (const [key, values] of Object.entries({
    presentation: ['compact', true], gap_display: ['stacked', false], gap_primary: ['leader', 1],
    position_change: ['latest', true], qualifying_focus: ['q4', 'race'],
    narrow_layout: ['false', 0], driver_badges: ['true', []], dim_retired: ['true', 1], tyre_age_inline: ['false', {}],
  })) for (const value of values) assert.throws(() => timing({ [key]: value }), new RegExp(`modules\\.0\\.options\\.${key}:`));
});
