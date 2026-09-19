const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

async function mount(page, config, width = 1400) {
  await page.evaluate(({ config, width }) => {
    document.querySelector('#root').style.cssText = `width:${width}px;max-width:100%;`;
    window.mountModular({ config: { layout: 'columns', columns: 3, ...config } });
  }, { config, width });
  await expect(page.locator('f1-module-view').first()).toBeVisible();
}

async function geometry(page) {
  return page.locator('f1-sensor-card .modules > f1-module-view:visible').evaluateAll(nodes => nodes.map(node => {
    const { x, y, width, height, bottom } = node.getBoundingClientRect();
    return { id: node.dataset.moduleId, x, y, width, height, bottom };
  }));
}

test('two-column Timing sits beside Track Map and full-width Race Control starts below them', async ({ page }) => {
  await mount(page, { modules: [
    { id: 'timing', type: 'timing', column_span: 2 },
    { id: 'map', type: 'map' },
    { id: 'control', type: 'race_control', column_span: 'full' },
  ] }, 1100);
  await expect(page.locator('f1-track-map-view')).toBeVisible();
  await expect.poll(async () => {
    const [timing, map] = await geometry(page);
    return Math.abs(timing.y - map.y);
  }).toBeLessThan(1);
  const [timing, map, control] = await geometry(page);
  const gap = map.x - timing.x - timing.width;
  expect(timing.width).toBeCloseTo(map.width * 2 + gap, 0);
  expect(control.width).toBeCloseTo(map.x + map.width - timing.x, 0);
  expect(control.y).toBeGreaterThanOrEqual(Math.max(timing.bottom, map.bottom));
  const a11y = await new AxeBuilder({ page }).include('f1-sensor-card').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(a11y.violations).toEqual([]);
});

test('two, three and four equal columns honor the configured maximum on a wide card', async ({ page }) => {
  for (const columns of [2, 3, 4]) {
    await mount(page, { columns, modules: Array.from({ length: 5 }, (_, i) => ({ id: `m${i}`, type: 'weather' })) });
    await expect.poll(async () => {
      const rows = await geometry(page);
      return rows.filter(row => Math.abs(row.y - rows[0].y) < 1).length;
    }).toBe(columns);
    const rows = await geometry(page);
    expect(rows[columns].y).toBeGreaterThan(rows[0].y);
    for (const row of rows) expect(row.width).toBeCloseTo(rows[0].width, 0);
  }
});

test('row wrapping preserves reading order and clamps spans without creating implicit columns', async ({ page }) => {
  await mount(page, { modules: [
    { id: 'a', type: 'overview', column_span: 2 },
    { id: 'b', type: 'overview', column_span: 2 },
    { id: 'c', type: 'overview' },
    { id: 'd', type: 'overview', column_span: 4 },
  ] });
  const [a, b, c, d] = await geometry(page);
  expect(b.y).toBeGreaterThan(a.y);
  expect(c.y).toBeCloseTo(b.y, 0);
  expect(c.x).toBeGreaterThan(b.x);
  expect(d.y).toBeGreaterThan(b.y);
  expect(d.width).toBeCloseTo(c.x + c.width - b.x, 0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('container-only resizing reflows four to three to two to one and restores saved widths', async ({ page }) => {
  await mount(page, { columns: 4, modules: [
    { id: 'a', type: 'timing', column_span: 2 },
    { id: 'b', type: 'weather' },
    { id: 'c', type: 'weather' },
    { id: 'd', type: 'race_control', column_span: 'full' },
  ] });
  await page.evaluate(() => { window.originalTimingNode = window.fixtureCard.moduleNodes.get('a'); });
  for (const [width, count] of [[1400, 4], [1100, 3], [760, 2], [390, 1], [340, 1], [1400, 4]]) {
    await page.locator('#root').evaluate((node, width) => { node.style.width = `${width}px`; }, width);
    await expect.poll(() => page.locator('f1-sensor-card .modules').evaluate(node => getComputedStyle(node).gridTemplateColumns.split(' ').length)).toBe(count);
    const rows = await geometry(page);
    expect(rows[0].width).toBeGreaterThan(0);
    if (count === 1) {
      expect(rows[1].y).toBeGreaterThanOrEqual(rows[0].bottom);
      for (const row of rows) expect(row.width).toBeCloseTo(rows[0].width, 0);
    }
    expect(await page.locator('f1-sensor-card ha-card').evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  }
  expect(await page.evaluate(() => window.fixtureCard.moduleNodes.get('a') === window.originalTimingNode)).toBe(true);
  expect(await page.evaluate(() => window.fixtureCard.config.modules.map(module => module.column_span))).toEqual([2, 1, 1, 'full']);
});

test('hidden modules release their space and return in source order', async ({ page }) => {
  await mount(page, { modules: [
    { id: 'a', type: 'overview' },
    { id: 'conditional', type: 'weather', visibility: [{ condition: 'state', entity: 'input_boolean.layout', state: 'on' }] },
    { id: 'disabled', type: 'weather', enabled: false },
    { id: 'c', type: 'overview', column_span: 2 },
  ] });
  expect((await geometry(page)).map(row => row.id)).toEqual(['a', 'c']);
  const [a, c] = await geometry(page);
  expect(c.y).toBeCloseTo(a.y, 0);
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.hass = { ...card.hass, states: { ...card.hass.states, 'input_boolean.layout': { state: 'on', attributes: {} } } };
  });
  await expect(page.locator('f1-module-view')).toHaveCount(3);
  const rows = await geometry(page);
  expect(rows.map(row => row.id)).toEqual(['a', 'conditional', 'c']);
  expect(rows[2].y).toBeGreaterThan(rows[1].y);
});

test('switching to stacks and tabs removes grid placement without losing module widths', async ({ page }) => {
  await mount(page, { modules: [{ id: 'a', type: 'overview', column_span: 2 }, { id: 'b', type: 'weather' }] });
  await page.evaluate(() => window.fixtureCard.setConfig({ ...window.fixtureCard.config, layout: 'stack' }));
  await expect.poll(async () => { const [a, b] = await geometry(page); return b.y - a.bottom; }).toBeGreaterThanOrEqual(0);
  await page.evaluate(() => window.fixtureCard.setConfig({ ...window.fixtureCard.config, layout: 'tabs' }));
  await expect(page.locator('f1-module-view:visible')).toHaveCount(1);
  await page.locator('nav').getByRole('button', { name: 'Weather overview', exact: true }).click();
  await expect(page.locator('f1-module-view[data-module-id=b]')).toBeVisible();
  await page.evaluate(() => window.fixtureCard.setConfig({ ...window.fixtureCard.config, layout: 'columns' }));
  await expect(page.locator('f1-module-view:visible')).toHaveCount(2);
  const [a, b] = await geometry(page);
  expect(a.y).toBeCloseTo(b.y, 0);
  expect(a.width).toBeGreaterThan(b.width * 2);
});

test('visual editor persists column count and widths, preserves HA sizing, and offers four-column preview', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, config: {
    grid_options: { columns: 'full' }, modules: [{ id: 'a', type: 'timing' }, { id: 'b', type: 'map' }],
  } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Layout and shared focus', { exact: true }).click();
  await editor.getByLabel('Layout', { exact: true }).selectOption('columns');
  await editor.getByLabel('Maximum columns', { exact: true }).selectOption('3');
  const selected = editor.getByRole('region', { name: 'Selected module', exact: true });
  await selected.getByLabel('Module width', { exact: true }).selectOption('2');
  await expect(editor.locator('.module-width').first()).toHaveText('2 columns');
  await editor.getByLabel('Preview width', { exact: true }).selectOption('extra-wide');
  await expect(editor.locator('.preview-shell')).toHaveCSS('width', '1400px');
  await editor.getByRole('button', { name: 'Move down Timing', exact: true }).focus();
  await page.keyboard.press('Enter');
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.columns).toBe(3);
  expect(saved.modules.map(module => [module.id, module.column_span])).toEqual([['b', 1], ['a', 2]]);
  expect(saved.grid_options).toEqual({ columns: 'full' });
  await editor.getByLabel('Layout', { exact: true }).selectOption('tabs');
  await expect(selected.getByLabel('Module width', { exact: true })).toHaveCount(0);
  await editor.getByLabel('Layout', { exact: true }).selectOption('columns');
  await expect(selected.getByLabel('Module width', { exact: true })).toHaveValue('2');
  await page.reload(); await page.waitForFunction(() => window.modularReady);
  await mount(page, saved, 1100);
  const [b, a] = await geometry(page);
  expect(a.y).toBeCloseTo(b.y, 0);
  expect(a.width).toBeGreaterThan(b.width * 2);
});

test('Swedish editor exposes full-width modules and keeps narrow layout accessible', async ({ page }) => {
  await page.evaluate(() => {
    document.querySelector('#root').style.width = '390px';
    window.mountModular({ editor: true, language: 'sv', config: { layout: 'columns', columns: 3, modules: [{ type: 'overview', column_span: 'full' }] } });
  });
  const editor = page.locator('f1-sensor-card-editor');
  await expect(editor.getByLabel('Modulbredd', { exact: true })).toHaveValue('full');
  await expect(editor.locator('.module-width')).toHaveText('Hela kortets bredd');
  await editor.getByText('Layout och gemensamt fokus', { exact: true }).click();
  await expect(editor.getByLabel('Max antal kolumner', { exact: true })).toHaveValue('3');
  expect(await editor.evaluate(node => node.scrollWidth <= 390)).toBe(true);
  const a11y = await new AxeBuilder({ page }).include('f1-sensor-card-editor').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(a11y.violations).toEqual([]);
});
