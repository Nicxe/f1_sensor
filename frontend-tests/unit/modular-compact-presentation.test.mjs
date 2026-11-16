import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig, resolvePresentation, exportConfig, importConfig, duplicateModule } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { MODULES } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js';

const moduleTypes = Object.keys(MODULES);

test('compact presentation remains opt-in for every module and does not reinterpret existing style or density', () => {
  const source = { appearance: { style: 'minimal', density: 'compact' }, modules: moduleTypes.map(type => ({ type })) };
  const config = normalizeConfig(source);
  assert.equal(config.appearance.presentation, 'current');
  assert.equal(config.appearance.style, 'minimal');
  assert.equal(config.appearance.density, 'compact');
  for (const module of config.modules) {
    assert.equal(module.appearance.presentation, 'inherit');
    assert.equal(resolvePresentation(config.appearance, module), 'current');
  }
  assert.equal(source.appearance.presentation, undefined);
  assert.ok(source.modules.every(module => module.appearance === undefined));
});

test('card presentation reaches registered modules and preserves their content choices', () => {
  const source = {
    appearance: { presentation: 'compact', density: 'spacious', style: 'ha' },
    modules: [
      { id: 'timing', type: 'timing', fields: ['driver', 'gap', 'interval', 'sector_1_with_minisectors', 'tyre'], options: { gap_display: 'combined', gap_primary: 'gap', show_gap_toggle: true } },
      { id: 'weather', type: 'weather', fields: ['temperature', 'humidity'], options: { content: 'current_conditions', presentation: 'metrics' } },
      { id: 'control', type: 'race_control', options: { presentation: 'list', order: 'oldest', hide_blue_flags: true } },
      { id: 'tyres', type: 'tyres', fields: ['driver', 'tyre', 'tyre_age', 'tyre_new'], options: { content: 'current', rows: 3 } },
      { id: 'results', type: 'results', appearance: { presentation: 'compact' } },
    ],
  };
  const current = normalizeConfig({ ...source, appearance: { ...source.appearance, presentation: 'current' } });
  const config = normalizeConfig(source);
  assert.deepEqual(config.modules, current.modules);
  assert.equal(config.appearance.density, 'spacious');
  assert.equal(config.appearance.style, 'ha');
  assert.deepEqual(config.modules.map(module => resolvePresentation(config.appearance, module)), ['compact', 'compact', 'compact', 'compact', 'compact']);
  assert.equal(resolvePresentation(config.appearance, { type: 'unrecognized', appearance: { presentation: 'compact' } }), 'current');
  assert.deepEqual(config.modules[0].fields, source.modules[0].fields);
  assert.equal(config.modules[0].options.gap_primary, 'gap');
  assert.equal(config.modules[1].options.presentation, 'metrics');
  assert.equal(config.modules[2].options.presentation, 'list');
});

test('all module families inherit and override presentation without changing their defaults or saved data choices', () => {
  for (const type of moduleTypes) {
    const config = normalizeConfig({ appearance: { presentation: 'compact' }, modules: [{ type }] });
    const original = normalizeConfig({ modules: [{ type }] });
    assert.equal(resolvePresentation(config.appearance, config.modules[0]), 'compact', `${type} follows the compact card`);
    assert.deepEqual(config.modules[0], original.modules[0], `${type} keeps its fields, options and source selection`);
    const overridden = normalizeConfig({ ...config, modules: [{ ...config.modules[0], appearance: { presentation: 'current' } }] });
    assert.equal(resolvePresentation(overridden.appearance, overridden.modules[0]), 'current', `${type} can opt out`);
    assert.deepEqual(importConfig(exportConfig(overridden)), overridden, `${type} keeps its override after transfer`);
  }
});

test('module presentation can opt out of or opt into the card presentation without changing fields', () => {
  for (const cardPresentation of ['current', 'compact']) {
    const config = normalizeConfig({ appearance: { presentation: cardPresentation }, modules: [
      { type: 'weather', fields: ['temperature', 'rain_probability'], appearance: { presentation: 'current' } },
      { type: 'tyres', appearance: { presentation: 'compact' } },
      { type: 'race_control', appearance: { presentation: 'inherit' } },
    ] });
    assert.deepEqual(config.modules.map(module => resolvePresentation(config.appearance, module)), ['current', 'compact', cardPresentation]);
    assert.deepEqual(config.modules[0].fields, ['temperature', 'rain_probability']);
  }
});

test('explicit saved Timing presentation migrates once and survives normalization and editor transfers', () => {
  const config = normalizeConfig({ appearance: { presentation: 'compact' }, modules: [
    { id: 'legacy-current', type: 'timing', options: { presentation: 'current' } },
    { id: 'legacy-minimal', type: 'timing', options: { presentation: 'minimal' } },
    { id: 'follow', type: 'timing' },
  ] });
  assert.deepEqual(config.modules.map(module => module.appearance.presentation), ['current', 'compact', 'inherit']);
  assert.deepEqual(config.modules.map(module => module.options.presentation), ['current', 'minimal', 'current']);
  assert.deepEqual(config.modules.map(module => resolvePresentation(config.appearance, module)), ['current', 'compact', 'compact']);
  assert.deepEqual(normalizeConfig(config), config);
  assert.deepEqual(importConfig(exportConfig(config)), config);
  const duplicated = duplicateModule(config, 'legacy-minimal');
  assert.equal(duplicated.modules[2].appearance.presentation, 'compact');
  assert.equal(duplicated.modules[2].options.presentation, 'minimal');
  const changed = normalizeConfig({ ...config, appearance: { ...config.appearance, presentation: 'current' } });
  assert.deepEqual(changed.modules.map(module => resolvePresentation(changed.appearance, module)), ['current', 'compact', 'current']);
});

test('an explicit new Timing module choice takes precedence over the retained compatibility option', () => {
  const config = normalizeConfig({ appearance: { presentation: 'compact' }, modules: [
    { type: 'timing', appearance: { presentation: 'current' }, options: { presentation: 'minimal' } },
    { type: 'timing', appearance: { presentation: 'inherit' }, options: { presentation: 'current' } },
  ] });
  assert.deepEqual(config.modules.map(module => resolvePresentation(config.appearance, module)), ['current', 'compact']);
  assert.deepEqual(importConfig(exportConfig(config)), config);
});

test('card and module presentation reject malformed choices at their setting paths', () => {
  for (const value of ['minimal', 'inherit', '', false, 1, [], {}]) {
    assert.throws(() => normalizeConfig({ appearance: { presentation: value } }), /appearance\.presentation:/);
  }
  for (const value of ['minimal', 'auto', '', false, 1, [], {}]) {
    assert.throws(() => normalizeConfig({ modules: [{ type: 'weather', appearance: { presentation: value } }] }), /modules\.0\.appearance\.presentation:/);
  }
});
