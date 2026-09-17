const suffix = new URL(import.meta.url).searchParams.get('v');
const { CARD_TYPE, VERSION, MODULES, PRESETS, defaultFields } = await import(`./catalog.js${suffix ? `?v=${encodeURIComponent(suffix)}` : ''}`);

export class ConfigurationError extends Error {
  constructor(path, reason) { super(`${path}: ${reason}`); this.name = 'ConfigurationError'; this.path = path; }
}
const fail = (path, reason) => { throw new ConfigurationError(path, reason); };
const plain = value => value !== null && typeof value === 'object' && !Array.isArray(value);

// Preserve extension keys without retaining mutable input references or executable values.
export function copyConfig(value, path = 'config', depth = 0) {
  if (depth > 40) fail(path, 'nesting is too deep');
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (Array.isArray(value)) return value.map((item, index) => copyConfig(item, `${path}.${index}`, depth + 1));
  if (!plain(value) || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) fail(path, 'expected a JSON value');
  const result = {};
  for (const [key, item] of Object.entries(value)) {
    if (['__proto__', 'constructor', 'prototype'].includes(key)) fail(`${path}.${key}`, 'reserved property');
    result[key] = copyConfig(item, `${path}.${key}`, depth + 1);
  }
  return result;
}
const object = (value, path) => { if (!plain(value)) fail(path, 'expected an object'); return value; };
const text = (value, path) => { if (typeof value !== 'string') fail(path, 'expected text'); return value; };
const choice = (value, values, path) => { if (!values.includes(value)) fail(path, `choose ${values.join(', ')}`); return value; };
const bool = (value, path) => { if (typeof value !== 'boolean') fail(path, 'expected true or false'); return value; };
const integer = (value, min, max, path) => { if (!Number.isInteger(value) || value < min || value > max) fail(path, `expected ${min}–${max}`); return value; };
const strings = (value, path) => {
  if (!Array.isArray(value) || value.some(item => typeof item !== 'string')) fail(path, 'expected a list of names');
  if (new Set(value).size !== value.length) fail(path, 'duplicate names');
  return value;
};

export const APPEARANCE = {
  style: 'f1', mode: 'auto', font: 'auto', show_header: true, density: 'comfortable', accent: '#e10600',
  accent_mode: 'style', accent_team: '', surface: 'style',
  logos: true, logo_style: 'auto', logo_size: 'normal', flags: true, team_colors: true, full_names: false,
  numbers: 'tabular', tyre_style: 'ring', palette: {},
};
export const ACCESSIBILITY = { high_contrast: false, signals: 'shape', motion: 'system', announce: true };
export const PHASES = ['before', 'active', 'finished', 'unknown'];
export const CONTEXT = {
  driver: '', team: '', group: '', scope: 'local', spoilers: 'inherit', viewing_controls: false,
  selection: { mode: 'follow', source: 'auto' }, share: ['focus'],
};

function normalizeSelection(value, path, allowInherit) {
  const selected = copyConfig(object(value, path));
  selected.mode ??= allowInherit ? 'inherit' : 'follow';
  choice(selected.mode, allowInherit ? ['inherit', 'follow', 'pinned'] : ['follow', 'pinned'], `${path}.mode`);
  const allowed = selected.mode === 'inherit' ? ['mode'] : selected.mode === 'follow' ? ['mode', 'source'] : ['mode', 'source', 'season', 'meeting_key', 'session_key'];
  for (const key of Object.keys(selected)) if (!allowed.includes(key)) fail(`${path}.${key}`, `not allowed when mode is ${selected.mode}`);
  if (selected.mode === 'inherit') return selected;
  if (selected.mode === 'follow') {
    selected.source ??= 'auto';
    choice(selected.source, ['auto', 'live', 'replay'], `${path}.source`);
    return selected;
  }
  choice(selected.source, ['live', 'archive', 'replay'], `${path}.source`);
  integer(selected.season, 1950, 9999, `${path}.season`);
  for (const key of ['meeting_key', 'session_key']) {
    text(selected[key], `${path}.${key}`);
    if (!selected[key].trim()) fail(`${path}.${key}`, 'enter a stable source identifier');
  }
  return selected;
}

export function resolveSelection(context, module, group = {}) {
  if (module.selection.mode !== 'inherit') return copyConfig(module.selection);
  if (context.selection.mode === 'pinned') return copyConfig(context.selection);
  if (context.scope === 'group' && context.share.includes('selection') && group.selection) return normalizeSelection(group.selection, 'group.selection', false);
  return copyConfig(context.selection);
}

export function normalizeConfig(input) {
  const config = copyConfig(object(input, 'config'));
  config.type ??= CARD_TYPE;
  choice(config.type, [CARD_TYPE], 'type');
  const inputVersion = config.version ?? VERSION;
  choice(inputVersion, [1, VERSION], 'version');
  if (inputVersion === 1 && (config.context?.selection !== undefined || config.context?.share !== undefined || Array.isArray(config.modules) && config.modules.some(item => item?.selection !== undefined || item?.when !== undefined))) fail('version', 'version 2 is required for session selection and phase visibility');
  config.version = VERSION;
  config.title ??= 'F1 Sensor'; text(config.title, 'title');
  config.f1_entry_id ??= ''; text(config.f1_entry_id, 'f1_entry_id');
  config.layout ??= 'stack'; choice(config.layout, ['stack', 'tabs'], 'layout');
  config.appearance = { ...copyConfig(APPEARANCE), ...object(config.appearance ?? {}, 'appearance') };
  const appearance = config.appearance;
  for (const [key, values] of Object.entries({ style: ['f1', 'ha', 'minimal'], mode: ['auto', 'light', 'dark'], density: ['comfortable', 'compact', 'spacious'], font: ['auto', 'f1', 'system'], logo_style: ['auto', 'color', 'white', 'mono'], logo_size: ['small', 'normal', 'large'], accent_mode: ['style', 'neutral', 'f1', 'team', 'custom'], surface: ['style', 'framed', 'soft', 'flat'], numbers: ['tabular', 'inherit'], tyre_style: ['ring', 'image', 'text', 'both'] })) choice(appearance[key], values, `appearance.${key}`);
  for (const key of ['show_header', 'logos', 'flags', 'team_colors', 'full_names']) bool(appearance[key], `appearance.${key}`);
  const color = (value, path) => { if (typeof value !== 'string' || !/^#[0-9a-f]{6}$/i.test(value)) fail(path, 'expected a six-digit hex color'); };
  color(appearance.accent, 'appearance.accent');
  text(appearance.accent_team, 'appearance.accent_team');
  object(appearance.palette, 'appearance.palette');
  for (const [key, value] of Object.entries(appearance.palette)) color(value, `appearance.palette.${key}`);
  config.accessibility = { ...ACCESSIBILITY, ...object(config.accessibility ?? {}, 'accessibility') };
  for (const key of ['high_contrast', 'announce']) bool(config.accessibility[key], `accessibility.${key}`);
  choice(config.accessibility.signals, ['shape', 'text', 'both'], 'accessibility.signals');
  choice(config.accessibility.motion, ['system', 'reduced'], 'accessibility.motion');
  config.context = { ...copyConfig(CONTEXT), ...object(config.context ?? {}, 'context') };
  for (const key of ['driver', 'team', 'group']) text(config.context[key], `context.${key}`);
  choice(config.context.scope, ['local', 'group'], 'context.scope');
  choice(config.context.spoilers, ['inherit', 'hide'], 'context.spoilers');
  bool(config.context.viewing_controls, 'context.viewing_controls');
  config.context.selection = normalizeSelection(config.context.selection, 'context.selection', false);
  strings(config.context.share, 'context.share');
  for (const value of config.context.share) choice(value, ['focus', 'selection'], 'context.share');
  if (config.context.scope === 'group' && !config.context.group.trim()) fail('context.group', 'enter a group name');
  if (config.modules === undefined) config.modules = copyConfig(PRESETS.weekend.modules);
  if (!Array.isArray(config.modules)) fail('modules', 'expected a list');
  if (config.modules.length > 64) fail('modules', 'at most 64 modules');
  const ids = new Set(config.modules.map(item => item?.id).filter(Boolean));
  config.modules = config.modules.map((item, index) => {
    const path = `modules.${index}`;
    object(item, path); text(item.type, `${path}.type`);
    if (!item.id) { let id = `${item.type}-${index + 1}`; while (ids.has(id)) id += '-new'; item.id = id; ids.add(id); }
    text(item.id, `${path}.id`);
    if (!/^[a-zA-Z0-9_-]{1,100}$/.test(item.id)) fail(`${path}.id`, 'use letters, digits, hyphens or underscores');
    item.title ??= ''; text(item.title, `${path}.title`);
    item.enabled ??= true; bool(item.enabled, `${path}.enabled`);
    for (const key of ['show_header', 'show_table_header']) { item[key] ??= true; bool(item[key], `${path}.${key}`); }
    item.unavailable ??= 'explain'; choice(item.unavailable, ['explain', 'retain', 'hide'], `${path}.unavailable`);
    item.focus_mode ??= 'inherit'; choice(item.focus_mode, ['inherit', 'independent'], `${path}.focus_mode`);
    item.selection = normalizeSelection(item.selection ?? { mode: 'inherit' }, `${path}.selection`, true);
    item.when ??= [...PHASES]; strings(item.when, `${path}.when`);
    for (const value of item.when) choice(value, PHASES, `${path}.when`);
    item.driver ??= ''; text(item.driver, `${path}.driver`);
    item.team ??= ''; text(item.team, `${path}.team`);
    const definition = MODULES[item.type];
    if (item.type === 'archive' && Array.isArray(item.fields) && item.options?.profile == null) item.options = { ...item.options, profile: 'custom' };
    item.fields ??= [...defaultFields(item)];
    strings(item.fields, `${path}.fields`);
    item.options = { ...Object.fromEntries(Object.entries(definition?.options ?? {}).map(([key, spec]) => [key, copyConfig(spec.default)])), ...object(item.options ?? {}, `${path}.options`) };
    for (const [key, spec] of Object.entries(definition?.options ?? {})) {
      const optionPath = `${path}.options.${key}`;
      if (spec.type === 'enum') choice(item.options[key], spec.values, optionPath);
      else if (spec.type === 'integer') integer(item.options[key], spec.min, spec.max, optionPath);
      else if (spec.type === 'boolean') bool(item.options[key], optionPath);
      else if (spec.type === 'source_list') strings(item.options[key], optionPath);
      else if (spec.type === 'lap_selections') {
        strings(item.options[key], optionPath);
        if (item.options[key].length > 4 || item.options[key].some(id => !/^[1-9]\d?:[1-9]\d{0,2}$/.test(id) || Number(id.split(':')[1]) > 500)) fail(optionPath, 'choose at most four valid driver/lap pairs');
      }
      else if (spec.type === 'list') { strings(item.options[key], optionPath); for (const value of item.options[key]) choice(value, spec.values, optionPath); }
      else text(item.options[key], optionPath);
    }
    return item;
  });
  if (new Set(config.modules.map(item => item.id)).size !== config.modules.length) fail('modules', 'module IDs must be unique');
  return config;
}

export function configWarnings(config) {
  return config.modules.flatMap(item => {
    const definition = MODULES[item.type];
    if (!definition) return [{ module: item.id, kind: 'unsupported_module', value: item.type }];
    return item.fields.filter(id => !definition.fields.includes(id)).map(id => ({ module: item.id, kind: 'unsupported_field', value: id }));
  });
}
export function applyPreset(config, preset) {
  if (!PRESETS[preset]) fail('preset', 'unknown preset');
  return normalizeConfig({ ...config, modules: copyConfig(PRESETS[preset].modules) });
}
export function makeModule(type, current = []) {
  if (!MODULES[type]) fail('module', 'unknown module');
  let n = 1; while (current.some(item => item.id === `${type}-${n}`)) n++;
  return normalizeConfig({ modules: [{ type, id: `${type}-${n}` }] }).modules[0];
}
export function duplicateModule(config, id) {
  const result = copyConfig(config), index = result.modules.findIndex(item => item.id === id);
  if (index < 0) fail('module', 'not found');
  let next = `${id}-copy`; while (result.modules.some(item => item.id === next)) next += '-copy';
  result.modules.splice(index + 1, 0, { ...copyConfig(result.modules[index]), id: next });
  return normalizeConfig(result);
}
export function moveModule(config, id, offset) {
  const result = copyConfig(config), index = result.modules.findIndex(item => item.id === id), next = index + offset;
  if (index < 0 || next < 0 || next >= result.modules.length) return result;
  const [item] = result.modules.splice(index, 1); result.modules.splice(next, 0, item);
  return result;
}
export const exportConfig = config => JSON.stringify(normalizeConfig(config), null, 2);
export function importConfig(source) {
  if (typeof source !== 'string' || source.length > 512_000) fail('import', 'expected JSON, at most 512 KB');
  let value; try { value = JSON.parse(source); } catch { fail('import', 'invalid JSON'); }
  return normalizeConfig(value);
}
export function exportTemplate(config, name) {
  if (typeof name !== 'string' || !name.trim() || name.trim().length > 100) fail('template.name', 'enter a name of 1–100 characters');
  return JSON.stringify({ format: 'f1-sensor-template', version: 1, name: name.trim(), card: normalizeConfig(config) }, null, 2);
}
export function importTemplate(source) {
  if (typeof source !== 'string' || source.length > 512_000) fail('template', 'expected JSON, at most 512 KB');
  let value; try { value = JSON.parse(source); } catch { fail('template', 'invalid JSON'); }
  object(value, 'template');
  choice(value.format, ['f1-sensor-template'], 'template.format');
  choice(value.version, [1], 'template.version');
  const name = text(value.name, 'template.name').trim();
  if (!name || name.length > 100) fail('template.name', 'enter a name of 1–100 characters');
  return { format: value.format, version: value.version, name, card: normalizeConfig(object(value.card, 'template.card')) };
}
