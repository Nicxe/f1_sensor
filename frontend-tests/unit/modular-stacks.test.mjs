import assert from 'node:assert/strict';
import test from 'node:test';
import {
  normalizeConfig, layoutStacks, placeModuleInStack, moveStack, changeStackWidth,
  removeModule, duplicateModule, moveModule, applyPreset, exportConfig, importConfig,
  exportTemplate, importTemplate,
} from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';

const source = () => ({
  layout: 'stacks', columns: 4, grid_options: { columns: 'full', rows: 'auto' },
  modules: [
    { id: 'overview', type: 'overview', column_span: 'full' },
    { id: 'timing', type: 'timing', column_span: 3 },
    { id: 'tyres', type: 'tyres', options: { content: 'history' } },
    { id: 'map', type: 'map' },
  ],
  stacks: [
    { id: 'overview-stack', column_span: 'full', modules: ['overview'] },
    { id: 'timing-stack', column_span: 3, modules: ['timing'] },
    { id: 'side-stack', column_span: 1, modules: ['tyres', 'map'] },
  ],
});

test('independent module stacks preserve their grouping, widths and module settings across transfers', () => {
  const input = source(), original = structuredClone(input), config = normalizeConfig(input);
  assert.deepEqual(input, original);
  assert.deepEqual(config.stacks, original.stacks);
  assert.deepEqual(importConfig(exportConfig(config)), config);
  assert.deepEqual(importTemplate(exportTemplate(config, 'Race stacks')).card, config);
  assert.deepEqual(config.grid_options, original.grid_options);
  assert.equal(config.modules[2].options.content, 'history');
  for (const layout of ['stack', 'tabs', 'columns']) {
    const switched = normalizeConfig({ ...config, layout });
    assert.deepEqual(switched.stacks, config.stacks);
    assert.deepEqual(normalizeConfig({ ...switched, layout: 'stacks' }), config);
  }
});

test('entering independent stacks creates one group per existing module without changing old layouts', () => {
  const input = source(); delete input.stacks;
  for (const layout of ['stack', 'tabs', 'columns']) {
    const config = normalizeConfig({ ...input, layout });
    assert.equal(config.stacks, undefined);
    assert.deepEqual(layoutStacks(config).map(stack => [stack.column_span, stack.modules]), [
      ['full', ['overview']], [3, ['timing']], [1, ['tyres']], [1, ['map']],
    ]);
  }
  const config = normalizeConfig(input);
  assert.deepEqual(config.stacks.map(stack => [stack.column_span, stack.modules]), [
    ['full', ['overview']], [3, ['timing']], [1, ['tyres']], [1, ['map']],
  ]);
  assert.equal(new Set(config.stacks.map(stack => stack.id)).size, 4);
});

test('unassigned modules receive independent groups while configured empty groups remain valid', () => {
  const input = source();
  input.stacks = [{ id: 'empty', modules: [] }, { id: 'side', modules: ['tyres', 'map'] }];
  const config = normalizeConfig(input);
  assert.deepEqual(config.stacks[0], { id: 'empty', column_span: 1, modules: [] });
  assert.deepEqual(config.stacks[1], { id: 'side', column_span: 1, modules: ['tyres', 'map'] });
  assert.deepEqual(config.stacks.slice(2).map(stack => [stack.column_span, stack.modules]), [['full', ['overview']], [3, ['timing']]]);
  assert.deepEqual(config.stacks.flatMap(stack => stack.modules).sort(), ['map', 'overview', 'timing', 'tyres']);
});

test('malformed stack structure, placement references and widths fail at their setting', () => {
  for (const stacks of [true, 1, {}, 'side']) assert.throws(() => normalizeConfig({ ...source(), stacks }), /stacks:/);
  for (const invalid of [
    { id: 'bad id', modules: ['overview'] },
    { id: 'bad', modules: 'overview' },
    { id: 'bad', modules: ['missing'] },
    { id: 'bad', modules: ['overview', 'overview'] },
  ]) assert.throws(() => normalizeConfig({ ...source(), stacks: [invalid] }), /stacks\.0/);
  assert.throws(() => normalizeConfig({ ...source(), stacks: [{ id: 'same', modules: ['overview'] }, { id: 'same', modules: ['timing'] }] }), /stacks/);
  assert.throws(() => normalizeConfig({ ...source(), stacks: [{ id: 'one', modules: ['overview'] }, { id: 'two', modules: ['overview'] }] }), /stacks/);
  for (const column_span of [0, 5, 1.5, '2', 'auto', true, {}, []]) {
    assert.throws(() => normalizeConfig({ ...source(), stacks: [{ id: 'bad', modules: ['overview'], column_span }] }), /stacks\.0\.column_span/);
  }
});

test('placing modules in a stack changes only placement and removes an emptied source stack', () => {
  const config = normalizeConfig(source()), original = structuredClone(config);
  const moved = placeModuleInStack(config, 'map', 'timing-stack', 0);
  assert.deepEqual(config, original);
  assert.deepEqual(moved.stacks.find(stack => stack.id === 'timing-stack').modules, ['map', 'timing']);
  assert.deepEqual(moved.stacks.find(stack => stack.id === 'side-stack').modules, ['tyres']);
  assert.deepEqual(moved.modules.map(module => module.id), ['overview', 'map', 'timing', 'tyres']);
  for (const module of moved.modules) assert.deepEqual(module, config.modules.find(item => item.id === module.id));
  const merged = placeModuleInStack(moved, 'tyres', 'timing-stack');
  assert.equal(merged.stacks.some(stack => stack.id === 'side-stack'), false);
  assert.deepEqual(merged.stacks.find(stack => stack.id === 'timing-stack').modules, ['map', 'timing', 'tyres']);
});

test('modules can reorder within their stack or become an independent stack with preserved settings', () => {
  const config = normalizeConfig(source());
  const reordered = placeModuleInStack(config, 'map', 'side-stack', 0);
  assert.deepEqual(reordered.stacks.find(stack => stack.id === 'side-stack').modules, ['map', 'tyres']);
  const detached = placeModuleInStack(reordered, 'tyres', '');
  assert.deepEqual(detached.stacks.at(-1).modules, ['tyres']);
  assert.deepEqual(detached.stacks.find(stack => stack.id === 'side-stack').modules, ['map']);
  assert.equal(new Set(detached.stacks.map(stack => stack.id)).size, detached.stacks.length);
  assert.equal(detached.modules.find(module => module.id === 'tyres').options.content, 'history');
});

test('moving and resizing a stack preserves child order and saved module widths', () => {
  const config = normalizeConfig(source());
  const moved = moveStack(config, 'side-stack', -1);
  assert.deepEqual(moved.stacks.map(stack => stack.id), ['overview-stack', 'side-stack', 'timing-stack']);
  assert.deepEqual(moved.modules.map(module => module.id), ['overview', 'tyres', 'map', 'timing']);
  const resized = changeStackWidth(moved, 'side-stack', 'full');
  assert.equal(resized.stacks[1].column_span, 'full');
  assert.deepEqual(resized.stacks[1].modules, ['tyres', 'map']);
  assert.deepEqual(resized.modules.map(module => [module.id, module.column_span]), moved.modules.map(module => [module.id, module.column_span]));
});

test('imported stack order is the effective module order for the editor and keyboard moves', () => {
  const input = {
    layout: 'stacks', modules: [{ id: 'a', type: 'weather' }, { id: 'b', type: 'weather' }, { id: 'c', type: 'weather' }],
    stacks: [{ id: 'first', modules: ['c'] }, { id: 'second', modules: ['a', 'b'] }],
  };
  const config = normalizeConfig(input);
  assert.deepEqual(config.modules.map(module => module.id), ['c', 'a', 'b']);
  assert.deepEqual(input.modules.map(module => module.id), ['a', 'b', 'c']);
  const within = moveModule(config, 'b', -1);
  assert.deepEqual(within.stacks.map(stack => stack.modules), [['c'], ['b', 'a']]);
  assert.deepEqual(within.modules.map(module => module.id), ['c', 'b', 'a']);
  const across = moveModule(config, 'a', -1);
  assert.deepEqual(across.stacks.map(stack => stack.modules), [['a', 'c'], ['b']]);
  assert.deepEqual(across.modules.map(module => module.id), ['a', 'c', 'b']);
  const emptied = moveModule(config, 'c', 1);
  assert.deepEqual(emptied.stacks.map(stack => stack.modules), [['a', 'c', 'b']]);
  assert.deepEqual(emptied.modules.map(module => module.id), ['a', 'c', 'b']);
  assert.deepEqual(moveModule(config, 'c', -1), config);
  assert.deepEqual(moveModule(config, 'b', 1), config);
});

test('duplication and deletion keep stack references valid and presets replace their old layout groups', () => {
  const config = normalizeConfig(source());
  const copied = duplicateModule(config, 'tyres'), duplicate = copied.modules.find(module => module.id !== 'tyres' && module.type === 'tyres');
  assert.ok(duplicate);
  assert.deepEqual(copied.stacks.find(stack => stack.id === 'side-stack').modules, ['tyres', duplicate.id, 'map']);
  const removed = removeModule(copied, 'timing');
  assert.equal(removed.modules.some(module => module.id === 'timing'), false);
  assert.equal(removed.stacks.some(stack => stack.id === 'timing-stack'), false);
  assert.deepEqual(importConfig(exportConfig(removed)), removed);
  const preset = applyPreset(config, 'weekend');
  assert.equal(preset.stacks.some(stack => stack.id === 'side-stack'), false);
  assert.deepEqual(preset.stacks.flatMap(stack => stack.modules), preset.modules.map(module => module.id));
});
