/** Bounded class-local parameter propagation; unresolved dynamic accesses remain visible. */
function walk(node, visit) {
  if (!node || typeof node !== 'object') return;
  if (node.type) visit(node);
  for (const [key, value] of Object.entries(node)) {
    if (['loc', 'start', 'end', 'comments', 'tokens'].includes(key)) continue;
    if (Array.isArray(value)) value.forEach(item => walk(item, visit));
    else if (value && typeof value === 'object') walk(value, visit);
  }
}
const member = node => ['MemberExpression', 'OptionalMemberExpression'].includes(node?.type);
const name = node => node?.type === 'Identifier' ? node.name : node?.type === 'StringLiteral' ? node.value : null;
const property = node => !node?.computed ? name(node?.property) : node?.property?.type === 'StringLiteral' ? node.property.value : null;
const config = node => node?.type === 'Identifier' && node.name === 'config' || member(node) && node.object?.type === 'ThisExpression' && ['config', '_config'].includes(property(node));

function indirectConfigFields(classNode) {
  if (classNode?.type !== 'ClassDeclaration') return [];
  const methods = classNode.body.body.filter(node => node.type === 'ClassMethod');
  const info = new Map(methods.map(method => [name(method.key), { method, params: method.params.map(param => name(param.type === 'AssignmentPattern' ? param.left : param)), slots: new Set() }]));
  const findings = new Map();
  const add = (key, line, kind) => {
    if (!key) return;
    const id = `${key}:${line}:${kind}`;
    findings.set(id, { key, line, kind });
  };
  for (const { method, params, slots } of info.values()) {
    walk(method.body, node => {
      if (member(node) && config(node.object) && node.computed) {
        const index = params.indexOf(name(node.property));
        if (node.property.type === 'Identifier' && index >= 0) slots.add(index);
      }
      // HA form fields identify their configuration name alongside a selector.
      if (node.type === 'ObjectExpression' && node.properties.some(prop => name(prop.key) === 'selector')) {
        const field = node.properties.find(prop => name(prop.key) === 'name');
        if (field?.value?.type === 'StringLiteral') add(field.value.value, field.loc.start.line, 'form_schema');
        else if (field?.value?.type === 'Identifier') {
          const index = params.indexOf(field.value.name);
          if (index >= 0) slots.add(index);
        }
      }
      if (method.static && name(method.key) === 'getStubConfig' && node.type === 'ReturnStatement' && node.argument?.type === 'ObjectExpression') {
        for (const prop of node.argument.properties) {
          if (prop.type === 'ObjectProperty' && !prop.computed && name(prop.key) !== 'type') add(name(prop.key), prop.loc.start.line, 'stub_config');
        }
      }
    });
  }
  // Propagate only this.method(parameter), never similarly named unrelated calls.
  let changed = true;
  while (changed) {
    changed = false;
    for (const { method, params, slots } of info.values()) walk(method.body, node => {
      if (node.type !== 'CallExpression' || !member(node.callee) || node.callee.object.type !== 'ThisExpression') return;
      for (const index of info.get(property(node.callee))?.slots ?? []) {
        const argument = node.arguments[index];
        if (argument?.type === 'StringLiteral') add(argument.value, argument.loc.start.line, 'indirect_config_argument');
        else if (argument?.type === 'Identifier') {
          const callerSlot = params.indexOf(argument.name);
          if (callerSlot >= 0 && !slots.has(callerSlot)) { slots.add(callerSlot); changed = true; }
        }
      }
    });
  }
  return [...findings.values()].sort((a, b) => a.key.localeCompare(b.key) || a.line - b.line || a.kind.localeCompare(b.kind));
}

function computedConfigCoverage(classNode, domains = {}) {
  if (classNode?.type !== 'ClassDeclaration') return { accesses: [] };
  const methods = classNode.body.body.filter(node => node.type === 'ClassMethod');
  const info = new Map(methods.map(method => [name(method.key), {
    method,
    params: method.params.map(param => name(param.type === 'AssignmentPattern' ? param.left : param)),
  }]));
  const nodeId = (methodName, index) => `${methodName}:${index}`;
  const sinks = [];
  for (const [methodName, { method, params }] of info) {
    const arrays = new Map(), loopDomains = new Map();
    walk(method.body, node => {
      if (node.type === 'VariableDeclarator' && node.id?.type === 'Identifier' && node.init?.type === 'ArrayExpression') arrays.set(node.id.name, node.init);
    });
    walk(method.body, node => {
      if (node.type !== 'ForOfStatement' || node.left?.type !== 'VariableDeclaration' || node.right?.type !== 'Identifier') return;
      const pattern = node.left.declarations[0]?.id, values = arrays.get(node.right.name)?.elements;
      if (pattern?.type !== 'ArrayPattern' || !values) return;
      pattern.elements.forEach((element, index) => {
        if (element?.type !== 'Identifier') return;
        const domain = values.map(row => row?.type === 'ArrayExpression' ? row.elements[index]?.value : undefined).filter(value => typeof value === 'string');
        if (domain.length === values.length) loopDomains.set(element.name, domain);
      });
    });
    walk(method.body, node => {
      if (!member(node) || !config(node.object) || !node.computed) return;
      const index = node.property?.type === 'Identifier' ? params.indexOf(node.property.name) : -1;
      const directKeys = node.property?.type === 'Identifier' ? loopDomains.get(node.property.name) ?? [] : [];
      sinks.push({ line: node.loc.start.line, method: methodName, parameter: index >= 0 ? params[index] : null, node: index >= 0 ? nodeId(methodName, index) : null, directKeys });
    });
  }
  const calls = new Map();
  for (const [callerName, { method, params }] of info) walk(method.body, node => {
    if (node.type !== 'CallExpression' || !member(node.callee) || node.callee.object.type !== 'ThisExpression') return;
    const targetName = property(node.callee), target = info.get(targetName);
    if (!target) return;
    for (let index = 0; index < target.params.length; index++) {
      const targetId = nodeId(targetName, index), argument = node.arguments[index];
      const record = { line: node.loc.start.line, kind: 'dynamic', value: argument?.type ?? 'missing' };
      if (argument?.type === 'StringLiteral') Object.assign(record, { kind: 'literal', value: argument.value });
      else if (argument?.type === 'Identifier') {
        const callerIndex = params.indexOf(argument.name);
        if (callerIndex >= 0) Object.assign(record, { kind: 'parameter', value: nodeId(callerName, callerIndex) });
      }
      if (!calls.has(targetId)) calls.set(targetId, []);
      calls.get(targetId).push(record);
    }
  });
  const relevant = new Set(sinks.map(sink => sink.node).filter(Boolean)), keys = new Map(), unresolved = new Map(), edges = [];
  const add = (map, id, value) => {
    if (!map.has(id)) map.set(id, new Set());
    map.get(id).add(value);
  };
  let changed = true;
  while (changed) {
    changed = false;
    for (const id of [...relevant]) {
      if (domains[id]?.length) {
        for (const value of domains[id]) add(keys, id, value);
        continue;
      }
      const inbound = calls.get(id) ?? [];
      if (!inbound.length) add(unresolved, id, 'no class-local call site');
      for (const call of inbound) {
        if (call.kind === 'literal') add(keys, id, call.value);
        else if (call.kind === 'parameter') {
          edges.push([call.value, id]);
          if (!relevant.has(call.value)) { relevant.add(call.value); changed = true; }
        } else add(unresolved, id, `line ${call.line}: ${call.value}`);
      }
    }
  }
  let propagated = true;
  while (propagated) {
    propagated = false;
    for (const [from, to] of edges) for (const [mapFrom, mapTo] of [[keys, keys], [unresolved, unresolved]]) {
      for (const value of mapFrom.get(from) ?? []) {
        const before = mapTo.get(to)?.size ?? 0; add(mapTo, to, value);
        if ((mapTo.get(to)?.size ?? 0) !== before) propagated = true;
      }
    }
  }
  return { accesses: sinks.map(sink => ({
    line: sink.line, method: sink.method, parameter: sink.parameter,
    keys: sink.node ? [...(keys.get(sink.node) ?? [])].sort() : [...sink.directKeys].sort(),
    unresolved: sink.node ? [...(unresolved.get(sink.node) ?? [])].sort() : sink.directKeys.length ? [] : ['computed property is not a method parameter'],
  })) };
}
function sharedConfigFields(ast, className) {
  const findings = [], arrays = new Map();
  const members = node => {
    if (node?.type !== 'ArrayExpression') return [];
    return node.elements.flatMap(item => {
      if (item?.type === 'Identifier') return [item.name];
      // The optional track-map class is already known to exist when analyzed.
      if (item?.type === 'SpreadElement' && item.argument?.type === 'ConditionalExpression') {
        const { test, alternate } = item.argument;
        if (test.type === 'BinaryExpression' && test.operator === '===' && test.left?.type === 'UnaryExpression' && test.left.operator === 'typeof'
          && name(test.left.argument) === className && test.right?.value === 'undefined') return members(alternate);
        // Other conditional spreads remain outside this bounded analysis.
        return [];
      }
      return [];
    });
  };
  walk(ast, node => {
    if (node.type === 'VariableDeclarator' && node.id?.type === 'Identifier' && node.init?.type === 'ArrayExpression') arrays.set(node.id.name, node.init);
  });
  const add = (key, line, kind, extra = {}) => findings.push({ key, line, kind, ...extra });
  walk(ast, node => {
    if (node.type !== 'CallExpression') return;
    if (node.callee?.name === 'installF1EntityAutoBinding' && node.arguments[0]?.name === className && node.arguments[1]?.type === 'ObjectExpression') {
      add('f1_entry_id', node.loc.start.line, 'entity_discovery', { consumer: 'platform/entity-resolver.js' });
      for (const prop of node.arguments[1].properties) if (prop.type === 'ObjectProperty' && !prop.computed) {
        add(name(prop.key), prop.loc.start.line, 'entity_binding', { source: prop.value.type === 'StringLiteral' ? prop.value.value : 'dynamic: review binding expression' });
      }
    }
    if (member(node.callee) && property(node.callee) === 'forEach') {
      const array = arrays.get(name(node.callee.object)) ?? node.callee.object;
      if (!members(array).includes(className)) return;
      if (node.arguments[0]?.name === 'installFontStyleSupport') add('font_style', node.loc.start.line, 'installed_font_support');
      if (node.arguments[0]?.name === 'installNoSpoilerOverlay') add('no_spoiler_entity', node.loc.start.line, 'installed_spoiler_support');
    }
  });
  walk(ast, node => {
    if (node.type !== 'ClassDeclaration' || node.id?.name !== className) return;
    walk(node.body, call => {
      if (call.type !== 'CallExpression' || call.arguments[0]?.type !== 'ThisExpression') return;
      if (['renderThemeModeSelect', 'applyF1ThemeMode'].includes(call.callee?.name)) add('theme_mode', call.loc.start.line, 'shared_theme_helper');
      if (['renderThemeModeSelect', 'renderFontStyleSelect'].includes(call.callee?.name)) add('font_style', call.loc.start.line, 'shared_font_editor');
    });
  });
  return findings.sort((a, b) => a.key.localeCompare(b.key) || a.line - b.line);
}
module.exports = { computedConfigCoverage, indirectConfigFields, sharedConfigFields };
