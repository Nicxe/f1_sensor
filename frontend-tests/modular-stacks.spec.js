const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const raceLayout = () => ({
  layout: 'stacks', columns: 4, grid_options: { columns: 'full' },
  modules: [
    { id: 'overview', type: 'overview', fields: ['session', 'track_status'] },
    { id: 'timing', type: 'timing', options: { history: 5 } },
    { id: 'tyres', type: 'tyres', options: { content: 'history', rows: 1, show_legend: false } },
    { id: 'map', type: 'map' },
  ],
  stacks: [
    { id: 'overview-stack', column_span: 'full', modules: ['overview'] },
    { id: 'timing-stack', column_span: 3, modules: ['timing'] },
    { id: 'side-stack', column_span: 1, modules: ['tyres', 'map'] },
  ],
});
const moduleView = (page, id) => page.locator(`f1-sensor-card f1-module-view[data-module-id="${id}"]`);
const box = locator => locator.evaluate(node => {
  const { x, y, width, height, bottom } = node.getBoundingClientRect();
  return { x, y, width, height, bottom };
});

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.setViewportSize({ width: 1500, height: 1100 });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

async function mount(page, config = raceLayout(), editor = false) {
  await page.evaluate(({ config, editor }) => {
    document.querySelector('main').style.maxWidth = 'none';
    document.querySelector('#root').style.cssText = 'width:1400px;max-width:100%;';
    window.mountModular({ config, editor, nativePreview: false });
    window.changes = [];
    window.fixtureCard.addEventListener('config-changed', event => window.changes.push(event.detail.config));
  }, { config, editor });
  if (editor) {
    await page.locator('f1-sensor-card-editor button[aria-controls="module-arrangement"]').click();
    const arranger = page.locator('f1-module-arranger');
    await expect(arranger.locator('.tile')).toHaveCount(config.modules.length);
    return arranger;
  }
  await expect(moduleView(page, config.modules[0].id)).toBeVisible();
}

test('Tyre history and Track map stack directly beside taller Timing inside one F1 card', async ({ page }) => {
  await mount(page);
  await expect(page.locator('f1-track-map-view')).toBeVisible();
  await expect(page.locator('f1-tyre-history-view .driver-row')).toHaveCount(1);
  const overview = await box(moduleView(page, 'overview'));
  const timing = await box(moduleView(page, 'timing'));
  const tyres = await box(moduleView(page, 'tyres'));
  const map = await box(moduleView(page, 'map'));
  expect(timing.y).toBeGreaterThanOrEqual(overview.bottom);
  expect(tyres.y).toBeCloseTo(timing.y, 0);
  expect(tyres.x).toBeGreaterThan(timing.x + timing.width);
  expect(map.x).toBeCloseTo(tyres.x, 0);
  expect(map.width).toBeCloseTo(tyres.width, 0);
  expect(map.y - tyres.bottom).toBeGreaterThanOrEqual(0);
  expect(map.y - tyres.bottom).toBeLessThan(32);
  expect(map.y).toBeLessThan(timing.bottom);
  const columnGap = tyres.x - timing.x - timing.width;
  expect(timing.width).toBeCloseTo(tyres.width * 3 + columnGap * 2, 0);
  expect(overview.width).toBeCloseTo(timing.width + columnGap + tyres.width, 0);
  await expect(page.locator('f1-sensor-card')).toHaveCount(1);
  expect(await page.locator('f1-sensor-card ha-card').evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
});

test('expanding Tyre history moves only the following module and preserves Timing and module state', async ({ page }) => {
  await mount(page);
  const history = page.locator('f1-tyre-history-view');
  const driver = history.locator('.driver-row').first();
  await expect(driver).toBeVisible();
  const before = { timing: await box(moduleView(page, 'timing')), tyres: await box(moduleView(page, 'tyres')), map: await box(moduleView(page, 'map')) };
  await page.evaluate(() => { window.originalMap = window.fixtureCard.moduleNodes.get('map'); });
  await driver.press('Enter');
  await expect(driver).toHaveAttribute('aria-expanded', 'true');
  await expect(history.locator('.stints')).toBeVisible();
  const after = { timing: await box(moduleView(page, 'timing')), tyres: await box(moduleView(page, 'tyres')), map: await box(moduleView(page, 'map')) };
  expect(after.tyres.height).toBeGreaterThan(before.tyres.height);
  expect(after.map.y - before.map.y).toBeCloseTo(after.tyres.height - before.tyres.height, 0);
  expect(after.timing).toEqual(before.timing);
  expect(after.map.y - after.tyres.bottom).toBeCloseTo(before.map.y - before.tyres.bottom, 0);
  expect(await page.evaluate(() => window.fixtureCard.moduleNodes.get('map') === window.originalMap)).toBe(true);
  await driver.press('Enter');
  await expect(driver).toHaveAttribute('aria-expanded', 'false');
  expect((await box(moduleView(page, 'map'))).y).toBeCloseTo(before.map.y, 0);
});

test('hidden children and empty stacks release their space and return to their saved group', async ({ page }) => {
  const config = raceLayout();
  config.modules.find(module => module.id === 'tyres').visibility = [{ condition: 'state', entity: 'input_boolean.layout', state: 'on' }];
  config.modules.find(module => module.id === 'map').enabled = false;
  config.modules.push({ id: 'weather', type: 'weather' });
  config.stacks.push({ id: 'empty-stack', column_span: 'full', modules: [] }, { id: 'weather-stack', column_span: 1, modules: ['weather'] });
  await mount(page, config);
  await expect(moduleView(page, 'tyres')).toHaveCount(0);
  await expect(moduleView(page, 'map')).toHaveCount(0);
  const timing = await box(moduleView(page, 'timing'));
  expect((await box(moduleView(page, 'weather'))).y).toBeCloseTo(timing.y, 0);
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.hass = { ...card.hass, states: { ...card.hass.states, 'input_boolean.layout': { state: 'on', attributes: {} } } };
  });
  await expect(moduleView(page, 'tyres')).toBeVisible();
  expect((await box(moduleView(page, 'tyres'))).y).toBeCloseTo(timing.y, 0);
  expect((await box(moduleView(page, 'weather'))).y).toBeGreaterThanOrEqual(timing.bottom);
  await expect(moduleView(page, 'map')).toHaveCount(0);
});

test('container resizing clamps stack widths and preserves child order and existing module nodes', async ({ page }) => {
  await mount(page);
  await page.evaluate(() => { window.originalNodes = new Map(window.fixtureCard.moduleNodes); });
  for (const [width, count] of [[1400, 4], [1100, 3], [760, 2], [390, 1], [340, 1], [1400, 4]]) {
    await page.locator('#root').evaluate((node, value) => { node.style.width = `${value}px`; }, width);
    await expect.poll(() => page.locator('f1-sensor-card .modules').evaluate(node => getComputedStyle(node).gridTemplateColumns.split(' ').length)).toBe(count);
    const timing = await box(moduleView(page, 'timing')), tyres = await box(moduleView(page, 'tyres')), map = await box(moduleView(page, 'map'));
    expect(tyres.x).toBeCloseTo(map.x, 0);
    expect(map.y - tyres.bottom).toBeGreaterThanOrEqual(0);
    expect(map.y - tyres.bottom).toBeLessThan(32);
    if (count === 1) {
      expect(tyres.y).toBeGreaterThanOrEqual(timing.bottom);
      expect(timing.width).toBeCloseTo(tyres.width, 0);
    }
    expect(await page.locator('f1-sensor-card ha-card').evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  }
  expect(await page.evaluate(() => [...window.originalNodes].every(([id, node]) => window.fixtureCard.moduleNodes.get(id) === node))).toBe(true);
  expect(await page.evaluate(() => window.fixtureCard.config.stacks.map(stack => stack.column_span))).toEqual(['full', 3, 1]);
});

test('resizing stacks preserves expanded module state and accessible card content', async ({ page }) => {
  await mount(page);
  const driver = page.locator('f1-tyre-history-view .driver-row').first();
  await driver.press('Enter');
  await expect(driver).toHaveAttribute('aria-expanded', 'true');
  await page.evaluate(() => {
    const card = window.fixtureCard;
    window.originalHistory = card.moduleNodes.get('tyres');
    card.setConfig({ ...card.config, stacks: [card.config.stacks[0], { ...card.config.stacks[1], column_span: 2 }, { ...card.config.stacks[2], column_span: 2 }] });
  });
  await expect(driver).toHaveAttribute('aria-expanded', 'true');
  expect(await page.evaluate(() => window.fixtureCard.moduleNodes.get('tyres') === window.originalHistory)).toBe(true);
  const a11y = await new AxeBuilder({ page }).include('f1-sensor-card').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(a11y.violations).toEqual([]);
});

test('pointer drop inserts a module into another stack as one undoable edit', async ({ page }) => {
  const config = raceLayout();
  config.stacks[2].modules = ['tyres'];
  config.stacks.push({ id: 'map-stack', column_span: 1, modules: ['map'] });
  const board = await mount(page, config, true);
  const source = board.locator('[data-id="map"] [data-handle="move"]');
  const target = board.locator('.dropzone[data-stack-id="side-stack"][data-position="1"]');
  await source.scrollIntoViewIfNeeded();
  const handle = await source.boundingBox();
  await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
  await page.mouse.down();
  await page.mouse.move(handle.x + handle.width / 2 + 10, handle.y + handle.height / 2, { steps: 3 });
  await target.scrollIntoViewIfNeeded();
  const destination = await target.boundingBox();
  await page.mouse.move(destination.x + destination.width / 2, destination.y + destination.height / 2, { steps: 8 });
  expect(await page.evaluate(() => window.changes.length)).toBe(0);
  await page.mouse.up();
  await expect.poll(() => page.evaluate(() => window.fixtureCard.config.stacks.find(stack => stack.id === 'side-stack').modules)).toEqual(['tyres', 'map']);
  expect(await page.evaluate(() => window.changes.length)).toBe(1);
  expect(await page.evaluate(() => window.savedConfig.stacks.some(stack => stack.id === 'map-stack'))).toBe(false);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  expect(await page.evaluate(() => window.fixtureCard.config.stacks)).toEqual(config.stacks);
});

test('adjacent drops are no-ops and Escape cancels an unfinished move between stacks', async ({ page }) => {
  const config = raceLayout(), board = await mount(page, config, true);
  for (const position of [1, 2]) {
    const source = board.locator('[data-id="map"] [data-handle="move"]');
    await source.scrollIntoViewIfNeeded();
    const handle = await source.boundingBox();
    await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
    await page.mouse.down();
    await page.mouse.move(handle.x + handle.width / 2 + 10, handle.y + handle.height / 2, { steps: 3 });
    const target = board.locator(`.dropzone[data-stack-id="side-stack"][data-position="${position}"]`);
    await target.scrollIntoViewIfNeeded();
    const destination = await target.boundingBox();
    await page.mouse.move(destination.x + destination.width / 2, destination.y + destination.height / 2, { steps: 6 });
    await page.mouse.up();
    expect(await page.evaluate(() => window.changes.length)).toBe(0);
    expect(await page.evaluate(() => window.fixtureCard.config.stacks)).toEqual(config.stacks);
  }
  const source = board.locator('[data-id="map"] [data-handle="move"]');
  await source.scrollIntoViewIfNeeded();
  const handle = await source.boundingBox();
  await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
  await page.mouse.down();
  await page.mouse.move(handle.x + handle.width / 2 + 10, handle.y + handle.height / 2, { steps: 3 });
  const target = board.locator('.dropzone[data-stack-id="timing-stack"][data-position="1"]');
  await target.scrollIntoViewIfNeeded();
  const destination = await target.boundingBox();
  await page.mouse.move(destination.x + destination.width / 2, destination.y + destination.height / 2, { steps: 6 });
  await page.keyboard.press('Escape');
  await page.mouse.up();
  expect(await page.evaluate(() => window.changes.length)).toBe(0);
  expect(await page.evaluate(() => window.fixtureCard.config.stacks)).toEqual(config.stacks);
  expect(await board.evaluate(node => node.gesture === null && node.frame === null)).toBe(true);
});

test('keyboard handles move and resize whole stacks with their children and Undo restores the move', async ({ page }) => {
  const board = await mount(page, raceLayout(), true);
  const group = board.locator('.stack-group[data-stack-id="side-stack"]');
  const move = group.locator('[data-handle="stack-move"]');
  await move.focus();
  await page.keyboard.press('ArrowLeft');
  expect(await page.evaluate(() => window.savedConfig.stacks.map(stack => stack.id))).toEqual(['overview-stack', 'side-stack', 'timing-stack']);
  expect(await page.evaluate(() => window.savedConfig.modules.map(module => module.id))).toEqual(['overview', 'tyres', 'map', 'timing']);
  await expect(move).toBeFocused();
  expect(await page.evaluate(() => window.changes.length)).toBe(1);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  const resize = group.locator('[data-handle="stack-resize"]');
  await resize.focus();
  await page.keyboard.press('ArrowRight');
  expect(await page.evaluate(() => window.savedConfig.stacks.find(stack => stack.id === 'side-stack').column_span)).toBe(2);
  expect(await page.evaluate(() => window.savedConfig.stacks.find(stack => stack.id === 'side-stack').modules)).toEqual(['tyres', 'map']);
  expect(await page.evaluate(() => window.savedConfig.modules.map(module => module.column_span))).toEqual([1, 1, 1, 1]);
});

test('stack destination and width controls work without dragging and survive switching layouts', async ({ page }) => {
  const board = await mount(page, raceLayout(), true);
  await board.locator('[data-id="map"] .choose').click();
  await board.getByLabel('Move to stack', { exact: true }).selectOption('timing-stack');
  expect(await page.evaluate(() => window.savedConfig.stacks.find(stack => stack.id === 'timing-stack').modules)).toEqual(['timing', 'map']);
  await board.getByLabel('Stack width', { exact: true }).selectOption('2');
  expect(await page.evaluate(() => window.savedConfig.stacks.find(stack => stack.id === 'timing-stack').column_span)).toBe(2);
  const saved = await page.evaluate(() => window.savedConfig.stacks);
  await board.getByLabel('Module layout', { exact: true }).selectOption('columns');
  await board.getByLabel('Module layout', { exact: true }).selectOption('stacks');
  expect(await page.evaluate(() => window.savedConfig.stacks)).toEqual(saved);
  await board.getByLabel('Move to stack', { exact: true }).selectOption('__new__');
  expect(await page.evaluate(() => window.savedConfig.stacks.at(-1).modules)).toEqual(['map']);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await board.locator('.scroll').evaluate(node => node.scrollWidth > node.clientWidth)).toBe(true);
  const a11y = await new AxeBuilder({ page }).include('f1-sensor-card-editor').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(a11y.violations).toEqual([]);
});
