const { test } = require('node:test');
const assert = require('node:assert/strict');
const { parse } = require('@babel/parser');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const { computedConfigCoverage, indirectConfigFields } = require('../scripts/legacy_config_analysis.cjs');
const analyze = source => indirectConfigFields(parse(source).program.body[0]);

test('tracks config keys through multiple class-local calls and retains dynamic boundaries', () => {
  const fields = analyze(`class Weather {
    get(key) { return this.config[key]; }
    state(key) { return this.get(key); }
    weather() { return this.state('weather_entity'); }
    other() { return unrelated.state('not_a_key'); }
    dynamic() { return this.state(window.chosenKey); }
    label() { return this.title('not_config'); }
    title(text) { return text; }
  }`);
  assert.deepEqual(fields.map(field => field.key), ['weather_entity']);
  assert.equal(fields[0].line, 4);
});

test('recognizes selector names, literal stub keys and defaults without treating labels as keys', () => {
  const fields = analyze(`class Editor {
    static getStubConfig() { return { type: 'custom:example', show_header: true, ...defaults }; }
    picker(name, label) { return [{ name, label, selector: { entity: {} } }]; }
    toggle(name, label = '') { return [{ name, label, selector: { boolean: {} } }]; }
    render() { return [this.picker('entity', 'The source'), this.toggle('prefer_live', 'Live'), {name:'theme_mode', selector:{select:{}}}]; }
  }`);
  assert.deepEqual([...new Set(fields.map(field => field.key))].sort(), ['entity', 'prefer_live', 'show_header', 'theme_mode']);
  assert.ok(fields.some(field => field.kind === 'stub_config'));
  assert.ok(fields.some(field => field.kind === 'form_schema'));
});

test('recursive wrappers terminate and parameter positions are preserved', () => {
  const fields = analyze(`class Card {
    a(label, key) { return [this.b(key), this.config[key]]; }
    b(key) { return this.a('Label', key); }
    render() { return this.a('Not a key', 'session_entity'); }
  }`);
  assert.deepEqual(fields.map(field => field.key), ['session_entity']);
});

test('computed access coverage proves literal call chains and retains real dynamic boundaries', () => {
  const ast = parse(`class Card {
    get(key) { return this.config[key]; }
    wrapper(key) { return this.get(key); }
    render() { return [this.wrapper('session_entity'), this.wrapper(window.dynamicKey)]; }
  }`).program.body[0];
  const access = computedConfigCoverage(ast).accesses[0];
  assert.deepEqual(access.keys, ['session_entity']);
  assert.deepEqual(access.unresolved, ['line 4: MemberExpression']);

  const resolved = parse(`class Editor {
    value(name) { return this._config[name]; }
    render() { return [this.value('show_header'), this.value('show_footer')]; }
  }`).program.body[0];
  assert.deepEqual(computedConfigCoverage(resolved).accesses[0], {
    line: 2, method: 'value', parameter: 'name', keys: ['show_footer', 'show_header'], unresolved: [],
  });
});

test('computed access coverage resolves bounded loop values and declared external domains', () => {
  const loop = parse(`class Timing {
    colors() {
      const map = [['color_fastest', 'fast'], ['color_personal', 'personal']];
      for (const [key, token] of map) use(this.config[key], token);
    }
  }`).program.body[0];
  assert.deepEqual(computedConfigCoverage(loop).accesses[0].keys, ['color_fastest', 'color_personal']);
  assert.deepEqual(computedConfigCoverage(loop).accesses[0].unresolved, []);

  const external = parse(`class Replay {
    entity(key) { return this.config[key]; }
    run(action) { return this.entity(action.key); }
  }`).program.body[0];
  assert.deepEqual(computedConfigCoverage(external, { 'entity:0': ['play_entity', 'pause_entity'] }).accesses[0], {
    line: 2, method: 'entity', parameter: 'key', keys: ['pause_entity', 'play_entity'], unresolved: [],
  });
});

test('shared discovery records only explicitly installed sources and support', () => {
  const { sharedConfigFields } = require('../scripts/legacy_config_analysis.cjs');
  const ast = parse(`
    class First { render() { return renderThemeModeSelect(this); } }
    class Second {}
    class Optional {}
    installF1EntityAutoBinding(First, { entity: 'weather', selected: config => config.mode });
    installF1EntityAutoBinding(Second, { entity: 'other' });
    const fonts = [First, ...(typeof Optional === 'undefined' ? [] : [Optional])];
    fonts.forEach(installFontStyleSupport);
    [Second].forEach(installNoSpoilerOverlay);
  `);
  const first = sharedConfigFields(ast, 'First');
  assert.deepEqual([...new Set(first.map(field => field.key))].sort(), ['entity', 'f1_entry_id', 'font_style', 'selected', 'theme_mode']);
  assert.equal(first.find(field => field.key === 'entity').source, 'weather');
  assert.match(first.find(field => field.key === 'selected').source, /dynamic/);
  assert.deepEqual(sharedConfigFields(ast, 'Optional').map(field => field.key), ['font_style']);
  assert.ok(sharedConfigFields(ast, 'Second').some(field => field.key === 'no_spoiler_entity'));
  assert.equal(sharedConfigFields(ast, 'Missing').length, 0);
});

test('checked-in legacy inventory and migration audit match current source', () => {
  const root = path.resolve(__dirname, '..');
  execFileSync(process.execPath, [path.join(root, 'scripts/inventory_card_options.cjs'), '--check'], { cwd: root, stdio: 'pipe' });
  execFileSync(process.execPath, [path.join(root, 'scripts/audit_card_migration.mjs'), '--check'], { cwd: root, stdio: 'pipe' });
});
