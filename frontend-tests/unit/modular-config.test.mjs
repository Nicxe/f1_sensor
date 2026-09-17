import assert from 'node:assert/strict';
import test from 'node:test';
import { CUSTOM_STYLE_MAX_LENGTH, normalizeConfig, applyPreset, duplicateModule, moveModule, exportConfig, exportTemplate, importConfig, importTemplate, configWarnings, resolveSelection } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { MODULES, PRESETS, FIELDS } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js';

test('module focus behavior preserves explicit independence and rejects invalid modes', () => {
  const config = normalizeConfig({ modules: [{ type: 'timing' }, { type: 'timing', focus_mode: 'independent', driver: '16' }] });
  assert.equal(config.modules[0].focus_mode, 'inherit');
  const duplicate = duplicateModule(config, config.modules[1].id);
  assert.equal(duplicate.modules[2].focus_mode, 'independent');
  assert.deepEqual(importConfig(exportConfig(duplicate)), duplicate);
  assert.throws(() => normalizeConfig({ modules: [{ type: 'timing', focus_mode: 'invalid' }] }), /focus_mode/);
});

test('freeze control stays visible by default and can be hidden with a typed setting', () => {
  assert.equal(normalizeConfig({}).context.show_freeze_control, true);
  const hidden = normalizeConfig({ context: { show_freeze_control: false } });
  assert.equal(hidden.context.show_freeze_control, false);
  assert.deepEqual(importConfig(exportConfig(hidden)), hidden);
  assert.throws(() => normalizeConfig({ context: { show_freeze_control: 'false' } }), /show_freeze_control/);
});

test('driver focus control stays visible by default and can be hidden with a typed setting', () => {
  assert.equal(normalizeConfig({}).context.show_focus_control, true);
  const hidden = normalizeConfig({ context: { show_focus_control: false } });
  assert.equal(hidden.context.show_focus_control, false);
  assert.deepEqual(importConfig(exportConfig(hidden)), hidden);
  assert.throws(() => normalizeConfig({ context: { show_focus_control: 'false' } }), /show_focus_control/);
});

test('About sections stay visible by default and can be hidden per supported module', () => {
  for (const type of ['weather', 'battles', 'strategy', 'telemetry']) {
    const shown = normalizeConfig({ modules: [{ type }] });
    assert.equal(shown.modules[0].options.show_explanation, true);
    const hidden = normalizeConfig({ modules: [{ type, options: { show_explanation: false } }] });
    assert.equal(hidden.modules[0].options.show_explanation, false);
    assert.deepEqual(importConfig(exportConfig(hidden)), hidden);
  }
  assert.throws(() => normalizeConfig({ modules: [{ type: 'weather', options: { show_explanation: 'false' } }] }), /show_explanation/);
});

test('version 1 migrates to typed session selection and phase visibility without changing fields', () => {
  const migrated = normalizeConfig({ version: 1, context: { driver: '16' }, modules: [{ type: 'timing', fields: ['driver', 'last_lap'] }] });
  assert.equal(migrated.version, 2);
  assert.deepEqual(migrated.context.selection, { mode: 'follow', source: 'auto' });
  assert.deepEqual(migrated.context.share, ['focus']);
  assert.deepEqual(migrated.modules[0].selection, { mode: 'inherit' });
  assert.deepEqual(migrated.modules[0].when, ['before', 'active', 'finished', 'unknown']);
  assert.deepEqual(migrated.modules[0].fields, ['driver', 'last_lap']);
});

test('session selection is a strict union and follows module, card and group priority', () => {
  const pinned = { mode: 'pinned', source: 'replay', season: 2026, meeting_key: 'meeting', session_key: 'race' };
  const config = normalizeConfig({ context: { scope: 'group', group: 'F1', share: ['focus', 'selection'] }, modules: [{ type: 'timing' }, { type: 'timing', selection: pinned }] });
  assert.deepEqual(resolveSelection(config.context, config.modules[0], { selection: { mode: 'follow', source: 'live' } }), { mode: 'follow', source: 'live' });
  assert.deepEqual(resolveSelection(config.context, config.modules[1], { selection: { mode: 'follow', source: 'live' } }), pinned);
  for (const selection of [
    { mode: 'inherit' },
    { mode: 'follow', source: 'archive' },
    { mode: 'pinned', source: 'live', season: 1949, meeting_key: 'm', session_key: 's' },
    { mode: 'pinned', source: 'live', season: 2026, meeting_key: '', session_key: 's' },
    { mode: 'follow', source: 'auto', season: 2026 },
  ]) assert.throws(() => normalizeConfig({ context: { selection } }), /context.selection/);
  assert.throws(() => normalizeConfig({ version: 1, context: { selection: { mode: 'follow', source: 'auto' } } }), /version 2/);
  assert.throws(() => normalizeConfig({ modules: [{ type: 'timing', when: ['active', 'active'] }] }), /duplicate/);
});

test('graphical choices survive style changes, duplication and export with independent module headings', () => {
  const original = normalizeConfig({ appearance: { font: 'system', show_header: false, density: 'spacious', palette: { personal: '#2255bb' } }, modules: [{ type: 'timing', show_header: false, show_table_header: false }] });
  const changed = normalizeConfig({ ...original, appearance: { ...original.appearance, style: 'minimal' } });
  assert.deepEqual(changed.modules, original.modules);
  assert.equal(changed.appearance.font, 'system');
  const duplicated = duplicateModule(changed, changed.modules[0].id);
  duplicated.modules[1].show_header = true;
  assert.equal(duplicated.modules[0].show_header, false);
  assert.equal(duplicated.modules[1].show_table_header, false);
  assert.deepEqual(importConfig(exportConfig(duplicated)), duplicated);
  for (const appearance of [{ font: 'missing' }, { density: 'tiny' }, { show_header: 'false' }]) assert.throws(() => normalizeConfig({ appearance }));
  for (const key of ['show_header', 'show_table_header']) assert.throws(() => normalizeConfig({ modules: [{ type: 'timing', [key]: 'false' }] }));
});

test('accent, branding and surface choices serialize without overwriting focus or custom colors', () => {
  const config = normalizeConfig({ appearance: { accent_mode: 'team', accent_team: 'Ferrari', accent: '#2255bb', logo_size: 'large', logo_style: 'mono', surface: 'soft' }, context: { driver: '16' }, modules: [{ type: 'timing', fields: ['driver', 'last_lap'] }] });
  assert.deepEqual(importConfig(exportConfig(config)), config);
  const changed = normalizeConfig({ ...config, appearance: { ...config.appearance, style: 'minimal', accent_mode: 'neutral' } });
  assert.equal(changed.appearance.accent, '#2255bb');
  assert.equal(changed.appearance.accent_team, 'Ferrari');
  assert.deepEqual(changed.context, config.context);
  assert.deepEqual(changed.modules, config.modules);
  for (const appearance of [{ accent_team: 4 }, { logo_size: 1000 }, { logo_style: 'none' }, { surface: 'css' }, { accent_mode: 'semantic' }]) assert.throws(() => normalizeConfig({ appearance }));
});

test('custom CSS round trips as scoped presentation data and rejects active content', () => {
  const styles = `ha-card {\n  --f1-card-radius: 22px;\n}\n\nf1-module-view[data-module-type="timing"] {\n  --f1-cell-padding: 6px 8px;\n}`;
  const config = normalizeConfig({ styles, modules: [{ type: 'timing' }] });
  assert.equal(config.styles, styles);
  assert.deepEqual(importConfig(exportConfig(config)), config);
  assert.deepEqual(importTemplate(exportTemplate(config, 'Styled timing')).card, config);
  assert.equal(normalizeConfig({}).styles, undefined);
  for (const [value, pattern] of [
    [42, /styles/],
    ['@import "https:\/\/example.com\/theme.css";', /@import/],
    ['ha-card { background: url(https:\/\/example.com\/image.png); }', /url/],
    ['ha-card { color: ${hass.states["sensor.example"].state}; }', /JavaScript templates/],
    ['x'.repeat(CUSTOM_STYLE_MAX_LENGTH + 1), /at most/],
  ]) assert.throws(() => normalizeConfig({ styles: value }), pattern);
});

test('each preset saves without entity IDs and expands to independent editable modules', () => {
  for (const preset of Object.keys(PRESETS)) {
    const value = applyPreset(normalizeConfig({}), preset);
    assert.deepEqual(importConfig(exportConfig(value)), value);
    assert.equal(value.f1_entry_id, '');
    assert.equal(new Set(value.modules.map(module => module.id)).size, value.modules.length);
    if (value.modules[0]) value.modules[0].fields.push('extension');
    assert.ok(!PRESETS[preset].modules[0]?.fields?.includes('extension'));
  }
});

test('named templates round trip independently and reject ambiguous or unsupported input', () => {
  const config = normalizeConfig({ f1_entry_id: 'saved-entry', future_setting: { retained: true }, modules: [{ type: 'timing', fields: ['driver', 'last_lap'] }] });
  const source = exportTemplate(config, '  Race view  ');
  const template = importTemplate(source);
  assert.equal(template.format, 'f1-sensor-template');
  assert.equal(template.version, 1);
  assert.equal(template.name, 'Race view');
  assert.deepEqual(template.card, config);
  template.card.modules[0].fields.push('position');
  assert.deepEqual(config.modules[0].fields, ['driver', 'last_lap']);
  assert.throws(() => exportTemplate(config, '   '), /template.name/);
  assert.throws(() => importTemplate(exportConfig(config)), /template.format/);
  assert.throws(() => importTemplate(JSON.stringify({ format: 'f1-sensor-template', version: 2, name: 'Future', card: config })), /template.version/);
  assert.throws(() => importTemplate(JSON.stringify({ format: 'f1-sensor-template', version: 1, name: 'No card' })), /template.card/);
});

test('style switches, import and editing retain unknown settings and pinned drivers', () => {
  const original = normalizeConfig({ extensions: { future: [1, 'two'] }, appearance: { extra: 'keep' }, modules: [{ id: 'favorite', type: 'timing', driver: '16', fields: ['driver', 'best_lap', 'future'], options: { extension: true } }] });
  const changed = normalizeConfig({ ...original, appearance: { ...original.appearance, style: 'minimal', mode: 'light', palette: { personal: '#2255bb' } } });
  assert.deepEqual(changed.modules, original.modules);
  assert.deepEqual(importConfig(exportConfig(changed)), changed);
  assert.equal(changed.appearance.extra, 'keep');
  assert.deepEqual(changed.extensions, { future: [1, 'two'] });
  assert.deepEqual(configWarnings(changed), [{ module: 'favorite', kind: 'unsupported_field', value: 'future' }]);
});

test('stable IDs preserve identity through duplicate/reorder and do not mutate input', () => {
  const original = normalizeConfig({ modules: [{ type: 'timing', options: { history: 5 } }, { type: 'race_control' }] });
  const saved = exportConfig(original), id = original.modules[0].id;
  const duplicated = duplicateModule(original, id);
  assert.equal(duplicated.modules.length, 3);
  duplicated.modules[1].options.history = 12;
  assert.equal(duplicated.modules[0].options.history, 5);
  const reordered = moveModule(duplicated, id, 2);
  assert.equal(reordered.modules[2].id, id);
  assert.equal(exportConfig(original), saved);
  assert.deepEqual(normalizeConfig(reordered), reordered);
});

test('invalid values and unsafe input produce errors at the offending setting', () => {
  for (const [value, pattern] of [
    [{ version: 3 }, /version/],
    [{ appearance: { logos: 'false' } }, /appearance.logos/],
    [{ appearance: { accent: 'red;display:none' } }, /appearance.accent/],
    [{ modules: [{ type: 'timing', options: { rows: 0 } }] }, /modules.0.options.rows/],
    [{ modules: [{ type: 'timing', options: { sort: 'message' } }] }, /sort/],
    [{ modules: [{ type: 'replay', options: { refresh: 'false' } }] }, /refresh/],
    [{ modules: [{ type: 'timing', fields: ['driver', 'driver'] }] }, /duplicate/],
    [{ modules: [{ type: 'overview', id: 'same' }, { type: 'timing', id: 'same' }] }, /unique/],
    [{ context: { scope: 'group', group: '' } }, /context.group/],
    [{ module: () => {} }, /JSON/],
  ]) assert.throws(() => normalizeConfig(value), pattern);
  assert.throws(() => importConfig('{"__proto__":{"polluted":true}}'), /reserved/);
  assert.throws(() => importConfig('{invalid}'), /invalid JSON/);
  assert.equal({}.polluted, undefined);
});

test('unknown modules remain recoverable rather than being silently discarded', () => {
  const config = importConfig('{"modules":[{"id":"future","type":"future-module","options":{"custom":42}}]}');
  assert.equal(config.modules[0].options.custom, 42);
  assert.equal(configWarnings(config)[0].kind, 'unsupported_module');
  assert.deepEqual(importConfig(exportConfig(config)), config);
});

test('every published module field has a source, semantic metadata and translated UI label', () => {
  for (const definition of Object.values(MODULES)) for (const id of definition.fields) {
    const field = FIELDS[id];
    assert.ok(field, `${definition.id}.${id}`);
    for (const key of ['source', 'path', 'type', 'capability', 'modes', 'sessions', 'identity', 'generation', 'timestamps', 'freshness', 'presentations']) assert.ok(field[key], `${id}.${key}`);
    assert.equal(typeof field.spoiler, 'boolean');
    assert.ok(field.label.en && field.label.sv);
  }
});
