/** Generate a reviewable source inventory; unresolved computed settings stay explicit. */
const fs = require('node:fs');
const path = require('node:path');
const { parse } = require('@babel/parser');
const { computedConfigCoverage, indirectConfigFields, sharedConfigFields } = require('./legacy_config_analysis.cjs');

const root = path.resolve(__dirname, '..');
const directory = 'custom_components/f1_sensor/www/f1-sensor-live-data-card';
const source = fs.readFileSync(path.join(root, directory, 'f1-sensor-live-data-card.js'), 'utf8');
const registry = fs.readFileSync(path.join(root, directory, 'platform/card-registry.js'), 'utf8');
const ast = parse(source, { sourceType: 'module' });
const registryAst = parse(registry, { sourceType: 'module' });
function walk(node, visit) {
  if (!node || typeof node !== 'object') return;
  if (node.type) visit(node);
  for (const [key, value] of Object.entries(node)) {
    if (['loc', 'start', 'end', 'comments', 'tokens'].includes(key)) continue;
    if (Array.isArray(value)) value.forEach(item => walk(item, visit));
    else if (value && typeof value === 'object') walk(value, visit);
  }
}
const isMember = node => ['MemberExpression', 'OptionalMemberExpression'].includes(node?.type);
const property = node => !node?.computed && node?.property?.type === 'Identifier' ? node.property.name : node?.property?.type === 'StringLiteral' ? node.property.value : null;
const isConfig = node => node?.type === 'Identifier' && node.name === 'config' || isMember(node) && node.object?.type === 'ThisExpression' && ['config', '_config'].includes(property(node));
const snippet = node => source.slice(node.start, node.end).replace(/\s+/g, ' ').slice(0, 180);
const constantObjectKeys = variable => {
  let values = [];
  walk(ast, node => {
    if (node.type === 'VariableDeclarator' && node.id?.name === variable && node.init?.type === 'ObjectExpression') values = node.init.properties.filter(prop => prop.type === 'ObjectProperty' && !prop.computed).map(prop => prop.key?.name ?? prop.key?.value);
  });
  return values.filter(Boolean);
};
const constantArrayProperty = (variable, field) => {
  let values = [];
  walk(ast, node => {
    if (node.type !== 'VariableDeclarator' || node.id?.name !== variable || node.init?.type !== 'ArrayExpression') return;
    values = node.init.elements.map(item => item?.type === 'ObjectExpression' ? item.properties.find(prop => (prop.key?.name ?? prop.key?.value) === field)?.value?.value : undefined);
  });
  return values.filter(value => typeof value === 'string');
};
const replayEntityKeys = [...new Set([...constantObjectKeys('F1_REPLAY_ENTITY_DEFAULTS'), ...constantArrayProperty('F1_REPLAY_ACTIONS', 'key')])];
const classes = new Map(), registration = new Map();
let definitions;
walk(registryAst, node => {
  if (node.type === 'VariableDeclarator' && node.id.name === 'F1_CARD_DEFINITIONS') definitions = node.init.callee.object.elements.map(row => row.elements.map(value => value.value));
});
walk(ast, node => {
  if (node.type === 'ClassDeclaration') classes.set(node.id.name, node);
  if (node.type === 'CallExpression' && isMember(node.callee) && node.callee.object.name === 'customElements' && property(node.callee) === 'define') registration.set(node.arguments[0]?.value, node.arguments[1]?.name);
});
const analyze = node => {
  const settings = new Map(), unresolved = [];
  walk(node, item => {
    if (isMember(item) && isConfig(item.object)) {
      const key = property(item);
      if (key) { if (!settings.has(key)) settings.set(key, new Set()); settings.get(key).add(item.loc.start.line); }
      else unresolved.push({ line: item.loc.start.line, expression: snippet(item) });
    }
    // Editor callbacks carry computed setting names as literal arguments.
    if (item.type === 'CallExpression' && isMember(item.callee) && ['_valueChanged', '_updateConfig'].includes(property(item.callee)) && item.arguments[0]?.type === 'StringLiteral') {
      const key = item.arguments[0].value;
      if (!settings.has(key)) settings.set(key, new Set());
      settings.get(key).add(item.loc.start.line);
    }
  });
  const indirect = indirectConfigFields(node);
  const domains = node?.id?.name === 'F1ReplayControlCard' ? { '_configuredEntityId:0': replayEntityKeys } : {};
  const computed = computedConfigCoverage(node, domains).accesses;
  const shared = node?.type === 'ClassDeclaration' ? sharedConfigFields(ast, node.id.name) : [];
  for (const { key, line } of [...indirect, ...shared]) {
    if (!settings.has(key)) settings.set(key, new Set());
    settings.get(key).add(line);
  }
  return { fields: [...settings].sort(([a], [b]) => a.localeCompare(b)).map(([key, lines]) => ({ key, lines: [...lines].sort((a, b) => a - b), migration: 'not_reviewed' })), indirect_evidence: indirect, shared_evidence: shared,
    resolved_computed_access: computed.filter(item => !item.unresolved.length),
    computed_access: [...unresolved.filter(item => !computed.some(access => access.line === item.line && !access.unresolved.length)), ...computed.filter(item => item.unresolved.length)] };
};
if (!definitions?.length) throw new Error('Card registry could not be parsed');
const cards = definitions.filter(([type]) => type !== 'f1-sensor-card').map(([type, name]) => {
  const cardClass = registration.get(type), editorClass = registration.get(`${type}-editor`);
  if (!classes.has(cardClass) || !classes.has(editorClass)) throw new Error(`Missing class for ${type}`);
  return { type, name, card_class: cardClass, editor_class: editorClass, card: analyze(classes.get(cardClass)), editor: analyze(classes.get(editorClass)) };
});
const result = {
  format_version: 1,
  source: `${directory}/f1-sensor-live-data-card.js`,
  method: 'Static config access, class-local argument propagation, bounded literal loop domains, the declared replay entity-key domain, HA selector schemas, literal getStubConfig keys, explicit entity binding registrations and known shared font/theme/spoiler installers. Indirect/shared/computed evidence retains source lines and extraction kind. Unresolved computed accesses remain explicit. Other shared helpers, defaults and implicit behavior still require review. This inventory does not claim migration coverage.',
  aliases: [{ type: 'f1-session-archive-card', target: 'f1-last-race-results-card', class: registration.get('f1-session-archive-card'), card: analyze(classes.get(registration.get('f1-session-archive-card'))) }],
  all_config_access: analyze(ast), cards,
};
const destination = path.join(root, 'quality/legacy-card-options.json');
const rendered = `${JSON.stringify(result, null, 2)}\n`;
if (process.argv.includes('--check')) {
  if (fs.readFileSync(destination, 'utf8') !== rendered) throw new Error('quality/legacy-card-options.json is stale; run this script without --check');
} else fs.writeFileSync(destination, rendered);
const unresolvedCount = [...cards, ...result.aliases].reduce((total, card) => total + (card.card?.computed_access?.length ?? 0) + (card.editor?.computed_access?.length ?? 0), 0);
console.log(`Inventoried ${cards.length} legacy cards, ${result.aliases.length} alias and ${cards.reduce((n, card) => n + card.card.fields.length, 0)} card setting accesses. Unresolved computed accesses: ${unresolvedCount}. Shared defaults and migration meaning remain separately reviewable.`);
